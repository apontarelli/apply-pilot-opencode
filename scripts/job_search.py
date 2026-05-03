#!/usr/bin/env python3
"""Company-first job search command center CLI."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "APPLICATIONS" / "_ops" / "job_search.sqlite"
DEFAULT_PIPELINE_PATH = REPO_ROOT / "APPLICATIONS" / "_ops" / "job_pipeline.jsonl"
QUERY_PACK_REGISTRY_PATH = REPO_ROOT / "config" / "job_search_query_packs.json"
SCHEMA_VERSION = 4
OPEN_ACTION_STATUSES = ("queued", "in_progress", "blocked", "rescheduled")
TERMINAL_ACTION_STATUSES = ("done", "skipped")
ACTION_QUEUES = ("screen", "apply", "follow_up", "research", "artifact", "classify")
ATS_TYPES = ("greenhouse", "lever", "ashby")
QUERY_SOURCES = (
    "linkedin_mcp",
    "official_company_page",
    "ats_greenhouse",
    "ats_lever",
    "ats_ashby",
    "manual_browser",
)
SOURCE_STATUSES = ("active", "paused", "archived")
QUERY_RUN_STATUSES = ("planned", "running", "completed", "failed", "partial")
QUERY_RESULT_STATUSES = ("pending", "accepted", "rejected", "duplicate")
POLL_SCREEN_FIT_SCORE = 75
POLL_IGNORED_FIT_SCORE = 35
HTTP_TIMEOUT_SECONDS = 20
HTTP_USER_AGENT = "apply-pilot-job-search/1.0"
JOB_GENERATED_ACTIONS = (
    ("screen", "screen_role", "Promising role needs screening."),
    ("apply", "apply", "Role is marked ready to apply."),
    ("follow_up", "follow_up", "Application submitted; follow up in 5-7 business days."),
    ("classify", "classify_outcome", "Rejection needs outcome classification."),
)
COMPANY_STATUSES = ("active", "watch", "cooldown", "archived")
JOB_STATUSES = (
    "discovered",
    "screening",
    "ignored_by_filter",
    "ready_to_apply",
    "applied",
    "interviewing",
    "rejected",
    "closed",
    "archived",
)
ARTIFACT_STATUSES = ("idea", "queued", "drafting", "ready", "sent", "archived")
GAP_SEVERITIES = ("low", "medium", "high")
GAP_STATUSES = ("open", "in_progress", "resolved", "wont_fix")
EVENT_TYPES = (
    "application_submitted",
    "rejection_received",
    "interview",
    "message_sent",
    "coffee_chat",
    "referral_ask",
    "artifact_sent",
    "gap_identified",
    "status_changed",
    "note",
)
NO_INTERVIEW_COOLDOWN_DAYS = 45
INTERVIEW_LOOP_COOLDOWN_DAYS = 120
LIKELY_DUPLICATE_WINDOW_DAYS = 60
HYGIENE_ACTION_QUEUES = ("follow_up", "apply", "classify")
HYGIENE_COMPANY_ACTIVITY_DAYS = 14
HYGIENE_PENDING_OUTCOME_DAYS = 14
HYGIENE_UNSCHEDULED_ACTION_DAYS = 7
GENERIC_TITLE_TOKENS = {
    "associate",
    "director",
    "group",
    "head",
    "ii",
    "iii",
    "lead",
    "manager",
    "principal",
    "product",
    "program",
    "senior",
    "staff",
    "sr",
    "the",
}


@dataclass(frozen=True)
class DiscoveredJob:
    title: str
    canonical_url: str | None
    source_job_id: str | None
    location: str | None = None
    remote_status: str | None = None
    compensation_signal: str | None = None


@dataclass(frozen=True)
class PollStoreResult:
    status: str
    job_id: int | None = None


@dataclass(frozen=True)
class QueryPack:
    name: str
    label: str
    default_repeatable: bool
    description: str
    queries: tuple[str, ...]

    @property
    def pack_type(self) -> str:
        return "default" if self.default_repeatable else "exception"


@dataclass(frozen=True)
class CompanyImportOutcome:
    row_number: int
    company_name: str | None
    company_state: str
    source_state: str
    detail: str | None = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    tier INTEGER CHECK (tier BETWEEN 1 AND 3),
    lanes TEXT,
    why_interesting TEXT,
    fit_thesis TEXT,
    known_gaps TEXT,
    products_used TEXT,
    target_roles TEXT,
    career_url TEXT,
    ats_type TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'watch', 'cooldown', 'archived')),
    cooldown_until TEXT,
    last_touched_at TEXT,
    last_checked_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_sources (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL
        CHECK (source_type IN ('greenhouse', 'lever', 'ashby')),
    source_key TEXT NOT NULL,
    source_url TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived')),
    last_polled_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(company_id, source_type, source_key)
);

CREATE INDEX IF NOT EXISTS idx_company_sources_status
    ON company_sources(status, source_type);

CREATE TABLE IF NOT EXISTS query_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    pack TEXT,
    query_text TEXT NOT NULL,
    sort_mode TEXT,
    status TEXT NOT NULL DEFAULT 'completed'
        CHECK (status IN ('planned', 'running', 'completed', 'failed', 'partial')),
    result_count INTEGER NOT NULL DEFAULT 0 CHECK (result_count >= 0),
    accepted_count INTEGER NOT NULL DEFAULT 0 CHECK (accepted_count >= 0),
    rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    duplicate_count INTEGER NOT NULL DEFAULT 0 CHECK (duplicate_count >= 0),
    notes TEXT,
    raw_source_reference TEXT,
    import_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_query_runs_created
    ON query_runs(created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS query_run_results (
    id INTEGER PRIMARY KEY,
    query_run_id INTEGER NOT NULL REFERENCES query_runs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    company_name TEXT,
    title TEXT NOT NULL,
    canonical_url TEXT,
    source_job_id TEXT,
    location TEXT,
    remote_status TEXT,
    compensation_signal TEXT,
    result_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (result_status IN ('pending', 'accepted', 'rejected', 'duplicate')),
    duplicate_job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    duplicate_level TEXT,
    duplicate_reason TEXT,
    notes TEXT,
    raw_source_reference TEXT,
    raw_payload TEXT,
    result_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(query_run_id, result_key)
);

CREATE INDEX IF NOT EXISTS idx_query_run_results_run
    ON query_run_results(query_run_id, ordinal, id);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    canonical_url TEXT,
    source TEXT NOT NULL,
    source_job_id TEXT,
    location TEXT,
    remote_status TEXT,
    role_level TEXT,
    lane TEXT,
    status TEXT NOT NULL DEFAULT 'discovered'
        CHECK (
            status IN (
                'discovered',
                'screening',
                'ignored_by_filter',
                'ready_to_apply',
                'applied',
                'interviewing',
                'rejected',
                'closed',
                'archived'
            )
        ),
    discovery_status TEXT,
    fit_score INTEGER CHECK (fit_score BETWEEN 0 AND 100),
    relationship_path TEXT,
    artifact_opportunity TEXT,
    recommended_resume TEXT,
    materials_status TEXT,
    application_folder TEXT,
    material_paths TEXT,
    compensation_signal TEXT,
    rejection_reason TEXT,
    application_outcome TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_canonical_url
    ON jobs(canonical_url)
    WHERE canonical_url IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_source_id
    ON jobs(source, source_job_id)
    WHERE source_job_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    title TEXT,
    source TEXT,
    link TEXT,
    relationship_strength TEXT,
    last_contacted_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(company_id, link)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idea'
        CHECK (status IN ('idea', 'queued', 'drafting', 'ready', 'sent', 'archived')),
    thesis TEXT,
    link TEXT,
    path TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (link IS NOT NULL OR path IS NOT NULL OR status IN ('idea', 'queued', 'drafting'))
);

CREATE TABLE IF NOT EXISTS gaps (
    id INTEGER PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    gap_type TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('low', 'medium', 'high')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'resolved', 'wont_fix')),
    resolution_action TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (company_id IS NOT NULL OR job_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    artifact_id INTEGER REFERENCES artifacts(id) ON DELETE SET NULL,
    gap_id INTEGER REFERENCES gaps(id) ON DELETE SET NULL,
    queue TEXT NOT NULL
        CHECK (queue IN ('screen', 'apply', 'follow_up', 'research', 'artifact', 'classify')),
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'in_progress', 'done', 'blocked', 'skipped', 'rescheduled')),
    due_at TEXT,
    completed_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (status = 'done' AND completed_at IS NOT NULL)
        OR (status <> 'done' AND completed_at IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_actions_queue_status_due
    ON actions(queue, status, due_at);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    artifact_id INTEGER REFERENCES artifacts(id) ON DELETE SET NULL,
    gap_id INTEGER REFERENCES gaps(id) ON DELETE SET NULL,
    action_id INTEGER REFERENCES actions(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    happened_at TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_company_happened
    ON events(company_id, happened_at);

CREATE TRIGGER IF NOT EXISTS trg_jobs_company_immutable
BEFORE UPDATE OF company_id ON jobs
WHEN NEW.company_id <> OLD.company_id
BEGIN
    SELECT RAISE(ABORT, 'job company_id is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_contacts_company_immutable
BEFORE UPDATE OF company_id ON contacts
WHEN NEW.company_id <> OLD.company_id
BEGIN
    SELECT RAISE(ABORT, 'contact company_id is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_artifacts_company_immutable
BEFORE UPDATE OF company_id ON artifacts
WHEN NEW.company_id <> OLD.company_id
BEGIN
    SELECT RAISE(ABORT, 'artifact company_id is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_gaps_company_immutable
BEFORE UPDATE OF company_id ON gaps
WHEN COALESCE(NEW.company_id, -1) <> COALESCE(OLD.company_id, -1)
BEGIN
    SELECT RAISE(ABORT, 'gap company_id is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_actions_company_immutable
BEFORE UPDATE OF company_id ON actions
WHEN NEW.company_id <> OLD.company_id
BEGIN
    SELECT RAISE(ABORT, 'action company_id is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_events_company_immutable
BEFORE UPDATE OF company_id ON events
WHEN NEW.company_id <> OLD.company_id
BEGIN
    SELECT RAISE(ABORT, 'event company_id is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_artifacts_same_company_insert
BEFORE INSERT ON artifacts
WHEN NEW.job_id IS NOT NULL
    AND EXISTS (
        SELECT 1 FROM jobs
        WHERE jobs.id = NEW.job_id
            AND jobs.company_id <> NEW.company_id
    )
BEGIN
    SELECT RAISE(ABORT, 'artifact job belongs to a different company');
END;

CREATE TRIGGER IF NOT EXISTS trg_artifacts_same_company_update
BEFORE UPDATE OF company_id, job_id ON artifacts
WHEN NEW.job_id IS NOT NULL
    AND EXISTS (
        SELECT 1 FROM jobs
        WHERE jobs.id = NEW.job_id
            AND jobs.company_id <> NEW.company_id
    )
BEGIN
    SELECT RAISE(ABORT, 'artifact job belongs to a different company');
END;

CREATE TRIGGER IF NOT EXISTS trg_gaps_same_company_insert
BEFORE INSERT ON gaps
WHEN NEW.company_id IS NOT NULL
    AND NEW.job_id IS NOT NULL
    AND EXISTS (
        SELECT 1 FROM jobs
        WHERE jobs.id = NEW.job_id
            AND jobs.company_id <> NEW.company_id
    )
BEGIN
    SELECT RAISE(ABORT, 'gap job belongs to a different company');
END;

CREATE TRIGGER IF NOT EXISTS trg_gaps_same_company_update
BEFORE UPDATE OF company_id, job_id ON gaps
WHEN NEW.company_id IS NOT NULL
    AND NEW.job_id IS NOT NULL
    AND EXISTS (
        SELECT 1 FROM jobs
        WHERE jobs.id = NEW.job_id
            AND jobs.company_id <> NEW.company_id
    )
BEGIN
    SELECT RAISE(ABORT, 'gap job belongs to a different company');
END;

CREATE TRIGGER IF NOT EXISTS trg_actions_same_company_insert
BEFORE INSERT ON actions
WHEN (NEW.job_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM jobs
        WHERE jobs.id = NEW.job_id
            AND jobs.company_id <> NEW.company_id
    ))
    OR (NEW.contact_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM contacts
        WHERE contacts.id = NEW.contact_id
            AND contacts.company_id <> NEW.company_id
    ))
    OR (NEW.artifact_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM artifacts
        WHERE artifacts.id = NEW.artifact_id
            AND artifacts.company_id <> NEW.company_id
    ))
    OR (NEW.gap_id IS NOT NULL AND EXISTS (
        SELECT 1
        FROM gaps
        LEFT JOIN jobs ON jobs.id = gaps.job_id
        WHERE gaps.id = NEW.gap_id
            AND COALESCE(gaps.company_id, jobs.company_id) <> NEW.company_id
    ))
BEGIN
    SELECT RAISE(ABORT, 'action reference belongs to a different company');
END;

CREATE TRIGGER IF NOT EXISTS trg_actions_same_company_update
BEFORE UPDATE OF company_id, job_id, contact_id, artifact_id, gap_id ON actions
WHEN (NEW.job_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM jobs
        WHERE jobs.id = NEW.job_id
            AND jobs.company_id <> NEW.company_id
    ))
    OR (NEW.contact_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM contacts
        WHERE contacts.id = NEW.contact_id
            AND contacts.company_id <> NEW.company_id
    ))
    OR (NEW.artifact_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM artifacts
        WHERE artifacts.id = NEW.artifact_id
            AND artifacts.company_id <> NEW.company_id
    ))
    OR (NEW.gap_id IS NOT NULL AND EXISTS (
        SELECT 1
        FROM gaps
        LEFT JOIN jobs ON jobs.id = gaps.job_id
        WHERE gaps.id = NEW.gap_id
            AND COALESCE(gaps.company_id, jobs.company_id) <> NEW.company_id
    ))
BEGIN
    SELECT RAISE(ABORT, 'action reference belongs to a different company');
END;

CREATE TRIGGER IF NOT EXISTS trg_events_same_company_insert
BEFORE INSERT ON events
WHEN (NEW.job_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM jobs
        WHERE jobs.id = NEW.job_id
            AND jobs.company_id <> NEW.company_id
    ))
    OR (NEW.contact_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM contacts
        WHERE contacts.id = NEW.contact_id
            AND contacts.company_id <> NEW.company_id
    ))
    OR (NEW.artifact_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM artifacts
        WHERE artifacts.id = NEW.artifact_id
            AND artifacts.company_id <> NEW.company_id
    ))
    OR (NEW.gap_id IS NOT NULL AND EXISTS (
        SELECT 1
        FROM gaps
        LEFT JOIN jobs ON jobs.id = gaps.job_id
        WHERE gaps.id = NEW.gap_id
            AND COALESCE(gaps.company_id, jobs.company_id) <> NEW.company_id
    ))
    OR (NEW.action_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM actions
        WHERE actions.id = NEW.action_id
            AND actions.company_id <> NEW.company_id
    ))
BEGIN
    SELECT RAISE(ABORT, 'event reference belongs to a different company');
END;

CREATE TRIGGER IF NOT EXISTS trg_events_same_company_update
BEFORE UPDATE OF company_id, job_id, contact_id, artifact_id, gap_id, action_id ON events
WHEN (NEW.job_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM jobs
        WHERE jobs.id = NEW.job_id
            AND jobs.company_id <> NEW.company_id
    ))
    OR (NEW.contact_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM contacts
        WHERE contacts.id = NEW.contact_id
            AND contacts.company_id <> NEW.company_id
    ))
    OR (NEW.artifact_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM artifacts
        WHERE artifacts.id = NEW.artifact_id
            AND artifacts.company_id <> NEW.company_id
    ))
    OR (NEW.gap_id IS NOT NULL AND EXISTS (
        SELECT 1
        FROM gaps
        LEFT JOIN jobs ON jobs.id = gaps.job_id
        WHERE gaps.id = NEW.gap_id
            AND COALESCE(gaps.company_id, jobs.company_id) <> NEW.company_id
    ))
    OR (NEW.action_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM actions
        WHERE actions.id = NEW.action_id
            AND actions.company_id <> NEW.company_id
    ))
BEGIN
    SELECT RAISE(ABORT, 'event reference belongs to a different company');
END;
"""


OPEN_ACTION_DEDUPE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_actions_open_dedupe
    ON actions(
        company_id,
        queue,
        kind,
        COALESCE(job_id, -1),
        COALESCE(contact_id, -1),
        COALESCE(artifact_id, -1),
        COALESCE(gap_id, -1)
    )
    WHERE status IN ('queued', 'in_progress', 'blocked', 'rescheduled');
"""

SOURCE_DEFINITIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS company_sources (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL
        CHECK (source_type IN ('greenhouse', 'lever', 'ashby')),
    source_key TEXT NOT NULL,
    source_url TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived')),
    last_polled_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(company_id, source_type, source_key)
);

CREATE INDEX IF NOT EXISTS idx_company_sources_status
    ON company_sources(status, source_type);
"""

QUERY_RUN_SCHEMA = """
CREATE TABLE IF NOT EXISTS query_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    pack TEXT,
    query_text TEXT NOT NULL,
    sort_mode TEXT,
    status TEXT NOT NULL DEFAULT 'completed'
        CHECK (status IN ('planned', 'running', 'completed', 'failed', 'partial')),
    result_count INTEGER NOT NULL DEFAULT 0 CHECK (result_count >= 0),
    accepted_count INTEGER NOT NULL DEFAULT 0 CHECK (accepted_count >= 0),
    rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    duplicate_count INTEGER NOT NULL DEFAULT 0 CHECK (duplicate_count >= 0),
    notes TEXT,
    raw_source_reference TEXT,
    import_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_query_runs_created
    ON query_runs(created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS query_run_results (
    id INTEGER PRIMARY KEY,
    query_run_id INTEGER NOT NULL REFERENCES query_runs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    company_name TEXT,
    title TEXT NOT NULL,
    canonical_url TEXT,
    source_job_id TEXT,
    location TEXT,
    remote_status TEXT,
    compensation_signal TEXT,
    result_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (result_status IN ('pending', 'accepted', 'rejected', 'duplicate')),
    duplicate_job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    duplicate_level TEXT,
    duplicate_reason TEXT,
    notes TEXT,
    raw_source_reference TEXT,
    raw_payload TEXT,
    result_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(query_run_id, result_key)
);

CREATE INDEX IF NOT EXISTS idx_query_run_results_run
    ON query_run_results(query_run_id, ordinal, id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def add_business_days(start: datetime, days: int) -> datetime:
    current = start
    remaining = days
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_due_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return parse_utc(value).date()
    except ValueError:
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None


def due_state(due_at: str | None, *, today: date | None = None) -> str:
    if not due_at:
        return "unscheduled"
    today = today or datetime.now(timezone.utc).date()
    due_date = parse_due_date(due_at)
    if due_date is None:
        return "scheduled"
    if due_date < today:
        return "stale"
    if due_date == today:
        return "due_today"
    return "upcoming"


def company_name_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).casefold()


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url.strip())
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    cleaned = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        query="",
        fragment="",
    )
    return urlunsplit(cleaned)


def normalize_match_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def normalize_title(value: str | None) -> str:
    return normalize_match_text(value)


def title_keywords(value: str | None) -> set[str]:
    return {
        token
        for token in normalize_title(value).split()
        if token and token not in GENERIC_TITLE_TOKENS
    }


def parse_optional_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parse_utc(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def is_materially_different_role(candidate: sqlite3.Row, prior: sqlite3.Row) -> bool:
    if candidate["lane"] and prior["lane"] and candidate["lane"] != prior["lane"]:
        return True

    candidate_tokens = title_keywords(candidate["title"])
    prior_tokens = title_keywords(prior["title"])
    if candidate_tokens and prior_tokens and candidate_tokens.isdisjoint(prior_tokens):
        return True

    return False


def load_query_pack_registry(
    path: Path = QUERY_PACK_REGISTRY_PATH,
) -> dict[str, QueryPack]:
    if not path.exists():
        raise FileNotFoundError(f"Query pack registry not found: {path}")

    try:
        raw_registry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid query pack registry JSON at {path}: {error.msg}"
        ) from error

    if not isinstance(raw_registry, dict):
        raise ValueError("Query pack registry must be a JSON object")
    raw_packs = raw_registry.get("packs")
    if not isinstance(raw_packs, list) or not raw_packs:
        raise ValueError("Query pack registry must include a non-empty packs list")

    packs: dict[str, QueryPack] = {}
    for index, raw_pack in enumerate(raw_packs, start=1):
        if not isinstance(raw_pack, dict):
            raise ValueError(f"Query pack #{index} must be an object")

        name = str(raw_pack.get("name") or "").strip().upper()
        label = str(raw_pack.get("label") or "").strip()
        description = str(raw_pack.get("description") or "").strip()
        default_repeatable = raw_pack.get("default_repeatable")
        raw_queries = raw_pack.get("queries")

        if not name:
            raise ValueError(f"Query pack #{index} is missing name")
        if name in packs:
            raise ValueError(f"Duplicate query pack: {name}")
        if not label:
            raise ValueError(f"Query pack {name} is missing label")
        if not isinstance(default_repeatable, bool):
            raise ValueError(
                f"Query pack {name} default_repeatable must be true or false"
            )
        if not description:
            raise ValueError(f"Query pack {name} is missing description")
        if not isinstance(raw_queries, list) or not raw_queries:
            raise ValueError(f"Query pack {name} must include non-empty queries")

        queries = tuple(str(query).strip() for query in raw_queries)
        if any(not query for query in queries):
            raise ValueError(f"Query pack {name} includes a blank query")

        packs[name] = QueryPack(
            name=name,
            label=label,
            default_repeatable=default_repeatable,
            description=description,
            queries=queries,
        )

    default_names = {pack.name for pack in packs.values() if pack.default_repeatable}
    if default_names != {"AI", "FINTECH"}:
        raise ValueError(
            "Default repeatable query packs must be exactly AI and FINTECH"
        )

    return packs


def get_query_pack(name: str) -> QueryPack:
    normalized = name.strip().upper()
    packs = load_query_pack_registry()
    pack = packs.get(normalized)
    if pack is None:
        available = ", ".join(sorted(packs))
        raise ValueError(
            f"Unknown query pack: {name}. Available packs: {available}"
        )
    return pack


def format_query_pack_summary(pack: QueryPack) -> str:
    reason_label = "requires_reason" if not pack.default_repeatable else "repeatable"
    return (
        f"{pack.name}\t{pack.pack_type}\t{reason_label}\t"
        f"queries={len(pack.queries)}\t{pack.label}"
    )


def validate_query_pack_run(pack: QueryPack, reason: str | None) -> str | None:
    normalized_reason = (reason or "").strip()
    if pack.default_repeatable:
        return normalized_reason or None
    if not normalized_reason:
        raise ValueError(
            f"Query pack {pack.name} is an exception pack. Broad query runs with "
            f"non-FINTECH/AI packs require --reason."
        )
    return normalized_reason


def latest_rejected_job(
    connection: sqlite3.Connection,
    *,
    company_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT jobs.*
        FROM events
        JOIN jobs ON jobs.id = events.job_id
        WHERE events.company_id = ?
            AND events.event_type = 'rejection_received'
        ORDER BY events.happened_at DESC, events.id DESC
        LIMIT 1
        """,
        (company_id,),
    ).fetchone()


def job_can_bypass_company_cooldown(
    connection: sqlite3.Connection,
    *,
    job: sqlite3.Row,
    now: str,
) -> bool:
    company = connection.execute(
        "SELECT cooldown_until FROM companies WHERE id = ?",
        (job["company_id"],),
    ).fetchone()
    cooldown_until = parse_optional_utc(company["cooldown_until"] if company else None)
    if cooldown_until is None or cooldown_until <= parse_utc(now):
        return True

    prior = latest_rejected_job(connection, company_id=int(job["company_id"]))
    return prior is not None and is_materially_different_role(job, prior)


def job_duplicate_matches(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    title: str,
    canonical_url: str | None,
    source: str | None,
    source_job_id: str | None,
    location: str | None,
    remote_status: str | None,
    now: str,
) -> list[dict[str, object]]:
    normalized_url = normalize_url(canonical_url)
    normalized_title = normalize_title(title)
    normalized_location = normalize_match_text(location)
    normalized_remote = normalize_match_text(remote_status)
    window_start = (parse_utc(now) - timedelta(days=LIKELY_DUPLICATE_WINDOW_DAYS)).isoformat()

    matches: list[dict[str, object]] = []
    rows = connection.execute(
        """
        SELECT jobs.*, companies.name AS company_name
        FROM jobs
        JOIN companies ON companies.id = jobs.company_id
        ORDER BY jobs.id
        """
    ).fetchall()
    for row in rows:
        if normalized_url and normalize_url(row["canonical_url"]) == normalized_url:
            matches.append(
                {
                    "level": "strong",
                    "reason": "normalized_url",
                    "job_id": row["id"],
                    "title": row["title"],
                    "company": row["company_name"],
                }
            )
            continue
        if (
            source
            and source_job_id
            and row["source_job_id"]
            and normalize_match_text(row["source"]) == normalize_match_text(source)
            and row["source_job_id"] == source_job_id
        ):
            matches.append(
                {
                    "level": "strong",
                    "reason": "source_job_id",
                    "job_id": row["id"],
                    "title": row["title"],
                    "company": row["company_name"],
                }
            )
            continue
        if int(row["company_id"]) != company_id:
            continue
        same_title = normalize_title(row["title"]) == normalized_title
        same_location = (
            normalized_location
            and normalize_match_text(row["location"]) == normalized_location
        ) or (
            normalized_remote
            and normalize_match_text(row["remote_status"]) == normalized_remote
        )
        if (
            row["status"] not in ("closed", "archived")
            and same_title
            and same_location
            and row["created_at"] >= window_start
        ):
            matches.append(
                {
                    "level": "likely",
                    "reason": "same_company_title_location_window",
                    "job_id": row["id"],
                    "title": row["title"],
                    "company": row["company_name"],
                }
            )
    return matches


def format_duplicate_match(match: dict[str, object]) -> str:
    return (
        f"job duplicate level={match['level']} existing_id={match['job_id']} "
        f"reason={match['reason']} company={match['company']} title={match['title']}"
    )


def normalize_import_part(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def query_run_import_key(
    *,
    source: str,
    pack: str | None,
    query_text: str,
    sort_mode: str | None,
    raw_source_reference: str | None,
) -> str:
    parts = [
        normalize_import_part(source),
        normalize_import_part(pack),
        normalize_import_part(query_text),
        normalize_import_part(sort_mode),
        normalize_import_part(raw_source_reference),
    ]
    return "\x1f".join(parts)


def query_result_key(
    *,
    company_name: str | None,
    title: str,
    canonical_url: str | None,
    source_job_id: str | None,
    location: str | None,
    raw_source_reference: str | None,
) -> str:
    if raw_source_reference:
        return f"raw:{normalize_import_part(raw_source_reference)}"
    normalized_url = normalize_url(canonical_url)
    if normalized_url:
        return f"url:{normalized_url}"
    if source_job_id:
        return f"source_job_id:{normalize_import_part(source_job_id)}"
    return "candidate:" + "\x1f".join(
        [
            normalize_import_part(company_name),
            normalize_import_part(title),
            normalize_import_part(location),
        ]
    )


def parse_json_object(value: str, *, label: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid {label}: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"Invalid {label}: expected JSON object")
    return parsed


def read_query_import_payload(args: argparse.Namespace) -> dict[str, object]:
    payload: dict[str, object] = {}
    if args.file:
        path = Path(args.file)
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid query import file {path}: {error.msg}") from error
        if not isinstance(parsed, dict):
            raise ValueError(f"Invalid query import file {path}: expected JSON object")
        payload.update(parsed)

    field_map = {
        "source": args.source,
        "pack": args.pack,
        "query_text": args.query_text,
        "sort_mode": args.sort_mode,
        "status": args.status,
        "result_count": args.result_count,
        "notes": args.notes,
        "raw_source_reference": args.raw_source_reference,
    }
    for key, value in field_map.items():
        if value is not None:
            payload[key] = value

    result_json = getattr(args, "result_json", None) or []
    if result_json:
        results = list(payload.get("results") or [])
        if not isinstance(results, list):
            raise ValueError("Invalid query import payload: results must be an array")
        results.extend(
            parse_json_object(value, label="--result-json")
            for value in result_json
        )
        payload["results"] = results
    return payload


def payload_string(
    payload: dict[str, object],
    *keys: str,
    required: bool = False,
) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    if required:
        raise ValueError(f"query import requires {keys[0]}")
    return None


def payload_status(payload: dict[str, object]) -> str:
    status = payload_string(payload, "status") or "completed"
    if status not in QUERY_RUN_STATUSES:
        raise ValueError(
            "query import status must be one of: "
            + ", ".join(QUERY_RUN_STATUSES)
        )
    return status


def payload_non_negative_int(payload: dict[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"query import {key} must be a non-negative integer") from error
    if parsed < 0:
        raise ValueError(f"query import {key} must be a non-negative integer")
    return parsed


def result_status(payload: dict[str, object]) -> str:
    status = payload_string(payload, "result_status", "status", "decision") or "pending"
    if status == "pass":
        status = "rejected"
    if status not in QUERY_RESULT_STATUSES:
        raise ValueError(
            "query result status must be one of: "
            + ", ".join(QUERY_RESULT_STATUSES)
        )
    return status


def query_import_results(payload: dict[str, object]) -> list[dict[str, object]]:
    results = payload.get("results") or []
    if not isinstance(results, list):
        raise ValueError("Invalid query import payload: results must be an array")
    normalized: list[dict[str, object]] = []
    for index, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            raise ValueError(f"Invalid query result #{index}: expected object")
        title = payload_string(result, "title", required=True)
        assert title is not None
        canonical_url = normalize_url(payload_string(result, "canonical_url", "url"))
        normalized.append(
            {
                "ordinal": int(result.get("ordinal") or index),
                "company_name": payload_string(result, "company_name", "company"),
                "title": title,
                "canonical_url": canonical_url,
                "source_job_id": payload_string(result, "source_job_id", "source_id", "id"),
                "location": payload_string(result, "location"),
                "remote_status": payload_string(result, "remote_status", "remote"),
                "compensation_signal": payload_string(result, "compensation_signal", "compensation"),
                "result_status": result_status(result),
                "notes": payload_string(result, "notes"),
                "raw_source_reference": payload_string(
                    result,
                    "raw_source_reference",
                    "raw_reference",
                    "source_reference",
                ),
                "raw_payload": json.dumps(result, sort_keys=True),
            }
        )
    return normalized


def find_company_id_by_name(
    connection: sqlite3.Connection,
    company_name: str | None,
) -> int | None:
    if not company_name:
        return None
    row = connection.execute(
        "SELECT id FROM companies WHERE name_key = ?",
        (company_name_key(company_name),),
    ).fetchone()
    return int(row["id"]) if row else None


def duplicate_for_query_result(
    connection: sqlite3.Connection,
    *,
    source: str,
    result: dict[str, object],
    now: str,
) -> dict[str, object] | None:
    company_id = find_company_id_by_name(
        connection,
        str(result["company_name"]) if result["company_name"] else None,
    )
    matches = job_duplicate_matches(
        connection,
        company_id=company_id or -1,
        title=str(result["title"]),
        canonical_url=str(result["canonical_url"]) if result["canonical_url"] else None,
        source=source,
        source_job_id=(
            str(result["source_job_id"]) if result["source_job_id"] else None
        ),
        location=str(result["location"]) if result["location"] else None,
        remote_status=(
            str(result["remote_status"]) if result["remote_status"] else None
        ),
        now=now,
    )
    return matches[0] if matches else None


def split_configured_terms(value: str | None) -> list[str]:
    if not value:
        return []
    return [
        term.strip()
        for term in re.split(r"[,;\n|]+", value)
        if term.strip()
    ]


def first_configured_lane(lanes: str | None) -> str | None:
    lanes = split_configured_terms(lanes)
    return lanes[0] if lanes else None


def title_matches_target_role(title: str, target_role: str) -> bool:
    normalized_title = normalize_title(title)
    normalized_target = normalize_title(target_role)
    if not normalized_target:
        return False
    if normalized_target in normalized_title:
        return True

    target_tokens = set(normalized_target.split()) - GENERIC_TITLE_TOKENS
    title_tokens = set(normalized_title.split())
    return bool(target_tokens) and target_tokens.issubset(title_tokens)


def classify_polled_job(
    company: sqlite3.Row,
    discovered: DiscoveredJob,
) -> tuple[str, int, str | None, str]:
    target_roles = split_configured_terms(company["target_roles"])
    if any(title_matches_target_role(discovered.title, role) for role in target_roles):
        return (
            "screening",
            POLL_SCREEN_FIT_SCORE,
            first_configured_lane(company["lanes"]),
            "target_role_match",
        )
    return (
        "ignored_by_filter",
        POLL_IGNORED_FIT_SCORE,
        first_configured_lane(company["lanes"]),
        "ignored_by_filter",
    )


def source_endpoint_url(source: sqlite3.Row) -> str:
    if source["source_url"]:
        return source["source_url"]
    source_key = quote(source["source_key"].strip(), safe="")
    if source["source_type"] == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{source_key}/jobs?content=true"
    if source["source_type"] == "lever":
        return f"https://api.lever.co/v0/postings/{source_key}?mode=json"
    if source["source_type"] == "ashby":
        return (
            "https://api.ashbyhq.com/posting-api/job-board/"
            f"{source_key}?includeCompensation=true"
        )
    raise ValueError(f"Unsupported source type: {source['source_type']}")


def job_source_identity(source: sqlite3.Row) -> str:
    return f"{source['source_type']}:{source['source_key']}"


def fetch_json(url: str) -> object:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": HTTP_USER_AGENT,
        },
    )
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_compensation_signal(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in (
            "compensationTierSummary",
            "scrapeableCompensationSalarySummary",
            "salaryDescriptionPlain",
        ):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        if {"min", "max", "currency"} <= set(value):
            return f"{value['currency']} {value['min']}-{value['max']}"
    return None


def parse_greenhouse_jobs(payload: object) -> list[DiscoveredJob]:
    if not isinstance(payload, dict):
        raise ValueError("Greenhouse response must be a JSON object")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Greenhouse response missing jobs array")
    discovered: list[DiscoveredJob] = []
    for job in jobs:
        if not isinstance(job, dict) or not job.get("title"):
            continue
        location = job.get("location")
        discovered.append(
            DiscoveredJob(
                title=str(job["title"]),
                canonical_url=str(job["absolute_url"]) if job.get("absolute_url") else None,
                source_job_id=str(job["id"]) if job.get("id") is not None else None,
                location=(
                    str(location.get("name"))
                    if isinstance(location, dict) and location.get("name")
                    else None
                ),
            )
        )
    return discovered


def parse_lever_jobs(payload: object) -> list[DiscoveredJob]:
    if not isinstance(payload, list):
        raise ValueError("Lever response must be a JSON array")
    discovered: list[DiscoveredJob] = []
    for job in payload:
        if not isinstance(job, dict) or not job.get("text"):
            continue
        categories = job.get("categories") if isinstance(job.get("categories"), dict) else {}
        discovered.append(
            DiscoveredJob(
                title=str(job["text"]),
                canonical_url=(
                    str(job["hostedUrl"])
                    if job.get("hostedUrl")
                    else str(job["applyUrl"])
                    if job.get("applyUrl")
                    else None
                ),
                source_job_id=str(job["id"]) if job.get("id") is not None else None,
                location=(
                    str(categories.get("location"))
                    if categories.get("location")
                    else None
                ),
                remote_status=(
                    str(job["workplaceType"])
                    if job.get("workplaceType")
                    else None
                ),
                compensation_signal=extract_compensation_signal(job.get("salaryRange"))
                or extract_compensation_signal(job.get("salaryDescriptionPlain")),
            )
        )
    return discovered


def parse_ashby_jobs(payload: object) -> list[DiscoveredJob]:
    if not isinstance(payload, dict):
        raise ValueError("Ashby response must be a JSON object")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Ashby response missing jobs array")
    discovered: list[DiscoveredJob] = []
    for job in jobs:
        if not isinstance(job, dict) or not job.get("title"):
            continue
        canonical_url = str(job["jobUrl"]) if job.get("jobUrl") else None
        source_job_id = (
            str(job["id"])
            if job.get("id") is not None
            else canonical_url
        )
        discovered.append(
            DiscoveredJob(
                title=str(job["title"]),
                canonical_url=canonical_url,
                source_job_id=source_job_id,
                location=str(job["location"]) if job.get("location") else None,
                remote_status=(
                    str(job["workplaceType"])
                    if job.get("workplaceType")
                    else "Remote"
                    if job.get("isRemote") is True
                    else None
                ),
                compensation_signal=extract_compensation_signal(job.get("compensation")),
            )
        )
    return discovered


def fetch_source_jobs(source: sqlite3.Row) -> list[DiscoveredJob]:
    payload = fetch_json(source_endpoint_url(source))
    if source["source_type"] == "greenhouse":
        return parse_greenhouse_jobs(payload)
    if source["source_type"] == "lever":
        return parse_lever_jobs(payload)
    if source["source_type"] == "ashby":
        return parse_ashby_jobs(payload)
    raise ValueError(f"Unsupported source type: {source['source_type']}")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    db_path.chmod(0o600)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def open_action_status_sql(prefix: str = "") -> str:
    column = f"{prefix}.status" if prefix else "status"
    statuses = ", ".join(f"'{status}'" for status in OPEN_ACTION_STATUSES)
    return f"{column} IN ({statuses})"


def migrate_open_action_dedupe(connection: sqlite3.Connection, now: str) -> None:
    connection.execute(
        f"""
        UPDATE actions
        SET status = 'skipped',
            notes = CASE
                WHEN notes IS NULL OR notes = ''
                    THEN 'Skipped duplicate open action during schema v2 migration.'
                ELSE notes || char(10) || 'Skipped duplicate open action during schema v2 migration.'
            END,
            updated_at = ?
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            company_id,
                            queue,
                            kind,
                            COALESCE(job_id, -1),
                            COALESCE(contact_id, -1),
                            COALESCE(artifact_id, -1),
                            COALESCE(gap_id, -1)
                        ORDER BY id
                    ) AS duplicate_rank
                FROM actions
                WHERE {open_action_status_sql()}
            )
            WHERE duplicate_rank > 1
        )
        """,
        (now,),
    )
    connection.executescript(OPEN_ACTION_DEDUPE_INDEX)


def migrate_database(connection: sqlite3.Connection) -> None:
    version = connection.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
    ).fetchone()[0]
    if version < 2:
        now = utc_now()
        migrate_open_action_dedupe(connection, now)
        connection.execute(
            """
            INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (2, "open_action_dedupe", now),
        )
        version = 2
    if version < 3:
        now = utc_now()
        connection.executescript(SOURCE_DEFINITIONS_SCHEMA)
        connection.execute(
            """
            INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (3, "company_source_definitions", now),
        )
        version = 3
    if version < 4:
        now = utc_now()
        connection.executescript(QUERY_RUN_SCHEMA)
        connection.execute(
            """
            INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (4, "query_run_storage", now),
        )


def init_database(db_path: Path) -> int:
    with closing(connect(db_path)) as connection:
        with connection:
            connection.executescript(SCHEMA)
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (1, "initial_job_search_schema", utc_now()),
            )
            migrate_database(connection)
    return SCHEMA_VERSION


def read_status(db_path: Path) -> dict[str, int | str]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not initialized: {db_path}")

    with closing(connect(db_path)) as connection:
        version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        ).fetchone()[0]
        companies = connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        actions = connection.execute("SELECT COUNT(*) FROM actions").fetchone()[0]

    return {
        "path": str(db_path),
        "schema_version": version,
        "companies": companies,
        "jobs": jobs,
        "actions": actions,
    }


def read_daily_status(db_path: Path) -> dict[str, object]:
    today = datetime.now(timezone.utc).date()
    recent_since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    stale_check_before = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()

    with closing(connect(db_path)) as connection:
        open_actions = connection.execute(
            f"""
            SELECT queue, due_at, COUNT(*) AS count
            FROM actions
            WHERE {open_action_where_clause('actions')}
            GROUP BY queue, due_at
            """
        ).fetchall()
        job_statuses = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM jobs
            WHERE status NOT IN ('ignored_by_filter', 'closed', 'archived')
            GROUP BY status
            """
        ).fetchall()
        recent_outcomes = connection.execute(
            """
            SELECT event_type, COUNT(*) AS count
            FROM events
            WHERE happened_at >= ?
                AND event_type IN (
                    'application_submitted',
                    'interview',
                    'rejection_received',
                    'status_changed'
                )
            GROUP BY event_type
            ORDER BY event_type
            """,
            (recent_since,),
        ).fetchall()
        target_coverage = connection.execute(
            """
            SELECT
                COUNT(*) AS active_companies,
                SUM(CASE WHEN active_sources.company_id IS NOT NULL THEN 1 ELSE 0 END)
                    AS with_active_sources,
                SUM(
                    CASE
                        WHEN active_sources.company_id IS NULL
                            AND (companies.career_url IS NULL OR companies.career_url = '')
                        THEN 1
                        ELSE 0
                    END
                ) AS needs_source,
                SUM(
                    CASE
                        WHEN companies.last_checked_at IS NULL
                            OR companies.last_checked_at < ?
                        THEN 1
                        ELSE 0
                    END
                ) AS stale_checks
            FROM companies
            LEFT JOIN (
                SELECT DISTINCT company_id
                FROM company_sources
                WHERE status = 'active'
            ) AS active_sources ON active_sources.company_id = companies.id
            WHERE companies.status IN ('active', 'watch')
            """,
            (stale_check_before,),
        ).fetchone()

    queue_counts = {queue: 0 for queue in ACTION_QUEUES}
    stale_actions = 0
    due_today_actions = 0
    unscheduled_actions = 0
    for row in open_actions:
        queue_counts[row["queue"]] += row["count"]
        state = due_state(row["due_at"], today=today)
        if state == "stale":
            stale_actions += row["count"]
        elif state == "due_today":
            due_today_actions += row["count"]
        elif state == "unscheduled":
            unscheduled_actions += row["count"]

    return {
        "queue_counts": queue_counts,
        "open_action_count": sum(queue_counts.values()),
        "stale_action_count": stale_actions,
        "due_today_action_count": due_today_actions,
        "unscheduled_action_count": unscheduled_actions,
        "job_status_counts": {row["status"]: row["count"] for row in job_statuses},
        "recent_outcome_counts": {
            row["event_type"]: row["count"] for row in recent_outcomes
        },
        "target_coverage": {
            "active_companies": target_coverage["active_companies"] or 0,
            "with_active_sources": target_coverage["with_active_sources"] or 0,
            "needs_source": target_coverage["needs_source"] or 0,
            "stale_checks": target_coverage["stale_checks"] or 0,
        },
    }


def parse_report_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    parsed = parse_utc(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def command_center_record_count(connection: sqlite3.Connection) -> int:
    return sum(
        int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in (
            "companies",
            "company_sources",
            "query_runs",
            "query_run_results",
            "jobs",
            "contacts",
            "artifacts",
            "gaps",
            "actions",
            "events",
        )
    )


def stale_hygiene_actions(
    connection: sqlite3.Connection,
    *,
    as_of: datetime,
    unscheduled_days: int,
    limit: int,
) -> list[sqlite3.Row]:
    rows = connection.execute(
        action_rows_query(
            f"""
            WHERE actions.queue IN ({", ".join("?" for _ in HYGIENE_ACTION_QUEUES)})
                AND {open_action_where_clause('actions')}
            """
        ),
        HYGIENE_ACTION_QUEUES,
    ).fetchall()
    as_of_date = as_of.date()
    old_unscheduled_before = as_of - timedelta(days=unscheduled_days)
    stale_rows = []
    for row in rows:
        if due_state(row["due_at"], today=as_of_date) == "stale":
            stale_rows.append(row)
            continue
        created_at = parse_optional_utc(row["created_at"])
        if row["due_at"] is None and created_at is not None and created_at < old_unscheduled_before:
            stale_rows.append(row)
    return stale_rows[:limit]


def outcome_hygiene_gaps(
    connection: sqlite3.Connection,
    *,
    as_of: datetime,
    pending_days: int,
    limit: int,
) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT
            jobs.id AS job_id,
            jobs.title AS job_title,
            jobs.status AS job_status,
            jobs.rejection_reason,
            jobs.application_outcome,
            companies.id AS company_id,
            companies.name AS company_name,
            latest.event_id,
            latest.event_type,
            latest.happened_at
        FROM jobs
        JOIN companies ON companies.id = jobs.company_id
        JOIN (
            SELECT
                id AS event_id,
                job_id,
                event_type,
                happened_at
            FROM events
            WHERE job_id IS NOT NULL
                AND event_type IN ('application_submitted', 'interview', 'rejection_received')
        ) AS latest ON latest.job_id = jobs.id
        ORDER BY jobs.id, latest.event_id
        """
    ).fetchall()

    latest_by_job: dict[int, tuple[datetime, sqlite3.Row]] = {}
    for row in rows:
        event_at = parse_optional_utc(row["happened_at"])
        if event_at is None or event_at > as_of:
            continue
        job_id = int(row["job_id"])
        current = latest_by_job.get(job_id)
        if current is None or (event_at, int(row["event_id"])) > (
            current[0],
            int(current[1]["event_id"]),
        ):
            latest_by_job[job_id] = (event_at, row)

    pending_before = as_of - timedelta(days=pending_days)
    gaps: list[dict[str, object]] = []
    for event_at, row in sorted(
        latest_by_job.values(), key=lambda item: (item[0], int(item[1]["job_id"]))
    ):
        event_type = str(row["event_type"])
        job_status = str(row["job_status"])
        application_outcome = row["application_outcome"]
        rejection_reason = row["rejection_reason"]
        issue = None
        if event_type == "rejection_received":
            if job_status not in ("rejected", "closed", "archived"):
                issue = "rejection_event_status_mismatch"
            elif not application_outcome and not rejection_reason:
                issue = "unclassified_rejection"
        elif event_type in ("application_submitted", "interview") and job_status not in (
            "applied",
            "interviewing",
            "rejected",
            "closed",
            "archived",
        ):
            issue = f"{event_type}_status_mismatch"
        elif (
            event_type in ("application_submitted", "interview")
            and event_at < pending_before
            and job_status in ("applied", "interviewing")
            and not application_outcome
        ):
            issue = "pending_final_disposition"
        if issue is not None:
            gaps.append(
                {
                    "issue": issue,
                    "job_id": row["job_id"],
                    "job_title": row["job_title"],
                    "job_status": job_status,
                    "company_id": row["company_id"],
                    "company_name": row["company_name"],
                    "event_id": row["event_id"],
                    "event_type": event_type,
                    "happened_at": row["happened_at"],
                }
            )
        if len(gaps) >= limit:
            break
    return gaps


def companies_without_next_action(
    connection: sqlite3.Connection,
    *,
    as_of: datetime,
    activity_days: int,
    limit: int,
) -> list[sqlite3.Row]:
    activity_since = as_of - timedelta(days=activity_days)
    rows = connection.execute(
        f"""
        SELECT
            companies.id AS company_id,
            companies.name AS company_name,
            companies.status AS company_status,
            latest.id AS event_id,
            latest.event_type,
            latest.happened_at
        FROM companies
        JOIN events AS latest ON latest.company_id = companies.id
        WHERE companies.status IN ('active', 'watch')
            AND latest.event_type <> 'company_added'
            AND NOT EXISTS (
                SELECT 1
                FROM actions
                WHERE actions.company_id = companies.id
                    AND {open_action_where_clause('actions')}
            )
        ORDER BY companies.id, latest.id
        """,
        (),
    ).fetchall()
    latest_by_company: dict[int, tuple[datetime, sqlite3.Row]] = {}
    for row in rows:
        event_at = parse_optional_utc(row["happened_at"])
        if event_at is None or event_at < activity_since or event_at > as_of:
            continue
        company_id = int(row["company_id"])
        current = latest_by_company.get(company_id)
        if current is None or (event_at, int(row["event_id"])) > (
            current[0],
            int(current[1]["event_id"]),
        ):
            latest_by_company[company_id] = (event_at, row)
    return [
        row
        for _, row in sorted(
            latest_by_company.values(),
            key=lambda item: (item[0], int(item[1]["company_id"])),
        )[:limit]
    ]


def format_hygiene_action(row: sqlite3.Row, *, as_of: datetime) -> str:
    subject = f"company=#{row['company_id']} {row['company_name']}"
    if row["job_id"]:
        subject += f" | job=#{row['job_id']} {row['job_title']}"
    age_state = "old_unscheduled" if row["due_at"] is None else "scheduled"
    return (
        f"- action=#{row['id']} | queue={row['queue']} | kind={row['kind']} | "
        f"status={row['status']} | due={row['due_at'] or 'unscheduled'} | "
        f"due_state={due_state(row['due_at'], today=as_of.date())} | "
        f"age_state={age_state} | {subject}"
    )


def format_outcome_gap(gap: dict[str, object]) -> str:
    return (
        f"- issue={gap['issue']} | job=#{gap['job_id']} {gap['job_title']} | "
        f"status={gap['job_status']} | company=#{gap['company_id']} {gap['company_name']} | "
        f"event=#{gap['event_id']} {gap['event_type']} at {gap['happened_at']}"
    )


def format_company_hygiene(row: sqlite3.Row) -> str:
    return (
        f"- company=#{row['company_id']} {row['company_name']} | "
        f"status={row['company_status']} | latest_event=#{row['event_id']} "
        f"{row['event_type']} at {row['happened_at']} | open_actions=0"
    )


def pipeline_status_to_job_status(status: str | None) -> str:
    if status == "ready_to_apply":
        return "ready_to_apply"
    if status == "applied":
        return "applied"
    if status in ("screened_out", "skipped"):
        return "ignored_by_filter"
    return "discovered"


def resume_for_legacy_lane(lane: str | None) -> str | None:
    if lane == "FINTECH":
        return "YOUR_PROFILE/Fintech/FINTECH.md"
    if lane == "AI":
        return "YOUR_PROFILE/AI/AI.md"
    if lane == "ACCESS":
        return "YOUR_PROFILE/Access/ACCESS.md"
    if lane == "DESIGN":
        return "YOUR_PROFILE/DESIGN.md"
    if lane == "MEDIA_PLATFORM":
        return "YOUR_PROFILE/Media Platform/Antonio_Pontarelli_Resume.pdf"
    return None


def legacy_material_paths(record: dict[str, object]) -> str | None:
    paths = {
        key: value
        for key, value in {
            "jd": record.get("jd_path"),
            "qa": record.get("qa_path"),
            "coverletter": record.get("coverletter_path"),
        }.items()
        if isinstance(value, str) and value.strip()
    }
    return json.dumps(paths, sort_keys=True) if paths else None


def legacy_application_folder(record: dict[str, object]) -> str | None:
    for key in ("jd_path", "qa_path", "coverletter_path"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return str(Path(value).parent)
    return None


def legacy_note(record: dict[str, object]) -> str | None:
    note_parts = []
    for key in (
        "status",
        "summary",
        "why_now",
        "risks",
        "notes",
        "user_action",
        "search_query",
        "bucket",
        "query_pack",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            note_parts.append(f"{key}: {value.strip()}")
    return "\n".join(note_parts) if note_parts else None


def ensure_legacy_company(
    connection: sqlite3.Connection,
    *,
    record: dict[str, object],
    now: str,
) -> tuple[int, bool]:
    company_name = str(record.get("company") or "").strip()
    if not company_name:
        raise ValueError("legacy pipeline record is missing company")
    row = connection.execute(
        "SELECT id FROM companies WHERE name_key = ?",
        (company_name_key(company_name),),
    ).fetchone()
    if row is not None:
        return int(row["id"]), False

    cursor = connection.execute(
        """
        INSERT INTO companies(
            name, name_key, lanes, status, notes, created_at, updated_at
        )
        VALUES (?, ?, ?, 'active', ?, ?, ?)
        """,
        (
            company_name,
            company_name_key(company_name),
            record.get("lane") if record.get("lane") != "PASS" else None,
            "Imported from legacy job pipeline.",
            now,
            now,
        ),
    )
    company_id = int(cursor.lastrowid)
    log_event(
        connection,
        company_id=company_id,
        event_type="company_added",
        notes=f"Imported {company_name} from legacy job pipeline",
        happened_at=str(record.get("created_at") or now),
        now=now,
    )
    return company_id, True


def import_legacy_record(
    connection: sqlite3.Connection,
    *,
    record: dict[str, object],
    now: str,
) -> tuple[str, int | None, bool]:
    company_id, company_created = ensure_legacy_company(
        connection,
        record=record,
        now=now,
    )
    title = str(record.get("role") or "").strip()
    if not title:
        raise ValueError("legacy pipeline record is missing role")

    legacy_status = str(record.get("status") or "")
    job_status = pipeline_status_to_job_status(legacy_status)
    source = str(record.get("source") or "legacy_pipeline").strip() or "legacy_pipeline"
    source_job_id = str(record.get("id") or "").strip() or None
    canonical_url = normalize_url(
        str(record.get("job_url")).strip()
        if isinstance(record.get("job_url"), str)
        else None
    )
    location = (
        str(record.get("location")).strip()
        if isinstance(record.get("location"), str) and str(record.get("location")).strip()
        else None
    )
    duplicate_matches = job_duplicate_matches(
        connection,
        company_id=company_id,
        title=title,
        canonical_url=canonical_url,
        source=source,
        source_job_id=source_job_id,
        location=location,
        remote_status=None,
        now=now,
    )
    if duplicate_matches:
        return "skipped_duplicate", None, company_created

    created_at = str(record.get("created_at") or now)
    updated_at = str(record.get("updated_at") or record.get("last_screened_at") or now)
    material_paths = legacy_material_paths(record)
    cursor = connection.execute(
        """
        INSERT INTO jobs(
            company_id, title, canonical_url, source, source_job_id, location,
            lane, status, discovery_status, recommended_resume, materials_status,
            application_folder, material_paths, application_outcome, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_id,
            title,
            canonical_url,
            source,
            source_job_id,
            location,
            record.get("lane"),
            job_status,
            f"legacy_pipeline:{legacy_status}" if legacy_status else "legacy_pipeline",
            resume_for_legacy_lane(
                record.get("lane") if isinstance(record.get("lane"), str) else None
            ),
            "ready" if material_paths else None,
            legacy_application_folder(record),
            material_paths,
            record.get("recommendation"),
            created_at,
            updated_at,
        ),
    )
    job_id = int(cursor.lastrowid)
    generate_job_actions(connection, job_id=job_id, now=now)
    event_time = str(record.get("last_screened_at") or record.get("updated_at") or now)
    log_event(
        connection,
        company_id=company_id,
        job_id=job_id,
        event_type="job_added",
        happened_at=created_at,
        notes=f"Imported from legacy job pipeline: {record.get('id') or title}",
        now=now,
    )
    if job_status == "applied":
        log_event(
            connection,
            company_id=company_id,
            job_id=job_id,
            event_type="application_submitted",
            happened_at=event_time,
            notes=legacy_note(record) or "legacy status: applied",
            now=now,
        )
    elif job_status == "ready_to_apply":
        log_event(
            connection,
            company_id=company_id,
            job_id=job_id,
            event_type="status_changed",
            happened_at=event_time,
            notes=legacy_note(record) or "legacy status: ready_to_apply",
            now=now,
        )
    else:
        log_event(
            connection,
            company_id=company_id,
            job_id=job_id,
            event_type="note",
            happened_at=event_time,
            notes=legacy_note(record) or f"legacy status: {legacy_status or 'unknown'}",
            now=now,
        )
    return "imported", job_id, company_created


def require_database(db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not initialized: {db_path}")
    init_database(db_path)


def require_current_database_read_only(db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not initialized: {db_path}")
    with closing(connect(db_path)) as connection:
        version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        ).fetchone()[0]
    if version < SCHEMA_VERSION:
        raise ValueError(
            f"Database schema_version={version} is older than {SCHEMA_VERSION}; "
            "run init before reporting."
        )


def get_company(connection: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM companies WHERE name_key = ?",
        (company_name_key(name),),
    ).fetchone()
    if row is None:
        raise ValueError(f"Company not found: {name}")
    return row


def get_job(connection: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"Job not found: {job_id}")
    return row


def open_action_where_clause(prefix: str = "") -> str:
    return open_action_status_sql(prefix)


def action_exists(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    queue: str,
    kind: str,
    job_id: int | None = None,
    contact_id: int | None = None,
    artifact_id: int | None = None,
    gap_id: int | None = None,
) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM actions
        WHERE company_id = ?
            AND queue = ?
            AND kind = ?
            AND COALESCE(job_id, -1) = COALESCE(?, -1)
            AND COALESCE(contact_id, -1) = COALESCE(?, -1)
            AND COALESCE(artifact_id, -1) = COALESCE(?, -1)
            AND COALESCE(gap_id, -1) = COALESCE(?, -1)
        LIMIT 1
        """,
        (company_id, queue, kind, job_id, contact_id, artifact_id, gap_id),
    ).fetchone()
    return row is not None


def upsert_action(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    queue: str,
    kind: str,
    job_id: int | None = None,
    contact_id: int | None = None,
    artifact_id: int | None = None,
    gap_id: int | None = None,
    due_at: str | None = None,
    notes: str | None = None,
    now: str | None = None,
) -> tuple[int, bool]:
    now = now or utc_now()
    existing = connection.execute(
        f"""
        SELECT id FROM actions
        WHERE company_id = ?
            AND queue = ?
            AND kind = ?
            AND COALESCE(job_id, -1) = COALESCE(?, -1)
            AND COALESCE(contact_id, -1) = COALESCE(?, -1)
            AND COALESCE(artifact_id, -1) = COALESCE(?, -1)
            AND COALESCE(gap_id, -1) = COALESCE(?, -1)
            AND {open_action_where_clause()}
        ORDER BY id
        LIMIT 1
        """,
        (company_id, queue, kind, job_id, contact_id, artifact_id, gap_id),
    ).fetchone()
    if existing is not None:
        return int(existing["id"]), False

    cursor = connection.execute(
        """
        INSERT INTO actions(
            company_id, job_id, contact_id, artifact_id, gap_id, queue, kind,
            due_at, notes, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_id,
            job_id,
            contact_id,
            artifact_id,
            gap_id,
            queue,
            kind,
            due_at,
            notes,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid), True


def upsert_generated_job_action(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    job_id: int,
    queue: str,
    kind: str,
    due_at: str | None = None,
    notes: str | None = None,
    now: str | None = None,
) -> None:
    if action_exists(
        connection,
        company_id=company_id,
        job_id=job_id,
        queue=queue,
        kind=kind,
    ):
        return
    upsert_action(
        connection,
        company_id=company_id,
        job_id=job_id,
        queue=queue,
        kind=kind,
        due_at=due_at,
        notes=notes,
        now=now,
    )


def skip_superseded_job_actions(
    connection: sqlite3.Connection,
    *,
    job_id: int,
    active_actions: set[tuple[str, str]],
    now: str,
) -> None:
    for queue, kind, generated_notes in JOB_GENERATED_ACTIONS:
        if (queue, kind) in active_actions:
            continue
        connection.execute(
            f"""
            UPDATE actions
            SET status = 'skipped',
                notes = CASE
                    WHEN notes IS NULL OR notes = ''
                        THEN 'Skipped superseded generated action.'
                    ELSE notes || char(10) || 'Skipped superseded generated action.'
                END,
                updated_at = ?
            WHERE job_id = ?
                AND queue = ?
                AND kind = ?
                AND notes = ?
                AND {open_action_where_clause()}
            """,
            (now, job_id, queue, kind, generated_notes),
        )


def touch_company(
    connection: sqlite3.Connection, company_id: int, happened_at: str | None = None
) -> None:
    now = utc_now()
    touch_at = happened_at or now
    connection.execute(
        """
        UPDATE companies
        SET last_touched_at = CASE
                WHEN last_touched_at IS NULL OR last_touched_at < ? THEN ?
                ELSE last_touched_at
            END,
            updated_at = ?
        WHERE id = ?
        """,
        (touch_at, touch_at, now, company_id),
    )


def log_event(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    event_type: str,
    job_id: int | None = None,
    contact_id: int | None = None,
    artifact_id: int | None = None,
    gap_id: int | None = None,
    action_id: int | None = None,
    notes: str | None = None,
    happened_at: str | None = None,
    now: str | None = None,
) -> int:
    now = now or utc_now()
    happened_at = happened_at or now
    cursor = connection.execute(
        """
        INSERT INTO events(
            company_id, job_id, contact_id, artifact_id, gap_id, action_id,
            event_type, happened_at, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_id,
            job_id,
            contact_id,
            artifact_id,
            gap_id,
            action_id,
            event_type,
            happened_at,
            notes,
            now,
        ),
    )
    if event_type != "company_added":
        touch_company(connection, company_id, happened_at)
    if event_type == "rejection_received":
        apply_rejection_cooldown(
            connection,
            company_id=company_id,
            job_id=job_id,
            happened_at=happened_at,
            notes=notes,
            now=now,
        )
    return int(cursor.lastrowid)


def rejection_had_interview_loop(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    job_id: int | None,
    happened_at: str,
    notes: str | None,
) -> bool:
    normalized_notes = normalize_match_text(notes)
    if "no interview" in normalized_notes or "without interview" in normalized_notes:
        return False
    if "interview" in normalized_notes or "loop" in normalized_notes:
        return True

    predicates = ["company_id = ?", "event_type = 'interview'", "happened_at <= ?"]
    params: list[object] = [company_id, happened_at]
    if job_id is not None:
        predicates.append("job_id = ?")
        params.append(job_id)
    row = connection.execute(
        f"""
        SELECT 1
        FROM events
        WHERE {' AND '.join(predicates)}
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return row is not None


def apply_rejection_cooldown(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    job_id: int | None,
    happened_at: str,
    notes: str | None,
    now: str,
) -> None:
    base = parse_utc(happened_at)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    days = (
        INTERVIEW_LOOP_COOLDOWN_DAYS
        if rejection_had_interview_loop(
            connection,
            company_id=company_id,
            job_id=job_id,
            happened_at=happened_at,
            notes=notes,
        )
        else NO_INTERVIEW_COOLDOWN_DAYS
    )
    cooldown_until = (base + timedelta(days=days)).isoformat()
    connection.execute(
        """
        UPDATE companies
        SET status = 'cooldown',
            cooldown_until = CASE
                WHEN cooldown_until IS NULL OR cooldown_until < ? THEN ?
                ELSE cooldown_until
            END,
            updated_at = ?
        WHERE id = ?
        """,
        (cooldown_until, cooldown_until, now, company_id),
    )


def generate_company_actions(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    now: str | None = None,
) -> None:
    company = connection.execute(
        "SELECT id, tier FROM companies WHERE id = ?", (company_id,)
    ).fetchone()
    if company is None:
        return
    contact_count = connection.execute(
        "SELECT COUNT(*) FROM contacts WHERE company_id = ?", (company_id,)
    ).fetchone()[0]
    if company["tier"] == 1 and contact_count == 0:
        upsert_action(
            connection,
            company_id=company_id,
            queue="research",
            kind="find_contact",
            notes="Tier 1 company has no contacts.",
            now=now,
        )


def generate_job_actions(
    connection: sqlite3.Connection,
    *,
    job_id: int,
    now: str | None = None,
) -> None:
    job = get_job(connection, job_id)
    now = now or utc_now()
    now_dt = parse_utc(now)
    company_id = int(job["company_id"])
    active_actions: set[tuple[str, str]] = set()

    should_screen = job["status"] in ("discovered", "screening") and (
        job["fit_score"] is not None and int(job["fit_score"]) >= 70
    )
    if should_screen:
        active_actions.add(("screen", "screen_role"))
    if job["status"] == "ready_to_apply":
        if job_can_bypass_company_cooldown(connection, job=job, now=now):
            active_actions.add(("apply", "apply"))
    if job["status"] == "applied":
        active_actions.add(("follow_up", "follow_up"))
    if job["status"] == "rejected" or job["rejection_reason"]:
        active_actions.add(("classify", "classify_outcome"))

    skip_superseded_job_actions(
        connection,
        job_id=job_id,
        active_actions=active_actions,
        now=now,
    )

    if should_screen:
        upsert_generated_job_action(
            connection,
            company_id=company_id,
            job_id=job_id,
            queue="screen",
            kind="screen_role",
            notes="Promising role needs screening.",
            now=now,
        )

    if job["status"] == "ready_to_apply" and job_can_bypass_company_cooldown(
        connection, job=job, now=now
    ):
        upsert_generated_job_action(
            connection,
            company_id=company_id,
            job_id=job_id,
            queue="apply",
            kind="apply",
            notes="Role is marked ready to apply.",
            now=now,
        )

    if job["status"] == "applied":
        due_at = add_business_days(now_dt, 6).isoformat()
        upsert_generated_job_action(
            connection,
            company_id=company_id,
            job_id=job_id,
            queue="follow_up",
            kind="follow_up",
            due_at=due_at,
            notes="Application submitted; follow up in 5-7 business days.",
            now=now,
        )

    if job["status"] == "rejected" or job["rejection_reason"]:
        upsert_generated_job_action(
            connection,
            company_id=company_id,
            job_id=job_id,
            queue="classify",
            kind="classify_outcome",
            notes="Rejection needs outcome classification.",
            now=now,
        )


def generate_message_follow_up(
    connection: sqlite3.Connection,
    *,
    action: sqlite3.Row,
    now: str | None = None,
) -> None:
    now = now or utc_now()
    due_at = add_business_days(parse_utc(now), 4).isoformat()
    upsert_action(
        connection,
        company_id=int(action["company_id"]),
        job_id=action["job_id"],
        contact_id=action["contact_id"],
        queue="follow_up",
        kind="follow_up",
        due_at=due_at,
        notes="Message sent; follow up in 3-5 business days.",
        now=now,
    )


def create_company(
    connection: sqlite3.Connection,
    args: argparse.Namespace,
) -> int:
    now = utc_now()
    cursor = connection.execute(
        """
        INSERT INTO companies(
            name, name_key, tier, lanes, why_interesting, fit_thesis, known_gaps,
            products_used, target_roles, career_url, ats_type, status, cooldown_until,
            notes, last_touched_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            args.name,
            company_name_key(args.name),
            args.tier,
            args.lanes,
            args.why_interesting,
            args.fit_thesis,
            args.known_gaps,
            args.products_used,
            args.target_roles,
            args.career_url,
            args.ats_type,
            args.status,
            args.cooldown_until,
            args.notes,
            None,
            now,
            now,
        ),
    )
    company_id = int(cursor.lastrowid)
    generate_company_actions(connection, company_id=company_id, now=now)
    log_event(
        connection,
        company_id=company_id,
        event_type="company_added",
        notes=f"Added {args.name}",
        now=now,
    )
    return company_id


def create_company_source(
    connection: sqlite3.Connection,
    args: argparse.Namespace,
) -> int:
    company = get_company(connection, args.company)
    now = utc_now()
    source_url = args.url.strip() if args.url else None
    cursor = connection.execute(
        """
        INSERT INTO company_sources(
            company_id, source_type, source_key, source_url, status, notes,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company["id"],
            args.source_type,
            args.source_key,
            source_url,
            args.status,
            args.notes,
            now,
            now,
        ),
    )
    connection.execute(
        """
        UPDATE companies
        SET ats_type = COALESCE(ats_type, ?),
            updated_at = ?
        WHERE id = ?
        """,
        (args.source_type, now, company["id"]),
    )
    return int(cursor.lastrowid)


def non_empty_text(record: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            if items:
                return ", ".join(items)
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def nested_record(record: dict[str, object], key: str) -> dict[str, object]:
    value = record.get(key)
    return value if isinstance(value, dict) else {}


def company_import_rows(path: Path) -> list[dict[str, object] | object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid company import file {path}: {error.msg}") from error

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("companies", "targets", "rows"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
        if any(key in payload for key in ("name", "company", "company_name")):
            return [payload]
    raise ValueError(
        f"Invalid company import file {path}: expected array or object with companies array"
    )


def company_import_tier(record: dict[str, object]) -> int | None:
    value = record.get("tier")
    if value is None or value == "":
        return None
    try:
        tier = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("tier must be 1, 2, or 3") from error
    if tier not in (1, 2, 3):
        raise ValueError("tier must be 1, 2, or 3")
    return tier


def researched_company_values(record: dict[str, object]) -> tuple[str, dict[str, object]]:
    name = non_empty_text(record, "name", "company_name", "company")
    if name is None:
        raise ValueError("missing company name")

    ats = nested_record(record, "ats")
    ats_type = non_empty_text(record, "ats_type", "source_type", "provider") or non_empty_text(
        ats, "type", "provider", "source_type"
    )
    values: dict[str, object] = {
        "tier": company_import_tier(record),
        "lanes": non_empty_text(record, "lanes", "lane"),
        "why_interesting": non_empty_text(record, "why_interesting", "why"),
        "fit_thesis": non_empty_text(record, "fit_thesis", "thesis"),
        "known_gaps": non_empty_text(record, "known_gaps", "gaps"),
        "products_used": non_empty_text(record, "products_used"),
        "target_roles": non_empty_text(record, "target_roles", "target_role"),
        "career_url": non_empty_text(record, "career_url", "careers_url"),
        "ats_type": ats_type.casefold() if ats_type else None,
        "status": non_empty_text(record, "status"),
        "notes": non_empty_text(record, "notes"),
    }
    status = values.get("status")
    if status is not None and status not in COMPANY_STATUSES:
        raise ValueError(
            "status must be one of: " + ", ".join(COMPANY_STATUSES)
        )
    return name, {key: value for key, value in values.items() if value not in (None, "")}


def upsert_researched_company(
    connection: sqlite3.Connection,
    *,
    name: str,
    values: dict[str, object],
    now: str,
) -> tuple[int, str]:
    row = connection.execute(
        "SELECT id FROM companies WHERE name_key = ?",
        (company_name_key(name),),
    ).fetchone()
    if row is None:
        insert_values = {
            "name": name,
            "name_key": company_name_key(name),
            "status": "active",
            **values,
            "created_at": now,
            "updated_at": now,
        }
        columns = ", ".join(insert_values)
        placeholders = ", ".join("?" for _ in insert_values)
        cursor = connection.execute(
            f"INSERT INTO companies({columns}) VALUES ({placeholders})",
            tuple(insert_values.values()),
        )
        company_id = int(cursor.lastrowid)
        generate_company_actions(connection, company_id=company_id, now=now)
        log_event(
            connection,
            company_id=company_id,
            event_type="company_added",
            notes=f"Imported researched company: {name}",
            now=now,
        )
        return company_id, "created"

    company_id = int(row["id"])
    if values:
        update_columns(connection, "companies", company_id, values)
        generate_company_actions(connection, company_id=company_id, now=now)
        return company_id, "updated"
    return company_id, "existing"


def source_details_for_company_import(
    record: dict[str, object],
) -> tuple[str | None, str | None, str | None, str | None]:
    ats = nested_record(record, "ats")
    source_type = non_empty_text(record, "ats_type", "source_type", "provider") or non_empty_text(
        ats, "type", "provider", "source_type"
    )
    source_type = source_type.casefold() if source_type else None
    source_url = non_empty_text(
        record,
        "ats_source_url",
        "source_url",
        "ats_url",
    ) or non_empty_text(ats, "source_url", "url")
    source_key = non_empty_text(
        record,
        "ats_source_key",
        "source_key",
        "ats_key",
        "board_token",
    ) or non_empty_text(ats, "source_key", "key", "board_token")
    source_notes = non_empty_text(record, "source_notes") or non_empty_text(ats, "notes")
    if source_key is None and source_url is not None:
        source_key = normalize_url(source_url) or source_url.strip()
    return source_type, source_key, source_url, source_notes


def upsert_company_source(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    source_type: str,
    source_key: str,
    source_url: str | None,
    notes: str | None,
    now: str,
) -> str:
    existing = connection.execute(
        """
        SELECT *
        FROM company_sources
        WHERE company_id = ? AND source_type = ? AND source_key = ?
        """,
        (company_id, source_type, source_key),
    ).fetchone()
    if existing is None:
        connection.execute(
            """
            INSERT INTO company_sources(
                company_id, source_type, source_key, source_url, status, notes,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (company_id, source_type, source_key, source_url, notes, now, now),
        )
        return "source_created"

    values = {
        key: value
        for key, value in {"source_url": source_url, "notes": notes}.items()
        if value is not None and value != existing[key]
    }
    if values:
        update_columns(connection, "company_sources", int(existing["id"]), values)
        return "source_updated"
    return "source_existing"


def import_researched_company_row(
    connection: sqlite3.Connection,
    *,
    row_number: int,
    raw_row: object,
    now: str,
) -> CompanyImportOutcome:
    if not isinstance(raw_row, dict):
        return CompanyImportOutcome(
            row_number=row_number,
            company_name=None,
            company_state="invalid_row",
            source_state="invalid_row",
            detail="expected object",
        )

    try:
        company_name, company_values = researched_company_values(raw_row)
    except ValueError as error:
        return CompanyImportOutcome(
            row_number=row_number,
            company_name=non_empty_text(raw_row, "name", "company_name", "company"),
            company_state="invalid_row",
            source_state="invalid_row",
            detail=str(error),
        )

    company_id, company_state = upsert_researched_company(
        connection,
        name=company_name,
        values=company_values,
        now=now,
    )
    source_type, source_key, source_url, source_notes = source_details_for_company_import(
        raw_row
    )

    if not source_type and not source_key and not source_url:
        source_state = "needs_manual_source"
        detail = "missing ATS source details"
    elif source_type not in ATS_TYPES:
        source_state = "unsupported_ats"
        detail = f"ats_type={source_type or 'missing'}"
    elif not source_key:
        source_state = "needs_manual_source"
        detail = "missing ATS source key or source URL"
    else:
        source_state = upsert_company_source(
            connection,
            company_id=company_id,
            source_type=source_type,
            source_key=source_key,
            source_url=source_url,
            notes=source_notes,
            now=now,
        )
        detail = f"type={source_type} key={source_key}"

    return CompanyImportOutcome(
        row_number=row_number,
        company_name=company_name,
        company_state=f"company_{company_state}",
        source_state=source_state,
        detail=detail,
    )


def format_company_import_outcome(outcome: CompanyImportOutcome) -> str:
    parts = [
        f"row={outcome.row_number}",
        f"company={outcome.company_name or 'unknown'}",
        outcome.company_state,
        outcome.source_state,
    ]
    if outcome.detail:
        parts.append(outcome.detail)
    return " | ".join(parts)


def update_columns(
    connection: sqlite3.Connection,
    table: str,
    row_id: int,
    values: dict[str, object],
) -> None:
    if not values:
        return
    values["updated_at"] = utc_now()
    assignments = ", ".join(f"{column} = ?" for column in values)
    connection.execute(
        f"UPDATE {table} SET {assignments} WHERE id = ?",
        (*values.values(), row_id),
    )


def print_company_row(row: sqlite3.Row) -> None:
    fields = [
        f"id={row['id']}",
        f"name={row['name']}",
        f"tier={row['tier'] or 'unset'}",
        f"status={row['status']}",
    ]
    if row["lanes"]:
        fields.append(f"lanes={row['lanes']}")
    if row["cooldown_until"]:
        fields.append(f"cooldown_until={row['cooldown_until']}")
    print(" | ".join(fields))


def format_job(row: sqlite3.Row) -> str:
    parts = [
        f"#{row['id']}",
        row["title"],
        f"status={row['status']}",
    ]
    if row["fit_score"] is not None:
        parts.append(f"fit={row['fit_score']}")
    if row["lane"]:
        parts.append(f"lane={row['lane']}")
    if row["canonical_url"]:
        parts.append(row["canonical_url"])
    return " | ".join(parts)


def format_action(row: sqlite3.Row) -> str:
    due = row["due_at"] or "unscheduled"
    subject = row["company_name"]
    if row["job_title"]:
        subject += f" / {row['job_title']}"
    if row["job_id"]:
        subject += f" | job=#{row['job_id']}"
    parts = [
        f"#{row['id']} | {row['queue']}:{row['kind']} | "
        f"{action_review_state(row)} | status={row['status']} | "
        f"due={due} | {subject}"
    ]
    if row["job_url"]:
        parts.append(f"url={row['job_url']}")
    if row["job_resume"]:
        parts.append(f"resume={row['job_resume']}")
    if row["job_application_folder"]:
        parts.append(f"materials={row['job_application_folder']}")
    if row["contact_id"]:
        contact = f"contact=#{row['contact_id']} {row['contact_name']}"
        if row["contact_title"]:
            contact += f" ({row['contact_title']})"
        parts.append(contact)
    if row["artifact_id"]:
        artifact = (
            f"artifact=#{row['artifact_id']} "
            f"{row['artifact_type']} status={row['artifact_status']}"
        )
        if row["artifact_link"]:
            artifact += f" link={row['artifact_link']}"
        if row["artifact_path"]:
            artifact += f" path={row['artifact_path']}"
        parts.append(artifact)
    if row["gap_id"]:
        parts.append(
            f"gap=#{row['gap_id']} {row['gap_severity']} "
            f"status={row['gap_status']} {row['gap_description']}"
        )
    return " | ".join(parts)


def action_review_state(row: sqlite3.Row) -> str:
    if row["status"] in TERMINAL_ACTION_STATUSES:
        return str(row["status"])
    if row["status"] == "blocked":
        return "blocked"
    try:
        due_at = parse_optional_utc(row["due_at"])
    except ValueError:
        due_at = None
    if due_at is None:
        return "ready"

    now = datetime.now(timezone.utc)
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    if due_at < now.replace(hour=0, minute=0, second=0, microsecond=0):
        return "stale"
    if due_at <= now:
        return "due"
    return "ready"


def action_review_order_sql() -> str:
    return """
            CASE
                WHEN actions.status = 'blocked' THEN 2
                WHEN actions.due_at IS NOT NULL
                    AND julianday(actions.due_at) < julianday('now', 'start of day')
                    THEN 0
                WHEN actions.due_at IS NOT NULL
                    AND julianday(actions.due_at) <= julianday('now')
                    THEN 1
                ELSE 3
            END,
            CASE WHEN actions.due_at IS NULL THEN 1 ELSE 0 END,
            actions.due_at,
            actions.id
    """


def format_action_next(row: sqlite3.Row) -> str:
    parts = [format_action(row), f"due_state={due_state(row['due_at'])}"]
    company_context = [
        f"status={row['company_status']}",
        f"tier={row['company_tier'] if row['company_tier'] is not None else 'unset'}",
    ]
    if row["company_lanes"]:
        company_context.append(f"lanes={row['company_lanes']}")
    if row["company_last_checked_at"]:
        company_context.append(f"last_checked={row['company_last_checked_at']}")
    parts.append("company=" + ",".join(company_context))
    if row["job_id"]:
        job_context = [f"status={row['job_status']}"]
        if row["job_fit_score"] is not None:
            job_context.append(f"fit={row['job_fit_score']}")
        if row["job_lane"]:
            job_context.append(f"lane={row['job_lane']}")
        if row["job_location"]:
            job_context.append(f"location={row['job_location']}")
        if row["job_remote_status"]:
            job_context.append(f"remote={row['job_remote_status']}")
        parts.append("job_context=" + ",".join(job_context))
    if row["notes"]:
        parts.append(f"note={row['notes']}")
    return " | ".join(parts)


def action_rows_query(where_sql: str = "") -> str:
    return f"""
        SELECT
            actions.*,
            companies.name AS company_name,
            companies.tier AS company_tier,
            companies.status AS company_status,
            companies.lanes AS company_lanes,
            companies.last_checked_at AS company_last_checked_at,
            jobs.title AS job_title,
            jobs.canonical_url AS job_url,
            jobs.status AS job_status,
            jobs.fit_score AS job_fit_score,
            jobs.lane AS job_lane,
            jobs.location AS job_location,
            jobs.remote_status AS job_remote_status,
            jobs.recommended_resume AS job_resume,
            jobs.application_folder AS job_application_folder,
            contacts.name AS contact_name,
            contacts.title AS contact_title,
            artifacts.type AS artifact_type,
            artifacts.status AS artifact_status,
            artifacts.link AS artifact_link,
            artifacts.path AS artifact_path,
            gaps.description AS gap_description,
            gaps.severity AS gap_severity,
            gaps.status AS gap_status
        FROM actions
        JOIN companies ON companies.id = actions.company_id
        LEFT JOIN jobs ON jobs.id = actions.job_id
        LEFT JOIN contacts ON contacts.id = actions.contact_id
        LEFT JOIN artifacts ON artifacts.id = actions.artifact_id
        LEFT JOIN gaps ON gaps.id = actions.gap_id
        {where_sql}
        ORDER BY
            {action_review_order_sql()}
    """


def resolve_company_id(connection: sqlite3.Connection, company: str) -> int:
    row = None
    if company.isdecimal():
        row = connection.execute(
            "SELECT id FROM companies WHERE id = ?", (int(company),)
        ).fetchone()
    if row is None:
        row = connection.execute(
            "SELECT id FROM companies WHERE name_key = ?",
            (company_name_key(company),),
        ).fetchone()
    if row is None:
        raise ValueError(f"Company not found: {company}")
    return int(row["id"])


def require_row(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...],
    missing_message: str,
) -> sqlite3.Row:
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise ValueError(missing_message)
    return row


def print_row_summary(prefix: str, row_id: int) -> None:
    print(f"{prefix} id={row_id}")


def render_optional(label: str, value: object | None) -> str:
    if value is None or value == "":
        return ""
    return f" {label}={value}"


def render_event(row: sqlite3.Row) -> str:
    parts = [
        f"{row['id']}",
        row["happened_at"],
        row["event_type"],
        f"company={row['company_name']}",
    ]
    for label, column in (
        ("job", "job_title"),
        ("contact", "contact_name"),
        ("artifact", "artifact_type"),
        ("gap", "gap_description"),
        ("action", "action_kind"),
    ):
        if row[column]:
            parts.append(f"{label}={row[column]}")
    if row["notes"]:
        parts.append(f"notes={row['notes']}")
    return " | ".join(parts)


def event_type_for_job_status(status: str) -> str:
    if status == "applied":
        return "application_submitted"
    if status == "interviewing":
        return "interview"
    if status == "rejected":
        return "rejection_received"
    return "status_changed"


def event_type_for_artifact_status(status: str) -> str:
    if status == "sent":
        return "artifact_sent"
    return "status_changed"


def read_events(
    connection: sqlite3.Connection,
    *,
    company_id: int | None = None,
    limit: int = 50,
) -> list[sqlite3.Row]:
    parameters: list[object] = []
    predicates = ["events.event_type NOT IN ('company_added', 'job_added')"]
    if company_id is not None:
        predicates.append("events.company_id = ?")
        parameters.append(company_id)
    where = f"WHERE {' AND '.join(predicates)}"
    parameters.append(limit)
    rows = connection.execute(
        f"""
        SELECT events.*, companies.name AS company_name, jobs.title AS job_title,
            contacts.name AS contact_name, artifacts.type AS artifact_type,
            gaps.description AS gap_description, actions.kind AS action_kind
        FROM events
        JOIN companies ON companies.id = events.company_id
        LEFT JOIN jobs ON jobs.id = events.job_id
        LEFT JOIN contacts ON contacts.id = events.contact_id
        LEFT JOIN artifacts ON artifacts.id = events.artifact_id
        LEFT JOIN gaps ON gaps.id = events.gap_id
        LEFT JOIN actions ON actions.id = events.action_id
        {where}
        ORDER BY events.happened_at DESC, events.id DESC
        LIMIT ?
        """,
        tuple(parameters),
    ).fetchall()
    return list(reversed(rows))


def command_company_add(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        with connection:
            company_id = create_company(connection, args)
    print(f"company added id={company_id} name={args.name}")
    return 0


def command_company_update(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        with connection:
            company = get_company(connection, args.name)
            values = {
                key: value
                for key, value in {
                    "tier": args.tier,
                    "lanes": args.lanes,
                    "why_interesting": args.why_interesting,
                    "fit_thesis": args.fit_thesis,
                    "known_gaps": args.known_gaps,
                    "products_used": args.products_used,
                    "target_roles": args.target_roles,
                    "career_url": args.career_url,
                    "ats_type": args.ats_type,
                    "status": args.status,
                    "cooldown_until": args.cooldown_until,
                    "notes": args.notes,
                    "last_touched_at": utc_now(),
                }.items()
                if value is not None
            }
            update_columns(connection, "companies", int(company["id"]), values)
            generate_company_actions(connection, company_id=int(company["id"]))
    print(f"company updated name={args.name}")
    return 0


def command_company_list(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    filters = []
    params: list[object] = []
    if args.status:
        filters.append("status = ?")
        params.append(args.status)
    if args.tier:
        filters.append("tier = ?")
        params.append(args.tier)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM companies
            {where}
            ORDER BY COALESCE(tier, 9), name_key
            """,
            params,
        ).fetchall()
    for row in rows:
        print_company_row(row)
    if not rows:
        print("no companies")
    return 0


def command_company_import(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    import_path = Path(args.file)
    require_database(db_path)
    rows = company_import_rows(import_path)
    now = utc_now()
    outcomes: list[CompanyImportOutcome] = []
    with closing(connect(db_path)) as connection:
        with connection:
            for row_number, raw_row in enumerate(rows, start=1):
                outcomes.append(
                    import_researched_company_row(
                        connection,
                        row_number=row_number,
                        raw_row=raw_row,
                        now=now,
                    )
                )

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.company_state] = counts.get(outcome.company_state, 0) + 1
        counts[outcome.source_state] = counts.get(outcome.source_state, 0) + 1
        print(format_company_import_outcome(outcome))

    summary = " ".join(f"{key}={counts[key]}" for key in sorted(counts))
    print(f"company import rows={len(outcomes)} {summary}".rstrip())
    return 0


def command_company_show(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        company = get_company(connection, args.name)
        jobs = connection.execute(
            """
            SELECT * FROM jobs
            WHERE company_id = ?
                AND status NOT IN ('ignored_by_filter', 'closed', 'archived')
            ORDER BY updated_at DESC, id
            """,
            (company["id"],),
        ).fetchall()
        actions = connection.execute(
            action_rows_query(
                f"WHERE actions.company_id = ? AND {open_action_where_clause('actions')}"
            ),
            (company["id"],),
        ).fetchall()
        next_action = actions[0] if actions else None
        last_outcome = connection.execute(
            """
            SELECT events.event_type, events.happened_at, events.notes, jobs.title AS job_title
            FROM events
            LEFT JOIN jobs ON jobs.id = events.job_id
            WHERE events.company_id = ?
                AND event_type IN (
                    'application_submitted',
                    'interview',
                    'rejection_received',
                    'status_changed'
                )
            ORDER BY events.happened_at DESC, events.id DESC
            LIMIT 1
            """,
            (company["id"],),
        ).fetchone()
        last_application = connection.execute(
            """
            SELECT events.happened_at, jobs.title AS job_title
            FROM events
            JOIN jobs ON jobs.id = events.job_id
            WHERE events.company_id = ?
                AND events.event_type = 'application_submitted'
            ORDER BY events.happened_at DESC, events.id DESC
            LIMIT 1
            """,
            (company["id"],),
        ).fetchone()

    print(f"Company: {company['name']}")
    print(
        "Summary: "
        + " | ".join(
            [
                f"tier={company['tier'] or 'unset'}",
                f"status={company['status']}",
                f"lanes={company['lanes'] or 'unset'}",
            ]
        )
    )
    print(f"Cooldown: {company['cooldown_until'] or 'none'}")
    print(f"Last touched: last_touched_at={company['last_touched_at'] or 'none'}")
    if last_application:
        print(
            f"Last applied role: {last_application['job_title']} at {last_application['happened_at']}"
        )
    else:
        print("Last applied role: none")
    if last_outcome:
        subject = f" job={last_outcome['job_title']}" if last_outcome["job_title"] else ""
        print(
            f"Last outcome: {last_outcome['event_type']} at {last_outcome['happened_at']}{subject}"
        )
    else:
        print("Last outcome: none")

    print("Active jobs:")
    if jobs:
        for job in jobs:
            print(f"- {format_job(job)}")
    else:
        print("- none")

    print("Open actions:")
    if actions:
        for action in actions:
            print(f"- {format_action(action)}")
    else:
        print("- none")

    print(f"Next best action: {format_action(next_action) if next_action else 'none'}")
    return 0


def command_source_add(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        with connection:
            source_id = create_company_source(connection, args)
    print(
        f"source added id={source_id} company={args.company} "
        f"type={args.source_type} key={args.source_key}"
    )
    return 0


def command_source_list(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    filters = []
    params: list[object] = []
    if args.company:
        filters.append("companies.name_key = ?")
        params.append(company_name_key(args.company))
    if args.status:
        filters.append("company_sources.status = ?")
        params.append(args.status)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            f"""
            SELECT company_sources.*, companies.name AS company_name
            FROM company_sources
            JOIN companies ON companies.id = company_sources.company_id
            {where}
            ORDER BY companies.name_key, company_sources.source_type, company_sources.id
            """,
            params,
        ).fetchall()
    for row in rows:
        parts = [
            f"id={row['id']}",
            f"company={row['company_name']}",
            f"type={row['source_type']}",
            f"key={row['source_key']}",
            f"status={row['status']}",
            f"last_polled={row['last_polled_at'] or 'never'}",
        ]
        if row["source_url"]:
            parts.append(f"url={row['source_url']}")
        print(" | ".join(parts))
    if not rows:
        print("no sources")
    return 0


def poll_source_rows(
    connection: sqlite3.Connection,
    *,
    company: str | None,
    source_id: int | None,
) -> list[sqlite3.Row]:
    filters = ["company_sources.status = 'active'"]
    params: list[object] = []
    if company:
        filters.append("companies.name_key = ?")
        params.append(company_name_key(company))
    if source_id is not None:
        filters.append("company_sources.id = ?")
        params.append(source_id)
    where = f"WHERE {' AND '.join(filters)}"
    return connection.execute(
        f"""
        SELECT company_sources.*, companies.name AS company_name
        FROM company_sources
        JOIN companies ON companies.id = company_sources.company_id
        {where}
        ORDER BY companies.name_key, company_sources.id
        """,
        params,
    ).fetchall()


def store_polled_job(
    connection: sqlite3.Connection,
    *,
    source: sqlite3.Row,
    discovered: DiscoveredJob,
    now: str,
) -> PollStoreResult:
    company = connection.execute(
        "SELECT * FROM companies WHERE id = ?", (source["company_id"],)
    ).fetchone()
    if company is None:
        raise ValueError(f"Company not found for source: {source['id']}")
    canonical_url = normalize_url(discovered.canonical_url)
    status, fit_score, lane, discovery_status = classify_polled_job(company, discovered)
    duplicate_matches = job_duplicate_matches(
        connection,
        company_id=int(company["id"]),
        title=discovered.title,
        canonical_url=canonical_url,
        source=job_source_identity(source),
        source_job_id=discovered.source_job_id,
        location=discovered.location,
        remote_status=discovered.remote_status,
        now=now,
    )
    if duplicate_matches:
        return PollStoreResult(status="duplicate")

    cursor = connection.execute(
        """
        INSERT INTO jobs(
            company_id, title, canonical_url, source, source_job_id, location,
            remote_status, lane, status, discovery_status, fit_score,
            compensation_signal, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company["id"],
            discovered.title,
            canonical_url,
            job_source_identity(source),
            discovered.source_job_id,
            discovered.location,
            discovered.remote_status,
            lane,
            status,
            discovery_status,
            fit_score,
            discovered.compensation_signal,
            now,
            now,
        ),
    )
    job_id = int(cursor.lastrowid)
    generate_job_actions(connection, job_id=job_id, now=now)
    log_event(
        connection,
        company_id=int(company["id"]),
        job_id=job_id,
        event_type="job_added",
        notes=f"poll:{source['source_type']}:{discovered.title}",
        now=now,
    )
    return PollStoreResult(status=status, job_id=job_id)


def command_poll(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        sources = poll_source_rows(
            connection,
            company=args.company,
            source_id=args.source_id,
        )
        if not sources:
            print("no active sources")
            return 0

        failed = False
        for source in sources:
            now = utc_now()
            try:
                discovered_jobs = fetch_source_jobs(source)
            except (HTTPError, URLError, OSError, ValueError) as error:
                failed = True
                print(
                    "poll "
                    f"source_id={source['id']} company={source['company_name']} "
                    f"type={source['source_type']} failed error={error}"
                )
                continue
            inserted = 0
            ignored = 0
            duplicates = 0
            screen_actions = 0
            with connection:
                for discovered in discovered_jobs:
                    result = store_polled_job(
                        connection,
                        source=source,
                        discovered=discovered,
                        now=now,
                    )
                    if result.status == "duplicate":
                        duplicates += 1
                        continue
                    inserted += 1
                    if result.status == "ignored_by_filter":
                        ignored += 1
                    if result.status == "screening" and result.job_id is not None:
                        action = connection.execute(
                            """
                            SELECT 1
                            FROM actions
                            WHERE job_id = ?
                                AND queue = 'screen'
                                AND kind = 'screen_role'
                                AND status IN ('queued', 'in_progress', 'blocked', 'rescheduled')
                            LIMIT 1
                            """,
                            (result.job_id,),
                        ).fetchone()
                        if action is not None:
                            screen_actions += 1
                connection.execute(
                    """
                    UPDATE company_sources
                    SET last_polled_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, source["id"]),
                )
                connection.execute(
                    """
                    UPDATE companies
                    SET last_checked_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, source["company_id"]),
                )
            print(
                "poll "
                f"source_id={source['id']} company={source['company_name']} "
                f"type={source['source_type']} discovered={len(discovered_jobs)} "
                f"inserted={inserted} ignored={ignored} duplicates={duplicates} "
                f"screen_actions={screen_actions}"
            )
    return 1 if failed else 0


def command_query_import(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    payload = read_query_import_payload(args)
    source = payload_string(payload, "source", required=True)
    query_text = payload_string(payload, "query_text", "query", required=True)
    assert source is not None
    assert query_text is not None
    pack = payload_string(payload, "pack")
    sort_mode = payload_string(payload, "sort_mode", "sort")
    raw_source_reference = payload_string(
        payload,
        "raw_source_reference",
        "raw_reference",
        "source_reference",
    )
    status = payload_status(payload)
    notes = payload_string(payload, "notes")
    results = query_import_results(payload)
    result_count = (
        len(results)
        if results
        else payload_non_negative_int(payload, "result_count") or 0
    )
    import_key = query_run_import_key(
        source=source,
        pack=pack,
        query_text=query_text,
        sort_mode=sort_mode,
        raw_source_reference=raw_source_reference,
    )
    now = utc_now()

    with closing(connect(db_path)) as connection:
        with connection:
            existing = connection.execute(
                "SELECT id FROM query_runs WHERE import_key = ?",
                (import_key,),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO query_runs(
                        source, pack, query_text, sort_mode, status, notes,
                        raw_source_reference, import_key, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source,
                        pack,
                        query_text,
                        sort_mode,
                        status,
                        notes,
                        raw_source_reference,
                        import_key,
                        now,
                        now,
                    ),
                )
                query_run_id = int(cursor.lastrowid)
                import_state = "created"
            else:
                query_run_id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE query_runs
                    SET source = ?, pack = ?, query_text = ?, sort_mode = ?,
                        status = ?, notes = ?, raw_source_reference = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        source,
                        pack,
                        query_text,
                        sort_mode,
                        status,
                        notes,
                        raw_source_reference,
                        now,
                        query_run_id,
                    ),
                )
                connection.execute(
                    "DELETE FROM query_run_results WHERE query_run_id = ?",
                    (query_run_id,),
                )
                import_state = "updated"

            for result in results:
                duplicate = duplicate_for_query_result(
                    connection,
                    source=source,
                    result=result,
                    now=now,
                )
                final_status = str(result["result_status"])
                duplicate_job_id = None
                duplicate_level = None
                duplicate_reason = None
                if duplicate is not None:
                    final_status = "duplicate"
                    duplicate_job_id = duplicate["job_id"]
                    duplicate_level = duplicate["level"]
                    duplicate_reason = duplicate["reason"]
                result_key = query_result_key(
                    company_name=(
                        str(result["company_name"])
                        if result["company_name"]
                        else None
                    ),
                    title=str(result["title"]),
                    canonical_url=(
                        str(result["canonical_url"])
                        if result["canonical_url"]
                        else None
                    ),
                    source_job_id=(
                        str(result["source_job_id"])
                        if result["source_job_id"]
                        else None
                    ),
                    location=str(result["location"]) if result["location"] else None,
                    raw_source_reference=(
                        str(result["raw_source_reference"])
                        if result["raw_source_reference"]
                        else None
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO query_run_results(
                        query_run_id, ordinal, company_name, title, canonical_url,
                        source_job_id, location, remote_status, compensation_signal,
                        result_status, duplicate_job_id, duplicate_level,
                        duplicate_reason, notes, raw_source_reference, raw_payload,
                        result_key, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(query_run_id, result_key) DO UPDATE SET
                        ordinal = excluded.ordinal,
                        company_name = excluded.company_name,
                        title = excluded.title,
                        canonical_url = excluded.canonical_url,
                        source_job_id = excluded.source_job_id,
                        location = excluded.location,
                        remote_status = excluded.remote_status,
                        compensation_signal = excluded.compensation_signal,
                        result_status = excluded.result_status,
                        duplicate_job_id = excluded.duplicate_job_id,
                        duplicate_level = excluded.duplicate_level,
                        duplicate_reason = excluded.duplicate_reason,
                        notes = excluded.notes,
                        raw_source_reference = excluded.raw_source_reference,
                        raw_payload = excluded.raw_payload,
                        updated_at = excluded.updated_at
                    """,
                    (
                        query_run_id,
                        result["ordinal"],
                        result["company_name"],
                        result["title"],
                        result["canonical_url"],
                        result["source_job_id"],
                        result["location"],
                        result["remote_status"],
                        result["compensation_signal"],
                        final_status,
                        duplicate_job_id,
                        duplicate_level,
                        duplicate_reason,
                        result["notes"],
                        result["raw_source_reference"],
                        result["raw_payload"],
                        result_key,
                        now,
                        now,
                    ),
                )

            counts = {"accepted": 0, "rejected": 0, "duplicate": 0}
            if results:
                count_rows = connection.execute(
                    """
                    SELECT result_status, COUNT(*) AS status_count
                    FROM query_run_results
                    WHERE query_run_id = ?
                    GROUP BY result_status
                    """,
                    (query_run_id,),
                ).fetchall()
                result_count = sum(int(row["status_count"]) for row in count_rows)
                for row in count_rows:
                    status_key = str(row["result_status"])
                    if status_key in counts:
                        counts[status_key] = int(row["status_count"])

            connection.execute(
                """
                UPDATE query_runs
                SET result_count = ?, accepted_count = ?, rejected_count = ?,
                    duplicate_count = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    result_count,
                    counts["accepted"],
                    counts["rejected"],
                    counts["duplicate"],
                    now,
                    query_run_id,
                ),
            )

    print(
        f"query run {import_state} id={query_run_id} source={source}"
        + render_optional("pack", pack)
        + f" status={status} results={result_count}"
        + f" accepted={counts['accepted']} rejected={counts['rejected']}"
        + f" duplicates={counts['duplicate']}"
    )
    return 0


def command_query_list(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    if args.limit <= 0:
        raise ValueError("query list --limit must be a positive integer")
    filters = []
    params: list[object] = []
    if args.source:
        filters.append("source = ?")
        params.append(args.source)
    if args.pack:
        filters.append("pack = ?")
        params.append(args.pack)
    if args.status:
        filters.append("status = ?")
        params.append(args.status)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(args.limit)
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM query_runs
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    for row in rows:
        print(
            f"{row['id']} | source={row['source']}"
            + render_optional("pack", row["pack"])
            + f" | status={row['status']} | results={row['result_count']}"
            + f" | accepted={row['accepted_count']}"
            + f" | rejected={row['rejected_count']}"
            + f" | duplicates={row['duplicate_count']}"
            + f" | created={row['created_at']}"
        )
    if not rows:
        print("no query runs")
    return 0


def command_query_show(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        run = connection.execute(
            "SELECT * FROM query_runs WHERE id = ?",
            (args.query_run_id,),
        ).fetchone()
        if run is None:
            raise ValueError(f"Query run not found: {args.query_run_id}")
        rows = connection.execute(
            """
            SELECT query_run_results.*, jobs.title AS duplicate_title,
                companies.name AS duplicate_company
            FROM query_run_results
            LEFT JOIN jobs ON jobs.id = query_run_results.duplicate_job_id
            LEFT JOIN companies ON companies.id = jobs.company_id
            WHERE query_run_results.query_run_id = ?
            ORDER BY query_run_results.ordinal, query_run_results.id
            """,
            (args.query_run_id,),
        ).fetchall()

    print(f"Query run: #{run['id']}")
    print(
        "Metadata: "
        + " | ".join(
            [
                f"source={run['source']}",
                f"pack={run['pack'] or 'unset'}",
                f"query={run['query_text']}",
                f"sort={run['sort_mode'] or 'unset'}",
                f"status={run['status']}",
                f"created={run['created_at']}",
            ]
        )
    )
    print(
        "Counts: "
        f"results={run['result_count']} accepted={run['accepted_count']} "
        f"rejected={run['rejected_count']} duplicates={run['duplicate_count']}"
    )
    if run["raw_source_reference"]:
        print(f"Raw source: {run['raw_source_reference']}")
    if run["notes"]:
        print(f"Notes: {run['notes']}")
    print("Results:")
    if not rows:
        print("- none")
        return 0
    for row in rows:
        duplicate_text = ""
        if row["duplicate_job_id"]:
            duplicate_text = (
                f" | duplicate_job=#{row['duplicate_job_id']}"
                f" {row['duplicate_company']} / {row['duplicate_title']}"
                f" reason={row['duplicate_reason']}"
            )
        print(
            f"- {row['ordinal']} | status={row['result_status']} | "
            f"{row['company_name'] or 'Unknown'} | {row['title']}"
            + render_optional("url", row["canonical_url"])
            + render_optional("source_job_id", row["source_job_id"])
            + render_optional("location", row["location"])
            + render_optional("remote", row["remote_status"])
            + render_optional("comp", row["compensation_signal"])
            + duplicate_text
            + render_optional("notes", row["notes"])
        )
    return 0


def command_job_add(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    company_name = getattr(args, "company_option", None) or args.company
    title = getattr(args, "title_option", None) or args.title
    if not company_name or not title:
        raise ValueError("job add requires company and title")
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            company = get_company(connection, company_name)
            canonical_url = normalize_url(args.url)
            duplicate_matches = job_duplicate_matches(
                connection,
                company_id=int(company["id"]),
                title=title,
                canonical_url=canonical_url,
                source=args.source,
                source_job_id=args.source_job_id,
                location=args.location,
                remote_status=args.remote_status,
                now=now,
            )
            if duplicate_matches:
                print(format_duplicate_match(duplicate_matches[0]))
                return 0
            cursor = connection.execute(
                """
                INSERT INTO jobs(
                    company_id, title, canonical_url, source, source_job_id, location,
                    remote_status, role_level, lane, status, discovery_status, fit_score,
                    relationship_path, artifact_opportunity, recommended_resume,
                    materials_status, application_folder, material_paths,
                    compensation_signal, rejection_reason, application_outcome,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company["id"],
                    title,
                    canonical_url,
                    args.source,
                    args.source_job_id,
                    args.location,
                    args.remote_status,
                    args.role_level,
                    args.lane,
                    args.status,
                    args.discovery_status,
                    args.fit_score,
                    args.relationship_path,
                    args.artifact_opportunity,
                    args.recommended_resume,
                    args.materials_status,
                    args.application_folder,
                    args.material_paths,
                    args.compensation_signal,
                    args.rejection_reason,
                    args.application_outcome,
                    now,
                    now,
                ),
            )
            job_id = int(cursor.lastrowid)
            generate_job_actions(connection, job_id=job_id, now=now)
            log_event(
                connection,
                company_id=int(company["id"]),
                job_id=job_id,
                event_type=(
                    "job_added"
                    if args.status == "discovered"
                    else event_type_for_job_status(args.status)
                ),
                notes=(
                    title
                    if args.status == "discovered"
                    else f"job #{job_id} status initialized: {args.status}"
                ),
                now=now,
            )
    print(f"job id={job_id} added company={company_name} title={title}")
    return 0


def command_job_update(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        with connection:
            job = get_job(connection, args.job_id)
            values = {
                key: value
                for key, value in {
                    "title": getattr(args, "title", None),
                    "canonical_url": normalize_url(args.url),
                    "source": args.source,
                    "source_job_id": args.source_job_id,
                    "location": args.location,
                    "remote_status": args.remote_status,
                    "role_level": args.role_level,
                    "lane": args.lane,
                    "status": args.status,
                    "discovery_status": args.discovery_status,
                    "fit_score": args.fit_score,
                    "relationship_path": args.relationship_path,
                    "artifact_opportunity": args.artifact_opportunity,
                    "recommended_resume": args.recommended_resume,
                    "materials_status": args.materials_status,
                    "application_folder": args.application_folder,
                    "material_paths": args.material_paths,
                    "compensation_signal": args.compensation_signal,
                    "rejection_reason": args.rejection_reason,
                    "application_outcome": args.application_outcome,
                }.items()
                if value is not None
            }
            update_columns(connection, "jobs", args.job_id, values)
            generate_job_actions(connection, job_id=args.job_id)
            updated = get_job(connection, args.job_id)
            if args.status and args.status != job["status"]:
                log_event(
                    connection,
                    company_id=int(updated["company_id"]),
                    job_id=args.job_id,
                    event_type=event_type_for_job_status(args.status),
                    happened_at=getattr(args, "happened_at", None),
                    notes=(
                        getattr(args, "notes", None)
                        or args.rejection_reason
                        or f"{job['status']} -> {args.status}"
                    ),
                )
    print(f"job updated id={args.job_id}")
    return 0


def command_job_status(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            job = get_job(connection, args.job_id)
            connection.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                (args.status, now, args.job_id),
            )
            generate_job_actions(connection, job_id=args.job_id, now=now)
            event_id = log_event(
                connection,
                company_id=int(job["company_id"]),
                job_id=args.job_id,
                event_type=event_type_for_job_status(args.status),
                happened_at=args.happened_at,
                notes=args.notes or f"{job['status']} -> {args.status}",
                now=now,
            )
    print(f"job id={args.job_id} status={args.status} event_id={event_id}")
    return 0


def command_job_show(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        job = connection.execute(
            """
            SELECT jobs.*, companies.name AS company_name
            FROM jobs
            JOIN companies ON companies.id = jobs.company_id
            WHERE jobs.id = ?
            """,
            (args.job_id,),
        ).fetchone()
        if job is None:
            raise ValueError(f"Job not found: {args.job_id}")
        actions = connection.execute(
            action_rows_query(
                f"WHERE actions.job_id = ? AND {open_action_where_clause('actions')}"
            ),
            (args.job_id,),
        ).fetchall()

    print(f"Job: #{job['id']} {job['title']}")
    print(f"Company: {job['company_name']}")
    print(
        "Summary: "
        + " | ".join(
            [
                f"status={job['status']}",
                f"fit={job['fit_score'] if job['fit_score'] is not None else 'unset'}",
                f"lane={job['lane'] or 'unset'}",
            ]
        )
    )
    if job["canonical_url"]:
        print(f"URL: {job['canonical_url']}")
    print("Open actions:")
    if actions:
        for action in actions:
            print(f"- {format_action(action)}")
    else:
        print("- none")
    return 0


def command_job_list(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    filters = []
    params: list[object] = []
    if args.company:
        filters.append("companies.name_key = ?")
        params.append(company_name_key(args.company))
    if args.status:
        filters.append("jobs.status = ?")
        params.append(args.status)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            f"""
            SELECT jobs.*, companies.name AS company_name
            FROM jobs
            JOIN companies ON companies.id = jobs.company_id
            {where}
            ORDER BY companies.name_key, jobs.updated_at DESC, jobs.id
            """,
            params,
        ).fetchall()
    for row in rows:
        print(f"{row['company_name']} | {format_job(row)}")
    if not rows:
        print("no jobs")
    return 0


def command_contact_add(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            company_id = resolve_company_id(connection, args.company)
            cursor = connection.execute(
                """
                INSERT INTO contacts(
                    company_id, name, title, source, link, relationship_strength,
                    last_contacted_at, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    args.name,
                    args.title,
                    args.source,
                    args.link,
                    args.relationship_strength,
                    args.last_contacted,
                    args.notes,
                    now,
                    now,
                ),
            )
            contact_id = int(cursor.lastrowid)
            touch_company(connection, company_id, args.last_contacted)
    print_row_summary("contact", contact_id)
    return 0


def command_contact_list(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    parameters: list[object] = []
    predicates: list[str] = []
    with closing(connect(db_path)) as connection:
        if args.company:
            predicates.append("contacts.company_id = ?")
            parameters.append(resolve_company_id(connection, args.company))
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        rows = connection.execute(
            f"""
            SELECT contacts.*, companies.name AS company_name
            FROM contacts
            JOIN companies ON companies.id = contacts.company_id
            {where}
            ORDER BY contacts.last_contacted_at DESC, contacts.name
            """,
            tuple(parameters),
        ).fetchall()
    for row in rows:
        print(
            f"{row['id']} | {row['company_name']} | {row['name']}"
            + render_optional("title", row["title"])
            + render_optional("relationship_strength", row["relationship_strength"])
            + render_optional("last_contacted", row["last_contacted_at"])
            + render_optional("source", row["source"])
            + render_optional("link", row["link"])
            + render_optional("notes", row["notes"])
        )
    if not rows:
        print("no contacts")
    return 0


def command_artifact_add(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            company_id = resolve_company_id(connection, args.company)
            cursor = connection.execute(
                """
                INSERT INTO artifacts(
                    company_id, job_id, type, status, thesis, link, path, notes,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    args.job_id,
                    args.type,
                    args.status,
                    args.thesis,
                    args.link,
                    args.path,
                    args.notes,
                    now,
                    now,
                ),
            )
            artifact_id = int(cursor.lastrowid)
            touch_company(connection, company_id)
            event_id = None
            if args.status == "sent":
                event_id = log_event(
                    connection,
                    company_id=company_id,
                    job_id=args.job_id,
                    artifact_id=artifact_id,
                    event_type="artifact_sent",
                    happened_at=args.happened_at,
                    notes=args.notes or f"artifact #{artifact_id} sent",
                    now=now,
                )
    if event_id is None:
        print_row_summary("artifact", artifact_id)
    else:
        print(f"artifact id={artifact_id} event_id={event_id}")
    return 0


def command_artifact_list(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    parameters: list[object] = []
    predicates: list[str] = []
    with closing(connect(db_path)) as connection:
        if args.company:
            predicates.append("artifacts.company_id = ?")
            parameters.append(resolve_company_id(connection, args.company))
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        rows = connection.execute(
            f"""
            SELECT artifacts.*, companies.name AS company_name, jobs.title AS job_title
            FROM artifacts
            JOIN companies ON companies.id = artifacts.company_id
            LEFT JOIN jobs ON jobs.id = artifacts.job_id
            {where}
            ORDER BY artifacts.updated_at DESC, artifacts.id DESC
            """,
            tuple(parameters),
        ).fetchall()
    for row in rows:
        print(
            f"{row['id']} | {row['company_name']} | type={row['type']} | status={row['status']}"
            + render_optional("job", row["job_title"])
            + render_optional("thesis", row["thesis"])
            + render_optional("link", row["link"])
            + render_optional("path", row["path"])
            + render_optional("notes", row["notes"])
        )
    if not rows:
        print("no artifacts")
    return 0


def command_artifact_status(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            row = require_row(
                connection,
                "SELECT company_id, job_id, status, link, path FROM artifacts WHERE id = ?",
                (args.artifact_id,),
                f"Artifact not found: {args.artifact_id}",
            )
            if (
                args.status not in ("idea", "queued", "drafting")
                and not (args.link or args.path or row["link"] or row["path"])
            ):
                raise ValueError(
                    f"artifact status {args.status} requires an existing link/path or --link/--path"
                )
            connection.execute(
                """
                UPDATE artifacts
                SET status = ?, link = COALESCE(?, link), path = COALESCE(?, path),
                    updated_at = ?
                WHERE id = ?
                """,
                (args.status, args.link, args.path, now, args.artifact_id),
            )
            event_id = log_event(
                connection,
                company_id=int(row["company_id"]),
                job_id=row["job_id"],
                artifact_id=args.artifact_id,
                event_type=event_type_for_artifact_status(args.status),
                happened_at=args.happened_at,
                notes=args.notes
                or f"artifact #{args.artifact_id} status changed: {row['status']} -> {args.status}",
                now=now,
            )
    print(f"artifact id={args.artifact_id} status={args.status} event_id={event_id}")
    return 0


def command_gap_add(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    if args.company is None and args.job_id is None:
        raise ValueError("gap add requires --company or --job-id")
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            company_id = resolve_company_id(connection, args.company) if args.company else None
            if company_id is None and args.job_id is not None:
                job = require_row(
                    connection,
                    "SELECT company_id FROM jobs WHERE id = ?",
                    (args.job_id,),
                    f"Job not found: {args.job_id}",
                )
                company_id = int(job["company_id"])
            cursor = connection.execute(
                """
                INSERT INTO gaps(
                    company_id, job_id, gap_type, description, severity, status,
                    resolution_action, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    args.job_id,
                    args.gap_type,
                    args.description,
                    args.severity,
                    args.status,
                    args.resolution_action,
                    now,
                    now,
                ),
            )
            gap_id = int(cursor.lastrowid)
            event_id = log_event(
                connection,
                company_id=int(company_id),
                job_id=args.job_id,
                gap_id=gap_id,
                event_type="gap_identified",
                happened_at=args.happened_at,
                notes=args.notes or args.description,
                now=now,
            )
    print(f"gap id={gap_id} event_id={event_id}")
    return 0


def command_gap_list(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    parameters: list[object] = []
    predicates: list[str] = []
    with closing(connect(db_path)) as connection:
        if args.company:
            predicates.append("COALESCE(gaps.company_id, jobs.company_id) = ?")
            parameters.append(resolve_company_id(connection, args.company))
        if args.status:
            predicates.append("gaps.status = ?")
            parameters.append(args.status)
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        rows = connection.execute(
            f"""
            SELECT gaps.*, companies.name AS company_name, jobs.title AS job_title
            FROM gaps
            LEFT JOIN jobs ON jobs.id = gaps.job_id
            LEFT JOIN companies
                ON companies.id = COALESCE(gaps.company_id, jobs.company_id)
            {where}
            ORDER BY
                CASE gaps.severity
                    WHEN 'high' THEN 3
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 1
                    ELSE 0
                END DESC,
                gaps.updated_at DESC,
                gaps.id DESC
            """,
            tuple(parameters),
        ).fetchall()
    for row in rows:
        print(
            f"{row['id']} | {row['company_name']} | type={row['gap_type']} | "
            f"severity={row['severity']} | status={row['status']} | {row['description']}"
            + render_optional("job", row["job_title"])
            + render_optional("resolution_action", row["resolution_action"])
        )
    if not rows:
        print("no gaps")
    return 0


def command_gap_status(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            row = require_row(
                connection,
                """
                SELECT gaps.company_id, gaps.job_id, gaps.status, jobs.company_id AS job_company_id
                FROM gaps
                LEFT JOIN jobs ON jobs.id = gaps.job_id
                WHERE gaps.id = ?
                """,
                (args.gap_id,),
                f"Gap not found: {args.gap_id}",
            )
            company_id = int(row["company_id"] or row["job_company_id"])
            connection.execute(
                """
                UPDATE gaps
                SET status = ?, resolution_action = COALESCE(?, resolution_action),
                    updated_at = ?
                WHERE id = ?
                """,
                (args.status, args.resolution_action, now, args.gap_id),
            )
            event_id = log_event(
                connection,
                company_id=company_id,
                job_id=row["job_id"],
                gap_id=args.gap_id,
                event_type="status_changed",
                happened_at=args.happened_at,
                notes=args.notes or f"gap #{args.gap_id} status changed: {row['status']} -> {args.status}",
                now=now,
            )
    print(f"gap id={args.gap_id} status={args.status} event_id={event_id}")
    return 0


def command_event_add(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        with connection:
            company_id = resolve_company_id(connection, args.company)
            event_id = log_event(
                connection,
                company_id=company_id,
                job_id=args.job_id,
                contact_id=args.contact_id,
                artifact_id=args.artifact_id,
                gap_id=args.gap_id,
                action_id=args.action_id,
                event_type=args.event_type,
                happened_at=args.happened_at,
                notes=args.notes,
            )
    print_row_summary("event", event_id)
    return 0


def command_event_list(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        company_id = resolve_company_id(connection, args.company) if args.company else None
        rows = read_events(connection, company_id=company_id, limit=args.limit)
    for row in rows:
        print(render_event(row))
    if not rows:
        print("no events")
    return 0


def percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def command_metrics(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    until = parse_optional_utc(args.until) if args.until else datetime.now(timezone.utc)
    assert until is not None
    since = (
        parse_optional_utc(args.since)
        if args.since
        else until - timedelta(days=args.days)
    )
    assert since is not None
    since_text = since.isoformat()
    until_text = until.isoformat()

    with closing(connect(db_path)) as connection:
        jobs_screened = connection.execute(
            """
            SELECT COUNT(DISTINCT job_id)
            FROM actions
            WHERE queue = 'screen'
                AND status = 'done'
                AND job_id IS NOT NULL
                AND completed_at >= ?
                AND completed_at < ?
            """,
            (since_text, until_text),
        ).fetchone()[0]
        applications_submitted = connection.execute(
            """
            SELECT COUNT(DISTINCT job_id)
            FROM events
            WHERE event_type = 'application_submitted'
                AND job_id IS NOT NULL
                AND happened_at >= ?
                AND happened_at < ?
            """,
            (since_text, until_text),
        ).fetchone()[0]
        applications_by_lane = connection.execute(
            """
            SELECT COALESCE(jobs.lane, 'unset') AS lane, COUNT(DISTINCT events.job_id) AS count
            FROM events
            JOIN jobs ON jobs.id = events.job_id
            WHERE events.event_type = 'application_submitted'
                AND events.happened_at >= ?
                AND events.happened_at < ?
            GROUP BY COALESCE(jobs.lane, 'unset')
            ORDER BY lane
            """,
            (since_text, until_text),
        ).fetchall()
        ready_jobs = connection.execute(
            """
            SELECT COUNT(DISTINCT job_id)
            FROM events
            WHERE job_id IS NOT NULL
                AND event_type = 'status_changed'
                AND notes LIKE '%ready_to_apply%'
                AND happened_at >= ?
                AND happened_at < ?
            """,
            (since_text, until_text),
        ).fetchone()[0]
        interviews = connection.execute(
            """
            SELECT COUNT(DISTINCT job_id)
            FROM events
            WHERE event_type = 'interview'
                AND job_id IS NOT NULL
                AND happened_at >= ?
                AND happened_at < ?
            """,
            (since_text, until_text),
        ).fetchone()[0]
        rejections = connection.execute(
            """
            SELECT COUNT(DISTINCT job_id)
            FROM events
            WHERE event_type = 'rejection_received'
                AND job_id IS NOT NULL
                AND happened_at >= ?
                AND happened_at < ?
            """,
            (since_text, until_text),
        ).fetchone()[0]
        messages_sent = connection.execute(
            """
            SELECT COUNT(*)
            FROM events
            WHERE event_type = 'message_sent'
                AND happened_at >= ?
                AND happened_at < ?
            """,
            (since_text, until_text),
        ).fetchone()[0]
        outreach_responses = connection.execute(
            """
            SELECT COUNT(*)
            FROM events
            WHERE event_type = 'coffee_chat'
                AND happened_at >= ?
                AND happened_at < ?
            """,
            (since_text, until_text),
        ).fetchone()[0]
        companies_touched = connection.execute(
            """
            SELECT COUNT(DISTINCT company_id)
            FROM events
            WHERE event_type NOT IN ('company_added', 'job_added')
                AND happened_at >= ?
                AND happened_at < ?
            """,
            (since_text, until_text),
        ).fetchone()[0]
        actions_completed = connection.execute(
            """
            SELECT COUNT(*)
            FROM actions
            WHERE status = 'done'
                AND completed_at >= ?
                AND completed_at < ?
            """,
            (since_text, until_text),
        ).fetchone()[0]
        average_days = connection.execute(
            """
            SELECT AVG(julianday(events.happened_at) - julianday(jobs.created_at))
            FROM events
            JOIN jobs ON jobs.id = events.job_id
            WHERE events.event_type = 'application_submitted'
                AND events.happened_at >= ?
                AND events.happened_at < ?
            """,
            (since_text, until_text),
        ).fetchone()[0]

    lane_summary = ", ".join(
        f"{row['lane']}:{row['count']}" for row in applications_by_lane
    ) or "none"
    print(f"Metrics since={since_text} until={until_text}")
    print(f"jobs_screened={jobs_screened}")
    print(f"applications_submitted={applications_submitted}")
    print(f"applications_by_lane={lane_summary}")
    print(f"ready_to_apply_rate={percent(ready_jobs, jobs_screened)}")
    print(f"interview_rate={percent(interviews, applications_submitted)}")
    print(f"rejection_rate={percent(rejections, applications_submitted)}")
    print(f"outreach_response_rate={percent(outreach_responses, messages_sent)}")
    print(f"companies_touched={companies_touched}")
    print(f"actions_completed={actions_completed}")
    print(
        "average_days_from_discovery_to_application="
        + ("0.0" if average_days is None else f"{average_days:.1f}")
    )
    return 0


def command_report_hygiene(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_current_database_read_only(db_path)
    as_of = parse_report_as_of(args.as_of)
    if args.limit <= 0:
        raise ValueError("report hygiene --limit must be a positive integer")
    if args.company_activity_days < 1:
        raise ValueError("report hygiene --company-activity-days must be positive")
    if args.pending_outcome_days < 1:
        raise ValueError("report hygiene --pending-outcome-days must be positive")
    if args.unscheduled_action_days < 1:
        raise ValueError("report hygiene --unscheduled-action-days must be positive")

    with closing(connect(db_path)) as connection:
        record_count = command_center_record_count(connection)
        stale_actions = stale_hygiene_actions(
            connection,
            as_of=as_of,
            unscheduled_days=args.unscheduled_action_days,
            limit=args.limit,
        )
        outcome_gaps = outcome_hygiene_gaps(
            connection,
            as_of=as_of,
            pending_days=args.pending_outcome_days,
            limit=args.limit,
        )
        companies_without_actions = companies_without_next_action(
            connection,
            as_of=as_of,
            activity_days=args.company_activity_days,
            limit=args.limit,
        )

    print(f"Hygiene report as_of={as_of.isoformat()}")
    print(
        "Thresholds: "
        f"company_activity_days={args.company_activity_days} | "
        f"pending_outcome_days={args.pending_outcome_days} | "
        f"unscheduled_action_days={args.unscheduled_action_days}"
    )
    if record_count == 0:
        print("No command center data.")
        print("Next step: add a company, import a query run, or poll a target company.")
        return 0

    finding_count = (
        len(stale_actions) + len(outcome_gaps) + len(companies_without_actions)
    )
    if finding_count == 0:
        print(
            "All clean: no stale actions, outcome gaps, or active companies "
            "without next action."
        )
        return 0

    print("Stale actions:")
    if stale_actions:
        for row in stale_actions:
            print(format_hygiene_action(row, as_of=as_of))
    else:
        print("- none")

    print("Outcome gaps:")
    if outcome_gaps:
        for gap in outcome_gaps:
            print(format_outcome_gap(gap))
    else:
        print("- none")

    print("Companies with recent activity and no next action:")
    if companies_without_actions:
        for row in companies_without_actions:
            print(format_company_hygiene(row))
    else:
        print("- none")
    return 0


def command_action_next(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    params: list[object] = []
    where = f"WHERE {open_action_where_clause('actions')}"
    if args.queue:
        where += " AND actions.queue = ?"
        params.append(args.queue)
    params.append(args.limit)
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            action_rows_query(where) + " LIMIT ?",
            params,
        ).fetchall()
    for row in rows:
        print(format_action_next(row))
    if not rows:
        scope = f"queue={args.queue}" if args.queue else "all queues"
        print(f"no actions | no open actions | scope={scope}")
        print("next_step=add an action, import a query run, or poll a target company")
    return 0


def command_action_add(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            company_id = resolve_company_id(connection, args.company)
            action_id, created = upsert_action(
                connection,
                company_id=company_id,
                job_id=args.job_id,
                contact_id=args.contact_id,
                artifact_id=args.artifact_id,
                gap_id=args.gap_id,
                queue=args.queue,
                kind=args.kind,
                due_at=args.due_at,
                notes=args.notes,
                now=now,
            )
            touch_company(connection, company_id, now)
    state = "added" if created else "existing"
    print(f"action {state} id={action_id}")
    return 0


def command_action_list(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    filters = []
    params: list[object] = []
    if args.queue:
        filters.append("actions.queue = ?")
        params.append(args.queue)
    if args.status:
        filters.append("actions.status = ?")
        params.append(args.status)
    else:
        filters.append(open_action_where_clause("actions"))
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(args.limit)
    with closing(connect(db_path)) as connection:
        rows = connection.execute(action_rows_query(where) + " LIMIT ?", params).fetchall()
    for row in rows:
        print(format_action(row))
    if not rows:
        print("no actions")
    return 0


def command_action_transition(args: argparse.Namespace, status: str) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            action = connection.execute(
                "SELECT * FROM actions WHERE id = ?", (args.action_id,)
            ).fetchone()
            if action is None:
                raise ValueError(f"Action not found: {args.action_id}")
            if action["status"] in TERMINAL_ACTION_STATUSES:
                if action["status"] == status:
                    print(f"action {status} id={args.action_id}")
                    return 0
                raise ValueError(
                    f"Action {args.action_id} is already terminal: {action['status']}"
                )
            completed_at = now if status == "done" else None
            due_at = getattr(args, "due_at", None)
            connection.execute(
                """
                UPDATE actions
                SET status = ?, completed_at = ?, due_at = COALESCE(?, due_at),
                    notes = COALESCE(?, notes), updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    completed_at,
                    due_at,
                    getattr(args, "notes", None),
                    now,
                    args.action_id,
                ),
            )
            log_event(
                connection,
                company_id=int(action["company_id"]),
                job_id=action["job_id"],
                action_id=args.action_id,
                event_type=f"action_{status}",
                notes=getattr(args, "notes", None) or action["kind"],
                now=now,
            )
            if status == "done" and getattr(args, "message_sent", False):
                log_event(
                    connection,
                    company_id=int(action["company_id"]),
                    job_id=action["job_id"],
                    action_id=args.action_id,
                    event_type="message_sent",
                    notes=getattr(args, "notes", None),
                    now=now,
                )
                generate_message_follow_up(connection, action=action, now=now)
    print(f"action {status} id={args.action_id}")
    return 0


def command_action_reschedule(args: argparse.Namespace) -> int:
    return command_action_transition(args, "rescheduled")


def command_query_packs_list(args: argparse.Namespace) -> int:
    packs = load_query_pack_registry()
    selected_packs = list(packs.values())
    if args.default_only:
        selected_packs = [pack for pack in selected_packs if pack.default_repeatable]

    for pack in selected_packs:
        print(format_query_pack_summary(pack))
    return 0


def command_query_packs_show(args: argparse.Namespace) -> int:
    pack = get_query_pack(args.pack)
    print(f"name={pack.name}")
    print(f"label={pack.label}")
    print(f"type={pack.pack_type}")
    print(f"default_repeatable={str(pack.default_repeatable).lower()}")
    print(f"description={pack.description}")
    print("queries:")
    for index, query in enumerate(pack.queries, start=1):
        print(f"{index}. {query}")
    return 0


def command_query_run(args: argparse.Namespace) -> int:
    pack = get_query_pack(args.pack)
    reason = validate_query_pack_run(pack, args.reason)

    parts = [
        "query run prepared",
        f"source={args.source}",
        f"pack={pack.name}",
        f"type={pack.pack_type}",
        f"limit={args.limit}",
    ]
    if reason:
        parts.append(f"reason={reason}")
    print(" ".join(parts))
    print("queries:")
    for query in pack.queries:
        print(f"- {query}")
    return 0


def add_stub_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    help_text: str,
    commands: tuple[str, ...],
) -> None:
    group = subparsers.add_parser(name, help=help_text)
    nested = group.add_subparsers(
        dest=f"{name}_command", metavar="command", required=True
    )
    for command in commands:
        nested.add_parser(command, help=f"{command.replace('_', ' ')} {name} records")


def add_company_fields(
    parser: argparse.ArgumentParser,
    *,
    update: bool = False,
) -> None:
    parser.add_argument("--tier", type=int, choices=(1, 2, 3))
    parser.add_argument("--lanes")
    parser.add_argument("--why-interesting")
    parser.add_argument("--fit-thesis")
    parser.add_argument("--known-gaps")
    parser.add_argument("--products-used")
    parser.add_argument("--target-roles")
    parser.add_argument("--career-url")
    parser.add_argument("--ats-type")
    parser.add_argument(
        "--status",
        choices=COMPANY_STATUSES,
        default=None if update else "active",
    )
    parser.add_argument("--cooldown-until")
    parser.add_argument("--notes")


def add_job_fields(
    parser: argparse.ArgumentParser,
    *,
    update: bool = False,
) -> None:
    parser.add_argument("--url", dest="url")
    parser.add_argument("--source", default=None if update else "manual")
    parser.add_argument("--source-job-id")
    parser.add_argument("--location")
    parser.add_argument("--remote-status")
    parser.add_argument("--role-level")
    parser.add_argument("--lane")
    parser.add_argument(
        "--status",
        choices=(
            "discovered",
            "screening",
            "ignored_by_filter",
            "ready_to_apply",
            "applied",
            "interviewing",
            "rejected",
            "closed",
            "archived",
        ),
        default=None if update else "discovered",
    )
    parser.add_argument("--discovery-status")
    parser.add_argument("--fit-score", type=int, choices=range(0, 101), metavar="0-100")
    parser.add_argument("--relationship-path")
    parser.add_argument("--artifact-opportunity")
    parser.add_argument("--recommended-resume")
    parser.add_argument("--materials-status")
    parser.add_argument("--application-folder")
    parser.add_argument("--material-paths")
    parser.add_argument("--compensation-signal")
    parser.add_argument("--rejection-reason")
    parser.add_argument("--application-outcome")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage the company-first job search command center."
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help="SQLite database path.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Create or migrate the job search database.")
    subparsers.add_parser("status", help="Read a smoke summary from the database.")
    import_pipeline = subparsers.add_parser(
        "import-pipeline",
        help="Import legacy job_pipeline.jsonl records into SQLite.",
    )
    import_pipeline.add_argument(
        "--path",
        default=str(DEFAULT_PIPELINE_PATH),
        help="Legacy job_pipeline.jsonl path.",
    )

    company = subparsers.add_parser("company", help="Manage target companies.")
    company_subparsers = company.add_subparsers(
        dest="company_command", metavar="command", required=True
    )
    company_add = company_subparsers.add_parser("add", help="Add a target company.")
    company_add.add_argument("name")
    add_company_fields(company_add)
    company_update = company_subparsers.add_parser(
        "update", help="Update a target company."
    )
    company_update.add_argument("name")
    add_company_fields(company_update, update=True)
    company_show = company_subparsers.add_parser("show", help="Show company summary.")
    company_show.add_argument("name")
    company_list = company_subparsers.add_parser("list", help="List companies.")
    company_list.add_argument("--status", choices=COMPANY_STATUSES)
    company_list.add_argument("--tier", type=int, choices=(1, 2, 3))
    company_import = company_subparsers.add_parser(
        "import", help="Import researched companies and ATS source details."
    )
    company_import.add_argument(
        "--file",
        required=True,
        help="Researched-company JSON file.",
    )

    source = subparsers.add_parser("source", help="Manage target-company ATS sources.")
    source_subparsers = source.add_subparsers(
        dest="source_command", metavar="command", required=True
    )
    source_add = source_subparsers.add_parser("add", help="Add an ATS source.")
    source_add.add_argument("company")
    source_add.add_argument("--type", dest="source_type", choices=ATS_TYPES, required=True)
    source_add.add_argument("--key", dest="source_key", required=True)
    source_add.add_argument("--url")
    source_add.add_argument("--status", choices=SOURCE_STATUSES, default="active")
    source_add.add_argument("--notes")
    source_list = source_subparsers.add_parser("list", help="List ATS sources.")
    source_list.add_argument("--company")
    source_list.add_argument("--status", choices=SOURCE_STATUSES)

    poll = subparsers.add_parser("poll", help="Poll configured active ATS sources.")
    poll.add_argument("--company")
    poll.add_argument("--source-id", type=int)

    query = subparsers.add_parser(
        "query", help="Manage broad discovery query runs and packs."
    )
    query_subparsers = query.add_subparsers(
        dest="query_command", metavar="command", required=True
    )
    query_import = query_subparsers.add_parser(
        "import", help="Import a saved or manual discovery query run."
    )
    query_import.add_argument("--file", help="JSON file with query run metadata/results.")
    query_import.add_argument("--source")
    query_import.add_argument("--pack")
    query_import.add_argument("--query", dest="query_text")
    query_import.add_argument("--sort-mode")
    query_import.add_argument("--status", choices=QUERY_RUN_STATUSES)
    query_import.add_argument("--result-count", type=int)
    query_import.add_argument("--notes")
    query_import.add_argument("--raw-source-reference")
    query_import.add_argument(
        "--result-json",
        action="append",
        help="Result JSON object; may be repeated.",
    )
    query_list = query_subparsers.add_parser("list", help="List discovery query runs.")
    query_list.add_argument("--source")
    query_list.add_argument("--pack")
    query_list.add_argument("--status", choices=QUERY_RUN_STATUSES)
    query_list.add_argument("--limit", type=int, default=20)
    query_show = query_subparsers.add_parser("show", help="Show a discovery query run.")
    query_show.add_argument("query_run_id", type=int)
    query_packs = query_subparsers.add_parser(
        "packs", help="List and inspect query packs."
    )
    query_packs_subparsers = query_packs.add_subparsers(
        dest="query_packs_command", metavar="command", required=True
    )
    query_packs_list = query_packs_subparsers.add_parser(
        "list", help="List query packs."
    )
    query_packs_list.add_argument(
        "--default-only",
        action="store_true",
        help="Show only default repeatable discovery packs.",
    )
    query_packs_show = query_packs_subparsers.add_parser(
        "show", help="Show queries for a query pack."
    )
    query_packs_show.add_argument("pack")
    query_run = query_subparsers.add_parser(
        "run",
        help="Validate a broad query run before using a source adapter.",
    )
    query_run.add_argument("--source", choices=QUERY_SOURCES, required=True)
    query_run.add_argument("--pack", required=True)
    query_run.add_argument("--limit", type=positive_int, default=25)
    query_run.add_argument(
        "--reason",
        help="Required for exception packs such as ACCESS.",
    )
    job = subparsers.add_parser("job", help="Manage company roles.")
    job_subparsers = job.add_subparsers(dest="job_command", metavar="command", required=True)
    job_add = job_subparsers.add_parser("add", help="Add a job.")
    job_add.add_argument("company", nargs="?")
    job_add.add_argument("title", nargs="?")
    job_add.add_argument("--company", dest="company_option")
    job_add.add_argument("--title", dest="title_option")
    add_job_fields(job_add)
    job_update = job_subparsers.add_parser("update", help="Update a job.")
    job_update.add_argument("job_id", type=int)
    job_update.add_argument("--title")
    add_job_fields(job_update, update=True)
    job_show = job_subparsers.add_parser("show", help="Show a job.")
    job_show.add_argument("job_id", type=int)
    job_list = job_subparsers.add_parser("list", help="List jobs.")
    job_list.add_argument("--company")
    job_list.add_argument(
        "--status",
        choices=(
            "discovered",
            "screening",
            "ignored_by_filter",
            "ready_to_apply",
            "applied",
            "interviewing",
            "rejected",
            "closed",
            "archived",
        ),
    )
    job_status = job_subparsers.add_parser("status", help="Update job status.")
    job_status.add_argument("job_id", type=int)
    job_status.add_argument("status", choices=JOB_STATUSES)
    job_status.add_argument("--happened-at")
    job_status.add_argument("--notes")

    contact = subparsers.add_parser("contact", help="Manage relationship paths.")
    contact_subparsers = contact.add_subparsers(
        dest="contact_command", metavar="command", required=True
    )
    contact_add = contact_subparsers.add_parser("add", help="Add a contact.")
    contact_add.add_argument("--company", required=True)
    contact_add.add_argument("--name", required=True)
    contact_add.add_argument("--title")
    contact_add.add_argument("--source")
    contact_add.add_argument("--link")
    contact_add.add_argument("--relationship-strength")
    contact_add.add_argument("--last-contacted")
    contact_add.add_argument("--notes")
    contact_list = contact_subparsers.add_parser("list", help="List contacts.")
    contact_list.add_argument("--company")

    artifact = subparsers.add_parser("artifact", help="Manage targeted proof artifacts.")
    artifact_subparsers = artifact.add_subparsers(
        dest="artifact_command", metavar="command", required=True
    )
    artifact_add = artifact_subparsers.add_parser("add", help="Add an artifact.")
    artifact_add.add_argument("--company", required=True)
    artifact_add.add_argument("--job-id", type=int)
    artifact_add.add_argument("--type", required=True)
    artifact_add.add_argument("--status", choices=ARTIFACT_STATUSES, default="idea")
    artifact_add.add_argument("--thesis")
    artifact_add.add_argument("--link")
    artifact_add.add_argument("--path")
    artifact_add.add_argument("--notes")
    artifact_add.add_argument("--happened-at")
    artifact_list = artifact_subparsers.add_parser("list", help="List artifacts.")
    artifact_list.add_argument("--company")
    artifact_status = artifact_subparsers.add_parser(
        "status", help="Update artifact status."
    )
    artifact_status.add_argument("artifact_id", type=int)
    artifact_status.add_argument("status", choices=ARTIFACT_STATUSES)
    artifact_status.add_argument("--link")
    artifact_status.add_argument("--path")
    artifact_status.add_argument("--happened-at")
    artifact_status.add_argument("--notes")

    gap = subparsers.add_parser("gap", help="Manage search gaps.")
    gap_subparsers = gap.add_subparsers(dest="gap_command", metavar="command", required=True)
    gap_add = gap_subparsers.add_parser("add", help="Add a structured gap.")
    gap_add.add_argument("--company")
    gap_add.add_argument("--job-id", type=int)
    gap_add.add_argument("--type", dest="gap_type", required=True)
    gap_add.add_argument("--description", required=True)
    gap_add.add_argument("--severity", choices=GAP_SEVERITIES, default="medium")
    gap_add.add_argument("--status", choices=GAP_STATUSES, default="open")
    gap_add.add_argument("--resolution-action")
    gap_add.add_argument("--notes")
    gap_add.add_argument("--happened-at")
    gap_list = gap_subparsers.add_parser("list", help="List gaps.")
    gap_list.add_argument("--company")
    gap_list.add_argument("--status", choices=GAP_STATUSES)
    gap_status = gap_subparsers.add_parser("status", help="Update gap status.")
    gap_status.add_argument("gap_id", type=int)
    gap_status.add_argument("status", choices=GAP_STATUSES)
    gap_status.add_argument("--resolution-action")
    gap_status.add_argument("--happened-at")
    gap_status.add_argument("--notes")

    action = subparsers.add_parser("action", help="Manage action queues.")
    action_subparsers = action.add_subparsers(
        dest="action_command", metavar="command", required=True
    )
    action_add = action_subparsers.add_parser("add", help="Add a manual action.")
    action_add.add_argument("--company", required=True)
    action_add.add_argument(
        "--queue",
        choices=ACTION_QUEUES,
        required=True,
    )
    action_add.add_argument("--kind", required=True)
    action_add.add_argument("--job-id", type=int)
    action_add.add_argument("--contact-id", type=int)
    action_add.add_argument("--artifact-id", type=int)
    action_add.add_argument("--gap-id", type=int)
    action_add.add_argument("--due-at")
    action_add.add_argument("--notes")
    action_next = action_subparsers.add_parser("next", help="Show next queued actions.")
    action_next.add_argument(
        "--queue",
        choices=ACTION_QUEUES,
    )
    action_next.add_argument("--limit", type=positive_int, default=10)
    action_list = action_subparsers.add_parser("list", help="List actions.")
    action_list.add_argument(
        "--queue",
        choices=ACTION_QUEUES,
    )
    action_list.add_argument(
        "--status",
        choices=("queued", "in_progress", "done", "blocked", "skipped", "rescheduled"),
    )
    action_list.add_argument("--limit", type=positive_int, default=50)
    action_done = action_subparsers.add_parser("done", help="Mark an action done.")
    action_done.add_argument("action_id", type=int)
    action_done.add_argument("--notes")
    action_done.add_argument(
        "--message-sent",
        action="store_true",
        help="Also generate a follow-up for a sent message.",
    )
    for command in ("block", "skip"):
        transition = action_subparsers.add_parser(
            command, help=f"Mark an action {command}ed."
        )
        transition.add_argument("action_id", type=int)
        transition.add_argument("--notes")
    action_reschedule = action_subparsers.add_parser(
        "reschedule", help="Reschedule an action."
    )
    action_reschedule.add_argument("action_id", type=int)
    action_reschedule.add_argument("due_at")
    action_reschedule.add_argument("--notes")

    event = subparsers.add_parser("event", help="Manage append-only history.")
    event_subparsers = event.add_subparsers(
        dest="event_command", metavar="command", required=True
    )
    event_add = event_subparsers.add_parser("add", help="Add a history event.")
    event_add.add_argument("--company", required=True)
    event_add.add_argument("--type", dest="event_type", choices=EVENT_TYPES, required=True)
    event_add.add_argument("--happened-at")
    event_add.add_argument("--notes")
    event_add.add_argument("--job-id", type=int)
    event_add.add_argument("--contact-id", type=int)
    event_add.add_argument("--artifact-id", type=int)
    event_add.add_argument("--gap-id", type=int)
    event_add.add_argument("--action-id", type=int)
    event_list = event_subparsers.add_parser("list", help="List company history events.")
    event_list.add_argument("--company")
    event_list.add_argument("--limit", type=int, default=50)
    metrics = subparsers.add_parser("metrics", help="Show job search metrics.")
    metrics.add_argument("--since")
    metrics.add_argument("--until")
    metrics.add_argument("--days", type=int, default=7)
    report = subparsers.add_parser("report", help="Show read-only hygiene reports.")
    report_subparsers = report.add_subparsers(
        dest="report_command", metavar="command", required=True
    )
    hygiene = report_subparsers.add_parser(
        "hygiene",
        help="Show stale actions, outcome gaps, and companies needing next actions.",
    )
    hygiene.add_argument("--as-of")
    hygiene.add_argument("--limit", type=int, default=20)
    hygiene.add_argument(
        "--company-activity-days",
        type=int,
        default=HYGIENE_COMPANY_ACTIVITY_DAYS,
    )
    hygiene.add_argument(
        "--pending-outcome-days",
        type=int,
        default=HYGIENE_PENDING_OUTCOME_DAYS,
    )
    hygiene.add_argument(
        "--unscheduled-action-days",
        type=int,
        default=HYGIENE_UNSCHEDULED_ACTION_DAYS,
    )

    return parser.parse_args()


def command_init(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    version = init_database(db_path)
    print(f"initialized {db_path} schema_version={version}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    status = read_status(db_path)
    print(
        " | ".join(
            [
                f"schema_version={status['schema_version']}",
                f"companies={status['companies']}",
                f"jobs={status['jobs']}",
                f"actions={status['actions']}",
                f"path={status['path']}",
            ]
        )
    )
    daily_status = read_daily_status(db_path)
    queue_counts = daily_status["queue_counts"]
    active_queues = [
        f"{queue}={count}" for queue, count in queue_counts.items() if count
    ]
    if active_queues:
        print(
            "Open action queues: "
            + ", ".join(active_queues)
            + " | "
            + " | ".join(
                [
                    f"stale={daily_status['stale_action_count']}",
                    f"due_today={daily_status['due_today_action_count']}",
                    f"unscheduled={daily_status['unscheduled_action_count']}",
                ]
            )
        )
    else:
        print("Open action queues: none")

    job_status_counts = daily_status["job_status_counts"]
    if job_status_counts:
        ordered_jobs = [
            f"{status}={job_status_counts[status]}"
            for status in JOB_STATUSES
            if status in job_status_counts
        ]
        print("Active jobs: " + ", ".join(ordered_jobs))
    else:
        print("Active jobs: none")

    recent_outcomes = daily_status["recent_outcome_counts"]
    if recent_outcomes:
        print(
            "Recent outcomes (7d): "
            + ", ".join(
                f"{event_type}={recent_outcomes[event_type]}"
                for event_type in sorted(recent_outcomes)
            )
        )
    else:
        print("Recent outcomes (7d): none")

    coverage = daily_status["target_coverage"]
    if coverage["active_companies"]:
        print(
            "Target coverage: "
            + " | ".join(
                [
                    f"active_companies={coverage['active_companies']}",
                    f"with_active_sources={coverage['with_active_sources']}",
                    f"needs_source={coverage['needs_source']}",
                    f"stale_checks={coverage['stale_checks']}",
                ]
            )
        )
    else:
        print("Target coverage: no active target companies")
    return 0


def command_import_pipeline(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    pipeline_path = Path(args.path)
    if not pipeline_path.exists():
        raise FileNotFoundError(f"Legacy pipeline file not found: {pipeline_path}")

    require_database(db_path)
    now = utc_now()
    imported = 0
    skipped_duplicates = 0
    companies_created = 0
    line_number = 0
    with closing(connect(db_path)) as connection:
        with connection:
            for line_number, line in enumerate(
                pipeline_path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Invalid JSON on line {line_number}: {error.msg}"
                    ) from error
                if not isinstance(record, dict):
                    raise ValueError(
                        f"Invalid record on line {line_number}: expected object"
                    )
                status, _, company_created = import_legacy_record(
                    connection,
                    record=record,
                    now=now,
                )
                if company_created:
                    companies_created += 1
                if status == "imported":
                    imported += 1
                elif status == "skipped_duplicate":
                    skipped_duplicates += 1

    print(
        "legacy pipeline import "
        f"path={pipeline_path} lines={line_number} companies_created={companies_created} "
        f"jobs_imported={imported} duplicates_skipped={skipped_duplicates}"
    )
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "init":
            return command_init(args)
        if args.command == "status":
            return command_status(args)
        if args.command == "import-pipeline":
            return command_import_pipeline(args)
        if args.command == "company":
            if args.company_command == "add":
                return command_company_add(args)
            if args.company_command == "update":
                return command_company_update(args)
            if args.company_command == "show":
                return command_company_show(args)
            if args.company_command == "list":
                return command_company_list(args)
            if args.company_command == "import":
                return command_company_import(args)
        if args.command == "source":
            if args.source_command == "add":
                return command_source_add(args)
            if args.source_command == "list":
                return command_source_list(args)
        if args.command == "poll":
            return command_poll(args)
        if args.command == "query":
            if args.query_command == "import":
                return command_query_import(args)
            if args.query_command == "list":
                return command_query_list(args)
            if args.query_command == "show":
                return command_query_show(args)
            if args.query_command == "packs":
                if args.query_packs_command == "list":
                    return command_query_packs_list(args)
                if args.query_packs_command == "show":
                    return command_query_packs_show(args)
            if args.query_command == "run":
                return command_query_run(args)
        if args.command == "job":
            if args.job_command == "add":
                return command_job_add(args)
            if args.job_command == "update":
                return command_job_update(args)
            if args.job_command == "show":
                return command_job_show(args)
            if args.job_command == "list":
                return command_job_list(args)
            if args.job_command == "status":
                return command_job_status(args)
        if args.command == "contact":
            if args.contact_command == "add":
                return command_contact_add(args)
            if args.contact_command == "list":
                return command_contact_list(args)
        if args.command == "artifact":
            if args.artifact_command == "add":
                return command_artifact_add(args)
            if args.artifact_command == "list":
                return command_artifact_list(args)
            if args.artifact_command == "status":
                return command_artifact_status(args)
        if args.command == "gap":
            if args.gap_command == "add":
                return command_gap_add(args)
            if args.gap_command == "list":
                return command_gap_list(args)
            if args.gap_command == "status":
                return command_gap_status(args)
        if args.command == "event":
            if args.event_command == "add":
                return command_event_add(args)
            if args.event_command == "list":
                return command_event_list(args)
        if args.command == "report":
            if args.report_command == "hygiene":
                return command_report_hygiene(args)
        if args.command == "action":
            if args.action_command == "add":
                return command_action_add(args)
            if args.action_command == "next":
                return command_action_next(args)
            if args.action_command == "list":
                return command_action_list(args)
            if args.action_command == "done":
                return command_action_transition(args, "done")
            if args.action_command == "block":
                return command_action_transition(args, "blocked")
            if args.action_command == "skip":
                return command_action_transition(args, "skipped")
            if args.action_command == "reschedule":
                return command_action_reschedule(args)
        if args.command == "metrics":
            return command_metrics(args)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 1
    except sqlite3.DatabaseError as error:
        print(f"Database error: {error}", file=sys.stderr)
        return 1

    raise SystemExit(
        f"`{args.command}` is scaffolded for help output; implementation comes in later slices."
    )


if __name__ == "__main__":
    raise SystemExit(main())

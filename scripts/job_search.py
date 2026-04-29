#!/usr/bin/env python3
"""Company-first job search command center CLI."""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "APPLICATIONS" / "_ops" / "job_search.sqlite"
SCHEMA_VERSION = 2
OPEN_ACTION_STATUSES = ("queued", "in_progress", "blocked", "rescheduled")
TERMINAL_ACTION_STATUSES = ("done", "skipped")
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


def is_materially_different_role(candidate: sqlite3.Row, prior: sqlite3.Row) -> bool:
    if candidate["lane"] and prior["lane"] and candidate["lane"] != prior["lane"]:
        return True

    candidate_tokens = title_keywords(candidate["title"])
    prior_tokens = title_keywords(prior["title"])
    if candidate_tokens and prior_tokens and candidate_tokens.isdisjoint(prior_tokens):
        return True

    return False


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


def require_database(db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not initialized: {db_path}")
    init_database(db_path)


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
    return (
        f"#{row['id']} | {row['queue']}:{row['kind']} | {row['status']} | "
        f"due={due} | {subject}"
    )


def action_rows_query(where_sql: str = "") -> str:
    return f"""
        SELECT
            actions.*,
            companies.name AS company_name,
            jobs.title AS job_title
        FROM actions
        JOIN companies ON companies.id = actions.company_id
        LEFT JOIN jobs ON jobs.id = actions.job_id
        {where_sql}
        ORDER BY
            CASE WHEN actions.due_at IS NULL THEN 1 ELSE 0 END,
            actions.due_at,
            actions.id
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
        print(format_action(row))
    if not rows:
        print("no actions")
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
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with closing(connect(db_path)) as connection:
        rows = connection.execute(action_rows_query(where), params).fetchall()
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
    action_next = action_subparsers.add_parser("next", help="Show next queued actions.")
    action_next.add_argument(
        "--queue",
        choices=("screen", "apply", "follow_up", "research", "artifact", "classify"),
    )
    action_next.add_argument("--limit", type=int, default=10)
    action_list = action_subparsers.add_parser("list", help="List actions.")
    action_list.add_argument(
        "--queue",
        choices=("screen", "apply", "follow_up", "research", "artifact", "classify"),
    )
    action_list.add_argument(
        "--status",
        choices=("queued", "in_progress", "done", "blocked", "skipped", "rescheduled"),
    )
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

    return parser.parse_args()


def command_init(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    version = init_database(db_path)
    print(f"initialized {db_path} schema_version={version}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    status = read_status(Path(args.db_path))
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
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "init":
            return command_init(args)
        if args.command == "status":
            return command_status(args)
        if args.command == "company":
            if args.company_command == "add":
                return command_company_add(args)
            if args.company_command == "update":
                return command_company_update(args)
            if args.company_command == "show":
                return command_company_show(args)
            if args.company_command == "list":
                return command_company_list(args)
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
        if args.command == "action":
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

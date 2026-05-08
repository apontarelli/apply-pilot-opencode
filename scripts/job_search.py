#!/usr/bin/env python3
"""Company-first job search command center CLI."""

from __future__ import annotations

import argparse
import hashlib
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
SCHEMA_VERSION = 6
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
AUTOMATION_RUN_STATUSES = ("planned", "running", "completed", "failed", "partial", "skipped")
AUTOMATION_RECOVERY_STATUSES = (
    "none",
    "unresolved",
    "retry_ready",
    "skipped",
    "manual_resolved",
)
DRAFT_TYPES = ("follow_up", "application_answer")
DRAFT_STATUSES = ("draft", "needs_revision", "rejected", "approved")
REJECTION_REASONS = (
    "fit_mismatch",
    "level_scope_mismatch",
    "recruiter_screen_risk",
    "missing_proof",
    "compensation_mismatch",
    "location_or_work_model_mismatch",
    "timing_or_capacity",
    "stale_or_closed_posting",
    "duplicate_or_already_tracked",
    "low_interest",
)
APPLICATION_OUTCOMES = (
    "pending_response",
    "active_interview_loop",
    "rejected_before_screen",
    "rejected_after_screen",
    "rejected_after_interview",
    "closed_before_apply",
    "passed_by_candidate",
    "archived_no_action",
)
LEGACY_APPLICATION_OUTCOME_MAP = {
    "applied": "pending_response",
    "no_response": "pending_response",
    "recruiter_screen": "active_interview_loop",
    "interview_loop": "active_interview_loop",
    "offer_received": "active_interview_loop",
    "offer_accepted": "active_interview_loop",
    "withdrawn": "passed_by_candidate",
    "offer_declined": "passed_by_candidate",
    "rejected_no_interview": "rejected_before_screen",
    "rejected_after_loop": "rejected_after_interview",
    "posting_closed": "closed_before_apply",
}
SCREEN_BUCKETS = (
    "ready_to_apply",
    "low_effort_apply",
    "stretch_warm_path",
    "portfolio_gap",
    "watch",
    "pass",
)
HIGH_SIGNAL_JOB_STATUSES = ("ready_to_apply", "applied", "interviewing")
NOISY_QUERY_RESULT_MARKERS = (
    "search_noisy",
    "malformed_payload",
    "stale_or_thin_result",
    "detail_validation_failed",
)
QUERY_TUNING_NOISY_MARKERS = ("search_noisy", "malformed_payload")
QUERY_TUNING_STALE_THIN_MARKERS = (
    "stale_or_thin_result",
    "detail_validation_failed",
)
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
    "draft_created",
    "draft_revised",
    "draft_rejected",
    "gap_identified",
    "status_changed",
    "note",
)
NO_INTERVIEW_COOLDOWN_DAYS = 45
INTERVIEW_LOOP_COOLDOWN_DAYS = 120
TIMING_CAPACITY_COOLDOWN_DAYS = 30
DURABLE_LOW_PRIORITY_REVIEW_DAYS = 180
COOLDOWN_RECOMMENDATION_LIMIT = 20
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
PROOF_GAP_STOPWORDS = {
    "about",
    "after",
    "against",
    "application",
    "artifact",
    "before",
    "better",
    "build",
    "case",
    "center",
    "company",
    "current",
    "demonstrate",
    "evidence",
    "example",
    "experience",
    "for",
    "from",
    "gap",
    "gaps",
    "has",
    "impact",
    "lack",
    "lacks",
    "missing",
    "need",
    "needed",
    "needs",
    "point",
    "portfolio",
    "proof",
    "reason",
    "resolution",
    "role",
    "show",
    "shows",
    "specific",
    "story",
    "study",
    "that",
    "the",
    "this",
    "with",
    "without",
}
PROOF_GAP_SEVERITY_SCORE = {"high": 3, "medium": 2, "low": 1}
PROOF_GAP_SOURCE_SCORE = {"gap": 4, "job": 3, "action": 2, "event": 2}


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
class SourcePollResult:
    source_id: int
    company_name: str
    source_type: str
    discovered_count: int = 0
    inserted_count: int = 0
    ignored_count: int = 0
    duplicate_count: int = 0
    screen_action_ids: tuple[int, ...] = ()
    failure: str | None = None


@dataclass(frozen=True)
class PollRunResult:
    source_count: int
    source_results: tuple[SourcePollResult, ...]

    @property
    def result_count(self) -> int:
        return sum(result.discovered_count for result in self.source_results)

    @property
    def inserted_count(self) -> int:
        return sum(result.inserted_count for result in self.source_results)

    @property
    def ignored_count(self) -> int:
        return sum(result.ignored_count for result in self.source_results)

    @property
    def duplicate_count(self) -> int:
        return sum(result.duplicate_count for result in self.source_results)

    @property
    def failure_count(self) -> int:
        return sum(1 for result in self.source_results if result.failure)

    @property
    def screen_action_ids(self) -> tuple[int, ...]:
        return tuple(
            action_id
            for result in self.source_results
            for action_id in result.screen_action_ids
        )


@dataclass(frozen=True)
class LlmAtsTriageInput:
    company_name: str
    company_tier: int | None
    title: str
    canonical_url: str | None
    source: str
    source_job_id: str | None
    deterministic_status: str
    deterministic_reason: str | None
    location: str | None = None
    remote_status: str | None = None
    compensation_signal: str | None = None
    job_id: int | None = None
    query_run_result_id: int | None = None
    poll_source_id: int | None = None
    poll_batch_key: str | None = None
    duplicate_job_id: int | None = None


@dataclass(frozen=True)
class LlmAtsTriageOutput:
    recommendation: str | None
    confidence: float | None
    uncertainty: str | None
    rationale: str | None
    suggested_rule_improvements: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class QueryImportOutcome:
    query_run_id: int
    import_state: str
    source: str
    pack: str | None
    status: str
    result_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    raw_source_reference: str | None


@dataclass(frozen=True)
class CooldownEvidence:
    signal: str
    job_id: int
    company_id: int
    company_name: str
    job_title: str
    job_status: str
    role_pattern: str
    application_outcome: str | None
    rejection_reason: str | None
    signal_at: str
    latest_event_id: int | None
    latest_event_type: str | None
    latest_event_at: str | None
    latest_action_id: int | None
    latest_action_queue: str | None
    latest_action_status: str | None


@dataclass(frozen=True)
class CooldownRecommendation:
    target_type: str
    target_key: str
    target_label: str
    recommendation_type: str
    signal: str
    reason: str
    next_review_at: str
    evidence: tuple[CooldownEvidence, ...]


@dataclass(frozen=True)
class ProofGapEvidence:
    source: str
    source_id: int
    company_id: int | None
    company_name: str | None
    job_id: int | None
    job_title: str | None
    lane: str | None
    job_status: str | None
    application_outcome: str | None
    rejection_reason: str | None
    gap_type: str | None
    severity: str | None
    gap_status: str | None
    action_queue: str | None
    action_kind: str | None
    action_status: str | None
    event_type: str | None
    happened_at: str | None
    text: str


@dataclass
class ProofGapGroup:
    key: str
    label: str
    evidence: list[ProofGapEvidence]

    @property
    def company_ids(self) -> set[int]:
        return {
            item.company_id for item in self.evidence if item.company_id is not None
        }

    @property
    def job_ids(self) -> set[int]:
        return {item.job_id for item in self.evidence if item.job_id is not None}

    @property
    def lanes(self) -> set[str]:
        return {item.lane for item in self.evidence if item.lane}

    @property
    def job_statuses(self) -> set[str]:
        return {item.job_status for item in self.evidence if item.job_status}

    @property
    def outcomes(self) -> set[str]:
        return {
            item.application_outcome
            for item in self.evidence
            if item.application_outcome
        }

    @property
    def rejection_reasons(self) -> set[str]:
        return {
            item.rejection_reason for item in self.evidence if item.rejection_reason
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

CREATE TABLE IF NOT EXISTS automation_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    scope TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('planned', 'running', 'completed', 'failed', 'partial', 'skipped')),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    result_count INTEGER NOT NULL DEFAULT 0 CHECK (result_count >= 0),
    failure_count INTEGER NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    created_action_count INTEGER NOT NULL DEFAULT 0 CHECK (created_action_count >= 0),
    created_artifact_count INTEGER NOT NULL DEFAULT 0 CHECK (created_artifact_count >= 0),
    created_draft_count INTEGER NOT NULL DEFAULT 0 CHECK (created_draft_count >= 0),
    created_query_run_count INTEGER NOT NULL DEFAULT 0 CHECK (created_query_run_count >= 0),
    failure_summary TEXT,
    action_ids TEXT,
    artifact_ids TEXT,
    draft_ids TEXT,
    query_run_ids TEXT,
    notes TEXT,
    recovery_status TEXT NOT NULL DEFAULT 'none'
        CHECK (recovery_status IN ('none', 'unresolved', 'retry_ready', 'skipped', 'manual_resolved')),
    recovery_notes TEXT,
    raw_source_reference TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_automation_runs_review
    ON automation_runs(status, recovery_status, started_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS llm_ats_triage_audits (
    id INTEGER PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    query_run_result_id INTEGER REFERENCES query_run_results(id) ON DELETE SET NULL,
    poll_source_id INTEGER REFERENCES company_sources(id) ON DELETE SET NULL,
    company_name TEXT NOT NULL,
    company_tier INTEGER CHECK (company_tier BETWEEN 1 AND 3),
    title TEXT NOT NULL,
    canonical_url TEXT,
    source TEXT NOT NULL,
    source_job_id TEXT,
    deterministic_status TEXT NOT NULL,
    deterministic_reason TEXT,
    eligibility_reason TEXT NOT NULL,
    input_payload TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    model TEXT NOT NULL,
    model_version TEXT NOT NULL,
    output_status TEXT NOT NULL
        CHECK (output_status IN ('valid', 'malformed', 'uncertain')),
    llm_recommendation TEXT
        CHECK (llm_recommendation IN ('screening', 'pass', 'uncertain')),
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    uncertainty TEXT,
    structured_output TEXT NOT NULL,
    raw_output TEXT NOT NULL,
    malformed_reason TEXT,
    reconciliation TEXT NOT NULL
        CHECK (
            reconciliation IN (
                'llm_rescues_ignored',
                'llm_passes_screening',
                'llm_agrees',
                'llm_uncertain',
                'llm_malformed',
                'duplicate_already_tracked'
            )
        ),
    duplicate_job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    proposal_target TEXT,
    proposal_reason TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_ats_triage_audits_created
    ON llm_ats_triage_audits(created_at DESC, id DESC);

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
    screen_bucket TEXT
        CHECK (
            screen_bucket IN (
                'ready_to_apply',
                'low_effort_apply',
                'stretch_warm_path',
                'portfolio_gap',
                'watch',
                'pass'
            )
        ),
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

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    artifact_id INTEGER REFERENCES artifacts(id) ON DELETE SET NULL,
    action_id INTEGER REFERENCES actions(id) ON DELETE SET NULL,
    draft_type TEXT NOT NULL CHECK (draft_type IN ('follow_up', 'application_answer')),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'needs_revision', 'rejected', 'approved')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    path TEXT,
    source_summary TEXT,
    approval_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_drafts_review
    ON drafts(status, draft_type, updated_at DESC, id DESC);

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

CREATE TRIGGER IF NOT EXISTS trg_drafts_company_immutable
BEFORE UPDATE OF company_id ON drafts
WHEN NEW.company_id <> OLD.company_id
BEGIN
    SELECT RAISE(ABORT, 'draft company_id is immutable');
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

AUTOMATION_RUN_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    scope TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('planned', 'running', 'completed', 'failed', 'partial', 'skipped')),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    result_count INTEGER NOT NULL DEFAULT 0 CHECK (result_count >= 0),
    failure_count INTEGER NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    created_action_count INTEGER NOT NULL DEFAULT 0 CHECK (created_action_count >= 0),
    created_artifact_count INTEGER NOT NULL DEFAULT 0 CHECK (created_artifact_count >= 0),
    created_draft_count INTEGER NOT NULL DEFAULT 0 CHECK (created_draft_count >= 0),
    created_query_run_count INTEGER NOT NULL DEFAULT 0 CHECK (created_query_run_count >= 0),
    failure_summary TEXT,
    action_ids TEXT,
    artifact_ids TEXT,
    draft_ids TEXT,
    query_run_ids TEXT,
    notes TEXT,
    recovery_status TEXT NOT NULL DEFAULT 'none'
        CHECK (recovery_status IN ('none', 'unresolved', 'retry_ready', 'skipped', 'manual_resolved')),
    recovery_notes TEXT,
    raw_source_reference TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_automation_runs_review
    ON automation_runs(status, recovery_status, started_at DESC, id DESC);
"""

DRAFT_SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    artifact_id INTEGER REFERENCES artifacts(id) ON DELETE SET NULL,
    action_id INTEGER REFERENCES actions(id) ON DELETE SET NULL,
    draft_type TEXT NOT NULL CHECK (draft_type IN ('follow_up', 'application_answer')),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'needs_revision', 'rejected', 'approved')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    path TEXT,
    source_summary TEXT,
    approval_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_drafts_review
    ON drafts(status, draft_type, updated_at DESC, id DESC);

CREATE TRIGGER IF NOT EXISTS trg_drafts_company_immutable
BEFORE UPDATE OF company_id ON drafts
WHEN NEW.company_id <> OLD.company_id
BEGIN
    SELECT RAISE(ABORT, 'draft company_id is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_drafts_same_company_insert
BEFORE INSERT ON drafts
WHEN
    (NEW.job_id IS NOT NULL AND EXISTS (
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
    OR (NEW.action_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM actions
        WHERE actions.id = NEW.action_id
            AND actions.company_id <> NEW.company_id
    ))
BEGIN
    SELECT RAISE(ABORT, 'draft reference belongs to a different company');
END;

CREATE TRIGGER IF NOT EXISTS trg_drafts_same_company_update
BEFORE UPDATE OF company_id, job_id, contact_id, artifact_id, action_id ON drafts
WHEN
    (NEW.job_id IS NOT NULL AND EXISTS (
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
    OR (NEW.action_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM actions
        WHERE actions.id = NEW.action_id
            AND actions.company_id <> NEW.company_id
    ))
BEGIN
    SELECT RAISE(ABORT, 'draft reference belongs to a different company');
END;
"""

SCREEN_BUCKET_SCHEMA = """
CREATE TRIGGER IF NOT EXISTS trg_jobs_screen_bucket_insert
BEFORE INSERT ON jobs
WHEN NEW.screen_bucket IS NOT NULL
    AND NEW.screen_bucket NOT IN (
        'ready_to_apply',
        'low_effort_apply',
        'stretch_warm_path',
        'portfolio_gap',
        'watch',
        'pass'
    )
BEGIN
    SELECT RAISE(ABORT, 'invalid jobs.screen_bucket');
END;

CREATE TRIGGER IF NOT EXISTS trg_jobs_screen_bucket_update
BEFORE UPDATE OF screen_bucket ON jobs
WHEN NEW.screen_bucket IS NOT NULL
    AND NEW.screen_bucket NOT IN (
        'ready_to_apply',
        'low_effort_apply',
        'stretch_warm_path',
        'portfolio_gap',
        'watch',
        'pass'
    )
BEGIN
    SELECT RAISE(ABORT, 'invalid jobs.screen_bucket');
END;
"""

LLM_ATS_TRIAGE_AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_ats_triage_audits (
    id INTEGER PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    query_run_result_id INTEGER REFERENCES query_run_results(id) ON DELETE SET NULL,
    poll_source_id INTEGER REFERENCES company_sources(id) ON DELETE SET NULL,
    company_name TEXT NOT NULL,
    company_tier INTEGER CHECK (company_tier BETWEEN 1 AND 3),
    title TEXT NOT NULL,
    canonical_url TEXT,
    source TEXT NOT NULL,
    source_job_id TEXT,
    deterministic_status TEXT NOT NULL,
    deterministic_reason TEXT,
    eligibility_reason TEXT NOT NULL,
    input_payload TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    model TEXT NOT NULL,
    model_version TEXT NOT NULL,
    output_status TEXT NOT NULL
        CHECK (output_status IN ('valid', 'malformed', 'uncertain')),
    llm_recommendation TEXT
        CHECK (llm_recommendation IN ('screening', 'pass', 'uncertain')),
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    uncertainty TEXT,
    structured_output TEXT NOT NULL,
    raw_output TEXT NOT NULL,
    malformed_reason TEXT,
    reconciliation TEXT NOT NULL
        CHECK (
            reconciliation IN (
                'llm_rescues_ignored',
                'llm_passes_screening',
                'llm_agrees',
                'llm_uncertain',
                'llm_malformed',
                'duplicate_already_tracked'
            )
        ),
    duplicate_job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    proposal_target TEXT,
    proposal_reason TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_ats_triage_audits_created
    ON llm_ats_triage_audits(created_at DESC, id DESC);
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


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
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
    if default_names != {"AI", "FINTECH", "GROWTH_BUSINESS_SYSTEMS"}:
        raise ValueError(
            "Default repeatable query packs must be exactly AI, FINTECH, "
            "and GROWTH_BUSINESS_SYSTEMS"
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
            f"non-default packs require --reason."
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
        payload.update(read_query_import_file(args.file))

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


def read_query_import_file(path_text: str) -> dict[str, object]:
    path = Path(path_text)
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid query import file {path}: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"Invalid query import file {path}: expected JSON object")
    return parsed


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
        normalized_result = {
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
        }
        normalized_result["raw_payload"] = json.dumps(
            {
                key: value
                for key, value in normalized_result.items()
                if value is not None
            },
            sort_keys=True,
        )
        normalized.append(normalized_result)
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


def llm_ats_triage_input_payload(triage_input: LlmAtsTriageInput) -> dict[str, object]:
    return {
        "company_name": triage_input.company_name,
        "company_tier": triage_input.company_tier,
        "title": triage_input.title,
        "canonical_url": normalize_url(triage_input.canonical_url),
        "source": triage_input.source,
        "source_job_id": triage_input.source_job_id,
        "location": triage_input.location,
        "remote_status": triage_input.remote_status,
        "compensation_signal": triage_input.compensation_signal,
        "deterministic_status": triage_input.deterministic_status,
        "deterministic_reason": triage_input.deterministic_reason,
        "job_id": triage_input.job_id,
        "query_run_result_id": triage_input.query_run_result_id,
        "poll_source_id": triage_input.poll_source_id,
        "poll_batch_key": triage_input.poll_batch_key,
        "duplicate_job_id": triage_input.duplicate_job_id,
    }


def llm_ats_triage_input_hash(triage_input: LlmAtsTriageInput) -> str:
    payload = llm_ats_triage_input_payload(triage_input)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def llm_ats_triage_eligibility_reason(triage_input: LlmAtsTriageInput) -> str:
    product_adjacent = bool(
        re.search(
            r"\b(product|platform|ledger|payments?|workflow)\b",
            triage_input.title,
            re.I,
        )
    )
    reasons: list[str] = []
    if triage_input.company_tier == 1:
        reasons.append("tier_1_company")
    if product_adjacent:
        reasons.append("product_adjacent_title")
    if triage_input.deterministic_status in ("ignored_by_filter", "screening"):
        reasons.append(f"deterministic_{triage_input.deterministic_status}")
    if triage_input.poll_batch_key or triage_input.poll_source_id is not None:
        reasons.append("newly_polled_batch")
    if triage_input.duplicate_job_id is not None:
        reasons.append("duplicate_already_tracked")
    return ",".join(reasons) if reasons else "not_eligible"


def reconcile_llm_ats_triage(
    *,
    triage_input: LlmAtsTriageInput,
    output_status: str,
    llm_recommendation: str | None,
) -> tuple[str, str | None, str | None]:
    if triage_input.duplicate_job_id is not None:
        return (
            "duplicate_already_tracked",
            "filter_rule",
            "Duplicate recommendations are evidence for dedupe/filter tuning only.",
        )
    if output_status == "malformed":
        return ("llm_malformed", None, None)
    if output_status == "uncertain" or llm_recommendation == "uncertain":
        return ("llm_uncertain", None, None)
    if (
        triage_input.deterministic_status == "ignored_by_filter"
        and llm_recommendation == "screening"
    ):
        return (
            "llm_rescues_ignored",
            "target_role",
            "Review target roles or query packs; deterministic filters require human approval.",
        )
    if (
        triage_input.deterministic_status == "screening"
        and llm_recommendation == "pass"
    ):
        return (
            "llm_passes_screening",
            "filter_rule",
            "Review filter-rule precision; deterministic filters require human approval.",
        )
    return ("llm_agrees", None, None)


def record_llm_ats_triage_audit(
    connection: sqlite3.Connection,
    *,
    triage_input: LlmAtsTriageInput,
    triage_output: LlmAtsTriageOutput | None,
    raw_output: str,
    prompt_version: str,
    schema_version: str,
    model: str,
    model_version: str,
    malformed_reason: str | None,
    now: str,
) -> int:
    valid_recommendations = {"screening", "pass", "uncertain"}
    output_malformed_reason = malformed_reason
    llm_recommendation = triage_output.recommendation if triage_output else None
    confidence = triage_output.confidence if triage_output else None
    if triage_output is not None and llm_recommendation not in valid_recommendations:
        output_malformed_reason = (
            f"invalid_recommendation:{llm_recommendation}"
            if llm_recommendation
            else "missing_recommendation"
        )
        llm_recommendation = None
    if triage_output is not None and confidence is not None and not 0 <= confidence <= 1:
        output_malformed_reason = (
            f"{output_malformed_reason};invalid_confidence:{confidence}"
            if output_malformed_reason
            else f"invalid_confidence:{confidence}"
        )
        confidence = None
    output_status = (
        "malformed"
        if triage_output is None or output_malformed_reason is not None
        else "uncertain"
        if triage_output.recommendation == "uncertain" or triage_output.uncertainty
        else "valid"
    )
    structured_output = (
        {}
        if triage_output is None
        else {
            "recommendation": triage_output.recommendation,
            "confidence": triage_output.confidence,
            "uncertainty": triage_output.uncertainty,
            "rationale": triage_output.rationale,
            "suggested_rule_improvements": list(
                triage_output.suggested_rule_improvements
            ),
        }
    )
    reconciliation, proposal_target, proposal_reason = reconcile_llm_ats_triage(
        triage_input=triage_input,
        output_status=output_status,
        llm_recommendation=llm_recommendation,
    )
    cursor = connection.execute(
        """
        INSERT INTO llm_ats_triage_audits(
            job_id, query_run_result_id, poll_source_id, company_name,
            company_tier, title, canonical_url, source, source_job_id,
            deterministic_status, deterministic_reason, eligibility_reason,
            input_payload, input_hash, prompt_version, schema_version, model,
            model_version, output_status, llm_recommendation, confidence, uncertainty,
            structured_output, raw_output, malformed_reason, reconciliation,
            duplicate_job_id, proposal_target, proposal_reason, created_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            triage_input.job_id,
            triage_input.query_run_result_id,
            triage_input.poll_source_id,
            triage_input.company_name,
            triage_input.company_tier,
            triage_input.title,
            normalize_url(triage_input.canonical_url),
            triage_input.source,
            triage_input.source_job_id,
            triage_input.deterministic_status,
            triage_input.deterministic_reason,
            llm_ats_triage_eligibility_reason(triage_input),
            json.dumps(llm_ats_triage_input_payload(triage_input), sort_keys=True),
            llm_ats_triage_input_hash(triage_input),
            prompt_version,
            schema_version,
            model,
            model_version,
            output_status,
            llm_recommendation,
            confidence,
            triage_output.uncertainty if triage_output else None,
            json.dumps(structured_output, sort_keys=True),
            raw_output,
            output_malformed_reason,
            reconciliation,
            triage_input.duplicate_job_id,
            proposal_target,
            proposal_reason,
            now,
        ),
    )
    return int(cursor.lastrowid)


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


def job_columns(connection: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}


def migrate_screen_bucket(connection: sqlite3.Connection) -> None:
    if "screen_bucket" not in job_columns(connection):
        connection.execute("ALTER TABLE jobs ADD COLUMN screen_bucket TEXT")
    connection.executescript(SCREEN_BUCKET_SCHEMA)
    connection.execute(
        """
        UPDATE jobs
        SET screen_bucket = CASE
            WHEN status = 'ready_to_apply' THEN 'ready_to_apply'
            WHEN rejection_reason = 'missing_proof' THEN 'portfolio_gap'
            WHEN status = 'ignored_by_filter' THEN 'pass'
            WHEN rejection_reason IN (
                'fit_mismatch',
                'level_scope_mismatch',
                'recruiter_screen_risk',
                'compensation_mismatch',
                'location_or_work_model_mismatch',
                'timing_or_capacity',
                'stale_or_closed_posting',
                'duplicate_or_already_tracked',
                'low_interest'
            ) THEN 'pass'
            ELSE screen_bucket
        END
        WHERE screen_bucket IS NULL
            AND (
                status IN ('ready_to_apply', 'ignored_by_filter')
                OR rejection_reason IS NOT NULL
            )
        """
    )


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
        version = 4
    if version < 5:
        now = utc_now()
        connection.executescript(AUTOMATION_RUN_SCHEMA)
        connection.execute(
            """
            INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (5, "automation_run_history", now),
        )
        version = 5
    if version < 6:
        now = utc_now()
        for column_sql in (
            "ALTER TABLE automation_runs ADD COLUMN created_draft_count INTEGER NOT NULL DEFAULT 0 CHECK (created_draft_count >= 0)",
            "ALTER TABLE automation_runs ADD COLUMN draft_ids TEXT",
        ):
            try:
                connection.execute(column_sql)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        connection.executescript(DRAFT_SCHEMA)
        connection.execute(
            """
            INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (6, "draft_review_storage_and_job_screen_bucket", now),
        )
        migrate_screen_bucket(connection)
        connection.executescript(LLM_ATS_TRIAGE_AUDIT_SCHEMA)


def init_database(db_path: Path) -> int:
    with closing(connect(db_path)) as connection:
        with connection:
            connection.executescript(SCHEMA)
            connection.executescript(SCREEN_BUCKET_SCHEMA)
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
        automation_recovery = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM automation_runs
            WHERE status IN ('failed', 'partial')
                AND recovery_status IN ('unresolved', 'retry_ready')
            GROUP BY status
            """
        ).fetchall()

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
        "automation_recovery_counts": {
            row["status"]: row["count"] for row in automation_recovery
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
            WHERE events.job_id IS NOT NULL
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


def role_pattern_label(*, lane: str | None, company_lanes: str | None, title: str) -> str:
    selected_lane = (lane or first_configured_lane(company_lanes) or "unknown").strip()
    keywords = sorted(title_keywords(title))
    keyword_label = "+".join(keywords[:4]) if keywords else normalize_title(title)
    if not keyword_label:
        keyword_label = "unclassified"
    return f"{selected_lane}/{keyword_label}"


def cooldown_evidence_rows(
    connection: sqlite3.Connection, *, as_of: datetime
) -> list[CooldownEvidence]:
    as_of_text = as_of.isoformat()
    rows = connection.execute(
        """
        SELECT
            jobs.id AS job_id,
            jobs.title AS job_title,
            jobs.status AS job_status,
            jobs.lane,
            jobs.application_outcome,
            jobs.rejection_reason,
            jobs.updated_at AS job_updated_at,
            companies.id AS company_id,
            companies.name AS company_name,
            companies.lanes AS company_lanes,
            rejection_event.id AS rejection_event_id,
            rejection_event.event_type AS rejection_event_type,
            rejection_event.happened_at AS rejection_event_at,
            rejection_action.id AS rejection_action_id,
            rejection_action.queue AS rejection_action_queue,
            rejection_action.status AS rejection_action_status,
            interview_event.id AS interview_event_id,
            interview_event.event_type AS interview_event_type,
            interview_event.happened_at AS interview_event_at,
            interview_action.id AS interview_action_id,
            interview_action.queue AS interview_action_queue,
            interview_action.status AS interview_action_status,
            timing_event.id AS timing_event_id,
            timing_event.event_type AS timing_event_type,
            timing_event.happened_at AS timing_event_at,
            timing_action.id AS timing_action_id,
            timing_action.queue AS timing_action_queue,
            timing_action.status AS timing_action_status,
            low_interest_event.id AS low_interest_event_id,
            low_interest_event.event_type AS low_interest_event_type,
            low_interest_event.happened_at AS low_interest_event_at,
            low_interest_action.id AS low_interest_action_id,
            low_interest_action.queue AS low_interest_action_queue,
            low_interest_action.status AS low_interest_action_status,
            status_event.id AS status_event_id,
            status_event.event_type AS status_event_type,
            status_event.happened_at AS status_event_at,
            status_action.id AS status_action_id,
            status_action.queue AS status_action_queue,
            status_action.status AS status_action_status,
            latest_action.id AS latest_action_id,
            latest_action.queue AS latest_action_queue,
            latest_action.status AS latest_action_status
        FROM jobs
        JOIN companies ON companies.id = jobs.company_id
        LEFT JOIN events AS rejection_event ON rejection_event.id = (
            SELECT events.id
            FROM events
            WHERE events.job_id = jobs.id
                AND events.event_type = 'rejection_received'
                AND events.happened_at <= ?
            ORDER BY events.happened_at DESC, events.id DESC
            LIMIT 1
        )
        LEFT JOIN actions AS rejection_action ON rejection_action.id = rejection_event.action_id
            AND rejection_action.updated_at <= ?
        LEFT JOIN events AS interview_event ON interview_event.id = (
            SELECT events.id
            FROM events
            WHERE events.job_id = jobs.id
                AND events.event_type = 'interview'
                AND events.happened_at <= ?
            ORDER BY events.happened_at DESC, events.id DESC
            LIMIT 1
        )
        LEFT JOIN actions AS interview_action ON interview_action.id = interview_event.action_id
            AND interview_action.updated_at <= ?
        LEFT JOIN events AS timing_event ON timing_event.id = (
            SELECT events.id
            FROM events
            WHERE events.job_id = jobs.id
                AND events.event_type IN ('status_changed', 'note')
                AND events.happened_at <= ?
                AND (
                    events.notes LIKE '%timing_or_capacity%'
                    OR events.notes LIKE '%timing/capacity%'
                    OR events.notes LIKE '%timing capacity%'
                )
            ORDER BY events.happened_at DESC, events.id DESC
            LIMIT 1
        )
        LEFT JOIN actions AS timing_action ON timing_action.id = timing_event.action_id
            AND timing_action.updated_at <= ?
        LEFT JOIN events AS low_interest_event ON low_interest_event.id = (
            SELECT events.id
            FROM events
            WHERE events.job_id = jobs.id
                AND events.event_type IN ('status_changed', 'note')
                AND events.happened_at <= ?
                AND (
                    events.notes LIKE '%low_interest%'
                    OR events.notes LIKE '%low interest%'
                    OR events.notes LIKE '%low-priority%'
                    OR events.notes LIKE '%low priority%'
                )
            ORDER BY events.happened_at DESC, events.id DESC
            LIMIT 1
        )
        LEFT JOIN actions AS low_interest_action ON low_interest_action.id = low_interest_event.action_id
            AND low_interest_action.updated_at <= ?
        LEFT JOIN events AS status_event ON status_event.id = (
            SELECT events.id
            FROM events
            WHERE events.job_id = jobs.id
                AND events.event_type = 'status_changed'
                AND events.happened_at <= ?
            ORDER BY events.happened_at DESC, events.id DESC
            LIMIT 1
        )
        LEFT JOIN actions AS status_action ON status_action.id = status_event.action_id
            AND status_action.updated_at <= ?
        LEFT JOIN actions AS latest_action ON latest_action.id = (
            SELECT actions.id
            FROM actions
            WHERE actions.job_id = jobs.id
                AND actions.status = 'done'
                AND actions.queue = 'classify'
                AND actions.updated_at <= ?
            ORDER BY actions.updated_at DESC, actions.id DESC
            LIMIT 1
        )
        WHERE (
            jobs.application_outcome IN (
                'rejected_before_screen',
                'rejected_after_screen',
                'rejected_after_interview',
                'passed_by_candidate'
            )
            OR jobs.rejection_reason IN ('timing_or_capacity', 'low_interest')
        )
            AND jobs.updated_at <= ?
        ORDER BY companies.name, jobs.id
        """,
        (
            as_of_text,
            as_of_text,
            as_of_text,
            as_of_text,
            as_of_text,
            as_of_text,
            as_of_text,
            as_of_text,
            as_of_text,
            as_of_text,
            as_of_text,
            as_of_text,
        ),
    ).fetchall()

    def build_evidence(
        row: sqlite3.Row,
        *,
        signal: str,
        event_prefixes: tuple[str, ...],
    ) -> CooldownEvidence:
        selected_prefix = next(
            (
                prefix
                for prefix in event_prefixes
                if row[f"{prefix}_event_id"] is not None
            ),
            None,
        )
        if selected_prefix is None:
            event_id = None
            event_type = None
            event_at = None
            event_action_id = None
            event_action_queue = None
            event_action_status = None
        else:
            event_id = int(row[f"{selected_prefix}_event_id"])
            event_type = row[f"{selected_prefix}_event_type"]
            event_at = row[f"{selected_prefix}_event_at"]
            event_action_id = row[f"{selected_prefix}_action_id"]
            event_action_queue = row[f"{selected_prefix}_action_queue"]
            event_action_status = row[f"{selected_prefix}_action_status"]
        action_id = event_action_id or row["latest_action_id"]
        action_queue = event_action_queue or row["latest_action_queue"]
        action_status = event_action_status or row["latest_action_status"]
        return CooldownEvidence(
            signal=signal,
            job_id=int(row["job_id"]),
            company_id=int(row["company_id"]),
            company_name=str(row["company_name"]),
            job_title=str(row["job_title"]),
            job_status=str(row["job_status"]),
            role_pattern=role_pattern_label(
                lane=row["lane"],
                company_lanes=row["company_lanes"],
                title=str(row["job_title"]),
            ),
            application_outcome=row["application_outcome"],
            rejection_reason=row["rejection_reason"],
            signal_at=str(event_at or row["job_updated_at"]),
            latest_event_id=event_id,
            latest_event_type=event_type,
            latest_event_at=event_at,
            latest_action_id=int(action_id) if action_id is not None else None,
            latest_action_queue=action_queue,
            latest_action_status=action_status,
        )

    evidence_rows: list[CooldownEvidence] = []
    for row in rows:
        if row["application_outcome"] == "rejected_before_screen":
            evidence_rows.append(
                build_evidence(
                    row,
                    signal="repeated_no_screen_rejection",
                    event_prefixes=("rejection", "status"),
                )
            )
        if row["application_outcome"] in (
            "rejected_after_screen",
            "rejected_after_interview",
        ):
            evidence_rows.append(
                build_evidence(
                    row,
                    signal="interview_loop_cooldown",
                    event_prefixes=("rejection", "interview", "status"),
                )
            )
        if row["rejection_reason"] == "timing_or_capacity" and row["timing_event_id"]:
            evidence_rows.append(
                build_evidence(
                    row,
                    signal="timing_capacity_cooldown",
                    event_prefixes=("timing",),
                )
            )
        if row["rejection_reason"] == "low_interest" and row["low_interest_event_id"]:
            evidence_rows.append(
                build_evidence(
                    row,
                    signal="durable_low_priority",
                    event_prefixes=("low_interest",),
                )
            )
    return evidence_rows


def normalize_report_datetime(value: str) -> datetime:
    parsed = parse_utc(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def cooldown_next_review(evidence_rows: list[CooldownEvidence], days: int) -> datetime:
    latest_signal_at = max(
        normalize_report_datetime(row.signal_at) for row in evidence_rows
    )
    return (latest_signal_at + timedelta(days=days)).replace(microsecond=0)


def grouped_cooldown_recommendations(
    *,
    evidence_rows: list[CooldownEvidence],
    as_of: datetime,
    limit: int,
) -> list[CooldownRecommendation]:
    recommendations: list[CooldownRecommendation] = []

    def add_grouped(
        *,
        signal: str,
        recommendation_type: str,
        reason: str,
        review_days: int,
        selected: list[CooldownEvidence],
        group_key: str,
        group_label: str,
        group_type: str,
        minimum_count: int,
    ) -> None:
        groups: dict[str, list[CooldownEvidence]] = {}
        for evidence in selected:
            key = group_key.format(
                company_id=evidence.company_id,
                company_name=evidence.company_name,
                role_pattern=evidence.role_pattern,
            )
            groups.setdefault(key, []).append(evidence)
        for key, rows in sorted(groups.items()):
            if len(rows) < minimum_count:
                continue
            next_review_at = cooldown_next_review(rows, review_days)
            if recommendation_type == "temporary" and next_review_at <= as_of:
                continue
            first = rows[0]
            label = group_label.format(
                company_id=first.company_id,
                company_name=first.company_name,
                role_pattern=first.role_pattern,
            )
            recommendations.append(
                CooldownRecommendation(
                    target_type=group_type,
                    target_key=key,
                    target_label=label,
                    recommendation_type=recommendation_type,
                    signal=signal,
                    reason=reason,
                    next_review_at=next_review_at.isoformat(),
                    evidence=tuple(rows[:limit]),
                )
            )

    no_screen = [
        row
        for row in evidence_rows
        if row.signal == "repeated_no_screen_rejection"
    ]
    interview_loop = [
        row
        for row in evidence_rows
        if row.signal == "interview_loop_cooldown"
    ]
    timing_capacity = [
        row for row in evidence_rows if row.signal == "timing_capacity_cooldown"
    ]
    durable_low_priority = [
        row
        for row in evidence_rows
        if row.signal == "durable_low_priority"
    ]

    common_group_specs = (
        (
            "company:{company_id}",
            "company=#{company_id} {company_name}",
            "company",
        ),
        (
            "role_pattern:{role_pattern}",
            "role_pattern={role_pattern}",
            "role_pattern",
        ),
    )
    for key_template, label_template, group_type in common_group_specs:
        add_grouped(
            signal="repeated_no_screen_rejection",
            recommendation_type="temporary",
            reason=(
                "Repeated rejected_before_screen outcomes; pause similar outreach "
                "until positioning or target criteria change."
            ),
            review_days=NO_INTERVIEW_COOLDOWN_DAYS,
            selected=no_screen,
            group_key=key_template,
            group_label=label_template,
            group_type=group_type,
            minimum_count=2,
        )
        add_grouped(
            signal="interview_loop_cooldown",
            recommendation_type="temporary",
            reason=(
                "Interview loop ended without conversion; pause similar high-effort "
                "work before re-entering the loop."
            ),
            review_days=INTERVIEW_LOOP_COOLDOWN_DAYS,
            selected=interview_loop,
            group_key=key_template,
            group_label=label_template,
            group_type=group_type,
            minimum_count=1,
        )
        add_grouped(
            signal="timing_capacity_cooldown",
            recommendation_type="temporary",
            reason=(
                "Stored timing_or_capacity reason says the opportunity is not worth "
                "the current queue slot."
            ),
            review_days=TIMING_CAPACITY_COOLDOWN_DAYS,
            selected=timing_capacity,
            group_key=key_template,
            group_label=label_template,
            group_type=group_type,
            minimum_count=1,
        )
        add_grouped(
            signal="durable_low_priority",
            recommendation_type="durable",
            reason=(
                "Stored low_interest reason points to a durable pass or low-priority "
                "decision."
            ),
            review_days=DURABLE_LOW_PRIORITY_REVIEW_DAYS,
            selected=durable_low_priority,
            group_key=key_template,
            group_label=label_template,
            group_type=group_type,
            minimum_count=1,
        )

    recommendations.sort(
        key=lambda recommendation: (
            0 if recommendation.recommendation_type == "temporary" else 1,
            recommendation.signal,
            recommendation.target_type,
            recommendation.target_key,
        )
    )
    return recommendations[:limit]


def format_cooldown_evidence(evidence: CooldownEvidence) -> str:
    event = (
        f"event=#{evidence.latest_event_id} {evidence.latest_event_type}"
        f" at {evidence.latest_event_at}"
        if evidence.latest_event_id is not None
        else "event=missing"
    )
    action = (
        f"action=#{evidence.latest_action_id} "
        f"{evidence.latest_action_queue}/{evidence.latest_action_status}"
        if evidence.latest_action_id is not None
        else "action=missing"
    )
    return (
        f"  - evidence job=#{evidence.job_id} {evidence.company_name} / "
        f"{evidence.job_title} | status={evidence.job_status} | "
        f"role_pattern={evidence.role_pattern} | "
        f"outcome={evidence.application_outcome or 'none'} | "
        f"reason={evidence.rejection_reason or 'none'} | {event} | {action}"
    )


def format_cooldown_recommendation(recommendation: CooldownRecommendation) -> list[str]:
    lines = [
        f"- type={recommendation.recommendation_type} | "
        f"target={recommendation.target_label} | "
        f"signal={recommendation.signal} | "
        f"cooldown_reason={recommendation.reason} | "
        f"suggested_next_review={recommendation.next_review_at} | "
        f"evidence_count={len(recommendation.evidence)}"
    ]
    lines.extend(format_cooldown_evidence(evidence) for evidence in recommendation.evidence)
    return lines


def compact_text(value: str, *, limit: int = 140) -> str:
    compacted = re.sub(r"\s+", " ", value).strip()
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 3].rstrip() + "..."


def join_text_parts(*values: object | None) -> str:
    return " | ".join(
        str(value).strip() for value in values if str(value or "").strip()
    )


def proof_gap_key_and_label(text: str, fallback: str | None = None) -> tuple[str, str]:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) > 2 and token not in PROOF_GAP_STOPWORDS
    ]
    if not tokens and fallback:
        tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", fallback.casefold())
            if len(token) > 2 and token not in PROOF_GAP_STOPWORDS
        ]
    if not tokens:
        tokens = ["uncategorized"]
    unique_tokens = list(dict.fromkeys(tokens))
    key_tokens = sorted(unique_tokens[:3])
    return " ".join(key_tokens), " ".join(unique_tokens[:3])


def proof_gap_evidence_from_row(row: sqlite3.Row) -> ProofGapEvidence:
    return ProofGapEvidence(
        source=str(row["source"]),
        source_id=int(row["source_id"]),
        company_id=int(row["company_id"]) if row["company_id"] is not None else None,
        company_name=row["company_name"],
        job_id=int(row["job_id"]) if row["job_id"] is not None else None,
        job_title=row["job_title"],
        lane=row["lane"],
        job_status=row["job_status"],
        application_outcome=row["application_outcome"],
        rejection_reason=row["rejection_reason"],
        gap_type=row["gap_type"],
        severity=row["severity"],
        gap_status=row["gap_status"],
        action_queue=row["action_queue"],
        action_kind=row["action_kind"],
        action_status=row["action_status"],
        event_type=row["event_type"],
        happened_at=row["happened_at"],
        text=compact_text(str(row["text"])),
    )


def proof_gap_evidence(connection: sqlite3.Connection) -> list[ProofGapEvidence]:
    evidence: list[ProofGapEvidence] = []
    evidence.extend(
        proof_gap_evidence_from_row(row)
        for row in connection.execute(
            """
            SELECT
                'gap' AS source,
                gaps.id AS source_id,
                COALESCE(gaps.company_id, jobs.company_id) AS company_id,
                companies.name AS company_name,
                jobs.id AS job_id,
                jobs.title AS job_title,
                jobs.lane,
                jobs.status AS job_status,
                jobs.application_outcome,
                jobs.rejection_reason,
                gaps.gap_type,
                gaps.severity,
                gaps.status AS gap_status,
                NULL AS action_queue,
                NULL AS action_kind,
                NULL AS action_status,
                NULL AS event_type,
                gaps.updated_at AS happened_at,
                TRIM(
                    gaps.description
                    || COALESCE(' | resolution_action=' || gaps.resolution_action, '')
                ) AS text
            FROM gaps
            LEFT JOIN jobs ON jobs.id = gaps.job_id
            LEFT JOIN companies ON companies.id = COALESCE(gaps.company_id, jobs.company_id)
            WHERE gaps.status IN ('open', 'in_progress')
            ORDER BY gaps.id
            """
        ).fetchall()
    )
    evidence.extend(
        proof_gap_evidence_from_row(row)
        for row in connection.execute(
            """
            SELECT
                'job' AS source,
                jobs.id AS source_id,
                jobs.company_id,
                companies.name AS company_name,
                jobs.id AS job_id,
                jobs.title AS job_title,
                jobs.lane,
                jobs.status AS job_status,
                jobs.application_outcome,
                jobs.rejection_reason,
                NULL AS gap_type,
                NULL AS severity,
                NULL AS gap_status,
                NULL AS action_queue,
                NULL AS action_kind,
                NULL AS action_status,
                NULL AS event_type,
                jobs.updated_at AS happened_at,
                TRIM(
                    COALESCE(jobs.artifact_opportunity, '')
                    || COALESCE(' | discovery=' || jobs.discovery_status, '')
                    || COALESCE(' | role=' || jobs.title, '')
                    || COALESCE(' | reason=' || jobs.rejection_reason, '')
                ) AS text
            FROM jobs
            JOIN companies ON companies.id = jobs.company_id
            WHERE jobs.rejection_reason = 'missing_proof'
                OR jobs.artifact_opportunity IS NOT NULL
            ORDER BY jobs.id
            """
        ).fetchall()
    )
    evidence.extend(
        proof_gap_evidence_from_row(row)
        for row in connection.execute(
            """
            SELECT
                'action' AS source,
                actions.id AS source_id,
                actions.company_id,
                companies.name AS company_name,
                jobs.id AS job_id,
                jobs.title AS job_title,
                jobs.lane,
                jobs.status AS job_status,
                jobs.application_outcome,
                jobs.rejection_reason,
                gaps.gap_type,
                gaps.severity,
                gaps.status AS gap_status,
                actions.queue AS action_queue,
                actions.kind AS action_kind,
                actions.status AS action_status,
                NULL AS event_type,
                COALESCE(actions.completed_at, actions.updated_at) AS happened_at,
                TRIM(
                    COALESCE(actions.notes, '')
                    || COALESCE(' | gap=' || gaps.description, '')
                    || COALESCE(' | resolution_action=' || gaps.resolution_action, '')
                ) AS text
            FROM actions
            JOIN companies ON companies.id = actions.company_id
            LEFT JOIN jobs ON jobs.id = actions.job_id
            LEFT JOIN gaps ON gaps.id = actions.gap_id
            WHERE actions.gap_id IS NOT NULL
                OR lower(COALESCE(actions.notes, '')) LIKE '%missing_proof%'
                OR lower(COALESCE(actions.notes, '')) LIKE '%proof gap%'
                OR lower(COALESCE(actions.notes, '')) LIKE '%portfolio_gap%'
            ORDER BY actions.id
            """
        ).fetchall()
    )
    evidence.extend(
        proof_gap_evidence_from_row(row)
        for row in connection.execute(
            """
            SELECT
                'event' AS source,
                events.id AS source_id,
                events.company_id,
                companies.name AS company_name,
                jobs.id AS job_id,
                jobs.title AS job_title,
                jobs.lane,
                jobs.status AS job_status,
                jobs.application_outcome,
                jobs.rejection_reason,
                gaps.gap_type,
                gaps.severity,
                gaps.status AS gap_status,
                NULL AS action_queue,
                NULL AS action_kind,
                NULL AS action_status,
                events.event_type,
                events.happened_at,
                TRIM(
                    COALESCE(events.notes, '')
                    || COALESCE(' | gap=' || gaps.description, '')
                    || COALESCE(' | resolution_action=' || gaps.resolution_action, '')
                ) AS text
            FROM events
            JOIN companies ON companies.id = events.company_id
            LEFT JOIN jobs ON jobs.id = events.job_id
            LEFT JOIN gaps ON gaps.id = events.gap_id
            WHERE events.gap_id IS NOT NULL
                OR events.event_type = 'gap_identified'
                OR lower(COALESCE(events.notes, '')) LIKE '%missing_proof%'
                OR lower(COALESCE(events.notes, '')) LIKE '%proof gap%'
                OR lower(COALESCE(events.notes, '')) LIKE '%portfolio_gap%'
            ORDER BY events.id
            """
        ).fetchall()
    )
    return [item for item in evidence if item.text]


def group_proof_gap_evidence(
    evidence: list[ProofGapEvidence],
) -> list[ProofGapGroup]:
    groups: dict[str, ProofGapGroup] = {}
    for item in evidence:
        key, label = proof_gap_key_and_label(item.text, item.gap_type)
        group = groups.get(key)
        if group is None:
            group = ProofGapGroup(key=key, label=label, evidence=[])
            groups[key] = group
        group.evidence.append(item)
    return sorted(groups.values(), key=proof_gap_sort_key)


def proof_gap_strength(group: ProofGapGroup) -> str:
    job_count = len(group.job_ids)
    company_count = len(group.company_ids)
    if job_count >= 2 and company_count >= 2:
        return "recurring"
    if job_count >= 2:
        return "repeated_role"
    if company_count >= 2:
        return "company_cluster"
    return "one_off"


def proof_gap_score(group: ProofGapGroup) -> int:
    source_score = sum(
        PROOF_GAP_SOURCE_SCORE.get(item.source, 1) for item in group.evidence
    )
    severity_score = sum(
        PROOF_GAP_SEVERITY_SCORE.get(item.severity or "", 0)
        for item in group.evidence
    )
    active_gap_score = sum(
        2 for item in group.evidence if item.gap_status in ("open", "in_progress")
    )
    return (
        len(group.job_ids) * 12
        + len(group.company_ids) * 8
        + len(group.evidence) * 3
        + source_score
        + severity_score
        + active_gap_score
    )


def proof_gap_sort_key(group: ProofGapGroup) -> tuple[int, int, int, str]:
    recurring_rank = 1 if proof_gap_strength(group) == "one_off" else 0
    return (
        recurring_rank,
        -proof_gap_score(group),
        -len(group.evidence),
        group.label,
    )


def proof_gap_haystack(group: ProofGapGroup) -> str:
    return " ".join(
        join_text_parts(
            item.text,
            item.gap_type,
            item.action_queue,
            item.action_kind,
            item.event_type,
        )
        for item in group.evidence
    ).casefold()


def proof_gap_has_any(group: ProofGapGroup, tokens: tuple[str, ...]) -> bool:
    haystack = proof_gap_haystack(group)
    return any(token in haystack for token in tokens)


def recommend_proof_gap_improvement(group: ProofGapGroup) -> str:
    haystack = proof_gap_haystack(group)
    if any(token in haystack for token in ("resume lane", "lane resume", "resume_lane")):
        return "resume lane"
    if any(
        token in haystack
        for token in ("application answer", "playbook", "interview", "cover letter")
    ):
        return "application playbook"
    if any(
        token in haystack
        for token in ("artifact", "case study", "demo", "portfolio", "memo", "teardown")
    ):
        return "artifact"
    if any(item.action_queue == "artifact" for item in group.evidence):
        return "artifact"
    if any(token in haystack for token in ("bullet", "metric", "impact", "quantified")):
        return "bullet"
    if any(token in haystack for token in ("profile", "positioning", "headline", "summary")):
        return "profile"
    if group.lanes and len(group.lanes) == 1:
        return "resume lane"
    return "bullet"


def proof_gap_routing(group: ProofGapGroup) -> str:
    if proof_gap_strength(group) == "one_off":
        return "sqlite"
    if any(item.action_queue == "artifact" for item in group.evidence):
        return "linear_candidate"
    if proof_gap_has_any(
        group,
        (
            "application answer",
            "artifact",
            "case study",
            "cover letter",
            "demo",
            "lane resume",
            "memo",
            "playbook",
            "portfolio",
            "resume lane",
            "resume_lane",
            "teardown",
        ),
    ):
        return "linear_candidate"
    return "sqlite"


def format_count_set(values: set[str]) -> str:
    return ",".join(sorted(values)) if values else "none"


def format_proof_gap_evidence(item: ProofGapEvidence) -> str:
    subject = (
        f"company=#{item.company_id} {item.company_name}"
        if item.company_id
        else "company=unknown"
    )
    if item.job_id:
        subject += f" | job=#{item.job_id} {item.job_title}"
    context = (
        render_optional("lane", item.lane)
        + render_optional("status", item.job_status)
        + render_optional("outcome", item.application_outcome)
        + render_optional("reason", item.rejection_reason)
        + render_optional("gap_type", item.gap_type)
        + render_optional("severity", item.severity)
        + render_optional("gap_status", item.gap_status)
        + render_optional("queue", item.action_queue)
        + render_optional("kind", item.action_kind)
        + render_optional("action_status", item.action_status)
        + render_optional("event", item.event_type)
        + render_optional("at", item.happened_at)
    )
    return (
        f"  - {item.source}=#{item.source_id} | "
        f"{subject}{context} | text={item.text}"
    )


def print_proof_gap_group(index: int, group: ProofGapGroup, evidence_limit: int) -> None:
    print(
        f"{index}. {group.label} | strength={proof_gap_strength(group)} | "
        f"score={proof_gap_score(group)} | "
        f"improvement={recommend_proof_gap_improvement(group)} | "
        f"routing={proof_gap_routing(group)}"
    )
    print(
        f"   evidence={len(group.evidence)} | jobs={len(group.job_ids)} | "
        f"companies={len(group.company_ids)} | lanes={format_count_set(group.lanes)} | "
        f"statuses={format_count_set(group.job_statuses)} | "
        f"outcomes={format_count_set(group.outcomes)} | "
        f"reasons={format_count_set(group.rejection_reasons)}"
    )
    for item in sorted(
        group.evidence,
        key=lambda evidence: (
            evidence.source,
            evidence.company_id or 0,
            evidence.job_id or 0,
            evidence.source_id,
        ),
    )[:evidence_limit]:
        print(format_proof_gap_evidence(item))
    hidden = len(group.evidence) - evidence_limit
    if hidden > 0:
        print(f"  - ... {hidden} more evidence rows")


def pipeline_status_to_job_status(status: str | None) -> str:
    if status == "ready_to_apply":
        return "ready_to_apply"
    if status == "applied":
        return "applied"
    if status in ("screened_out", "skipped"):
        return "ignored_by_filter"
    return "discovered"


def legacy_screen_bucket(record: dict[str, object], job_status: str) -> str | None:
    bucket = record.get("bucket")
    if isinstance(bucket, str) and bucket in SCREEN_BUCKETS:
        return bucket
    if job_status == "ready_to_apply":
        return "ready_to_apply"
    if job_status == "ignored_by_filter":
        return "pass"
    return None


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
        "recommendation",
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


def legacy_application_outcome(record: dict[str, object], job_status: str) -> str | None:
    recommendation = record.get("recommendation")
    if isinstance(recommendation, str) and recommendation in APPLICATION_OUTCOMES:
        return recommendation
    if (
        isinstance(recommendation, str)
        and recommendation in LEGACY_APPLICATION_OUTCOME_MAP
    ):
        return LEGACY_APPLICATION_OUTCOME_MAP[recommendation]
    if job_status == "applied":
        return "pending_response"
    if job_status == "interviewing":
        return "active_interview_loop"
    return None


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
            application_folder, material_paths, application_outcome, screen_bucket,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            legacy_application_outcome(record, job_status),
            legacy_screen_bucket(record, job_status),
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
        versions = {
            int(row[0])
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
    expected_versions = set(range(1, SCHEMA_VERSION + 1))
    version = max(versions, default=0)
    if version < SCHEMA_VERSION or not expected_versions.issubset(versions):
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
    if row["screen_bucket"]:
        parts.append(f"bucket={row['screen_bucket']}")
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


def action_review_state(row: sqlite3.Row, *, now: datetime | None = None) -> str:
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

    now = now or datetime.now(timezone.utc)
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


def format_action_reminder(
    row: sqlite3.Row, *, script_name: str, as_of: datetime
) -> str:
    parts = [
        f"- action=#{row['id']}",
        f"queue={row['queue']}",
        f"kind={row['kind']}",
        f"review_state={action_review_state(row, now=as_of)}",
        f"status={row['status']}",
        f"due_state={due_state(row['due_at'], today=as_of.date())}",
        f"due={row['due_at'] or 'unscheduled'}",
        f"company=#{row['company_id']} {row['company_name']}",
    ]
    if row["job_id"]:
        parts.append(f"job=#{row['job_id']} {row['job_title']}")
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
    parts.append(
        f"next_command={sys.executable} {script_name} action next "
        f"--queue {row['queue']} --limit 5"
    )
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


def reminder_action_rows(
    connection: sqlite3.Connection,
    *,
    queue: str | None,
    include_ready: bool,
    as_of: datetime,
    limit: int,
) -> list[sqlite3.Row]:
    filters = [open_action_where_clause("actions")]
    params: list[object] = []
    if queue:
        filters.append("actions.queue = ?")
        params.append(queue)
    where = f"WHERE {' AND '.join(filters)}"
    rows = sorted(
        connection.execute(action_rows_query(where), params).fetchall(),
        key=lambda row: reminder_action_order_key(row, as_of=as_of),
    )
    selected: list[sqlite3.Row] = []
    for row in rows:
        review_state = action_review_state(row, now=as_of)
        if review_state in ("stale", "due", "blocked") or (
            include_ready and review_state == "ready"
        ):
            selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def reminder_action_order_key(
    row: sqlite3.Row, *, as_of: datetime
) -> tuple[int, int, str, int]:
    due_at = None
    try:
        due_at = parse_optional_utc(row["due_at"])
    except ValueError:
        due_at = None
    if due_at is not None and due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)

    day_start = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
    if row["status"] == "blocked":
        state_order = 2
    elif due_at is not None and due_at < day_start:
        state_order = 0
    elif due_at is not None and due_at <= as_of:
        state_order = 1
    else:
        state_order = 3
    unscheduled_order = 1 if due_at is None else 0
    due_order = due_at.isoformat() if due_at is not None else ""
    return (state_order, unscheduled_order, due_order, int(row["id"]))


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


def draft_review_marker(draft_type: str) -> str:
    if draft_type == "application_answer":
        return "REVIEW ONLY - UNSUBMITTED. Human approval required before any application form submission."
    return "REVIEW ONLY - UNSENT. Human approval required before any email, LinkedIn message, or outreach."


def draft_markdown(
    *,
    draft_type: str,
    title: str,
    body: str,
    company_name: str,
    job_title: str | None,
    source_summary: str | None,
    action_id: int | None,
    contact_id: int | None,
    artifact_id: int | None,
) -> str:
    source_parts = [f"company={company_name}"]
    if job_title:
        source_parts.append(f"job={job_title}")
    if action_id is not None:
        source_parts.append(f"action=#{action_id}")
    if contact_id is not None:
        source_parts.append(f"contact=#{contact_id}")
    if artifact_id is not None:
        source_parts.append(f"artifact=#{artifact_id}")
    if source_summary:
        source_parts.append(f"source={source_summary}")
    return (
        f"# {title}\n\n"
        f"**{draft_review_marker(draft_type)}**\n\n"
        f"Source: {' | '.join(source_parts)}\n\n"
        "Approval boundary: revise, reject, or approve explicitly in the command center. "
        "Do not send or submit from this file.\n\n"
        "## Draft\n\n"
        f"{body.rstrip()}\n"
    )


def write_draft_file(
    *,
    path_text: str,
    draft_type: str,
    title: str,
    body: str,
    company_name: str,
    job_title: str | None,
    source_summary: str | None,
    action_id: int | None,
    contact_id: int | None,
    artifact_id: int | None,
) -> None:
    path = resolved_draft_path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(
        draft_markdown(
            draft_type=draft_type,
            title=title,
            body=body,
            company_name=company_name,
            job_title=job_title,
            source_summary=source_summary,
            action_id=action_id,
            contact_id=contact_id,
            artifact_id=artifact_id,
        ),
        encoding="utf-8",
    )
    temp_path.replace(path)


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def resolved_draft_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def validate_draft_path(
    path_text: str,
    *,
    db_path: Path,
    job_application_folder: str | None,
) -> None:
    path = resolved_draft_path(path_text)
    allowed_roots = [
        (REPO_ROOT / "APPLICATIONS" / "READY_TO_APPLY").resolve(),
        (db_path.parent / "APPLICATIONS" / "READY_TO_APPLY").resolve(),
    ]
    if job_application_folder:
        folder = Path(job_application_folder)
        if not folder.is_absolute():
            folder = REPO_ROOT / folder
        allowed_roots.append(folder.resolve())
    if not any(is_relative_to(path, root) for root in allowed_roots):
        raise ValueError(
            "draft path must be under APPLICATIONS/READY_TO_APPLY or the linked "
            "job application_folder"
        )


def render_draft(row: sqlite3.Row) -> str:
    parts = [
        f"draft id={row['id']}",
        f"type={row['draft_type']}",
        f"status={row['status']}",
        "review_only=unsent_unsubmitted",
        f"title={row['title']}",
        f"company={row['company_name']}",
    ]
    for label, column in (
        ("job", "job_title"),
        ("contact", "contact_name"),
        ("artifact", "artifact_type"),
        ("action", "action_kind"),
        ("path", "path"),
        ("source", "source_summary"),
        ("approval", "approval_note"),
    ):
        if row[column]:
            parts.append(f"{label}={row[column]}")
    parts.append("approval_required=before_external_side_effect")
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
    source_ids: list[int] | None = None,
) -> list[sqlite3.Row]:
    filters = ["company_sources.status = 'active'"]
    params: list[object] = []
    if company:
        filters.append("companies.name_key = ?")
        params.append(company_name_key(company))
    if source_ids:
        placeholders = ", ".join("?" for _ in source_ids)
        filters.append(f"company_sources.id IN ({placeholders})")
        params.extend(source_ids)
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
            compensation_signal, screen_bucket, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            "pass" if status == "ignored_by_filter" else None,
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


def find_open_screen_action_id(
    connection: sqlite3.Connection,
    *,
    job_id: int,
) -> int | None:
    action = connection.execute(
        """
        SELECT id
        FROM actions
        WHERE job_id = ?
            AND queue = 'screen'
            AND kind = 'screen_role'
            AND status IN ('queued', 'in_progress', 'blocked', 'rescheduled')
        LIMIT 1
        """,
        (job_id,),
    ).fetchone()
    return int(action["id"]) if action is not None else None


def poll_sources(
    connection: sqlite3.Connection,
    *,
    sources: list[sqlite3.Row],
) -> PollRunResult:
    source_results: list[SourcePollResult] = []
    for source in sources:
        now = utc_now()
        try:
            discovered_jobs = fetch_source_jobs(source)
        except (HTTPError, URLError, OSError, ValueError) as error:
            source_results.append(
                SourcePollResult(
                    source_id=int(source["id"]),
                    company_name=str(source["company_name"]),
                    source_type=str(source["source_type"]),
                    failure=str(error),
                )
            )
            continue
        inserted = 0
        ignored = 0
        duplicates = 0
        screen_action_ids: list[int] = []
        try:
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
                        action_id = find_open_screen_action_id(
                            connection,
                            job_id=result.job_id,
                        )
                        if action_id is not None:
                            screen_action_ids.append(action_id)
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
        except sqlite3.Error as error:
            if connection.in_transaction:
                connection.rollback()
            source_results.append(
                SourcePollResult(
                    source_id=int(source["id"]),
                    company_name=str(source["company_name"]),
                    source_type=str(source["source_type"]),
                    failure=str(error),
                )
            )
            continue
        source_results.append(
            SourcePollResult(
                source_id=int(source["id"]),
                company_name=str(source["company_name"]),
                source_type=str(source["source_type"]),
                discovered_count=len(discovered_jobs),
                inserted_count=inserted,
                ignored_count=ignored,
                duplicate_count=duplicates,
                screen_action_ids=tuple(screen_action_ids),
            )
        )
    return PollRunResult(source_count=len(sources), source_results=tuple(source_results))


def print_source_poll_result(result: SourcePollResult) -> None:
    if result.failure:
        print(
            "poll "
            f"source_id={result.source_id} company={result.company_name} "
            f"type={result.source_type} failed error={result.failure}"
        )
        return
    print(
        "poll "
        f"source_id={result.source_id} company={result.company_name} "
        f"type={result.source_type} discovered={result.discovered_count} "
        f"inserted={result.inserted_count} ignored={result.ignored_count} "
        f"duplicates={result.duplicate_count} "
        f"screen_actions={len(result.screen_action_ids)}"
    )


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

        run_result = poll_sources(connection, sources=sources)
        for source_result in run_result.source_results:
            print_source_poll_result(source_result)
    return 1 if run_result.failure_count else 0


def import_query_run_payload(
    connection: sqlite3.Connection,
    payload: dict[str, object],
    *,
    now: str,
) -> QueryImportOutcome:
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
    return QueryImportOutcome(
        query_run_id=query_run_id,
        import_state=import_state,
        source=source,
        pack=pack,
        status=status,
        result_count=result_count,
        accepted_count=counts["accepted"],
        rejected_count=counts["rejected"],
        duplicate_count=counts["duplicate"],
        raw_source_reference=raw_source_reference,
    )


def print_query_import_outcome(outcome: QueryImportOutcome) -> None:
    print(
        f"query run {outcome.import_state} id={outcome.query_run_id} source={outcome.source}"
        + render_optional("pack", outcome.pack)
        + f" status={outcome.status} results={outcome.result_count}"
        + f" accepted={outcome.accepted_count} rejected={outcome.rejected_count}"
        + f" duplicates={outcome.duplicate_count}"
    )


def command_query_import(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    payload = read_query_import_payload(args)
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            outcome = import_query_run_payload(connection, payload, now=now)
    print_query_import_outcome(outcome)
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


def automation_recovery_default(status: str) -> str:
    if status in ("failed", "partial"):
        return "unresolved"
    return "none"


def validate_automation_recovery_status(status: str, recovery_status: str) -> None:
    if status in ("failed", "partial"):
        if recovery_status == "none":
            raise ValueError(
                "failed or partial automation runs require unresolved, retry_ready, "
                "skipped, or manual_resolved recovery status"
            )
        return
    if recovery_status != "none":
        raise ValueError(
            "only failed or partial automation runs may have a recovery status"
        )


def validate_automation_failure_evidence(
    status: str,
    *,
    failure_count: int,
    failure_summary: str | None,
    recovery_notes: str | None,
) -> None:
    if status not in ("failed", "partial") and (
        failure_count > 0 or failure_summary
    ):
        raise ValueError(
            "automation runs with failure evidence must use status failed or partial"
        )
    if status not in ("failed", "partial") and recovery_notes:
        raise ValueError(
            "only failed or partial automation runs may have recovery notes"
        )


def encode_id_list(values: list[int] | None) -> str | None:
    if not values:
        return None
    return ",".join(str(value) for value in values)


def validate_existing_ids(
    connection: sqlite3.Connection,
    *,
    table: str,
    label: str,
    values: list[int] | None,
) -> None:
    if not values:
        return
    for value in values:
        row = connection.execute(
            f"SELECT id FROM {table} WHERE id = ?",
            (value,),
        ).fetchone()
        if row is None:
            raise ValueError(f"{label} not found: {value}")


def format_stable_links(row: sqlite3.Row) -> str:
    links: list[str] = []
    if row["action_ids"]:
        links.append(f"actions=#{row['action_ids'].replace(',', ',#')}")
    if row["artifact_ids"]:
        links.append(f"artifacts=#{row['artifact_ids'].replace(',', ',#')}")
    if "draft_ids" in row.keys() and row["draft_ids"]:
        links.append(f"drafts=#{row['draft_ids'].replace(',', ',#')}")
    if row["query_run_ids"]:
        links.append(f"query_runs=#{row['query_run_ids'].replace(',', ',#')}")
    return " ".join(links) if links else "links=none"


def automation_next_step(row: sqlite3.Row) -> str:
    if row["recovery_status"] == "retry_ready":
        return "run retry through the same source/scope and record a new automation run"
    if row["recovery_status"] in ("skipped", "manual_resolved", "none"):
        return "no recovery action pending"
    if row["status"] in ("failed", "partial"):
        return "choose: automation recover retry|skip|resolve"
    return "no recovery action pending"


def print_automation_run(row: sqlite3.Row) -> None:
    print(
        f"{row['id']} | source={row['source']} | scope={row['scope']} "
        f"| status={row['status']} | started={row['started_at']} "
        f"| ended={row['ended_at'] or 'unset'} | results={row['result_count']} "
        f"| failures={row['failure_count']} | created="
        f"actions:{row['created_action_count']},artifacts:{row['created_artifact_count']},"
        f"drafts:{row['created_draft_count']},"
        f"query_runs:{row['created_query_run_count']} | recovery={row['recovery_status']} "
        f"| {format_stable_links(row)}"
        + render_optional("failure", row["failure_summary"])
        + render_optional("notes", row["notes"])
    )


def insert_automation_run(
    connection: sqlite3.Connection,
    *,
    source: str,
    scope: str,
    status: str,
    started_at: str,
    ended_at: str | None,
    result_count: int = 0,
    failure_count: int = 0,
    failure_summary: str | None = None,
    action_ids: list[int] | None = None,
    artifact_ids: list[int] | None = None,
    draft_ids: list[int] | None = None,
    query_run_ids: list[int] | None = None,
    created_query_run_count: int | None = None,
    notes: str | None = None,
    recovery_status: str | None = None,
    recovery_notes: str | None = None,
    raw_source_reference: str | None = None,
    now: str | None = None,
) -> int:
    now = now or utc_now()
    recovery_status = recovery_status or automation_recovery_default(status)
    validate_automation_recovery_status(status, recovery_status)
    validate_automation_failure_evidence(
        status,
        failure_count=failure_count,
        failure_summary=failure_summary,
        recovery_notes=recovery_notes,
    )
    action_ids = action_ids or []
    artifact_ids = artifact_ids or []
    draft_ids = draft_ids or []
    query_run_ids = query_run_ids or []
    created_query_run_count = (
        len(query_run_ids) if created_query_run_count is None else created_query_run_count
    )
    validate_existing_ids(
        connection,
        table="actions",
        label="action",
        values=action_ids,
    )
    validate_existing_ids(
        connection,
        table="artifacts",
        label="artifact",
        values=artifact_ids,
    )
    validate_existing_ids(
        connection,
        table="drafts",
        label="draft",
        values=draft_ids,
    )
    validate_existing_ids(
        connection,
        table="query_runs",
        label="query run",
        values=query_run_ids,
    )
    cursor = connection.execute(
        """
        INSERT INTO automation_runs(
            source, scope, status, started_at, ended_at, result_count,
            failure_count, created_action_count, created_artifact_count,
            created_draft_count, created_query_run_count, failure_summary, action_ids,
            artifact_ids, draft_ids, query_run_ids, notes, recovery_status,
            recovery_notes, raw_source_reference, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            scope,
            status,
            started_at,
            ended_at,
            result_count,
            failure_count,
            len(action_ids),
            len(artifact_ids),
            len(draft_ids),
            created_query_run_count,
            failure_summary,
            encode_id_list(action_ids),
            encode_id_list(artifact_ids),
            encode_id_list(draft_ids),
            encode_id_list(query_run_ids),
            notes,
            recovery_status,
            recovery_notes,
            raw_source_reference,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def command_automation_record(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    now = utc_now()
    recovery_status = args.recovery_status or automation_recovery_default(args.status)
    with closing(connect(db_path)) as connection:
        with connection:
            run_id = insert_automation_run(
                connection,
                source=args.source,
                scope=args.scope,
                status=args.status,
                started_at=args.started_at,
                ended_at=args.ended_at,
                result_count=args.result_count,
                failure_count=args.failure_count,
                failure_summary=args.failure_summary,
                action_ids=args.action_id,
                artifact_ids=args.artifact_id,
                draft_ids=args.draft_id,
                query_run_ids=args.query_run_id,
                notes=args.notes,
                recovery_status=recovery_status,
                recovery_notes=args.recovery_notes,
                raw_source_reference=args.raw_source_reference,
                now=now,
            )
    print(
        f"automation run recorded id={run_id} source={args.source} scope={args.scope} "
        f"status={args.status} recovery={recovery_status}"
    )
    return 0


def automation_poll_scope(
    *,
    company: str | None,
    source_ids: list[int] | None,
) -> str:
    if company and source_ids:
        return f"company={company} source_ids={','.join(str(id_) for id_ in source_ids)}"
    if company:
        return f"company={company}"
    if source_ids:
        return f"source_ids={','.join(str(id_) for id_ in source_ids)}"
    return "active_target_company_sources"


def automation_poll_status(run_result: PollRunResult) -> str:
    if run_result.source_count == 0:
        return "skipped"
    if run_result.failure_count == 0:
        return "completed"
    if run_result.failure_count == run_result.source_count:
        return "failed"
    return "partial"


def automation_poll_failure_summary(run_result: PollRunResult) -> str | None:
    failures = [
        f"source_id={result.source_id} company={result.company_name} "
        f"type={result.source_type} error={result.failure}"
        for result in run_result.source_results
        if result.failure
    ]
    return "; ".join(failures) if failures else None


def missing_requested_source_results(
    *,
    requested_source_ids: list[int] | None,
    sources: list[sqlite3.Row],
    company: str | None,
) -> tuple[SourcePollResult, ...]:
    if not requested_source_ids:
        return ()
    returned_source_ids = {int(source["id"]) for source in sources}
    missing_source_ids = [
        source_id
        for source_id in dict.fromkeys(requested_source_ids)
        if source_id not in returned_source_ids
    ]
    return tuple(
        SourcePollResult(
            source_id=source_id,
            company_name=company or "unknown",
            source_type="unknown",
            failure="requested source is not an active source in scope",
        )
        for source_id in missing_source_ids
    )


def missing_requested_company_results(
    connection: sqlite3.Connection,
    *,
    company: str | None,
) -> tuple[SourcePollResult, ...]:
    if not company:
        return ()
    row = connection.execute(
        "SELECT id FROM companies WHERE name_key = ?",
        (company_name_key(company),),
    ).fetchone()
    if row is not None:
        return ()
    return (
        SourcePollResult(
            source_id=0,
            company_name=company,
            source_type="unknown",
            failure="requested company was not found",
        ),
    )


def no_active_requested_company_source_results(
    *,
    company: str | None,
    sources: list[sqlite3.Row],
    requested_source_ids: list[int] | None,
    missing_company_results: tuple[SourcePollResult, ...],
) -> tuple[SourcePollResult, ...]:
    if not company or sources or requested_source_ids or missing_company_results:
        return ()
    return (
        SourcePollResult(
            source_id=0,
            company_name=company,
            source_type="unknown",
            failure="requested company has no active ATS sources in scope",
        ),
    )


def combine_poll_results(
    *,
    run_result: PollRunResult,
    extra_results: tuple[SourcePollResult, ...],
) -> PollRunResult:
    if not extra_results:
        return run_result
    source_results = (*run_result.source_results, *extra_results)
    return PollRunResult(
        source_count=len(source_results),
        source_results=source_results,
    )


def automation_poll_notes(run_result: PollRunResult) -> str:
    return (
        f"sources={run_result.source_count} inserted={run_result.inserted_count} "
        f"ignored={run_result.ignored_count} duplicates={run_result.duplicate_count} "
        f"screen_actions={len(run_result.screen_action_ids)}; "
        "screen actions require human review before applying or outreach"
    )


def append_automation_run_to_actions(
    connection: sqlite3.Connection,
    *,
    action_ids: tuple[int, ...],
    automation_run_id: int,
    now: str,
) -> None:
    if not action_ids:
        return
    for action_id in action_ids:
        connection.execute(
            """
            UPDATE actions
            SET notes = CASE
                    WHEN notes IS NULL OR notes = ''
                        THEN ?
                    ELSE notes || char(10) || ?
                END,
                updated_at = ?
            WHERE id = ?
            """,
            (
                f"automation_run=#{automation_run_id}",
                f"automation_run=#{automation_run_id}",
                now,
                action_id,
            ),
        )


def command_automation_poll_targets(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    started_at = utc_now()
    scope = automation_poll_scope(company=args.company, source_ids=args.source_id)
    with closing(connect(db_path)) as connection:
        sources = poll_source_rows(
            connection,
            company=args.company,
            source_id=None,
            source_ids=args.source_id,
        )
        missing_source_results = missing_requested_source_results(
            requested_source_ids=args.source_id,
            sources=sources,
            company=args.company,
        )
        missing_company_results = missing_requested_company_results(
            connection,
            company=args.company,
        )
        no_active_company_source_results = no_active_requested_company_source_results(
            company=args.company,
            sources=sources,
            requested_source_ids=args.source_id,
            missing_company_results=missing_company_results,
        )
        scope_failure_results = (
            *missing_company_results,
            *missing_source_results,
            *no_active_company_source_results,
        )
        if not sources:
            ended_at = utc_now()
            run_result = combine_poll_results(
                run_result=PollRunResult(source_count=0, source_results=()),
                extra_results=scope_failure_results,
            )
            status = automation_poll_status(run_result)
            failure_summary = automation_poll_failure_summary(run_result)
            notes = (
                automation_poll_notes(run_result)
                if scope_failure_results
                else "No active Greenhouse, Lever, or Ashby sources matched scope."
            )
            with connection:
                run_id = insert_automation_run(
                    connection,
                    source="target_company_poll",
                    scope=scope,
                    status=status,
                    started_at=started_at,
                    ended_at=ended_at,
                    failure_count=run_result.failure_count,
                    failure_summary=failure_summary,
                    notes=notes,
                    raw_source_reference=scope,
                    now=ended_at,
                )
            if scope_failure_results:
                for source_result in run_result.source_results:
                    print_source_poll_result(source_result)
            else:
                print("no active sources")
            print(
                f"automation poll-targets run_id={run_id} status={status} "
                f"sources={run_result.source_count} results=0 "
                f"failures={run_result.failure_count} screen_actions=0"
            )
            return 1 if status in ("failed", "partial") else 0

        run_result = combine_poll_results(
            run_result=poll_sources(connection, sources=sources),
            extra_results=scope_failure_results,
        )
        ended_at = utc_now()
        status = automation_poll_status(run_result)
        failure_summary = automation_poll_failure_summary(run_result)
        with connection:
            run_id = insert_automation_run(
                connection,
                source="target_company_poll",
                scope=scope,
                status=status,
                started_at=started_at,
                ended_at=ended_at,
                result_count=run_result.result_count,
                failure_count=run_result.failure_count,
                failure_summary=failure_summary,
                action_ids=list(run_result.screen_action_ids),
                notes=automation_poll_notes(run_result),
                raw_source_reference=scope,
                now=ended_at,
            )
            append_automation_run_to_actions(
                connection,
                action_ids=run_result.screen_action_ids,
                automation_run_id=run_id,
                now=ended_at,
            )
    for source_result in run_result.source_results:
        print_source_poll_result(source_result)
    print(
        f"automation poll-targets run_id={run_id} status={status} "
        f"sources={run_result.source_count} results={run_result.result_count} "
        f"failures={run_result.failure_count} "
        f"screen_actions={len(run_result.screen_action_ids)}"
    )
    return 1 if status in ("failed", "partial") else 0


def automation_status_from_query_status(status: str) -> str:
    if status in ("completed", "failed", "partial"):
        return status
    return "planned"


def failure_summary_from_query_notes(notes: str | None) -> str | None:
    if not notes:
        return None
    match = re.search(r"\bfailure_class=([a-z0-9_]+)", notes)
    if match:
        return match.group(1)
    return None


def command_automation_prepare_query_run(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    pack = get_query_pack(args.pack)
    reason = validate_query_pack_run(pack, args.reason)
    payload = read_query_import_file(args.file)
    payload_source = payload_string(payload, "source")
    payload_pack = payload_string(payload, "pack")
    if payload_source and payload_source != args.source:
        raise ValueError(
            f"automation prepare-query-run source mismatch: "
            f"--source {args.source} but payload source is {payload_source}"
        )
    if payload_pack and payload_pack.strip().upper() != pack.name:
        raise ValueError(
            f"automation prepare-query-run pack mismatch: "
            f"--pack {pack.name} but payload pack is {payload_pack}"
        )
    payload["source"] = args.source
    payload["pack"] = pack.name
    notes = payload_string(payload, "notes")
    evidence_notes = ["prepared query run; human review required before accepting jobs"]
    if reason:
        evidence_notes.append(f"reason={reason}")
    if notes:
        evidence_notes.append(notes)
    payload["notes"] = "; ".join(evidence_notes)

    now = utc_now()
    started_at = args.started_at or now
    ended_at = args.ended_at or now
    with closing(connect(db_path)) as connection:
        with connection:
            outcome = import_query_run_payload(connection, payload, now=now)
            status = automation_status_from_query_status(outcome.status)
            failure_count = args.failure_count
            if status in ("failed", "partial") and failure_count == 0:
                failure_count = 1
            failure_summary = args.failure_summary
            if status in ("failed", "partial") and not failure_summary:
                failure_summary = (
                    failure_summary_from_query_notes(payload_string(payload, "notes"))
                    or f"query_run_status={outcome.status}"
                )
            recovery_status = args.recovery_status or automation_recovery_default(status)
            validate_automation_recovery_status(status, recovery_status)
            validate_automation_failure_evidence(
                status,
                failure_count=failure_count,
                failure_summary=failure_summary,
                recovery_notes=args.recovery_notes,
            )
            automation_run_id = insert_automation_run(
                connection,
                source=args.source,
                scope=pack.name,
                status=status,
                started_at=started_at,
                ended_at=ended_at,
                result_count=outcome.result_count,
                failure_count=failure_count,
                failure_summary=failure_summary,
                query_run_ids=[outcome.query_run_id],
                created_query_run_count=1 if outcome.import_state == "created" else 0,
                notes="prepared query run only; accepted-job creation remains manual",
                recovery_status=recovery_status,
                recovery_notes=args.recovery_notes,
                raw_source_reference=outcome.raw_source_reference,
                now=now,
            )

    print_query_import_outcome(outcome)
    print(
        f"automation query run prepared id={automation_run_id} "
        f"source={args.source} pack={pack.name} status={status} "
        f"query_run_id={outcome.query_run_id} recovery={recovery_status}"
    )
    return 0


def automation_rows(
    connection: sqlite3.Connection,
    *,
    status: str | None,
    review_only: bool,
    limit: int,
) -> list[sqlite3.Row]:
    predicates: list[str] = []
    params: list[object] = []
    if review_only:
        predicates.append("status IN ('failed', 'partial')")
        predicates.append("recovery_status IN ('unresolved', 'retry_ready')")
    if status:
        predicates.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
    params.append(limit)
    return connection.execute(
        f"""
        SELECT *
        FROM automation_runs
        {where}
        ORDER BY started_at DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def command_automation_list(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        rows = automation_rows(
            connection,
            status=args.status,
            review_only=False,
            limit=args.limit,
        )
    for row in rows:
        print_automation_run(row)
    if not rows:
        print("no automation runs")
    return 0


def command_automation_review(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        rows = automation_rows(
            connection,
            status=args.status,
            review_only=True,
            limit=args.limit,
        )
    if not rows:
        print("no automation runs need recovery")
        return 0
    for row in rows:
        print_automation_run(row)
        print(f"  recovery_path={automation_next_step(row)}")
    return 0


def command_automation_show(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM automation_runs WHERE id = ?",
            (args.automation_run_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"Automation run not found: {args.automation_run_id}")
    print_automation_run(row)
    print(f"Recovery: {automation_next_step(row)}")
    if row["recovery_notes"]:
        print(f"Recovery notes: {row['recovery_notes']}")
    if row["raw_source_reference"]:
        print(f"Raw source reference: {row['raw_source_reference']}")
    return 0


def command_automation_recover(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    recovery_status = {
        "retry": "retry_ready",
        "skip": "skipped",
        "resolve": "manual_resolved",
    }[args.recovery_command]
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            row = connection.execute(
                "SELECT id, status, recovery_status FROM automation_runs WHERE id = ?",
                (args.automation_run_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Automation run not found: {args.automation_run_id}")
            if row["status"] not in ("failed", "partial"):
                raise ValueError(
                    "only failed or partial automation runs can be marked for recovery"
                )
            if row["recovery_status"] in ("skipped", "manual_resolved"):
                raise ValueError(
                    "automation run recovery is already closed; record a new run "
                    "for further recovery work"
                )
            connection.execute(
                """
                UPDATE automation_runs
                SET recovery_status = ?, recovery_notes = COALESCE(?, recovery_notes),
                    updated_at = ?
                WHERE id = ?
                """,
                (recovery_status, args.notes, now, args.automation_run_id),
            )
    print(
        f"automation recovery updated id={args.automation_run_id} "
        f"recovery={recovery_status}"
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
                    screen_bucket,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    args.screen_bucket,
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
                    "screen_bucket": args.screen_bucket,
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
            screen_bucket = (
                "ready_to_apply"
                if args.status == "ready_to_apply" and job["screen_bucket"] is None
                else job["screen_bucket"]
            )
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, screen_bucket = ?, updated_at = ?
                WHERE id = ?
                """,
                (args.status, screen_bucket, now, args.job_id),
            )
            generate_job_actions(connection, job_id=args.job_id, now=now)
            event_id = log_event(
                connection,
                company_id=int(job["company_id"]),
                job_id=args.job_id,
                event_type=event_type_for_job_status(args.status),
                happened_at=args.happened_at,
                notes=args.notes
                or (
                    f"{job['status']} -> {args.status}; "
                    f"screen_bucket={screen_bucket}"
                    if screen_bucket != job["screen_bucket"]
                    else f"{job['status']} -> {args.status}"
                ),
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
                f"bucket={job['screen_bucket'] or 'unset'}",
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
    if args.screen_bucket:
        filters.append("jobs.screen_bucket = ?")
        params.append(args.screen_bucket)
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


def count_noisy_query_results(rows: list[sqlite3.Row]) -> int:
    count = 0
    for row in rows:
        haystack = " ".join(
            str(row[field]).casefold()
            for field in ("notes", "duplicate_reason")
            if row[field]
        )
        if any(marker in haystack for marker in NOISY_QUERY_RESULT_MARKERS):
            count += 1
    return count


def query_tuning_note_text(row: sqlite3.Row) -> str:
    return " ".join(
        str(row[field]).casefold()
        for field in ("result_notes", "duplicate_reason")
        if row[field]
    )


def query_tuning_marker_count(
    rows: list[sqlite3.Row],
    markers: tuple[str, ...],
) -> int:
    return sum(
        1
        for row in rows
        if any(marker in query_tuning_note_text(row) for marker in markers)
    )


def query_tuning_marker_rows(
    rows: list[sqlite3.Row],
    markers: tuple[str, ...],
) -> list[sqlite3.Row]:
    return [
        row
        for row in rows
        if any(marker in query_tuning_note_text(row) for marker in markers)
    ]


def query_tuning_samples(rows: list[sqlite3.Row], *, limit: int = 3) -> str:
    samples = []
    for row in rows:
        company = row["company_name"] or "Unknown"
        samples.append(f"{company} / {row['title']}")
        if len(samples) == limit:
            break
    return "; ".join(samples) if samples else "none"


def query_tuning_reason(row: sqlite3.Row) -> str:
    for field in ("result_notes", "duplicate_reason", "run_notes"):
        if row[field]:
            return str(row[field]).strip()
    return "reviewed query-run outcome"


def query_tuning_explicit_reason(notes: str) -> str | None:
    match = re.search(r"(?:^|[\s;])reason=([^;\n]+)", notes)
    if match is None:
        return None
    reason = match.group(1).strip()
    return f"reason={reason}" if reason else None


def query_tuning_exception_reason(rows: list[sqlite3.Row]) -> str | None:
    for row in rows:
        notes = str(row["run_notes"] or "").strip()
        reason = query_tuning_explicit_reason(notes)
        if reason:
            return reason
    return None


def format_query_tuning_line(
    *,
    pack: str,
    query: str,
    reviewed: int,
    count_name: str,
    count: int,
    rate_name: str,
    samples: str,
    action: str,
) -> str:
    return (
        f"- pack={pack} query={json.dumps(query)} reviewed={reviewed} "
        f"{count_name}={count} {rate_name}={percent(count, reviewed)} "
        f"samples={json.dumps(samples)} action={json.dumps(action)}"
    )


def strategy_feedback_artifact_target(improvement: str) -> str:
    if improvement == "application playbook":
        return "application playbook"
    if improvement == "bullet":
        return "user bullets"
    if improvement == "resume lane":
        return "resume lane"
    if improvement == "artifact":
        return "Linear follow-up"
    return "career strategy"


def strategy_feedback_query_quality(
    connection: sqlite3.Connection, *, since_text: str, until_text: str
) -> sqlite3.Row:
    return connection.execute(
        """
        SELECT
            COUNT(*) AS results,
            SUM(CASE WHEN result_status != 'pending' THEN 1 ELSE 0 END) AS reviewed,
            SUM(CASE WHEN result_status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN result_status = 'accepted' THEN 1 ELSE 0 END) AS accepted,
            SUM(CASE WHEN result_status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
            SUM(CASE WHEN result_status = 'duplicate' THEN 1 ELSE 0 END) AS duplicate,
            SUM(
                CASE
                    WHEN result_status = 'rejected'
                        AND (
                            lower(COALESCE(notes, '')) LIKE '%search_noisy%'
                            OR lower(COALESCE(notes, '')) LIKE '%malformed_payload%'
                            OR lower(COALESCE(duplicate_reason, '')) LIKE '%search_noisy%'
                            OR lower(COALESCE(duplicate_reason, '')) LIKE '%malformed_payload%'
                        )
                    THEN 1
                    ELSE 0
                END
            ) AS noisy,
            SUM(
                CASE
                    WHEN result_status = 'rejected'
                        AND (
                            lower(COALESCE(notes, '')) LIKE '%stale_or_thin_result%'
                            OR lower(COALESCE(notes, '')) LIKE '%detail_validation_failed%'
                            OR lower(COALESCE(duplicate_reason, '')) LIKE '%stale_or_thin_result%'
                            OR lower(COALESCE(duplicate_reason, '')) LIKE '%detail_validation_failed%'
                        )
                    THEN 1
                    ELSE 0
                END
            ) AS stale_thin
        FROM query_run_results
        WHERE updated_at >= ?
            AND updated_at < ?
        """,
        (since_text, until_text),
    ).fetchone()


def strategy_feedback_top_query(
    connection: sqlite3.Connection, *, status: str, since_text: str, until_text: str
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT query_runs.pack, query_runs.query_text, COUNT(*) AS count
        FROM query_run_results
        JOIN query_runs ON query_runs.id = query_run_results.query_run_id
        WHERE query_run_results.result_status = ?
            AND query_run_results.updated_at >= ?
            AND query_run_results.updated_at < ?
        GROUP BY query_runs.pack, query_runs.query_text
        ORDER BY count DESC, query_runs.pack, query_runs.query_text
        LIMIT 1
        """,
        (status, since_text, until_text),
    ).fetchone()


def strategy_feedback_target_coverage(
    connection: sqlite3.Connection, *, stale_before_text: str
) -> sqlite3.Row:
    return connection.execute(
        f"""
        SELECT
            COUNT(*) AS active_targets,
            SUM(CASE WHEN active_sources.company_id IS NOT NULL THEN 1 ELSE 0 END)
                AS with_active_sources,
            SUM(CASE WHEN active_sources.company_id IS NULL THEN 1 ELSE 0 END)
                AS missing_active_sources,
            SUM(
                CASE
                    WHEN active_sources.company_id IS NULL
                        AND (companies.career_url IS NULL OR companies.career_url = '')
                    THEN 1
                    ELSE 0
                END
            ) AS missing_source_details,
            SUM(
                CASE
                    WHEN active_sources.company_id IS NULL
                        AND companies.career_url IS NOT NULL
                        AND companies.career_url != ''
                    THEN 1
                    ELSE 0
                END
            ) AS official_fallback_only,
            SUM(
                CASE
                    WHEN companies.ats_type IS NOT NULL
                        AND companies.ats_type != ''
                        AND lower(companies.ats_type) NOT IN ({", ".join("?" for _ in ATS_TYPES)})
                    THEN 1
                    ELSE 0
                END
            ) AS unsupported_sources,
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
        (*ATS_TYPES, stale_before_text),
    ).fetchone()


def format_strategy_feedback_recommendation(
    decision: str,
    *,
    target: str,
    evidence: str,
    recommendation: str,
    operator_action: str,
) -> str:
    return (
        f"- decision={decision} | target={target} | evidence={evidence} | "
        f"recommendation={recommendation} | operator_action={operator_action}"
    )


def command_report_strategy_feedback(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_current_database_read_only(db_path)
    as_of = parse_report_as_of(args.as_of)
    if args.days <= 0:
        raise ValueError("report strategy-feedback --days must be a positive integer")
    if args.limit <= 0:
        raise ValueError("report strategy-feedback --limit must be a positive integer")

    since = as_of - timedelta(days=args.days)
    since_text = since.isoformat()
    as_of_text = as_of.isoformat()
    stale_before_text = (as_of - timedelta(days=14)).isoformat()

    with closing(connect(db_path)) as connection:
        record_count = command_center_record_count(connection)
        outcome_rows = connection.execute(
            """
            SELECT
                COUNT(*) AS total_jobs,
                SUM(CASE WHEN application_outcome IS NOT NULL THEN 1 ELSE 0 END)
                    AS outcome_classified,
                SUM(CASE WHEN application_outcome = 'pending_response' THEN 1 ELSE 0 END)
                    AS pending_response,
                SUM(CASE WHEN application_outcome = 'active_interview_loop' THEN 1 ELSE 0 END)
                    AS active_interview_loop,
                SUM(CASE WHEN application_outcome LIKE 'rejected_%' THEN 1 ELSE 0 END)
                    AS rejected,
                SUM(CASE WHEN rejection_reason = 'missing_proof' THEN 1 ELSE 0 END)
                    AS missing_proof,
                SUM(CASE WHEN rejection_reason = 'low_interest' THEN 1 ELSE 0 END)
                    AS low_interest,
                SUM(CASE WHEN rejection_reason = 'recruiter_screen_risk' THEN 1 ELSE 0 END)
                    AS recruiter_screen_risk
            FROM jobs
            """
        ).fetchone()
        funnel = connection.execute(
            """
            SELECT
                SUM(CASE WHEN queue = 'screen' AND status = 'done' THEN 1 ELSE 0 END)
                    AS screens_done,
                SUM(CASE WHEN queue = 'apply' AND status = 'done' THEN 1 ELSE 0 END)
                    AS apply_actions_done
            FROM actions
            WHERE COALESCE(completed_at, updated_at) >= ?
                AND COALESCE(completed_at, updated_at) < ?
            """,
            (since_text, as_of_text),
        ).fetchone()
        event_counts = connection.execute(
            """
            SELECT
                SUM(CASE WHEN event_type = 'application_submitted' THEN 1 ELSE 0 END)
                    AS applications_submitted,
                SUM(CASE WHEN event_type = 'interview' THEN 1 ELSE 0 END)
                    AS interviews,
                SUM(CASE WHEN event_type = 'rejection_received' THEN 1 ELSE 0 END)
                    AS rejections
            FROM events
            WHERE happened_at >= ?
                AND happened_at < ?
            """,
            (since_text, as_of_text),
        ).fetchone()
        target_coverage = strategy_feedback_target_coverage(
            connection, stale_before_text=stale_before_text
        )
        query_quality = strategy_feedback_query_quality(
            connection, since_text=since_text, until_text=as_of_text
        )
        top_accepted_query = strategy_feedback_top_query(
            connection,
            status="accepted",
            since_text=since_text,
            until_text=as_of_text,
        )
        top_rejected_query = strategy_feedback_top_query(
            connection,
            status="rejected",
            since_text=since_text,
            until_text=as_of_text,
        )
        cooldowns = grouped_cooldown_recommendations(
            evidence_rows=cooldown_evidence_rows(connection, as_of=as_of),
            as_of=as_of,
            limit=args.limit,
        )
        proof_groups = group_proof_gap_evidence(proof_gap_evidence(connection))

    temporary_cooldowns = [
        item for item in cooldowns if item.recommendation_type == "temporary"
    ]
    durable_cooldowns = [
        item for item in cooldowns if item.recommendation_type == "durable"
    ]
    recurring_proof_groups = [
        group for group in proof_groups if proof_gap_strength(group) != "one_off"
    ]
    one_off_proof_groups = [
        group for group in proof_groups if proof_gap_strength(group) == "one_off"
    ]

    print(f"Strategy feedback report as_of={as_of.isoformat()} window_days={args.days}")
    print(
        "Mode: advisory read-only; document, config, and Linear changes remain operator-controlled."
    )
    print(
        "Workflow boundary: command-center strategy review only; route discovery to "
        "$job-search and ready-JD application materials to $job-apply."
    )
    if record_count == 0:
        print("No command center data.")
        print("Evidence:")
        print("- outcomes: none")
        print("- funnel_metrics: none")
        print("- cooldowns: none")
        print("- proof_gaps: none")
        print("- target_company_coverage: none")
        print("- query_quality: none")
        print("Recommendations:")
        print("Keep:")
        print("- none")
        print("Change:")
        print("- none")
        print("Defer:")
        print("- none")
        return 0

    applications = event_counts["applications_submitted"] or 0
    interviews = event_counts["interviews"] or 0
    rejections = event_counts["rejections"] or 0
    query_results = query_quality["results"] or 0
    query_reviewed = query_quality["reviewed"] or 0
    query_pending = query_quality["pending"] or 0
    query_accepted = query_quality["accepted"] or 0
    query_rejected = query_quality["rejected"] or 0
    query_duplicate = query_quality["duplicate"] or 0
    query_noisy = query_quality["noisy"] or 0
    query_stale_thin = query_quality["stale_thin"] or 0
    active_targets = target_coverage["active_targets"] or 0
    targets_with_sources = target_coverage["with_active_sources"] or 0
    targets_missing_sources = target_coverage["missing_active_sources"] or 0
    targets_missing_details = target_coverage["missing_source_details"] or 0
    targets_fallback_only = target_coverage["official_fallback_only"] or 0
    targets_unsupported = target_coverage["unsupported_sources"] or 0
    targets_stale = target_coverage["stale_checks"] or 0

    print("Evidence:")
    print(
        "- outcomes: "
        f"jobs={outcome_rows['total_jobs'] or 0} "
        f"outcome_classified={outcome_rows['outcome_classified'] or 0} "
        f"pending_response={outcome_rows['pending_response'] or 0} "
        f"active_interview_loop={outcome_rows['active_interview_loop'] or 0} "
        f"rejected={outcome_rows['rejected'] or 0} "
        f"missing_proof={outcome_rows['missing_proof'] or 0} "
        f"low_interest={outcome_rows['low_interest'] or 0} "
        f"recruiter_screen_risk={outcome_rows['recruiter_screen_risk'] or 0}"
    )
    print(
        "- funnel_metrics: "
        f"screens_done={funnel['screens_done'] or 0} "
        f"apply_actions_done={funnel['apply_actions_done'] or 0} "
        f"applications_submitted={applications} interviews={interviews} "
        f"rejections={rejections} interview_rate={percent(interviews, applications)} "
        f"rejection_rate={percent(rejections, applications)}"
    )
    print(
        "- cooldowns: "
        f"temporary={len(temporary_cooldowns)} durable={len(durable_cooldowns)} "
        f"top={cooldowns[0].target_label if cooldowns else 'none'}"
    )
    print(
        "- proof_gaps: "
        f"groups={len(proof_groups)} recurring={len(recurring_proof_groups)} "
        f"one_off={len(one_off_proof_groups)} "
        f"top={proof_groups[0].label if proof_groups else 'none'}"
    )
    print(
        "- target_company_coverage: "
        f"active_targets={active_targets} with_active_sources={targets_with_sources} "
        f"missing_active_sources={targets_missing_sources} "
        f"missing_source_details={targets_missing_details} "
        f"official_fallback_only={targets_fallback_only} "
        f"unsupported_sources={targets_unsupported} stale_checks={targets_stale}"
    )
    accepted_query_label = (
        f"{top_accepted_query['pack']}:{top_accepted_query['query_text']}"
        if top_accepted_query
        else "none"
    )
    rejected_query_label = (
        f"{top_rejected_query['pack']}:{top_rejected_query['query_text']}"
        if top_rejected_query
        else "none"
    )
    print(
        "- query_quality: "
        f"results={query_results} reviewed={query_reviewed} pending={query_pending} "
        f"accepted={query_accepted} rejected={query_rejected} "
        f"duplicate={query_duplicate} noisy={query_noisy} "
        f"stale_thin={query_stale_thin} "
        f"top_accepted_query={json.dumps(accepted_query_label)} "
        f"top_rejected_query={json.dumps(rejected_query_label)}"
    )

    keep: list[str] = []
    change: list[str] = []
    defer: list[str] = []

    if top_accepted_query:
        keep.append(
            format_strategy_feedback_recommendation(
                "keep",
                target="query-pack config",
                evidence=(
                    f"accepted={top_accepted_query['count']} "
                    f"pack={top_accepted_query['pack']} "
                    f"query={json.dumps(top_accepted_query['query_text'])}"
                ),
                recommendation="preserve this query pattern in the next search cycle",
                operator_action="review before editing config/job_search_query_packs.json",
            )
        )
    if active_targets > 0:
        keep.append(
            format_strategy_feedback_recommendation(
                "keep",
                target="product strategy",
                evidence=(
                    f"active_targets={active_targets} "
                    f"with_active_sources={targets_with_sources} "
                    f"missing_active_sources={targets_missing_sources}"
                ),
                recommendation="keep target-company coverage in the weekly learning loop",
                operator_action=(
                    "update docs/PRODUCT_STRATEGY.md only if coverage goals or "
                    "company-first workflow priorities change"
                ),
            )
        )
    if applications > 0 or interviews > 0:
        keep.append(
            format_strategy_feedback_recommendation(
                "keep",
                target="career strategy",
                evidence=f"applications_submitted={applications} interviews={interviews}",
                recommendation="keep the current apply-through loop visible in weekly review",
                operator_action="update career strategy only if this becomes a durable priority",
            )
        )

    if query_noisy > 0 or query_stale_thin > 0:
        change.append(
            format_strategy_feedback_recommendation(
                "change",
                target="query-pack config",
                evidence=(
                    f"noisy={query_noisy} stale_thin={query_stale_thin} "
                    f"top_rejected_query={json.dumps(rejected_query_label)}"
                ),
                recommendation="tighten noisy queries or prefer canonical/official sources",
                operator_action="edit config only after reviewing query-pack-tuning evidence",
            )
        )
    if targets_missing_sources > 0 or targets_stale > 0:
        change.append(
            format_strategy_feedback_recommendation(
                "change",
                target="career strategy",
                evidence=(
                    f"missing_active_sources={targets_missing_sources} "
                    f"stale_checks={targets_stale}"
                ),
                recommendation="prioritize source coverage for active target companies",
                operator_action="create explicit research/source actions before changing strategy docs",
            )
        )
    if temporary_cooldowns:
        first = temporary_cooldowns[0]
        change.append(
            format_strategy_feedback_recommendation(
                "change",
                target="career strategy",
                evidence=(
                    f"cooldown={first.target_label} signal={first.signal} "
                    f"next_review={first.next_review_at}"
                ),
                recommendation="reduce near-term effort on cooled targets or role patterns",
                operator_action="reschedule actions manually if the evidence still applies",
            )
        )
    if recurring_proof_groups:
        group = recurring_proof_groups[0]
        improvement = recommend_proof_gap_improvement(group)
        change.append(
            format_strategy_feedback_recommendation(
                "change",
                target=strategy_feedback_artifact_target(improvement),
                evidence=(
                    f"proof_gap={group.label} strength={proof_gap_strength(group)} "
                    f"jobs={len(group.job_ids)} companies={len(group.company_ids)}"
                ),
                recommendation=(
                    "promote recurring proof gap into artifact work"
                    if improvement == "artifact"
                    else f"promote recurring proof gap into a {improvement} update"
                ),
                operator_action="make the doc/config/issue change explicitly after review",
            )
        )

    if durable_cooldowns:
        first = durable_cooldowns[0]
        defer.append(
            format_strategy_feedback_recommendation(
                "defer",
                target="career strategy",
                evidence=(
                    f"durable_cooldown={first.target_label} "
                    f"signal={first.signal} next_review={first.next_review_at}"
                ),
                recommendation="defer renewed effort until the review date or target criteria change",
                operator_action="leave company/job changes under operator control",
            )
        )
    if one_off_proof_groups:
        group = one_off_proof_groups[0]
        defer.append(
            format_strategy_feedback_recommendation(
                "defer",
                target="Linear follow-up",
                evidence=(
                    f"proof_gap={group.label} strength=one_off "
                    f"evidence={len(group.evidence)}"
                ),
                recommendation="do not create larger proof-building work until the pattern repeats",
                operator_action="keep evidence in command-center state for now",
            )
        )
    if query_pending > query_reviewed:
        defer.append(
            format_strategy_feedback_recommendation(
                "defer",
                target="query-pack config",
                evidence=f"pending={query_pending} reviewed={query_reviewed}",
                recommendation="defer pack edits until pending/raw hits are reviewed",
                operator_action="review query_run_results before changing config",
            )
        )

    print("Recommendations:")
    print("Keep:")
    for line in keep[: args.limit]:
        print(line)
    if not keep:
        print("- none")
    print("Change:")
    for line in change[: args.limit]:
        print(line)
    if not change:
        print("- none")
    print("Defer:")
    for line in defer[: args.limit]:
        print(line)
    if not defer:
        print("- none")
    return 0


def command_report_query_pack_tuning(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_current_database_read_only(db_path)
    if args.limit <= 0:
        raise ValueError("report query-pack-tuning --limit must be a positive integer")

    packs = load_query_pack_registry()
    with closing(connect(db_path)) as connection:
        reviewed_rows = connection.execute(
            """
            SELECT query_runs.id AS query_run_id, query_runs.source,
                query_runs.pack, query_runs.query_text, query_runs.notes AS run_notes,
                query_run_results.company_name, query_run_results.title,
                query_run_results.result_status,
                query_run_results.duplicate_reason,
                query_run_results.notes AS result_notes
            FROM query_run_results
            JOIN query_runs ON query_runs.id = query_run_results.query_run_id
            WHERE query_run_results.result_status != 'pending'
            ORDER BY query_runs.pack, query_runs.query_text,
                query_run_results.ordinal, query_run_results.id
            """
        ).fetchall()
        pending_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM query_run_results
            WHERE result_status = 'pending'
            """
        ).fetchone()[0]

    print("Query-pack tuning report")
    print(
        f"Basis: reviewed query_run_results only | reviewed={len(reviewed_rows)} "
        f"pending_ignored={pending_count}"
    )
    print(
        "Source-quality boundary: source-quality reasons stay in "
        "query_run_results.notes and are not job rejection taxonomy."
    )
    print("Config: read-only; config/job_search_query_packs.json was not edited.")
    if not reviewed_rows:
        print("No reviewed query-run results.")
        print("Next step: review query_run_results before tuning packs.")
        return 0

    grouped: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in reviewed_rows:
        pack = str(row["pack"] or "unset")
        grouped.setdefault((pack, str(row["query_text"])), []).append(row)

    summaries: list[dict[str, object]] = []
    for (pack_name, query_text), rows in grouped.items():
        reviewed = len(rows)
        accepted_rows = [row for row in rows if row["result_status"] == "accepted"]
        rejected_rows = [row for row in rows if row["result_status"] == "rejected"]
        duplicate_rows = [row for row in rows if row["result_status"] == "duplicate"]
        noisy_count = query_tuning_marker_count(rows, QUERY_TUNING_NOISY_MARKERS)
        noisy_rows = query_tuning_marker_rows(rows, QUERY_TUNING_NOISY_MARKERS)
        stale_thin_count = query_tuning_marker_count(
            rows, QUERY_TUNING_STALE_THIN_MARKERS
        )
        stale_thin_rows = query_tuning_marker_rows(
            rows, QUERY_TUNING_STALE_THIN_MARKERS
        )
        pack = packs.get(pack_name)
        summaries.append(
            {
                "pack": pack_name,
                "query": query_text,
                "pack_type": pack.pack_type if pack else "unknown",
                "reviewed": reviewed,
                "accepted_rows": accepted_rows,
                "rejected_rows": rejected_rows,
                "duplicate_rows": duplicate_rows,
                "noisy_count": noisy_count,
                "noisy_rows": noisy_rows,
                "stale_thin_count": stale_thin_count,
                "stale_thin_rows": stale_thin_rows,
                "rows": rows,
                "exception_reason": (
                    query_tuning_exception_reason(rows)
                    if pack and pack.pack_type == "exception"
                    else None
                ),
            }
        )

    def limited(items: list[dict[str, object]]) -> list[dict[str, object]]:
        return items[: args.limit]

    def candidate_edit_count(item: dict[str, object]) -> int:
        duplicate_rows = item["duplicate_rows"]
        accepted_rows = item["accepted_rows"]
        assert isinstance(duplicate_rows, list)
        assert isinstance(accepted_rows, list)
        return (
            int(item["noisy_count"])
            + int(item["stale_thin_count"])
            + len(duplicate_rows)
            + len(accepted_rows)
        )

    print("Noisy queries:")
    noisy = sorted(
        (item for item in summaries if int(item["noisy_count"]) > 0),
        key=lambda item: (-int(item["noisy_count"]), str(item["pack"]), str(item["query"])),
    )
    if noisy:
        for item in limited(noisy):
            rows = item["rows"]
            assert isinstance(rows, list)
            noisy_rows = item["noisy_rows"]
            assert isinstance(noisy_rows, list)
            print(
                format_query_tuning_line(
                    pack=str(item["pack"]),
                    query=str(item["query"]),
                    reviewed=int(item["reviewed"]),
                    count_name="noisy",
                    count=int(item["noisy_count"]),
                    rate_name="noisy_rate",
                    samples=query_tuning_samples(noisy_rows),
                    action="tighten query terms or pause broad source pattern",
                )
            )
    else:
        print("- none")

    print("Stale/thin sources:")
    stale = sorted(
        (item for item in summaries if int(item["stale_thin_count"]) > 0),
        key=lambda item: (
            -int(item["stale_thin_count"]),
            str(item["pack"]),
            str(item["query"]),
        ),
    )
    if stale:
        for item in limited(stale):
            rows = item["rows"]
            assert isinstance(rows, list)
            stale_thin_rows = item["stale_thin_rows"]
            assert isinstance(stale_thin_rows, list)
            print(
                format_query_tuning_line(
                    pack=str(item["pack"]),
                    query=str(item["query"]),
                    reviewed=int(item["reviewed"]),
                    count_name="stale_thin",
                    count=int(item["stale_thin_count"]),
                    rate_name="stale_thin_rate",
                    samples=query_tuning_samples(stale_thin_rows),
                    action="validate canonical postings or prefer ATS/official sources",
                )
            )
    else:
        print("- none")

    print("Duplicate patterns:")
    duplicates = sorted(
        (item for item in summaries if len(item["duplicate_rows"]) > 0),
        key=lambda item: (
            -len(item["duplicate_rows"]),
            str(item["pack"]),
            str(item["query"]),
        ),
    )
    if duplicates:
        for item in limited(duplicates):
            duplicate_rows = item["duplicate_rows"]
            assert isinstance(duplicate_rows, list)
            reason = query_tuning_reason(duplicate_rows[0])
            print(
                format_query_tuning_line(
                    pack=str(item["pack"]),
                    query=str(item["query"]),
                    reviewed=int(item["reviewed"]),
                    count_name="duplicates",
                    count=len(duplicate_rows),
                    rate_name="duplicate_rate",
                    samples=query_tuning_samples(duplicate_rows),
                    action=f"dedupe by existing roles; reason={reason}",
                )
            )
    else:
        print("- none")

    print("Strong accepted patterns:")
    accepted = sorted(
        (item for item in summaries if len(item["accepted_rows"]) > 0),
        key=lambda item: (
            -len(item["accepted_rows"]),
            str(item["pack"]),
            str(item["query"]),
        ),
    )
    if accepted:
        for item in limited(accepted):
            accepted_rows = item["accepted_rows"]
            assert isinstance(accepted_rows, list)
            print(
                format_query_tuning_line(
                    pack=str(item["pack"]),
                    query=str(item["query"]),
                    reviewed=int(item["reviewed"]),
                    count_name="accepted",
                    count=len(accepted_rows),
                    rate_name="accepted_rate",
                    samples=query_tuning_samples(accepted_rows),
                    action="preserve or expand this query pattern",
                )
            )
    else:
        print("- none")

    print("Candidate pack edits:")
    edit_count = 0
    candidate_edits = sorted(
        (item for item in summaries if candidate_edit_count(item) > 0),
        key=lambda item: (
            -candidate_edit_count(item),
            str(item["pack"]),
            str(item["query"]),
        ),
    )
    for item in limited(candidate_edits):
        pack_name = str(item["pack"])
        query_text = str(item["query"])
        if int(item["noisy_count"]) > 0:
            noisy_rows = item["noisy_rows"]
            assert isinstance(noisy_rows, list)
            edit_count += 1
            print(
                f"- pack={pack_name} query={json.dumps(query_text)} "
                "edit=tighten_or_pause "
                f"reason={json.dumps(query_tuning_reason(noisy_rows[0]))}"
            )
        if int(item["stale_thin_count"]) > 0:
            stale_thin_rows = item["stale_thin_rows"]
            assert isinstance(stale_thin_rows, list)
            edit_count += 1
            print(
                f"- pack={pack_name} query={json.dumps(query_text)} "
                "edit=prefer_canonical_or_official_source "
                f"reason={json.dumps(query_tuning_reason(stale_thin_rows[0]))}"
            )
        duplicate_rows = item["duplicate_rows"]
        assert isinstance(duplicate_rows, list)
        if duplicate_rows:
            edit_count += 1
            print(
                f"- pack={pack_name} query={json.dumps(query_text)} "
                "edit=dedupe_or_reduce_overlap "
                f"reason={json.dumps(query_tuning_reason(duplicate_rows[0]))}"
            )
        accepted_rows = item["accepted_rows"]
        assert isinstance(accepted_rows, list)
        if accepted_rows:
            edit_count += 1
            print(
                f"- pack={pack_name} query={json.dumps(query_text)} "
                "edit=preserve_or_expand "
                f"reason={json.dumps(query_tuning_reason(accepted_rows[0]))}"
            )
    exception_guardrails = sorted(
        (item for item in summaries if item["pack_type"] == "exception"),
        key=lambda item: (str(item["pack"]), str(item["query"])),
    )
    for item in exception_guardrails:
        pack_name = str(item["pack"])
        query_text = str(item["query"])
        reason = item["exception_reason"]
        if reason:
            action = f"preserve explicit exception reason: {reason}"
        else:
            action = "do not promote or repeat until an explicit exception reason is recorded"
        edit_count += 1
        print(
            f"- pack={pack_name} query={json.dumps(query_text)} "
            "edit=preserve_exception_guardrail "
            f"reason={json.dumps(action)}"
        )
    if edit_count == 0:
        print("- none")
    return 0


def read_draft_body(args: argparse.Namespace) -> str:
    if bool(args.body) == bool(args.body_file):
        raise ValueError("provide exactly one of --body or --body-file")
    if args.body:
        return args.body
    return Path(args.body_file).read_text(encoding="utf-8").strip()


def command_draft_add(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    now = utc_now()
    body = read_draft_body(args)
    if not body:
        raise ValueError("draft body cannot be empty")
    if not any(
        value is not None
        for value in (args.job_id, args.contact_id, args.artifact_id, args.action_id)
    ):
        raise ValueError(
            "draft requires at least one source link: --job-id, --contact-id, "
            "--artifact-id, or --action-id"
        )
    with closing(connect(db_path)) as connection:
        with connection:
            company_id = resolve_company_id(connection, args.company)
            company = require_row(
                connection,
                "SELECT id, name FROM companies WHERE id = ?",
                (company_id,),
                f"Company not found: {args.company}",
            )
            job = None
            if args.job_id is not None:
                job = require_row(
                    connection,
                    """
                    SELECT id, title, application_folder
                    FROM jobs
                    WHERE id = ? AND company_id = ?
                    """,
                    (args.job_id, company_id),
                    f"job not found for company: {args.job_id}",
                )
            if args.contact_id is not None:
                require_row(
                    connection,
                    "SELECT id FROM contacts WHERE id = ? AND company_id = ?",
                    (args.contact_id, company_id),
                    f"contact not found for company: {args.contact_id}",
                )
            if args.artifact_id is not None:
                require_row(
                    connection,
                    "SELECT id FROM artifacts WHERE id = ? AND company_id = ?",
                    (args.artifact_id, company_id),
                    f"artifact not found for company: {args.artifact_id}",
                )
            if args.action_id is not None:
                require_row(
                    connection,
                    "SELECT id FROM actions WHERE id = ? AND company_id = ?",
                    (args.action_id, company_id),
                    f"action not found for company: {args.action_id}",
                )
            if args.path:
                validate_draft_path(
                    args.path,
                    db_path=db_path,
                    job_application_folder=str(job["application_folder"])
                    if job and job["application_folder"]
                    else None,
                )
            cursor = connection.execute(
                """
                INSERT INTO drafts(
                    company_id, job_id, contact_id, artifact_id, action_id,
                    draft_type, status, title, body, path, source_summary,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    args.job_id,
                    args.contact_id,
                    args.artifact_id,
                    args.action_id,
                    args.type,
                    args.title,
                    body,
                    args.path,
                    args.source_summary,
                    now,
                    now,
                ),
            )
            draft_id = int(cursor.lastrowid)
            log_event(
                connection,
                company_id=company_id,
                job_id=args.job_id,
                contact_id=args.contact_id,
                artifact_id=args.artifact_id,
                action_id=args.action_id,
                event_type="draft_created",
                happened_at=args.happened_at or now,
                notes=(
                    f"draft=#{draft_id} type={args.type} status=draft "
                    f"review_only=unsent_unsubmitted approval_required=true"
                    + (f" path={args.path}" if args.path else "")
                ),
            )
            if args.path:
                write_draft_file(
                    path_text=args.path,
                    draft_type=args.type,
                    title=args.title,
                    body=body,
                    company_name=str(company["name"]),
                    job_title=str(job["title"]) if job else None,
                    source_summary=args.source_summary,
                    action_id=args.action_id,
                    contact_id=args.contact_id,
                    artifact_id=args.artifact_id,
                )
    print(
        f"draft created id={draft_id} type={args.type} status=draft "
        "review_only=unsent_unsubmitted approval_required=before_external_side_effect"
        + (f" path={args.path}" if args.path else "")
    )
    return 0


def draft_rows(
    connection: sqlite3.Connection,
    *,
    company_id: int | None,
    status: str | None,
    limit: int,
) -> list[sqlite3.Row]:
    predicates: list[str] = []
    params: list[object] = []
    if company_id is not None:
        predicates.append("drafts.company_id = ?")
        params.append(company_id)
    if status is not None:
        predicates.append("drafts.status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
    params.append(limit)
    return connection.execute(
        f"""
        SELECT drafts.*, companies.name AS company_name, jobs.title AS job_title,
            contacts.name AS contact_name, artifacts.type AS artifact_type,
            actions.kind AS action_kind
        FROM drafts
        JOIN companies ON companies.id = drafts.company_id
        LEFT JOIN jobs ON jobs.id = drafts.job_id
        LEFT JOIN contacts ON contacts.id = drafts.contact_id
        LEFT JOIN artifacts ON artifacts.id = drafts.artifact_id
        LEFT JOIN actions ON actions.id = drafts.action_id
        {where}
        ORDER BY drafts.updated_at DESC, drafts.id DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()


def command_draft_list(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    with closing(connect(db_path)) as connection:
        company_id = resolve_company_id(connection, args.company) if args.company else None
        rows = draft_rows(
            connection,
            company_id=company_id,
            status=args.status,
            limit=args.limit,
        )
    if not rows:
        print("no drafts")
        return 0
    for row in rows:
        print(render_draft(row))
    return 0


def command_draft_status(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
    now = utc_now()
    event_type = "draft_revised" if args.status == "needs_revision" else "draft_rejected"
    if args.status == "approved":
        event_type = "status_changed"
    with closing(connect(db_path)) as connection:
        with connection:
            row = require_row(
                connection,
                "SELECT * FROM drafts WHERE id = ?",
                (args.draft_id,),
                f"Draft not found: {args.draft_id}",
            )
            connection.execute(
                """
                UPDATE drafts
                SET status = ?, approval_note = ?, updated_at = ?
                WHERE id = ?
                """,
                (args.status, args.notes, now, args.draft_id),
            )
            log_event(
                connection,
                company_id=int(row["company_id"]),
                job_id=row["job_id"],
                contact_id=row["contact_id"],
                artifact_id=row["artifact_id"],
                action_id=row["action_id"],
                event_type=event_type,
                happened_at=args.happened_at or now,
                notes=(
                    f"draft=#{args.draft_id} status={args.status} "
                    "source_context_preserved=true external_side_effect=false"
                    + (f" notes={args.notes}" if args.notes else "")
                ),
            )
    print(f"draft id={args.draft_id} status={args.status} external_side_effect=false")
    return 0


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
            JOIN jobs ON jobs.id = events.job_id
            WHERE events.job_id IS NOT NULL
                AND event_type = 'status_changed'
                AND (
                    notes LIKE '%screen_bucket=ready_to_apply%'
                    OR notes LIKE '%screen_bucket=low_effort_apply%'
                    OR notes LIKE '%ready_to_apply%'
                )
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
        job_status_rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM jobs
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
        resolved_jobs = connection.execute(
            """
            SELECT COUNT(*)
            FROM jobs
            WHERE screen_bucket IS NOT NULL
            """,
        ).fetchone()[0]
        unresolved_jobs = connection.execute(
            """
            SELECT COUNT(*)
            FROM jobs
            WHERE screen_bucket IS NULL
                AND status IN ('discovered', 'screening')
            """,
        ).fetchone()[0]
        screen_bucket_rows = connection.execute(
            """
            SELECT screen_bucket, COUNT(*) AS count
            FROM jobs
            WHERE screen_bucket IS NOT NULL
            GROUP BY screen_bucket
            ORDER BY screen_bucket
            """
        ).fetchall()
        high_signal_jobs = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM jobs
            WHERE status IN ({", ".join("?" for _ in HIGH_SIGNAL_JOB_STATUSES)})
                OR screen_bucket IN ('ready_to_apply', 'low_effort_apply')
            """,
            HIGH_SIGNAL_JOB_STATUSES,
        ).fetchone()[0]
        query_quality = connection.execute(
            """
            SELECT
                COUNT(*) AS results,
                SUM(CASE WHEN query_run_results.result_status != 'pending' THEN 1 ELSE 0 END)
                    AS reviewed,
                SUM(CASE WHEN query_run_results.result_status = 'pending' THEN 1 ELSE 0 END)
                    AS pending,
                SUM(CASE WHEN query_run_results.result_status = 'accepted' THEN 1 ELSE 0 END)
                    AS accepted,
                SUM(CASE WHEN query_run_results.result_status = 'rejected' THEN 1 ELSE 0 END)
                    AS rejected,
                SUM(CASE WHEN query_run_results.result_status = 'duplicate' THEN 1 ELSE 0 END)
                    AS duplicate
            FROM query_run_results
            JOIN query_runs ON query_runs.id = query_run_results.query_run_id
            WHERE query_run_results.updated_at >= ?
                AND query_run_results.updated_at < ?
            """,
            (since_text, until_text),
        ).fetchone()
        accepted_high_signal_results = connection.execute(
            f"""
            SELECT COUNT(*) AS accepted,
                SUM(
                    CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM jobs
                            JOIN companies ON companies.id = jobs.company_id
                            WHERE (
                                    jobs.status IN ({", ".join("?" for _ in HIGH_SIGNAL_JOB_STATUSES)})
                                    OR jobs.screen_bucket IN ('ready_to_apply', 'low_effort_apply')
                                )
                                AND (
                                    (
                                        query_run_results.canonical_url IS NOT NULL
                                        AND jobs.canonical_url = query_run_results.canonical_url
                                    )
                                    OR (
                                        query_run_results.source_job_id IS NOT NULL
                                        AND jobs.source = query_runs.source
                                        AND jobs.source_job_id = query_run_results.source_job_id
                                    )
                                )
                        )
                        THEN 1
                        ELSE 0
                    END
                ) AS matched
            FROM query_run_results
            JOIN query_runs ON query_runs.id = query_run_results.query_run_id
            WHERE query_run_results.result_status = 'accepted'
                AND query_run_results.updated_at >= ?
                AND query_run_results.updated_at < ?
            """,
            (*HIGH_SIGNAL_JOB_STATUSES, since_text, until_text),
        ).fetchone()
        noisy_rows = connection.execute(
            """
            SELECT query_run_results.notes, query_run_results.raw_payload,
                query_run_results.duplicate_reason
            FROM query_run_results
            JOIN query_runs ON query_runs.id = query_run_results.query_run_id
            WHERE query_run_results.result_status = 'rejected'
                AND query_run_results.updated_at >= ?
                AND query_run_results.updated_at < ?
            """,
            (since_text, until_text),
        ).fetchall()
        stale_action_rows = connection.execute(
            f"""
            SELECT queue, COUNT(*) AS count
            FROM actions
            WHERE {open_action_where_clause('actions')}
                AND due_at IS NOT NULL
                AND date(due_at) < date(?)
            GROUP BY queue
            ORDER BY queue
            """,
            (until_text,),
        ).fetchall()
        open_actions = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM actions
            WHERE {open_action_where_clause('actions')}
            """
        ).fetchone()[0]
        target_coverage = connection.execute(
            f"""
            SELECT
                COUNT(*) AS active_targets,
                SUM(CASE WHEN active_sources.company_id IS NOT NULL THEN 1 ELSE 0 END)
                    AS with_active_sources,
                SUM(CASE WHEN active_sources.company_id IS NULL THEN 1 ELSE 0 END)
                    AS missing_active_sources,
                SUM(
                    CASE
                        WHEN active_sources.company_id IS NULL
                            AND (companies.career_url IS NULL OR companies.career_url = '')
                        THEN 1
                        ELSE 0
                    END
                ) AS missing_source_details,
                SUM(
                    CASE
                        WHEN active_sources.company_id IS NULL
                            AND companies.career_url IS NOT NULL
                            AND companies.career_url != ''
                        THEN 1
                        ELSE 0
                    END
                ) AS official_fallback_only,
                SUM(
                    CASE
                        WHEN companies.ats_type IS NOT NULL
                            AND companies.ats_type != ''
                            AND lower(companies.ats_type) NOT IN ({", ".join("?" for _ in ATS_TYPES)})
                        THEN 1
                        ELSE 0
                    END
                ) AS unsupported_sources,
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
            (*ATS_TYPES, (until - timedelta(days=14)).isoformat()),
        ).fetchone()
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
    status_summary = ", ".join(
        f"{row['status']}:{row['count']}" for row in job_status_rows
    ) or "none"
    screen_bucket_summary = ", ".join(
        f"{row['screen_bucket']}:{row['count']}" for row in screen_bucket_rows
    ) or "none"
    stale_by_queue = ", ".join(
        f"{row['queue']}:{row['count']}" for row in stale_action_rows
    ) or "none"
    query_results = query_quality["results"] or 0
    query_reviewed = query_quality["reviewed"] or 0
    query_accepted = query_quality["accepted"] or 0
    query_rejected = query_quality["rejected"] or 0
    query_duplicate = query_quality["duplicate"] or 0
    query_pending = query_quality["pending"] or 0
    accepted_result_count = accepted_high_signal_results["accepted"] or 0
    matched_high_signal_results = accepted_high_signal_results["matched"] or 0
    noisy_rejected = count_noisy_query_results(noisy_rows)
    target_active = target_coverage["active_targets"] or 0
    target_with_sources = target_coverage["with_active_sources"] or 0
    target_missing_sources = target_coverage["missing_active_sources"] or 0
    target_missing_details = target_coverage["missing_source_details"] or 0
    target_fallback_only = target_coverage["official_fallback_only"] or 0
    target_unsupported = target_coverage["unsupported_sources"] or 0
    target_stale_checks = target_coverage["stale_checks"] or 0
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
        "bucket_resolution="
        f"resolved_jobs={resolved_jobs} unresolved_jobs={unresolved_jobs} "
        f"resolution_rate={percent(resolved_jobs, resolved_jobs + unresolved_jobs)} "
        f"buckets={screen_bucket_summary} statuses={status_summary}"
    )
    print(
        "reviewed_query_results="
        f"results={query_results} reviewed={query_reviewed} pending={query_pending} "
        f"accepted={query_accepted} rejected={query_rejected} "
        f"duplicate={query_duplicate} noisy={noisy_rejected} "
        f"review_rate={percent(query_reviewed, query_results)}"
    )
    print(
        "accepted_high_signal_roles="
        f"query_results_accepted={accepted_result_count} "
        f"matched_high_signal_jobs={matched_high_signal_results} "
        f"unconverted_accepted_results={accepted_result_count - matched_high_signal_results} "
        f"ready_or_later_jobs={high_signal_jobs}"
    )
    print(
        "stale_actions="
        f"open={open_actions} stale={sum(row['count'] for row in stale_action_rows)} "
        f"by_queue={stale_by_queue}"
    )
    print(
        "target_company_coverage="
        f"active_targets={target_active} with_active_sources={target_with_sources} "
        f"missing_active_sources={target_missing_sources} "
        f"missing_source_details={target_missing_details} "
        f"official_fallback_only={target_fallback_only} "
        f"unsupported_sources={target_unsupported} "
        f"stale_checks={target_stale_checks}"
    )
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


def command_report_cooldowns(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_current_database_read_only(db_path)
    as_of = parse_report_as_of(args.as_of)
    if args.limit <= 0:
        raise ValueError("report cooldowns --limit must be a positive integer")

    with closing(connect(db_path)) as connection:
        record_count = command_center_record_count(connection)
        evidence_rows = cooldown_evidence_rows(connection, as_of=as_of)
        recommendations = grouped_cooldown_recommendations(
            evidence_rows=evidence_rows,
            as_of=as_of,
            limit=args.limit,
        )

    print(f"Cooldown recommendations report as_of={as_of.isoformat()}")
    print(
        "Thresholds: "
        f"no_interview_days={NO_INTERVIEW_COOLDOWN_DAYS} | "
        f"interview_loop_days={INTERVIEW_LOOP_COOLDOWN_DAYS} | "
        f"timing_capacity_days={TIMING_CAPACITY_COOLDOWN_DAYS} | "
        f"durable_low_priority_review_days={DURABLE_LOW_PRIORITY_REVIEW_DAYS}"
    )
    print("Mode: advisory read-only; no company, job, action, or due-date changes applied.")
    if record_count == 0:
        print("No command center data.")
        print("Next step: record outcomes before reviewing cooldown recommendations.")
        return 0
    if not recommendations:
        print("No cooldown recommendations from stored outcome evidence.")
        return 0

    temporary = [
        recommendation
        for recommendation in recommendations
        if recommendation.recommendation_type == "temporary"
    ]
    durable = [
        recommendation
        for recommendation in recommendations
        if recommendation.recommendation_type == "durable"
    ]

    print("Temporary cooldown recommendations:")
    if temporary:
        for recommendation in temporary:
            for line in format_cooldown_recommendation(recommendation):
                print(line)
    else:
        print("- none")

    print("Durable pass / low-priority recommendations:")
    if durable:
        for recommendation in durable:
            for line in format_cooldown_recommendation(recommendation):
                print(line)
    else:
        print("- none")
    return 0


def command_report_proof_gaps(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_current_database_read_only(db_path)
    as_of = parse_report_as_of(args.as_of)
    if args.limit <= 0:
        raise ValueError("report proof-gaps --limit must be a positive integer")
    if args.evidence_limit <= 0:
        raise ValueError("report proof-gaps --evidence-limit must be a positive integer")
    if args.one_off_limit < 0:
        raise ValueError("report proof-gaps --one-off-limit must be zero or greater")

    with closing(connect(db_path)) as connection:
        record_count = command_center_record_count(connection)
        groups = group_proof_gap_evidence(proof_gap_evidence(connection))

    print(f"Proof gap report as_of={as_of.isoformat()}")
    print(
        "Ranking: recurring groups sort above one-off groups; "
        "score weights jobs, companies, source evidence, severity, and open gaps."
    )
    if record_count == 0:
        print("No command center data.")
        return 0
    if not groups:
        print("No proof gaps found.")
        return 0

    recurring_groups = [
        group for group in groups if proof_gap_strength(group) != "one_off"
    ][: args.limit]
    one_off_groups = [
        group for group in groups if proof_gap_strength(group) == "one_off"
    ][: args.one_off_limit]

    print("Recommendations:")
    if recurring_groups:
        for index, group in enumerate(recurring_groups, start=1):
            print_proof_gap_group(index, group, args.evidence_limit)
    else:
        print("- none")

    print("Lower-signal one-offs:")
    if one_off_groups:
        for index, group in enumerate(one_off_groups, start=1):
            print_proof_gap_group(index, group, args.evidence_limit)
    else:
        print("- none")
    suppressed = max(0, len(groups) - len(recurring_groups) - len(one_off_groups))
    if suppressed:
        print(f"Suppressed lower-ranked groups={suppressed}")
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


def command_action_remind(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_current_database_read_only(db_path)
    if args.failure_count < 0:
        raise ValueError("action remind --failure-count must be zero or greater")
    if args.record_status == "completed" and (
        args.failure_count or args.failure_summary
    ):
        raise ValueError(
            "completed reminder runs cannot include failure_count or failure_summary"
        )
    as_of = parse_report_as_of(args.as_of)
    started_at = as_of.isoformat()
    with closing(connect(db_path)) as connection:
        with connection:
            rows = reminder_action_rows(
                connection,
                queue=args.queue,
                include_ready=args.include_ready,
                as_of=as_of,
                limit=args.limit,
            )
            should_record = (
                rows or args.record_all_clear or args.record_status in ("failed", "partial")
            )
            if args.record_run and should_record:
                ended_at = utc_now()
                action_ids = encode_id_list([int(row["id"]) for row in rows])
                notes = (
                    "read-only stale-action reminder; no actions completed, skipped, "
                    "rescheduled, reprioritized, or rewritten"
                )
                recovery_status = (
                    "unresolved" if args.record_status in ("failed", "partial") else "none"
                )
                connection.execute(
                    """
                    INSERT INTO automation_runs(
                        source, scope, status, started_at, ended_at, result_count,
                        failure_count, created_action_count, created_artifact_count,
                        created_query_run_count, failure_summary, action_ids, notes,
                        recovery_status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "stale_action_reminder",
                        args.queue or "all_actions",
                        args.record_status,
                        started_at,
                        ended_at,
                        len(rows),
                        args.failure_count,
                        args.failure_summary,
                        action_ids,
                        notes,
                        recovery_status,
                        ended_at,
                        ended_at,
                    ),
                )

    scope = f"queue={args.queue}" if args.queue else "all queues"
    print(f"Action reminders as_of={started_at} | scope={scope} | surfaced={len(rows)}")
    print("mode=read_only | mutation=none")
    if not rows:
        print("All clear: no stale, due, blocked, or ready actions matched reminder scope.")
        print("next_command=python3 scripts/job_search.py action next")
        return 0
    for row in rows:
        print(format_action_reminder(row, script_name=str(Path(__file__)), as_of=as_of))
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
    parser.add_argument("--rejection-reason", choices=REJECTION_REASONS)
    parser.add_argument("--application-outcome", choices=APPLICATION_OUTCOMES)
    parser.add_argument("--screen-bucket", choices=SCREEN_BUCKETS)


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
    automation = subparsers.add_parser(
        "automation", help="Record and review assistive automation runs."
    )
    automation_subparsers = automation.add_subparsers(
        dest="automation_command", metavar="command", required=True
    )
    automation_record = automation_subparsers.add_parser(
        "record", help="Record a scheduled or assistive automation run."
    )
    automation_record.add_argument("--source", required=True)
    automation_record.add_argument("--scope", required=True)
    automation_record.add_argument("--status", choices=AUTOMATION_RUN_STATUSES, required=True)
    automation_record.add_argument("--started-at", required=True)
    automation_record.add_argument("--ended-at")
    automation_record.add_argument("--result-count", type=non_negative_int, default=0)
    automation_record.add_argument("--failure-count", type=non_negative_int, default=0)
    automation_record.add_argument("--failure-summary")
    automation_record.add_argument("--action-id", type=positive_int, action="append")
    automation_record.add_argument("--artifact-id", type=positive_int, action="append")
    automation_record.add_argument("--draft-id", type=positive_int, action="append")
    automation_record.add_argument("--query-run-id", type=positive_int, action="append")
    automation_record.add_argument("--notes")
    automation_record.add_argument("--recovery-status", choices=AUTOMATION_RECOVERY_STATUSES)
    automation_record.add_argument("--recovery-notes")
    automation_record.add_argument("--raw-source-reference")
    automation_poll = automation_subparsers.add_parser(
        "poll-targets",
        help="Poll active target-company ATS sources and record automation evidence.",
    )
    automation_poll.add_argument("--company")
    automation_poll.add_argument("--source-id", type=positive_int, action="append")
    automation_prepare_query_run = automation_subparsers.add_parser(
        "prepare-query-run",
        help="Prepare and record an approved broad-source query run.",
    )
    automation_prepare_query_run.add_argument("--source", choices=QUERY_SOURCES, required=True)
    automation_prepare_query_run.add_argument("--pack", required=True)
    automation_prepare_query_run.add_argument("--file", required=True)
    automation_prepare_query_run.add_argument(
        "--reason",
        help="Required for exception packs such as ACCESS.",
    )
    automation_prepare_query_run.add_argument("--started-at")
    automation_prepare_query_run.add_argument("--ended-at")
    automation_prepare_query_run.add_argument("--failure-count", type=non_negative_int, default=0)
    automation_prepare_query_run.add_argument("--failure-summary")
    automation_prepare_query_run.add_argument("--recovery-status", choices=AUTOMATION_RECOVERY_STATUSES)
    automation_prepare_query_run.add_argument("--recovery-notes")
    automation_list = automation_subparsers.add_parser(
        "list", help="List automation run history."
    )
    automation_list.add_argument("--status", choices=AUTOMATION_RUN_STATUSES)
    automation_list.add_argument("--limit", type=positive_int, default=20)
    automation_review = automation_subparsers.add_parser(
        "review", help="Show failed or partial automation runs needing recovery."
    )
    automation_review.add_argument("--status", choices=("failed", "partial"))
    automation_review.add_argument("--limit", type=positive_int, default=20)
    automation_show = automation_subparsers.add_parser(
        "show", help="Show one automation run and recovery path."
    )
    automation_show.add_argument("automation_run_id", type=positive_int)
    automation_recover = automation_subparsers.add_parser(
        "recover", help="Mark a failed or partial automation run for recovery."
    )
    automation_recover.add_argument("automation_run_id", type=positive_int)
    automation_recover_subparsers = automation_recover.add_subparsers(
        dest="recovery_command", metavar="choice", required=True
    )
    for recovery_choice in ("retry", "skip", "resolve"):
        recovery = automation_recover_subparsers.add_parser(recovery_choice)
        recovery.add_argument("--notes")
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
    job_list.add_argument("--screen-bucket", choices=SCREEN_BUCKETS)
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
    action_remind = action_subparsers.add_parser(
        "remind",
        help="Show read-only stale, due, blocked, and optionally ready action reminders.",
    )
    action_remind.add_argument(
        "--queue",
        choices=ACTION_QUEUES,
    )
    action_remind.add_argument("--limit", type=positive_int, default=20)
    action_remind.add_argument("--as-of")
    action_remind.add_argument(
        "--include-ready",
        action="store_true",
        help="Include ready unscheduled/upcoming actions after stale, due, and blocked work.",
    )
    action_remind.add_argument(
        "--record-run",
        action="store_true",
        help="Record surfaced reminders in automation_runs.",
    )
    action_remind.add_argument(
        "--record-status",
        choices=("completed", "failed", "partial"),
        default="completed",
        help="Status to store when --record-run records the reminder run.",
    )
    action_remind.add_argument(
        "--failure-count",
        type=int,
        default=0,
        help="Failure count to store with failed or partial recorded reminder runs.",
    )
    action_remind.add_argument(
        "--failure-summary",
        help="Failure summary to store with failed or partial recorded reminder runs.",
    )
    action_remind.add_argument(
        "--record-all-clear",
        action="store_true",
        help="With --record-run, also record all-clear runs.",
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

    draft = subparsers.add_parser(
        "draft", help="Save review-only follow-ups and application answers."
    )
    draft_subparsers = draft.add_subparsers(
        dest="draft_command", metavar="command", required=True
    )
    draft_add = draft_subparsers.add_parser(
        "add", help="Create a review-only draft without sending or submitting."
    )
    draft_add.add_argument("--company", required=True)
    draft_add.add_argument("--type", choices=DRAFT_TYPES, required=True)
    draft_add.add_argument("--title", required=True)
    body_group = draft_add.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body")
    body_group.add_argument("--body-file")
    draft_add.add_argument("--path")
    draft_add.add_argument("--job-id", type=positive_int)
    draft_add.add_argument("--contact-id", type=positive_int)
    draft_add.add_argument("--artifact-id", type=positive_int)
    draft_add.add_argument("--action-id", type=positive_int)
    draft_add.add_argument("--source-summary")
    draft_add.add_argument("--happened-at")
    draft_list = draft_subparsers.add_parser("list", help="List review-only drafts.")
    draft_list.add_argument("--company")
    draft_list.add_argument("--status", choices=DRAFT_STATUSES)
    draft_list.add_argument("--limit", type=positive_int, default=50)
    draft_status = draft_subparsers.add_parser(
        "status", help="Reject, approve, or request revision for a draft."
    )
    draft_status.add_argument("draft_id", type=positive_int)
    draft_status.add_argument("status", choices=("needs_revision", "rejected", "approved"))
    draft_status.add_argument("--notes")
    draft_status.add_argument("--happened-at")
    metrics = subparsers.add_parser("metrics", help="Show job search metrics.")
    metrics.add_argument("--since")
    metrics.add_argument("--until")
    metrics.add_argument("--days", type=int, default=7)
    report = subparsers.add_parser("report", help="Show read-only reports.")
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
    cooldowns = report_subparsers.add_parser(
        "cooldowns",
        help="Show advisory cooldown recommendations from recorded outcomes.",
    )
    cooldowns.add_argument("--as-of")
    cooldowns.add_argument("--limit", type=int, default=COOLDOWN_RECOMMENDATION_LIMIT)
    proof_gaps = report_subparsers.add_parser(
        "proof-gaps",
        help="Rank recurring proof gaps across jobs, companies, actions, and events.",
    )
    proof_gaps.add_argument("--as-of")
    proof_gaps.add_argument("--limit", type=int, default=20)
    proof_gaps.add_argument("--evidence-limit", type=int, default=4)
    proof_gaps.add_argument("--one-off-limit", type=int, default=5)
    strategy_feedback = report_subparsers.add_parser(
        "strategy-feedback",
        help="Compose weekly strategy feedback from command-center reports.",
    )
    strategy_feedback.add_argument("--as-of")
    strategy_feedback.add_argument("--days", type=int, default=7)
    strategy_feedback.add_argument("--limit", type=int, default=20)
    query_pack_tuning = report_subparsers.add_parser(
        "query-pack-tuning",
        help="Recommend query-pack tuning from reviewed query-run results.",
    )
    query_pack_tuning.add_argument("--limit", type=int, default=20)

    return parser.parse_args()


def command_init(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    version = init_database(db_path)
    print(f"initialized {db_path} schema_version={version}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    require_database(db_path)
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
    automation_recovery = daily_status["automation_recovery_counts"]
    if automation_recovery:
        print(
            "Automation runs needing recovery: "
            + ", ".join(
                f"{status}={automation_recovery[status]}"
                for status in ("failed", "partial")
                if status in automation_recovery
            )
        )
    else:
        print("Automation runs needing recovery: none")
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
        if args.command == "automation":
            if args.automation_command == "record":
                return command_automation_record(args)
            if args.automation_command == "poll-targets":
                return command_automation_poll_targets(args)
            if args.automation_command == "prepare-query-run":
                return command_automation_prepare_query_run(args)
            if args.automation_command == "list":
                return command_automation_list(args)
            if args.automation_command == "review":
                return command_automation_review(args)
            if args.automation_command == "show":
                return command_automation_show(args)
            if args.automation_command == "recover":
                return command_automation_recover(args)
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
        if args.command == "draft":
            if args.draft_command == "add":
                return command_draft_add(args)
            if args.draft_command == "list":
                return command_draft_list(args)
            if args.draft_command == "status":
                return command_draft_status(args)
        if args.command == "report":
            if args.report_command == "hygiene":
                return command_report_hygiene(args)
            if args.report_command == "cooldowns":
                return command_report_cooldowns(args)
            if args.report_command == "proof-gaps":
                return command_report_proof_gaps(args)
            if args.report_command == "strategy-feedback":
                return command_report_strategy_feedback(args)
            if args.report_command == "query-pack-tuning":
                return command_report_query_pack_tuning(args)
        if args.command == "action":
            if args.action_command == "add":
                return command_action_add(args)
            if args.action_command == "next":
                return command_action_next(args)
            if args.action_command == "list":
                return command_action_list(args)
            if args.action_command == "remind":
                return command_action_remind(args)
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

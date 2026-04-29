#!/usr/bin/env python3
"""Company-first job search command center CLI."""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "APPLICATIONS" / "_ops" / "job_search.sqlite"
SCHEMA_VERSION = 1

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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def company_name_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).casefold()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    db_path.chmod(0o600)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def init_database(db_path: Path) -> int:
    with closing(connect(db_path)) as connection:
        with connection:
            connection.executescript(SCHEMA)
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (SCHEMA_VERSION, "initial_job_search_schema", utc_now()),
            )
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


def connect_initialized(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not initialized: {db_path}")
    return connect(db_path)


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


def touch_company(
    connection: sqlite3.Connection, company_id: int, happened_at: str | None = None
) -> None:
    now = utc_now()
    touch_at = happened_at or now
    connection.execute(
        """
        UPDATE companies
        SET last_touched_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (touch_at, now, company_id),
    )


def insert_event(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    event_type: str,
    happened_at: str | None = None,
    notes: str | None = None,
    job_id: int | None = None,
    contact_id: int | None = None,
    artifact_id: int | None = None,
    gap_id: int | None = None,
    action_id: int | None = None,
) -> int:
    timestamp = happened_at or utc_now()
    connection.execute(
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
            timestamp,
            notes,
            utc_now(),
        ),
    )
    touch_company(connection, company_id, timestamp)
    return int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])


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
    company_subparsers = company.add_subparsers(dest="company_command", required=True)
    company_add = company_subparsers.add_parser("add", help="Add a target company.")
    company_add.add_argument("name")
    company_add.add_argument("--tier", type=int, choices=(1, 2, 3))
    company_add.add_argument("--lanes")
    company_add.add_argument("--why-interesting")
    company_add.add_argument("--fit-thesis")
    company_add.add_argument("--known-gaps")
    company_add.add_argument("--products-used")
    company_add.add_argument("--target-roles")
    company_add.add_argument("--career-url")
    company_add.add_argument("--ats-type")
    company_add.add_argument("--status", choices=COMPANY_STATUSES, default="active")
    company_add.add_argument("--cooldown-until")
    company_add.add_argument("--notes")
    company_show = company_subparsers.add_parser("show", help="Show a target company.")
    company_show.add_argument("company")
    company_list = company_subparsers.add_parser("list", help="List target companies.")
    company_list.add_argument("--status", choices=COMPANY_STATUSES)

    job = subparsers.add_parser("job", help="Manage company roles.")
    job_subparsers = job.add_subparsers(dest="job_command", required=True)
    job_add = job_subparsers.add_parser("add", help="Add a company role.")
    job_add.add_argument("--company", required=True)
    job_add.add_argument("--title", required=True)
    job_add.add_argument("--source", default="manual")
    job_add.add_argument("--url", dest="canonical_url")
    job_add.add_argument("--source-job-id")
    job_add.add_argument("--location")
    job_add.add_argument("--remote-status")
    job_add.add_argument("--role-level")
    job_add.add_argument("--lane")
    job_add.add_argument("--status", choices=JOB_STATUSES, default="discovered")
    job_add.add_argument("--fit-score", type=int)
    job_add.add_argument("--relationship-path")
    job_add.add_argument("--artifact-opportunity")
    job_add.add_argument("--recommended-resume")
    job_add.add_argument("--materials-status")
    job_add.add_argument("--application-folder")
    job_add.add_argument("--material-paths")
    job_add.add_argument("--compensation-signal")
    job_add.add_argument("--rejection-reason")
    job_add.add_argument("--application-outcome")
    job_show = job_subparsers.add_parser("show", help="Show a role.")
    job_show.add_argument("job_id", type=int)
    job_list = job_subparsers.add_parser("list", help="List roles.")
    job_list.add_argument("--company")
    job_list.add_argument("--status", choices=JOB_STATUSES)
    job_status = job_subparsers.add_parser("status", help="Update role status.")
    job_status.add_argument("job_id", type=int)
    job_status.add_argument("status", choices=JOB_STATUSES)
    job_status.add_argument("--happened-at")
    job_status.add_argument("--notes")

    contact = subparsers.add_parser("contact", help="Manage relationship paths.")
    contact_subparsers = contact.add_subparsers(dest="contact_command", required=True)
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
    artifact_subparsers = artifact.add_subparsers(dest="artifact_command", required=True)
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
    artifact_status = artifact_subparsers.add_parser("status", help="Update artifact status.")
    artifact_status.add_argument("artifact_id", type=int)
    artifact_status.add_argument("status", choices=ARTIFACT_STATUSES)
    artifact_status.add_argument("--happened-at")
    artifact_status.add_argument("--notes")

    gap = subparsers.add_parser("gap", help="Manage search gaps.")
    gap_subparsers = gap.add_subparsers(dest="gap_command", required=True)
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
    action_subparsers = action.add_subparsers(dest="action_command", required=True)
    for command in ("next", "done", "list"):
        action_subparsers.add_parser(command, help=f"{command.replace('_', ' ')} actions")

    event = subparsers.add_parser("event", help="Manage append-only history.")
    event_subparsers = event.add_subparsers(dest="event_command", required=True)
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
    subparsers.add_parser("metrics", help="Show job search metrics.")

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


def command_company(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    with closing(connect_initialized(db_path)) as connection:
        if args.company_command == "add":
            now = utc_now()
            with connection:
                connection.execute(
                    """
                    INSERT INTO companies(
                        name, name_key, tier, lanes, why_interesting, fit_thesis,
                        known_gaps, products_used, target_roles, career_url, ats_type,
                        status, cooldown_until, notes, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        now,
                        now,
                    ),
                )
            print_row_summary("company", int(connection.execute("SELECT last_insert_rowid()").fetchone()[0]))
            return 0

        if args.company_command == "show":
            company_id = resolve_company_id(connection, args.company)
            company = require_row(
                connection,
                "SELECT * FROM companies WHERE id = ?",
                (company_id,),
                f"Company not found: {args.company}",
            )
            print(
                f"{company['id']} | {company['name']} | status={company['status']}"
                + render_optional("tier", company["tier"])
                + render_optional("lanes", company["lanes"])
                + render_optional("last_touched_at", company["last_touched_at"])
                + render_optional("notes", company["notes"])
            )
            rows = read_events(connection, company_id=company_id, limit=10)
            if rows:
                print("history:")
                for row in rows:
                    print(render_event(row))
            return 0

        if args.company_command == "list":
            parameters: list[object] = []
            where = ""
            if args.status:
                where = "WHERE status = ?"
                parameters.append(args.status)
            rows = connection.execute(
                f"""
                SELECT id, name, status, tier, lanes, last_touched_at
                FROM companies
                {where}
                ORDER BY tier IS NULL, tier, name
                """,
                tuple(parameters),
            ).fetchall()
            for row in rows:
                print(
                    f"{row['id']} | {row['name']} | status={row['status']}"
                    + render_optional("tier", row["tier"])
                    + render_optional("lanes", row["lanes"])
                    + render_optional("last_touched_at", row["last_touched_at"])
                )
            return 0

    raise ValueError(f"Unknown company command: {args.company_command}")


def command_job(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    with closing(connect_initialized(db_path)) as connection:
        if args.job_command == "add":
            company_id = resolve_company_id(connection, args.company)
            now = utc_now()
            with connection:
                connection.execute(
                    """
                    INSERT INTO jobs(
                        company_id, title, canonical_url, source, source_job_id,
                        location, remote_status, role_level, lane, status, fit_score,
                        relationship_path, artifact_opportunity, recommended_resume,
                        materials_status, application_folder, material_paths,
                        compensation_signal, rejection_reason, application_outcome,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        company_id,
                        args.title,
                        args.canonical_url,
                        args.source,
                        args.source_job_id,
                        args.location,
                        args.remote_status,
                        args.role_level,
                        args.lane,
                        args.status,
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
                job_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
                touch_company(connection, company_id)
            print_row_summary("job", job_id)
            return 0

        if args.job_command == "show":
            row = require_row(
                connection,
                """
                SELECT jobs.*, companies.name AS company_name
                FROM jobs
                JOIN companies ON companies.id = jobs.company_id
                WHERE jobs.id = ?
                """,
                (args.job_id,),
                f"Job not found: {args.job_id}",
            )
            print(
                f"{row['id']} | {row['company_name']} | {row['title']} | status={row['status']}"
                + render_optional("source", row["source"])
                + render_optional("url", row["canonical_url"])
                + render_optional("lane", row["lane"])
            )
            return 0

        if args.job_command == "list":
            parameters: list[object] = []
            predicates: list[str] = []
            if args.company:
                predicates.append("jobs.company_id = ?")
                parameters.append(resolve_company_id(connection, args.company))
            if args.status:
                predicates.append("jobs.status = ?")
                parameters.append(args.status)
            where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
            rows = connection.execute(
                f"""
                SELECT jobs.id, companies.name AS company_name, jobs.title, jobs.status,
                    jobs.source, jobs.canonical_url
                FROM jobs
                JOIN companies ON companies.id = jobs.company_id
                {where}
                ORDER BY jobs.updated_at DESC, jobs.id DESC
                """,
                tuple(parameters),
            ).fetchall()
            for row in rows:
                print(
                    f"{row['id']} | {row['company_name']} | {row['title']} | status={row['status']}"
                    + render_optional("source", row["source"])
                    + render_optional("url", row["canonical_url"])
                )
            return 0

        if args.job_command == "status":
            row = require_row(
                connection,
                "SELECT company_id, status, title FROM jobs WHERE id = ?",
                (args.job_id,),
                f"Job not found: {args.job_id}",
            )
            now = utc_now()
            notes = (
                args.notes
                or f"job #{args.job_id} status changed: {row['status']} -> {args.status}"
            )
            with connection:
                connection.execute(
                    "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                    (args.status, now, args.job_id),
                )
                event_id = insert_event(
                    connection,
                    company_id=int(row["company_id"]),
                    job_id=args.job_id,
                    event_type=event_type_for_job_status(args.status),
                    happened_at=args.happened_at,
                    notes=notes,
                )
            print(f"job id={args.job_id} status={args.status} event_id={event_id}")
            return 0

    raise ValueError(f"Unknown job command: {args.job_command}")


def command_contact(args: argparse.Namespace) -> int:
    with closing(connect_initialized(Path(args.db_path))) as connection:
        if args.contact_command == "add":
            company_id = resolve_company_id(connection, args.company)
            now = utc_now()
            with connection:
                connection.execute(
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
                contact_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
                touch_company(connection, company_id, args.last_contacted)
            print_row_summary("contact", contact_id)
            return 0

        if args.contact_command == "list":
            parameters: list[object] = []
            where = ""
            if args.company:
                where = "WHERE contacts.company_id = ?"
                parameters.append(resolve_company_id(connection, args.company))
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
            return 0

    raise ValueError(f"Unknown contact command: {args.contact_command}")


def command_artifact(args: argparse.Namespace) -> int:
    with closing(connect_initialized(Path(args.db_path))) as connection:
        if args.artifact_command == "add":
            company_id = resolve_company_id(connection, args.company)
            now = utc_now()
            with connection:
                connection.execute(
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
                artifact_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
                touch_company(connection, company_id)
                event_id = None
                if args.status == "sent":
                    event_id = insert_event(
                        connection,
                        company_id=company_id,
                        job_id=args.job_id,
                        artifact_id=artifact_id,
                        event_type="artifact_sent",
                        happened_at=args.happened_at,
                        notes=args.notes or f"artifact #{artifact_id} sent",
                    )
            if event_id is None:
                print_row_summary("artifact", artifact_id)
            else:
                print(f"artifact id={artifact_id} event_id={event_id}")
            return 0

        if args.artifact_command == "list":
            parameters: list[object] = []
            where = ""
            if args.company:
                where = "WHERE artifacts.company_id = ?"
                parameters.append(resolve_company_id(connection, args.company))
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
            return 0

        if args.artifact_command == "status":
            row = require_row(
                connection,
                "SELECT company_id, job_id, status FROM artifacts WHERE id = ?",
                (args.artifact_id,),
                f"Artifact not found: {args.artifact_id}",
            )
            now = utc_now()
            notes = (
                args.notes
                or f"artifact #{args.artifact_id} status changed: {row['status']} -> {args.status}"
            )
            with connection:
                connection.execute(
                    "UPDATE artifacts SET status = ?, updated_at = ? WHERE id = ?",
                    (args.status, now, args.artifact_id),
                )
                event_id = insert_event(
                    connection,
                    company_id=int(row["company_id"]),
                    job_id=row["job_id"],
                    artifact_id=args.artifact_id,
                    event_type=event_type_for_artifact_status(args.status),
                    happened_at=args.happened_at,
                    notes=notes,
                )
            print(f"artifact id={args.artifact_id} status={args.status} event_id={event_id}")
            return 0

    raise ValueError(f"Unknown artifact command: {args.artifact_command}")


def command_gap(args: argparse.Namespace) -> int:
    with closing(connect_initialized(Path(args.db_path))) as connection:
        if args.gap_command == "add":
            if args.company is None and args.job_id is None:
                raise ValueError("gap add requires --company or --job-id")
            company_id = resolve_company_id(connection, args.company) if args.company else None
            if company_id is None and args.job_id is not None:
                job = require_row(
                    connection,
                    "SELECT company_id FROM jobs WHERE id = ?",
                    (args.job_id,),
                    f"Job not found: {args.job_id}",
                )
                company_id = int(job["company_id"])
            now = utc_now()
            with connection:
                connection.execute(
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
                gap_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
                event_id = insert_event(
                    connection,
                    company_id=int(company_id),
                    job_id=args.job_id,
                    gap_id=gap_id,
                    event_type="gap_identified",
                    happened_at=args.happened_at,
                    notes=args.notes or args.description,
                )
            print(f"gap id={gap_id} event_id={event_id}")
            return 0

        if args.gap_command == "list":
            parameters: list[object] = []
            predicates: list[str] = []
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
                ORDER BY gaps.severity DESC, gaps.updated_at DESC, gaps.id DESC
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
            return 0

        if args.gap_command == "status":
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
            now = utc_now()
            notes = args.notes or f"gap #{args.gap_id} status changed: {row['status']} -> {args.status}"
            with connection:
                connection.execute(
                    """
                    UPDATE gaps
                    SET status = ?, resolution_action = COALESCE(?, resolution_action),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (args.status, args.resolution_action, now, args.gap_id),
                )
                event_id = insert_event(
                    connection,
                    company_id=company_id,
                    job_id=row["job_id"],
                    gap_id=args.gap_id,
                    event_type="status_changed",
                    happened_at=args.happened_at,
                    notes=notes,
                )
            print(f"gap id={args.gap_id} status={args.status} event_id={event_id}")
            return 0

    raise ValueError(f"Unknown gap command: {args.gap_command}")


def read_events(
    connection: sqlite3.Connection,
    *,
    company_id: int | None = None,
    limit: int = 50,
) -> list[sqlite3.Row]:
    parameters: list[object] = []
    where = ""
    if company_id is not None:
        where = "WHERE events.company_id = ?"
        parameters.append(company_id)
    parameters.append(limit)
    return list(
        connection.execute(
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
            ORDER BY events.happened_at ASC, events.id ASC
            LIMIT ?
            """,
            tuple(parameters),
        ).fetchall()
    )


def command_event(args: argparse.Namespace) -> int:
    with closing(connect_initialized(Path(args.db_path))) as connection:
        if args.event_command == "add":
            company_id = resolve_company_id(connection, args.company)
            with connection:
                event_id = insert_event(
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

        if args.event_command == "list":
            company_id = resolve_company_id(connection, args.company) if args.company else None
            for row in read_events(connection, company_id=company_id, limit=args.limit):
                print(render_event(row))
            return 0

    raise ValueError(f"Unknown event command: {args.event_command}")


def main() -> int:
    args = parse_args()
    try:
        if args.command == "init":
            return command_init(args)
        if args.command == "status":
            return command_status(args)
        if args.command == "company":
            return command_company(args)
        if args.command == "job":
            return command_job(args)
        if args.command == "contact":
            return command_contact(args)
        if args.command == "artifact":
            return command_artifact(args)
        if args.command == "gap":
            return command_gap(args)
        if args.command == "event":
            return command_event(args)
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 1
    except ValueError as error:
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

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


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "APPLICATIONS" / "_ops" / "job_search.sqlite"
SCHEMA_VERSION = 1


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


def require_database(db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not initialized: {db_path}")


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
    column = f"{prefix}.status" if prefix else "status"
    return f"{column} IN ('queued', 'in_progress', 'blocked', 'rescheduled')"


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


def log_event(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    event_type: str,
    job_id: int | None = None,
    action_id: int | None = None,
    notes: str | None = None,
    happened_at: str | None = None,
    now: str | None = None,
) -> None:
    now = now or utc_now()
    connection.execute(
        """
        INSERT INTO events(company_id, job_id, action_id, event_type, happened_at, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (company_id, job_id, action_id, event_type, happened_at or now, notes, now),
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

    if job["status"] in ("discovered", "screening") and (
        job["fit_score"] is not None and int(job["fit_score"]) >= 70
    ):
        upsert_action(
            connection,
            company_id=int(job["company_id"]),
            job_id=job_id,
            queue="screen",
            kind="screen_role",
            notes="Promising role needs screening.",
            now=now,
        )

    if job["status"] == "ready_to_apply":
        upsert_action(
            connection,
            company_id=int(job["company_id"]),
            job_id=job_id,
            queue="apply",
            kind="apply",
            notes="Role is marked ready to apply.",
            now=now,
        )

    if job["status"] == "applied":
        due_at = add_business_days(now_dt, 6).isoformat()
        upsert_action(
            connection,
            company_id=int(job["company_id"]),
            job_id=job_id,
            queue="follow_up",
            kind="follow_up",
            due_at=due_at,
            notes="Application submitted; follow up in 5-7 business days.",
            now=now,
        )

    if job["status"] == "rejected" or job["rejection_reason"]:
        upsert_action(
            connection,
            company_id=int(job["company_id"]),
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
            now,
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
            SELECT event_type, happened_at, notes
            FROM events
            WHERE company_id = ?
            ORDER BY happened_at DESC, id DESC
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
    if last_outcome:
        print(
            f"Last outcome: {last_outcome['event_type']} at {last_outcome['happened_at']}"
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
    now = utc_now()
    with closing(connect(db_path)) as connection:
        with connection:
            company = get_company(connection, args.company)
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
                    args.title,
                    args.url,
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
                event_type="job_added",
                notes=args.title,
                now=now,
            )
    print(f"job added id={job_id} company={args.company} title={args.title}")
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
                    "canonical_url": args.url,
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
                event_type = f"job_status_{args.status}"
                log_event(
                    connection,
                    company_id=int(updated["company_id"]),
                    job_id=args.job_id,
                    event_type=event_type,
                    notes=f"{job['status']} -> {args.status}",
                )
    print(f"job updated id={args.job_id}")
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
            completed_at = now if status == "done" else None
            due_at = getattr(args, "due_at", None)
            connection.execute(
                """
                UPDATE actions
                SET status = ?, completed_at = ?, due_at = COALESCE(?, due_at),
                    notes = COALESCE(?, notes), updated_at = ?
                WHERE id = ?
                """,
                (status, completed_at, due_at, getattr(args, "notes", None), now, args.action_id),
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
        choices=("active", "watch", "cooldown", "archived"),
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
    company_list.add_argument("--status", choices=("active", "watch", "cooldown", "archived"))
    company_list.add_argument("--tier", type=int, choices=(1, 2, 3))

    job = subparsers.add_parser("job", help="Manage company roles.")
    job_subparsers = job.add_subparsers(dest="job_command", metavar="command", required=True)
    job_add = job_subparsers.add_parser("add", help="Add a job.")
    job_add.add_argument("company")
    job_add.add_argument("title")
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

    add_stub_group(subparsers, "contact", "Manage relationship paths.", ("add", "list"))
    add_stub_group(subparsers, "artifact", "Manage targeted proof artifacts.", ("add", "list"))
    add_stub_group(subparsers, "gap", "Manage search gaps.", ("add", "list"))

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

    add_stub_group(subparsers, "event", "Manage append-only history.", ("add", "list"))
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

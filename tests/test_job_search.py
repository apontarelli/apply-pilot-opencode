from __future__ import annotations

import importlib.util
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts" / "job_search.py"
NOW = "2026-04-27T00:00:00+00:00"

JOB_SEARCH_SPEC = importlib.util.spec_from_file_location("job_search_cli", CLI)
assert JOB_SEARCH_SPEC is not None
assert JOB_SEARCH_SPEC.loader is not None
JOB_SEARCH = importlib.util.module_from_spec(JOB_SEARCH_SPEC)
sys.modules[JOB_SEARCH_SPEC.name] = JOB_SEARCH
JOB_SEARCH_SPEC.loader.exec_module(JOB_SEARCH)


class JobSearchDatabaseTests(unittest.TestCase):
    def run_cli(self, db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), "--db-path", str(db_path), *args],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

    def connect(self, db_path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def last_id(self, connection: sqlite3.Connection) -> int:
        return connection.execute("SELECT last_insert_rowid()").fetchone()[0]

    def stdout_id(self, result: subprocess.CompletedProcess[str]) -> int:
        match = re.search(r"id=(\d+)", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        return int(match.group(1))

    def insert_company(self, connection: sqlite3.Connection, name: str) -> int:
        connection.execute(
            """
            INSERT INTO companies(name, name_key, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, name.casefold(), NOW, NOW),
        )
        return self.last_id(connection)

    def insert_job(
        self,
        connection: sqlite3.Connection,
        company_id: int,
        *,
        title: str = "Product Lead",
        lane: str | None = None,
        status: str = "discovered",
        rejection_reason: str | None = None,
        application_outcome: str | None = None,
        artifact_opportunity: str | None = None,
    ) -> int:
        connection.execute(
            """
            INSERT INTO jobs(
                company_id, title, source, lane, status, rejection_reason,
                application_outcome, artifact_opportunity, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                title,
                "manual",
                lane,
                status,
                rejection_reason,
                application_outcome,
                artifact_opportunity,
                NOW,
                NOW,
            ),
        )
        return self.last_id(connection)

    def insert_contact(self, connection: sqlite3.Connection, company_id: int) -> int:
        connection.execute(
            """
            INSERT INTO contacts(company_id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (company_id, "Hiring Manager", NOW, NOW),
        )
        return self.last_id(connection)

    def insert_artifact(
        self,
        connection: sqlite3.Connection,
        company_id: int,
        job_id: int | None = None,
        *,
        status: str = "idea",
        link: str | None = None,
        path: str | None = None,
    ) -> int:
        connection.execute(
            """
            INSERT INTO artifacts(
                company_id, job_id, type, status, link, path, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (company_id, job_id, "memo", status, link, path, NOW, NOW),
        )
        return self.last_id(connection)

    def insert_gap(
        self,
        connection: sqlite3.Connection,
        company_id: int | None,
        job_id: int | None = None,
        *,
        gap_type: str = "domain",
        description: str = "Needs proof",
        severity: str = "medium",
        status: str = "open",
        resolution_action: str | None = None,
    ) -> int:
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
                job_id,
                gap_type,
                description,
                severity,
                status,
                resolution_action,
                NOW,
                NOW,
            ),
        )
        return self.last_id(connection)

    def insert_action(
        self,
        connection: sqlite3.Connection,
        company_id: int,
        *,
        job_id: int | None = None,
        contact_id: int | None = None,
        artifact_id: int | None = None,
        gap_id: int | None = None,
        queue: str = "apply",
        kind: str = "apply",
        status: str = "queued",
        due_at: str | None = None,
        completed_at: str | None = None,
        notes: str | None = None,
    ) -> int:
        connection.execute(
            """
            INSERT INTO actions(
                company_id, job_id, contact_id, artifact_id, gap_id, queue, kind,
                status, due_at, completed_at, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                job_id,
                contact_id,
                artifact_id,
                gap_id,
                queue,
                kind,
                status,
                due_at,
                completed_at,
                notes,
                NOW,
                NOW,
            ),
        )
        return self.last_id(connection)

    def insert_event(
        self,
        connection: sqlite3.Connection,
        company_id: int,
        *,
        job_id: int | None = None,
        contact_id: int | None = None,
        artifact_id: int | None = None,
        gap_id: int | None = None,
        action_id: int | None = None,
        event_type: str = "note",
        happened_at: str = NOW,
        notes: str | None = None,
    ) -> int:
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
                happened_at,
                notes,
                NOW,
            ),
        )
        return self.last_id(connection)

    def seed_two_company_graph(
        self, connection: sqlite3.Connection
    ) -> dict[str, int]:
        company_a = self.insert_company(connection, "Company A")
        company_b = self.insert_company(connection, "Company B")
        job_a = self.insert_job(connection, company_a)
        job_b = self.insert_job(connection, company_b)
        contact_b = self.insert_contact(connection, company_b)
        artifact_a = self.insert_artifact(connection, company_a, job_a)
        artifact_b = self.insert_artifact(connection, company_b, job_b)
        gap_a = self.insert_gap(connection, company_a, job_a)
        gap_b = self.insert_gap(connection, company_b, job_b)
        action_a = self.insert_action(connection, company_a)
        action_b = self.insert_action(connection, company_b, job_id=job_b)
        event_a = self.insert_event(connection, company_a)

        return {
            "company_a": company_a,
            "company_b": company_b,
            "job_a": job_a,
            "job_b": job_b,
            "contact_b": contact_b,
            "artifact_a": artifact_a,
            "artifact_b": artifact_b,
            "gap_a": gap_a,
            "gap_b": gap_b,
            "action_a": action_a,
            "action_b": action_b,
            "event_a": event_a,
        }

    def test_init_is_idempotent_and_status_reads_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"

            first = self.run_cli(db_path, "init")
            second = self.run_cli(db_path, "init")
            status = self.run_cli(db_path, "status")

            self.assertIn("schema_version=4", first.stdout)
            self.assertIn("schema_version=4", second.stdout)
            self.assertIn("schema_version=4", status.stdout)
            self.assertIn("companies=0", status.stdout)
            self.assertIn("jobs=0", status.stdout)
            self.assertIn("actions=0", status.stdout)
            self.assertIn("Open action queues: none", status.stdout)
            self.assertIn("Active jobs: none", status.stdout)
            self.assertIn("Recent outcomes (7d): none", status.stdout)
            self.assertIn("Target coverage: no active target companies", status.stdout)

            with closing(self.connect(db_path)) as connection:
                migration_count = connection.execute(
                    "SELECT COUNT(*) FROM schema_migrations"
                ).fetchone()[0]
                self.assertEqual(migration_count, 4)
            self.assertEqual(db_path.stat().st_mode & 0o777, 0o600)

    def test_status_shows_daily_operator_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_a = self.insert_company(connection, "Company A")
                    company_b = self.insert_company(connection, "Company B")
                    connection.execute(
                        """
                        UPDATE companies
                        SET tier = 1, lanes = 'FINTECH', last_checked_at = ?
                        WHERE id = ?
                        """,
                        ("2026-01-01T00:00:00+00:00", company_a),
                    )
                    connection.execute(
                        """
                        INSERT INTO company_sources(
                            company_id, source_type, source_key, status, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (company_b, "greenhouse", "company-b", "active", NOW, NOW),
                    )
                    job_id = self.insert_job(connection, company_a)
                    connection.execute(
                        "UPDATE jobs SET status = 'ready_to_apply' WHERE id = ?",
                        (job_id,),
                    )
                    self.insert_action(
                        connection,
                        company_a,
                        job_id=job_id,
                        due_at="2026-01-02T00:00:00+00:00",
                    )
                    self.insert_action(
                        connection,
                        company_a,
                        job_id=job_id,
                        kind="prepare_materials",
                        due_at=JOB_SEARCH.utc_now(),
                    )
                    self.insert_action(
                        connection,
                        company_b,
                        queue="research",
                        kind="poll_sources",
                    )
                    connection.execute(
                        """
                        INSERT INTO events(company_id, job_id, event_type, happened_at, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            company_a,
                            job_id,
                            "application_submitted",
                            JOB_SEARCH.utc_now(),
                            JOB_SEARCH.utc_now(),
                        ),
                    )

            status = self.run_cli(db_path, "status")

            self.assertIn("schema_version=4", status.stdout)
            self.assertIn("companies=2", status.stdout)
            self.assertIn("jobs=1", status.stdout)
            self.assertIn("actions=3", status.stdout)
            self.assertIn(
                "Open action queues: apply=2, research=1 | stale=1",
                status.stdout,
            )
            self.assertIn("due_today=1", status.stdout)
            self.assertIn("unscheduled=1", status.stdout)
            self.assertIn("Active jobs: ready_to_apply=1", status.stdout)
            self.assertIn(
                "Recent outcomes (7d): application_submitted=1", status.stdout
            )
            self.assertIn(
                "Target coverage: active_companies=2 | with_active_sources=1 | "
                "needs_source=1 | stale_checks=2",
                status.stdout,
            )

    def test_report_hygiene_surfaces_stale_actions_and_outcome_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    ready_company = self.insert_company(connection, "Ready Co")
                    ready_job = self.insert_job(connection, ready_company)
                    connection.execute(
                        "UPDATE jobs SET status = 'ready_to_apply' WHERE id = ?",
                        (ready_job,),
                    )
                    self.insert_action(
                        connection,
                        ready_company,
                        job_id=ready_job,
                        queue="apply",
                        kind="apply",
                        due_at="2026-04-01T00:00:00+00:00",
                    )

                    follow_company = self.insert_company(connection, "Follow Co")
                    follow_job = self.insert_job(connection, follow_company)
                    self.insert_action(
                        connection,
                        follow_company,
                        job_id=follow_job,
                        queue="follow_up",
                        kind="follow_up",
                        due_at="2026-04-02T00:00:00+00:00",
                    )

                    classify_company = self.insert_company(connection, "Classify Co")
                    classify_job = self.insert_job(connection, classify_company)
                    self.insert_action(
                        connection,
                        classify_company,
                        job_id=classify_job,
                        queue="classify",
                        kind="classify_outcome",
                        due_at="2026-04-03T00:00:00+00:00",
                    )

                    old_apply_company = self.insert_company(connection, "Old Apply Co")
                    old_apply_job = self.insert_job(connection, old_apply_company)
                    old_apply_action = self.insert_action(
                        connection,
                        old_apply_company,
                        job_id=old_apply_job,
                        queue="apply",
                        kind="apply",
                    )
                    connection.execute(
                        """
                        UPDATE actions
                        SET created_at = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            "2026-04-01T00:00:00+00:00",
                            "2026-04-01T00:00:00+00:00",
                            old_apply_action,
                        ),
                    )

                    mismatch_company = self.insert_company(connection, "Mismatch Co")
                    mismatch_job = self.insert_job(connection, mismatch_company)
                    self.insert_event(
                        connection,
                        mismatch_company,
                        job_id=mismatch_job,
                        event_type="rejection_received",
                        happened_at="2026-04-04T00:00:00+00:00",
                    )

                    rejected_company = self.insert_company(connection, "Rejected Co")
                    rejected_job = self.insert_job(connection, rejected_company)
                    connection.execute(
                        "UPDATE jobs SET status = 'rejected' WHERE id = ?",
                        (rejected_job,),
                    )
                    self.insert_event(
                        connection,
                        rejected_company,
                        job_id=rejected_job,
                        event_type="rejection_received",
                        happened_at="2026-04-05T00:00:00+00:00",
                    )

                    pending_company = self.insert_company(connection, "Pending Co")
                    pending_job = self.insert_job(connection, pending_company)
                    connection.execute(
                        "UPDATE jobs SET status = 'applied' WHERE id = ?",
                        (pending_job,),
                    )
                    self.insert_event(
                        connection,
                        pending_company,
                        job_id=pending_job,
                        event_type="application_submitted",
                        happened_at="2026-04-06T00:00:00+00:00",
                    )

                    event_only_company = self.insert_company(connection, "Event Only Co")
                    event_only_job = self.insert_job(connection, event_only_company)
                    self.insert_event(
                        connection,
                        event_only_company,
                        job_id=event_only_job,
                        event_type="application_submitted",
                        happened_at="2026-04-07T00:00:00+00:00",
                    )

                    future_company = self.insert_company(connection, "Future Co")
                    future_job = self.insert_job(connection, future_company)
                    connection.execute(
                        "UPDATE jobs SET status = 'rejected' WHERE id = ?",
                        (future_job,),
                    )
                    self.insert_event(
                        connection,
                        future_company,
                        job_id=future_job,
                        event_type="rejection_received",
                        happened_at="2026-05-03T00:00:00+00:00",
                    )

                    offset_future_company = self.insert_company(connection, "Offset Future Co")
                    offset_future_job = self.insert_job(connection, offset_future_company)
                    connection.execute(
                        "UPDATE jobs SET status = 'rejected' WHERE id = ?",
                        (offset_future_job,),
                    )
                    self.insert_event(
                        connection,
                        offset_future_company,
                        job_id=offset_future_job,
                        event_type="rejection_received",
                        happened_at="2026-05-01T20:00:00-07:00",
                    )

                    cooldown_company = self.insert_company(connection, "Cooldown Co")
                    connection.execute(
                        """
                        UPDATE companies
                        SET status = 'cooldown',
                            cooldown_until = '2026-06-01T00:00:00+00:00'
                        WHERE id = ?
                        """,
                        (cooldown_company,),
                    )
                    self.insert_event(
                        connection,
                        cooldown_company,
                        event_type="note",
                        happened_at="2026-05-01T00:00:00+00:00",
                    )

                    quiet_company = self.insert_company(connection, "Quiet Co")
                    self.insert_event(
                        connection,
                        quiet_company,
                        event_type="note",
                        happened_at="2026-05-01T00:00:00+00:00",
                    )
                    before_counts = connection.execute(
                        """
                        SELECT
                            (SELECT COUNT(*) FROM companies),
                            (SELECT COUNT(*) FROM jobs),
                            (SELECT COUNT(*) FROM actions),
                            (SELECT COUNT(*) FROM events)
                        """
                    ).fetchone()

            result = self.run_cli(
                db_path,
                "report",
                "hygiene",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            with closing(self.connect(db_path)) as connection:
                after_counts = connection.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM companies),
                        (SELECT COUNT(*) FROM jobs),
                        (SELECT COUNT(*) FROM actions),
                        (SELECT COUNT(*) FROM events)
                    """
                ).fetchone()

            self.assertEqual(before_counts, after_counts)
            self.assertIn("Hygiene report as_of=2026-05-02T00:00:00+00:00", result.stdout)
            self.assertIn("Stale actions:", result.stdout)
            self.assertIn("queue=apply", result.stdout)
            self.assertIn("queue=follow_up", result.stdout)
            self.assertIn("queue=classify", result.stdout)
            self.assertIn("age_state=old_unscheduled", result.stdout)
            self.assertIn("Old Apply Co", result.stdout)
            self.assertIn("job=#", result.stdout)
            self.assertIn("Outcome gaps:", result.stdout)
            self.assertIn("issue=rejection_event_status_mismatch", result.stdout)
            self.assertIn("issue=unclassified_rejection", result.stdout)
            self.assertIn("issue=pending_final_disposition", result.stdout)
            self.assertIn("issue=application_submitted_status_mismatch", result.stdout)
            self.assertIn("Event Only Co", result.stdout)
            self.assertNotIn("Future Co", result.stdout)
            self.assertNotIn("Offset Future Co", result.stdout)
            self.assertIn("Companies with recent activity and no next action:", result.stdout)
            self.assertIn("company=#", result.stdout)
            self.assertIn("Quiet Co", result.stdout)
            self.assertNotIn("Cooldown Co", result.stdout)

    def test_report_hygiene_handles_no_data_and_all_clean_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            no_data = self.run_cli(db_path, "report", "hygiene")
            self.assertIn("No command center data.", no_data.stdout)

            self.run_cli(db_path, "company", "add", "Clean Co")
            all_clean = self.run_cli(
                db_path,
                "report",
                "hygiene",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            self.assertIn(
                "All clean: no stale actions, outcome gaps, or active companies "
                "without next action.",
                all_clean.stdout,
            )

    def test_report_hygiene_does_not_migrate_old_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    connection.execute("DROP TABLE query_run_results")
                    connection.execute("DROP TABLE query_runs")
                    connection.execute("DELETE FROM schema_migrations WHERE version = 4")

            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--db-path",
                    str(db_path),
                    "report",
                    "hygiene",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            with closing(self.connect(db_path)) as connection:
                version = connection.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
                ).fetchone()[0]
                query_runs_exists = connection.execute(
                    """
                    SELECT 1
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'query_runs'
                    """
                ).fetchone()

            self.assertEqual(result.returncode, 1)
            self.assertIn("run init before reporting", result.stderr)
            self.assertEqual(version, 3)
            self.assertIsNone(query_runs_exists)

    def test_report_cooldowns_smoke_surfaces_repeated_no_screen_rejection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = self.insert_company(connection, "No Screen Co")
                    job_a = self.insert_job(
                        connection,
                        company_id,
                        title="Senior Product Manager, Lending Platform",
                        lane="FINTECH",
                        status="rejected",
                        application_outcome="rejected_before_screen",
                        rejection_reason="recruiter_screen_risk",
                    )
                    job_b = self.insert_job(
                        connection,
                        company_id,
                        title="Staff Product Manager, Lending Platform",
                        lane="FINTECH",
                        status="rejected",
                        application_outcome="rejected_before_screen",
                        rejection_reason="recruiter_screen_risk",
                    )
                    for job_id in (job_a, job_b):
                        action_id = self.insert_action(
                            connection,
                            company_id,
                            job_id=job_id,
                            queue="classify",
                            kind="classify_outcome",
                            status="done",
                            completed_at="2026-04-10T00:00:00+00:00",
                            notes="classified outcome=rejected_before_screen",
                        )
                        self.insert_event(
                            connection,
                            company_id,
                            job_id=job_id,
                            action_id=action_id,
                            event_type="rejection_received",
                            happened_at="2026-04-10T00:00:00+00:00",
                            notes="Rejected before recruiter screen.",
                        )
                        self.insert_action(
                            connection,
                            company_id,
                            job_id=job_id,
                            queue="research",
                            kind="company_research",
                            status="done",
                            completed_at="2026-04-12T00:00:00+00:00",
                            notes="unrelated later action",
                        )
                    before_counts = connection.execute(
                        """
                        SELECT
                            (SELECT COUNT(*) FROM companies),
                            (SELECT COUNT(*) FROM jobs),
                            (SELECT COUNT(*) FROM actions),
                            (SELECT COUNT(*) FROM events)
                        """
                    ).fetchone()

            result = self.run_cli(
                db_path,
                "report",
                "cooldowns",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            with closing(self.connect(db_path)) as connection:
                after_counts = connection.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM companies),
                        (SELECT COUNT(*) FROM jobs),
                        (SELECT COUNT(*) FROM actions),
                        (SELECT COUNT(*) FROM events)
                    """
                ).fetchone()
                company_status = connection.execute(
                    "SELECT status, cooldown_until FROM companies WHERE id = ?",
                    (company_id,),
                ).fetchone()

            self.assertEqual(before_counts, after_counts)
            self.assertEqual(tuple(company_status), ("active", None))
            self.assertIn(
                "Cooldown recommendations report as_of=2026-05-02T00:00:00+00:00",
                result.stdout,
            )
            self.assertIn("Mode: advisory read-only", result.stdout)
            self.assertIn("Temporary cooldown recommendations:", result.stdout)
            self.assertIn("type=temporary", result.stdout)
            self.assertIn("target=company=#1 No Screen Co", result.stdout)
            self.assertIn("target=role_pattern=FINTECH/lending+platform", result.stdout)
            self.assertIn("signal=repeated_no_screen_rejection", result.stdout)
            self.assertIn("suggested_next_review=2026-05-25T00:00:00+00:00", result.stdout)
            self.assertIn("evidence job=#", result.stdout)
            self.assertIn("outcome=rejected_before_screen", result.stdout)
            self.assertIn("reason=recruiter_screen_risk", result.stdout)
            self.assertIn("event=#", result.stdout)
            self.assertIn("classify/done", result.stdout)
            self.assertNotIn("research/done", result.stdout)

            expired = self.run_cli(
                db_path,
                "report",
                "cooldowns",
                "--as-of",
                "2026-05-26T00:00:00+00:00",
            )

            self.assertIn(
                "No cooldown recommendations from stored outcome evidence.",
                expired.stdout,
            )

    def test_report_cooldowns_surfaces_interview_loop_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = self.insert_company(connection, "Loop Co")
                    job_id = self.insert_job(
                        connection,
                        company_id,
                        title="Senior Product Manager, Workflow Automation",
                        lane="AI",
                        status="rejected",
                        application_outcome="rejected_after_interview",
                        rejection_reason="missing_proof",
                    )
                    self.insert_event(
                        connection,
                        company_id,
                        job_id=job_id,
                        event_type="interview",
                        happened_at="2026-04-18T00:00:00+00:00",
                    )
                    self.insert_event(
                        connection,
                        company_id,
                        job_id=job_id,
                        event_type="rejection_received",
                        happened_at="2026-04-25T00:00:00+00:00",
                    )

            result = self.run_cli(
                db_path,
                "report",
                "cooldowns",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            self.assertIn("signal=interview_loop_cooldown", result.stdout)
            self.assertIn("type=temporary", result.stdout)
            self.assertIn("target=company=#1 Loop Co", result.stdout)
            self.assertIn("outcome=rejected_after_interview", result.stdout)
            self.assertIn("suggested_next_review=2026-08-23T00:00:00+00:00", result.stdout)

    def test_report_cooldowns_surfaces_timing_capacity_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = self.insert_company(connection, "Capacity Co")
                    job_id = self.insert_job(
                        connection,
                        company_id,
                        title="Principal Product Manager, Payments",
                        lane="FINTECH",
                        status="ignored_by_filter",
                        rejection_reason="timing_or_capacity",
                    )
                    self.insert_event(
                        connection,
                        company_id,
                        job_id=job_id,
                        event_type="note",
                        happened_at="2026-04-20T00:00:00+00:00",
                        notes="reason=timing_or_capacity; good in abstract, not worth this month's queue.",
                    )

            result = self.run_cli(
                db_path,
                "report",
                "cooldowns",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            self.assertIn("signal=timing_capacity_cooldown", result.stdout)
            self.assertIn("type=temporary", result.stdout)
            self.assertIn("reason=timing_or_capacity", result.stdout)
            self.assertIn("suggested_next_review=2026-05-20T00:00:00+00:00", result.stdout)

    def test_report_cooldowns_surfaces_durable_low_priority_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = self.insert_company(connection, "Low Priority Co")
                    job_id = self.insert_job(
                        connection,
                        company_id,
                        title="Product Manager, Consumer Growth",
                        lane="AI",
                        status="ignored_by_filter",
                        application_outcome="passed_by_candidate",
                        rejection_reason="low_interest",
                    )
                    self.insert_event(
                        connection,
                        company_id,
                        job_id=job_id,
                        event_type="status_changed",
                        happened_at="2026-04-22T00:00:00+00:00",
                        notes="reason=low_interest; candidate passed; low priority target pattern.",
                    )

            result = self.run_cli(
                db_path,
                "report",
                "cooldowns",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            self.assertIn("Durable pass / low-priority recommendations:", result.stdout)
            self.assertIn("type=durable", result.stdout)
            self.assertIn("signal=durable_low_priority", result.stdout)
            self.assertIn("outcome=passed_by_candidate", result.stdout)
            self.assertIn("reason=low_interest", result.stdout)
            self.assertIn("suggested_next_review=2026-10-19T00:00:00+00:00", result.stdout)

    def test_report_cooldowns_does_not_treat_archival_as_durable_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = self.insert_company(connection, "Archive Co")
                    self.insert_job(
                        connection,
                        company_id,
                        title="Product Manager, Old Role",
                        lane="AI",
                        status="archived",
                        application_outcome="archived_no_action",
                    )

            result = self.run_cli(
                db_path,
                "report",
                "cooldowns",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            self.assertIn(
                "No cooldown recommendations from stored outcome evidence.",
                result.stdout,
            )

    def test_report_cooldowns_excludes_future_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = self.insert_company(connection, "Future Co")
                    for title in (
                        "Senior Product Manager, Platform",
                        "Staff Product Manager, Platform",
                    ):
                        job_id = self.insert_job(
                            connection,
                            company_id,
                            title=title,
                            lane="AI",
                            status="rejected",
                            application_outcome="rejected_before_screen",
                            rejection_reason="recruiter_screen_risk",
                        )
                        self.insert_event(
                            connection,
                            company_id,
                            job_id=job_id,
                            event_type="rejection_received",
                            happened_at="2026-06-01T00:00:00+00:00",
                        )
                    connection.execute(
                        "UPDATE jobs SET updated_at = ?",
                        ("2026-06-01T00:00:00+00:00",),
                    )

            result = self.run_cli(
                db_path,
                "report",
                "cooldowns",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            self.assertIn(
                "No cooldown recommendations from stored outcome evidence.",
                result.stdout,
            )

    def test_report_cooldowns_excludes_future_outcome_update_with_old_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = self.insert_company(connection, "Future Outcome Co")
                    for title in (
                        "Senior Product Manager, Platform",
                        "Staff Product Manager, Platform",
                    ):
                        job_id = self.insert_job(
                            connection,
                            company_id,
                            title=title,
                            lane="AI",
                            status="rejected",
                            application_outcome="rejected_before_screen",
                            rejection_reason="recruiter_screen_risk",
                        )
                        self.insert_event(
                            connection,
                            company_id,
                            job_id=job_id,
                            event_type="note",
                            happened_at="2026-04-01T00:00:00+00:00",
                            notes="Old company note before outcome classification.",
                        )
                    connection.execute(
                        "UPDATE jobs SET updated_at = ?",
                        ("2026-06-01T00:00:00+00:00",),
                    )

            result = self.run_cli(
                db_path,
                "report",
                "cooldowns",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            self.assertIn(
                "No cooldown recommendations from stored outcome evidence.",
                result.stdout,
            )

    def test_report_cooldowns_ignores_unrelated_later_notes_for_signal_date(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = self.insert_company(connection, "Later Note Co")
                    for title in (
                        "Senior Product Manager, Lending Platform",
                        "Staff Product Manager, Lending Platform",
                    ):
                        job_id = self.insert_job(
                            connection,
                            company_id,
                            title=title,
                            lane="FINTECH",
                            status="rejected",
                            application_outcome="rejected_before_screen",
                            rejection_reason="recruiter_screen_risk",
                        )
                        self.insert_event(
                            connection,
                            company_id,
                            job_id=job_id,
                            event_type="rejection_received",
                            happened_at="2026-04-10T00:00:00+00:00",
                            notes="Rejected before recruiter screen.",
                        )
                        self.insert_event(
                            connection,
                            company_id,
                            job_id=job_id,
                            event_type="note",
                            happened_at="2026-04-30T00:00:00+00:00",
                            notes="Unrelated company note.",
                        )

            result = self.run_cli(
                db_path,
                "report",
                "cooldowns",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            self.assertIn("suggested_next_review=2026-05-25T00:00:00+00:00", result.stdout)
            self.assertNotIn("suggested_next_review=2026-06-14T00:00:00+00:00", result.stdout)

    def test_report_cooldowns_ignores_unrelated_notes_for_timing_and_low_interest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    timing_company_id = self.insert_company(connection, "Timing Note Co")
                    timing_job_id = self.insert_job(
                        connection,
                        timing_company_id,
                        title="Principal Product Manager, Payments",
                        lane="FINTECH",
                        status="ignored_by_filter",
                        rejection_reason="timing_or_capacity",
                    )
                    low_interest_company_id = self.insert_company(
                        connection, "Low Interest Note Co"
                    )
                    low_interest_job_id = self.insert_job(
                        connection,
                        low_interest_company_id,
                        title="Product Manager, Consumer Growth",
                        lane="AI",
                        status="ignored_by_filter",
                        application_outcome="passed_by_candidate",
                        rejection_reason="low_interest",
                    )
                    connection.execute(
                        "UPDATE jobs SET updated_at = ? WHERE id IN (?, ?)",
                        (
                            "2026-04-20T00:00:00+00:00",
                            timing_job_id,
                            low_interest_job_id,
                        ),
                    )
                    for company_id, job_id in (
                        (timing_company_id, timing_job_id),
                        (low_interest_company_id, low_interest_job_id),
                    ):
                        self.insert_event(
                            connection,
                            company_id,
                            job_id=job_id,
                            event_type="note",
                            happened_at="2026-04-30T00:00:00+00:00",
                            notes="Unrelated company note.",
                        )

            result = self.run_cli(
                db_path,
                "report",
                "cooldowns",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            self.assertIn(
                "No cooldown recommendations from stored outcome evidence.",
                result.stdout,
            )
            self.assertNotIn("suggested_next_review=2026-05-30T00:00:00+00:00", result.stdout)
            self.assertNotIn("suggested_next_review=2026-10-27T00:00:00+00:00", result.stdout)

    def test_report_proof_gaps_groups_repeated_missing_proof_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    ramp = self.insert_company(connection, "Ramp")
                    stripe = self.insert_company(connection, "Stripe")
                    ramp_job = self.insert_job(
                        connection,
                        ramp,
                        title="Risk Platform PM",
                        lane="FINTECH",
                        status="rejected",
                        rejection_reason="missing_proof",
                        application_outcome="rejected_before_screen",
                        artifact_opportunity="payments risk controls",
                    )
                    stripe_job = self.insert_job(
                        connection,
                        stripe,
                        title="Product Lead, Controls",
                        lane="FINTECH",
                        status="ignored_by_filter",
                        rejection_reason="missing_proof",
                        artifact_opportunity="payments risk controls",
                    )
                    ramp_gap = self.insert_gap(
                        connection,
                        ramp,
                        ramp_job,
                        description="Needs proof: payments risk controls",
                        severity="high",
                        resolution_action="Build payments risk controls case study.",
                    )
                    stripe_gap = self.insert_gap(
                        connection,
                        stripe,
                        stripe_job,
                        description="Missing proof: payments risk controls",
                        severity="medium",
                    )
                    self.insert_action(
                        connection,
                        ramp,
                        job_id=ramp_job,
                        gap_id=ramp_gap,
                        queue="artifact",
                        kind="build_case_study",
                        notes="payments risk controls case study",
                    )
                    self.insert_event(
                        connection,
                        stripe,
                        job_id=stripe_job,
                        gap_id=stripe_gap,
                        event_type="gap_identified",
                        notes="payments risk controls came up again",
                    )
                    before_counts = connection.execute(
                        """
                        SELECT
                            (SELECT COUNT(*) FROM companies),
                            (SELECT COUNT(*) FROM jobs),
                            (SELECT COUNT(*) FROM gaps),
                            (SELECT COUNT(*) FROM actions),
                            (SELECT COUNT(*) FROM events)
                        """
                    ).fetchone()

            result = self.run_cli(
                db_path,
                "report",
                "proof-gaps",
                "--as-of",
                "2026-05-02T00:00:00+00:00",
            )

            with closing(self.connect(db_path)) as connection:
                after_counts = connection.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM companies),
                        (SELECT COUNT(*) FROM jobs),
                        (SELECT COUNT(*) FROM gaps),
                        (SELECT COUNT(*) FROM actions),
                        (SELECT COUNT(*) FROM events)
                    """
                ).fetchone()

            self.assertEqual(before_counts, after_counts)
            self.assertIn(
                "Proof gap report as_of=2026-05-02T00:00:00+00:00",
                result.stdout,
            )
            self.assertIn("payments risk controls", result.stdout)
            self.assertIn("strength=recurring", result.stdout)
            self.assertIn("improvement=artifact", result.stdout)
            self.assertIn("routing=linear_candidate", result.stdout)
            self.assertIn("jobs=2", result.stdout)
            self.assertIn("companies=2", result.stdout)
            self.assertIn("lanes=FINTECH", result.stdout)
            self.assertIn("statuses=ignored_by_filter,rejected", result.stdout)
            self.assertIn("outcomes=rejected_before_screen", result.stdout)
            self.assertIn("reasons=missing_proof", result.stdout)
            self.assertIn("gap=#", result.stdout)
            self.assertIn("action=#", result.stdout)
            self.assertIn("event=#", result.stdout)

    def test_report_proof_gaps_ranks_one_offs_below_recurring_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_a = self.insert_company(connection, "Company A")
                    company_b = self.insert_company(connection, "Company B")
                    company_c = self.insert_company(connection, "Company C")
                    job_a = self.insert_job(
                        connection,
                        company_a,
                        lane="AI",
                        rejection_reason="missing_proof",
                        artifact_opportunity="workflow automation ROI",
                    )
                    job_b = self.insert_job(
                        connection,
                        company_b,
                        lane="AI",
                        rejection_reason="missing_proof",
                        artifact_opportunity="ROI from workflow automation",
                    )
                    job_c = self.insert_job(
                        connection,
                        company_c,
                        lane="FINTECH",
                        rejection_reason="missing_proof",
                        artifact_opportunity="treasury operations",
                    )
                    self.insert_gap(
                        connection,
                        company_a,
                        job_a,
                        description="Needs proof: workflow automation ROI",
                    )
                    self.insert_gap(
                        connection,
                        company_b,
                        job_b,
                        description="Missing proof: ROI from workflow automation",
                    )
                    self.insert_gap(
                        connection,
                        company_c,
                        job_c,
                        description="Missing proof: treasury operations",
                    )

            result = self.run_cli(db_path, "report", "proof-gaps")

            recurring_index = result.stdout.index("workflow automation roi")
            one_off_index = result.stdout.index("treasury operations")
            self.assertLess(recurring_index, one_off_index)
            self.assertIn(
                "workflow automation roi | strength=recurring",
                result.stdout,
            )
            self.assertIn("improvement=resume lane | routing=sqlite", result.stdout)
            self.assertIn("treasury operations | strength=one_off", result.stdout)
            self.assertIn("Lower-signal one-offs:", result.stdout)

    def test_action_next_includes_execution_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = self.insert_company(connection, "Stripe")
                    connection.execute(
                        """
                        UPDATE companies
                        SET tier = 1, lanes = 'FINTECH', last_checked_at = ?
                        WHERE id = ?
                        """,
                        ("2026-01-01T00:00:00+00:00", company_id),
                    )
                    job_id = self.insert_job(connection, company_id)
                    connection.execute(
                        """
                        UPDATE jobs
                        SET status = 'ready_to_apply',
                            fit_score = 91,
                            lane = 'FINTECH',
                            canonical_url = 'https://example.com/stripe-job',
                            recommended_resume = 'YOUR_PROFILE/Fintech/FINTECH.md',
                            application_folder = 'APPLICATIONS/READY_TO_APPLY/Stripe_PM'
                        WHERE id = ?
                        """,
                        (job_id,),
                    )
                    self.insert_action(
                        connection,
                        company_id,
                        job_id=job_id,
                        due_at="2026-01-02T00:00:00+00:00",
                        notes="Submit base FINTECH package.",
                    )

            result = self.run_cli(db_path, "action", "next", "--limit", "1")

            self.assertIn("Stripe / Product Lead", result.stdout)
            self.assertIn("due_state=stale", result.stdout)
            self.assertIn("company=status=active,tier=1,lanes=FINTECH", result.stdout)
            self.assertIn(
                "job_context=status=ready_to_apply,fit=91,lane=FINTECH",
                result.stdout,
            )
            self.assertIn("url=https://example.com/stripe-job", result.stdout)
            self.assertIn("resume=YOUR_PROFILE/Fintech/FINTECH.md", result.stdout)
            self.assertIn("materials=APPLICATIONS/READY_TO_APPLY/Stripe_PM", result.stdout)
            self.assertIn("note=Submit base FINTECH package.", result.stdout)

    def test_init_migrates_duplicate_open_actions_before_dedupe_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    connection.execute("DROP INDEX idx_actions_open_dedupe")
                    connection.execute("DELETE FROM schema_migrations WHERE version >= 2")
                    company_id = self.insert_company(connection, "Company A")
                    self.insert_action(connection, company_id)
                    self.insert_action(connection, company_id)

            migrated = self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                actions = connection.execute(
                    """
                    SELECT status, notes
                    FROM actions
                    ORDER BY id
                    """
                ).fetchall()
                versions = connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()
                with self.assertRaises(sqlite3.IntegrityError):
                    self.insert_action(connection, company_id)

            self.assertIn("schema_version=4", migrated.stdout)
            self.assertEqual([row[0] for row in versions], [1, 2, 3, 4])
            self.assertEqual(actions[0][0], "queued")
            self.assertEqual(actions[1][0], "skipped")
            self.assertIn("schema v2 migration", actions[1][1])

    def test_init_migrates_existing_database_to_query_run_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    connection.execute("DROP TABLE query_run_results")
                    connection.execute("DROP TABLE query_runs")
                    connection.execute("DELETE FROM schema_migrations WHERE version = 4")

            migrated = self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                version = connection.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0]
                query_run_count = connection.execute(
                    "SELECT COUNT(*) FROM query_runs"
                ).fetchone()[0]

            self.assertIn("schema_version=4", migrated.stdout)
            self.assertEqual(version, 4)
            self.assertEqual(query_run_count, 0)

    def test_status_reports_uninitialized_database_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "missing.sqlite"

            result = subprocess.run(
                [sys.executable, str(CLI), "--db-path", str(db_path), "status"],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Database not initialized:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_query_import_file_is_idempotent_and_reports_job_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Stripe")
            self.run_cli(
                db_path,
                "job",
                "add",
                "Stripe",
                "Senior Product Manager",
                "--url",
                "https://jobs.example.com/stripe/123?utm=ignored",
                "--source",
                "linkedin",
                "--source-job-id",
                "123",
            )
            payload_path = Path(tmpdir) / "query-run.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "source": "linkedin",
                        "pack": "fintech-core",
                        "query": "senior product manager payroll",
                        "sort_mode": "relevance",
                        "status": "completed",
                        "raw_source_reference": "linkedin-search-abc",
                        "results": [
                            {
                                "company": "Stripe",
                                "title": "Senior Product Manager",
                                "url": "https://jobs.example.com/stripe/123",
                                "source_job_id": "123",
                                "status": "accepted",
                            },
                            {
                                "company": "Mercury",
                                "title": "Product Manager, Banking Platform",
                                "url": "https://jobs.example.com/mercury/456",
                                "status": "accepted",
                            },
                            {
                                "company": "SlowCo",
                                "title": "Growth Product Manager",
                                "status": "rejected",
                                "notes": "consumer growth role",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            first = self.run_cli(db_path, "query", "import", "--file", str(payload_path))
            second = self.run_cli(db_path, "query", "import", "--file", str(payload_path))
            query_run_id = self.stdout_id(first)
            listed = self.run_cli(db_path, "query", "list")
            shown = self.run_cli(db_path, "query", "show", str(query_run_id))

            with closing(self.connect(db_path)) as connection:
                job_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                run_count = connection.execute("SELECT COUNT(*) FROM query_runs").fetchone()[0]
                result_rows = connection.execute(
                    """
                    SELECT result_status, duplicate_job_id
                    FROM query_run_results
                    ORDER BY ordinal
                    """
                ).fetchall()

            self.assertIn(f"query run created id={query_run_id}", first.stdout)
            self.assertIn(f"query run updated id={query_run_id}", second.stdout)
            self.assertIn("results=3 accepted=1 rejected=1 duplicates=1", first.stdout)
            self.assertIn("source=linkedin", listed.stdout)
            self.assertIn("pack=fintech-core", listed.stdout)
            self.assertIn("status=completed", listed.stdout)
            self.assertIn("results=3", listed.stdout)
            self.assertIn("accepted=1", listed.stdout)
            self.assertIn("rejected=1", listed.stdout)
            self.assertIn("duplicates=1", listed.stdout)
            self.assertIn("Query run:", shown.stdout)
            self.assertIn("duplicate_job=#1", shown.stdout)
            self.assertIn("reason=normalized_url", shown.stdout)
            self.assertEqual(job_count, 1)
            self.assertEqual(run_count, 1)
            self.assertEqual(
                result_rows,
                [("duplicate", 1), ("accepted", None), ("rejected", None)],
            )

    def test_query_import_counts_persisted_rows_after_result_key_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            payload_path = Path(tmpdir) / "query-run.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "source": "linkedin",
                        "pack": "ai-core",
                        "query": "ai workflow product manager",
                        "results": [
                            {
                                "company": "OpenAI",
                                "title": "Product Manager, Workflows",
                                "url": "https://jobs.example.com/openai/pm-workflows?utm=one",
                                "status": "accepted",
                            },
                            {
                                "company": "OpenAI",
                                "title": "Product Manager, Workflows",
                                "url": "https://jobs.example.com/openai/pm-workflows#saved",
                                "status": "rejected",
                                "notes": "same listing saved twice",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_cli(db_path, "query", "import", "--file", str(payload_path))
            query_run_id = self.stdout_id(result)

            with closing(self.connect(db_path)) as connection:
                run = connection.execute(
                    """
                    SELECT result_count, accepted_count, rejected_count, duplicate_count
                    FROM query_runs
                    WHERE id = ?
                    """,
                    (query_run_id,),
                ).fetchone()
                result_rows = connection.execute(
                    """
                    SELECT result_status, notes
                    FROM query_run_results
                    WHERE query_run_id = ?
                    """,
                    (query_run_id,),
                ).fetchall()

            self.assertIn("results=1 accepted=0 rejected=1 duplicates=0", result.stdout)
            self.assertEqual(tuple(run), (1, 0, 1, 0))
            self.assertEqual(result_rows, [("rejected", "same listing saved twice")])

    def test_query_import_accepts_explicit_fields_and_result_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            result = self.run_cli(
                db_path,
                "query",
                "import",
                "--source",
                "manual-board",
                "--pack",
                "ai-core",
                "--query",
                "ai workflow product manager",
                "--sort-mode",
                "date",
                "--raw-source-reference",
                "manual-2026-04-29",
                "--result-json",
                json.dumps(
                    {
                        "company": "OpenAI",
                        "title": "Product Manager, Workflows",
                        "url": "https://jobs.example.com/openai/pm-workflows",
                        "decision": "accepted",
                    }
                ),
            )
            query_run_id = self.stdout_id(result)
            shown = self.run_cli(db_path, "query", "show", str(query_run_id))

            self.assertIn("query run created", result.stdout)
            self.assertIn("results=1 accepted=1 rejected=0 duplicates=0", result.stdout)
            self.assertIn("source=manual-board", shown.stdout)
            self.assertIn("pack=ai-core", shown.stdout)
            self.assertIn("sort=date", shown.stdout)
            self.assertIn("OpenAI | Product Manager, Workflows", shown.stdout)

    def test_query_import_records_manual_run_without_result_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            result = self.run_cli(
                db_path,
                "query",
                "import",
                "--source",
                "linkedin_mcp",
                "--pack",
                "fintech-core",
                "--query",
                "product manager accounting",
                "--status",
                "partial",
                "--result-count",
                "12",
                "--notes",
                "saved summary only",
            )
            query_run_id = self.stdout_id(result)
            shown = self.run_cli(db_path, "query", "show", str(query_run_id))

            self.assertIn("results=12 accepted=0 rejected=0 duplicates=0", result.stdout)
            self.assertIn("Counts: results=12 accepted=0 rejected=0 duplicates=0", shown.stdout)
            self.assertIn("- none", shown.stdout)

    def test_query_list_rejects_non_positive_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--db-path",
                    str(db_path),
                    "query",
                    "list",
                    "--limit",
                    "0",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("query list --limit must be a positive integer", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_query_packs_default_list_excludes_exception_packs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"

            result = self.run_cli(db_path, "query", "packs", "list", "--default-only")

            self.assertEqual(
                result.stdout.splitlines(),
                [
                    "FINTECH\tdefault\trepeatable\tqueries=6\tFintech / Platform",
                    "AI\tdefault\trepeatable\tqueries=6\tAI / Workflow",
                ],
            )
            self.assertNotIn("ACCESS", result.stdout)

    def test_query_pack_registry_rejects_non_default_lane_as_repeatable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "query_packs.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "packs": [
                            {
                                "name": "FINTECH",
                                "label": "Fintech / Platform",
                                "default_repeatable": True,
                                "description": "Default lane.",
                                "queries": ["senior product manager payroll"],
                            },
                            {
                                "name": "AI",
                                "label": "AI / Workflow",
                                "default_repeatable": True,
                                "description": "Default lane.",
                                "queries": ["senior product manager ai workflow"],
                            },
                            {
                                "name": "ACCESS",
                                "label": "Access / Trust Workflow",
                                "default_repeatable": True,
                                "description": "Exception lane.",
                                "queries": ["product manager access reviews"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Default repeatable query packs must be exactly AI and FINTECH",
            ):
                JOB_SEARCH.load_query_pack_registry(registry_path)

    def test_query_pack_registry_rejects_blank_queries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "query_packs.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "packs": [
                            {
                                "name": "FINTECH",
                                "label": "Fintech / Platform",
                                "default_repeatable": True,
                                "description": "Default lane.",
                                "queries": ["senior product manager payroll"],
                            },
                            {
                                "name": "AI",
                                "label": "AI / Workflow",
                                "default_repeatable": True,
                                "description": "Default lane.",
                                "queries": [""],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Query pack AI includes a blank query",
            ):
                JOB_SEARCH.load_query_pack_registry(registry_path)

    def test_query_pack_show_reads_exception_pack_queries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"

            result = self.run_cli(db_path, "query", "packs", "show", "ACCESS")

            self.assertIn("name=ACCESS", result.stdout)
            self.assertIn("type=exception", result.stdout)
            self.assertIn("default_repeatable=false", result.stdout)
            self.assertIn("product manager access reviews", result.stdout)

    def test_report_query_pack_tuning_uses_reviewed_results_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(
                db_path,
                "company",
                "add",
                "ExistingCo",
            )
            self.run_cli(
                db_path,
                "job",
                "add",
                "ExistingCo",
                "Senior Product Manager",
                "--url",
                "https://jobs.example.com/existing/senior-pm",
            )
            registry_before = JOB_SEARCH.QUERY_PACK_REGISTRY_PATH.read_text(
                encoding="utf-8"
            )
            payload_path = Path(tmpdir) / "query-run.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "source": "linkedin_mcp",
                        "pack": "FINTECH",
                        "query": "senior product manager payroll",
                        "notes": "search_noisy: run-level note must not drive tuning",
                        "results": [
                            {
                                "company": "GoodCo",
                                "title": "Senior Product Manager, Payroll",
                                "url": "https://jobs.example.com/good/payroll",
                                "status": "accepted",
                                "notes": "strong payroll platform fit",
                            },
                            {
                                "company": "NoiseCo",
                                "title": "Engineering Manager, Payroll",
                                "url": "https://jobs.example.com/noise/engineering",
                                "status": "rejected",
                                "notes": "search_noisy: people-management-heavy result",
                            },
                            {
                                "company": "ThinCo",
                                "title": "Product Manager",
                                "url": "https://jobs.example.com/thin/pm",
                                "status": "rejected",
                                "notes": "stale_or_thin_result: posting closed or too thin",
                            },
                            {
                                "company": "ExistingCo",
                                "title": "Senior Product Manager",
                                "url": "https://jobs.example.com/existing/senior-pm",
                                "status": "accepted",
                            },
                            {
                                "company": "PendingCo",
                                "title": "Product Manager, Payroll",
                                "url": "https://jobs.example.com/pending/payroll",
                                "status": "pending",
                                "notes": "search_noisy: pending raw hit must not drive tuning",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.run_cli(db_path, "query", "import", "--file", str(payload_path))

            result = self.run_cli(db_path, "report", "query-pack-tuning")

            self.assertIn("reviewed=4 pending_ignored=1", result.stdout)
            self.assertIn("Noisy queries:", result.stdout)
            self.assertIn("noisy=1 noisy_rate=25.0%", result.stdout)
            self.assertIn("Stale/thin sources:", result.stdout)
            self.assertIn("stale_thin=1 stale_thin_rate=25.0%", result.stdout)
            self.assertIn("Duplicate patterns:", result.stdout)
            self.assertIn("duplicates=1 duplicate_rate=25.0%", result.stdout)
            self.assertIn("Strong accepted patterns:", result.stdout)
            self.assertIn("accepted=1 accepted_rate=25.0%", result.stdout)
            self.assertIn("edit=tighten_or_pause", result.stdout)
            self.assertIn("edit=prefer_canonical_or_official_source", result.stdout)
            self.assertIn("edit=dedupe_or_reduce_overlap", result.stdout)
            self.assertIn("edit=preserve_or_expand", result.stdout)
            self.assertNotIn("PendingCo", result.stdout)
            self.assertEqual(
                registry_before,
                JOB_SEARCH.QUERY_PACK_REGISTRY_PATH.read_text(encoding="utf-8"),
            )

    def test_report_query_pack_tuning_preserves_exception_reason_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            payload_path = Path(tmpdir) / "access-query-run.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "source": "manual_browser",
                        "pack": "ACCESS",
                        "query": "product manager access reviews",
                        "notes": "reason=specific access/trust target role at Okta",
                        "results": [
                            {
                                "company": "Okta",
                                "title": "Product Manager, Access Reviews",
                                "url": "https://jobs.example.com/okta/access-reviews",
                                "status": "accepted",
                                "notes": "access workflow match",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.run_cli(db_path, "query", "import", "--file", str(payload_path))

            result = self.run_cli(db_path, "report", "query-pack-tuning")

            self.assertIn("pack=ACCESS", result.stdout)
            self.assertIn("edit=preserve_exception_guardrail", result.stdout)
            self.assertIn(
                "preserve explicit exception reason: "
                "reason=specific access/trust target role at Okta",
                result.stdout,
            )

    def test_report_query_pack_tuning_flags_exception_pack_without_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            fintech_payload_path = Path(tmpdir) / "fintech-query-run.json"
            fintech_payload_path.write_text(
                json.dumps(
                    {
                        "source": "linkedin_mcp",
                        "pack": "FINTECH",
                        "query": "senior product manager payroll",
                        "results": [
                            {
                                "company": "GoodCo",
                                "title": "Senior Product Manager, Payroll",
                                "url": "https://jobs.example.com/good/payroll",
                                "status": "accepted",
                                "notes": "strong payroll platform fit",
                            },
                            {
                                "company": "NoiseCo",
                                "title": "Engineering Manager, Payroll",
                                "url": "https://jobs.example.com/noise/engineering",
                                "status": "rejected",
                                "notes": "search_noisy: people-management-heavy result",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.run_cli(db_path, "query", "import", "--file", str(fintech_payload_path))
            payload_path = Path(tmpdir) / "access-query-run.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "source": "manual_browser",
                        "pack": "ACCESS",
                        "query": "product manager access reviews",
                        "notes": "search_noisy: broad exception run without explicit rationale",
                        "results": [
                            {
                                "company": "Okta",
                                "title": "Product Manager, Access Reviews",
                                "url": "https://jobs.example.com/okta/access-reviews",
                                "status": "accepted",
                                "notes": "access workflow match",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.run_cli(db_path, "query", "import", "--file", str(payload_path))

            result = self.run_cli(db_path, "report", "query-pack-tuning", "--limit", "1")

            self.assertIn("pack=ACCESS", result.stdout)
            self.assertIn("edit=preserve_exception_guardrail", result.stdout)
            self.assertIn(
                "do not promote or repeat until an explicit exception reason is recorded",
                result.stdout,
            )

    def test_report_strategy_feedback_composes_weekly_recommendations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    payroll_a = self.insert_company(connection, "Payroll A")
                    payroll_b = self.insert_company(connection, "Payroll B")
                    ai_workflow = self.insert_company(connection, "AI Workflow Co")
                    job_a = self.insert_job(
                        connection,
                        payroll_a,
                        title="Senior Product Manager, Payroll Controls",
                        lane="FINTECH",
                        status="ignored_by_filter",
                        rejection_reason="missing_proof",
                    )
                    job_b = self.insert_job(
                        connection,
                        payroll_b,
                        title="Product Manager, Payroll Reporting",
                        lane="FINTECH",
                        status="ignored_by_filter",
                        rejection_reason="missing_proof",
                    )
                    job_c = self.insert_job(
                        connection,
                        ai_workflow,
                        title="Product Manager, AI Workflow",
                        lane="AI",
                        status="applied",
                        application_outcome="pending_response",
                    )
                    self.insert_gap(
                        connection,
                        payroll_a,
                        job_a,
                        description="Needs payroll controls case study",
                        severity="high",
                    )
                    self.insert_gap(
                        connection,
                        payroll_b,
                        job_b,
                        description="Needs payroll controls case study",
                        severity="high",
                    )
                    self.insert_gap(
                        connection,
                        ai_workflow,
                        job_c,
                        description="Needs AI evals demo",
                        severity="medium",
                    )
                    self.insert_action(
                        connection,
                        ai_workflow,
                        job_id=job_c,
                        queue="screen",
                        kind="screen_role",
                        status="done",
                        completed_at="2026-04-30T00:00:00+00:00",
                    )
                    self.insert_event(
                        connection,
                        ai_workflow,
                        job_id=job_c,
                        event_type="application_submitted",
                        happened_at="2026-04-30T00:00:00+00:00",
                        notes="Submitted with AI resume.",
                    )
                    connection.execute(
                        """
                        INSERT INTO query_runs(
                            source, pack, query_text, status, result_count,
                            accepted_count, rejected_count, duplicate_count,
                            import_key, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "linkedin_mcp",
                            "FINTECH",
                            "senior product manager payroll",
                            "completed",
                            2,
                            1,
                            1,
                            0,
                            "strategy-feedback-fixture",
                            "2026-04-30T00:00:00+00:00",
                            "2026-04-30T00:00:00+00:00",
                        ),
                    )
                    query_run_id = self.last_id(connection)
                    connection.execute(
                        """
                        INSERT INTO query_run_results(
                            query_run_id, ordinal, company_name, title,
                            canonical_url, result_status, notes, result_key,
                            created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            query_run_id,
                            1,
                            "Good Payroll Co",
                            "Senior Product Manager, Payroll",
                            "https://jobs.example.com/good/payroll",
                            "accepted",
                            "strong payroll platform fit",
                            "accepted",
                            "2026-04-30T00:00:00+00:00",
                            "2026-04-30T00:00:00+00:00",
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO query_run_results(
                            query_run_id, ordinal, company_name, title,
                            canonical_url, result_status, notes, result_key,
                            created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            query_run_id,
                            2,
                            "Noise Co",
                            "Engineering Manager, Payroll",
                            "https://jobs.example.com/noise/eng-manager",
                            "rejected",
                            "search_noisy: people-management-heavy result",
                            "rejected",
                            "2026-04-30T00:00:00+00:00",
                            "2026-04-30T00:00:00+00:00",
                        ),
                    )
            registry_before = JOB_SEARCH.QUERY_PACK_REGISTRY_PATH.read_text(
                encoding="utf-8"
            )

            result = self.run_cli(
                db_path,
                "report",
                "strategy-feedback",
                "--as-of",
                "2026-05-07T00:00:00+00:00",
                "--days",
                "30",
            )

            self.assertIn("Strategy feedback report", result.stdout)
            self.assertIn("Evidence:", result.stdout)
            self.assertIn("- outcomes:", result.stdout)
            self.assertIn("- funnel_metrics:", result.stdout)
            self.assertIn("- cooldowns:", result.stdout)
            self.assertIn("- proof_gaps:", result.stdout)
            self.assertIn("- target_company_coverage:", result.stdout)
            self.assertIn("- query_quality:", result.stdout)
            self.assertIn("Recommendations:", result.stdout)
            self.assertIn("decision=keep | target=query-pack config", result.stdout)
            self.assertIn("decision=change | target=query-pack config", result.stdout)
            self.assertIn("decision=change | target=Linear follow-up", result.stdout)
            self.assertIn("decision=defer | target=Linear follow-up", result.stdout)
            self.assertIn("operator_action=", result.stdout)
            self.assertIn("$job-search", result.stdout)
            self.assertIn("$job-apply", result.stdout)
            self.assertEqual(
                registry_before,
                JOB_SEARCH.QUERY_PACK_REGISTRY_PATH.read_text(encoding="utf-8"),
            )

    def test_company_import_adds_multiple_researched_companies_and_sources(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            payload_path = Path(tmpdir) / "companies.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "companies": [
                            {
                                "name": "Ramp",
                                "tier": 1,
                                "lanes": ["FINTECH", "AI"],
                                "why_interesting": "Finance automation.",
                                "fit_thesis": "Strong platform fit.",
                                "target_roles": ["Senior Product Manager"],
                                "career_url": "https://ramp.com/careers",
                                "ats_type": "greenhouse",
                                "ats_source_key": "ramp",
                                "notes": "Tier 1 target.",
                            },
                            {
                                "company_name": "Mercury",
                                "tier": "2",
                                "lane": "FINTECH",
                                "target_role": "Product Manager",
                                "ats": {
                                    "type": "lever",
                                    "key": "mercury",
                                    "url": "https://api.lever.co/v0/postings/mercury?mode=json",
                                },
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            self.run_cli(db_path, "init")
            result = self.run_cli(
                db_path, "company", "import", "--file", str(payload_path)
            )

            self.assertIn("row=1 | company=Ramp | company_created | source_created", result.stdout)
            self.assertIn("row=2 | company=Mercury | company_created | source_created", result.stdout)
            self.assertIn("company_created=2", result.stdout)
            self.assertIn("source_created=2", result.stdout)

            with closing(self.connect(db_path)) as connection:
                companies = connection.execute(
                    """
                    SELECT name, tier, lanes, target_roles, ats_type
                    FROM companies
                    ORDER BY name_key
                    """
                ).fetchall()
                sources = connection.execute(
                    """
                    SELECT companies.name, source_type, source_key, source_url
                    FROM company_sources
                    JOIN companies ON companies.id = company_sources.company_id
                    ORDER BY companies.name_key
                    """
                ).fetchall()

            self.assertEqual(
                companies,
                [
                    ("Mercury", 2, "FINTECH", "Product Manager", "lever"),
                    ("Ramp", 1, "FINTECH, AI", "Senior Product Manager", "greenhouse"),
                ],
            )
            self.assertEqual(
                sources,
                [
                    (
                        "Mercury",
                        "lever",
                        "mercury",
                        "https://api.lever.co/v0/postings/mercury?mode=json",
                    ),
                    ("Ramp", "greenhouse", "ramp", None),
                ],
            )

    def test_company_import_rerun_is_idempotent_for_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            payload_path = Path(tmpdir) / "companies.json"
            payload_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "Ashby Co",
                            "ats_type": "ashby",
                            "ats_source_key": "ashby-co",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            self.run_cli(db_path, "init")
            first = self.run_cli(
                db_path, "company", "import", "--file", str(payload_path)
            )
            second = self.run_cli(
                db_path, "company", "import", "--file", str(payload_path)
            )

            self.assertIn("company_created", first.stdout)
            self.assertIn("source_created", first.stdout)
            self.assertIn("company_updated", second.stdout)
            self.assertIn("source_existing", second.stdout)

            with closing(self.connect(db_path)) as connection:
                company_count = connection.execute(
                    "SELECT COUNT(*) FROM companies"
                ).fetchone()[0]
                source_count = connection.execute(
                    "SELECT COUNT(*) FROM company_sources"
                ).fetchone()[0]

            self.assertEqual(company_count, 1)
            self.assertEqual(source_count, 1)

    def test_company_import_missing_source_details_needs_manual_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            payload_path = Path(tmpdir) / "companies.json"
            payload_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "Plaid",
                            "tier": 1,
                            "lanes": "FINTECH",
                            "why_interesting": "Financial data platform.",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            self.run_cli(db_path, "init")
            result = self.run_cli(
                db_path, "company", "import", "--file", str(payload_path)
            )

            self.assertIn("company_created", result.stdout)
            self.assertIn("needs_manual_source", result.stdout)
            with closing(self.connect(db_path)) as connection:
                source_count = connection.execute(
                    "SELECT COUNT(*) FROM company_sources"
                ).fetchone()[0]
            self.assertEqual(source_count, 0)

    def test_company_import_unsupported_ats_does_not_mutate_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            payload_path = Path(tmpdir) / "companies.json"
            payload_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "Workday Co",
                            "ats_type": "workday",
                            "ats_source_key": "workday-co",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            self.run_cli(db_path, "init")
            result = self.run_cli(
                db_path, "company", "import", "--file", str(payload_path)
            )

            self.assertIn("unsupported_ats", result.stdout)
            self.assertIn("ats_type=workday", result.stdout)
            with closing(self.connect(db_path)) as connection:
                source_count = connection.execute(
                    "SELECT COUNT(*) FROM company_sources"
                ).fetchone()[0]
            self.assertEqual(source_count, 0)

    def test_company_import_continues_after_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            payload_path = Path(tmpdir) / "companies.json"
            payload_path.write_text(
                json.dumps(
                    [
                        {"tier": 1, "ats_type": "greenhouse", "ats_source_key": "missing"},
                        "not an object",
                        {
                            "name": "Valid Co",
                            "ats_type": "greenhouse",
                            "ats_source_key": "valid-co",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            self.run_cli(db_path, "init")
            result = self.run_cli(
                db_path, "company", "import", "--file", str(payload_path)
            )

            self.assertIn("row=1 | company=unknown | invalid_row | invalid_row", result.stdout)
            self.assertIn("row=2 | company=unknown | invalid_row | invalid_row", result.stdout)
            self.assertIn("row=3 | company=Valid Co | company_created | source_created", result.stdout)
            with closing(self.connect(db_path)) as connection:
                companies = connection.execute("SELECT name FROM companies").fetchall()
                sources = connection.execute(
                    "SELECT source_type, source_key FROM company_sources"
                ).fetchall()

            self.assertEqual(companies, [("Valid Co",)])
            self.assertEqual(sources, [("greenhouse", "valid-co")])

    def test_company_import_preserves_absent_existing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            payload_path = Path(tmpdir) / "companies.json"
            payload_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "Stripe",
                            "fit_thesis": "Updated thesis.",
                            "ats_type": "greenhouse",
                            "ats_source_key": "stripe",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            self.run_cli(db_path, "init")
            self.run_cli(
                db_path,
                "company",
                "add",
                "Stripe",
                "--tier",
                "1",
                "--lanes",
                "FINTECH",
                "--why-interesting",
                "Existing why.",
                "--target-roles",
                "Product Manager",
            )
            result = self.run_cli(
                db_path, "company", "import", "--file", str(payload_path)
            )

            self.assertIn("company_updated", result.stdout)
            with closing(self.connect(db_path)) as connection:
                company = connection.execute(
                    """
                    SELECT tier, lanes, why_interesting, fit_thesis, target_roles
                    FROM companies
                    WHERE name_key = ?
                    """,
                    ("stripe",),
                ).fetchone()

            self.assertEqual(
                tuple(company),
                (
                    1,
                    "FINTECH",
                    "Existing why.",
                    "Updated thesis.",
                    "Product Manager",
                ),
            )

    def test_query_run_rejects_exception_pack_without_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"

            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--db-path",
                    str(db_path),
                    "query",
                    "run",
                    "--source",
                    "manual_browser",
                    "--pack",
                    "ACCESS",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Query pack ACCESS is an exception pack", result.stderr)
            self.assertIn("require --reason", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_query_run_allows_default_pack_without_reason_and_exception_with_reason(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"

            fintech = self.run_cli(
                db_path,
                "query",
                "run",
                "--source",
                "linkedin_mcp",
                "--pack",
                "FINTECH",
                "--limit",
                "25",
            )
            access = self.run_cli(
                db_path,
                "query",
                "run",
                "--source",
                "manual_browser",
                "--pack",
                "ACCESS",
                "--reason",
                "specific access target role",
            )

            self.assertIn(
                "query run prepared source=linkedin_mcp "
                "pack=FINTECH type=default limit=25",
                fintech.stdout,
            )
            self.assertIn("senior product manager payroll", fintech.stdout)
            self.assertIn(
                "query run prepared source=manual_browser pack=ACCESS type=exception",
                access.stdout,
            )
            self.assertIn("reason=specific access target role", access.stdout)

    def test_import_pipeline_preserves_legacy_roles_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            pipeline_path = Path(tmpdir) / "job_pipeline.jsonl"
            records = [
                {
                    "id": "url:https://example.com/stripe-baas",
                    "company": "Stripe",
                    "role": "Product Manager, Banking as a Service",
                    "status": "ready_to_apply",
                    "lane": "FINTECH",
                    "source": "linkedin",
                    "job_url": "https://example.com/stripe-baas?ref=linkedin",
                    "location": "United States (Remote)",
                    "recommendation": "apply",
                    "summary": "Financial infrastructure role.",
                    "risks": "Direct issuing depth is lighter.",
                    "jd_path": "APPLICATIONS/READY_TO_APPLY/Stripe_PM/JD.md",
                    "qa_path": "APPLICATIONS/READY_TO_APPLY/Stripe_PM/QA.md",
                    "created_at": "2026-04-22T03:41:35+00:00",
                    "updated_at": "2026-04-22T04:13:15+00:00",
                    "last_screened_at": "2026-04-22T04:13:15+00:00",
                },
                {
                    "id": "url:https://example.com/stripe-payments",
                    "company": "Stripe",
                    "role": "Product Manager, Payments",
                    "status": "watch",
                    "lane": "FINTECH",
                    "source": "linkedin",
                    "job_url": "https://example.com/stripe-payments",
                    "recommendation": "low-priority_apply",
                    "created_at": "2026-04-22T03:41:35+00:00",
                    "updated_at": "2026-04-22T04:13:15+00:00",
                },
                {
                    "id": "url:https://example.com/amazon-pv",
                    "company": "Amazon",
                    "role": "Senior Product Manager - Tech, Prime Video Financial Systems",
                    "status": "applied",
                    "lane": "FINTECH",
                    "source": "amazon_jobs",
                    "job_url": "https://example.com/amazon-pv",
                    "recommendation": "apply",
                    "user_action": "Applied.",
                    "created_at": "2026-04-27T00:57:33+00:00",
                    "updated_at": "2026-04-27T01:03:25+00:00",
                    "last_screened_at": "2026-04-27T01:03:25+00:00",
                },
                {
                    "id": "url:https://example.com/relo",
                    "company": "Relo Metrics",
                    "role": "Senior Product Manager",
                    "status": "screened_out",
                    "lane": "PASS",
                    "source": "linkedin",
                    "job_url": "https://example.com/relo",
                    "recommendation": "pass",
                    "risks": "Comp below floor.",
                    "created_at": "2026-04-28T21:50:20+00:00",
                    "updated_at": "2026-04-28T21:50:41+00:00",
                },
            ]
            pipeline_path.write_text(
                "\n".join(json.dumps(record) for record in records),
                encoding="utf-8",
            )

            self.run_cli(db_path, "init")
            first = self.run_cli(
                db_path,
                "import-pipeline",
                "--path",
                str(pipeline_path),
            )
            second = self.run_cli(
                db_path,
                "import-pipeline",
                "--path",
                str(pipeline_path),
            )

            self.assertIn("companies_created=3", first.stdout)
            self.assertIn("jobs_imported=4", first.stdout)
            self.assertIn("duplicates_skipped=0", first.stdout)
            self.assertIn("companies_created=0", second.stdout)
            self.assertIn("jobs_imported=0", second.stdout)
            self.assertIn("duplicates_skipped=4", second.stdout)

            with closing(self.connect(db_path)) as connection:
                jobs = connection.execute(
                    """
                    SELECT companies.name, jobs.title, jobs.status, jobs.lane,
                        jobs.recommended_resume, jobs.materials_status,
                        jobs.application_folder, jobs.application_outcome
                    FROM jobs
                    JOIN companies ON companies.id = jobs.company_id
                    ORDER BY companies.name, jobs.title
                    """
                ).fetchall()
                actions = connection.execute(
                    """
                    SELECT companies.name, jobs.title, actions.queue, actions.kind
                    FROM actions
                    JOIN companies ON companies.id = actions.company_id
                    LEFT JOIN jobs ON jobs.id = actions.job_id
                    ORDER BY companies.name, jobs.title, actions.queue
                    """
                ).fetchall()
                events = connection.execute(
                    """
                    SELECT companies.name, jobs.title, events.event_type, events.notes
                    FROM events
                    JOIN companies ON companies.id = events.company_id
                    LEFT JOIN jobs ON jobs.id = events.job_id
                    WHERE events.event_type <> 'company_added'
                    ORDER BY companies.name, jobs.title, events.event_type
                    """
                ).fetchall()
                event_notes = [row[3] for row in events if row[3]]

            self.assertEqual(
                jobs,
                [
                    (
                        "Amazon",
                        "Senior Product Manager - Tech, Prime Video Financial Systems",
                        "applied",
                        "FINTECH",
                        "YOUR_PROFILE/Fintech/FINTECH.md",
                        None,
                        None,
                        "pending_response",
                    ),
                    (
                        "Relo Metrics",
                        "Senior Product Manager",
                        "ignored_by_filter",
                        "PASS",
                        None,
                        None,
                        None,
                        None,
                    ),
                    (
                        "Stripe",
                        "Product Manager, Banking as a Service",
                        "ready_to_apply",
                        "FINTECH",
                        "YOUR_PROFILE/Fintech/FINTECH.md",
                        "ready",
                        "APPLICATIONS/READY_TO_APPLY/Stripe_PM",
                        None,
                    ),
                    (
                        "Stripe",
                        "Product Manager, Payments",
                        "discovered",
                        "FINTECH",
                        "YOUR_PROFILE/Fintech/FINTECH.md",
                        None,
                        None,
                        None,
                    ),
                ],
            )
            self.assertTrue(
                any("recommendation: low-priority_apply" in note for note in event_notes)
            )
            self.assertTrue(any("recommendation: pass" in note for note in event_notes))
            self.assertEqual(
                actions,
                [
                    (
                        "Amazon",
                        "Senior Product Manager - Tech, Prime Video Financial Systems",
                        "follow_up",
                        "follow_up",
                    ),
                    (
                        "Stripe",
                        "Product Manager, Banking as a Service",
                        "apply",
                        "apply",
                    ),
                ],
            )
            self.assertTrue(
                any(
                    row[0] == "Amazon"
                    and row[1] == "Senior Product Manager - Tech, Prime Video Financial Systems"
                    and row[2] == "application_submitted"
                    and "status: applied" in (row[3] or "")
                    and "user_action: Applied." in (row[3] or "")
                    for row in events
                )
            )
            self.assertTrue(
                any(
                    row[0] == "Stripe"
                    and row[1] == "Product Manager, Banking as a Service"
                    and row[2] == "status_changed"
                    and "status: ready_to_apply" in (row[3] or "")
                    and "summary: Financial infrastructure role." in (row[3] or "")
                    for row in events
                )
            )

    def test_schema_enforces_core_uniqueness_and_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                now = "2026-04-27T00:00:00+00:00"
                with connection:
                    connection.execute(
                        """
                        INSERT INTO companies(name, name_key, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        ("Coinbase", "coinbase", now, now),
                    )
                    company_id = connection.execute("SELECT id FROM companies").fetchone()[0]

                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            """
                            INSERT INTO companies(name, name_key, created_at, updated_at)
                            VALUES (?, ?, ?, ?)
                            """,
                            ("Coinbase ", "coinbase", now, now),
                        )

                    connection.execute(
                        """
                        INSERT INTO jobs(
                            company_id, title, canonical_url, source, source_job_id,
                            created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            company_id,
                            "Senior Product Manager",
                            "https://example.com/jobs/123",
                            "greenhouse",
                            "123",
                            now,
                            now,
                        ),
                    )

                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            """
                            INSERT INTO jobs(
                                company_id, title, canonical_url, source, source_job_id,
                                created_at, updated_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                company_id,
                                "Product Lead",
                                "https://example.com/jobs/123",
                                "greenhouse",
                                "456",
                                now,
                                now,
                            ),
                        )

                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            """
                            INSERT INTO jobs(
                                company_id, title, source, source_job_id,
                                created_at, updated_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (company_id, "Product Lead", "greenhouse", "123", now, now),
                        )

                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            """
                            INSERT INTO actions(company_id, job_id, queue, kind, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (company_id, 999, "apply", "apply", now, now),
                        )

    def test_schema_enforces_same_company_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                now = "2026-04-27T00:00:00+00:00"
                with connection:
                    connection.execute(
                        """
                        INSERT INTO companies(name, name_key, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        ("Company A", "company a", now, now),
                    )
                    company_a = connection.execute(
                        "SELECT last_insert_rowid()"
                    ).fetchone()[0]
                    connection.execute(
                        """
                        INSERT INTO companies(name, name_key, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        ("Company B", "company b", now, now),
                    )
                    company_b = connection.execute(
                        "SELECT last_insert_rowid()"
                    ).fetchone()[0]
                    connection.execute(
                        """
                        INSERT INTO jobs(company_id, title, source, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (company_b, "Product Lead", "manual", now, now),
                    )
                    job_b = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
                    connection.execute(
                        """
                        INSERT INTO contacts(company_id, name, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (company_b, "Hiring Manager", now, now),
                    )
                    contact_b = connection.execute(
                        "SELECT last_insert_rowid()"
                    ).fetchone()[0]
                    connection.execute(
                        """
                        INSERT INTO artifacts(company_id, job_id, type, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (company_b, job_b, "memo", now, now),
                    )
                    artifact_b = connection.execute(
                        "SELECT last_insert_rowid()"
                    ).fetchone()[0]
                    connection.execute(
                        """
                        INSERT INTO gaps(company_id, job_id, gap_type, description, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (company_b, job_b, "domain", "Needs proof", now, now),
                    )
                    gap_b = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
                    connection.execute(
                        """
                        INSERT INTO actions(company_id, job_id, queue, kind, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (company_b, job_b, "apply", "apply", now, now),
                    )
                    action_b = connection.execute(
                        "SELECT last_insert_rowid()"
                    ).fetchone()[0]

                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            """
                            INSERT INTO artifacts(company_id, job_id, type, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (company_a, job_b, "memo", now, now),
                        )
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            """
                            INSERT INTO gaps(company_id, job_id, gap_type, description, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (company_a, job_b, "domain", "Needs proof", now, now),
                        )

                    action_mismatches = (
                        ("job_id", job_b),
                        ("contact_id", contact_b),
                        ("artifact_id", artifact_b),
                        ("gap_id", gap_b),
                    )
                    for column, value in action_mismatches:
                        with self.subTest(table="actions", column=column):
                            with self.assertRaises(sqlite3.IntegrityError):
                                connection.execute(
                                    f"""
                                    INSERT INTO actions(
                                        company_id, {column}, queue, kind, created_at, updated_at
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?)
                                    """,
                                    (company_a, value, "apply", "apply", now, now),
                                )

                    event_mismatches = (
                        ("job_id", job_b),
                        ("contact_id", contact_b),
                        ("artifact_id", artifact_b),
                        ("gap_id", gap_b),
                        ("action_id", action_b),
                    )
                    for column, value in event_mismatches:
                        with self.subTest(table="events", column=column):
                            with self.assertRaises(sqlite3.IntegrityError):
                                connection.execute(
                                    f"""
                                    INSERT INTO events(
                                        company_id, {column}, event_type, happened_at, created_at
                                    )
                                    VALUES (?, ?, ?, ?, ?)
                                    """,
                                    (company_a, value, "note", now, now),
                                )

    def test_schema_prevents_parent_company_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    ids = self.seed_two_company_graph(connection)

                    ownership_updates = (
                        ("jobs", ids["job_b"], ids["company_a"]),
                        ("contacts", ids["contact_b"], ids["company_a"]),
                        ("artifacts", ids["artifact_b"], ids["company_a"]),
                        ("gaps", ids["gap_b"], ids["company_a"]),
                        ("actions", ids["action_b"], ids["company_a"]),
                        ("events", ids["event_a"], ids["company_b"]),
                    )
                    for table, row_id, new_company_id in ownership_updates:
                        with self.subTest(table=table):
                            with self.assertRaises(sqlite3.IntegrityError):
                                connection.execute(
                                    f"UPDATE {table} SET company_id = ? WHERE id = ?",
                                    (new_company_id, row_id),
                                )

                    mismatched_action_count = connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM actions
                        JOIN jobs ON jobs.id = actions.job_id
                        WHERE actions.company_id <> jobs.company_id
                        """
                    ).fetchone()[0]
                    self.assertEqual(mismatched_action_count, 0)

    def test_schema_enforces_same_company_reference_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    ids = self.seed_two_company_graph(connection)

                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            "UPDATE artifacts SET job_id = ? WHERE id = ?",
                            (ids["job_b"], ids["artifact_a"]),
                        )
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            "UPDATE gaps SET job_id = ? WHERE id = ?",
                            (ids["job_b"], ids["gap_a"]),
                        )

                    action_mismatches = (
                        ("job_id", ids["job_b"]),
                        ("contact_id", ids["contact_b"]),
                        ("artifact_id", ids["artifact_b"]),
                        ("gap_id", ids["gap_b"]),
                    )
                    for column, value in action_mismatches:
                        with self.subTest(table="actions", column=column):
                            with self.assertRaises(sqlite3.IntegrityError):
                                connection.execute(
                                    f"UPDATE actions SET {column} = ? WHERE id = ?",
                                    (value, ids["action_a"]),
                                )

                    event_mismatches = (
                        ("job_id", ids["job_b"]),
                        ("contact_id", ids["contact_b"]),
                        ("artifact_id", ids["artifact_b"]),
                        ("gap_id", ids["gap_b"]),
                        ("action_id", ids["action_b"]),
                    )
                    for column, value in event_mismatches:
                        with self.subTest(table="events", column=column):
                            with self.assertRaises(sqlite3.IntegrityError):
                                connection.execute(
                                    f"UPDATE events SET {column} = ? WHERE id = ?",
                                    (value, ids["event_a"]),
                                )

    def test_schema_enforces_lifecycle_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = self.insert_company(connection, "Company A")

                    with self.assertRaises(sqlite3.IntegrityError):
                        self.insert_action(connection, company_id, status="done")
                    with self.assertRaises(sqlite3.IntegrityError):
                        self.insert_action(
                            connection,
                            company_id,
                            status="queued",
                            completed_at=NOW,
                        )
                    self.insert_action(
                        connection,
                        company_id,
                        status="done",
                        completed_at=NOW,
                    )

                    with self.assertRaises(sqlite3.IntegrityError):
                        self.insert_artifact(connection, company_id, status="ready")
                    self.insert_artifact(
                        connection,
                        company_id,
                        status="ready",
                        path="APPLICATIONS/Company_A/artifact.md",
                    )

    def test_events_prevent_company_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                now = "2026-04-27T00:00:00+00:00"
                with connection:
                    connection.execute(
                        """
                        INSERT INTO companies(name, name_key, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        ("Coinbase", "coinbase", now, now),
                    )
                    company_id = connection.execute("SELECT id FROM companies").fetchone()[0]
                    connection.execute(
                        """
                        INSERT INTO events(company_id, event_type, happened_at, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (company_id, "note", now, now),
                    )

                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            "DELETE FROM companies WHERE id = ?",
                            (company_id,),
                        )

    def test_support_object_commands_write_company_first_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            self.run_cli(db_path, "company", "add", "Coinbase", "--tier", "1")
            contact = self.run_cli(
                db_path,
                "contact",
                "add",
                "--company",
                "Coinbase",
                "--name",
                "Avery Chen",
                "--title",
                "Product Director",
                "--source",
                "linkedin",
                "--link",
                "https://linkedin.example/avery",
                "--relationship-strength",
                "warm",
                "--last-contacted",
                "2026-04-27T09:00:00+00:00",
                "--notes",
                "Intro path through alumni network",
            )
            artifact = self.run_cli(
                db_path,
                "artifact",
                "add",
                "--company",
                "Coinbase",
                "--type",
                "memo",
                "--status",
                "ready",
                "--thesis",
                "Ledger close automation maps to reporting platform work",
                "--path",
                "APPLICATIONS/Coinbase/artifact.md",
                "--notes",
                "Use before referral ask",
            )
            gap = self.run_cli(
                db_path,
                "gap",
                "add",
                "--company",
                "Coinbase",
                "--type",
                "domain",
                "--description",
                "Need clearer crypto accounting proof",
                "--severity",
                "high",
                "--resolution-action",
                "Draft targeted artifact",
            )

            self.assertIn("contact id=", contact.stdout)
            self.assertIn("artifact id=", artifact.stdout)
            self.assertIn("gap id=", gap.stdout)

            contacts = self.run_cli(db_path, "contact", "list", "--company", "Coinbase")
            artifacts = self.run_cli(db_path, "artifact", "list", "--company", "Coinbase")
            gaps = self.run_cli(db_path, "gap", "list", "--company", "Coinbase")

            self.assertIn("Avery Chen", contacts.stdout)
            self.assertIn("relationship_strength=warm", contacts.stdout)
            self.assertIn("Ledger close automation", artifacts.stdout)
            self.assertIn("status=ready", artifacts.stdout)
            self.assertIn("Need clearer crypto accounting proof", gaps.stdout)
            self.assertIn("severity=high", gaps.stdout)

    def test_event_creation_and_company_history_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            self.run_cli(db_path, "company", "add", "Ramp", "--tier", "1")
            job_id = self.stdout_id(
                self.run_cli(
                    db_path,
                    "job",
                    "add",
                    "--company",
                    "Ramp",
                    "--title",
                    "Senior Product Manager",
                    "--source",
                    "manual",
                )
            )
            contact_id = self.stdout_id(
                self.run_cli(
                    db_path,
                    "contact",
                    "add",
                    "--company",
                    "Ramp",
                    "--name",
                    "Hiring Manager",
                    "--title",
                    "Head of Product",
                )
            )
            artifact_id = self.stdout_id(
                self.run_cli(
                    db_path,
                    "artifact",
                    "add",
                    "--company",
                    "Ramp",
                    "--job-id",
                    str(job_id),
                    "--type",
                    "case-study",
                    "--status",
                    "sent",
                    "--link",
                    "https://example.com/ramp-case-study",
                    "--happened-at",
                    "2026-04-27T10:00:00+00:00",
                )
            )
            gap_id = self.stdout_id(
                self.run_cli(
                    db_path,
                    "gap",
                    "add",
                    "--company",
                    "Ramp",
                    "--job-id",
                    str(job_id),
                    "--type",
                    "domain",
                    "--description",
                    "Need clearer card issuing proof",
                    "--happened-at",
                    "2026-04-27T11:00:00+00:00",
                )
            )
            self.run_cli(
                db_path,
                "event",
                "add",
                "--company",
                "Ramp",
                "--type",
                "message_sent",
                "--contact-id",
                str(contact_id),
                "--happened-at",
                "2026-04-27T09:00:00+00:00",
            )
            self.run_cli(
                db_path,
                "event",
                "add",
                "--company",
                "Ramp",
                "--type",
                "application_submitted",
                "--job-id",
                str(job_id),
                "--happened-at",
                "2026-04-27T12:00:00+00:00",
                "--notes",
                "Applied with fintech resume",
            )
            self.run_cli(
                db_path,
                "event",
                "add",
                "--company",
                "Ramp",
                "--type",
                "interview",
                "--job-id",
                str(job_id),
                "--happened-at",
                "2026-04-27T12:30:00+00:00",
            )
            self.run_cli(
                db_path,
                "event",
                "add",
                "--company",
                "Ramp",
                "--type",
                "referral_ask",
                "--contact-id",
                str(contact_id),
                "--artifact-id",
                str(artifact_id),
                "--happened-at",
                "2026-04-27T13:00:00+00:00",
            )
            self.run_cli(
                db_path,
                "job",
                "status",
                str(job_id),
                "rejected",
                "--happened-at",
                "2026-04-27T14:00:00+00:00",
            )
            self.run_cli(
                db_path,
                "gap",
                "status",
                str(gap_id),
                "resolved",
                "--resolution-action",
                "Added card issuing proof to artifact",
                "--happened-at",
                "2026-04-27T15:00:00+00:00",
            )

            history = self.run_cli(db_path, "event", "list", "--company", "Ramp")

            for expected in (
                "message_sent",
                "artifact_sent",
                "gap_identified",
                "application_submitted",
                "interview",
                "referral_ask",
                "rejection_received",
                "status_changed",
                "company=Ramp",
                "job=Senior Product Manager",
                "contact=Hiring Manager",
                "artifact=case-study",
                "gap=Need clearer card issuing proof",
            ):
                self.assertIn(expected, history.stdout)
            self.assertLess(
                history.stdout.index("artifact_sent"),
                history.stdout.index("rejection_received"),
            )

    def test_artifact_status_can_complete_idea_with_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            self.run_cli(db_path, "company", "add", "Stripe")
            artifact_id = self.stdout_id(
                self.run_cli(
                    db_path,
                    "artifact",
                    "add",
                    "--company",
                    "Stripe",
                    "--type",
                    "memo",
                )
            )
            updated = self.run_cli(
                db_path,
                "artifact",
                "status",
                str(artifact_id),
                "ready",
                "--path",
                "APPLICATIONS/Stripe/memo.md",
            )

            artifacts = self.run_cli(db_path, "artifact", "list", "--company", "Stripe")

            self.assertIn(f"artifact id={artifact_id} status=ready", updated.stdout)
            self.assertIn("status=ready", artifacts.stdout)
            self.assertIn("path=APPLICATIONS/Stripe/memo.md", artifacts.stdout)

    def test_backfilled_events_preserve_latest_company_touch_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            self.run_cli(db_path, "company", "add", "Mercury")
            self.run_cli(
                db_path,
                "event",
                "add",
                "--company",
                "Mercury",
                "--type",
                "interview",
                "--happened-at",
                "2026-04-27T14:00:00+00:00",
            )
            self.run_cli(
                db_path,
                "event",
                "add",
                "--company",
                "Mercury",
                "--type",
                "coffee_chat",
                "--happened-at",
                "2026-04-26T09:00:00+00:00",
            )

            company = self.run_cli(db_path, "company", "show", "Mercury")

            self.assertIn("last_touched_at=2026-04-27T14:00:00+00:00", company.stdout)

    def test_event_limit_returns_recent_history_in_chronological_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            self.run_cli(db_path, "company", "add", "Brex")
            for day in (25, 26, 27):
                self.run_cli(
                    db_path,
                    "event",
                    "add",
                    "--company",
                    "Brex",
                    "--type",
                    "note",
                    "--happened-at",
                    f"2026-04-{day}T09:00:00+00:00",
                    "--notes",
                    f"day-{day}",
                )

            history = self.run_cli(db_path, "event", "list", "--company", "Brex", "--limit", "2")

            self.assertNotIn("day-25", history.stdout)
            self.assertLess(history.stdout.index("day-26"), history.stdout.index("day-27"))

    def test_gap_list_orders_high_severity_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            self.run_cli(db_path, "company", "add", "Plaid")
            for severity in ("low", "high", "medium"):
                self.run_cli(
                    db_path,
                    "gap",
                    "add",
                    "--company",
                    "Plaid",
                    "--type",
                    "domain",
                    "--description",
                    f"{severity} severity proof gap",
                    "--severity",
                    severity,
                )

            gaps = self.run_cli(db_path, "gap", "list", "--company", "Plaid")

            self.assertLess(
                gaps.stdout.index("high severity proof gap"),
                gaps.stdout.index("medium severity proof gap"),
            )
            self.assertLess(
                gaps.stdout.index("medium severity proof gap"),
                gaps.stdout.index("low severity proof gap"),
            )

    def test_job_add_initial_lifecycle_status_records_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            self.run_cli(db_path, "company", "add", "Rippling")
            job = self.run_cli(
                db_path,
                "job",
                "add",
                "--company",
                "Rippling",
                "--title",
                "Senior Product Manager",
                "--status",
                "applied",
            )

            history = self.run_cli(db_path, "event", "list", "--company", "Rippling")

            self.assertIn("job id=", job.stdout)
            self.assertIn("application_submitted", history.stdout)
            self.assertIn("job=Senior Product Manager", history.stdout)

    def test_help_exposes_core_command_groups(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CLI), "--help"],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        for command in (
            "init",
            "status",
            "import-pipeline",
            "company",
            "job",
            "contact",
            "artifact",
            "gap",
            "action",
            "event",
            "metrics",
        ):
            self.assertIn(command, result.stdout)

    def test_company_job_workflow_generates_actions_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            self.run_cli(
                db_path,
                "company",
                "add",
                "Coinbase",
                "--tier",
                "1",
                "--lanes",
                "fintech",
            )
            self.run_cli(
                db_path,
                "job",
                "add",
                "Coinbase",
                "Senior Product Manager",
                "--fit-score",
                "85",
                "--url",
                "https://example.com/coinbase-spm",
            )
            first_ready = self.run_cli(
                db_path, "job", "update", "1", "--status", "ready_to_apply"
            )
            second_ready = self.run_cli(
                db_path, "job", "update", "1", "--status", "ready_to_apply"
            )
            next_apply = self.run_cli(
                db_path, "action", "next", "--queue", "apply", "--limit", "5"
            )
            company_show = self.run_cli(db_path, "company", "show", "Coinbase")
            self.run_cli(db_path, "action", "done", "3")
            self.run_cli(db_path, "job", "update", "1", "--lane", "platform")

            self.assertIn("job updated id=1", first_ready.stdout)
            self.assertIn("job updated id=1", second_ready.stdout)
            self.assertIn(
                "#3 | apply:apply | ready | status=queued | due=unscheduled | "
                "Coinbase / Senior Product Manager",
                next_apply.stdout,
            )
            self.assertIn("job=#1", next_apply.stdout)
            self.assertIn("url=https://example.com/coinbase-spm", next_apply.stdout)
            self.assertIn("Company: Coinbase", company_show.stdout)
            self.assertIn(
                "Summary: tier=1 | status=active | lanes=fintech",
                company_show.stdout,
            )
            self.assertIn("Cooldown: none", company_show.stdout)
            self.assertIn("Active jobs:", company_show.stdout)
            self.assertIn("Open actions:", company_show.stdout)
            self.assertIn("Next best action:", company_show.stdout)

            with closing(self.connect(db_path)) as connection:
                action_counts = connection.execute(
                    """
                    SELECT queue, kind, status, COUNT(*)
                    FROM actions
                    GROUP BY queue, kind, status
                    ORDER BY queue, kind, status
                    """
                ).fetchall()

            self.assertEqual(
                action_counts,
                [
                    ("apply", "apply", "done", 1),
                    ("research", "find_contact", "queued", 1),
                    ("screen", "screen_role", "skipped", 1),
                ],
            )

    def test_manual_action_add_queues_company_research_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Ramp", "--tier", "2")

            first = self.run_cli(
                db_path,
                "action",
                "add",
                "--company",
                "Ramp",
                "--queue",
                "research",
                "--kind",
                "vet_company",
                "--due-at",
                "2026-04-30T16:00:00+00:00",
                "--notes",
                "Decide if Ramp belongs in the active target list.",
            )
            second = self.run_cli(
                db_path,
                "action",
                "add",
                "--company",
                "Ramp",
                "--queue",
                "research",
                "--kind",
                "vet_company",
                "--due-at",
                "2026-04-30T16:00:00+00:00",
                "--notes",
                "Decide if Ramp belongs in the active target list.",
            )
            next_research = self.run_cli(
                db_path, "action", "next", "--queue", "research", "--limit", "5"
            )

            self.assertIn("action added id=1", first.stdout)
            self.assertIn("action existing id=1", second.stdout)
            self.assertIn(
                "#1 | research:vet_company | stale | status=queued | "
                "due=2026-04-30T16:00:00+00:00 | Ramp",
                next_research.stdout,
            )

    def test_action_queue_review_views_show_state_order_and_linked_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            due_now = JOB_SEARCH.utc_now()
            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = self.insert_company(connection, "QueueCo")
                    job_id = self.insert_job(connection, company_id)
                    contact_id = self.insert_contact(connection, company_id)
                    artifact_id = self.insert_artifact(
                        connection,
                        company_id,
                        job_id,
                        status="ready",
                        path="APPLICATIONS/QueueCo/artifact.md",
                    )
                    gap_id = self.insert_gap(connection, company_id, job_id)
                    self.insert_action(
                        connection,
                        company_id,
                        job_id=job_id,
                        queue="screen",
                        kind="screen_role",
                        due_at="2000-01-01T00:00:00+00:00",
                    )
                    self.insert_action(
                        connection,
                        company_id,
                        queue="screen",
                        kind="screen_due",
                        due_at=due_now,
                    )
                    self.insert_action(
                        connection,
                        company_id,
                        queue="screen",
                        kind="screen_blocked",
                        status="blocked",
                    )
                    self.insert_action(
                        connection,
                        company_id,
                        queue="screen",
                        kind="screen_ready",
                    )
                    self.insert_action(
                        connection,
                        company_id,
                        queue="screen",
                        kind="screen_done",
                        status="done",
                        completed_at=due_now,
                    )
                    self.insert_action(
                        connection,
                        company_id,
                        job_id=job_id,
                        queue="apply",
                        kind="apply",
                        due_at=due_now,
                    )
                    self.insert_action(
                        connection,
                        company_id,
                        contact_id=contact_id,
                        queue="follow_up",
                        kind="follow_up",
                        status="blocked",
                        due_at="2000-01-01T00:00:00+00:00",
                    )
                    self.insert_action(
                        connection,
                        company_id,
                        queue="research",
                        kind="vet_company",
                        due_at="2999-01-01T00:00:00+00:00",
                    )
                    self.insert_action(
                        connection,
                        company_id,
                        artifact_id=artifact_id,
                        queue="artifact",
                        kind="draft_artifact",
                    )
                    self.insert_action(
                        connection,
                        company_id,
                        gap_id=gap_id,
                        queue="classify",
                        kind="classify_gap",
                    )

            expected_by_queue = {
                "screen": ("stale", "job=#1"),
                "apply": ("due", "job=#1"),
                "follow_up": ("blocked", "contact=#1 Hiring Manager"),
                "research": ("ready", "QueueCo"),
                "artifact": (
                    "ready",
                    "artifact=#1 memo status=ready path=APPLICATIONS/QueueCo/artifact.md",
                ),
                "classify": ("ready", "gap=#1 medium status=open Needs proof"),
            }
            for queue, expected in expected_by_queue.items():
                with self.subTest(queue=queue):
                    reviewed = self.run_cli(
                        db_path, "action", "next", "--queue", queue, "--limit", "1"
                    )
                    self.assertIn(f"| {queue}:", reviewed.stdout)
                    for text in expected:
                        self.assertIn(text, reviewed.stdout)

            listed = self.run_cli(db_path, "action", "list", "--queue", "screen", "--limit", "2")
            listed_lines = listed.stdout.splitlines()
            self.assertEqual(len(listed_lines), 2)
            self.assertIn("| screen:screen_role | stale |", listed_lines[0])
            self.assertIn("| screen:screen_due | due |", listed_lines[1])
            self.assertNotIn("screen_blocked", listed.stdout)
            self.assertNotIn("screen_done", listed.stdout)

            done = self.run_cli(
                db_path,
                "action",
                "list",
                "--queue",
                "screen",
                "--status",
                "done",
                "--limit",
                "1",
            )
            self.assertIn("| screen:screen_done | done | status=done |", done.stdout)

            invalid = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--db-path",
                    str(db_path),
                    "action",
                    "next",
                    "--queue",
                    "network",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("invalid choice: 'network'", invalid.stderr)

    def test_job_state_changes_generate_follow_up_and_classify_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Stripe", "--tier", "2")
            self.run_cli(db_path, "job", "add", "Stripe", "Product Manager")

            self.run_cli(db_path, "job", "update", "1", "--status", "applied")
            self.run_cli(
                db_path,
                "job",
                "update",
                "1",
                "--status",
                "rejected",
                "--rejection-reason",
                "missing_proof",
            )

            with closing(self.connect(db_path)) as connection:
                generated = connection.execute(
                    """
                    SELECT queue, kind, status, due_at
                    FROM actions
                    ORDER BY queue, kind
                    """
                ).fetchall()

            self.assertEqual(generated[0][:3], ("classify", "classify_outcome", "queued"))
            self.assertEqual(generated[1][:3], ("follow_up", "follow_up", "skipped"))
            self.assertIsNotNone(generated[1][3])

    def test_job_add_accepts_documented_outcome_taxonomy_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Stripe")

            self.run_cli(
                db_path,
                "job",
                "add",
                "Stripe",
                "Product Manager",
                "--status",
                "rejected",
                "--rejection-reason",
                "fit_mismatch",
                "--application-outcome",
                "rejected_before_screen",
            )

            with closing(self.connect(db_path)) as connection:
                recorded = connection.execute(
                    """
                    SELECT status, rejection_reason, application_outcome
                    FROM jobs
                    WHERE id = 1
                    """
                ).fetchone()

            self.assertEqual(
                recorded[:],
                ("rejected", "fit_mismatch", "rejected_before_screen"),
            )

    def test_job_update_accepts_all_documented_outcome_taxonomy_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Stripe")
            self.run_cli(db_path, "job", "add", "Stripe", "Product Manager")

            for outcome in JOB_SEARCH.APPLICATION_OUTCOMES:
                with self.subTest(outcome=outcome):
                    self.run_cli(
                        db_path,
                        "job",
                        "update",
                        "1",
                        "--application-outcome",
                        outcome,
                    )

                    with closing(self.connect(db_path)) as connection:
                        recorded = connection.execute(
                            "SELECT application_outcome FROM jobs WHERE id = 1"
                        ).fetchone()

                    self.assertEqual(recorded[0], outcome)

            for reason in JOB_SEARCH.REJECTION_REASONS:
                with self.subTest(reason=reason):
                    self.run_cli(
                        db_path,
                        "job",
                        "update",
                        "1",
                        "--rejection-reason",
                        reason,
                    )

                    with closing(self.connect(db_path)) as connection:
                        recorded = connection.execute(
                            "SELECT rejection_reason FROM jobs WHERE id = 1"
                        ).fetchone()

                    self.assertEqual(recorded[0], reason)

    def test_job_update_rejects_non_taxonomy_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Stripe")
            self.run_cli(db_path, "job", "add", "Stripe", "Product Manager")

            for option, value in (
                ("--rejection-reason", "vibes"),
                ("--application-outcome", "maybe_later"),
            ):
                with self.subTest(option=option):
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(CLI),
                            "--db-path",
                            str(db_path),
                            "job",
                            "update",
                            "1",
                            option,
                            value,
                        ],
                        cwd=REPO_ROOT,
                        text=True,
                        capture_output=True,
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"invalid choice: '{value}'", result.stderr)

    def test_job_help_exposes_documented_taxonomy_values_only(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CLI), "job", "update", "--help"],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        for value in (*JOB_SEARCH.APPLICATION_OUTCOMES, *JOB_SEARCH.REJECTION_REASONS):
            with self.subTest(value=value):
                self.assertIn(value, result.stdout)
        self.assertNotIn("no_response", result.stdout)
        self.assertNotIn("role_fit", result.stdout)

    def test_legacy_application_outcome_maps_old_values_to_canonical(self) -> None:
        self.assertEqual(
            JOB_SEARCH.legacy_application_outcome(
                {"recommendation": "rejected_after_loop"}, "rejected"
            ),
            "rejected_after_interview",
        )
        self.assertEqual(
            JOB_SEARCH.legacy_application_outcome(
                {"recommendation": "offer_received"}, "interviewing"
            ),
            "active_interview_loop",
        )
        self.assertEqual(
            JOB_SEARCH.legacy_application_outcome(
                {"recommendation": "offer_accepted"}, "applied"
            ),
            "active_interview_loop",
        )
        self.assertEqual(
            JOB_SEARCH.legacy_application_outcome({}, "applied"),
            "pending_response",
        )

    def test_no_interview_rejection_creates_company_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Coinbase", "--tier", "1")
            self.run_cli(
                db_path,
                "job",
                "add",
                "Coinbase",
                "Senior Product Manager",
                "--lane",
                "fintech",
            )
            self.run_cli(
                db_path,
                "job",
                "status",
                "1",
                "applied",
                "--happened-at",
                "2026-04-26T12:00:00+00:00",
            )

            self.run_cli(
                db_path,
                "job",
                "status",
                "1",
                "rejected",
                "--happened-at",
                "2026-04-27T12:00:00+00:00",
                "--notes",
                "No interview rejection",
            )

            company = self.run_cli(db_path, "company", "show", "Coinbase")

            self.assertIn("Summary: tier=1 | status=cooldown", company.stdout)
            self.assertIn("Cooldown: 2026-06-11T12:00:00+00:00", company.stdout)
            self.assertIn("Last outcome: rejection_received", company.stdout)

    def test_interview_loop_rejection_creates_longer_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Ramp")
            self.run_cli(db_path, "job", "add", "Ramp", "Product Lead")
            self.run_cli(
                db_path,
                "event",
                "add",
                "--company",
                "Ramp",
                "--type",
                "interview",
                "--job-id",
                "1",
                "--happened-at",
                "2026-04-28T12:00:00+00:00",
            )

            self.run_cli(
                db_path,
                "job",
                "status",
                "1",
                "rejected",
                "--happened-at",
                "2026-04-29T12:00:00+00:00",
            )

            company = self.run_cli(db_path, "company", "show", "Ramp")

            self.assertIn("Cooldown: 2026-08-27T12:00:00+00:00", company.stdout)

    def test_materially_different_lane_can_bypass_company_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Mercury")
            self.run_cli(
                db_path,
                "job",
                "add",
                "Mercury",
                "Consumer Product Manager",
                "--lane",
                "consumer",
                "--status",
                "applied",
            )
            self.run_cli(
                db_path,
                "job",
                "status",
                "1",
                "rejected",
                "--happened-at",
                "2026-04-27T12:00:00+00:00",
                "--notes",
                "No interview rejection",
            )

            self.run_cli(
                db_path,
                "job",
                "add",
                "Mercury",
                "Consumer Product Manager II",
                "--lane",
                "consumer",
                "--status",
                "ready_to_apply",
            )
            blocked_actions = self.run_cli(db_path, "action", "next", "--queue", "apply")

            self.run_cli(
                db_path,
                "job",
                "add",
                "Mercury",
                "Ledger Product Manager",
                "--lane",
                "platform",
                "--status",
                "ready_to_apply",
            )
            actions = self.run_cli(db_path, "action", "next", "--queue", "apply")

            self.assertIn("no actions", blocked_actions.stdout)
            self.assertIn("Mercury / Ledger Product Manager", actions.stdout)

    def test_duplicate_detection_reports_strong_and_likely_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Coinbase")
            self.run_cli(
                db_path,
                "job",
                "add",
                "Coinbase",
                "Product Manager, Payments",
                "--source",
                "greenhouse",
                "--source-job-id",
                "abc123",
                "--url",
                "https://jobs.example.com/roles/123?gh_src=linkedin#apply",
                "--location",
                "New York, NY",
            )

            url_duplicate = self.run_cli(
                db_path,
                "job",
                "add",
                "Coinbase",
                "Product Manager, Payments",
                "--source",
                "manual",
                "--url",
                "https://jobs.example.com/roles/123/",
                "--location",
                "New York, NY",
            )
            source_duplicate = self.run_cli(
                db_path,
                "job",
                "add",
                "Coinbase",
                "Product Manager, Payments",
                "--source",
                "Greenhouse",
                "--source-job-id",
                "abc123",
                "--location",
                "New York, NY",
            )
            likely_duplicate = self.run_cli(
                db_path,
                "job",
                "add",
                "Coinbase",
                "Product Manager, Payments",
                "--location",
                "New York, NY",
            )

            self.assertIn("level=strong", url_duplicate.stdout)
            self.assertIn("reason=normalized_url", url_duplicate.stdout)
            self.assertIn("level=strong", source_duplicate.stdout)
            self.assertIn("reason=source_job_id", source_duplicate.stdout)
            self.assertIn("level=likely", likely_duplicate.stdout)
            self.assertIn("reason=same_company_title_location_window", likely_duplicate.stdout)

            with closing(self.connect(db_path)) as connection:
                job_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            self.assertEqual(job_count, 1)

            self.run_cli(db_path, "job", "status", "1", "closed")
            closed_url_duplicate = self.run_cli(
                db_path,
                "job",
                "add",
                "Coinbase",
                "Product Manager, Payments",
                "--url",
                "https://jobs.example.com/roles/123/",
            )
            repost = self.run_cli(
                db_path,
                "job",
                "add",
                "Coinbase",
                "Product Manager, Payments",
                "--location",
                "New York, NY",
            )

            self.assertIn("reason=normalized_url", closed_url_duplicate.stdout)
            self.assertIn("job id=2 added", repost.stdout)

    def test_polling_ats_sources_preserves_weak_matches_and_dedupes_active_roles(
        self,
    ) -> None:
        cases = {
            "greenhouse": {
                "jobs": [
                    {
                        "id": 101,
                        "title": "Senior Product Manager, Payments",
                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
                        "location": {"name": "Remote"},
                    },
                    {
                        "id": 102,
                        "title": "Customer Support Specialist",
                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/102",
                        "location": {"name": "Remote"},
                    },
                ]
            },
            "lever": [
                {
                    "id": "lev-101",
                    "text": "Senior Product Manager, Payments",
                    "hostedUrl": "https://jobs.lever.co/acme/lev-101",
                    "categories": {"location": "Remote"},
                    "workplaceType": "remote",
                },
                {
                    "id": "lev-102",
                    "text": "Customer Support Specialist",
                    "hostedUrl": "https://jobs.lever.co/acme/lev-102",
                    "categories": {"location": "Remote"},
                    "workplaceType": "remote",
                },
            ],
            "ashby": {
                "jobs": [
                    {
                        "id": "ash-101",
                        "title": "Senior Product Manager, Payments",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/ash-101",
                        "location": "Remote",
                        "workplaceType": "Remote",
                    },
                    {
                        "id": "ash-102",
                        "title": "Customer Support Specialist",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/ash-102",
                        "location": "Remote",
                        "workplaceType": "Remote",
                    },
                ]
            },
        }

        for ats_type, payload in cases.items():
            with self.subTest(ats_type=ats_type):
                with tempfile.TemporaryDirectory() as tmpdir:
                    db_path = Path(tmpdir) / "job_search.sqlite"
                    payload_path = Path(tmpdir) / f"{ats_type}.json"
                    payload_path.write_text(json.dumps(payload), encoding="utf-8")

                    self.run_cli(db_path, "init")
                    self.run_cli(
                        db_path,
                        "company",
                        "add",
                        f"Acme {ats_type}",
                        "--lanes",
                        "fintech",
                        "--target-roles",
                        "Product Manager",
                    )
                    self.run_cli(
                        db_path,
                        "source",
                        "add",
                        f"Acme {ats_type}",
                        "--type",
                        ats_type,
                        "--key",
                        f"acme-{ats_type}",
                        "--url",
                        payload_path.as_uri(),
                    )

                    first_poll = self.run_cli(
                        db_path, "poll", "--company", f"Acme {ats_type}"
                    )
                    second_poll = self.run_cli(
                        db_path, "poll", "--company", f"Acme {ats_type}"
                    )

                    self.assertIn("discovered=2", first_poll.stdout)
                    self.assertIn("inserted=2", first_poll.stdout)
                    self.assertIn("ignored=1", first_poll.stdout)
                    self.assertIn("screen_actions=1", first_poll.stdout)
                    self.assertIn("inserted=0", second_poll.stdout)
                    self.assertIn("duplicates=2", second_poll.stdout)

                    with closing(self.connect(db_path)) as connection:
                        jobs = connection.execute(
                            """
                            SELECT title, status, fit_score, lane
                            FROM jobs
                            ORDER BY id
                            """
                        ).fetchall()
                        actions = connection.execute(
                            """
                            SELECT jobs.title, actions.queue, actions.kind
                            FROM actions
                            JOIN jobs ON jobs.id = actions.job_id
                            ORDER BY actions.id
                            """
                        ).fetchall()

                    self.assertEqual(
                        jobs,
                        [
                            (
                                "Senior Product Manager, Payments",
                                "screening",
                                75,
                                "fintech",
                            ),
                            (
                                "Customer Support Specialist",
                                "ignored_by_filter",
                                35,
                                "fintech",
                            ),
                        ],
                    )
                    self.assertEqual(
                        actions,
                        [("Senior Product Manager, Payments", "screen", "screen_role")],
                    )

    def test_polling_scopes_source_ids_and_reports_per_source_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            first_payload_path = Path(tmpdir) / "first.json"
            second_payload_path = Path(tmpdir) / "second.json"
            first_payload_path.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": 101,
                                "title": "Senior Product Manager, Payments",
                                "absolute_url": "https://boards.greenhouse.io/first/jobs/101",
                                "location": {"name": "Remote"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            second_payload_path.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "id": 101,
                                "title": "Senior Product Manager, Payments",
                                "absolute_url": "https://boards.greenhouse.io/second/jobs/101",
                                "location": {"name": "Remote"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            self.run_cli(db_path, "init")
            for company in ("Bad Co", "First Co", "Second Co"):
                self.run_cli(
                    db_path,
                    "company",
                    "add",
                    company,
                    "--lanes",
                    "fintech",
                    "--target-roles",
                    "Product Manager",
                )
            self.run_cli(
                db_path,
                "source",
                "add",
                "Bad Co",
                "--type",
                "greenhouse",
                "--key",
                "bad",
                "--url",
                (Path(tmpdir) / "missing.json").as_uri(),
            )
            self.run_cli(
                db_path,
                "source",
                "add",
                "First Co",
                "--type",
                "greenhouse",
                "--key",
                "first",
                "--url",
                first_payload_path.as_uri(),
            )
            self.run_cli(
                db_path,
                "source",
                "add",
                "Second Co",
                "--type",
                "greenhouse",
                "--key",
                "second",
                "--url",
                second_payload_path.as_uri(),
            )

            result = subprocess.run(
                [sys.executable, str(CLI), "--db-path", str(db_path), "poll"],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("company=Bad Co type=greenhouse failed error=", result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("company=First Co type=greenhouse discovered=1 inserted=1", result.stdout)
            self.assertIn("company=Second Co type=greenhouse discovered=1 inserted=1", result.stdout)

            with closing(self.connect(db_path)) as connection:
                jobs = connection.execute(
                    "SELECT source, source_job_id FROM jobs ORDER BY source"
                ).fetchall()
                action_count = connection.execute(
                    "SELECT COUNT(*) FROM actions WHERE queue = 'screen'"
                ).fetchone()[0]

            self.assertEqual(
                jobs,
                [
                    ("greenhouse:first", "101"),
                    ("greenhouse:second", "101"),
                ],
            )
            self.assertEqual(action_count, 2)

    def test_metrics_aggregates_weekly_review_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Stripe")
            self.run_cli(
                db_path,
                "job",
                "add",
                "Stripe",
                "Senior Product Manager",
                "--lane",
                "fintech",
                "--fit-score",
                "85",
            )
            self.run_cli(db_path, "action", "done", "1")
            self.run_cli(
                db_path,
                "job",
                "status",
                "1",
                "ready_to_apply",
                "--happened-at",
                "2026-04-22T12:00:00+00:00",
            )
            self.run_cli(
                db_path,
                "job",
                "status",
                "1",
                "applied",
                "--happened-at",
                "2026-04-27T12:00:00+00:00",
            )
            self.run_cli(
                db_path,
                "event",
                "add",
                "--company",
                "Stripe",
                "--type",
                "interview",
                "--job-id",
                "1",
                "--happened-at",
                "2026-04-28T12:00:00+00:00",
            )
            self.run_cli(
                db_path,
                "job",
                "status",
                "1",
                "rejected",
                "--happened-at",
                "2026-04-29T12:00:00+00:00",
            )
            self.run_cli(
                db_path,
                "event",
                "add",
                "--company",
                "Stripe",
                "--type",
                "message_sent",
                "--happened-at",
                "2026-04-26T12:00:00+00:00",
            )
            self.run_cli(
                db_path,
                "event",
                "add",
                "--company",
                "Stripe",
                "--type",
                "coffee_chat",
                "--happened-at",
                "2026-04-27T09:00:00+00:00",
            )

            with closing(self.connect(db_path)) as connection:
                with connection:
                    connection.execute(
                        """
                        UPDATE jobs
                        SET created_at = ?
                        WHERE id = 1
                        """,
                        ("2026-04-20T12:00:00+00:00",),
                    )
                    connection.execute(
                        """
                        UPDATE actions
                        SET completed_at = ?
                        WHERE queue = 'screen'
                        """,
                        ("2026-04-22T12:00:00+00:00",),
                    )

            metrics = self.run_cli(
                db_path,
                "metrics",
                "--since",
                "2026-04-20T00:00:00+00:00",
                "--until",
                "2026-05-01T00:00:00+00:00",
            )

            for expected in (
                "jobs_screened=1",
                "applications_submitted=1",
                "applications_by_lane=fintech:1",
                "ready_to_apply_rate=100.0%",
                "interview_rate=100.0%",
                "rejection_rate=100.0%",
                "outreach_response_rate=100.0%",
                "companies_touched=1",
                "actions_completed=1",
                "average_days_from_discovery_to_application=7.0",
            ):
                self.assertIn(expected, metrics.stdout)

    def test_metrics_reports_funnel_query_quality_and_source_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(
                db_path,
                "company",
                "add",
                "Stripe",
                "--career-url",
                "https://stripe.com/jobs",
                "--ats-type",
                "greenhouse",
            )
            self.run_cli(
                db_path,
                "company",
                "add",
                "OpenAI",
                "--career-url",
                "https://openai.com/careers",
            )
            self.run_cli(
                db_path,
                "company",
                "add",
                "WorkdayCo",
                "--ats-type",
                "workday",
            )
            self.run_cli(
                db_path,
                "job",
                "add",
                "Stripe",
                "Product Lead",
                "--url",
                "https://jobs.example.com/stripe/product-lead",
            )
            self.run_cli(db_path, "job", "status", "1", "ready_to_apply")
            self.run_cli(db_path, "job", "add", "OpenAI", "Product Manager")
            self.run_cli(
                db_path,
                "source",
                "add",
                "Stripe",
                "--type",
                "greenhouse",
                "--key",
                "stripe",
            )
            payload_path = Path(tmpdir) / "query-run.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "source": "linkedin_mcp",
                        "pack": "FINTECH",
                        "query": "senior product manager payroll",
                        "results": [
                            {
                                "company": "Mercury",
                                "title": "Senior Product Manager",
                                "url": "https://jobs.example.com/mercury/pm",
                                "status": "accepted",
                            },
                            {
                                "company": "NoisyCo",
                                "title": "Product Manager",
                                "url": "https://jobs.example.com/noisy/pm",
                                "status": "rejected",
                                "notes": "search_noisy: people-manager-heavy results",
                            },
                            {
                                "company": "WeakCo",
                                "title": "Growth Product Manager",
                                "url": "https://jobs.example.com/weak/growth",
                                "status": "rejected",
                                "notes": "consumer growth role",
                            },
                            {
                                "company": "Stripe",
                                "title": "Product Lead",
                                "url": "https://jobs.example.com/stripe/product-lead",
                                "status": "accepted",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.run_cli(db_path, "query", "import", "--file", str(payload_path))
            self.run_cli(db_path, "company", "add", "Mercury")
            self.run_cli(
                db_path,
                "job",
                "add",
                "Mercury",
                "Senior Product Manager",
                "--url",
                "https://jobs.example.com/mercury/pm",
                "--status",
                "ready_to_apply",
            )

            with closing(self.connect(db_path)) as connection:
                with connection:
                    connection.execute(
                        """
                        UPDATE query_runs
                        SET created_at = ?, updated_at = ?
                        """,
                        (
                            "2026-04-01T12:00:00+00:00",
                            "2026-04-29T12:00:00+00:00",
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE query_run_results
                        SET updated_at = ?
                        """,
                        (
                            "2026-04-29T12:00:00+00:00",
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE companies
                        SET last_checked_at = ?
                        WHERE name = ?
                        """,
                        ("2026-04-01T00:00:00+00:00", "WorkdayCo"),
                    )
                    connection.execute(
                        """
                        UPDATE companies
                        SET status = 'archived'
                        WHERE name = ?
                        """,
                        ("Mercury",),
                    )
                    connection.execute("UPDATE actions SET status = 'skipped'")
                    self.insert_action(
                        connection,
                        1,
                        job_id=1,
                        due_at="2026-04-20T00:00:00+00:00",
                    )

            metrics = self.run_cli(
                db_path,
                "metrics",
                "--since",
                "2026-04-20T00:00:00+00:00",
                "--until",
                "2026-05-01T00:00:00+00:00",
            )

            self.assertIn(
                "bucket_resolution=resolved_jobs=2 unresolved_jobs=1 "
                "resolution_rate=66.7%",
                metrics.stdout,
            )
            self.assertIn(
                "reviewed_query_results=results=4 reviewed=4 pending=0 "
                "accepted=1 rejected=2 duplicate=1 noisy=1 review_rate=100.0%",
                metrics.stdout,
            )
            self.assertIn(
                "accepted_high_signal_roles=query_results_accepted=1 "
                "matched_high_signal_jobs=1 unconverted_accepted_results=0 "
                "ready_or_later_jobs=2",
                metrics.stdout,
            )
            self.assertIn(
                "stale_actions=open=1 stale=1 by_queue=apply:1",
                metrics.stdout,
            )
            self.assertIn(
                "target_company_coverage=active_targets=3 with_active_sources=1 "
                "missing_active_sources=2 missing_source_details=1 "
                "official_fallback_only=1 unsupported_sources=1 stale_checks=3",
                metrics.stdout,
            )

    def test_done_message_action_generates_single_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")
            self.run_cli(db_path, "company", "add", "Mercury", "--tier", "2")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    company_id = connection.execute(
                        "SELECT id FROM companies WHERE name = ?", ("Mercury",)
                    ).fetchone()[0]
                    connection.execute(
                        """
                        INSERT INTO actions(company_id, queue, kind, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (company_id, "research", "send_message", NOW, NOW),
                    )

            self.run_cli(db_path, "action", "done", "1", "--message-sent")
            self.run_cli(db_path, "action", "done", "1", "--message-sent")

            with closing(self.connect(db_path)) as connection:
                follow_up_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM actions
                    WHERE queue = 'follow_up' AND kind = 'follow_up'
                    """
                ).fetchone()[0]
                events = connection.execute(
                    """
                    SELECT event_type, COUNT(*)
                    FROM events
                    GROUP BY event_type
                    ORDER BY event_type
                    """
                ).fetchall()

            self.assertEqual(follow_up_count, 1)
            self.assertEqual(
                events,
                [
                    ("action_done", 1),
                    ("company_added", 1),
                    ("message_sent", 1),
                ],
            )


if __name__ == "__main__":
    unittest.main()

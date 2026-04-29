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

    def insert_job(self, connection: sqlite3.Connection, company_id: int) -> int:
        connection.execute(
            """
            INSERT INTO jobs(company_id, title, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (company_id, "Product Lead", "manual", NOW, NOW),
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
    ) -> int:
        connection.execute(
            """
            INSERT INTO gaps(company_id, job_id, gap_type, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (company_id, job_id, "domain", "Needs proof", NOW, NOW),
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
        status: str = "queued",
        completed_at: str | None = None,
    ) -> int:
        connection.execute(
            """
            INSERT INTO actions(
                company_id, job_id, contact_id, artifact_id, gap_id, queue, kind,
                status, completed_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                job_id,
                contact_id,
                artifact_id,
                gap_id,
                "apply",
                "apply",
                status,
                completed_at,
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
    ) -> int:
        connection.execute(
            """
            INSERT INTO events(
                company_id, job_id, contact_id, artifact_id, gap_id, action_id,
                event_type, happened_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                job_id,
                contact_id,
                artifact_id,
                gap_id,
                action_id,
                "note",
                NOW,
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

            self.assertIn("schema_version=3", first.stdout)
            self.assertIn("schema_version=3", second.stdout)
            self.assertIn("schema_version=3", status.stdout)
            self.assertIn("companies=0", status.stdout)
            self.assertIn("jobs=0", status.stdout)
            self.assertIn("actions=0", status.stdout)

            with closing(self.connect(db_path)) as connection:
                migration_count = connection.execute(
                    "SELECT COUNT(*) FROM schema_migrations"
                ).fetchone()[0]
                self.assertEqual(migration_count, 3)
            self.assertEqual(db_path.stat().st_mode & 0o777, 0o600)

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

            self.assertIn("schema_version=3", migrated.stdout)
            self.assertEqual([row[0] for row in versions], [1, 2, 3])
            self.assertEqual(actions[0][0], "queued")
            self.assertEqual(actions[1][0], "skipped")
            self.assertIn("schema v2 migration", actions[1][1])

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
                        jobs.application_folder
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
                    ),
                    (
                        "Relo Metrics",
                        "Senior Product Manager",
                        "ignored_by_filter",
                        "PASS",
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
                    ),
                    (
                        "Stripe",
                        "Product Manager, Payments",
                        "discovered",
                        "FINTECH",
                        "YOUR_PROFILE/Fintech/FINTECH.md",
                        None,
                        None,
                    ),
                ],
            )
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
                "#3 | apply:apply | queued | due=unscheduled | Coinbase / Senior Product Manager",
                next_apply.stdout,
            )
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
                "#1 | research:vet_company | queued | "
                "due=2026-04-30T16:00:00+00:00 | Ramp",
                next_research.stdout,
            )

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
                "No interview",
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
            self.run_cli(db_path, "job", "status", "1", "ready_to_apply")
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

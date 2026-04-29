from __future__ import annotations

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

            self.assertIn("schema_version=2", first.stdout)
            self.assertIn("schema_version=2", second.stdout)
            self.assertIn("schema_version=2", status.stdout)
            self.assertIn("companies=0", status.stdout)
            self.assertIn("jobs=0", status.stdout)
            self.assertIn("actions=0", status.stdout)

            with closing(self.connect(db_path)) as connection:
                migration_count = connection.execute(
                    "SELECT COUNT(*) FROM schema_migrations"
                ).fetchone()[0]
                self.assertEqual(migration_count, 2)
            self.assertEqual(db_path.stat().st_mode & 0o777, 0o600)

    def test_init_migrates_duplicate_open_actions_before_dedupe_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"
            self.run_cli(db_path, "init")

            with closing(self.connect(db_path)) as connection:
                with connection:
                    connection.execute("DROP INDEX idx_actions_open_dedupe")
                    connection.execute("DELETE FROM schema_migrations WHERE version = 2")
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

            self.assertIn("schema_version=2", migrated.stdout)
            self.assertEqual([row[0] for row in versions], [1, 2])
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

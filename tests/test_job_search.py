from __future__ import annotations

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

            self.assertIn("schema_version=1", first.stdout)
            self.assertIn("schema_version=1", second.stdout)
            self.assertIn("schema_version=1", status.stdout)
            self.assertIn("companies=0", status.stdout)
            self.assertIn("jobs=0", status.stdout)
            self.assertIn("actions=0", status.stdout)

            with closing(self.connect(db_path)) as connection:
                migration_count = connection.execute(
                    "SELECT COUNT(*) FROM schema_migrations"
                ).fetchone()[0]
                self.assertEqual(migration_count, 1)
            self.assertEqual(db_path.stat().st_mode & 0o777, 0o600)

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


if __name__ == "__main__":
    unittest.main()

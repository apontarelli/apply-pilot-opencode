from __future__ import annotations

import json
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
JOB_SEARCH_CLI = REPO_ROOT / "scripts" / "job_search.py"
HANDOFF_CLI = REPO_ROOT / "scripts" / "linkedin_mcp_query_handoff.py"


class LinkedInMcpQueryHandoffTests(unittest.TestCase):
    def run_job_search(self, db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(JOB_SEARCH_CLI), "--db-path", str(db_path), *args],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

    def run_handoff(
        self,
        db_path: Path,
        *args: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(HANDOFF_CLI),
                "--db-path",
                str(db_path),
                *args,
            ],
            cwd=REPO_ROOT,
            check=check,
            text=True,
            capture_output=True,
        )

    def connect(self, db_path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def test_prepare_imports_validated_details_without_raw_mcp_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "job_search.sqlite"
            search_path = root / "search.json"
            details_path = root / "details.json"
            output_path = root / "linkedin-query-run.json"
            self.run_job_search(db_path, "init")
            search_path.write_text(
                json.dumps({"job_ids": ["4252026496", "4252026497"]}),
                encoding="utf-8",
            )
            details_path.write_text(
                json.dumps(
                    [
                        {
                            "job_id": "4252026496",
                            "payload": {
                                "title": "Senior Product Manager, Payroll",
                                "companyName": "Gusto",
                                "jobUrl": "https://www.linkedin.com/jobs/view/4252026496",
                                "location": "United States",
                                "workplaceType": "Remote",
                                "description": "Full raw JD text should stay out of the import row.",
                                "sessionCookie": "secret-cookie",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_handoff(
                db_path,
                "prepare",
                "--pack",
                "FINTECH",
                "--query-index",
                "1",
                "--search-json",
                str(search_path),
                "--details-json",
                str(details_path),
                "--sort-mode",
                "relevance",
                "--output",
                str(output_path),
                "--import",
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))

            with closing(self.connect(db_path)) as connection:
                run = connection.execute(
                    """
                    SELECT source, pack, status, result_count, accepted_count, rejected_count
                    FROM query_runs
                    """
                ).fetchone()
                rows = connection.execute(
                    """
                    SELECT title, result_status, source_job_id, raw_payload
                    FROM query_run_results
                    ORDER BY ordinal
                    """
                ).fetchall()

            self.assertIn("query run created", result.stdout)
            self.assertEqual(run, ("linkedin_mcp", "FINTECH", "completed", 2, 1, 1))
            self.assertEqual(rows[0][:3], ("Senior Product Manager, Payroll", "accepted", "4252026496"))
            self.assertEqual(rows[1][1], "rejected")
            self.assertIn("stale_or_thin_result", rows[1][3])
            serialized_payload = json.dumps(payload)
            self.assertNotIn("Full raw JD text", serialized_payload)
            self.assertNotIn("secret-cookie", serialized_payload)

    def test_failure_classes_drive_failed_partial_and_completed_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "job_search.sqlite"
            details_path = root / "details.json"
            failed_output = root / "failed.json"
            partial_output = root / "partial.json"
            noisy_output = root / "noisy.json"
            details_path.write_text(
                json.dumps(
                    {
                        "4252026496": {
                            "title": "Senior Product Manager, AI Workflow",
                            "companyName": "OpenAI",
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.run_handoff(
                db_path,
                "prepare",
                "--pack",
                "AI",
                "--query-index",
                "1",
                "--failure",
                "auth_required",
                "--output",
                str(failed_output),
            )
            self.run_handoff(
                db_path,
                "prepare",
                "--pack",
                "AI",
                "--query-index",
                "1",
                "--details-json",
                str(details_path),
                "--failure",
                "rate_limited",
                "--output",
                str(partial_output),
            )
            self.run_handoff(
                db_path,
                "prepare",
                "--pack",
                "AI",
                "--query-index",
                "1",
                "--failure",
                json.dumps({"class": "search_noisy", "message": "too many generic PM roles"}),
                "--output",
                str(noisy_output),
            )

            self.assertEqual(json.loads(failed_output.read_text())["status"], "failed")
            self.assertEqual(json.loads(partial_output.read_text())["status"], "partial")
            noisy_payload = json.loads(noisy_output.read_text())
            self.assertEqual(noisy_payload["status"], "completed")
            self.assertIn("failure_class=search_noisy", noisy_payload["notes"])

    def test_single_raw_detail_object_is_not_treated_as_job_id_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "job_search.sqlite"
            details_path = root / "single-detail.json"
            output_path = root / "payload.json"
            details_path.write_text(
                json.dumps(
                    {
                        "job_id": "4252026496",
                        "title": "Senior Product Manager, Payroll",
                        "companyName": "Gusto",
                    }
                ),
                encoding="utf-8",
            )

            self.run_handoff(
                db_path,
                "prepare",
                "--pack",
                "FINTECH",
                "--query-index",
                "1",
                "--details-json",
                str(details_path),
                "--output",
                str(output_path),
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual(len(payload["results"]), 1)
            self.assertEqual(payload["results"][0]["source_job_id"], "4252026496")
            self.assertEqual(payload["results"][0]["status"], "accepted")

    def test_limit_caps_search_and_extra_detail_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "job_search.sqlite"
            search_path = root / "search.json"
            details_path = root / "details.json"
            output_path = root / "payload.json"
            search_path.write_text(
                json.dumps({"job_ids": ["4252026496", "4252026497"]}),
                encoding="utf-8",
            )
            details_path.write_text(
                json.dumps(
                    {
                        "4252026498": {
                            "title": "Senior Product Manager, Payroll",
                            "companyName": "Gusto",
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.run_handoff(
                db_path,
                "prepare",
                "--pack",
                "FINTECH",
                "--query-index",
                "1",
                "--search-json",
                str(search_path),
                "--details-json",
                str(details_path),
                "--limit",
                "2",
                "--output",
                str(output_path),
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual(
                [result["source_job_id"] for result in payload["results"]],
                ["4252026496", "4252026497"],
            )

    def test_debug_capture_is_redacted_local_only_and_referenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "job_search.sqlite"
            search_path = root / "search.json"
            details_path = root / "details.json"
            output_path = root / "payload.json"
            debug_dir = root / "debug"
            search_path.write_text(
                json.dumps({"job_ids": ["4252026496"], "authToken": "secret-token"}),
                encoding="utf-8",
            )
            details_path.write_text(
                json.dumps(
                    {
                        "4252026496": {
                            "title": "Senior Product Manager, Payroll",
                            "companyName": "Gusto",
                            "profileEmail": "person@example.com",
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.run_handoff(
                db_path,
                "prepare",
                "--pack",
                "FINTECH",
                "--query-index",
                "1",
                "--search-json",
                str(search_path),
                "--details-json",
                str(details_path),
                "--output",
                str(output_path),
                "--debug-capture",
                "--debug-dir",
                str(debug_dir),
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            debug_files = list(debug_dir.glob("*.json"))

            self.assertEqual(len(debug_files), 1)
            mode = stat.S_IMODE(debug_files[0].stat().st_mode)
            self.assertEqual(mode, 0o600)
            debug_text = debug_files[0].read_text(encoding="utf-8")
            self.assertIn("[REDACTED]", debug_text)
            self.assertNotIn("secret-token", debug_text)
            self.assertNotIn("person@example.com", debug_text)
            self.assertIn("debug_payload=", payload["raw_source_reference"])

    def test_exception_pack_still_requires_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "job_search.sqlite"

            result = self.run_handoff(
                db_path,
                "prepare",
                "--pack",
                "ACCESS",
                "--query-index",
                "1",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Query pack ACCESS is an exception pack", result.stderr)


if __name__ == "__main__":
    unittest.main()

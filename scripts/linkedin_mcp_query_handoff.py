#!/usr/bin/env python3
"""Prepare LinkedIn MCP query-run import payloads.

This script is intentionally a local handoff helper. Codex is responsible for
calling LinkedIn MCP tools and saving their read-only outputs. The deterministic
job_search CLI remains the SQLite control layer and never owns LinkedIn auth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import job_search


SOURCE = "linkedin_mcp"
DEFAULT_DEBUG_DIR = job_search.REPO_ROOT / "APPLICATIONS" / "_ops" / "query_runs"
FAILURE_CLASSES = (
    "auth_required",
    "session_expired",
    "mcp_unavailable",
    "network_error",
    "rate_limited",
    "malformed_payload",
    "search_noisy",
    "stale_or_thin_result",
    "detail_validation_failed",
    "partial_results",
)
RUN_FAILURE_CLASSES = {
    "auth_required",
    "session_expired",
    "mcp_unavailable",
    "network_error",
    "rate_limited",
    "malformed_payload",
    "search_noisy",
    "partial_results",
}
RESULT_FAILURE_CLASSES = {
    "malformed_payload",
    "stale_or_thin_result",
    "detail_validation_failed",
}
SECRET_KEY_PARTS = (
    "authorization",
    "cookie",
    "csrf",
    "email",
    "li_at",
    "phone",
    "profile",
    "session",
    "token",
)


@dataclass(frozen=True)
class DetailRecord:
    job_id: str
    payload: object
    decision: str | None = None
    notes: str | None = None
    failure_class: str | None = None


def utc_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json_file(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON file {path}: {error.msg}") from error


def compact(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return re.sub(r"\s+", " ", text) if text else None


def key_matches(key: str, names: Iterable[str]) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return normalized in {re.sub(r"[^a-z0-9]", "", name.casefold()) for name in names}


def first_string(payload: object, names: Iterable[str]) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key_matches(str(key), names):
                candidate = compact(value)
                if candidate:
                    return candidate
        for value in payload.values():
            candidate = first_string(value, names)
            if candidate:
                return candidate
    elif isinstance(payload, list):
        for item in payload:
            candidate = first_string(item, names)
            if candidate:
                return candidate
    return None


def job_id_from_text(value: object) -> str | None:
    text = compact(value)
    if not text:
        return None
    match = re.search(r"(?:jobs/view/|jobPosting:|job:)?(\d{6,})", text)
    if match:
        return match.group(1)
    if re.fullmatch(r"\d{6,}", text):
        return text
    return None


def job_id_from_object(value: object) -> str | None:
    if isinstance(value, (str, int)):
        return job_id_from_text(value)
    if not isinstance(value, dict):
        return None
    for key in ("job_id", "jobId", "id", "jobPostingId", "entityUrn", "urn", "url"):
        if key in value:
            candidate = job_id_from_text(value[key])
            if candidate:
                return candidate
    return first_string(value, ("job_id", "jobId", "jobPostingId"))


def list_value(payload: object, names: Iterable[str]) -> list[object] | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key_matches(str(key), names) and isinstance(value, list):
                return value
        for value in payload.values():
            nested = list_value(value, names)
            if nested is not None:
                return nested
    return None


def search_job_ids(search_payload: object | None) -> list[str]:
    if search_payload is None:
        return []
    candidates: list[object]
    if isinstance(search_payload, list):
        candidates = search_payload
    else:
        candidates = list_value(
            search_payload,
            ("job_ids", "jobIds", "ids", "jobs", "results", "elements", "items"),
        ) or []

    seen: set[str] = set()
    job_ids: list[str] = []
    for candidate in candidates:
        job_id = job_id_from_object(candidate)
        if job_id and job_id not in seen:
            seen.add(job_id)
            job_ids.append(job_id)
    return job_ids


def detail_records(details_payload: object | None) -> dict[str, DetailRecord]:
    if details_payload is None:
        return {}
    raw_records: list[object]
    if isinstance(details_payload, dict):
        if "details" in details_payload and isinstance(details_payload["details"], list):
            raw_records = details_payload["details"]
        elif all(
            job_id_from_text(key) and isinstance(value, (dict, list))
            for key, value in details_payload.items()
        ):
            raw_records = [
                {"job_id": key, "payload": value}
                for key, value in details_payload.items()
            ]
        else:
            raw_records = [details_payload]
    elif isinstance(details_payload, list):
        raw_records = details_payload
    else:
        raise ValueError("details JSON must be an object or array")

    records: dict[str, DetailRecord] = {}
    for index, raw in enumerate(raw_records, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"detail record #{index} must be an object")
        payload = raw.get("payload", raw.get("detail", raw))
        job_id = compact(raw.get("job_id") or raw.get("jobId")) or job_id_from_object(payload)
        if not job_id:
            raise ValueError(f"detail record #{index} is missing job_id")
        failure_class = compact(raw.get("failure_class"))
        if failure_class and failure_class not in FAILURE_CLASSES:
            raise ValueError(f"Unknown failure class: {failure_class}")
        records[job_id] = DetailRecord(
            job_id=job_id,
            payload=payload,
            decision=compact(raw.get("decision") or raw.get("status")),
            notes=compact(raw.get("notes")),
            failure_class=failure_class,
        )
    return records


def failure_records(values: list[str] | None) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for value in values or []:
        parsed = json.loads(value) if value.strip().startswith("{") else {"class": value}
        if not isinstance(parsed, dict):
            raise ValueError("--failure must be a class name or JSON object")
        failure_class = compact(parsed.get("class") or parsed.get("failure_class"))
        if failure_class not in FAILURE_CLASSES:
            raise ValueError(f"Unknown failure class: {failure_class}")
        record = {"class": failure_class}
        message = compact(parsed.get("message") or parsed.get("notes"))
        if message:
            record["message"] = message
        failures.append(record)
    return failures


def run_status(failures: list[dict[str, str]], result_count: int) -> str:
    run_failures = [item["class"] for item in failures if item["class"] in RUN_FAILURE_CLASSES]
    if not run_failures:
        return "completed"
    if run_failures == ["search_noisy"]:
        return "completed"
    if result_count > 0:
        return "partial"
    return "failed"


def notes_with_failures(notes: str | None, failures: list[dict[str, str]], search_count: int) -> str | None:
    parts: list[str] = []
    if notes:
        parts.append(notes)
    if search_count:
        parts.append(f"linkedin_search_result_count={search_count}")
    for failure in failures:
        text = f"failure_class={failure['class']}"
        if failure.get("message"):
            text += f": {failure['message']}"
        parts.append(text)
    return "\n".join(parts) if parts else None


def normalize_result(job_id: str, record: DetailRecord | None) -> dict[str, object]:
    if record is None:
        return {
            "title": f"LinkedIn job {job_id}",
            "source_job_id": job_id,
            "url": f"https://www.linkedin.com/jobs/view/{job_id}",
            "status": "rejected",
            "notes": "failure_class=stale_or_thin_result: no get_job_details payload captured",
            "raw_source_reference": f"linkedin_job:{job_id}",
        }

    payload = record.payload
    title = first_string(payload, ("title", "job_title", "jobTitle"))
    company = first_string(payload, ("company", "company_name", "companyName"))
    url = first_string(
        payload,
        ("canonical_url", "url", "job_url", "jobUrl", "linkedin_url", "apply_url", "applyUrl"),
    )
    location = first_string(payload, ("location", "formattedLocation"))
    remote_status = first_string(payload, ("remote_status", "remote", "workplaceType", "workplace"))
    compensation = first_string(
        payload,
        ("compensation_signal", "compensation", "salary", "salaryRange", "payRange"),
    )
    source_job_id = first_string(payload, ("source_job_id", "job_id", "jobId", "id")) or job_id

    failure_class = record.failure_class
    notes = record.notes
    if not title or not company:
        failure_class = failure_class or "detail_validation_failed"
    if failure_class and failure_class not in RESULT_FAILURE_CLASSES:
        failure_class = "detail_validation_failed"

    result_status = record.decision or "accepted"
    if result_status == "pass":
        result_status = "rejected"
    if failure_class:
        result_status = "rejected"
        prefix = f"failure_class={failure_class}"
        notes = f"{prefix}: {notes}" if notes else prefix
    if result_status not in job_search.QUERY_RESULT_STATUSES:
        raise ValueError(f"Invalid detail decision for LinkedIn job {job_id}: {result_status}")

    result = {
        "company": company,
        "title": title or f"LinkedIn job {job_id}",
        "url": url or f"https://www.linkedin.com/jobs/view/{job_id}",
        "source_job_id": source_job_id,
        "location": location,
        "remote_status": remote_status,
        "compensation_signal": compensation,
        "status": result_status,
        "notes": notes,
        "raw_source_reference": f"linkedin_job:{job_id}",
    }
    return {key: value for key, value in result.items() if value is not None}


def stable_raw_source_reference(pack: str, query_text: str, sort_mode: str | None) -> str:
    digest = hashlib.sha256(
        "\x1f".join([pack, query_text, sort_mode or ""]).encode("utf-8")
    ).hexdigest()[:12]
    return f"linkedin_mcp:{pack}:{digest}:{utc_stamp()}"


def redact(value: object) -> object:
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, item in value.items():
            normalized_key = str(key).casefold()
            if any(secret in normalized_key for secret in SECRET_KEY_PARTS):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[REDACTED_EMAIL]", value)
        return value
    return value


def write_json(path: Path, payload: object, *, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(mode)


def debug_capture_reference(
    *,
    enabled: bool,
    debug_dir: Path,
    pack: str,
    query_text: str,
    search_payload: object | None,
    details_payload: object | None,
    failures: list[dict[str, str]],
) -> str | None:
    if not enabled:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", f"{pack}-{query_text}".casefold()).strip("-")[:80]
    path = debug_dir / f"{utc_stamp().replace(':', '').replace('+', 'Z')}-{slug}.json"
    write_json(
        path,
        redact(
            {
                "source": SOURCE,
                "pack": pack,
                "query": query_text,
                "search": search_payload,
                "details": details_payload,
                "failures": failures,
            }
        ),
    )
    try:
        return str(path.relative_to(job_search.REPO_ROOT))
    except ValueError:
        return str(path)


def build_payload(args: argparse.Namespace) -> dict[str, object]:
    pack = job_search.get_query_pack(args.pack)
    job_search.validate_query_pack_run(pack, args.reason)
    if args.query_index and args.query_index > len(pack.queries):
        raise ValueError(
            f"Query index {args.query_index} exceeds pack {pack.name} size {len(pack.queries)}"
        )
    query_text = args.query or (pack.queries[args.query_index - 1] if args.query_index else None)
    if not query_text:
        raise ValueError("LinkedIn handoff requires --query or --query-index")
    if query_text not in pack.queries:
        raise ValueError(f"Query is not part of pack {pack.name}: {query_text}")

    search_payload = read_json_file(Path(args.search_json)) if args.search_json else None
    details_payload = read_json_file(Path(args.details_json)) if args.details_json else None
    failures = failure_records(args.failure)
    details = detail_records(details_payload)

    job_ids = search_job_ids(search_payload)
    if not job_ids:
        job_ids = list(details)
    ordered_ids = list(job_ids)
    for job_id in details:
        if job_id not in ordered_ids:
            ordered_ids.append(job_id)
    if args.limit:
        ordered_ids = ordered_ids[: args.limit]

    results = [normalize_result(job_id, details.get(job_id)) for job_id in ordered_ids]
    status = args.status or run_status(failures, len(results))
    if status not in ("completed", "partial", "failed"):
        raise ValueError("LinkedIn handoff status must be completed, partial, or failed")

    debug_reference = debug_capture_reference(
        enabled=args.debug_capture,
        debug_dir=Path(args.debug_dir),
        pack=pack.name,
        query_text=query_text,
        search_payload=search_payload,
        details_payload=details_payload,
        failures=failures,
    )
    raw_reference = stable_raw_source_reference(pack.name, query_text, args.sort_mode)
    if debug_reference:
        raw_reference = f"{raw_reference}; debug_payload={debug_reference}"

    payload: dict[str, object] = {
        "source": SOURCE,
        "pack": pack.name,
        "query": query_text,
        "sort_mode": args.sort_mode,
        "status": status,
        "result_count": len(results),
        "raw_source_reference": raw_reference,
        "notes": notes_with_failures(args.notes, failures, len(job_ids)),
        "results": results,
    }
    return {key: value for key, value in payload.items() if value is not None}


def command_prepare(args: argparse.Namespace) -> int:
    payload = build_payload(args)
    output = Path(args.output) if args.output else None
    if output:
        write_json(output, payload)
        print(f"wrote LinkedIn MCP query payload: {output}")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))

    if args.import_run:
        if output is None:
            raise ValueError("--import requires --output so job_search imports the saved payload")
        command = [
            sys.executable,
            str(job_search.REPO_ROOT / "scripts" / "job_search.py"),
            "--db-path",
            args.db_path,
            "query",
            "import",
            "--file",
            str(output),
        ]
        result = subprocess.run(
            command,
            cwd=job_search.REPO_ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        return result.returncode
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare local query-run import payloads from LinkedIn MCP output."
    )
    parser.add_argument("--db-path", default=str(job_search.DEFAULT_DB_PATH))
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare",
        help="Normalize saved LinkedIn MCP search/detail output into a query import payload.",
    )
    prepare.add_argument("--pack", required=True)
    query_group = prepare.add_mutually_exclusive_group(required=True)
    query_group.add_argument("--query")
    query_group.add_argument("--query-index", type=job_search.positive_int)
    prepare.add_argument("--reason")
    prepare.add_argument("--search-json")
    prepare.add_argument("--details-json")
    prepare.add_argument("--sort-mode", choices=("relevance", "date"))
    prepare.add_argument("--limit", type=job_search.positive_int)
    prepare.add_argument("--status", choices=("completed", "partial", "failed"))
    prepare.add_argument("--failure", action="append")
    prepare.add_argument("--notes")
    prepare.add_argument("--output")
    prepare.add_argument("--import", dest="import_run", action="store_true")
    prepare.add_argument("--debug-capture", action="store_true")
    prepare.add_argument("--debug-dir", default=str(DEFAULT_DEBUG_DIR))
    prepare.set_defaults(func=command_prepare)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return args.func(args)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

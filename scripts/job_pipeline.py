#!/usr/bin/env python3
"""Track job-screening decisions across sessions."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


REPO_ROOT = Path(__file__).resolve().parent.parent
OPS_DIR = REPO_ROOT / "APPLICATIONS" / "_ops"
LEDGER_PATH = OPS_DIR / "job_pipeline.jsonl"
DASHBOARD_PATH = OPS_DIR / "JOB_PIPELINE.md"

STATUSES = (
    "queued",
    "screened_out",
    "watch",
    "ready_to_apply",
    "applied",
    "skipped",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def slugify(value: str) -> str:
    collapsed = collapse_spaces(value).lower()
    return re.sub(r"[^a-z0-9]+", "-", collapsed).strip("-")


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    cleaned = parsed._replace(query="", fragment="")
    normalized_path = re.sub(r"/+", "/", cleaned.path).rstrip("/")
    cleaned = cleaned._replace(path=normalized_path)
    return urlunsplit(
        (
            cleaned.scheme.lower(),
            cleaned.netloc.lower(),
            cleaned.path,
            cleaned.query,
            cleaned.fragment,
        )
    )


def make_key(company: str, role: str, location: str | None, job_url: str | None) -> str:
    if job_url:
        return f"url:{normalize_url(job_url)}"

    parts = [slugify(company), slugify(role)]
    if location:
        parts.append(slugify(location))
    return "job:" + "|".join(filter(None, parts))


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def write_records(path: Path, records: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    ordered = sorted(records, key=lambda item: item.get("updated_at", ""), reverse=True)
    payload = "\n".join(json.dumps(record, sort_keys=True) for record in ordered)
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")


def display_path(path_value: str | None) -> str:
    if not path_value:
        return ""

    path = Path(path_value)
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def render_record(record: dict[str, Any]) -> str:
    fragments = [
        record.get("company", ""),
        record.get("role", ""),
        record.get("status", ""),
    ]
    summary = " | ".join(fragment for fragment in fragments if fragment)
    extras: list[str] = []
    if record.get("lane"):
        extras.append(f"lane={record['lane']}")
    if record.get("recommendation"):
        extras.append(f"recommendation={record['recommendation']}")
    if record.get("updated_at"):
        extras.append(f"updated={record['updated_at']}")
    if extras:
        summary += " | " + " | ".join(extras)
    return summary


def build_dashboard(records: list[dict[str, Any]]) -> str:
    counts = Counter(record.get("status", "queued") for record in records)
    lines = [
        "# Job Pipeline",
        "",
        f"Updated: {utc_now()}",
        "",
        "## Counts",
        "",
    ]

    for status in STATUSES:
        lines.append(f"- `{status}`: {counts.get(status, 0)}")

    sections = (
        ("ready_to_apply", "Ready To Apply"),
        ("watch", "Watch"),
        ("applied", "Applied"),
        ("screened_out", "Screened Out"),
        ("skipped", "Skipped"),
        ("queued", "Queued"),
    )

    for status, heading in sections:
        lines.extend(["", f"## {heading}", ""])
        matching = [record for record in records if record.get("status") == status][:25]
        if not matching:
            lines.append("- None")
            continue

        for record in matching:
            line = f"- `{record.get('company', '')}` | `{record.get('role', '')}`"
            if record.get("lane"):
                line += f" | lane `{record['lane']}`"
            if record.get("recommendation"):
                line += f" | recommendation `{record['recommendation']}`"
            if record.get("location"):
                line += f" | {record['location']}"
            if record.get("risks"):
                line += f" | risk: {record['risks']}"
            lines.append(line)

            detail_parts: list[str] = []
            if record.get("search_query"):
                detail_parts.append(f"query `{record['search_query']}`")
            if record.get("job_url"):
                detail_parts.append(record["job_url"])
            if record.get("jd_path"):
                detail_parts.append(f"JD `{display_path(record['jd_path'])}`")
            if record.get("qa_path"):
                detail_parts.append(f"QA `{display_path(record['qa_path'])}`")
            if record.get("search_path"):
                detail_parts.append(f"SEARCH `{display_path(record['search_path'])}`")
            if record.get("coverletter_path"):
                detail_parts.append(f"COVERLETTER `{display_path(record['coverletter_path'])}`")
            if detail_parts:
                lines.append(f"  - {' | '.join(detail_parts)}")

    return "\n".join(lines) + "\n"


def write_dashboard(path: Path, records: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    path.write_text(build_dashboard(records), encoding="utf-8")


def find_existing(
    records: list[dict[str, Any]],
    company: str,
    role: str,
    location: str | None,
    job_url: str | None,
) -> dict[str, Any] | None:
    key = make_key(company, role, location, job_url)
    for record in records:
        if record.get("id") == key:
            return record
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track job-screening decisions.")
    parser.add_argument(
        "--ledger-path",
        default=str(LEDGER_PATH),
        help="Path to the JSONL ledger file.",
    )
    parser.add_argument(
        "--dashboard-path",
        default=str(DASHBOARD_PATH),
        help="Path to the generated markdown dashboard.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    upsert = subparsers.add_parser("upsert", help="Insert or update a tracked role.")
    upsert.add_argument("--company", required=True)
    upsert.add_argument("--role", required=True)
    upsert.add_argument("--status", required=True, choices=STATUSES)
    upsert.add_argument("--location")
    upsert.add_argument("--source", default="linkedin")
    upsert.add_argument("--job-url")
    upsert.add_argument("--lane")
    upsert.add_argument("--recommendation")
    upsert.add_argument("--search-query")
    upsert.add_argument("--query-pack")
    upsert.add_argument("--summary")
    upsert.add_argument("--why-now")
    upsert.add_argument("--risks")
    upsert.add_argument("--notes")
    upsert.add_argument("--bucket")
    upsert.add_argument("--jd-path")
    upsert.add_argument("--search-path")
    upsert.add_argument("--qa-path")
    upsert.add_argument("--coverletter-path")
    upsert.add_argument("--user-action")

    find = subparsers.add_parser("find", help="Look up a tracked role.")
    find.add_argument("--company", required=True)
    find.add_argument("--role", required=True)
    find.add_argument("--location")
    find.add_argument("--job-url")

    summary = subparsers.add_parser("summary", help="Print a markdown summary.")
    summary.add_argument("--status", choices=STATUSES)
    summary.add_argument("--limit", type=int, default=10)

    return parser.parse_args()


def command_upsert(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger_path)
    dashboard_path = Path(args.dashboard_path)
    records = load_records(ledger_path)

    existing = find_existing(records, args.company, args.role, args.location, args.job_url)
    record_id = make_key(args.company, args.role, args.location, args.job_url)
    now = utc_now()

    base: dict[str, Any] = dict(existing) if existing else {}
    base.update(
        {
            "id": record_id,
            "company": collapse_spaces(args.company),
            "role": collapse_spaces(args.role),
            "status": args.status,
            "source": args.source,
            "updated_at": now,
            "last_screened_at": now,
        }
    )
    if not existing:
        base["created_at"] = now

    optional_fields = {
        "location": args.location,
        "job_url": normalize_url(args.job_url) if args.job_url else None,
        "lane": args.lane,
        "recommendation": args.recommendation,
        "search_query": args.search_query,
        "query_pack": args.query_pack,
        "summary": args.summary,
        "why_now": args.why_now,
        "risks": args.risks,
        "notes": args.notes,
        "bucket": args.bucket,
        "jd_path": args.jd_path,
        "search_path": args.search_path,
        "qa_path": args.qa_path,
        "coverletter_path": args.coverletter_path,
        "user_action": args.user_action,
    }

    for key, value in optional_fields.items():
        if value is not None:
            base[key] = value

    updated_records = []
    replaced = False
    for record in records:
        if record.get("id") == record_id:
            updated_records.append(base)
            replaced = True
        else:
            updated_records.append(record)

    if not replaced:
        updated_records.append(base)

    write_records(ledger_path, updated_records)
    write_dashboard(dashboard_path, updated_records)
    print(render_record(base))
    return 0


def command_find(args: argparse.Namespace) -> int:
    records = load_records(Path(args.ledger_path))
    existing = find_existing(records, args.company, args.role, args.location, args.job_url)
    if existing is None:
        print("NOT_FOUND")
        return 1

    print(json.dumps(existing, indent=2, sort_keys=True))
    return 0


def command_summary(args: argparse.Namespace) -> int:
    records = load_records(Path(args.ledger_path))
    if args.status:
        records = [record for record in records if record.get("status") == args.status]

    print(build_dashboard(records[: args.limit] if args.status else records))
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "upsert":
        return command_upsert(args)
    if args.command == "find":
        return command_find(args)
    if args.command == "summary":
        return command_summary(args)
    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

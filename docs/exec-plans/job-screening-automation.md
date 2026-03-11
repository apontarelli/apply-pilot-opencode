# Job Screening Automation

Status: superseded by `docs/exec-plans/job-search-command-center.md`.

Keep this document as historical context for the role-first JSONL pipeline. Do not use it as the active implementation plan.

## Purpose

Make LinkedIn discovery durable across sessions instead of repeating the same screening decisions in chat.

## Decisions

- Keep LinkedIn MCP as the discovery source.
- Let `$job-search` screen roles in batches and continue into `$job-apply` when the user asks for end-to-end vetting.
- Treat `$job-apply` as the last automated gate before Antonio applies manually.
- Persist every decision in a local ledger.

## Ledger

Paths:
- `APPLICATIONS/_ops/job_pipeline.jsonl`
- `APPLICATIONS/_ops/JOB_PIPELINE.md`

Script:
- `python3 scripts/job_pipeline.py`

Minimum tracked fields:
- company
- role
- status
- lane
- interest_level
- comp_signal
- recommendation
- search query
- risks

Statuses:
- `screened_out`
- `watch`
- `ready_to_apply`
- `applied`

## Workflow

1. `$job-search` reads the pipeline summary.
2. It skips roles already screened unless there is a reason to revisit.
3. It validates a role with LinkedIn MCP.
4. If the role survives the first screen and the user wants full vetting, it continues into `$job-apply`.
5. `$job-apply` decides whether the role is worth Antonio's time and saves materials under `APPLICATIONS/READY_TO_APPLY/`.
6. The ledger is updated after every role.
7. Every `ready_to_apply` handoff shown to Antonio includes the canonical job link.
8. Every `ready_to_apply` handoff shown to Antonio includes the resume to use and any app-specific materials to review.

## Live Findings

- LinkedIn search is noisy enough that duplicate prevention and durable logging are necessary.
- Relevance sorting is often better than date sorting for discovery.
- Good workflow fit is still not enough if the title implies direct people management or the domain gap is too large.
- Interest and disclosed comp need to be treated as first-class gates, not just notes.
- Current base-comp bands: `180k` floor, `205k-225k` target, `230k+` premium/stretch.

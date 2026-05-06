---
name: career-command-center
description: "Use when the user wants the daily job-search operating loop: inspect command-center status, next actions, company/job queues, follow-ups, research/artifact/proof-gap work, outcomes, metrics, or decide what to do next from existing repo state. Hand discovery/search/LinkedIn intake to $job-search and ready-JD application materials to $job-apply. Never submit applications or message people without explicit human direction."
---

# Career Command Center

Use this skill for the stateful career operating loop over the repo's command
center.

Do not use it for live job-board discovery, LinkedIn URL intake, JD
normalization, resume routing, cover letters, application answers, autonomous
application submission, or outreach.

## Goals

1. Start from current command-center state.
2. Make the next action obvious.
3. Keep companies, jobs, actions, gaps, artifacts, outcomes, and metrics clean.
4. Include direct job links whenever recommending or summarizing job-specific
   actions.
5. Route discovery work to `$job-search`.
6. Route ready-JD application work to `$job-apply` only when it adds value
   beyond the command-center record.

## Read First

- `docs/PRODUCT_STRATEGY.md`
- `docs/HOW_IT_WORKS.md`
- `docs/README.md`
- `YOUR_PROFILE/CAREER_STRATEGY.md`
- `YOUR_PROFILE/APPLICATION_PLAYBOOK.md`

Read skill docs only when routing into them:

- `.agents/skills/job-search/SKILL.md`
- `.agents/skills/job-apply/SKILL.md`

## Default Workflow

Start every command-center session with:

```bash
python3 scripts/job_search.py status
python3 scripts/job_search.py action next
```

If `status` says the database is not initialized, run:

```bash
python3 scripts/job_search.py init
```

Then classify the user's request:

- daily loop, stale actions, queue health, outcomes, metrics, or strategy
  feedback: stay in `$career-command-center`
- role search, LinkedIn/canonical URL intake, broad query runs, ATS polling
  validation, or JD normalization: route to `$job-search`
- ready JD, saved `JD.md`, missing resume lane, application answers, cover
  letter, package verification, or final apply package: route to `$job-apply`

When presenting job-specific next actions, always include the job URL from the
command output or job record. If no URL is stored, say `url=missing` and make
capturing the canonical link part of the next action.

## Operating Surfaces

Use `scripts/job_search.py` as the deterministic command surface.

Common reads:

- `python3 scripts/job_search.py status`
- `python3 scripts/job_search.py action next`
- `python3 scripts/job_search.py action next --queue <queue>`
- `python3 scripts/job_search.py company list`
- `python3 scripts/job_search.py company show "Company"`
- `python3 scripts/job_search.py job list --company "Company"`
- `python3 scripts/job_search.py contact list --company "Company"`
- `python3 scripts/job_search.py event list --company "Company"`
- `python3 scripts/job_search.py metrics`
- `python3 scripts/job_search.py report cooldowns`
- `python3 scripts/job_search.py report proof-gaps`
- `python3 scripts/job_search.py report query-pack-tuning`
- `python3 scripts/job_search.py report strategy-feedback`

Common writes:

- `python3 scripts/job_search.py company update "Company" ...`
- `python3 scripts/job_search.py job status <job_id> <status> --notes "..."`
- `python3 scripts/job_search.py event add --company "Company" --type note --notes "..."`
- `python3 scripts/job_search.py action add --company "Company" --queue <queue> --kind <kind> --notes "..."`
- `python3 scripts/job_search.py action done <action_id> --notes "..."`

Use exact commands from `docs/HOW_IT_WORKS.md` when syntax matters.

## Queue Semantics

Treat queues as operator surfaces:

- `screen`: roles or companies needing fit validation; usually route to
  `$job-search` when external details are needed
- `apply`: ready or near-ready application work; route to `$job-apply` only
  when materials need creation, verification, answers, cover-letter guidance,
  or a final submit checklist. If the command-center record already has the
  link, resume, materials path, and no unanswered form requirements, present it
  directly as manual-submit work.
- `follow_up`: reminders, outcomes, and human-approved follow-up preparation
- `research`: company, contact, source, or market research
- `artifact`: proof gaps, portfolio ideas, demos, teardown work, or reusable
  materials
- `classify`: stale or ambiguous records needing a durable decision

Do not create duplicate actions when an existing open action already captures
the next step. Update or complete the current action instead.

## Outcome Hygiene

Own `classify` queue cleanup and weekly outcome hygiene in the command center.
Use the exact operating taxonomy in `docs/HOW_IT_WORKS.md` when recording
application dispositions or rejection reasons.

Durable fields:

- `jobs.status`: lifecycle state, set with
  `python3 scripts/job_search.py job status <job_id> <status> --notes "..."` or
  `job update`.
- `jobs.application_outcome`: comparable disposition such as
  `pending_response`, `active_interview_loop`, `rejected_before_screen`,
  `rejected_after_screen`, `rejected_after_interview`, `closed_before_apply`,
  `passed_by_candidate`, or `archived_no_action`.
- `jobs.rejection_reason`: comparable reason such as `fit_mismatch`,
  `level_scope_mismatch`, `recruiter_screen_risk`, `missing_proof`,
  `compensation_mismatch`, `location_or_work_model_mismatch`,
  `timing_or_capacity`, `stale_or_closed_posting`,
  `duplicate_or_already_tracked`, or `low_interest`.
- `events.notes` and `actions.notes`: evidence and handoff detail.

Use taxonomy values for anything that should group in metrics or strategy
feedback. Use freeform notes for the proof behind the classification: recruiter
feedback, comp number, screen-risk detail, source link, or why the operator chose
the bucket.

Common classify flow:

```bash
python3 scripts/job_search.py action next --queue classify --limit 10
python3 scripts/job_search.py job update <job_id> --status rejected --application-outcome rejected_before_screen --rejection-reason recruiter_screen_risk
python3 scripts/job_search.py event add --company "Company" --job-id <job_id> --type rejection_received --notes "Auto-reject after submit; likely PM-years/title screen."
python3 scripts/job_search.py action done <action_id> --notes "classified outcome=rejected_before_screen reason=recruiter_screen_risk"
```

For stale `applied` or `interviewing` jobs, choose the current known disposition
instead of leaving the hygiene item open: `pending_response`,
`active_interview_loop`, `rejected_after_screen`, `rejected_after_interview`,
`passed_by_candidate`, or `archived_no_action`. Reserve `closed_before_apply`
for roles that closed before submission.

Keep broad query source-quality reasons out of job outcomes. `search_noisy`,
`malformed_payload`, `stale_or_thin_result`, `detail_validation_failed`, and
duplicate/noisy broad-source rows stay in `query_run_results.notes` until
SID-145 creates query-pack tuning reports. Only use job-level reasons after a
result has become a command-center job.

Use `python3 scripts/job_search.py report cooldowns` during weekly outcome
hygiene or before adding new work for a company or repeated role pattern. Treat
the report as advisory only: inspect the evidence rows, distinguish temporary
timing/interview/no-screen cooldowns from durable pass or low-priority signals,
then make any company status, action, or due-date changes explicitly through the
normal commands. Do not let the report hide jobs, cancel actions, or mutate
company state automatically.

Use `python3 scripts/job_search.py report proof-gaps` during weekly review to
identify recurring missing-proof patterns that may justify profile, bullet,
artifact, resume-lane, application-playbook, or Linear follow-up work.

Use `python3 scripts/job_search.py report query-pack-tuning` after reviewed
query runs accumulate. Treat candidate edits as recommendations; do not let the
report edit query-pack config automatically.

Use `python3 scripts/job_search.py report strategy-feedback` for weekly
keep/change/defer recommendations across outcomes, metrics, cooldowns, proof
gaps, target-company coverage, and reviewed query quality. Keep the workflow in
the command center, and route live discovery to `$job-search` or ready-JD
materials work to `$job-apply`.

## Decision Rules

Every meaningful role or company review should end with one of:

- `ready_to_apply`
- `low_effort_apply`
- `stretch_warm_path`
- `portfolio_gap`
- `watch`
- `pass`

Keep these questions separate:

1. Do we like it?
2. Can Antonio credibly win it now?
3. If not now, is it worth building toward?

Create campaign, proof-gap, watch, or pass actions only when there is a concrete
next step or durable reason. Do not let company excitement create vague queue
items.

## Handoffs

Use `$job-search` when the next step requires:

- live LinkedIn or job-board search
- canonical posting validation
- query-pack runs
- ATS polling review
- JD normalization
- role screening from external job text

Use `$job-apply` when the next step requires:

- resume lane selection
- pass/apply recommendation from a ready JD
- application answers
- cover letter guidance
- saved application package materials
- package verification before manual submission

Do not route to `$job-apply` just because a role is in the `apply` queue. If
the command-center row already identifies the resume and materials path, the
command-center can directly tell Antonio: company, role, job link, resume,
materials path, and action id to close after manual submission.

For several independent apply actions, the command center may prepare a
parallel handoff plan to run `$job-apply` per role when the user explicitly asks
for subagents or parallel prep. Each subagent should own one role, verify or
create only that role's package, and return:

- company
- role
- job link
- action id and job id
- resume lane
- materials path
- missing form answers or package gaps
- exact command-center update needed after Antonio submits or passes

For handoffs, include:

- company
- role, if any
- job link, if any
- current command-center state
- exact open action or job id, if known
- reason for the handoff
- expected output back into the command center

## Guardrails

- SQLite at `APPLICATIONS/_ops/job_search.sqlite` is the source of truth.
- LinkedIn, browser tabs, and external boards are discovery surfaces only.
- Do not submit applications without explicit human direction.
- Do not message people without explicit human direction.
- Do not store raw LinkedIn/MCP payloads in durable artifacts unless the user
  explicitly asks for local debugging capture.
- Do not let resume polishing block application volume.
- Prefer small, clear state updates over broad speculative cleanup.

# Job Search Command Center Plan

## Purpose

Replace the role-first JSONL job pipeline with a company-first job-search command center.

The system should help Antonio decide what to do next across target companies, roles, contacts, artifacts, gaps, and outcomes without overbuilding a CRM or making LinkedIn scraping the source of truth.

## Product Decisions

- Primary model: company-first.
- Primary surface: Codex conversation.
- Control layer: deterministic CLI.
- Source of truth: SQLite.
- Dashboard: no Markdown dashboard in v1.
- Daily workflow: queue-based execution.
- Queue model: separate queues by action type.
- Targets: lightweight targets, not strict quotas.
- Automation posture: manual-first with assistive automation.
- Polling: not in first slice, but important for v1.1.

## Strategic Alignment

The system should reinforce the current search thesis:

- Primary lanes:
  - fintech / platform PM
  - AI workflow PM
  - access / trust workflow PM
- Selective bridge lanes:
  - product engineer
  - forward deployed / solutions
  - implementation / technical customer-facing roles
- Target-company motion:
  - understand the company
  - identify roles where existing proof maps cleanly
  - find warm paths before applying when possible
  - build targeted proof artifacts for tier 1 companies

## V1 Scope

Build `scripts/job_search.py` as a new clean CLI.

Use SQLite at `APPLICATIONS/_ops/job_search.sqlite`.

Core entities:

- `companies`
- `jobs`
- `contacts`
- `artifacts`
- `gaps`
- `actions`
- `events`

Core commands:

```bash
python3 scripts/job_search.py init
python3 scripts/job_search.py company add ...
python3 scripts/job_search.py company show Coinbase
python3 scripts/job_search.py job add ...
python3 scripts/job_search.py contact add ...
python3 scripts/job_search.py artifact add ...
python3 scripts/job_search.py gap add ...
python3 scripts/job_search.py action next --queue apply --limit 5
python3 scripts/job_search.py action done <id>
python3 scripts/job_search.py event add ...
python3 scripts/job_search.py metrics
```

## Queues

V1 queues:

- `screen`: evaluate fresh roles
- `apply`: submit ready roles
- `follow_up`: timed relationship or application follow-ups
- `research`: fill company, role, or domain gaps
- `artifact`: build or send targeted proof
- `classify`: record outcomes, rejection reasons, or stale state

Daily use:

1. Ask Codex what is next in a queue.
2. Process multiple items based on available time and energy.
3. Mark actions done, blocked, skipped, or rescheduled.

## Action Generation Rules

Auto-create obvious actions, with manual edits allowed.

Initial rules:

- New tier 1 company with no contacts -> `find_contact`.
- New promising role -> `screen_role`.
- Role marked `ready_to_apply` -> `apply`.
- Application submitted -> optional `follow_up` in 5-7 business days.
- Message sent -> `follow_up` in 3-5 business days.
- Rejection logged -> `classify_outcome`.
- Tier 1 company with no artifact -> `artifact_idea`.
- Open high-severity gap -> `fill_gap` or `artifact` action.

## Data Model Notes

### Companies

Track durable target-company state:

- name
- tier
- lanes
- why interesting
- fit thesis
- known gaps
- products used
- target roles
- career URL
- ATS type
- status
- cooldown until
- last touched at
- last checked at
- notes

### Jobs

Track role-level execution:

- company
- title
- canonical URL
- source
- source job ID
- location / remote status
- role level
- lane
- status
- discovery status
- fit score
- relationship path
- artifact opportunity
- recommended resume
- materials status
- application folder / material paths
- compensation signal
- rejection reason
- application outcome

### Contacts

Minimal v1 contact tracking:

- name
- company
- title
- source / link
- relationship strength
- last contacted at
- notes

### Artifacts

Minimal targeted-proof tracking:

- company
- related job optional
- type
- status
- thesis
- link / path
- notes

### Gaps

Structured but light gap records:

- company optional
- job optional
- gap type
- description
- severity
- status
- resolution action optional

### Actions

Actions are first-class queue items linked to a company and optionally to a job, contact, artifact, or gap.

Statuses:

- `queued`
- `in_progress`
- `done`
- `blocked`
- `skipped`
- `rescheduled`

### Events

Append-only history:

- application submitted
- rejection received
- interview
- message sent
- coffee chat
- referral ask
- artifact sent
- gap identified
- status changed

Events should power metrics and company history.

## Rejections And Cooldowns

Track rejection at the job/application level, then roll up company state.

Default rules:

- No-interview rejection -> company cooldown of 30-60 days.
- Interview-loop rejection -> company cooldown of 90-180 days.
- Materially different team or role can bypass cooldown.
- Rejection with clear gap should create a gap record and resolution action.

Company show output should answer:

- last applied role
- last outcome
- cooldown until
- unresolved gaps
- next best action

## Discovery And Polling

First slice:

- Manual job intake.
- Source definitions for target companies.
- No automated polling.

V1.1 implemented slice:

- Target-company polling first through explicit `source` definitions and manual `poll` runs.
- ATS-native integrations before generic page scraping.
- Initial ATS priority:
  - Greenhouse
  - Lever
  - Ashby
  - Workday only if a target company justifies it

Polling should:

- preserve all discovered jobs
- create `screen` actions only for moderately strict matches
- mark weak matches `ignored_by_filter`
- dedupe with layered rules

Duplicate rules:

- Strong duplicate:
  - same ATS job ID
  - same normalized URL
- Likely duplicate:
  - same company
  - similar normalized title
  - same location / remote status
  - same active 60-day window
- Repost:
  - likely duplicate where prior job is closed or older than 60 days

## Metrics

Track minimal weekly metrics from events:

- jobs screened
- applications submitted
- applications by lane
- ready-to-apply rate
- interview rate
- rejection rate
- outreach response rate
- companies touched
- actions completed
- average days from discovery to application

Metrics are for weekly review, not daily pressure.

## Cutover

Status: complete for the role-first JSONL workflow.

Cutover changes:

- Removed the active `scripts/job_pipeline.py` command path.
- No legacy `APPLICATIONS/_ops/job_pipeline.jsonl` or `APPLICATIONS/_ops/JOB_PIPELINE.md` files existed in this workspace at cutover time, so there were no records to migrate.
- Updated `$job-search`, `YOUR_PROFILE/APPLICATION_PLAYBOOK.md`, and `README.md` to use the company-first SQLite command center.

Historical references to the old pipeline may remain only in superseded exec plans.

## Non-Goals

- No UI.
- No auto-apply.
- No auto-outreach.
- No inbox automation.
- No full CRM.
- No generic web scraper in v1.
- No Markdown dashboard in v1.
- No complex scoring model.
- No broad market polling in the first polling slice.

## Validation

Implementation should include:

- CLI help output for core commands.
- SQLite init and migration test.
- Unit tests for:
  - action generation
  - duplicate detection
  - cooldown calculation
  - metrics aggregation
- Manual smoke test:
  - add Coinbase
  - add one role
  - mark ready to apply
  - confirm apply action exists
  - log rejection
  - confirm cooldown, gap/action behavior, and company show output

## Linear Tracking Recommendation

Use Linear if implementation will be split across more than one focused work session or if polling starts immediately.

Recommended Linear shape:

- Project: Job Search Command Center
- Ticket 1: SQLite schema and CLI foundation
- Ticket 2: Company, job, and action workflows
- Ticket 3: Contacts, artifacts, gaps, and events
- Ticket 4: Cut over `$job-search` and remove old pipeline
- Ticket 5: Metrics and validation tests
- Later ticket: ATS-native target-company polling

Do not create Linear tickets for the planning conversation alone. Create them once implementation is ready to start or when the work needs to be delegated.

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

## Broad Job-board Query Workflow

Status: v1 decision for `SID-100`.

Chosen strategy: hybrid, with source-gated query packs.

Use two repeatable discovery motions:

- Source-first for known target companies:
  - run configured official ATS sources through `source` and `poll`
  - prefer Greenhouse, Lever, and Ashby APIs before official career pages
  - use official company career pages only as manual/browser fallback when no ATS source is configured
- Query-pack-first within each broad source adapter:
  - run explicit `FINTECH` and `AI` packs against LinkedIn MCP or another board source
  - keep `ACCESS` and other variants as role-specific exception packs when a posting or target-company source warrants them
  - record one query run per source and pack before accepting or rejecting jobs
  - validate promising broad-source hits through the canonical posting before adding them as jobs

Rejected alternatives:

- Source-first only:
  - too reliable-but-narrow for discovery beyond the configured company list
  - misses high-fit roles at companies not yet in the command center
- Query-pack-first only:
  - recreates the noisy LinkedIn/manual-search problem in a more durable wrapper
  - makes duplicate prevention and follow-up sequencing harder because source reliability differs by board
- LinkedIn-only:
  - fragile because MCP auth/session drift and loose search matching are already known failure modes
  - violates the system goal of not making LinkedIn scraping the source of truth

### Query Run Record

Each broad discovery run should become a durable record before jobs are accepted into the command center.

Minimum fields:

- source:
  - `linkedin_mcp`
  - `official_company_page`
  - `ats_greenhouse`
  - `ats_lever`
  - `ats_ashby`
  - `manual_browser`
- query pack:
  - `FINTECH`
  - `AI`
  - role-specific exception pack, such as `ACCESS`, only when justified by a specific posting or target-company exception
- query text or query pack item
- sort mode when the source exposes it, such as `relevance` or `date`
- run status:
  - `completed`
  - `partial`
  - `failed`
- result count returned by the source
- candidate count accepted into `jobs`
- rejected count with concise reasons
- duplicate count
- follow-up actions created, such as `screen_role`, `research_company`, or `add_source`
- raw source reference when useful:
  - LinkedIn job ID
  - ATS job ID
  - normalized canonical URL
  - saved local import file path
- run notes for source failures, noisy result patterns, or pack tuning

The query run is not a job application artifact. It is an audit trail for discovery quality and for avoiding repeated broad searches that produce the same weak results.

### Failure And Noise Handling

LinkedIn MCP failure handling:

- A failed `linkedin_mcp` run should be recorded as `failed` or `partial`, with the error class in notes.
- Failure should not block the whole discovery session.
- The operator should continue with:
  - configured ATS `poll` runs for target companies
  - official company career pages for high-priority targets
  - manual/browser import for a small set of visible promising roles
- Do not add jobs from malformed LinkedIn search-result metadata without validating the detail page or canonical company posting.

Noisy broad results:

- Start with narrow problem-domain query packs, not generic title-only searches.
- Cap each source/pack pass to a reviewable result set before broadening.
- Reject or down-rank malformed metadata, people-management-heavy titles, stale/thin posts, and roles where the JD shifts away from the query intent.
- Record rejected/noisy counts on the query run so future pack tuning has evidence.
- Only jobs that survive detail validation should enter `jobs`; low-signal search results stay in query-run notes, not the main job list.

### Duplicate Interaction

Duplicate detection must run before a discovered result becomes a new `jobs` row.

Layering:

- Imported Notion or legacy pipeline history becomes command-center history first, through an import command that creates companies, jobs, events, and outcomes.
- New broad-source candidates are compared against imported history and current jobs using the existing duplicate rules:
  - normalized canonical URL
  - source plus source job ID
  - same company, similar normalized title, same location/remote status, active 60-day window
- Strong duplicates should increment the query run duplicate count and should not create new jobs.
- Likely duplicates should not create a new job by default; record the existing job ID and only add a new job when the canonical posting is materially different.
- Reposts can become new jobs only when the prior job is closed or outside the active duplicate window; the new run should still link notes back to the prior job.

### Proposed Command Surface

Smallest next implementation surface:

```bash
python3 scripts/job_search.py query run --source linkedin_mcp --pack FINTECH --limit 25
python3 scripts/job_search.py query run --source linkedin_mcp --pack AI --limit 15
python3 scripts/job_search.py query run --source manual_browser --pack ACCESS --reason "specific access/trust target role"
python3 scripts/job_search.py query import --source manual_browser --pack FINTECH --path APPLICATIONS/_ops/query-runs/fintech.json
python3 scripts/job_search.py query list --source linkedin_mcp --pack FINTECH
python3 scripts/job_search.py query show <query_run_id>
```

Implementation notes:

- `query run` can start as a record-and-review command; source execution can stay MCP/manual-assisted until a safe adapter boundary exists.
- `query import` is the fallback for LinkedIn MCP failures and manual/browser runs.
- Accepted jobs should still be written through existing `job add` semantics or the same internal storage path so duplicate checks and action generation remain centralized.
- Target-company ATS polling remains `source add` plus `poll`, not a query command.
- Non-FINTECH/AI variants require an explicit reason on the run; `ACCESS` is not a default v1 broad-search lane.

### Follow-up Implementation Slices

Ready:

- Proposed ticket: Add query run schema and CLI read/write surface.
  - Acceptance:
    - SQLite migration adds `query_runs` and `query_run_results` or an equivalent normalized structure.
    - CLI supports `query import`, `query list`, and `query show`.
    - Imported result rows record source, pack, query text, result count, accepted/rejected/duplicate counts, and notes.
    - Duplicate candidates are reported against existing jobs without creating new jobs.
  - Validation:
    - `make test`
    - targeted tests for query import idempotency and duplicate reporting

- Proposed ticket: Add query-pack registry for FINTECH and AI, with exception-pack support.
  - Acceptance:
    - Packs are machine-readable from the repo, not only prose.
    - CLI can list packs and queries.
    - Exception packs require an explicit reason when used in broad query runs.
    - ACCESS pack is available for identity, trust, permissions, access, controls, and risk workflow terms, but is not listed as a default v1 broad-search lane.
  - Validation:
    - `make test`
    - targeted parser/registry tests

Needs grooming:

- Proposed ticket: Add LinkedIn MCP query adapter behind the query run interface.
  - Needs decisions:
    - how Codex-external MCP calls are invoked from a deterministic CLI
    - whether raw MCP payloads should be saved locally for replay
    - how auth/session failures should be classified
  - Acceptance draft:
    - failed MCP runs create a failed query-run record
    - successful runs normalize source job IDs and canonical URLs before duplicate checks
    - detail validation is required before accepting a candidate into `jobs`
  - Validation draft:
    - unit tests with saved MCP-like fixtures
    - manual smoke run when LinkedIn MCP auth is available

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
- Added `python3 scripts/job_search.py import-pipeline` for workspaces that still have legacy `APPLICATIONS/_ops/job_pipeline.jsonl` records.
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

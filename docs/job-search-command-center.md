# Job Search Command Center

The job-search command center is the durable operating system for active job discovery, screening, application tracking, and outcome history.

## Current Shape

- Primary surface: Codex conversation.
- Control layer: `scripts/job_search.py`.
- Source of truth: SQLite at `APPLICATIONS/_ops/job_search.sqlite`.
- Primary workflow: company-first, queue-based execution.
- Default search lanes: FINTECH / platform PM and AI workflow PM.
- Exception lanes: ACCESS / trust workflow, media platform, industrial/autonomy, and other variants only when a specific role or target-company source warrants them.
- Automation posture: manual-first with assistive automation.
- LinkedIn posture: useful discovery source, not the source of truth.

The command center tracks:

- `companies`
- `company_sources`
- `jobs`
- `contacts`
- `artifacts`
- `gaps`
- `actions`
- `events`

## Core Commands

```bash
python3 scripts/job_search.py init
python3 scripts/job_search.py status
python3 scripts/job_search.py company add "Company"
python3 scripts/job_search.py company show "Company"
python3 scripts/job_search.py company list
python3 scripts/job_search.py source add "Company" --type greenhouse --key <board-token>
python3 scripts/job_search.py source list --company "Company"
python3 scripts/job_search.py poll --company "Company"
python3 scripts/job_search.py job add --company "Company" --title "Senior Product Manager" --source manual
python3 scripts/job_search.py job list --company "Company"
python3 scripts/job_search.py action next --queue apply --limit 5
python3 scripts/job_search.py action done <action_id>
python3 scripts/job_search.py event add --company "Company" --type note --notes "..."
python3 scripts/job_search.py event list --company "Company"
python3 scripts/job_search.py metrics
python3 scripts/job_search.py import-pipeline
```

Run `python3 scripts/job_search.py import-pipeline` only when a legacy `APPLICATIONS/_ops/job_pipeline.jsonl` file exists. The old role-first `scripts/job_pipeline.py` workflow has been removed.

## Daily Workflow

1. Check the command center before searching:

```bash
python3 scripts/job_search.py status
python3 scripts/job_search.py action next
```

2. For a known company, inspect history before adding work:

```bash
python3 scripts/job_search.py company show "Company"
python3 scripts/job_search.py job list --company "Company"
python3 scripts/job_search.py event list --company "Company"
```

3. Process queued work by queue:

- `screen`: evaluate fresh roles.
- `apply`: submit ready roles.
- `follow_up`: timed relationship or application follow-ups.
- `research`: fill company, role, or domain gaps.
- `artifact`: build or send targeted proof.
- `classify`: record outcomes, rejection reasons, or stale state.

4. Record the final state in SQLite through `scripts/job_search.py`.

## Target-Company Polling

Configured target-company polling is source-first.

- Add explicit ATS sources with `source add`.
- Poll configured active sources with `poll`.
- Prefer Greenhouse, Lever, and Ashby APIs before official career-page browsing.
- Use official company career pages as manual/browser fallback when no ATS source is configured.
- Workday support should wait until a target company justifies it.

Polling behavior:

- Preserve all discovered jobs.
- Create `screen` actions only for moderately strict target-role matches.
- Mark weak matches `ignored_by_filter`.
- Dedupe using layered rules.

Duplicate rules:

- Strong duplicate: same normalized URL or same source plus source job ID.
- Likely duplicate: same company, similar normalized title, same location or remote status, and same active 60-day window.
- Repost: likely duplicate where the prior job is closed or older than the active duplicate window.

## Broad Job-Board Query Strategy

SID-100 chose a hybrid strategy: source-gated query packs.

Use two repeatable discovery motions:

- Source-first for known target companies:
  - run configured official ATS sources through `source` and `poll`
  - use official career pages only as manual/browser fallback
- Query-pack-first within broad source adapters:
  - run explicit FINTECH and AI packs against LinkedIn MCP or another broad board source
  - keep ACCESS and other variants as role-specific exception packs
  - record one query run per source and pack before accepting or rejecting jobs
  - validate promising broad-source hits through the canonical posting before adding them as jobs

Rejected alternatives:

- Source-first only: reliable but too narrow for discovery beyond the configured company list.
- Query-pack-first only: recreates noisy broad search with weaker duplicate prevention.
- LinkedIn-only: too fragile because MCP auth/session drift and loose matching are known failure modes.

## Query Run Record

Broad discovery runs should become durable records before jobs are accepted into the command center.

Minimum fields:

- source, such as `linkedin_mcp`, `official_company_page`, `ats_greenhouse`, `ats_lever`, `ats_ashby`, or `manual_browser`
- query pack: `FINTECH`, `AI`, or an explicitly justified exception pack
- query text or query pack item
- sort mode when available
- run status: `completed`, `partial`, or `failed`
- result count
- accepted candidate count
- rejected candidate count with concise reasons
- duplicate count
- follow-up actions created
- raw source reference when useful
- notes for source failures, noisy result patterns, or pack tuning

The query run is not an application artifact. It is an audit trail for discovery quality and for avoiding repeated broad searches that produce the same weak results.

## Failure And Noise Handling

LinkedIn MCP failures:

- Record failed or partial runs with the error class in notes.
- Do not block the whole discovery session.
- Continue with configured ATS polls, high-priority official career pages, or manual/browser import for a small set of visible promising roles.
- Do not add jobs from malformed LinkedIn search-result metadata without validating the detail page or canonical company posting.

Noisy broad results:

- Start with narrow problem-domain query packs.
- Cap each source/pack pass to a reviewable result set before broadening.
- Reject malformed metadata, people-management-heavy titles, stale/thin posts, and roles where the JD shifts away from the query intent.
- Only jobs that survive detail validation should enter `jobs`.

## Query Packs

The default repeatable broad-search packs are:

- FINTECH / platform
- AI / workflow

ACCESS and other variants are exception packs. They are valid for specific access/trust roles or target-company exceptions, but they are not default broad-search lanes.

The current prose pack guidance lives in `.agents/skills/job-search/references/query-packs.md`. SID-102 should make these packs machine-readable.

## Current Next Work

Tracked in Linear project `Job Search Command Center`:

- SID-101: Add query run schema and CLI import surface.
- SID-102: Add query-pack registry with exception-pack guardrails.
- SID-103: Groom LinkedIn MCP query adapter design.

Recommended order:

1. SID-102, so query-pack defaults and exception-pack rules are executable.
2. SID-101, so manual/imported broad discovery runs have durable storage.
3. SID-103, after the CLI/MCP boundary is clarified.

## Validation

Before handoff, run:

```bash
make test
```

For command-center changes, include targeted tests around:

- migrations
- duplicate detection
- action generation
- query-pack validation
- query-run import/list/show behavior
- metrics aggregation when touched

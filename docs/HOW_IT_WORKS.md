# How It Works

This is the operating source of truth for the current job-search system:
commands, workflow, SQLite state, polling, LinkedIn handoff, and validation.

Longer-term product direction, problem framing, milestones, and success metrics
live in [Product Strategy](PRODUCT_STRATEGY.md).

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
- `query_runs`
- `query_run_results`
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
python3 scripts/job_search.py company import --file APPLICATIONS/_ops/researched-companies/fintech-targets.json
python3 scripts/job_search.py company show "Company"
python3 scripts/job_search.py company list
python3 scripts/job_search.py source add "Company" --type greenhouse --key <board-token>
python3 scripts/job_search.py source list --company "Company"
python3 scripts/job_search.py poll --company "Company"
python3 scripts/job_search.py query import --file APPLICATIONS/_ops/query-runs/fintech.json
python3 scripts/job_search.py query import --source manual_browser --pack FINTECH --query "senior product manager payroll" --result-count 12 --raw-source-reference manual-2026-04-29
python3 scripts/job_search.py query list
python3 scripts/job_search.py query show <query_run_id>
python3 scripts/job_search.py query packs list --default-only
python3 scripts/job_search.py query packs show FINTECH
python3 scripts/job_search.py query run --source linkedin_mcp --pack FINTECH --limit 25
python3 scripts/linkedin_mcp_query_handoff.py prepare --pack FINTECH --query-index 1 --search-json APPLICATIONS/_ops/query_runs/linkedin-search.json --details-json APPLICATIONS/_ops/query_runs/linkedin-details.json --output APPLICATIONS/_ops/query-runs/fintech-linkedin.json --import
python3 scripts/job_search.py job add --company "Company" --title "Senior Product Manager" --source manual
python3 scripts/job_search.py job list --company "Company"
python3 scripts/job_search.py action next --queue apply --limit 5
python3 scripts/job_search.py action list --queue apply --limit 25
python3 scripts/job_search.py action done <action_id>
python3 scripts/job_search.py event add --company "Company" --type note --notes "..."
python3 scripts/job_search.py event list --company "Company"
python3 scripts/job_search.py metrics
python3 scripts/job_search.py report hygiene
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

Use a direct review command for each daily lane:

```bash
python3 scripts/job_search.py action next --queue screen --limit 10
python3 scripts/job_search.py action next --queue apply --limit 10
python3 scripts/job_search.py action next --queue follow_up --limit 10
python3 scripts/job_search.py action next --queue research --limit 10
python3 scripts/job_search.py action next --queue artifact --limit 10
python3 scripts/job_search.py action next --queue classify --limit 10
```

Use `action list --queue <queue> --limit <n>` when reviewing a larger lane backlog.
By default, `action next` and `action list` show open work only. Add `--status done`,
`--status skipped`, or another lifecycle status when reviewing history or a specific
state. Open queue review output labels each shown action as `stale`, `due`, `blocked`,
or `ready`, then shows linked company, job, contact, artifact, and gap context when
present.

4. Record the final state in SQLite through `scripts/job_search.py`.

5. Check hygiene before ending a session:

```bash
python3 scripts/job_search.py report hygiene
```

The hygiene report is read-only. It surfaces stale `follow_up`, `apply`, and
`classify` actions, old unscheduled apply/classify/follow-up actions, jobs whose
application or rejection events still need final outcome/disposition cleanup,
and recently active companies that no longer have an open next action. Each row
includes stable action, job, company, or event IDs needed to resolve the item
through the normal command paths.

## Target-Company Polling

Configured target-company polling is source-first.

- Default discovery workflow: research target companies externally, import the
  researched-company JSON, review configured ATS sources, then run `poll`.
- Use `company import --file <path>` for Codex/ChatGPT research output that
  includes company thesis, target roles, career URL, and ATS source details.
- Add explicit ATS sources with `source add`.
- Poll configured active sources with `poll`.
- Prefer Greenhouse, Lever, and Ashby APIs before official career-page browsing.
- Use official company career pages as manual/browser fallback when no ATS source is configured.
- Workday support should wait until a target company justifies it.

Researched-company import accepts either a JSON array or an object with a
`companies` array. Each row should use a small, reviewable shape:

```json
{
  "name": "ExampleCo",
  "tier": 1,
  "lanes": ["FINTECH", "AI"],
  "why_interesting": "Why this company belongs on the target list.",
  "fit_thesis": "Why Antonio's proof maps to the company.",
  "target_roles": ["Senior Product Manager", "Product Lead"],
  "career_url": "https://example.com/careers",
  "ats_type": "greenhouse",
  "ats_source_key": "exampleco",
  "notes": "Research notes worth preserving."
}
```

Import behavior:

- Upserts companies by normalized `name_key`; missing fields never wipe existing
  values.
- Upserts `company_sources` for supported `greenhouse`, `lever`, and `ashby`
  sources using the existing `(company_id, source_type, source_key)` uniqueness.
- Reports each row as `company_created`, `company_updated`, or
  `company_existing`, plus source outcomes such as `source_created`,
  `source_updated`, `source_existing`, `needs_manual_source`,
  `unsupported_ats`, or `invalid_row`.
- Does not create jobs. Run `poll` explicitly after review.

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

Broad job-board APIs are secondary/backlog. Do not make SerpApi, JSearch,
DataForSEO, Adzuna, or another broad API the default discovery backbone unless a
future ticket explicitly changes that posture.

Use two repeatable discovery motions:

- Source-first for known target companies:
  - run configured official ATS sources through `source` and `poll`
  - use official career pages only as manual/browser fallback
- Query-pack-first within broad source adapters:
  - run explicit FINTECH and AI packs from `config/job_search_query_packs.json` against LinkedIn MCP or another broad board source
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

Saved import JSON supports run metadata plus a `results` array. Result objects may include `company`, `title`, `url`, `source_job_id`, `location`, `remote_status`, `compensation_signal`, `status` / `decision`, `notes`, and raw source references.

Accepted jobs should still be written through existing `job add` semantics after review so duplicate checks and action generation remain centralized.

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

## LinkedIn MCP Adapter Decision

SID-103 chose a hybrid adapter boundary:

- Codex invokes LinkedIn MCP tools.
- `scripts/job_search.py` remains the deterministic SQLite control layer.
- The handoff between them is a local query-run import payload, not direct CLI access to MCP tools.
- LinkedIn remains a discovery source; accepted jobs still flow through query-run review and existing job storage semantics.

Why this boundary:

- LinkedIn MCP auth, session state, and tool availability belong to the Codex runtime.
- The CLI should stay runnable in tests and local shells without a live LinkedIn session.
- Query-run records are the audit trail; raw LinkedIn search output is not the source of truth.

Raw payload policy:

- Do not persist full raw MCP payloads by default.
- Persist stable source references, canonical URLs, LinkedIn job IDs when available, normalized result fields, result counts, and concise rejection or failure notes.
- Allow explicit debug capture only for local troubleshooting. Debug captures must be redacted for profile/account/session data, stored outside application artifacts under `APPLICATIONS/_ops/query_runs/`, and referenced from the query run rather than copied into docs.
- Treat raw debug captures as local-only operational evidence, not reusable application material.

Failure classes for `linkedin_mcp` query runs:

- `auth_required`: no usable LinkedIn authentication is available before a search starts; record the run as `failed`.
- `session_expired`: authentication existed but the session is no longer usable; record the run as `failed` unless some results were already imported, then `partial`.
- `mcp_unavailable`: the LinkedIn MCP tool is missing, disabled, or not reachable; record as `failed`.
- `network_error`: transport failure, timeout, or transient service failure; record as `failed` or `partial` depending on whether usable results were captured.
- `rate_limited`: LinkedIn or MCP throttling prevents a complete pass; record as `partial` when some results were captured, otherwise `failed`.
- `malformed_payload`: required result fields are missing or inconsistent; reject affected rows and mark the run `partial` when the rest of the run is usable.
- `search_noisy`: result quality is too broad for the pack/query intent; record as `completed` when reviewed, with high rejection counts and pack-tuning notes.
- `stale_or_thin_result`: result detail is stale, closed, missing, or too thin to trust; reject affected rows.
- `detail_validation_failed`: `get_job_details` or the canonical posting contradicts the search result; reject affected rows.
- `partial_results`: catch-all for interrupted runs with enough normalized rows to review; record as `partial` with the more specific cause in notes.

SID-104 implements this handoff as a local helper layered over the SID-101
query-run import support and SID-102 machine-readable query packs.

## LinkedIn MCP Handoff

Use `scripts/linkedin_mcp_query_handoff.py` after Codex has called LinkedIn MCP
`search_jobs` and `get_job_details`. The helper does not call LinkedIn and does
not manage auth; it only normalizes saved MCP outputs into the local
`query import` payload.

Example successful run:

```bash
python3 scripts/linkedin_mcp_query_handoff.py prepare \
  --pack FINTECH \
  --query-index 1 \
  --search-json APPLICATIONS/_ops/query_runs/linkedin-search.json \
  --details-json APPLICATIONS/_ops/query_runs/linkedin-details.json \
  --sort-mode relevance \
  --output APPLICATIONS/_ops/query-runs/fintech-linkedin.json \
  --import
```

Use one payload per pack query. Rows are marked `accepted` only when a matching
`get_job_details` payload has usable company/title detail; search-only rows are
rejected with `stale_or_thin_result`.

Example unauthenticated failure path:

```bash
python3 scripts/linkedin_mcp_query_handoff.py prepare \
  --pack AI \
  --query-index 1 \
  --failure auth_required \
  --output APPLICATIONS/_ops/query-runs/ai-linkedin-auth-required.json \
  --import
```

Raw MCP payloads are not persisted by default. Use `--debug-capture` only for
local troubleshooting; the helper writes a redacted `0600` file under
`APPLICATIONS/_ops/query_runs/` and references it from the query run.

## Query Packs

The default repeatable broad-search packs are:

- FINTECH / platform
- AI / workflow

ACCESS and other variants are exception packs. They are valid for specific access/trust roles or target-company exceptions, but they are not default broad-search lanes.

Machine-readable source of truth: `config/job_search_query_packs.json`. The prose guidance in `.agents/skills/job-search/references/query-packs.md` must stay aligned with that registry.

CLI guardrails:

```bash
python3 scripts/job_search.py query packs list --default-only
python3 scripts/job_search.py query packs show FINTECH
python3 scripts/job_search.py query run --source linkedin_mcp --pack FINTECH --limit 25
python3 scripts/job_search.py query run --source manual_browser --pack ACCESS --reason "specific access/trust target role"
```

`query run` is a preflight planner: it prints the source, pack, and queries
while enforcing pack guardrails. Durable records are created by `query import`
after a reviewed source pass or adapter handoff.

## Current Next Work

Tracked in Linear project `Job Search Command Center`:

- Improve daily operator summaries for `status`, `action next`, and queue-specific views.
- Strengthen metrics around stale actions, outcome hygiene, target-company coverage, and query-run quality.
- Add more manual smoke tests for source polling, query-run import, and LinkedIn handoff paths.
- Turn repeated pass/rejection patterns into lane, query-pack, bullet, or artifact recommendations.

## Validation

Before handoff, run the deterministic repo gate:

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

Use the manual smoke tests in [manual-smoke-tests/](manual-smoke-tests/) when
checking command-center workflows by hand.

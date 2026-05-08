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
- Default search lanes: FINTECH / platform PM, AI workflow PM, and growth / business systems PM.
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
- `drafts`
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
python3 scripts/job_search.py automation poll-targets --company "Company"
python3 scripts/job_search.py query import --file APPLICATIONS/_ops/query-runs/fintech.json
python3 scripts/job_search.py query import --source manual_browser --pack FINTECH --query "senior product manager payroll" --result-count 12 --raw-source-reference manual-2026-04-29
python3 scripts/job_search.py query list
python3 scripts/job_search.py query show <query_run_id>
python3 scripts/job_search.py query packs list --default-only
python3 scripts/job_search.py query packs show FINTECH
python3 scripts/job_search.py query run --source linkedin_mcp --pack FINTECH --limit 25
python3 scripts/job_search.py automation prepare-query-run --source linkedin_mcp --pack FINTECH --file APPLICATIONS/_ops/query-runs/fintech-linkedin.json
python3 scripts/linkedin_mcp_query_handoff.py prepare --pack FINTECH --query-index 1 --search-json APPLICATIONS/_ops/query_runs/linkedin-search.json --details-json APPLICATIONS/_ops/query_runs/linkedin-details.json --output APPLICATIONS/_ops/query-runs/fintech-linkedin.json --import
python3 scripts/job_search.py job add --company "Company" --title "Senior Product Manager" --source manual
python3 scripts/job_search.py job list --company "Company"
python3 scripts/job_search.py action next --queue apply --limit 5
python3 scripts/job_search.py action list --queue apply --limit 25
python3 scripts/job_search.py action remind --include-ready
python3 scripts/job_search.py action done <action_id>
python3 scripts/job_search.py draft add --company "Company" --type follow_up --title "Follow-up draft" --action-id <action_id> --body "..."
python3 scripts/job_search.py draft add --company "Company" --type application_answer --title "Application answers" --job-id <job_id> --action-id <action_id> --path APPLICATIONS/READY_TO_APPLY/Company_Role/QA.md --body-file /tmp/answers.md
python3 scripts/job_search.py draft list --status draft
python3 scripts/job_search.py draft status <draft_id> needs_revision --notes "Tighten proof."
python3 scripts/job_search.py draft status <draft_id> rejected --notes "Do not use."
python3 scripts/job_search.py event add --company "Company" --type note --notes "..."
python3 scripts/job_search.py event list --company "Company"
python3 scripts/job_search.py metrics
python3 scripts/job_search.py report hygiene
python3 scripts/job_search.py report cooldowns
python3 scripts/job_search.py report proof-gaps
python3 scripts/job_search.py report strategy-feedback
python3 scripts/job_search.py report query-pack-tuning
python3 scripts/job_search.py import-pipeline
```

Run `python3 scripts/job_search.py import-pipeline` only when a legacy `APPLICATIONS/_ops/job_pipeline.jsonl` file exists. The old role-first `scripts/job_pipeline.py` workflow has been removed.

## Daily Workflow

1. Check the command center before searching:

```bash
python3 scripts/job_search.py status
python3 scripts/job_search.py action next
```

For a five-minute pre-session and post-session smoke path, use
[Daily Job Search Smoke Checklist](manual-smoke-tests/daily-job-search.md).

2. For a known company, inspect history before adding work:

```bash
python3 scripts/job_search.py company show "Company"
python3 scripts/job_search.py job list --company "Company"
python3 scripts/job_search.py event list --company "Company"
```

3. Process queued work by queue:

- `screen`: evaluate fresh roles.
- `apply`: prepare ready roles for Antonio's manual submission.
- `follow_up`: timed relationship or application follow-up preparation.
- `research`: fill company, role, or domain gaps.
- `artifact`: build targeted proof; sending it requires explicit human approval.
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

Draft follow-ups and application answers are saved through `draft` commands only.
They are review-only records and, when `--path` is provided, review-only package
files. Every generated draft must include source links such as company, job,
action, contact, or artifact IDs. Draft files and list output are marked
unsent/unsubmitted, and approval is only ledger metadata: it does not send
email, send LinkedIn messages, click application forms, submit applications, or
mark a job `applied`.

Draft write contract:

- Follow-up drafts: `draft add --type follow_up` creates a `drafts` row linked
  to source context and a `draft_created` event. Use `--contact-id`,
  `--action-id`, `--job-id`, or `--artifact-id` when those records exist.
- Application answer drafts: `draft add --type application_answer` creates the
  same review metadata and may write a package file under
  `APPLICATIONS/READY_TO_APPLY/<Company>_<Role>/QA.md` with a review-only
  unsubmitted marker.
- Durable proof/material drafts may also link to `artifacts`; artifact sending
  still uses the existing artifact/event workflow only after explicit human
  approval.
- Revision or rejection uses `draft status <id> needs_revision|rejected` and
  writes `draft_revised` or `draft_rejected` events without losing the original
  source links.
- Automation evidence should record created drafts with
  `automation record --draft-id <id>` alongside any action, artifact, or query
  run IDs, so recovery can explain exactly which review artifacts were created.

Use `action remind` for a read-only stale-action reminder pass over existing action
state:

```bash
python3 scripts/job_search.py action remind
python3 scripts/job_search.py action remind --include-ready --record-run
```

Reminder output surfaces stale, due, and blocked open actions by default; add
`--include-ready` to include ready open work, and `--as-of` when a deterministic
review timestamp is needed. Each row includes action ID, queue, kind, status, due
state, linked company/job/contact/artifact/gap context when present, and a
recommended `action next --queue <queue>` command. The command never completes,
skips, reschedules, reprioritizes, rewrites actions, or migrates an old schema; run
`init` first if the database is behind the current schema. `--record-run` records
surfaced reminders in `automation_runs` with `result_count` equal to the number of
surfaced actions. All-clear runs are explicit in output and are not recorded unless
`--record-all-clear` is also supplied. Automation wrappers can store failed or
partial reminder runs with `--record-status failed|partial`, `--failure-count`, and
`--failure-summary`; those runs appear in `automation review` with unresolved
recovery status.

4. Record the final state in SQLite through `scripts/job_search.py`.

5. Check hygiene before ending a session:

```bash
python3 scripts/job_search.py report hygiene
python3 scripts/job_search.py report cooldowns
python3 scripts/job_search.py report proof-gaps
python3 scripts/job_search.py report strategy-feedback
python3 scripts/job_search.py report query-pack-tuning
```

The hygiene report is read-only. It surfaces stale `follow_up`, `apply`, and
`classify` actions, old unscheduled apply/classify/follow-up actions, jobs whose
application or rejection events still need final outcome/disposition cleanup,
and recently active companies that no longer have an open next action. Each row
includes stable action, job, company, or event IDs needed to resolve the item
through the normal command paths.

The cooldown recommendations report is also read-only. It surfaces advisory
company and role-pattern cooldowns from stored `jobs.application_outcome`,
`jobs.rejection_reason`, and linked `events` / `actions` evidence. It distinguishes
temporary no-screen, interview-loop, and timing/capacity signals from durable
pass or low-priority signals, prints the evidence rows behind each
recommendation, and suggests the next review date.
Operators should treat the report as a decision aid: inspect the evidence, then
make any company status, action, or due-date changes explicitly through normal
commands when the recommendation is still correct.

The proof-gap report is also read-only. It groups repeated missing-proof signals
from structured `gaps`, `jobs.rejection_reason`, artifact opportunities, linked
actions, and linked events, then ranks recurring patterns above one-off gaps.
Each recommendation shows strength, score, suggested improvement type
(`profile`, `bullet`, `artifact`, `resume lane`, or `application playbook`),
job/company/lane/status counts, SQLite-vs-Linear routing guidance, and
supporting evidence IDs.

Keep role- and company-specific relevance in SQLite when the gap is still a
screening reason, rejection reason, open command-center action, or small
profile/materials update. Create a Linear follow-up only when the report shows a
recurring pattern that requires larger proof-building work outside normal queue
execution, such as a new artifact, reusable case study, resume-lane rewrite, or
application-playbook addition. The report never creates portfolio projects or
Linear issues automatically.

For weekly strategy feedback:

```bash
python3 scripts/job_search.py report strategy-feedback
```

The strategy-feedback report is also read-only. It composes existing
command-center evidence and Milestone 6 recommendation reports into an
operator-controlled weekly review. It always reviews outcomes, funnel metrics,
cooldown recommendations, proof-gap recommendations, target-company coverage,
and reviewed query quality. Output is split into `Evidence` and
`Recommendations`; recommendations are grouped into `Keep`, `Change`, and
`Defer`, and each recommendation names the durable artifact target to consider:
product strategy, career strategy, application playbook, user bullets, resume
lane, query-pack config, or Linear follow-up.

Use the report as a decision aid, not as an updater. Make any doc, config,
Linear, action, company, or job changes explicitly through the normal command
paths after reviewing the evidence. Keep this workflow inside
`$career-command-center`; route live discovery, posting validation, and JD
normalization to `$job-search`, and route ready-JD resume/materials work to
`$job-apply`.

For query-pack tuning:

```bash
python3 scripts/job_search.py report query-pack-tuning
```

The query-pack tuning report is read-only. It only uses reviewed
`query_run_results` (`accepted`, `rejected`, or `duplicate`) and explicitly
ignores pending/raw hits. It surfaces noisy queries, stale/thin source patterns,
duplicate overlap, strong accepted patterns, and candidate pack edits. Exception
pack recommendations preserve the explicit-reason guardrail; if a reviewed
exception run has no `reason=...` rationale in its query-run notes, the report
recommends recording a reason before repeating or promoting that pack. The report
does not edit `config/job_search_query_packs.json`.

## Outcome Taxonomy Recording

Outcome taxonomy is operating guidance over existing SQLite outcome/rejection
fields. Do not add a new durable product requirement or schema just to classify
an outcome or rejection reason. Use the controlled values below in
`jobs.application_outcome` and `jobs.rejection_reason`; use notes for the
specific evidence behind the value.

Role screening buckets are a separate decision model. Store bucket decisions in
`jobs.screen_bucket`; use notes only for supporting evidence.

Exact fields:

- `jobs.status`: lifecycle state, set with `job status` or `job update`.
- `jobs.screen_bucket`: controlled screening bucket, set with `job add` or
  `job update --screen-bucket`.
- `jobs.application_outcome`: comparable application disposition.
- `jobs.rejection_reason`: comparable pass or rejection reason.
- `events.notes`: human-readable evidence, timestamps, or message details.
- `actions.notes`: queue handoff and completion evidence.
- `query_run_results.result_status` and `query_run_results.notes`: broad-source
  result review state and source-quality notes.

Use taxonomy values when the fact should group cleanly in weekly review,
strategy-feedback reports, or outcome hygiene. Use freeform notes for the
supporting details: quoted recruiter feedback, comp number, location constraint,
title filter, source URL, or the exact judgment call.

Application outcome values:

- `pending_response`: submitted, no response yet, and no immediate follow-up
  decision.
- `active_interview_loop`: interview process is active.
- `rejected_before_screen`: rejected, auto-rejected, or went silent before a
  human screen.
- `rejected_after_screen`: rejected after recruiter, hiring-manager, or first
  screen.
- `rejected_after_interview`: rejected after a deeper interview loop or take-home
  stage.
- `closed_before_apply`: posting closed or vanished before Antonio applied.
- `passed_by_candidate`: Antonio deliberately passed or withdrew.
- `archived_no_action`: old record archived without a useful market signal.

Rejection and pass reason values:

- `fit_mismatch`: role center of gravity does not map truthfully to current
  proof.
- `level_scope_mismatch`: title, seniority, staff/group/director scope, or
  people-management expectation is wrong.
- `recruiter_screen_risk`: formal screen likely blocks the story even if the
  company is interesting.
- `missing_proof`: good target pattern, but current resume/artifacts lack a
  reusable proof point.
- `compensation_mismatch`: disclosed or confirmed comp is below the current bar.
- `location_or_work_model_mismatch`: geo, remote, hybrid, relocation, or work
  authorization constraint blocks the role.
- `timing_or_capacity`: good enough in abstract, but not worth the current queue
  slot or timing window.
- `stale_or_closed_posting`: canonical posting is stale, closed, unavailable, or
  too thin to trust as an active role.
- `duplicate_or_already_tracked`: duplicate posting, repost, or role already
  represented by another command-center record.
- `low_interest`: truthful enough, but not strategically interesting.

Screen bucket values:

- `ready_to_apply`: strong fit, no major truth gap, ready for final human submit.
- `low_effort_apply`: good enough for base-resume volume without customization.
- `stretch_warm_path`: strategic, but cold odds are weak; needs a warm path.
- `portfolio_gap`: attractive pattern blocked by missing reusable proof.
- `watch`: interesting, but not ready for action now.
- `pass`: skip for fit, interest, comp, timing, or screen-risk reasons.

Common commands:

```bash
python3 scripts/job_search.py job update <job_id> --status rejected --application-outcome rejected_before_screen --rejection-reason recruiter_screen_risk
python3 scripts/job_search.py event add --company "Company" --job-id <job_id> --type rejection_received --notes "Auto-reject after submit; likely PM-years/title screen."
python3 scripts/job_search.py action done <action_id> --notes "classified outcome=rejected_before_screen reason=recruiter_screen_risk"
```

For an apply still waiting on a response:

```bash
python3 scripts/job_search.py job update <job_id> --status applied --application-outcome pending_response
python3 scripts/job_search.py action done <action_id> --notes "application submitted; outcome=pending_response"
```

Use those commands only after Antonio confirms the application was submitted.
Automation may prepare the final package and submit checklist, but it must not
mark a role `applied` on inference alone.

For a screening pass before application:

```bash
python3 scripts/job_search.py job update <job_id> --status ignored_by_filter --screen-bucket portfolio_gap --rejection-reason missing_proof
python3 scripts/job_search.py action done <action_id> --notes "reason=missing_proof; needs controls/reporting case study before re-opening"
```

Classify queue ownership:

- `$career-command-center` owns `classify` actions, outcome hygiene, and weekly
  cleanup of old `applied`, `interviewing`, `rejected`, `closed`, and
  `archived` jobs.
- `$job-search` records screening/pass reasons only when discovery or role
  validation creates or updates a job. It should hand the final state back to
  the command center, not own weekly outcome cleanup.
- `$job-apply` owns ready-JD materials and final apply package guidance. It
  should report application submission, pass, withdrawal, or rejection facts
  back through the same `job update`, `event add`, and `action done` paths.

Broad query source-quality boundary:

- Keep `query_run_results.result_status` as review state only: `pending`,
  `accepted`, `rejected`, or `duplicate`.
- Keep source-quality reason strings in `query_run_results.notes`; use
  `report query-pack-tuning` as the current review surface for repeated
  broad-source quality patterns.
- Use query-result review notes for `search_noisy`, `malformed_payload`,
  `stale_or_thin_result`, `detail_validation_failed`, and duplicate/noisy
  broad-source rows.
- Do not copy broad-source noise into `jobs.rejection_reason` unless the result
  has already become a command-center job and the same issue is now a real role
  disposition, such as `stale_or_closed_posting` or
  `duplicate_or_already_tracked`.

## Target-Company Polling

Configured target-company polling is source-first.

- Default discovery workflow: research target companies externally, import the
  researched-company JSON, review configured ATS sources, then run `poll`.
- Use `company import --file <path>` for Codex/ChatGPT research output that
  includes company thesis, target roles, career URL, and ATS source details.
- Add explicit ATS sources with `source add`.
- Poll configured active sources with `poll`.
- Use `automation poll-targets` for schedulable preparation runs that poll only
  active Greenhouse, Lever, and Ashby sources, persist the normal jobs/actions
  output, and record `automation_runs` evidence with recovery state.
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

The broad-search strategy is source-gated query packs.

Broad job-board APIs are secondary/backlog. Do not make SerpApi, JSearch,
DataForSEO, Adzuna, or another broad API the default discovery backbone unless
the product strategy explicitly changes that posture.

Use two repeatable discovery motions:

- Source-first for known target companies:
  - run configured official ATS sources through `source` and `poll`
  - use official career pages only as manual/browser fallback
- Query-pack-first within broad source adapters:
  - run explicit FINTECH, AI, and GROWTH_BUSINESS_SYSTEMS packs from `config/job_search_query_packs.json` against LinkedIn MCP or another broad board source
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
- query pack: `FINTECH`, `AI`, `GROWTH_BUSINESS_SYSTEMS`, or an explicitly justified exception pack
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

## Automation Approval Boundary

Safe assistive automation is preparation, not external execution. It may read
approved sources, prepare records, suggest classifications, draft materials, and
record run history. It must stop before application submission, outreach,
browser form submission, unapproved deterministic rule changes, or raw
third-party payload persistence. Automation implementation tickets should
reference this section instead of restating the approval policy.

Allowed automation:

- configured-source polling for reviewed Greenhouse, Lever, and Ashby sources
- command-center-visible reminders for stale, due, blocked, or ready actions
- approved-source query-run preparation and local import payload preparation
- classification suggestions, LLM triage recommendations, and fit/risk
  explanations
- draft follow-ups, application answers, cover letters, and saved package files
  marked for review
- duplicate detection, queue creation, and suggested next actions
- `automation_runs` recording, review, and recovery-state updates

Explicit human approval is required before:

- submitting an application or marking a role `applied` without confirmation
- sending outreach, follow-ups, connection requests, emails, or LinkedIn
  messages
- submitting browser forms, clicking final external confirmation buttons, or
  writing to an external account on Antonio's behalf
- changing deterministic rules such as target-role filters, query-pack defaults,
  cooldown policy, classification taxonomy, strategy docs, or resume/profile
  positioning based only on an automation suggestion
- persisting full raw third-party payloads beyond local/redacted debug capture
- enabling new external notification channels, account integrations, or
  unattended schedulers

Agents should stop and ask for explicit direction when the next step would cross
one of those approval boundaries, when a draft is ready to send or submit, when
an automation recommendation would mutate durable strategy or deterministic
rules, when source details are contradictory or malformed, or when a failed or
partial run needs a non-obvious recovery choice.

### Automation Run History

Scheduled and assistive automation runs are recorded separately from raw source
payloads:

```bash
python3 scripts/job_search.py automation record --source linkedin_mcp --scope FINTECH --status partial --started-at 2026-04-27T10:00:00+00:00 --ended-at 2026-04-27T10:04:00+00:00 --result-count 3 --failure-count 1 --failure-summary rate_limited --query-run-id 12 --notes "normalized rows imported; raw payload stayed local"
python3 scripts/job_search.py automation poll-targets --company "Company"
python3 scripts/job_search.py automation poll-targets --source-id 12 --source-id 13
python3 scripts/job_search.py automation prepare-query-run --source linkedin_mcp --pack FINTECH --file APPLICATIONS/_ops/query-runs/fintech-linkedin.json
python3 scripts/job_search.py automation review
python3 scripts/job_search.py automation recover <run_id> retry --notes "retry with smaller limit"
```

Each run captures status, source/scope, start/end timing, counts, failure
summary, created action/artifact/query-run IDs, concise notes, and recovery
state. `automation review` is the operator surface for failed and partial runs;
it shows the stable command-center links and the available recovery choices:
retry, skip, or `resolve`.

`automation poll-targets` wraps the same source polling as `poll`: successful
sources create the normal job ledger rows, weak matches stay
`ignored_by_filter`, promising roles create reviewable `screen` actions, and
duplicates are skipped by the existing duplicate rules. The automation run links
created screen actions in `action_ids` and appends the run ID to those action
notes for review. If one source fails while another succeeds, the run is
`partial`; if all selected sources fail, it is `failed`; both states appear in
`automation review` until recovered.

`automation prepare-query-run` is the approved preparation-only path for broad
source packages that already have a normalized query-import JSON payload. It
enforces the same source list and query-pack guardrails as `query run`, imports
the query run before any review or acceptance work, and records one linked
`automation_runs` row with `query_run_ids` evidence. Exception packs such as
`ACCESS` still require `--reason`. The command creates no jobs, actions, or
artifacts; operators must review `query_run_results` and accept jobs through a
separate command-center step.

Evidence expectations:

- successful runs record source/scope, start/end timing, reviewed result counts,
  created job/action/artifact/query-run IDs, duplicate or ignored counts when
  relevant, and a concise note explaining what is ready for human review
- partial runs record the usable subset, missing or failed subset, linked
  records created before interruption, failure summary, recovery status, and the
  exact safe next choice such as retry with smaller scope, skip, or manual
  resolve
- failed runs record source/scope, start/end timing when known, zero or partial
  counts, failure class, recovery status, whether any records were created, and
  enough operator notes to avoid repeating the same failure blindly

Do not paste unredacted third-party payloads into automation run notes. Keep
debug captures local under existing policy and reference the local/redacted
debug path only when it helps explain the run.

Noisy broad results:

- Start with narrow problem-domain query packs.
- Cap each source/pack pass to a reviewable result set before broadening.
- Reject malformed metadata, people-management-heavy titles, stale/thin posts, and roles where the JD shifts away from the query intent.
- Only jobs that survive detail validation should enter `jobs`.

## LinkedIn MCP Adapter Decision

LinkedIn MCP uses a hybrid adapter boundary:

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

This handoff is implemented as a local helper layered over query-run import
support and machine-readable query packs.

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
- GROWTH_BUSINESS_SYSTEMS / growth and business systems

ACCESS and other variants are exception packs. They are valid for specific access/trust roles or target-company exceptions, but they are not default broad-search lanes.

Machine-readable source of truth: `config/job_search_query_packs.json`. The prose guidance in `.agents/skills/job-search/references/query-packs.md` must stay aligned with that registry.

CLI guardrails:

```bash
python3 scripts/job_search.py query packs list --default-only
python3 scripts/job_search.py query packs show FINTECH
python3 scripts/job_search.py query run --source linkedin_mcp --pack FINTECH --limit 25
python3 scripts/job_search.py query run --source manual_browser --pack ACCESS --reason "specific access/trust target role"
python3 scripts/job_search.py automation prepare-query-run --source linkedin_mcp --pack FINTECH --file APPLICATIONS/_ops/query-runs/fintech-linkedin.json
python3 scripts/job_search.py report query-pack-tuning
```

`query run` is a preflight planner: it prints the source, pack, and queries
while enforcing pack guardrails. Durable records are created by `query import`
after a reviewed source pass or adapter handoff.

## Current Next Work

Tracked follow-ups from the Milestone 6 structured-field review should build on
the shipped `jobs.screen_bucket` field instead of reintroducing bucket parsing
from notes or lifecycle statuses.

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

## Metrics Review

`python3 scripts/job_search.py metrics` is the weekly review surface. The
existing application and outreach rates remain intact, and Milestone 5 adds
execution-health lines:

- `bucket_resolution`: counts roles with `jobs.screen_bucket` set versus
  unresolved discovered/screening roles and prints bucket counts. Low resolution
  rate means screen the backlog or record pass/ready decisions.
- `reviewed_query_results`: shows broad-source result quality for the window:
  total, reviewed, pending, accepted, rejected, duplicate, and noisy. High
  pending means finish review; high noisy/rejected means tune the query pack or
  source.
- `accepted_high_signal_roles`: compares accepted broad-source results with
  roles currently at `ready_to_apply`, `applied`, or `interviewing`. A weak
  ratio means accepted roles are not converting into real application work.
- `stale_actions`: counts open actions whose due date is before the review
  cutoff, plus queue distribution. Use it to clear blocked execution queues.
- `target_company_coverage`: counts active/watch target companies with active
  ATS sources, missing active sources, career-page-only fallbacks, unsupported
  ATS types, and stale checks. Missing or unsupported sources should drive
  company-source research before broader searching.

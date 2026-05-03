# Job Search Product Strategy

This is the product source of truth for the job-search system. The detailed operating model lives in [How It Works](HOW_IT_WORKS.md).

## Product Thesis

The product is a command center for high-signal job search execution.

It helps Antonio discover, screen, track, and apply to the right roles without letting noisy job boards, scattered notes, or resume polishing consume the search. The system should make every search session more durable: companies, roles, contacts, decisions, artifacts, gaps, actions, and outcomes all become reusable state.

The first customer is Antonio. The product should stay optimized for that workflow until the operating model is proven.

## Problem

Modern job search creates too much undifferentiated work:

- broad job-board searches are noisy and easy to repeat without learning
- company research, role screening, application materials, contacts, and outcomes live in different places
- LinkedIn is useful for discovery but brittle as a source of truth
- resume customization can block application volume
- prior decisions are easy to forget, causing duplicate work and weak follow-through
- strategic target companies need campaign management, not one-off role reactions

The product solves this by turning job search into a stateful operating system with deterministic storage, repeatable discovery lanes, and clear queues.

## Product Promise

For every serious role or target company, the system should answer:

- Have we seen this company or role before?
- What is the current next action?
- Does this role fit the active lanes?
- Should this become apply-now, low-effort apply, warm-path campaign, portfolio gap, watch, or pass?
- Which resume lane and materials should be used?
- What happened after submission or follow-up?
- What did this search session teach the system?

## Current Product Shape

- Primary surface: Codex conversation.
- Control layer: `scripts/job_search.py`.
- Source of truth: SQLite at `APPLICATIONS/_ops/job_search.sqlite`.
- Strategy source: this document.
- Operating-model source: `docs/HOW_IT_WORKS.md`.
- Primary workflow: company-first, queue-based execution.
- Default discovery lanes: FINTECH / platform PM and AI workflow PM.
- Exception lanes: ACCESS / trust workflow, payments / insurance / crypto trust, media platform, industrial / autonomy bridge, and other variants only when a specific role or target-company reason warrants them.
- Application workflow: `$job-search` screens and normalizes roles; `$job-apply` routes ready JDs to the best resume lane and application materials.
- Automation posture: manual-first with assistive automation.
- LinkedIn posture: useful discovery source, never the system of record.

## Users And Operators

Primary operator:

- Antonio, using Codex as the daily command surface.

Secondary operators:

- repo agents using `.agents/skills/job-search/` for discovery and screening
- repo agents using `.agents/skills/job-apply/` for application routing and answer drafting
- future automation jobs that can safely poll, classify, or prepare work without submitting applications

Non-goal for now:

- multi-user SaaS workflow
- autonomous application submission
- automated outreach to people
- making LinkedIn, browser state, or any external job board the canonical store

## Core Product Surfaces

### Command Center

The command center stores durable job-search state in SQLite and exposes deterministic CLI commands for:

- companies
- company sources
- query runs
- query run results
- jobs
- contacts
- artifacts
- gaps
- actions
- events
- metrics

### Source-First Target Company Workflow

For known target companies:

1. Research the company externally or manually.
2. Import reviewed company JSON.
3. Configure official ATS sources when available.
4. Poll Greenhouse, Lever, or Ashby before relying on browser scraping.
5. Store discovered roles, duplicates, weak matches, and screen actions.

### Query-Pack Broad Discovery

For broader discovery:

1. Use default FINTECH and AI query packs.
2. Use exception packs only with an explicit reason.
3. Record query runs before accepting roles into the command center.
4. Validate promising results through detail pages or canonical postings.
5. Preserve rejection, duplicate, noise, and failure notes.

### Live Application Routing

For ready JDs:

1. Run a history check against the command center.
2. Decide apply/pass/bucket.
3. Pick the best existing resume lane.
4. Draft concise answers or cover letters only when useful.
5. Save high-signal packages under `APPLICATIONS/READY_TO_APPLY/`.
6. Record final state and next action.

## Design Principles

- Company-first, not role-spreadsheet-first.
- SQLite is the source of truth; docs describe behavior, not state.
- Manual-first at external side-effect boundaries.
- Assistive automation should prepare, classify, dedupe, and queue work.
- Application volume should not be blocked by resume perfection.
- Broad search should be source-gated and query-pack-constrained.
- Every search session should produce reusable state or an explicit decision.
- Prefer official ATS sources over brittle page scraping.
- Keep raw third-party payloads out of durable application artifacts unless explicitly captured for local debugging.
- Build for one excellent operator before generalizing.

## Decision Model

Every role should resolve to one bucket:

- `ready_to_apply`: strong fit, no major truth gap, ready for final human submission.
- `low_effort_apply`: acceptable fit, base resume only, useful for volume.
- `stretch_warm_path`: strategic company or role, but cold odds are weak; requires a concrete warm-path action.
- `portfolio_gap`: attractive target pattern, but missing reusable proof; create or reference a proof-gap action.
- `watch`: company or space matters, but no clean immediate role or action.
- `pass`: weak interest, weak comp, fake story risk, high screen risk, or no concrete next action.

The product should keep these questions separate:

1. Do we like it?
2. Can Antonio credibly win it now?
3. If not now, is it worth building toward?

## Milestones

### Milestone 0: Application Package Generator

Status: shipped baseline.

- `/apply` transforms a pasted JD into assessment, resume, cover letter, outreach, and DOCX materials.
- Base resume lanes exist for FINTECH, AI, and DESIGN.
- `$job-apply` routes a ready JD to a resume lane and produces concise application answers.

### Milestone 1: Command Center V1

Status: shipped baseline.

- SQLite command center exists at `APPLICATIONS/_ops/job_search.sqlite`.
- `scripts/job_search.py` supports companies, jobs, actions, contacts, artifacts, gaps, events, metrics, and legacy import.
- Daily workflow starts with `status` and `action next`.
- Old role-first JSONL pipeline is deprecated and migrated through `import-pipeline`.

### Milestone 2: Target Company Polling

Status: shipped baseline.

- Company import supports researched-company JSON.
- Company sources support Greenhouse, Lever, and Ashby.
- Polling stores all discovered jobs.
- Target-role filters create screen actions for plausible matches and mark weak matches as `ignored_by_filter`.
- Duplicate and repost rules protect the job ledger.

### Milestone 3: Query-Pack Discovery

Status: shipped baseline.

- Query packs are machine-readable in `config/job_search_query_packs.json`.
- FINTECH and AI are default repeatable packs.
- ACCESS and other variants require an explicit exception reason.
- Query runs can be imported, listed, and inspected.
- Query run results preserve accepted, rejected, duplicate, noisy, and failure outcomes.

### Milestone 4: LinkedIn MCP Handoff

Status: shipped baseline.

- Codex owns live LinkedIn MCP interaction.
- `scripts/linkedin_mcp_query_handoff.py` normalizes saved MCP search/detail outputs into query-run import payloads.
- Failure classes are recorded as query runs.
- Raw MCP payloads are not durable product state by default.

### Milestone 5: Operator-Grade Daily Loop

Status: next product focus.

Goal: make daily execution fast, visible, and hard to forget.

Deliverables:

- clearer `status` and `action next` summaries
- queue-specific views for `screen`, `apply`, `follow_up`, `research`, `artifact`, and `classify`
- outcome and follow-up hygiene reports
- manual smoke-test checklist for daily search sessions
- stronger metrics around funnel health, target-company coverage, and stale actions

### Milestone 6: Strategy Feedback Loop

Status: planned.

Goal: make the system learn from outcomes.

Deliverables:

- rejection/outcome taxonomy that can tune lanes and query packs
- company and role cooldown rules
- gap aggregation across passed or failed roles
- recommended profile, bullet, artifact, or resume-lane improvements
- durable strategy updates in `YOUR_PROFILE/CAREER_STRATEGY.md` and `YOUR_PROFILE/APPLICATION_PLAYBOOK.md`

### Milestone 7: Safe Assistive Automation

Status: planned.

Goal: automate preparation without crossing human-submission boundaries.

Deliverables:

- scheduled target-company polling
- stale-action reminders
- automated query-run preparation for approved sources
- saved drafts for follow-ups or application answers
- explicit human approval before any outreach or submission

## Success Metrics

Operational metrics:

- fewer duplicate searches and duplicate role reviews
- more roles resolved into explicit buckets
- fewer stale queued actions
- faster apply-ready handoff after role discovery
- higher ratio of reviewed query results to accepted high-signal roles
- lower noisy/rejected broad-source share after query-pack tuning

Strategic metrics:

- stronger target-company coverage
- fewer active target companies with missing or unsupported source coverage
- clearer reasons for passes and rejections
- better resume-lane fit over time
- more reusable proof gaps identified and closed
- more applications submitted without sacrificing truthfulness or fit

## Source-Of-Truth Map

- Product strategy: `docs/PRODUCT_STRATEGY.md`
- Command-center operating model: `docs/HOW_IT_WORKS.md`
- Query pack registry: `config/job_search_query_packs.json`
- Query pack prose guidance: `.agents/skills/job-search/references/query-packs.md`
- Discovery skill: `.agents/skills/job-search/SKILL.md`
- Application skill: `.agents/skills/job-apply/SKILL.md`
- Career strategy: `YOUR_PROFILE/CAREER_STRATEGY.md`
- Application answer guidance: `YOUR_PROFILE/APPLICATION_PLAYBOOK.md`
- Base resumes: `YOUR_PROFILE/Fintech/FINTECH.md`, `YOUR_PROFILE/AI/AI.md`, `YOUR_PROFILE/DESIGN.md`

## Open Product Questions

- Should the next operator surface stay CLI-first, or should it produce a generated daily markdown brief?
- Which metrics best predict quality: applications submitted, ready-to-apply roles, warm-path actions created, or interviews?
- When should exception lanes graduate into default repeatable packs?
- What minimum evidence should promote a portfolio gap into an actual artifact project?
- How much automation is useful before it starts hiding judgment from the operator?

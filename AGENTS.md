# AGENTS.md - Job Search Command Center

Guidance for agents working in this repository.

## Start Here

Primary docs:

- `docs/PRODUCT_STRATEGY.md` - product thesis, promise, milestones, success metrics, and open product questions
- `docs/HOW_IT_WORKS.md` - implemented command-center model, operator workflow, CLI behavior, SQLite state, polling, LinkedIn handoff, and validation
- `docs/README.md` - docs map and source-of-truth boundaries
- `config/job_search_query_packs.json` - machine-readable query-pack registry
- `.agents/skills/career-command-center/SKILL.md` - daily command-center operator workflow
- `.agents/skills/job-search/SKILL.md` - live discovery, LinkedIn intake, and role screening workflow
- `.agents/skills/job-apply/SKILL.md` - ready-JD application routing and answer drafting workflow

Treat `docs/PRODUCT_STRATEGY.md` as the product source of truth. Treat
`docs/HOW_IT_WORKS.md` as the operating source of truth.

## Product Rules

- Source of truth: SQLite at `APPLICATIONS/_ops/job_search.sqlite`.
- Primary workflow: company-first, queue-based execution.
- Default discovery lanes: `FINTECH` / platform and `AI` / workflow.
- Exception lanes require a specific role or target-company reason.
- LinkedIn is a discovery source, not the source of truth.
- Prefer Greenhouse, Lever, and Ashby APIs before official career-page browsing.
- Record query runs as audit trails before accepting broad-source jobs.
- Validate promising broad-source hits through detail pages or canonical postings.
- Keep raw LinkedIn/MCP payloads out of durable application artifacts unless explicitly captured for local debugging.
- Do not let resume polishing block application volume.
- Do not submit applications or message people without explicit human direction.

## Default Workflow

Start every job-search session with the command center:

```bash
python3 scripts/job_search.py status
python3 scripts/job_search.py action next
```

Use `$career-command-center` for daily queue operation, command-center hygiene,
metrics, outcomes, stale actions, and deciding what to do next from existing
state.

For current commands, polling, query packs, LinkedIn handoff, and validation,
use `docs/HOW_IT_WORKS.md`.

## Role Buckets

Resolve each screened role into one bucket:

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

## Resume And Application Rules

- Maintain lane-specific resumes in `YOUR_PROFILE/Fintech/FINTECH.md`, `YOUR_PROFILE/AI/AI.md`, and `YOUR_PROFILE/DESIGN.md`.
- Treat `YOUR_PROFILE/Fintech/FINTECH.md` as the current strongest source for senior+ fintech/platform framing.
- Use `ACTIVE` bullets from `YOUR_PROFILE/USER_BULLETS.md` first.
- Pull from `ON ICE / REVIEW LATER` only with deliberate review.
- Generated resumes use Summary, Professional Experience, Skills, and Education. No Certifications section.
- Cover letters are selective, plainspoken, proof-first, and usually 100-140 words.

Reusable application guidance belongs in:

- `YOUR_PROFILE/APPLICATION_PLAYBOOK.md` for recurring application questions
- `YOUR_PROFILE/USER_PROFILE.md` for durable positioning or preferences
- `YOUR_PROFILE/USER_BULLETS.md` for proof points
- `APPLICATIONS/<Company>_<Role>/` or `APPLICATIONS/READY_TO_APPLY/<Company>_<Role>/` for company-specific materials

## Verification

Before handoff, run the strongest feasible gate:

```bash
make test
```

For command-center changes, include targeted coverage around migrations,
duplicate detection, action generation, query-pack validation, query-run
import/list/show behavior, and metrics aggregation when touched.

When adding or changing tests, use `$high-signal-tests`. Before handoff on
non-trivial test changes, run `$test-deslop` on the diff.

Capture recurring failures as one of: test, script, guardrail, or runbook.

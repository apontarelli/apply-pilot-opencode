# AGENTS.md - Job Search Command Center

Guidance for agents working in this repository.

## Product Source Of Truth

Primary docs:

- `docs/PRODUCT_STRATEGY.md` - product thesis, problem, milestones, success metrics, source-of-truth map
- `docs/job-search-command-center.md` - implemented command-center model, operator workflow, broad query strategy, CLI behavior
- `config/job_search_query_packs.json` - machine-readable query-pack registry
- `.agents/skills/job-search/SKILL.md` - live discovery, LinkedIn intake, and role screening workflow
- `.agents/skills/job-apply/SKILL.md` - ready-JD application routing and answer drafting workflow

Treat `docs/PRODUCT_STRATEGY.md` as the long-term product strategy.
Treat `docs/job-search-command-center.md` as the operational source of truth.

## What This Product Does

This repo is a job-search operating system for active discovery, screening,
application tracking, and outcome history.

It supports:

- **Command-center mode**: company-first SQLite ledger for companies, sources, query runs, jobs, contacts, artifacts, gaps, actions, events, and metrics
- **Job-search mode**: `$job-search` for LinkedIn-backed discovery, URL intake, role validation, and normalized JD handoff
- **Application mode**: `$job-apply` for ready-JD lane routing, apply/pass calls, cover-letter guidance, and concise application answers
- **Tailored package mode**: `/apply` for JD-in, tailored package-out materials
- **Base resume mode**: reusable `FINTECH.md`, `AI.md`, and `DESIGN.md` resume lanes in `YOUR_PROFILE/`

The product is manual-first with assistive automation. It prepares, classifies,
dedupes, and queues work; it does not submit applications or message people
without explicit human direction.

## Default Workflow

Start every job-search session with the command center:

```bash
python3 scripts/job_search.py status
python3 scripts/job_search.py action next
```

For a known company, inspect history before adding work:

```bash
python3 scripts/job_search.py company show "Company"
python3 scripts/job_search.py job list --company "Company"
python3 scripts/job_search.py event list --company "Company"
```

For target-company work:

```bash
python3 scripts/job_search.py company import --file APPLICATIONS/_ops/researched-companies/fintech-targets.json
python3 scripts/job_search.py source list --company "Company"
python3 scripts/job_search.py poll --company "Company"
```

For broad discovery:

```bash
python3 scripts/job_search.py query packs list --default-only
python3 scripts/job_search.py query packs show FINTECH
python3 scripts/job_search.py query run --source linkedin_mcp --pack FINTECH --limit 25
python3 scripts/job_search.py query import --file APPLICATIONS/_ops/query-runs/fintech.json
python3 scripts/job_search.py query list
python3 scripts/job_search.py query show <query_run_id>
```

For LinkedIn MCP handoff after Codex has saved search/detail payloads:

```bash
python3 scripts/linkedin_mcp_query_handoff.py prepare \
  --pack FINTECH \
  --query-index 1 \
  --search-json APPLICATIONS/_ops/query_runs/linkedin-search.json \
  --details-json APPLICATIONS/_ops/query_runs/linkedin-details.json \
  --output APPLICATIONS/_ops/query-runs/fintech-linkedin.json \
  --import
```

Run `python3 scripts/job_search.py import-pipeline` only when a legacy
`APPLICATIONS/_ops/job_pipeline.jsonl` file exists.

## Product Rules

- Source of truth: SQLite at `APPLICATIONS/_ops/job_search.sqlite`.
- Primary workflow: company-first, queue-based execution.
- Default discovery lanes: `FINTECH` / platform and `AI` / workflow.
- Exception lanes: `ACCESS`, payments / insurance / crypto trust, media platform, industrial / autonomy, and other variants only with a specific role or target-company reason.
- LinkedIn is a discovery source, not the source of truth.
- Prefer Greenhouse, Lever, and Ashby APIs before official career-page browsing.
- Use official company pages as manual/browser fallback when no ATS source is configured.
- Broad job-board APIs are secondary/backlog; do not make SerpApi, JSearch, DataForSEO, Adzuna, or similar APIs the default backbone without a new decision.
- Record query runs as audit trails before accepting broad-source jobs.
- Validate promising broad-source hits through detail pages or canonical postings.
- Keep raw LinkedIn/MCP payloads out of durable application artifacts unless explicitly captured for local debugging.
- Do not let resume polishing block application volume.

## Role Buckets

Resolve each screened role into one bucket:

- `ready_to_apply`: strong fit, no major truth gap, ready for final human submission
- `low_effort_apply`: good enough, base resume only, useful for volume
- `stretch_warm_path`: strategic company, cold odds weak, concrete warm-path action required
- `portfolio_gap`: attractive target pattern, missing reusable proof
- `watch`: company or space matters, no clean immediate action
- `pass`: fake story, weak interest, weak comp, high screen risk, or no next action

Keep these questions separate:

1. Do we like it?
2. Can Antonio credibly win it now?
3. If not now, is it worth building toward?

## Resume And Application Rules

### Base Resume Rules

- Maintain lane-specific resumes in `YOUR_PROFILE/Fintech/FINTECH.md`, `YOUR_PROFILE/AI/AI.md`, and `YOUR_PROFILE/DESIGN.md`.
- Treat `YOUR_PROFILE/Fintech/FINTECH.md` as the current strongest source for senior+ fintech/platform framing.
- In fintech resumes, lead with payroll/accounting/reporting/platform problems; entertainment context trails unless it adds proof.
- Keep title truthful: `Senior Product Manager`.
- Imply staff-level scope through cross-org ownership, standards-setting, and business-critical outcomes.
- Use `ACTIVE` bullets from `YOUR_PROFILE/USER_BULLETS.md` first.
- Pull from `ON ICE / REVIEW LATER` only with deliberate review.

### Generated Resume Rules

- Sections: Summary, Professional Experience, Skills, Education.
- No Certifications section.
- Side Projects can be separate when they support the core story.
- Summary: outcome-first, keyword-aware, no invented metrics.
- Experience: 13 bullets is the target for generated resumes, but distinct proof beats padding.
- Bullets: 240-260 characters when generating tailored resumes.
- Skills: 3-5 hard-skill categories aligned to the JD.

### Bullet Framework

Each bullet should include:

1. Action
2. Context
3. Method
4. Result
5. Impact
6. Business outcome

No invented metrics. Use estimates only when defensible.

### Cover Letters

- Use selectively for strong-fit or required applications.
- Target 100-140 words; acceptable 90-150.
- Structure: team/problem hook, proof, contribution/close.
- No formal headers.
- Plainspoken tone; no fake enthusiasm or abstract filler.

## Key Files

- `scripts/job_search.py` - deterministic command-center CLI
- `scripts/linkedin_mcp_query_handoff.py` - local LinkedIn MCP result normalizer
- `APPLICATIONS/_ops/job_search.sqlite` - command-center database
- `APPLICATIONS/READY_TO_APPLY/` - saved high-signal application packages
- `YOUR_PROFILE/USER_PROFILE.md` - profile, role history, education, durable positioning
- `YOUR_PROFILE/USER_BULLETS.md` - proof library
- `YOUR_PROFILE/CAREER_STRATEGY.md` - lane strategy, comp bands, cadence
- `YOUR_PROFILE/APPLICATION_PLAYBOOK.md` - recurring application question guidance
- `PLAYBOOK/` - legacy package-generation templates and DOCX script

## Verification

Before handoff, run the strongest feasible gate:

```bash
make test
```

For command-center changes, include targeted coverage around:

- migrations
- duplicate detection
- action generation
- query-pack validation
- query-run import/list/show behavior
- metrics aggregation when touched

When adding or changing tests, use `$high-signal-tests`. Before handoff on
non-trivial test changes, run `$test-deslop` on the diff.

## Repo Maintenance

For live applications, answer the immediate form or decision first. Then ask
whether any part should become reusable.

Reusable items belong in:

- `YOUR_PROFILE/APPLICATION_PLAYBOOK.md` for recurring application questions
- `YOUR_PROFILE/USER_PROFILE.md` for durable positioning or preferences
- `YOUR_PROFILE/USER_BULLETS.md` for proof points
- `APPLICATIONS/<Company>_<Role>/` or `APPLICATIONS/READY_TO_APPLY/<Company>_<Role>/` for company-specific materials
- `docs/PRODUCT_STRATEGY.md` for product strategy changes
- `docs/job-search-command-center.md` for operating-model changes

Capture recurring failures as one of: test, script, guardrail, or runbook.

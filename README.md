# Job Search Command Center

![OpenCode for Job Applications](assets/cc-for-job-applications.png)

**Not a prompt. A job-search operating system.**

This repo helps Antonio discover, screen, track, and apply to high-signal roles without turning LinkedIn, scattered notes, or resume polishing into the source of truth.

It combines:

- a company-first SQLite command center
- repo-scoped `$job-search` and `$job-apply` skills
- reusable resume lanes for FINTECH, AI, and DESIGN
- a legacy `/apply` package generator for full tailored application materials

Forked and maintained by Antonio Pontarelli from the original by Shashikiran Devadiga.

## Source Of Truth

- [Product Strategy](docs/PRODUCT_STRATEGY.md): what the product does, the problem it solves, milestones, success metrics, source-of-truth map
- [Command Center](docs/job-search-command-center.md): implemented operating model, daily workflow, CLI commands, query strategy, LinkedIn handoff rules
- [Docs Router](docs/README.md): durable docs map

## What It Does

The command center tracks durable job-search state:

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

The system answers:

- Have we seen this company or role before?
- What is the next action?
- Does the role fit FINTECH, AI, or an exception lane?
- Should it be ready-to-apply, low-effort apply, warm path, portfolio gap, watch, or pass?
- Which resume should be used?
- What happened after submission or follow-up?

LinkedIn is useful for discovery. SQLite is the source of truth.

## Quick Start

### Prerequisites

- [OpenCode CLI](https://opencode.ai)
- Python 3.x
- `python-docx`

Install the Python dependency when needed:

```bash
pip install python-docx
```

### Initialize The Command Center

```bash
python3 scripts/job_search.py init
python3 scripts/job_search.py status
python3 scripts/job_search.py action next
```

The database lives at:

```text
APPLICATIONS/_ops/job_search.sqlite
```

### Use The Daily Workflow

For known companies:

```bash
python3 scripts/job_search.py company show "Company"
python3 scripts/job_search.py job list --company "Company"
python3 scripts/job_search.py event list --company "Company"
```

For target-company polling:

```bash
python3 scripts/job_search.py company import --file APPLICATIONS/_ops/researched-companies/fintech-targets.json
python3 scripts/job_search.py source add "Company" --type greenhouse --key <board-token>
python3 scripts/job_search.py poll --company "Company"
```

For broad query-pack discovery:

```bash
python3 scripts/job_search.py query packs list --default-only
python3 scripts/job_search.py query packs show FINTECH
python3 scripts/job_search.py query run --source linkedin_mcp --pack FINTECH --limit 25
python3 scripts/job_search.py query import --file APPLICATIONS/_ops/query-runs/fintech.json
python3 scripts/job_search.py query list
```

### Use The Skills

Use `$job-search` when you want to:

- search LinkedIn
- validate a role
- normalize a LinkedIn posting into JD text
- gather light company or people context
- hand off a clean JD packet to `$job-apply`

Use `$job-apply` when you already have a JD and want:

- resume-lane recommendation
- apply/pass call
- cover-letter recommendation
- concise application answers
- saved ready-to-apply materials

Use `/apply` when you want the older full package flow:

- `JD.md`
- `RESUME.md`
- `COVERLETTER.md`
- `OUTREACH.md`
- DOCX files

## Product Model

Default discovery lanes:

- `FINTECH`: payroll, accounting, reporting, controls, identity, reconciliation, high-trust platform workflows
- `AI`: workflow software, orchestration, operator tooling, evals, guardrails, structured-output systems

Exception lanes require a specific role or target-company reason:

- `ACCESS`
- payments / insurance / crypto trust
- media platform
- industrial / autonomy bridge

Every screened role should land in one bucket:

- `ready_to_apply`
- `low_effort_apply`
- `stretch_warm_path`
- `portfolio_gap`
- `watch`
- `pass`

## Architecture

```text
Codex conversation
  -> $job-search / $job-apply skills
  -> scripts/job_search.py
  -> APPLICATIONS/_ops/job_search.sqlite
  -> APPLICATIONS/READY_TO_APPLY/<Company>_<Role>/
```

LinkedIn MCP flow:

```text
Codex LinkedIn MCP tools
  -> saved search/detail JSON
  -> scripts/linkedin_mcp_query_handoff.py
  -> query-run import payload
  -> scripts/job_search.py query import
```

Package-generation flow:

```text
/apply
  -> JD assessment
  -> resume creation and verification
  -> cover letter creation and verification
  -> outreach creation and verification
  -> Markdown and DOCX outputs
```

## Key Commands

| Command | Purpose |
| --- | --- |
| `python3 scripts/job_search.py init` | Create or migrate the command-center database |
| `python3 scripts/job_search.py status` | Show current command-center state |
| `python3 scripts/job_search.py action next` | Show queued work |
| `python3 scripts/job_search.py company add "Company"` | Add a company |
| `python3 scripts/job_search.py company import --file <json>` | Import researched companies |
| `python3 scripts/job_search.py source add "Company" --type greenhouse --key <token>` | Add ATS source |
| `python3 scripts/job_search.py poll --company "Company"` | Poll configured ATS source |
| `python3 scripts/job_search.py query packs list --default-only` | Show default query packs |
| `python3 scripts/job_search.py query import --file <json>` | Import a broad discovery run |
| `python3 scripts/job_search.py query show <id>` | Inspect query-run results |
| `python3 scripts/job_search.py metrics` | Show funnel metrics |
| `python3 scripts/job_search.py import-pipeline` | Import legacy JSONL pipeline records |

## File Structure

```text
OPEN_SOURCE_JOB_APPLICATION_SYSTEM/
├── .agents/
│   └── skills/
│       ├── job-apply/
│       └── job-search/
├── APPLICATIONS/
│   ├── READY_TO_APPLY/
│   └── _ops/
│       └── job_search.sqlite
├── config/
│   └── job_search_query_packs.json
├── docs/
│   ├── PRODUCT_STRATEGY.md
│   ├── job-search-command-center.md
│   └── manual-smoke-tests/
├── PLAYBOOK/
├── scripts/
│   ├── job_search.py
│   └── linkedin_mcp_query_handoff.py
├── YOUR_PROFILE/
│   ├── USER_PROFILE.md
│   ├── USER_BULLETS.md
│   ├── APPLICATION_PLAYBOOK.md
│   ├── CAREER_STRATEGY.md
│   ├── Fintech/FINTECH.md
│   ├── AI/AI.md
│   └── DESIGN.md
├── AGENTS.md
└── README.md
```

## Validation

Run the deterministic repo gate before handoff:

```bash
make test
```

## Legacy Application Package Generator

The original package generator still exists for full tailored materials.

Generated resume rules:

- Summary, Professional Experience, Skills, Education
- 13 target bullets when the tailored output needs them
- 240-260 characters per generated bullet
- no Certifications section
- hard skills only
- no invented metrics

Cover-letter rules:

- 100-140 words target
- three short paragraphs
- proof-first
- no formal headers

## Credits

Original system built by Shashikiran Devadiga.
OpenCode fork maintained by Antonio Pontarelli.

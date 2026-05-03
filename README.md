# Job Search Command Center

![OpenCode for Job Applications](assets/cc-for-job-applications.png)

**Not a prompt. A job-search operating system.**

This repo helps Antonio discover, screen, track, and apply to high-signal roles
without turning LinkedIn, scattered notes, or resume polishing into the source
of truth.

Forked and maintained by Antonio Pontarelli from the original by Shashikiran
Devadiga.

## Source Of Truth

- [Product Strategy](docs/PRODUCT_STRATEGY.md): why the product exists, what it promises, milestones, success metrics, and open product questions.
- [How It Works](docs/HOW_IT_WORKS.md): current command-center behavior, daily workflow, CLI commands, SQLite state, polling, LinkedIn handoff, and validation.
- [Docs Map](docs/README.md): documentation boundaries and routing.

## What It Does

The command center is a company-first SQLite ledger for:

- companies, sources, jobs, contacts, artifacts, gaps, actions, events, and metrics
- broad query runs and reviewed query-run results
- apply/pass decisions, follow-ups, and outcome history

The system keeps LinkedIn and job boards as discovery sources. SQLite remains the
source of truth.

## Quick Start

Prerequisites:

- [OpenCode CLI](https://opencode.ai)
- Python 3.x
- `python-docx` when generating DOCX application materials

Install the Python dependency when needed:

```bash
pip install python-docx
```

Initialize or inspect the command center:

```bash
python3 scripts/job_search.py init
python3 scripts/job_search.py status
python3 scripts/job_search.py action next
```

Use the full operating guide for command examples:

- [How It Works](docs/HOW_IT_WORKS.md#core-commands)
- [Daily Workflow](docs/HOW_IT_WORKS.md#daily-workflow)
- [LinkedIn MCP Handoff](docs/HOW_IT_WORKS.md#linkedin-mcp-handoff)

## Main Surfaces

- `scripts/job_search.py`: deterministic command-center CLI.
- `scripts/linkedin_mcp_query_handoff.py`: local LinkedIn MCP result normalizer.
- `APPLICATIONS/_ops/job_search.sqlite`: command-center database.
- `APPLICATIONS/READY_TO_APPLY/`: saved high-signal application packages.
- `.agents/skills/job-search/`: live discovery, LinkedIn intake, and role screening.
- `.agents/skills/job-apply/`: ready-JD application routing and answer drafting.
- `YOUR_PROFILE/`: durable profile, proof library, career strategy, answer guidance, and base resume lanes.
- `PLAYBOOK/`: legacy full package-generation templates and DOCX script.

## Validation

Run the deterministic repo gate before handoff:

```bash
make test
```

## Credits

Original system built by Shashikiran Devadiga. OpenCode fork maintained by
Antonio Pontarelli.

# LinkedIn MCP Job Search Plan

Status: partially superseded by `docs/exec-plans/job-search-command-center.md`.

Keep the LinkedIn MCP findings as source-specific context. Do not use this document as the active system plan.

## Purpose

Add a repo-scoped LinkedIn MCP intake layer for this repo without turning application drafting into a brittle scraper workflow.

## Decisions

- Add LinkedIn MCP in repo-local `.codex/config.toml`, not only global config.
- Keep the allowed tool surface narrow:
  - `search_jobs`
  - `get_job_details`
  - `get_company_profile`
  - `search_people`
- Create a separate `$job-search` skill for discovery, validation, and JD normalization.
- Keep `$job-apply` focused on routing, pass/apply decisions, and application drafting once a JD exists.
- Keep LinkedIn access read-only by default.

## Why Separate Skills

- Search and validation have different failure modes than application drafting.
- LinkedIn auth, scraping drift, and session issues should not contaminate the core apply workflow.
- A distinct handoff keeps `JD text` as the contract between search and apply.

## Handoff Contract

`$job-search` should hand off:
- lane recommendation
- company
- role
- short fit reasoning
- main risks
- normalized JD text

`$job-apply` should consume that packet as if the user had pasted the JD directly.

## Follow-up

- Authenticate LinkedIn MCP with `uvx linkedin-scraper-mcp@latest --login`.
- Restart or reopen the Codex project so the repo-local `.codex/config.toml` is loaded cleanly.
- Expand tool access only if there is a clear repeatable need.

## Live Findings

Verified on April 21, 2026:
- `search_jobs` works with the authenticated repo-scoped MCP.
- `get_job_details`, `get_company_profile`, and `search_people` also return usable data.
- Raw LinkedIn search quality is noisy enough that the skill needs query packs and detail validation rather than one literal search.

Observed failure modes:
- loose keyword matching
- malformed top-level metadata such as a company field that resolves to `Remote`
- generic or promoted roles crowding out stronger workflow-fit roles
- date-sorted discovery can be materially worse than relevance-sorted discovery

Implication:
- `$job-search` should start with narrow problem-domain queries, rerun strong cores by relevance when date-sorted results are noisy, validate promising hits with `get_job_details`, and only then enrich with company or people context.

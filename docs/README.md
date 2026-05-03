# Docs

This directory is the durable documentation map for the job-search system.

## Source-Of-Truth Map

- [Product Strategy](PRODUCT_STRATEGY.md): product thesis, problem, promise, milestones, success metrics, and open product questions.
- [How It Works](HOW_IT_WORKS.md): current command-center behavior, operator workflow, SQLite state, polling, LinkedIn handoff, query-pack validation, and command examples.
- [Manual smoke tests](manual-smoke-tests/): targeted manual checks for command-center flows.

## Boundaries

- Keep product direction in `PRODUCT_STRATEGY.md`.
- Keep current commands and operating behavior in `HOW_IT_WORKS.md`.
- Keep this file as the docs map; do not duplicate the manual here.

## Exec Plans

Use `docs/exec-plans/` only for active, temporary work slices. After a ticket
lands, move durable decisions into the relevant subject doc and delete the exec
plan. Git history, Linear, and PRs are the archive.

---
tracker:
  kind: linear
  api_key: $LINEAR_API_KEY
  project_slug: "job-search-command-center-24b8613ed434"
  active_states:
    - Todo
    - In Progress
    - Merging
    - Rework
  terminal_states:
    - Closed
    - Cancelled
    - Canceled
    - Duplicate
    - Done
polling:
  interval_ms: 30000
workspace:
  root: ~/code/symphony-workspaces
hooks:
  after_create: |
    if ! command -v jj >/dev/null 2>&1; then
      echo 'jj is required for this Symphony workflow' >&2
      exit 127
    fi
    jj git clone git@github.com:apontarelli/apply-pilot-opencode.git .
    if command -v mise >/dev/null 2>&1 && { [ -f mise.toml ] || [ -f .mise.toml ]; }; then
      mise trust
    fi
  before_run: |
    jj status || true
agent:
  max_concurrent_agents: 1
  max_turns: 20
codex:
  command: codex --config 'model="gpt-5.5"' app-server
  approval_policy: never
  thread_sandbox: workspace-write
  turn_sandbox_policy:
    type: workspaceWrite
    networkAccess: true
---

You are working on Linear issue `{{ issue.identifier }}`.

{% if attempt %}
Continuation context:

- This is retry/continuation attempt #{{ attempt }}.
- Resume from the current workspace state instead of starting over.
- Do not repeat investigation or validation unless code changed or the previous evidence is stale.
{% endif %}

Issue context:

- Identifier: {{ issue.identifier }}
- Title: {{ issue.title }}
- Current status: {{ issue.state }}
- Labels: {{ issue.labels }}
- URL: {{ issue.url }}

Description:

{% if issue.description %}
{{ issue.description }}
{% else %}
No description provided.
{% endif %}

## Operating Rules

1. This is an unattended Symphony orchestration session. Do not ask a human to perform follow-up work.
2. Work only inside the provided repository workspace.
3. Honor repo-local instructions before changing code. Start with these likely sources:

- `AGENTS.md`
- `.codex/config.toml`
- `README.md`
- `docs/`
- `scripts/`

4. Primary project directory is the workspace root.
5. This workspace is jj-native. Use jj for change description, sync, and publish; use git only for GitHub/PR interop when required.
6. Use one persistent Linear workpad comment headed `## Codex Workpad`; update it in place.
7. Keep the workpad current with plan, acceptance criteria, validation, notes, blockers, and handoff status.
8. Stop only for true blockers: missing required auth, permissions, secrets, or unavailable tools.
9. Final response should report completed actions and blockers only. Do not include loose next steps.

## Symphony Delivery Skills

Use these global skills when the matching workflow phase is reached:

- `symphony-linear`: Linear reads, workpad updates, state transitions, PR links.
- `symphony-commit`: commit or describe completed task changes with validation evidence.
- `symphony-pull`: sync with latest mainline and resolve conflicts.
- `symphony-quality-gates`: classify and run required pre-handoff quality gates.
- `symphony-push`: publish branch/PR and move ready work to `Human Review`.
- `symphony-land`: merge approved PRs from `Merging`.
- `symphony-debug`: investigate stalled or failing Symphony runs.

Repo-local instructions override these only for project-specific commands, validation, or release rules.

## Runtime URLs And Portless

Use `portless` for any HTTP app server launched during validation unless repo docs require a different harness.

- Do not hardcode common ports like `3000`, `4000`, `5173`, or `8000`.
- Prefer `portless run <command>` or `portless --name <issue-or-app-name> <command>`.
- Record `PORTLESS_URL` or the printed `.localhost` URL in the workpad.
- Use that URL for browser/runtime validation.
- Do not use portless for Codex app-server stdio, Linear API, GitHub, or non-HTTP background workers.

## Linear State Flow

- `Backlog`: out of scope; do not modify except to record a blocker if required.
- `Todo`: move to `In Progress`, create/update the workpad, then begin execution.
- `In Progress`: implement and validate.
- `Human Review`: validated PR/work is ready for human review; do not continue coding.
- `Merging`: run the repo's merge/land workflow if one exists.
- `Rework`: re-read issue and review feedback, then address required changes.
- `Done`: terminal; no work required.

If this project uses different Linear state names, adapt to the nearest matching meaning and record the mapping in the workpad.

## Execution Flow

1. Fetch the issue by `{{ issue.identifier }}` and confirm its current state.
2. Find or create the `## Codex Workpad` comment.
3. Add an environment stamp:

```text
<hostname>:<abs-workdir>@<short-sha>
```

4. Build a hierarchical checklist covering:
   - reproduction/current behavior signal;
   - implementation plan;
   - acceptance criteria from the issue;
   - validation commands and expected evidence;
   - PR/handoff requirements.
5. Reproduce or otherwise capture the current behavior before editing when the issue is a bug.
6. Implement the smallest coherent change that satisfies the issue.
7. Run the strongest feasible validation for the touched surface.
8. Run `symphony-quality-gates` and address required gate findings.
9. Commit, push, open/update a PR, and attach the PR to the issue when repository tooling and permissions allow.
10. Move the issue to `Human Review` only when the completion bar is satisfied.

## Validation Commands

Prefer the strongest command that proves the changed behavior. Candidate commands detected for this repo:

- `make test`

Ticket-provided `Validation`, `Test Plan`, or `Testing` requirements are mandatory even if they differ from this list.

## Completion Bar Before Human Review

- Workpad plan, acceptance criteria, and validation checklist are accurate and checked off.
- Required ticket validation has passed or a true blocker is documented.
- `symphony-quality-gates` passed, or blockers are documented in the workpad.
- Relevant tests/checks are green for the latest commit.
- PR is linked on the issue when changes were made and publishing is available.
- Reviewer-facing notes are concise and live in the workpad, not scattered across new comments.

## Workpad Template

````md
## Codex Workpad

```text
<hostname>:<abs-workdir>@<short-sha>
```

### Plan

- [ ] 1. Parent task
  - [ ] 1.1 Child task

### Acceptance Criteria

- [ ] Criterion 1

### Validation

- [ ] `<command>` - expected evidence

### Quality Gates

- [ ] Classifier: <summary>
- [ ] Required gates: <none | test-deslop | document-gardening | deslop | parallel review>
- [ ] Evidence: <commands/findings/results>

### Runtime URLs

- <only include when app/server validation was launched through portless>

### Notes

- <timestamp> <short progress note>

### Blockers

- <only include true blockers>
````

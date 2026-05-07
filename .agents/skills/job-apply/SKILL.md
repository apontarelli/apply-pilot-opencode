---
name: job-apply
description: Use when the user already has a live job description, saved JD.md, or $job-search handoff and wants the best resume lane, a pass/apply call, cover-letter guidance, saved application package, or concise application answers grounded in this repo's existing materials. Prefer existing base resumes over bespoke rewrites. For LinkedIn search, validation, or URL intake, use $job-search first. For daily queue operation, outcomes, metrics, or command-center hygiene, use $career-command-center.
---

# Job Apply

Use this skill for live application routing and answer drafting once the JD is already in hand.

Use `$career-command-center` instead when the user wants daily queue operation,
outcome hygiene, metrics, stale actions, or deciding what command-center work to
do next.

## Goals

1. Route the JD quickly:
   - `FINTECH`
   - `AI`
   - `DESIGN`
   - `PASS`
2. Recommend the best existing resume variant.
3. Decide whether a cover letter is worth it.
4. Draft truthful, concise application answers.
5. Save high-signal applications in `APPLICATIONS/`.
6. Capture reusable improvements in repo docs when patterns recur.

## Read First

- `YOUR_PROFILE/APPLICATION_PLAYBOOK.md`
- `YOUR_PROFILE/CAREER_STRATEGY.md`
- `YOUR_PROFILE/USER_PROFILE.md`
- Relevant base resume:
  - `YOUR_PROFILE/Fintech/FINTECH.md`
  - `YOUR_PROFILE/AI/AI.md`
  - `YOUR_PROFILE/DESIGN.md`

Read `YOUR_PROFILE/USER_BULLETS.md` only if you need supporting proof beyond the base resume.

Use `scripts/job_search.py` to keep cross-session state current:
- `python3 scripts/job_search.py status`
- `python3 scripts/job_search.py company show "Company"`
- `python3 scripts/job_search.py job list --company "Company"`
- `python3 scripts/job_search.py action next --queue apply`
- `python3 scripts/job_search.py event list --company "Company"`

If the user only has a LinkedIn URL, wants to search for roles, or needs job validation before applying, use `$job-search` first.
Use `docs/HOW_IT_WORKS.md#automation-approval-boundary` as the durable policy
for submission, outreach, browser-form, deterministic-rule, raw-payload, and
run-history approval boundaries.

## Default Workflow

1. Read the JD and classify fit.
2. Recommend one of:
   - `Use FINTECH`
   - `Use AI`
   - `Use DESIGN`
   - `Pass`
3. Explain the choice in a few direct lines:
   - role fit
   - interest level
   - comp signal when available
   - comp read against the `180k / 205k-225k / 230k+` bands when disclosed
   - strongest proof match
   - biggest mismatch or risk
4. Decide on cover letter:
   - write one for strong-fit or high-signal roles
   - skip for low-interest, low-signal, or spammy roles
5. If the user asks application questions, answer them:
   - concise
   - truthful
   - no fake enthusiasm
   - no invented metrics
6. If the role is worth saving, create:
   - `APPLICATIONS/READY_TO_APPLY/<Company>_<Role>/JD.md`
   - `APPLICATIONS/READY_TO_APPLY/<Company>_<Role>/QA.md`
   - `APPLICATIONS/READY_TO_APPLY/<Company>_<Role>/COVERLETTER.md`
   - optional DOCX outputs when requested
7. Update the command-center ledger:
   - `ready_to_apply` when the role should be handed to Antonio for the final application
   - `ignored_by_filter` when the role does not survive deeper vetting
   - `discovered` or `screening` when the role is plausible but not worth immediate submission
8. If Antonio later says he submitted, update the ledger to `applied`

Do not submit applications, submit browser forms, click final external
confirmation buttons, send outreach, or mark a role `applied` without explicit
human confirmation for that action.

Assume the JD came from one of:
- pasted job text
- normalized output from `$job-search`
- a saved `JD.md`

If the JD came from `$job-search`, preserve the canonical job URL in the final handoff unless deeper review shows the posting is malformed.

Re-check the preference gates before final handoff:
- interest level
- disclosed compensation
- location or timezone constraints

## Routing Rules

### FINTECH

Use when the role centers on:
- payroll
- accounting
- reporting
- controls
- platform
- trust / identity
- internal ops tooling

Default resume:
- `YOUR_PROFILE/Fintech/FINTECH.md`

### AI

Use when the role centers on:
- AI workflows
- agents
- orchestration
- guardrails / evals
- technical product work in messy operational domains
- operator software
- internal tools
- agentic coding / AI-enabled delivery systems

Default resume:
- `YOUR_PROFILE/AI/AI.md`

Use `YOUR_PROFILE/AI/AI.md` now when the JD is primarily about:
- AI workflow software
- human-in-the-loop operational systems
- agent orchestration
- internal tools / devtools-adjacent workflow products
- high-trust AI features with structured outputs, controls, or evals

Be cautious when the JD primarily expects:
- multiple shipped AI-native product features as the main proof
- consumer AI engagement / recommendation / personalization depth
- model research, core ML, or infrastructure-heavy AI depth
- a story that would be materially stronger only after Hard Sets ships its AI coach

If the AI lane is directionally right but `YOUR_PROFILE/AI/AI.md` is still not the strongest truthful asset for that JD, recommend `YOUR_PROFILE/Fintech/FINTECH.md` instead and say why.

### DESIGN

Use when the role centers on:
- design systems
- product systems
- UX platform
- cross-product interaction models

Default resume:
- `YOUR_PROFILE/DESIGN.md`

### PASS

Pass when:
- the role would require a fake story
- the fit is weak across domain, product type, and seniority
- the user has better lanes to prioritize
- the full JD reveals low interest once the actual problem is clear
- disclosed compensation is clearly weak for the band and not rescued by unusually high interest
- disclosed base comp is below `180k` and the role is not an unusually compelling exception
- the JD's center of gravity is shipped AI-native product proof the current materials do not yet support

## Pipeline Behavior

If `$job-search` handed off the role in the same turn, preserve the same company, role, location, and JD text unless deeper review proves the first screen wrong.

`$job-apply` is the last automated gate before Antonio applies manually. A successful outcome here should mean:
- the role is logged as `ready_to_apply`
- the relevant files exist under `APPLICATIONS/READY_TO_APPLY/<Company>_<Role>/`
- the final handoff shown to Antonio includes the canonical job link
- the final handoff shown to Antonio includes the exact resume to use
- the final handoff shown to Antonio lists any app-specific materials to review
- Antonio can review the saved materials and submit himself

## Answer Standards

- Stay close to shipped proof.
- Do not overstate interest in a company the user does not care about.
- Prefer 3-5 sentence answers unless the form clearly needs more.
- For `ready_to_apply` outcomes, always include the job link in the final response.
- For `ready_to_apply` outcomes, always include the interest level and comp signal in the final response.
- For `ready_to_apply` outcomes, always include the exact resume to use in the final response.
- For `ready_to_apply` outcomes, always list app-specific materials such as `JD.md`, `QA.md`, `COVERLETTER.md`, or `none`.
- For “Why this role/company?” answers:
  - 1 sentence on role fit
  - 1 sentence on relevant proof
  - 1 sentence on why the problem space is interesting
  - 1 sentence on how the user would contribute quickly

## Repo Maintenance

After each live application, ask:
- Should any part of this become reusable?

If yes, update one of:
- `YOUR_PROFILE/APPLICATION_PLAYBOOK.md`
- `YOUR_PROFILE/USER_PROFILE.md`
- `YOUR_PROFILE/USER_BULLETS.md`

Also update `scripts/job_search.py` outputs when the recurring issue is pipeline-related.
Treat reusable profile, playbook, strategy, and deterministic workflow edits as
human-approved maintenance decisions, not automatic mutations from one
application suggestion.

Do not let repo maintenance block the immediate application task.

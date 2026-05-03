---
name: job-search
description: Use when the user wants to search LinkedIn or other job sources, validate whether a specific role is worth applying to, normalize a job post into reusable JD text, screen a target-company role, or gather light company and people context before invoking $job-apply. For daily queue operation, status, metrics, outcomes, stale actions, or command-center hygiene, use $career-command-center. Keep this as an intake layer; do not message people or submit applications.
---

# Job Search

Use this skill for discovery, validation, screening, and JD intake before
application work starts.

Use `$career-command-center` instead when the user wants daily queue operation,
status, metrics, outcomes, stale actions, or command-center hygiene.

## Goals

1. Find roles aligned to current lanes:
   - `FINTECH`
   - `ACCESS`
   - `AI`
2. Filter out low-signal roles quickly.
3. Turn LinkedIn job posts into normalized JD text.
4. Gather light company and people context for later outreach.
5. Hand off a clean JD packet to `$job-apply`.

## Read First

- `YOUR_PROFILE/APPLICATION_PLAYBOOK.md`
- `YOUR_PROFILE/CAREER_STRATEGY.md`
- `YOUR_PROFILE/USER_PROFILE.md`

Read base resumes only when lane fit is unclear:
- `YOUR_PROFILE/Fintech/FINTECH.md`
- `YOUR_PROFILE/Access/ACCESS.md`
- `YOUR_PROFILE/AI/AI.md`

Read `references/query-packs.md` before running multi-query discovery.

Use the registry-backed CLI before broad discovery:
- `python3 scripts/job_search.py company import --file APPLICATIONS/_ops/researched-companies/fintech-targets.json`
- `python3 scripts/job_search.py source list --status active`
- `python3 scripts/job_search.py poll`
- `python3 scripts/job_search.py query packs list --default-only`
- `python3 scripts/job_search.py query packs show FINTECH`
- `python3 scripts/job_search.py query run --source linkedin_mcp --pack FINTECH --limit 25`
- `python3 scripts/job_search.py query run --source manual_browser --pack ACCESS --reason "specific access/trust target role"`

Default discovery backbone:
1. Research target companies externally with Codex/ChatGPT or manual browsing.
2. Import the reviewed company JSON with `company import`.
3. Review configured Greenhouse, Lever, or Ashby sources with `source list`.
4. Run `poll` against configured sources.

Broad job-board APIs and broad source adapters are secondary/backlog. Do not
make SerpApi, JSearch, DataForSEO, Adzuna, or another broad API the default
discovery path.

Exception packs such as `ACCESS`, `PAYMENTS_INSURANCE_CRYPTO_TRUST`, and `INDUSTRIAL_AUTONOMY_BRIDGE` require `--reason` on broad query runs. Do not treat them as default lanes.

Use `scripts/job_search.py` to check history and record search decisions:
- `python3 scripts/job_search.py init` if `status` says the database is not initialized
- `python3 scripts/job_search.py status`
- `python3 scripts/job_search.py company import --file <researched-companies.json>`
- `python3 scripts/job_search.py company show "Company"`
- `python3 scripts/job_search.py job list --company "Company"`
- `python3 scripts/job_search.py action next`
- `python3 scripts/job_search.py event list --company "Company"`

Before searching listings or recommending a role, check the command center for:
- company history, cooldowns, last applied role, last outcome, active jobs, and open actions
- existing jobs for the company, especially duplicate titles or recent attempts
- action history that already makes the next step clear

For target-company work, use the same command center rather than a separate list:
- `python3 scripts/job_search.py company list`
- `python3 scripts/job_search.py company update "Company" --tier 1 --lanes "FINTECH" ...`
- `python3 scripts/job_search.py contact list --company "Company"`
- `python3 scripts/job_search.py action add --company "Company" --queue research --kind vet_company --notes "..."`
- `python3 scripts/job_search.py action add --company "Company" --queue research --kind find_contact --notes "..."`

## Lane Priority

Default search motion:
1. Source-first target-company research, import, and ATS polling.
2. `FINTECH` / `PLATFORM`
3. `AI` / `WORKFLOW`
4. `INDUSTRIAL` / `AUTONOMY` only when the user explicitly wants exploratory bridge roles

Primary lane:
- `FINTECH` / `PLATFORM`
- strongest proof: payroll, accounting, reporting, controls, identity, internal ops, high-trust shared systems
- default resume lane: `YOUR_PROFILE/Fintech/FINTECH.md`

Selective lane:
- `AI` / `WORKFLOW`
- search when the role centers on orchestration, operator tooling, structured outputs, evals, guardrails, or high-trust AI workflows
- default resume lane: `YOUR_PROFILE/AI/AI.md`

Bridge categories that still route through `FINTECH` unless the JD clearly says otherwise:
- payments operations
- insurance / claims workflows
- trust-first crypto infrastructure, reporting, controls, or internal ops
- media / operations software with strong workflow overlap

Low-priority or default-pass:
- pure people-management roles
- consumer growth PM
- ML infra, model research, or data-science platform roles
- pure design systems as the main story
- direct robotics, AV, or hardware-native roles without a credible software-systems bridge

## Preference Gates

Use `YOUR_PROFILE/CAREER_STRATEGY.md` as a real screening surface, not just background context.

Always score each role on:
- `Interest`: high / medium / low
- `Comp`: strong / unclear / weak
- `Geo`: good / caution / weak
- `Win-now fit`: strong / plausible / weak
- `Screen risk`: low / medium / high
- `Bucket`: `ready_to_apply` / `low_effort_apply` / `stretch_warm_path` / `portfolio_gap` / `watch` / `pass`
- `Next action`: exact apply, campaign, proof-gap, watch, or pass action

Default behavior:
- high interest + acceptable risk can become `ready_to_apply`
- medium interest usually needs stronger fit or stronger comp to become `ready_to_apply`
- low interest should usually be `pass` unless the role is an unusually strong bridge
- disclosed comp below `180k` base should usually be `pass`
- `180k-204k` base should usually need high interest, strong scope, or unusually good upside
- `205k-225k` base is the target band
- `230k+` base is strong comp support
- clearly weak disclosed comp should block `ready_to_apply`
- missing comp should not block on its own

## Strategy-Aware Triage

Separate three questions before recommending a role:
1. Do we like it?
2. Can Antonio credibly win it now?
3. If not now, is it worth building toward?

`win_now_fit` outranks `company_pull` for apply-now decisions.

Do not let company excitement, domain fit, or long-term interest hide:
- formal PM-years gaps
- staff/principal/group/director title filters
- people-management-first expectations
- direct domain-proof requirements
- shipped AI-native adoption requirements
- payments rail, API/devtools, crypto trading-core, robotics, industrial, or autonomy expertise that is being used as a hard screen

Bucket rules:
- `ready_to_apply`: strong fit, no major truth gap; continue to `$job-apply`
- `low_effort_apply`: good enough, no fake story, base resume only; counts toward volume
- `stretch_warm_path`: loved or strategic company, but cold odds are weak; create a concrete company-campaign action
- `portfolio_gap`: strong target pattern, but missing reusable proof; create or reference a proof-gap action
- `watch`: good company or space, no clean role or immediate action; record watch condition
- `pass`: fake story, weak interest, weak comp, or high screen risk with no concrete campaign path

Use `stretch_warm_path` only when there is a concrete next action:
- find a recruiter, likely hiring manager, referral, or better-fit role
- draft or prepare approved outreach
- research a specific company angle
- define a targeted artifact

If there is no concrete next action, pass on the role and use company `watch` only when the company still matters.

For Stripe, Mercury, and similar loved stretch companies:
- treat hard-screen roles as target-company campaign inputs, not default application queue items
- search for roles closer to 3-5 years PM or senior IC scope
- apply only when the form does not hard-block or there is a warm path
- avoid counting campaign work as application volume

## Tooling

Prefer the repo-scoped LinkedIn MCP when available:
- `search_jobs`
- `get_job_details`
- `get_company_profile`
- `search_people`

LinkedIn access is read-only by default.

Do not use:
- `send_message`
- `connect_with_person`
- inbox or conversation tools

If the LinkedIn MCP is unavailable or not authenticated, say so directly and ask for one of:
- pasted JD text
- LinkedIn job text copied from the page
- company and role name for a manual fit call

## Querying

`search_jobs` is noisy. Do not trust one broad query.

Default broad-query order, after source-first target-company polling:
1. Start with `2-4` narrow queries from `references/query-packs.md`.
2. Prefer title + problem-domain combinations over generic title-only searches.
3. Broaden from exact domain to adjacent workflow, not from exact domain to generic `platform` alone.
4. If the first pass is weak, rerun the strongest core queries by relevance before drifting into weaker adjacent domains.
5. Validate promising hits with `get_job_details` before recommending them.
6. Use `get_company_profile` and `search_people` only on shortlisted roles.

Avoid broad first-pass searches like:
- `product manager platform`
- `product manager internal tools`
- `ai product manager`
- `director of product`

## Batch Screening

When the user wants maximum automation:
1. run `python3 scripts/job_search.py init` first if the database is not initialized
2. read `python3 scripts/job_search.py status`
3. read `python3 scripts/job_search.py action next` to see pending screen/apply work
4. check each target company with `company show`, `job list --company`, and `event list --company` before searching or validating new listings
5. search LinkedIn in batches only after existing company/job/action history is understood
6. skip roles already tracked unless the user asks to revisit them or new details materially change the case
7. validate promising roles with `get_job_details`
8. continue directly into `$job-apply` for roles that survive the first screen
9. record every final decision with `scripts/job_search.py`

Default job statuses:
- `ignored_by_filter`: pass
- `screening`: still evaluating
- `ready_to_apply`: worth handing off to Antonio for the final human application
- `applied`: Antonio confirms he submitted
- `rejected`, `closed`, or `archived`: known terminal outcomes

The skill should not stop at a shortlist if the user asked for end-to-end vetting.

## Default Workflow

1. Identify the user's need:
   - search for roles
   - validate a specific role
   - normalize a LinkedIn URL into JD text
2. Check command-center history before searching:
   - run `python3 scripts/job_search.py init` first if the database is not initialized
   - `python3 scripts/job_search.py status`
   - `python3 scripts/job_search.py action next`
   - for each known company, run `company show`, `job list --company`, and `event list --company`
3. Map the request to likely lanes:
   - `FINTECH`
   - `AI`
   - `INDUSTRIAL`
   - mixed / unclear bridge search
4. Use LinkedIn MCP to gather only the minimum needed:
   - `search_jobs` for discovery
   - `get_job_details` for a specific posting
   - `get_company_profile` for brief company context
   - `search_people` for likely hiring-manager or recruiter context when useful
5. Produce a compact decision:
   - likely lane
   - interest level
   - win-now fit
   - screen risk
   - bucket
   - comp signal when available
   - comp read against the `180k / 205k-225k / 230k+` bands when disclosed
   - why it fits
   - biggest mismatch or risk
   - exact next action
6. If the user asked for search-only, stop at the shortlist and record the decision.
7. If the user asked for search + vetting, continue directly into `$job-apply` only for `ready_to_apply` and `low_effort_apply` roles.
8. Normalize the role into a reusable packet for `$job-apply`:
   - company
   - role title
   - location / remote status if available
   - canonical job URL
   - recommended resume
   - JD summary
   - raw JD text or best-available extracted responsibilities / requirements
   - company context
   - optional people context for later outreach

## Search Standards

- Bias toward the current active search motion in `YOUR_PROFILE/APPLICATION_PLAYBOOK.md`.
- Default to the current application volume plan: more fintech/platform discovery than AI exploration.
- Prefer quality over volume.
- Avoid presenting long undifferentiated lists.
- Prefer truthful title bands first:
  - `senior product manager`
  - `product manager`
  - `lead product manager` only if the JD reads like a senior IC or staff-scope role rather than a people-manager role
- Prefer direct problem filters:
  - payroll / accounting / reporting / controls / trust / identity / internal ops
  - AI workflows / agents / orchestration / operator tools / evals / guardrails
- Treat company, title, and location metadata from `search_jobs` as provisional until validated.

For search results, return a short ranked list with:
- company
- role
- lane
- interest level
- win-now fit
- screen risk
- bucket
- quick reason
- risk or mismatch

## Result Hygiene

Discard or down-rank results when:
- company or title metadata is malformed
- the detail page shows a different problem than the search result implied
- the title is inflated beyond a truthful pitch
- the title implies formal people management even when the domain fit looks strong
- the role is clearly people-management heavy
- the domain center of gravity would require a fake story
- the posting looks stale, thin, spammy, or duplicated

Validate at least the most promising hits with `get_job_details` before calling them high-signal.

Before recommending or screening a role, check whether it is already in the command center:
- if the company is in cooldown, do not reopen it unless the role is materially different or strategically important
- if the job is already `ready_to_apply`, do not re-vet unless the user asks
- if the job is already `ignored_by_filter`, `closed`, or `archived`, skip unless there is a concrete reason to revisit
- if open actions already exist, finish or update those actions before creating duplicate work

## Validation Standards

When validating a specific role, answer:
- Is this lane-aligned?
- Is this actually interesting enough to pursue?
- Can Antonio credibly win this now?
- Is there a formal recruiter-screen risk?
- Is compensation disclosed, and if so does it clear the current comp bands?
- Is it truthful with current proof?
- Does it look high-signal, medium-signal, or low-signal?
- Is `$job-apply` the next step, or should this become campaign, proof-gap, watch, or pass work?

Pass quickly when:
- the role needs a fake story
- the center of gravity is people management the user has not done
- the role expects deep domain-native proof that is not bridged by current materials
- the role is generic enough that the search query matched but the JD does not
- the role is low-interest and not a special strategic exception
- the disclosed compensation is clearly weak for the seniority band
- the disclosed base comp is below `180k` and the role is not an unusually compelling exception
- the posting looks stale, thin, spammy, or internally inconsistent

## Logging

Every screened role should end with command-center writes through `scripts/job_search.py`.

Minimum fields:
- `company`
- `job title`
- `status`
- `lane`
- `fit_score` or concise fit/risk notes when available
- `compensation_signal`
- `recommended_resume`
- `canonical_url`
- `application_folder` or material paths when saved
- bucket, `win_now_fit`, `screen_risk`, and `next_action` in notes when no first-class field exists
- optional `external_ref` or `linear_url` in notes when a proof gap has been promoted to Linear

Use:
- `ignored_by_filter` for passes
- company `watch` or action notes for plausible but deferred targets
- `ready_to_apply` when the role should be handed off to Antonio
- `applied` when Antonio confirms submission
- `rejected`, `closed`, or `archived` when the outcome is known

Action conventions:
- company campaign: `find_better_role`, `find_contact`, `draft_outreach`, `follow_up`, `company_research`
- proof gap: `build_artifact`, `product_teardown`, `portfolio_case_study`, `demo`, `resume_gap`, `gap_research`
- market signal: `ship_note`, `build_log`, `problem_teardown`, `artifact_release`, `lesson_learned`, `conversation`
- watch: `monitor_company`, `monitor_role`, `revisit_later`, `poll_source`

Do not add new SQLite schema for these fields until repeated usage proves it is needed.

## Target Company Research

Use this flow when the user wants to add companies to the target list, find
role/source opportunities, or vet a company from external research.

Use `$career-command-center` for ongoing queue operation, stale-action cleanup,
metrics, and state hygiene around already-tracked companies.

1. Start from command-center reality:
   - `status`
   - `company list`
   - `job list`
   - `contact list`
   - `action next --queue research`
2. Classify existing companies before adding many new ones:
   - `tier 1`: strongest strategic targets; worth contact research, role polling, or targeted proof
   - `tier 2`: good targets; monitor roles and apply when fit is clean
   - `tier 3`: opportunistic; keep only if a specific role justifies attention
   - `watch`: plausible company but no immediate role or contact motion
   - `archived`: weak fit, stale, or not worth future search time
3. Evaluate target companies on:
   - lane fit: `FINTECH`, `ACCESS`, `AI`, `MEDIA_PLATFORM`, or `PASS`
   - problem fit: payroll, accounting, reporting, controls, identity/access, internal ops, AI workflow, operator systems
   - interest: high / medium / low
   - comp likelihood: strong / unclear / weak
   - role-market signal: likely PM openings at truthful seniority
   - contact path: warm path, recruiter path, hiring-manager path, or none yet
   - research gap: what must be known before applying or investing more time
4. Record the decision:
   - update company `tier`, `lanes`, `why_interesting`, `fit_thesis`, `known_gaps`, `target_roles`, and `notes`
   - add contacts only when you have a real person and source link
   - add `research:vet_company`, `research:find_contact`, or `artifact:artifact_idea` actions when there is a concrete next step
   - add a gap when the blocker is reusable or material, not just ordinary uncertainty
5. Do not let target-company research block the apply queue:
   - active `ready_to_apply` roles stay first unless the user explicitly prioritizes company research
   - add new companies in small batches, then queue research actions instead of trying to finish every company in one pass

Default target-company expansion batch:
- 5-8 fintech/platform companies
- 2-4 access/trust workflow companies
- 2-4 AI workflow companies
- avoid generic B2B SaaS lists unless the company maps to the current proof

Target-company handoff format:
- `Add now`: company, tier, lane, why, target roles, next action
- `Watch`: company, lane, condition that would make it active
- `Skip`: company, reason
- `Queue`: exact `action add` commands or confirmed command-center actions

Common writes:
- `python3 scripts/job_search.py company add "Company" ...`
- `python3 scripts/job_search.py job add "Company" "Role" --url "..." ...`
- `python3 scripts/job_search.py job status <job_id> ready_to_apply --notes "..."`
- `python3 scripts/job_search.py event add --company "Company" --job-id <job_id> --type note --notes "..."`
- `python3 scripts/job_search.py action done <action_id> --notes "..."`

## Handoff To `$job-apply`

When screening a role, end with a handoff or routing block:

- `Lane`: `FINTECH` / `ACCESS` / `AI` / `PASS`
- `Recommendation`: `ready_to_apply` / `low_effort_apply` / `stretch_warm_path` / `portfolio_gap` / `watch` / `pass`
- `Company`: ...
- `Role`: ...
- `Location`: ...
- `Link`: canonical job URL
- `Interest`: high / medium / low
- `Win-now fit`: strong / plausible / weak
- `Screen risk`: low / medium / high
- `Comp`: strong / unclear / weak
- `Resume`: exact base resume to use
- `Why now`: 1-2 lines
- `Risks`: 1-2 lines
- `Next action`: exact apply, campaign, proof-gap, watch, or pass action
- `App Materials`: any saved JD / QA / cover letter files to review before applying, or `none yet`
- `JD Text`: normalized text

Exploratory industrial or autonomy roles should usually still hand off as `FINTECH` when the bridge story is truthful, otherwise `PASS`.

If the user asked for automated vetting, continue into `$job-apply` without asking for a second command only when the bucket is `ready_to_apply` or `low_effort_apply`.

For `ready_to_apply` roles, always show:
- the job link
- the exact resume to use
- any app-specific materials to review before submitting

## Saving Work

For `ready_to_apply` roles, save under `APPLICATIONS/READY_TO_APPLY/<Company>_<Role>/`.

Maintain `APPLICATIONS/READY_TO_APPLY/INDEX.md` as the human click-through queue:
- every `ready_to_apply` role must appear there
- the job title must be a Markdown link to the canonical job URL
- include the exact resume lane and a link to the saved role folder, `JD.md`, `QA.md`, or `SEARCH.md`
- keep high-interest and urgent roles at the top
- when a role becomes `applied`, `closed`, `ignored_by_filter`, or otherwise terminal, move it out of the active apply section

For `watch` roles, save only when the user asks or the role is unusually strong but deferred.

When saving search-stage material, prefer:
- `APPLICATIONS/READY_TO_APPLY/<Company>_<Role>/JD.md`
- `APPLICATIONS/READY_TO_APPLY/<Company>_<Role>/SEARCH.md`

Keep search-stage notes concise.

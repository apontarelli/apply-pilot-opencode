# APPLICATION PLAYBOOK

---

## PURPOSE

Keep the repo useful during active job search.

This file is for:
- recurring application questions
- answer patterns worth reusing
- guidance for when to create extra materials
- improvements the repo should absorb after live applications

This file is not for:
- one-off company research that does not generalize
- replacing the resume variants

---

## CURRENT MOTION

- Default resume for active applications: `YOUR_PROFILE/Fintech/FINTECH.md`
- Access / trust workflow resume: `YOUR_PROFILE/Access/ACCESS.md`
- Secondary resume for targeted applications: `YOUR_PROFILE/AI/AI.md`
- Daily application target: `5` fintech/platform applications per weekday
- Weekly target: `25`
- Do not pause applications while building new resume variants
- Default Codex entrypoint for live applications: `$job-apply`
- Default Codex entrypoint for LinkedIn discovery and intake: `$job-search`

Current build order:
1. Apply with `FINTECH.md`
2. Use `ACCESS.md` for identity, access management, employee onboarding/offboarding, access reviews, compliance operations, and trust-management workflow roles
3. Use `AI.md` selectively for strong-fit AI workflow / operator systems roles
4. Use Hard Sets AI workout import selectively as demoable pre-launch AI proof
5. Ship Hard Sets AI coach to deepen AI-native product proof further
6. Research physical-world automation segments
7. Build `INDUSTRIAL_SYSTEMS.md`

---

## OPERATING QUEUES

Daily job-search execution has five separate queues. Do not mix application volume with campaign, proof, or market-signal work.

### Application Queue

Purpose:
- keep pipeline volume alive

Counts:
- `ready_to_apply`
- `low_effort_apply`

Cadence:
- `5` applications per weekday

Done means:
- submitted application, or a role is ready for Antonio to submit with exact link, resume, and required materials

Owner system:
- SQLite command center
- saved role materials under `APPLICATIONS/READY_TO_APPLY/` when needed

### Company Campaign Queue

Purpose:
- improve access to loved or stretch companies

Cadence:
- `1` company campaign action per weekday
- cap routine work at `20-30` minutes unless explicitly promoted to a project

Task kinds:
- `find_better_role`
- `find_contact`
- `draft_outreach`
- `send_outreach` only after Antonio approves
- `follow_up`
- `company_research`

Done means:
- concrete role lead, contact, outreach draft, sent outreach, follow-up, or company-specific research note

Owner system:
- SQLite command-center actions
- Linear only when the task becomes system-improvement work

### Proof Gap Queue

Purpose:
- close reusable credibility gaps across several companies or lanes

Cadence:
- `1` proof-gap block per week

Task kinds:
- `build_artifact`
- `product_teardown`
- `portfolio_case_study`
- `demo`
- `resume_gap`
- `gap_research`

Done means:
- a reusable artifact, brief, demo, case study, resume proof point, or scoped follow-up ticket exists

Owner system:
- SQLite command-center actions for local tracking
- separate Side Projects Linear project when the artifact becomes real build work
- use action notes for optional `external_ref` or `linear_url`

### Market Signal Queue

Purpose:
- turn Hard Sets and related work into credible public proof

Cadence:
- `1` market-signal action per week
- start as guidance plus optional action kind; do not make this a first-class SQLite queue yet

Channels:
- LinkedIn: career signal for product craft, AI workflow, operator UX, trust, and systems thinking
- X: founder/product signal for building in public, app progress, product taste, experiments, and light promotion

Task kinds:
- `ship_note`
- `build_log`
- `problem_teardown`
- `artifact_release`
- `lesson_learned`
- `conversation`

Done means:
- draft, published post, released artifact, useful reply/comment, or reusable content note

Claim-strength rule:
- LinkedIn should be mostly shipped or demoable proof
- X can include shipped work, in-progress work, opinions, experiments, and promotion

### Watch Queue

Purpose:
- monitor companies or roles without turning them into active work

Task kinds:
- `monitor_company`
- `monitor_role`
- `revisit_later`
- `poll_source`

Done means:
- watch condition is recorded, checked, or converted into application/campaign/proof work

Owner system:
- SQLite company status, job status, events, and actions

### Linear Boundary

Use Linear for:
- system improvements to this repo
- larger proof/build artifacts under the Side Projects team

Do not use Linear for:
- daily application execution
- routine contact search
- small follow-ups
- normal watch-list maintenance

---

## LIVE APPLICATION RULES

When a live application comes in:
1. Help answer the immediate question
2. Stay true to existing proof; do not invent credentials or enthusiasm
3. Use the current resume lane unless there is a clear mismatch
4. After answering, decide whether the repo needs a durable update

Preferred flow:
1. If you need discovery, validation, or LinkedIn URL intake, invoke `$job-search`
2. Invoke `$job-apply` with the pasted JD or the normalized JD packet from `$job-search`
3. Route to the best existing resume lane or pass
4. Draft only the extra materials the application actually needs

### Batch screening and handoff

Default automation goal:
- search listings in batches
- vet them one by one
- hand only `ready_to_apply` roles to Antonio for final submission

Durable state lives in the SQLite command center:
- `APPLICATIONS/_ops/job_search.sqlite`
- deterministic CLI: `scripts/job_search.py`

Default job statuses:
- `ignored_by_filter`
- `screening`
- `ready_to_apply`
- `applied`
- `rejected`
- `closed`

Rules:
- check company, job, action, and event history before searching listings
- record every screened role, not just the winners
- skip jobs already tracked unless there is a reason to revisit
- let `$job-search` continue straight into `$job-apply` when the user wants end-to-end vetting
- treat `$job-apply` as the final automated gate before Antonio submits manually
- when Antonio confirms he applied, update the job to `applied` and log an `application_submitted` event
- every `ready_to_apply` handoff shown to Antonio must include the job link, not just saved file paths
- every `ready_to_apply` handoff shown to Antonio must include the resume to use and any app-specific materials to review
- interest level and comp signal are real gates, not optional commentary

Low-effort apply rule:
- if a role is good enough to submit now with an existing base resume, it should be `ready_to_apply`, not `watch`
- reserve company `watch` status or action notes for roles not worth immediate submission
- record `low_effort_apply` in job or action notes when the right move is: existing resume, no custom cover letter, and only minimal QA if the form forces text fields
- default low-effort apply shape: medium-or-better interest, geo good enough, comp not clearly weak, and no fake story required
- `low_effort_apply` counts toward the daily and weekly application target

### LinkedIn MCP intake

Use the repo-scoped LinkedIn MCP as an optional intake layer, not as the application workflow itself.

Use it for:
- finding roles
- checking whether a posting is worth the time
- extracting normalized JD text from LinkedIn
- getting light company context
- identifying likely recruiter or hiring-manager targets for later outreach

Do not use it by default for:
- sending messages
- connection requests
- inbox work
- any action that mutates LinkedIn state

Default rule:
- keep LinkedIn MCP read-only
- treat it as upstream of `$job-apply`
- if MCP is unavailable or auth is stale, fall back to pasted JD text and keep moving

### Interest and comp filters

Use `YOUR_PROFILE/CAREER_STRATEGY.md` to screen for:
- real interest in the problem space
- remote/timezone practicality
- disclosed compensation quality when available

Current comp rule:
- use `180k` base as the default floor
- treat `205k-225k` base as the target band
- treat `230k+` base as premium / stretch comp
- missing comp should not block a role by itself
- clearly weak disclosed comp should usually block `ready_to_apply`
- disclosed comp below `180k` should usually be `pass` unless the role is unusually compelling

### AI lane routing

Use `YOUR_PROFILE/AI/AI.md` now when the JD centers on:
- AI workflow software
- agents / orchestration
- human-in-the-loop operational systems
- internal tools or devtools-adjacent AI products
- guardrails, evals, structured outputs, or high-trust AI workflows

Prefer `YOUR_PROFILE/Fintech/FINTECH.md` or pass when the JD centers on:
- consumer AI product growth
- recommendation / personalization as the main proof need
- multiple shipped AI-native features as the primary credibility test
- model research, ML platform, or infra-heavy AI depth

Current rule:
- do not wait broadly for Hard Sets AI coach to ship before using `YOUR_PROFILE/AI/AI.md`
- Hard Sets AI workout import is valid pre-launch proof for interviews and targeted AI roles when framed as built, tested, and demoable
- keep the pre-launch caveat in interview framing and tailored answers, not in the base resume bullet itself
- do not call Hard Sets AI workout import launched or cite adoption metrics that do not exist yet
- keep Wrapbook as the main shipped AI proof when a JD filters hard on production credibility
- do use the JD to decide whether current AI proof is sufficient
- after Hard Sets AI workout import launches or Hard Sets AI coach ships, revisit the threshold for AI-native product roles

### Access / onboarding lane routing

Use `YOUR_PROFILE/Access/ACCESS.md` when the JD centers on:
- identity and access management
- employee onboarding or offboarding
- access reviews or permission-sensitive workflows
- trust management, compliance operations, or auditability
- HRIS-adjacent operational workflows where setup, controls, and customer trust matter

Default proof hierarchy:
- Wrapbook company/project setup strategy and requirements, including dependency mapping across hiring, startwork, employee management, payroll / hours-to-gross calculations, workers comp, and accounting
- reusable multi-step setup pattern established through the design system after project setup exposed a common need for complex, savable flows
- MFA rollout and Auth0 migration for 50,000+ active users
- reporting and workflow systems across payroll, onboarding, and financial operations
- AI workflow guardrails as a supporting differentiator, not the headline unless the JD centers on AI

Boundary:
- Antonio should claim strategy, requirements, dependency mapping, and design/engineering partnership for the original project setup refactor
- do not claim end-to-end rollout ownership for that refactor because he moved teams before final delivery

Prefer `ACCESS.md` over `AI.md` when AI is listed as an expansion opportunity rather than the role's core operating surface.

Durable update examples:
- a recurring “Why this role/company?” pattern
- a recurring AI / platform / fintech positioning answer
- a repeated weakness in the resume or profile
- a recurring application field that deserves a prepared response

---

## RECURRING QUESTION TYPES

### Why this role / why this company

Default pattern:
- 1 sentence on role fit
- 1 sentence on relevant proof
- 1 sentence on why the product/problem space is interesting
- 1 sentence on why the user would contribute quickly

Good ingredients:
- 0-to-1
- high-trust workflows
- platform/shared systems
- AI workflows / guardrails / evals
- operational complexity
- for media roles, optional domain credibility from film/TV production finance plus nearly 20 years as a recording artist and producer

Avoid:
- flattery
- overclaiming passion for a company you do not really care about
- generic “mission-driven” filler
- using the music background as a substitute for shipped product proof

### Optional cover letter

Create one when:
- the role is strong enough to justify the extra signal
- the job is a meaningful lane fit
- the form clearly allows it and the company is likely to read it

Skip or minimize when:
- low-interest role
- low-signal job board spam
- the application already has multiple custom text fields

Default standard:
- short
- direct
- no ornate enthusiasm
- resume-consistent

### Crypto bridge screen

Use `YOUR_PROFILE/Fintech/FINTECH.md` for crypto roles when the work is primarily about:
- trust, controls, and auditability
- reporting, ledger visibility, or reconciliation
- identity, onboarding, permissions, or compliance workflows
- internal operations, finance tooling, or shared product systems
- stablecoin payments or institutional workflow software where operator reliability matters more than trading expertise

Treat as a bridge role, not a direct hit, when the domain is crypto but the product problems still map to shipped proof in:
- accounting and payroll operations
- high-trust financial workflows
- platform and shared systems
- messy data and reporting surfaces

Pass when the role explicitly requires:
- matching engine or exchange-core product experience
- custody architecture or wallet-infrastructure depth
- post-trade settlement, collateral, or clearing expertise
- institutional trading workflows as the center of gravity
- tokenomics, staking economics, protocol incentives, or onchain governance design as core proof
- market-structure fluency that would require a fake story

Default rule:
- if trust-and-operations is the core problem, apply with `FINTECH.md`
- if trading infrastructure is the core problem, pass unless there is unusually strong adjacent overlap

Useful “Why crypto?” angle:
- crypto compresses finance, infrastructure, and trust into one product surface
- the relevant bridge from Antonio's background is high-stakes financial operations, controls, reporting, and workflow reliability
- avoid generic enthusiasm about tokens or markets; stay grounded in product problems

### Payments bridge screen

Use `YOUR_PROFILE/Fintech/FINTECH.md` for payments roles when the work is primarily about:
- high-trust money workflows
- reconciliation, settlement visibility, and downstream financial correctness
- operator-facing payment tooling
- payment reliability, exceptions, or workflow design
- API and partner integrations where product judgment matters more than deep network-specialist depth

Treat as a bridge role, not a direct hit, when the JD prefers payments experience but the core product problem still maps to shipped proof in:
- accounting and payroll operations
- reporting and ledger-adjacent systems
- controls, auditability, and financial workflow reliability
- cross-functional platform work across engineering, operations, and finance

Low-priority apply or pass when the role explicitly requires:
- deep ACH, NACHA, card-network, or processor/gateway expertise as the main proof
- fraud, dispute, or transaction-monitoring depth as the core domain moat
- direct prior ownership of authorization, capture, settlement, and payment-method expansion
- payments-intelligence optimization where the main proof is ML-driven authorization, fraud, dispute, or cost-routing systems
- formal product-manager people leadership when Antonio does not have that proof

Default rule:
- if the job is mostly about trustworthy financial workflows and systems judgment, apply with `FINTECH.md`
- if it is mostly about payment-rails specialization, payments-intelligence optimization, or PM people management, apply only if friction is low or pass
- do not over-claim direct payments pedigree; frame the overlap as financial-systems, controls, reconciliation, and reliability experience

### Insurance / claims bridge screen

Use `YOUR_PROFILE/Fintech/FINTECH.md` for insurtech roles when the work is primarily about:
- claims or case-management workflows
- operator-facing insurance tooling
- trust, auditability, exceptions, or decision support
- billing, controls, reporting, or workflow reliability in a regulated environment
- claimant, adjuster, or internal-ops experiences backed by complex product logic

Treat as a bridge role, not a direct hit, when the JD prefers insurance experience but the core product problem still maps to shipped proof in:
- payroll, accounting, and other high-trust financial workflows
- identity, permissions, controls, and reporting systems
- workers comp or insurance-adjacent operational logic
- AI used carefully inside decision-heavy workflows, with guardrails and clear system boundaries

Low-priority apply or pass when the role explicitly requires:
- deep carrier-side claims operations, claims-adjusting, or policy-admin ownership
- underwriting, actuarial, pricing, reserve, or risk-model specialization as the center of gravity
- fraud, SIU, or insurance-operations depth that would require a fake story
- formal PM people-management proof when that is clearly non-negotiable

Default rule:
- if the job is mostly about trustworthy insurance workflow software and systems judgment, apply with `FINTECH.md`
- if the job is mostly about insurance-specialist depth or explicit people-management requirements, apply only if friction is low or pass
- do not over-claim insurtech pedigree; frame the overlap as high-trust financial systems, controls, reporting, and insurance-adjacent workflow experience

Useful “Why insurance?” angle:
- insurance is another high-stakes workflow domain where clarity, auditability, and decision traceability matter
- the relevant bridge from Antonio's background is financial operations, controls, reporting, workers comp, and product systems that must hold up under real operational pressure

### Ad tech / media buying screen

Use `YOUR_PROFILE/Fintech/FINTECH.md` only as a low-conviction bridge when the role is primarily about:
- operator-facing workflow software
- order, booking, billing, reconciliation, or approval flows adjacent to advertising operations
- enterprise systems judgment where the domain layer is ads but the real product challenge is workflow correctness and downstream coordination

Treat as a stretch apply, not a direct hit, when the JD prefers ad-tech experience but the core product problem still maps to shipped proof in:
- stateful workflow design
- billing, reporting, and downstream system integration
- high-trust internal tooling used by operators
- cross-functional execution across operations, finance, legal, and policy stakeholders

Pass when the role explicitly requires:
- Direct IO or programmatic-buying depth as the main credibility test
- Mediaocean, Prisma, ad server, trafficking, yield, or campaign-management expertise
- ad-tech domain fluency that would require a fake story
- category-native proof in media planning and insertion-order workflows rather than general workflow skill

Default rule:
- if the job is mainly enterprise workflow and coordination with light ad-tech specificity, low-priority swing with `FINTECH.md`
- if the job is mainly ad-tech/media-buying product depth, pass
- do not over-claim ads pedigree; frame any overlap as workflow systems, billing/reporting rigor, and operational product judgment

### Industrial / robotics / manufacturing software bridge screen

Use `YOUR_PROFILE/Fintech/FINTECH.md` only as a bridge for industrial or manufacturing software roles when the work is primarily about:
- operator-facing workflow software
- scheduling, coordination, quoting, tracking, or execution systems around factory operations
- high-stakes internal tools where reliability, correctness, and cross-functional systems judgment matter more than deep robotics-domain expertise
- software that helps technical teams manage complex real-world workflows, even if the end domain is manufacturing

Treat as a stretch apply, not a direct hit, when the JD prefers industrial or robotics context but the core product problem still maps to shipped proof in:
- high-trust operational systems
- internal tools used by expert operators
- workflow orchestration across engineering, operations, and business stakeholders
- complex software delivery in domains where mistakes are costly

Pass when the role explicitly requires:
- direct CAD / CAM / PLM / MES / robotics software experience
- path planning, simulation, collision detection, or computational geometry as core product proof
- manufacturing process expertise, digital fabrication depth, or factory-ops credibility that would require a fake story
- technical education or domain background that is clearly being used as a screen

Default rule:
- if the role is mainly workflow and coordination software around industrial operations, consider a low-priority bridge apply with `FINTECH.md`
- if the role is mainly robotics-domain software or geometry-heavy technical tooling, pass unless there is unusually strong adjacent overlap
- do not over-claim manufacturing pedigree; frame the overlap as trusted operator software, systems judgment, and high-stakes execution

Useful “Why industrial software?” angle:
- the long-term draw is software coordinating real-world systems where reliability and execution quality matter
- the credible bridge from Antonio's background is turning messy, high-stakes workflows into dependable software for expert users
- avoid pretending to be a robotics insider; stay grounded in operator software, systems design, and cross-functional delivery

### Autonomy / transportation systems software bridge screen

Use `YOUR_PROFILE/Fintech/FINTECH.md` as a bridge for autonomy or transportation-software roles when the work is primarily about:
- enterprise software coordinating real-world operations
- traffic, fleet, dispatch, routing, scheduling, or integration systems around physical movement
- operator-facing platforms that must work with legacy infrastructure, external partners, and technical constraints
- system orchestration where product judgment matters more than direct autonomy-stack or controls depth

Treat as a meaningful bridge apply, not a direct hit, when the JD includes autonomy or vehicle context but the PM scope is still centered on:
- SaaS platforms and enterprise integrations
- roadmap ownership across engineering, operations, customers, and external partners
- complex workflow software in domains where reliability and correctness matter
- 0-to-1 platform definition under ambiguity

Pass when the role explicitly requires:
- direct autonomy-stack, AV, or robotics product ownership
- embedded systems, controls, perception, simulation, or vehicle-software depth as core proof
- deep freight, rail, or transportation-domain expertise that would require a fake story
- hardware program management as the center of gravity rather than enterprise software

Default rule:
- if the role is mainly enterprise software for coordinating physical operations, apply as a bridge with `FINTECH.md`
- if the role is mainly embedded autonomy, controls, or hardware-domain product work, pass unless there is unusually strong adjacent overlap
- do not over-claim transportation pedigree; frame the overlap as high-stakes systems software, integrations, operator workflows, and technical product judgment

Useful "Why this category?" angle:
- the long-term draw is software that coordinates real-world systems, not transportation branding by itself
- the credible bridge from Antonio's background is 0-to-1 product work in complex, high-trust operational domains with real downstream consequences
- emphasize system orchestration, integrations, and dependable operator software over domain cosplay

### AI / computer vision / physical security screen

Use `YOUR_PROFILE/AI/AI.md` only when the role is primarily about:
- operator workflow software with AI layered into decision support
- explainability, guardrails, structured outputs, and trustworthy augmentation
- roadmap ownership for AI features where the PM value is workflow judgment more than deep model specialization
- enterprise operations products in physical-world domains where the core proof need is still high-trust product systems

Treat as an interesting but selective bridge apply, not a direct hit, when the JD includes security operations, monitoring, or physical-world response but the actual PM scope still maps to:
- messy operator workflows
- enterprise customer discovery in high-stakes environments
- AI-assisted decision support rather than core perception or model-platform ownership
- product work where trust, explainability, and operational reliability matter more than raw AI novelty

Pass when the role explicitly requires:
- multiple years shipping AI-native products as the main credibility test
- computer vision, video analytics, anomaly detection, or real-time AI systems depth
- model training pipelines, dataset management, inference optimization, or edge deployment as expected PM fluency
- security-tech or surveillance-domain background that would require a fake story

Default rule:
- if the job is mostly trustworthy operator software with some AI, consider `AI.md`
- if the job is really screening for prior AI/CV shipping depth, real-time model tradeoffs, or security-domain pedigree, pass
- do not let long-term interest in physical-world systems override the current proof bar

Useful "Why this category?" angle:
- the draw is high-stakes software augmenting real operators in real environments
- the truthful bridge is AI workflow judgment, guardrails, structured outputs, and trusted operational software
- avoid pretending to be a computer-vision or security-tech insider

### Media / content production / live streaming bridge screen

Use `YOUR_PROFILE/Fintech/FINTECH.md` as a bridge for media-platform roles when the work is primarily about:
- media operations, metadata, asset management, integrations, or operator-facing workflow software
- shared platforms that help production, editorial, marketing, or downstream teams move faster
- technical product strategy across APIs, data models, reliability, and cross-system coordination
- workflow automation where the real proof need is platform judgment, not pure consumer-media growth

Treat as a selective bridge apply, not a direct hit, when the JD includes live media, sports, or streaming context but the PM scope still maps to:
- complex platform or integration ownership
- cross-functional alignment across technical teams and operational partners
- real-time or high-stakes workflows where reliability and discoverability matter
- messy domain translation rather than direct playback or recommendation ownership

Pass when the role explicitly requires:
- deep prior ownership of media asset management, MAM/DAM systems, live ingest, transcoding, playback, or distribution infrastructure
- sports-broadcast, live control-room, or streaming-platform depth as the main credibility screen
- recommendation, personalization, or consumer engagement expertise as the center of gravity
- a level of media-domain fluency that would require a fake story

Default rule:
- if the role is mainly platform, metadata, integrations, and workflow reliability for media teams, consider a bridge apply with `FINTECH.md`
- if the role is mainly streaming infrastructure, playback quality, or direct live-media-domain depth, apply only if friction is low or pass
- do not over-claim media-tech pedigree; frame the overlap as trusted platform work, entertainment-production context, and high-stakes workflow software

Useful "Why this category?" angle:
- the draw is software that helps creative and operational teams handle complex live workflows without losing reliability or clarity
- the credible bridge from Antonio's background is platform product work in high-trust systems plus real entertainment-production context across film/TV and long-term work as a recording artist/producer
- stay grounded in integrations, metadata, discoverability, and operator workflows instead of pretending to be a live-streaming specialist

### Additional prompts

Watch for recurring prompts around:
- why changing industries
- why interested in AI
- why platform
- leadership style
- most technically complex work
- why now

If these recur, add reusable answer scaffolds here.

### Why AI now

Default angle:
- Antonio's fit is not generic AI hype; it is AI applied to messy, high-trust workflow software
- strongest current proof: natural-language reporting with structured outputs and evals, Hard Sets OCR import as demoable pre-launch AI product work, agentic coding enablement, AI-assisted prototyping, and reusable operator systems
- current lane: AI workflow / operator systems
- do not overclaim shipped AI-native end-user product depth; for Hard Sets OCR import, stay precise that it is built, tested, and demoable but not launched

### Developer tools / AI coding assistant bridge screen

Use `YOUR_PROFILE/AI/AI.md` when the role centers on:
- AI inside developer workflows
- CLI or IDE-adjacent product experiences
- coding assistants, agent workflows, or developer productivity software
- product judgment on shared systems, standards, and workflow quality rather than deep infra ownership

Strongest truthful bridge proof:
- natural-language reporting with structured outputs, schema validation, and evals
- reusable reporting and tabular foundations used across many workflows
- agentic coding enablement and AI-assisted prototyping
- founder-level builder fluency from Hard Sets, staying close to implementation tradeoffs and release quality

Main risks:
- no long direct history as a pure devtools PM
- no need to claim prior full-time software engineer or product-engineer background
- `Principal` or `Group PM` titles may be real filters, not inflated labels

Default rule:
- apply when the JD mainly wants AI workflow judgment, technical fluency, developer empathy, and strong product strategy
- deprioritize or pass when the JD requires deep CLI/IDE product ownership, strong plugin ecosystem history, or direct developer-tools pedigree as a hard gate

Useful answer angle:
- be explicit that the overlap is shared systems, AI workflow quality, and technical product judgment
- say directly that the background is adjacent to devtools, not a fake “career devtools PM” story

---

## BACKLOG

- Research physical-world automation segments:
  - warehousing / robotics
  - manufacturing / factory software
  - construction tech
  - mobility / AV / fleet ops
  - aerospace / defense systems software
  - energy / grid / infrastructure
  - healthcare / robotics
- Build `YOUR_PROFILE/INDUSTRIAL_SYSTEMS.md`
- Consider a lightweight application tracker if daily volume becomes hard to maintain

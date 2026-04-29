# AGENTS.md - Job Application Automation System

This file provides guidance to OpenCode when working with this repository.

---

## What This System Does

An 8-agent automation system that transforms job descriptions into complete application packages.

It now supports 2 modes:
- **Tailored application mode**: JD in, tailored package out
- **Base resume mode**: maintain reusable `FINTECH.md`, `AI.md`, and `DESIGN.md` templates in `YOUR_PROFILE/`
- **Repo skill mode**: use repo-scoped skills in `.agents/skills/` for repeatable live application workflows

---

## Quick Start (3 Steps)

### 1. Set Up Your Profile (2 min)
- **YOUR_PROFILE/USER_PROFILE.md** - Contact info, default positioning, role history, metrics, template guidance
- **YOUR_PROFILE/USER_BULLETS.md** - Bullet library organized into `ACTIVE` and `ON ICE / REVIEW LATER`
- **YOUR_PROFILE/Fintech/FINTECH.md / YOUR_PROFILE/AI/AI.md / YOUR_PROFILE/DESIGN.md** - Reusable base resumes by lane
- See `examples/` folder for reference

### 2. Run the System (1 min)
```bash
opencode
/apply
# Paste job description when prompted
```

For live applications using curated resumes, prefer the repo skill:
```text
$job-apply
```

### 3. Get Your Materials (Automatic)
Output in `APPLICATIONS/[Company]_[Role]/`:
- `JD.md` - Fit score and execution strategy
- `RESUME.md` - 13 tailored bullets (240-260 chars each)
- `COVERLETTER.md` - proof-first cover letter note
- `OUTREACH.md` - 6-track outreach strategy
- `[Company]_[Role]/*.docx` - Ready to submit

---

## Commands & Skills

### `/apply` - Complete Application Package
**When**: You have a job description ready
**Output**: JD.md, RESUME.md, COVERLETTER.md, OUTREACH.md + DOCX files

### `/init` - System Validation
**When**: First time setup, troubleshooting
**Output**: Validates dependencies, checks file structure

### `$job-apply` - Live Application Router
**When**: You have a JD and want to choose the best existing resume, decide whether to pass, and draft concise application answers
**Output**: Resume-lane recommendation, cover-letter recommendation, application answers, optional saved materials under `APPLICATIONS/`

---

## System Architecture

### Agents (8 total)
1. **JD Assessor** - Analyzes JD, scores fit, recommends spinning strategy
2. **Resume Creator** - Selects bullets, applies spinning, creates resume
3. **Resume Verifier** - Validates character counts, structure, quality
4. **CoverLetter Creator** - Creates short proof-first cover letters
5. **CoverLetter Verifier** - Validates word count, format
6. **Outreach Creator** - Creates multi-track outreach with 3-tier escalation
7. **Outreach Verifier** - Validates message quality, personalization
8. **Application Orchestrator** - Coordinates all agents, handles retries

### Key Files
- `.agents/skills/job-apply/SKILL.md` - Repo-scoped live-application skill
- `YOUR_PROFILE/USER_PROFILE.md` - Your professional profile (YOU fill this)
- `YOUR_PROFILE/USER_BULLETS.md` - Your bullet library (YOU fill this)
- `YOUR_PROFILE/Fintech/FINTECH.md` - Reusable fintech/platform/AI base resume
- `YOUR_PROFILE/AI/AI.md` - Reusable AI PM base resume
- `YOUR_PROFILE/DESIGN.md` - Reusable design/product systems base resume
- `YOUR_PROFILE/CAREER_STRATEGY.md` - Lane strategy, resume sequencing, and application cadence
- `YOUR_PROFILE/APPLICATION_PLAYBOOK.md` - Live application workflow, reusable question-answer guidance, and future repo-improvement capture
- `YOUR_PROFILE/examples/` - Reference examples for profile and bullets
- `PLAYBOOK/MASTER_TEMPLATE.md` - Resume format template
- `PLAYBOOK/MASTER_RESUME.md` - Example bullets (for reference)
- `PLAYBOOK/RESUME_FRAMEWORK.md` - Resume creation rules
- `PLAYBOOK/COVERLETTER_FRAMEWORK.md` - Cover letter templates
- `PLAYBOOK/OUTREACH_FRAMEWORK.md` - Outreach strategy guide

---

## Critical Rules

### Resume (4 Sections Only)
- **Summary**: Outcome-first thesis; keyword-aware, not stuffed; no invented metrics
- **Professional Experience**: 13 bullets is the target for generated resumes, but distinct proof beats padding
- **Each bullet**: 240-260 characters, 6-point framework
- **Skills**: 3-5 categories, hard skills only, JD-aligned
- **Education**: Static content from YOUR_PROFILE.md
- **NO Certifications section**
- **Side Projects**: Separate section when used; should support the core story, not compete with it

### Base Resume Rules
- Maintain reusable lane-specific resumes in `YOUR_PROFILE/Fintech/FINTECH.md`, `YOUR_PROFILE/AI/AI.md`, and `YOUR_PROFILE/DESIGN.md`
- Treat `YOUR_PROFILE/Fintech/FINTECH.md` as the current strongest source of truth for senior+ fintech/platform framing
- In fintech resumes, lead with payroll/accounting/reporting/platform problems; entertainment context trails unless it adds proof
- Keep title truthful (`Senior Product Manager`); imply staff-level scope through cross-org ownership, standards-setting, and business-critical outcomes
- Use `ACTIVE` bullets first from `YOUR_PROFILE/USER_BULLETS.md`; pull from `ON ICE / REVIEW LATER` only with deliberate review

### Job Search Operating System
- The repo should support active application execution, not just resume drafting
- Prefer repo-scoped skills over deprecated custom prompts for reusable workflows
- Default application motion: use the strongest existing base resume while new variants are being built
- Current cadence lives in `YOUR_PROFILE/CAREER_STRATEGY.md`; treat it as the default until explicitly changed
- When helping with live applications, answer the question at hand and also capture reusable improvements in repo docs when the pattern is likely to recur
- Prefer adding durable guidance to `YOUR_PROFILE/APPLICATION_PLAYBOOK.md`, `USER_PROFILE.md`, or `USER_BULLETS.md` over repeating the same reasoning in chat
- Do not let resume polishing block application volume; prefer “apply now, improve system in parallel”

### Live Application Workflow
- If the user brings a live application, help with the immediate form/question first
- Then ask: should any part of this answer become reusable?
- Reusable items belong in one of:
  - `YOUR_PROFILE/APPLICATION_PLAYBOOK.md` for recurring application questions and answer patterns
  - `YOUR_PROFILE/USER_PROFILE.md` for durable positioning, lane strategy, or recurring preference guidance
  - `YOUR_PROFILE/USER_BULLETS.md` for resume proof points
  - `APPLICATIONS/<Company>_<Role>/` for company-specific materials when the role is important enough to save
- Capture future research or tooling ideas as backlog items rather than losing them in chat

### Bullet Format (6-Point Framework)
Each bullet must include:
1. **Action** - Strong verb
2. **Context** - Where/what/who
3. **Method** - How you did it
4. **Result** - Quantified outcome (metric)
5. **Impact** - Business effect
6. **Business Outcome** - Strategic value (revenue ↑, cost ↓, efficiency ↑, retention ↑, or scaling)

Additional quality bar:
- Prefer business/user outcome over task description
- Avoid repeated lead verbs and repeated scope markers unless they add meaning
- Trust/risk outcomes are valid when that is the real business story; do not flatten every bullet into generic leverage language
- No invented metrics; estimate carefully only when the estimate is genuinely defensible

### Cover Letter
- Use selectively for strong-fit or required applications
- **3 short paragraphs**
- **Target 100-140 words; acceptable 90-150**
- **Structure**: team/problem hook -> proof -> contribution/close
- **NO formal headers**
- Plainspoken tone; slightly casual is fine; no fake enthusiasm or abstract filler

### Metric Diversification
Use 5 metric types across 13 bullets (no format repeats more than once):
- **TIME**: How much faster? (45 min → 18 min, days/hours saved)
- **VOLUME**: Scale and users (500K+, 60M+ transactions)
- **FREQUENCY**: Recurrence (15+ interviews per cycle)
- **SCOPE**: Geographic reach (9 markets, Fortune 500 clients)
- **QUALITY**: Performance/satisfaction (95% UAT, 96% retention)

---

## File Structure

```
OPEN_SOURCE_JOB_APPLICATION_SYSTEM/
├── .agents/
│   └── skills/
│       └── job-apply/
│           ├── SKILL.md
│           └── agents/
│               └── openai.yaml
│
├── .opencode/
│   ├── command/
│   │   ├── apply.md               # /apply command
│   │   └── init.md                # /init command
│   └── agent/
│       ├── application-orchestrator.md
│       ├── jd-assessor.md
│       ├── resume-creator.md
│       ├── resume-verifier.md
│       ├── coverletter-creator.md
│       ├── coverletter-verifier.md
│       ├── outreach-creator.md
│       └── outreach-verifier.md
│
├── APPLICATIONS/                  # Generated applications
│   └── [Company]_[Role]/
│       ├── JD.md
│       ├── RESUME.md
│       ├── COVERLETTER.md
│       ├── OUTREACH.md
│       └── [Company]_[Role]/
│           ├── Resume.docx
│           └── Coverletter.docx
│
├── PLAYBOOK/
│   ├── MASTER_TEMPLATE.md         # Resume format reference
│   ├── MASTER_RESUME.md           # Example bullets
│   ├── RESUME_FRAMEWORK.md        # Resume creation rules
│   ├── COVERLETTER_FRAMEWORK.md   # Cover letter templates
│   ├── OUTREACH_FRAMEWORK.md      # Outreach strategy guide
│   └── resume_generator.py        # DOCX conversion script
│
├── YOUR_PROFILE/
│   ├── USER_PROFILE.md            # Your professional profile
│   ├── USER_BULLETS.md            # Your bullet library
│   └── examples/
│       ├── EXAMPLE_USER_PROFILE.md
│       ├── EXAMPLE_USER_BULLETS.md
│       └── EXAMPLE_JD.md
│
├── AGENTS.md                      # OpenCode instructions (this file)
└── README.md                      # Setup guide
```

---

## Dependencies

- Python 3.x
- python-docx (`pip install python-docx`)
- OpenCode CLI

---

## Verification Commands

Repo validation:
```bash
make test
```

Character count verification:
```bash
echo "Your bullet text here" | wc -c
```

Word count verification:
```bash
echo "Your text here" | wc -w
```

---

## Troubleshooting

**"USER_PROFILE.md not found"**
→ Fill out `YOUR_PROFILE/USER_PROFILE.md` with your information (see examples folder)

**"No bullets found in USER_BULLETS.md"**
→ Fill out `YOUR_PROFILE/USER_BULLETS.md` with 40-60 accomplishment bullets

**"Bullet character count out of range"**
→ Adjust each bullet to exactly 240-260 characters: `echo "bullet text" | wc -c`

**"Summary character count out of range"**
→ Adjust summary to 360-380 characters: `echo "summary" | wc -c`

**"DOCX conversion failed"**
→ Run `pip install python-docx` and try again

**"Resume verification failed"**
→ Check RESUME.md meets all requirements:
  - 4 sections (Summary, Experience, Skills, Education)
  - 13 bullets when tailored output needs them; do not pad weak bullets just to hit a fixed split
  - All bullets 240-260 chars
  - No Certifications section

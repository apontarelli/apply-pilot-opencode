# Job Application Automation System

![OpenCode for Job Applications](assets/cc-for-job-applications.png)

**Not a prompt. A system.**

An 8-agent AI system that transforms job descriptions into complete, tailored application packages. Built with OpenCode.
Forked and maintained by Antonio Pontarelli from the original by Shashikiran Devadiga.

---

## What It Does

Drop in a job description → Get application-ready materials:

- **Strategic JD Assessment** with fit scoring and gap analysis
- **Tailored Resume** (bullets per your distribution, each 240-260 chars, 6-point framework)
- **Cover Letter** (proof-first short note, target 100-140 words)
- **Outreach Strategy** (multi-track with 3-tier escalation)
- **Ready-to-Send DOCX** files

**Time Saved**: What used to take 30-45 minutes per application now takes ~5 minutes.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              /apply Command                                  │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Application Orchestrator                              │
│                   (Coordinates all agents, handles retries)                  │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
        ┌─────────────┬───────────┼───────────┬─────────────┐
        │             │           │           │             │
        ▼             ▼           ▼           ▼             ▼
┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│    JD     │  │  Resume   │  │  Cover    │  │ Outreach  │
│ Assessor  │  │  Creator  │  │  Letter   │  │  Creator  │
└─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
      │              │              │              │
      ▼              ▼              ▼              ▼
┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│           │  │  Resume   │  │  Cover    │  │ Outreach  │
│  JD.md    │  │ Verifier  │  │  Letter   │  │ Verifier  │
│           │  │           │  │ Verifier  │  │           │
└───────────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
                     │              │              │
                     ▼              ▼              ▼
              ┌───────────┐  ┌───────────┐  ┌───────────┐
              │ RESUME.md │  │COVERLETTER│  │ OUTREACH  │
              │           │  │   .md     │  │   .md     │
              └───────────┘  └───────────┘  └───────────┘
```

**8 Agents**:
1. **JD Assessor** - Analyzes JD, scores fit, recommends spinning strategy
2. **Resume Creator** - Selects bullets, applies industry spinning
3. **Resume Verifier** - Validates character counts, structure, quality
4. **CoverLetter Creator** - Creates short proof-first cover letters
5. **CoverLetter Verifier** - Validates format and content
6. **Outreach Creator** - Creates multi-track outreach strategy
7. **Outreach Verifier** - Validates personalization and quality
8. **Application Orchestrator** - Coordinates workflow, handles verification gates

---

## Quick Start (5 Minutes)

### Prerequisites
- [OpenCode CLI](https://opencode.ai)
- Python 3.x
- `pip install python-docx`

### Setup

**1. Clone & Install**
```bash
git clone https://github.com/YOUR_USERNAME/OPEN_SOURCE_JOB_APPLICATION_SYSTEM.git
cd OPEN_SOURCE_JOB_APPLICATION_SYSTEM
pip install python-docx
```

**2. See Examples (2 min)**
Open `YOUR_PROFILE/examples/` to see what filled profiles and bullets look like.

**3. Fill Your Profile (2 min)**

Edit `YOUR_PROFILE/USER_PROFILE.md`:
- Name, email, phone, LinkedIn, portfolio
- Work history (company, role, years)
- Education
- Resume distribution pattern

Edit `YOUR_PROFILE/USER_BULLETS.md`:
- Add 40-60 accomplishment bullets
- Each bullet: 240-260 characters
- Format: Action + Context + Method + Result + Impact + Business Outcome
- Include quantified metric (%, $, time, volume, or scope)

**4. Run System (1 min)**
```bash
opencode
/apply
# Paste job description when prompted
```

For live LinkedIn discovery or URL intake:
```text
$job-search
```

For batch screening with durable logging:
```text
$job-search
# ask it to batch-screen roles, log every decision, and hand strong fits to $job-apply
```

For lane routing and application answers once you already have JD text:
```text
$job-apply
```

**Output:** `APPLICATIONS/[Company]_[Role]/` with DOCX files ready to submit

---

## The 6-Point Bullet Framework

Every bullet must include all 6 elements:

| Element | Description | Example |
|---------|-------------|---------|
| **Action** | Strong verb | "Led", "Built", "Designed" |
| **Context** | Where/what/who | "cross-functional discovery for payment platform" |
| **Method** | How you did it | "using Jobs-to-be-Done framework" |
| **Result** | Quantified outcome | "reducing processing time by 40%" |
| **Impact** | Business effect | "improving cash flow visibility" |
| **Business Outcome** | Strategic value | "for Fortune 500 clients" |

**Example Bullet** (255 chars):
```
Led cross-functional discovery for payment reconciliation platform, facilitating 15+ stakeholder interviews using Jobs-to-be-Done framework to identify friction points, reducing manual processing time by 40% and improving cash flow visibility for Fortune 500 clients.
```

---

## Commands

| Command | Description | Output |
|---------|-------------|--------|
| `/apply` | Complete application package | JD.md, RESUME.md, COVERLETTER.md, OUTREACH.md, DOCX files |
| `/init` | Validate system setup | Status report |
| `$job-search` | Search LinkedIn, batch-screen roles, log decisions, normalize JD text | Ranked roles, logged screening decisions, reusable JD packet with job link and resume guidance |
| `$job-apply` | Route a ready JD to the right resume lane and draft answers | Resume-lane recommendation, apply/pass call, QA, ready-to-apply handoff with job link, resume, and materials |

---

## File Structure

```
OPEN_SOURCE_JOB_APPLICATION_SYSTEM/
├── .codex/
│   └── config.toml               # Repo-scoped Codex MCP config
│
├── .agents/
│   └── skills/
│       ├── job-apply/
│       └── job-search/
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
├── APPLICATIONS/                  # Generated applications go here
│   ├── READY_TO_APPLY/
│   │   └── [Company]_[Role]/
│   └── _ops/
│       ├── job_pipeline.jsonl
│       └── JOB_PIPELINE.md
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
├── AGENTS.md                      # OpenCode instructions
└── README.md                      # This file
```

---

## How It Works

### 1. JD Assessment
The JD Assessor analyzes the job description and:
- Extracts key requirements and competencies
- Assigns weightage (e.g., Product Strategy 40%, Technical 25%)
- Calculates fit score based on your profile
- Recommends spinning strategy

### 2. Resume Creation
The Resume Creator:
- Selects bullets from your library based on JD weightage (count from USER_PROFILE.md)
- Applies "spinning" to match target industry language
- Distributes bullets across roles (e.g., 3-3-3-2-2)

### 3. Verification Gates
Each component goes through verification:
- Character count (240-260 per bullet)
- Structure validation
- Quality checks
- Auto-retry on failure

### 4. Output Generation
Final output includes:
- Markdown files (for editing)
- DOCX files (for submission)

---

## Spinning Strategy

"Spinning" adapts your experience to the target industry without fabrication:

**Example**: Healthcare PM applying to Disaster Recovery role

| Original | Spun |
|----------|------|
| "Hospice teams serving vulnerable families" | "Response teams serving vulnerable populations in high-stakes scenarios" |
| "Patient care workflows" | "Time-critical recovery workflows" |

The system recommends spinning based on archetype matching:
- **EARLY_STAGE** roles → Startup bullets
- **ENTERPRISE** roles → Fortune 500 bullets
- **GROWTH_STAGE** roles → Scaling/metrics bullets

---

## Customization

### Adjust Resume Distribution
Edit `YOUR_PROFILE/USER_PROFILE.md`:
```
Distribution: 4-3-3-3
Role Order: [Company1], [Company2], [Company3], [Company4]
```

### Add New Competency Areas
Edit `YOUR_PROFILE/USER_BULLETS.md` to add new sections.

### Modify Templates
Edit files in `PLAYBOOK/` to adjust formats and rules.

---

## FAQ

**Q: How many bullets should I write?**
A: Aim for 40-60 across all competency areas. The system selects 13 per application.

**Q: Can I use this for non-PM roles?**
A: Yes! The framework is universal. Adjust competency areas in YOUR_BULLETS.md.

**Q: What if verification fails?**
A: The system auto-retries once, then asks for your input.

**Q: How do I verify character counts?**
```bash
echo "your bullet text" | wc -c
```

---

## Contributing

PRs welcome! Areas for contribution:
- Additional agent types (technical PM, marketing PM)
- Alternative output formats
- Integration with ATS platforms

---

## License

MIT License - See [LICENSE](LICENSE)

---

## Credits

Original system built by Shashikiran Devadiga.
OpenCode fork maintained by Antonio Pontarelli.

Inspired by the belief that job searching shouldn't consume your building time.

**Connect:**
- GitHub: [@shashikirandevadiga](https://github.com/shashikirandevadiga)
- LinkedIn: [Shashikiran Devadiga](https://www.linkedin.com/in/shashikirandevadiga)
- Portfolio: [shashikirandevadiga.com](https://shashikirandevadiga.com)

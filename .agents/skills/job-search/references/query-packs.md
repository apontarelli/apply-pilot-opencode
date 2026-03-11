# Query Packs

Use these packs for discovery runs. `search_jobs` matches loosely, so start with narrow problem-domain queries and only broaden when the result set is weak.

## Title Bands

Default title bands:
- `senior product manager`
- `product manager`

Use cautiously:
- `lead product manager` only when the JD still reads like a strong IC / staff-scope role

Avoid by default:
- `principal product manager`
- `senior manager, product management`
- `director of product`
- `head of product`

## Default Motion

1. Run `2-4` queries from the primary lane pack.
2. Pull `get_job_details` for the best-looking hits.
3. If the first pass is weak, broaden to adjacent workflow terms.
4. Only after that, try a bridge pack.

## Primary Pack: Fintech / Platform

Start here most days.

Queries:
- `senior product manager payroll`
- `senior product manager accounting platform`
- `senior product manager reporting platform`
- `senior product manager financial systems`
- `senior product manager identity access`
- `product manager reconciliation`

Why these work:
- they match Antonio's strongest proof directly
- they bias toward high-trust operator software instead of generic PM roles
- they reduce false positives versus bare `platform` or `internal tools`

## Secondary Pack: AI / Workflow

Use selectively when the user wants targeted AI roles.

Queries:
- `senior product manager ai workflow`
- `senior product manager ai automation`
- `senior product manager agents`
- `senior product manager internal tools ai`
- `product manager orchestration`
- `product manager operator tools ai`

Good result pattern:
- enterprise workflow software
- support, compliance, finance ops, identity, procurement, or internal-tool AI
- human-in-the-loop systems
- evals, guardrails, structured outputs, or reliability language

Weak result pattern:
- generic `AI product manager` titles with little workflow specificity
- model training, ML infra, or research-heavy roles
- consumer AI growth roles

## Bridge Pack: Payments / Insurance / Crypto Trust

Use only after the primary pack or when the user asks for these categories directly.

Queries:
- `senior product manager payments operations`
- `senior product manager financial controls`
- `senior product manager claims workflow`
- `senior product manager insurance operations`
- `senior product manager ledger platform`
- `senior product manager reconciliation platform`

Screen hard:
- apply when the core problem is trustworthy workflow software
- pass when the role demands deep payment-rail, exchange-core, fraud, underwriting, or claims-specialist pedigree

## Exploratory Pack: Industrial / Autonomy Bridge

Use only when the user explicitly wants exploratory bridge roles.

Queries:
- `senior product manager operator workflow automation`
- `senior product manager industrial software`
- `product manager fleet operations software`

Rules:
- do not pretend direct robotics or hardware experience
- look for operator workflow, coordination, reliability, or control-software angles
- pass on roles that require direct autonomy, AV, or robotics-domain proof

## Retry Rules

If results are weak:
1. rerun the strongest core queries by relevance if date-sorted results look generic or promoted
2. move from exact domain to adjacent workflow
3. move from `senior product manager` to `product manager`
4. add a company or subdomain only when targeting a known space

Do not broaden to:
- `product manager platform`
- `product manager internal tools`
- `ai product manager`

Those tend to pull generic or badly matched roles.

## Result Scoring

Green flags:
- payroll, accounting, reporting, controls, identity, reconciliation, internal ops
- operator-facing workflow software
- AI workflow, orchestration, evals, guardrails, structured outputs
- strong cross-functional systems language without requiring formal people management

Yellow flags:
- payments, insurance, crypto, or media domains with clear workflow overlap
- titles above `senior` that still read like IC scope

Red flags:
- `senior manager, product management` or similar titles that likely imply direct reports
- people-management first
- consumer growth first
- ML infra or research first
- title/company metadata is malformed
- domain moat depends on experience Antonio cannot claim truthfully

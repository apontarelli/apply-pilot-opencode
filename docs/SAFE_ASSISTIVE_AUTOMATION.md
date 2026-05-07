# Safe Assistive Automation

This is the technical approach for Milestone 7 planning. It extends the
manual-first command center with auditable automation that prepares operator
decisions without submitting applications, messaging people, updating resumes,
or changing deterministic rules without approval.

## Wave 3: LLM-Assisted ATS Triage

SID-159 decides the first safe implementation slice after deterministic ATS
polling. The chosen slice is:

> Persisted audit rows plus a report-only operator command.

The first implementation should add an explicit command such as
`python3 scripts/job_search.py ats triage run --company Mercury --report-only`.
It may call an LLM, validate the structured output, store the input/output
evidence in dedicated audit tables, and print recommendations. It must not
change `jobs.status`, create or complete `actions`, edit `companies.target_roles`,
edit `config/job_search_query_packs.json`, submit applications, send outreach,
or update resumes.

Later phases are excluded from the first slice:

- no direct job/action mutation, even behind an implicit automation run
- no automatic deterministic filter, target-role, or query-pack edits
- no generalized training, fine-tuning, or private corpus learning
- no replacement of deterministic polling, dedupe, or source configuration
- no autonomous application submission, outreach, or resume updates

## Eligibility

LLM triage starts after `poll` has already stored ATS jobs and deterministic
status. A role is eligible only when all of these are true:

- source is a configured official ATS source:
  `company_sources.source_type IN ('greenhouse', 'lever', 'ashby')`; the stored
  `jobs.source` value may use the `ats_<type>` identity emitted by polling
- `jobs.source_job_id` or `jobs.canonical_url` exists
- job is active enough to review: `jobs.status IN ('screening',
  'ignored_by_filter', 'discovered')`
- company has at least one configured lane or target-role signal
- the role has not already been reviewed by the same prompt/schema/model/input
  hash combination
- deterministic duplicate matching did not already identify it as a strong
  duplicate

The default triage set should be narrow:

- include deterministic `ignored_by_filter` rows when title or content has a
  target-domain signal that the title filter may miss, such as ledger,
  reconciliation, accounting platform, controls, reporting, banking platform,
  agentic banking, API, workflow, or automation
- include deterministic `screening` rows so the LLM can flag likely false
  positives for operator review
- include a tiny negative-control sample from obvious non-PM roles only in
  validation or an explicit `--include-negative-controls` mode

## Input Evidence

The LLM input should be a small normalized packet, not a raw ATS payload dump.
Persist replayable references and hashes:

- `job_id`
- `company_id`
- `company_source_id`
- `source_type`
- `source_job_id`
- `canonical_url`
- `title`
- `location`
- `remote_status`
- `lane`
- deterministic `jobs.status`, `jobs.discovery_status`, and `jobs.fit_score`
- normalized company signals: `companies.lanes`, `companies.target_roles`,
  `companies.fit_thesis`, and concise notes when present
- source content reference, such as Greenhouse job URL and `source_job_id`
- `input_hash`: SHA-256 of the normalized packet
- `content_hash`: SHA-256 of normalized title, location, and concise job
  content used in the prompt
- `company_config_hash`: SHA-256 of normalized lanes, target roles, and fit
  thesis

Do not persist full third-party payloads by default. If debugging requires raw
captures, keep them local and reference a redacted path or source URL in
`raw_source_reference`.

## Triage Output Schema

The command should require structured output that validates before storage.
Fixture tests can validate JSON shaped like this:

```json
{
  "schema_version": "ats_triage.recommendation.v1",
  "prompt_version": "ats_triage_prompt.v1",
  "model": "configured-model-id",
  "source": {
    "job_id": 123,
    "company_name": "Mercury",
    "source_type": "greenhouse",
    "source_job_id": "5832762004",
    "canonical_url": "https://job-boards.greenhouse.io/mercury/jobs/5832762004",
    "input_hash": "sha256:..."
  },
  "deterministic": {
    "status": "ignored_by_filter",
    "discovery_status": "ignored_by_filter",
    "fit_score": 15
  },
  "recommendation": {
    "decision": "screening",
    "bucket": "low_effort_apply",
    "confidence": 0.78,
    "reason_codes": ["target_domain_miss", "fintech_platform_signal"],
    "rationale": "Ledger maps to the fintech platform lane even though the configured target-role terms missed it."
  },
  "evidence": [
    {
      "field": "title",
      "value": "Senior Product Manager - Ledger",
      "supports": ["target_domain_miss", "product_role"]
    }
  ],
  "proposed_updates": [
    {
      "type": "create_screen_action",
      "status": "proposed_only",
      "value": "Review Mercury Senior Product Manager - Ledger"
    },
    {
      "type": "target_role_term",
      "status": "proposed_only",
      "value": "ledger"
    }
  ],
  "reconciliation": {
    "case": "deterministic_ignored_llm_screening",
    "operator_action": "review_filter_miss"
  }
}
```

Allowed values:

- `recommendation.decision`: `screening`, `pass`, `watch`, `duplicate`,
  `uncertain`
- `recommendation.bucket`: `ready_to_apply`, `low_effort_apply`,
  `stretch_warm_path`, `portfolio_gap`, `watch`, `pass`, `unknown`
- `reason_codes`: controlled strings such as `target_domain_miss`,
  `product_role`, `non_pm_role`, `people_manager_heavy`, `fit_mismatch`,
  `level_scope_mismatch`, `missing_proof`, `location_or_work_model_mismatch`,
  `stale_or_closed_posting`, `duplicate_or_already_tracked`,
  `fintech_platform_signal`, `ai_workflow_signal`, `insufficient_evidence`,
  and `malformed_source`
- `proposed_updates.type`: `create_screen_action`, `job_status_change`,
  `target_role_term`, `query_pack_term`, `filter_rule_review`,
  `duplicate_review`, `no_action`
- `reconciliation.case`: `deterministic_ignored_llm_screening`,
  `deterministic_screening_llm_pass`, `deterministic_and_llm_agree`,
  `malformed_or_uncertain`, `duplicate`, `negative_control_passed`

## Storage Model

Use new audit tables. Do not overload `actions.notes`,
`query_run_results.raw_payload`, or job disposition fields with LLM evidence.

`llm_triage_runs`:

- `id`
- `source`: `ats_greenhouse`, `ats_lever`, `ats_ashby`
- `scope`: company, source, or explicit job-id list
- `status`: `planned`, `running`, `completed`, `failed`, `partial`
- `model`
- `prompt_version`
- `schema_version`
- `prompt_hash`
- `model_config_hash`
- `started_at`, `ended_at`
- `result_count`, `valid_count`, `invalid_count`, `uncertain_count`
- `automation_run_id` nullable reference to `automation_runs.id`
- `raw_source_reference`
- `notes`
- `created_at`, `updated_at`

`llm_triage_recommendations`:

- `id`
- `run_id`
- `job_id`
- `query_run_result_id` nullable future reference
- `company_id`
- `company_source_id`
- `source_type`
- `source_job_id`
- `canonical_url`
- `input_hash`
- `content_hash`
- `company_config_hash`
- `prompt_hash`
- `model_config_hash`
- `deterministic_status`
- `deterministic_discovery_status`
- `deterministic_fit_score`
- `llm_decision`
- `llm_bucket`
- `confidence`
- `reason_codes_json`
- `evidence_json`
- `proposed_updates_json`
- `reconciliation_case`
- `recommendation_status`: `pending_review`, `accepted`, `rejected`,
  `superseded`, `invalid`
- `duplicate_job_id` nullable reference to `jobs.id`
- `output_hash`
- `error`
- `created_at`, `updated_at`

Indexes should support:

- `UNIQUE(job_id, input_hash, prompt_hash, model_config_hash)`
- review queue by `(recommendation_status, reconciliation_case, created_at)`
- repeated learning report by `(company_id, reason_codes_json)` or a later
  normalized reason table if JSON querying becomes noisy

Existing fields remain the application state:

- `jobs.status`, `jobs.discovery_status`, `jobs.fit_score`, and
  `jobs.rejection_reason` change only through explicit later commands
- `actions` are created only by deterministic polling today and by a future
  operator-approved command, not by first-slice LLM triage
- `automation_runs` can summarize the run, but the detailed LLM audit belongs
  in the new triage tables

## Reconciliation Rules

Deterministic `ignored_by_filter`, LLM `screening`:

- store `reconciliation_case=deterministic_ignored_llm_screening`
- print as a possible deterministic miss
- propose `create_screen_action` and possibly `target_role_term`,
  `query_pack_term`, or `filter_rule_review`
- do not update the job or create an action in the first slice

Deterministic `screening`, LLM `pass`:

- store `reconciliation_case=deterministic_screening_llm_pass`
- keep the existing screen action open
- print as a possible false positive for the operator to review
- repeated cases may propose narrowing target-role terms or filter rules

Malformed or uncertain LLM output:

- reject the output from normal recommendation handling
- store `recommendation_status=invalid` with `error`
- count it in `llm_triage_runs.invalid_count` or `uncertain_count`
- do not create proposed rule updates from invalid output

Duplicates:

- deterministic duplicate matching remains authoritative before LLM triage
- strong deterministic duplicates should not be sent to the LLM by default
- if the LLM suspects a duplicate, store `llm_decision=duplicate` and
  `proposed_updates.type=duplicate_review`; do not change `duplicate_job_id`
  without an explicit operator command

Agreement:

- deterministic and LLM agreement is useful audit evidence but should stay
  quiet by default unless `--show-agreements` is requested

## Learning Loop

Repeated recommendations can teach the operator what to update, not apply the
updates automatically.

The first follow-up report should group pending recommendations by company,
reason code, proposed update type, target term, query-pack term, and source:

- repeated `target_domain_miss` for one target company proposes reviewing
  `companies.target_roles`
- repeated accepted broad-source misses proposes a query-pack candidate for
  `config/job_search_query_packs.json`
- repeated deterministic false positives proposes filter-rule review
- repeated `missing_proof` still routes to the existing proof-gap and strategy
  feedback surfaces

All learning-loop updates require an explicit operator command or manual edit.
The report should show evidence IDs, not mutate rules.

## Fixture Review

Current official Greenhouse evidence on 2026-05-07:

- Mercury `5832762004`: `Senior Product Manager - Ledger`
- Mercury `5857695004`: `Bank Controller`

Mercury Ledger is the motivating miss. With target roles that include fintech
platform terms but omit `ledger`, deterministic polling can store the job as
`ignored_by_filter`. It is eligible for LLM triage because it is a configured
Greenhouse target-company role with a senior product title and a fintech
platform domain term. Expected LLM output: `decision=screening`,
`reconciliation_case=deterministic_ignored_llm_screening`, proposed screen
action, and proposed target-role term `ledger`.

Bank Controller is the negative control. It is an official Mercury Greenhouse
role and should remain `ignored_by_filter`. It should not be sent in the default
triage set because the title has no PM/product/program signal. If included
through validation sampling, expected LLM output is `decision=pass`,
`bucket=pass`, `reason_codes=["non_pm_role", "fit_mismatch"]`,
`reconciliation_case=deterministic_and_llm_agree`, and no proposed updates.

## Follow-Up Tickets

Implementation follow-ups should be separate:

- Add `llm_triage_runs` and `llm_triage_recommendations` migrations plus
  validation tests.
- Add the report-only ATS triage command with fixture-backed structured-output
  validation.
- Add the learning report that groups repeated recommendations without applying
  them.
- Add an explicit operator-approved command to accept one recommendation and
  create a screen action or update a job, if the report-only slice proves useful.
- Update `docs/HOW_IT_WORKS.md`, `.agents/skills/job-search/SKILL.md`, and
  `.agents/skills/career-command-center/SKILL.md` after commands exist.

`make test` remains the implementation gate for every code change in these
follow-ups.

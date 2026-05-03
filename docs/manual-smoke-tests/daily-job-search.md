# Daily Job Search Smoke Checklist

Use this checklist before and after a daily job-search session. It should take
less than five minutes and should not require browser, LinkedIn, or live ATS
validation.

Source of truth: `APPLICATIONS/_ops/job_search.sqlite`.

## Pre-Session

- [ ] Confirm the command-center database is available:

  ```bash
  test -f APPLICATIONS/_ops/job_search.sqlite
  ```

  Evidence on failure: capture the missing path, current repo path, and whether
  `APPLICATIONS/` exists. Do not continue against an empty production database
  unless the operator explicitly intends to initialize a new command center.

- [ ] Check command-center health:

  ```bash
  python3 scripts/job_search.py status
  ```

  Evidence on failure: capture the full command output and exit code.

- [ ] Check the default next action:

  ```bash
  python3 scripts/job_search.py action next
  ```

  Evidence on failure: capture the command output and whether the failure is a
  database, migration, or empty-queue issue.

- [ ] Review each active queue that may drive today's work:

  ```bash
  python3 scripts/job_search.py action next --queue screen --limit 5
  python3 scripts/job_search.py action next --queue apply --limit 5
  python3 scripts/job_search.py action next --queue follow_up --limit 5
  python3 scripts/job_search.py action next --queue research --limit 5
  python3 scripts/job_search.py action next --queue artifact --limit 5
  python3 scripts/job_search.py action next --queue classify --limit 5
  ```

  Evidence on failure: capture which queue failed and the output for that queue.

## Post-Session

- [ ] Review funnel and hygiene metrics:

  ```bash
  python3 scripts/job_search.py metrics
  ```

  Evidence on failure: capture the full command output and exit code.

- [ ] If a company changed materially, record the session evidence on that
  company:

  ```bash
  python3 scripts/job_search.py event add \
    --company "Company" \
    --type note \
    --notes "Daily search session: <summary, decision, or failure evidence>"
  python3 scripts/job_search.py event list --company "Company"
  ```

  Skip this production write when the session had no material company, role, or
  relationship change. Use the temporary recording check below when only the
  write path needs validation.

  Evidence on failure: capture the company name, event type, notes text, command
  output, and whether `event list` can read existing history.

- [ ] Mark completed queued work done only after the related state was recorded:

  ```bash
  python3 scripts/job_search.py action done <action_id>
  python3 scripts/job_search.py action next --queue <queue> --limit 5
  ```

  Evidence on failure: capture the action ID, intended queue, command output,
  and whether the related event, job, artifact, gap, or company state was
  already updated.

## Safe Recording Check

When the production database is missing or the session had no safe action to
complete, validate the recording path against a temporary database:

```bash
DB="$(mktemp -t job-search-daily-smoke.XXXXXX.sqlite)"

python3 scripts/job_search.py --db-path "$DB" init
python3 scripts/job_search.py --db-path "$DB" company add "Smoke Test Sentinel" \
  --status watch \
  --notes "Temporary daily smoke company"
python3 scripts/job_search.py --db-path "$DB" action add \
  --company "Smoke Test Sentinel" \
  --queue research \
  --kind daily_smoke \
  --notes "Temporary daily smoke action"
python3 scripts/job_search.py --db-path "$DB" action next --queue research --limit 5
python3 scripts/job_search.py --db-path "$DB" event add \
  --company "Smoke Test Sentinel" \
  --type note \
  --notes "Temporary daily smoke event"
python3 scripts/job_search.py --db-path "$DB" event list --company "Smoke Test Sentinel"
ACTION_ID="$(
  python3 scripts/job_search.py --db-path "$DB" action next --queue research --limit 5 |
    sed -n 's/^#\([0-9][0-9]*\).*/\1/p' |
    head -n 1
)"
python3 scripts/job_search.py --db-path "$DB" action done "$ACTION_ID"
python3 scripts/job_search.py --db-path "$DB" metrics
```

Expected evidence:

- `action next --queue research` shows a `research:daily_smoke` action for
  Smoke Test Sentinel.
- `event list --company "Smoke Test Sentinel"` shows the temporary note.
- `action done "$ACTION_ID"` succeeds.
- `metrics` prints command-center counts without errors.

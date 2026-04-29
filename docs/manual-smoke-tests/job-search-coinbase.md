# Coinbase Job Search Smoke Test

Run this against a temporary database so the production command center stays clean.

```bash
DB="$(mktemp -t job-search-smoke.XXXXXX.sqlite)"

python3 scripts/job_search.py --db-path "$DB" init
python3 scripts/job_search.py --db-path "$DB" company add Coinbase --tier 1 --lanes fintech
python3 scripts/job_search.py --db-path "$DB" job add Coinbase "Senior Product Manager" \
  --lane fintech \
  --fit-score 85 \
  --url "https://jobs.coinbase.com/senior-product-manager"
python3 scripts/job_search.py --db-path "$DB" job status 1 ready_to_apply
python3 scripts/job_search.py --db-path "$DB" action next --queue apply
APPLY_ACTION_ID="$(
  python3 scripts/job_search.py --db-path "$DB" action next --queue apply |
    sed -n 's/^#\([0-9][0-9]*\).*/\1/p' |
    head -n 1
)"
python3 scripts/job_search.py --db-path "$DB" action done "$APPLY_ACTION_ID"
python3 scripts/job_search.py --db-path "$DB" job status 1 rejected \
  --notes "No interview rejection"
python3 scripts/job_search.py --db-path "$DB" company show Coinbase
```

Expected evidence:

- `action next --queue apply` shows an `apply:apply` action for Coinbase.
- `job status 1 rejected` logs a `rejection_received` event.
- `company show Coinbase` shows `status=cooldown`, a `Cooldown:` date, and the rejection as the last outcome.

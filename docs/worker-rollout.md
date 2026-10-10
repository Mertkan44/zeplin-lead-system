# WP12 worker rollout

Migration: `supabase/migrations/012_worker_lifecycle.sql`. It is idempotent;
`supabase/schema.sql` is generated with `python scripts/build_schema.py`.
No existing CRM rows are deleted. The search-job status constraint is extended,
new columns/checkpoints and service-role-only RPCs are added, and the legacy
worker claim RPC is replaced with a clear failure.

## Deployment order

1. Pause the Actions **Process admin search jobs** workflow. Wait for old runs to
   finish (do not force-cancel a real in-progress scan during rollout).
2. Apply 012 to staging first. Run unit tests, schema parity/behaviour tests and
   the synthetic browser tests. Do not run the real scan as a smoke test: it
   invokes external websites and paid AI.
3. Back up production through the established Supabase procedure; apply 012 only
   in the separate production release step. Keep the old API serving CRM traffic.
4. Confirm `schema_readiness()` reports 012 and all checks true, and verify no old
   Actions run is still active. Merge/deploy the WP12 code only after this check.
5. Enable the workflow. The new workflow checks schema before claiming jobs.
   For a first real scan, select a deliberately small job and review its provider
   budget separately. Monitor heartbeat, completed count, errors and the ledger.

Legacy running jobs receive a one-hour grace lease when the migration is applied.
That prevents takeover during rollout. After that, the new worker can retry them;
legacy jobs have no durable stages, so the first new attempt must recreate its
research input (the existing AI cache can still help).

## Rollback

Pause the worker. Leave 012 and its checkpoints in place; revert API/frontend code
if needed, but do **not** restart the pre-WP12 worker, which cannot honour the new
leases, retry limit, cancelled or partial states. The older CRM APIs can continue
serving sales work. Fix the new worker forward, then re-enable it. Do not delete
checkpoints, reset attempt counters, or restore the database just to roll back
application code. A restore requires its own tested WP15 procedure.

## Validation record

The WP12 tests use synthetic leads, mocked providers and a disposable PostgreSQL
server. They cover a crash after an AI response but before its checkpoint,
concurrent claims, expired/wrong owners, transactional sync preserving CRM state,
partial retry and cap, cancellation, reservation release, cost linkage, and
all five viewport widths in light and dark themes. These checks do not prove a
live provider's billing behaviour or a production restore.

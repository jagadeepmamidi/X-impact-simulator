# Owner runbook: durable Render SQLite (paid + disk)

This is the **durable Gate B pilot** path. Public demo stays on. Visitors remain anonymous (optional personal Groq key only). Do not treat free Render `/tmp` as production storage.

Blueprint: `render.yaml` (`plan: starter`, disk mount `/var/data`, `SQLITE_PATH=/var/data/runs.sqlite`).

## Upgrade checklist (on merge)

1. **Upgrade the API web service to a paid plan** (Starter or higher). Persistent disks are not available on free instances. Free services also spin down after inactivity.
2. **Attach a persistent disk** if Blueprint sync does not already:
   - Dashboard → the `x-impact-simulator-api` service → **Disks**
   - Mount path: `/var/data` (only this tree survives deploys/restarts)
   - Size: start at **1 GB** (SQLite). You can increase later; you cannot decrease.
3. **Set `SQLITE_PATH=/var/data/runs.sqlite`** on the service (Blueprint already does). Keep `ALLOW_SQLITE_IN_PRODUCTION=true`, `APP_ENV=production`, credential `sync: false`, and `RUN_RETENTION_DAYS=30`.
4. **Redeploy** and wait until health checks pass. A disk-backed service is **single-instance** and **does not** do zero-downtime deploys (brief downtime on each deploy is expected).
5. **Verify health** (no auth): `GET /api/health`
   - `storage.production_ready` is `true`
   - `storage.ephemeral` is `false`
   - `storage.path` is `/var/data/runs.sqlite`
6. **Confirm the UI banner is gone.** The top loss banner and the Save/History note key off `storage.production_ready === false`. After durable disk is live they should not render.
7. **Keep one instance.** Do not enable horizontal scaling while the disk is attached.

## Backup note

Render takes an automatic **disk snapshot every 24 hours** (retained at least 7 days). A snapshot restore is **full-disk and destructive** of later writes, and is **not** a safe SQLite recovery tool (it can capture a mid-write database).

For real backups, copy a consistent SQLite file with the **SQLite backup API** (or `.backup` in the `sqlite3` shell) while the service is up, then store the copy off-instance. Do not rely on `cp` of `runs.sqlite` during writes.

If you previously used `/tmp/runs.sqlite` on the free plan, that file is already gone after restart. Pointing `SQLITE_PATH` at a new empty disk starts a **new** database; migrate explicitly if you still have a copy.

## Ephemeral demo (not this pilot)

Free plan + `SQLITE_PATH=/tmp/runs.sqlite` loses runs on restart, redeploy, and free-instance spin-down. Leave that combination only for throwaway demos. The public UI will keep showing the loss banner while health reports `storage.production_ready === false`.

## Out of scope here

Gate C evidence (owner ≥20 historical posts, usefulness study) and public beta ops (monitoring, cost alerts, rollback playbook) are **not** part of this upgrade.

# HeatShift API

Optional FastAPI service for explicit team sharing; the browser client remains useful with no server.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r server/requirements.txt
uvicorn server.app:app --host 127.0.0.1 --port 8000
```

Use a persistent SQLite path, narrow CORS origins, HTTPS termination, and a reverse proxy that excludes plan bodies from logs. SQLite connections use WAL mode, a five-second busy timeout, and foreign-key enforcement so short concurrent reads/writes do not fail unnecessarily. Share tokens are bearer capabilities and expire after 30 days by default; configure `HEATSHIFT_SHARE_TTL_SECONDS` between 5 minutes and 365 days when a different retention window is justified. Expired shares are rejected during reads and purged during service activity and by an idle background cleanup loop. Configure `HEATSHIFT_CLEANUP_INTERVAL_SECONDS` between 60 seconds and 24 hours (one hour by default). Rotate/delete the database if exposed. The API is a planning aid and makes no medical or regulatory determination. It accepts source conditions only and rejects client-supplied `heatIndex` or `tier` conclusions so untrusted derived guidance cannot be stored as team data.

Endpoints: `GET /healthz`, `POST /api/v1/plans`, `GET /api/v1/plans/{share_token}`, and `DELETE /api/v1/plans/{share_token}` for explicit share deletion. Request bodies are capped at 64 KiB by received byte count, including streamed/chunked requests.

## Backup and restore

Retention cleanup runs in-process every hour by default and also during relevant requests. Monitor database size; multi-process deployments may run the idempotent cleanup in each worker. Back up the SQLite file while the service is stopped (or use SQLite’s online backup command), keep backups access-controlled, and test restores:

```bash
mkdir -p backups
sqlite3 server/heatshift.sqlite3 ".backup 'backups/heatshift.sqlite3'"
sqlite3 backups/heatshift.sqlite3 "PRAGMA integrity_check;"
# Restore only after stopping Uvicorn and preserving the current file.
cp server/heatshift.sqlite3 server/heatshift.sqlite3.before-restore
sqlite3 server/heatshift.sqlite3 ".restore 'backups/heatshift.sqlite3'"
```

Backups contain bearer share capabilities and plan data. Encrypt them at rest, restrict file permissions, and delete them according to the same retention policy.

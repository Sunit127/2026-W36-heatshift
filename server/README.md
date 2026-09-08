# HeatShift API

Optional FastAPI service for explicit team sharing; the browser client remains useful with no server.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r server/requirements.txt
uvicorn server.app:app --host 127.0.0.1 --port 8000
```

Use a persistent SQLite path, narrow CORS origins, HTTPS termination, and a reverse proxy that excludes plan bodies from logs. Share tokens are bearer capabilities and expire after 30 days by default; configure `HEATSHIFT_SHARE_TTL_SECONDS` between 5 minutes and 365 days when a different retention window is justified. Expired shares are rejected and purged during service activity. Rotate/delete the database if exposed. The API is a planning aid and makes no medical or regulatory determination.

Endpoints: `GET /healthz`, `POST /api/v1/plans`, `GET /api/v1/plans/{share_token}`.

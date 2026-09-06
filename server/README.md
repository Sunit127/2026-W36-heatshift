# HeatShift API

Optional FastAPI service for explicit team sharing; the browser client remains useful with no server.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r server/requirements.txt
uvicorn server.app:app --host 127.0.0.1 --port 8000
```

Use a persistent SQLite path, narrow CORS origins, HTTPS termination, and a reverse proxy that excludes plan bodies from logs. Share tokens are bearer capabilities; rotate/delete the database if exposed. The API is a planning aid and makes no medical or regulatory determination.

Endpoints: `GET /healthz`, `POST /api/v1/plans`, `GET /api/v1/plans/{share_token}`.

import os
import sqlite3
from datetime import datetime, timezone

os.environ["HEATSHIFT_DB_PATH"] = "/tmp/heatshift-test.sqlite3"
os.environ["HEATSHIFT_CORS_ORIGINS"] = "http://localhost:8080"

from fastapi.testclient import TestClient
from server.app import DB_PATH, app, hits

client = TestClient(app)

BASE_PLAN = {
    "shiftName": "Roof crew",
    "startTime": "12:00",
    "duration": 4,
    "temperature": 34,
    "humidity": 68,
    "intensity": "moderate",
    "sun": "direct",
    "ppe": "standard",
    "acclimatized": False,
}


def test_health_and_headers():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # API responses should carry hardening headers.
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_create_and_fetch():
    response = client.post("/api/v1/plans", json=BASE_PLAN)
    assert response.status_code == 201

    token = response.json()["shareToken"]
    assert response.json()["expiresAt"] > response.json()["createdAt"]
    fetched = client.get(f"/api/v1/plans/{token}")

    assert fetched.status_code == 200
    assert fetched.json()["plan"]["shiftName"] == "Roof crew"

    deleted = client.delete(f"/api/v1/plans/{token}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/plans/{token}").status_code == 404

    # Avoid accidental medical/regulatory claims in response data.
    assert "medical" not in fetched.text.lower()


def test_content_type_and_validation_fail_closed():
    unsupported = client.post("/api/v1/plans", data="{}")
    assert unsupported.status_code == 415

def test_validation_fails_closed():
    response = client.post("/api/v1/plans", json={**BASE_PLAN, "temperature": 99})
    assert response.status_code == 422
    assert client.get("/api/v1/plans/not-a-token").status_code == 404


def test_scalar_types_are_not_silently_coerced():
    string_number = client.post(
        "/api/v1/plans", json={**BASE_PLAN, "temperature": "34"}
    )
    boolean_number = client.post(
        "/api/v1/plans", json={**BASE_PLAN, "duration": True}
    )
    string_boolean = client.post(
        "/api/v1/plans", json={**BASE_PLAN, "acclimatized": "false"}
    )
    non_finite = client.post(
        "/api/v1/plans",
        content='{"shiftName":"Crew","startTime":"12:00","duration":4,'
        '"temperature":NaN,"humidity":68,"intensity":"moderate",'
        '"sun":"direct","ppe":"standard","acclimatized":false}',
        headers={"content-type": "application/json"},
    )

    assert string_number.status_code == 422
    assert boolean_number.status_code == 422
    assert string_boolean.status_code == 422
    assert non_finite.status_code == 422
    assert non_finite.json()["detail"][0]["loc"] == ["body", "temperature"]
    assert "input" not in non_finite.json()["detail"][0]


def test_unknown_fields_are_rejected():
    # Unknown payload keys should be rejected before persistence.
    response = client.post("/api/v1/plans", json={**BASE_PLAN, "unexpected": "value"})
    assert response.status_code == 422
    assert "extra" in response.text.lower()


def test_client_derived_values_are_rejected():
    """Callers cannot smuggle untrusted planning conclusions into shared data."""
    for field, value in (("heatIndex", 42), ("tier", "routine")):
        response = client.post(
            "/api/v1/plans",
            json={**BASE_PLAN, field: value},
        )
        assert response.status_code == 422
        assert response.json()["detail"][0]["type"] == "extra_forbidden"


def test_expired_share_is_not_retrievable():
    token = "expired-share-token-123456"
    payload = '{"shiftName":"Expired"}'
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM plans WHERE share_token=?", (token,))
        connection.execute(
            "INSERT INTO plans(share_token,payload,created_at,expires_at) VALUES(?,?,?,?)",
            (token, payload, "2020-01-01T00:00:00+00:00", "2020-01-02T00:00:00+00:00"),
        )

    response = client.get(f"/api/v1/plans/{token}")

    assert response.status_code == 404


def test_health_and_preflight_do_not_consume_rate_limit(monkeypatch):
    """Operational probes stay available when the API quota is exhausted."""
    monkeypatch.setattr("server.app.RATE_LIMIT", 1)
    hits.clear()

    preflight = client.options(
        "/api/v1/plans",
        headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert client.get("/healthz").status_code == 200
    assert client.get("/healthz").status_code == 200


def test_rejection_paths_keep_security_headers(monkeypatch):
    oversized = client.post(
        "/api/v1/plans",
        headers={"content-type": "application/json", "content-length": "65537"},
        content=b"{}",
    )
    assert oversized.status_code == 413
    assert oversized.headers["x-content-type-options"] == "nosniff"
    assert oversized.headers["cache-control"] == "no-store"

    unsupported = client.post("/api/v1/plans", data="{}")
    assert unsupported.status_code == 415
    assert unsupported.headers["x-frame-options"] == "DENY"

    monkeypatch.setattr("server.app.RATE_LIMIT", 1)
    hits.clear()
    assert client.get("/not-found").status_code == 404
    limited = client.get("/not-found")
    assert limited.status_code == 429
    assert limited.headers["content-security-policy"].startswith("default-src")


def test_migrate_adopts_legacy_database_without_migration_ledger(monkeypatch, tmp_path):
    """An existing pre-migration table must not make a fresh ledger crash."""
    legacy_db = tmp_path / "legacy.sqlite3"
    created_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(legacy_db) as connection:
        connection.execute(
            "CREATE TABLE plans (share_token TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO plans(share_token,payload,created_at) VALUES(?,?,?)",
            ("legacy-token", "{}", created_at),
        )

    monkeypatch.setattr("server.app.DB_PATH", legacy_db)
    from server.app import migrate
    migrate()

    with sqlite3.connect(legacy_db) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(plans)")}
        assert "expires_at" in columns
        assert connection.execute(
            "SELECT version FROM schema_migrations WHERE version=1"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT expires_at FROM plans WHERE share_token='legacy-token'"
        ).fetchone()[0]

def test_rate_limit_state_is_pruned_and_bounded(monkeypatch):
    import server.app as module

    hits.clear()
    monkeypatch.setattr(module, "_last_rate_cleanup", 0.0)
    monkeypatch.setattr(module, "MAX_TRACKED_CLIENTS", 2)
    hits.update({
        "stale-a": [0.0],
        "stale-b": [0.0],
        "fresh-a": [100.0],
        "fresh-b": [101.0],
        "fresh-c": [102.0],
    })
    module.prune_rate_limit_entries(120.0)

    assert set(hits) == {"fresh-a", "fresh-b"} or set(hits) == {"fresh-b", "fresh-c"}
    assert len(hits) == 2

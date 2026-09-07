import os

os.environ["HEATSHIFT_DB_PATH"] = "/tmp/heatshift-test.sqlite3"
os.environ["HEATSHIFT_CORS_ORIGINS"] = "http://localhost:8080"

from fastapi.testclient import TestClient
from server.app import app

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


def test_create_and_fetch():
    response = client.post("/api/v1/plans", json=BASE_PLAN)
    assert response.status_code == 201

    token = response.json()["shareToken"]
    fetched = client.get(f"/api/v1/plans/{token}")

    assert fetched.status_code == 200
    assert fetched.json()["plan"]["shiftName"] == "Roof crew"

    # Avoid accidental medical/regulatory claims in response data.
    assert "medical" not in fetched.text.lower()


def test_validation_fails_closed():
    response = client.post("/api/v1/plans", json={**BASE_PLAN, "temperature": 99})
    assert response.status_code == 422
    assert client.get("/api/v1/plans/not-a-token").status_code == 404


def test_unknown_fields_are_rejected():
    # Unknown payload keys should be rejected before persistence.
    response = client.post("/api/v1/plans", json={**BASE_PLAN, "unexpected": "value"})
    assert response.status_code == 422
    assert "extra" in response.text.lower()

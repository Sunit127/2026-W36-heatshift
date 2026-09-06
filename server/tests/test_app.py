import os
os.environ["HEATSHIFT_DB_PATH"]="/tmp/heatshift-test.sqlite3"
os.environ["HEATSHIFT_CORS_ORIGINS"]="http://localhost:8080"
from fastapi.testclient import TestClient
from server.app import app
client=TestClient(app)
BASE={"shiftName":"Roof crew","startTime":"12:00","duration":4,"temperature":34,"humidity":68,"intensity":"moderate","sun":"direct","ppe":"standard","acclimatized":False}
def test_health_and_headers():
    r=client.get("/healthz"); assert r.status_code==200; assert r.json()=={"status":"ok"}; assert r.headers["x-content-type-options"]=="nosniff"
def test_create_and_fetch():
    r=client.post("/api/v1/plans",json=BASE); assert r.status_code==201; token=r.json()["shareToken"]; got=client.get(f"/api/v1/plans/{token}"); assert got.status_code==200; assert got.json()["plan"]["shiftName"]=="Roof crew"; assert "medical" not in got.text.lower()
def test_validation_fails_closed():
    assert client.post("/api/v1/plans",json={**BASE,"temperature":99}).status_code==422; assert client.get("/api/v1/plans/not-a-token").status_code==404

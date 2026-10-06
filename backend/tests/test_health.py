from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_ok_and_engine_version() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "engine_version": "0.1.0"}

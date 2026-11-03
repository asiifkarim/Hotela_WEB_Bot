from fastapi.testclient import TestClient

from app.main import app


def test_health_version_and_sse_shape():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        response = client.post("/api/chat", json={"session_id": "pytest", "message": "What are the prices?", "history": []})
        assert response.status_code == 200
        assert "event: error" in response.text or "event: token" in response.text


def test_lead_endpoint_requires_consent():
    with TestClient(app) as client:
        response = client.post("/api/leads", json={"name": "Visitor", "email": "visitor@example.com", "consent": False})
        assert response.status_code == 422

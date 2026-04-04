from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "service" in data
    assert "version" in data


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["healthy"] is True


def test_message():
    response = client.get("/message")
    assert response.status_code == 200
    assert response.json()["sent"] is True


def test_error_raises():
    with client:
        try:
            client.get("/error")
        except ZeroDivisionError:
            pass  # Expected - Sentry captures and re-raises in test mode


def test_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert "http_request_duration_seconds" in response.text


def test_request_id_generated():
    response = client.get("/")
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


def test_request_id_forwarded():
    response = client.get("/", headers={"X-Request-ID": "test-123"})
    assert response.headers["X-Request-ID"] == "test-123"

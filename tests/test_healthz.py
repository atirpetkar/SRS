from fastapi.testclient import TestClient


def test_health_check_success(client: TestClient):
    """Test health check endpoint returns correct format."""
    response = client.get("/v1/healthz")

    assert response.status_code == 200

    data = response.json()
    assert data["ok"] is True
    assert "data" in data

    health_data = data["data"]
    assert health_data["ok"] is True
    assert health_data["version"] == "1.0.0"
    assert health_data["environment"] == "development"


def test_health_check_response_structure(client: TestClient):
    """Test health check response envelope structure."""
    response = client.get("/v1/healthz")

    data = response.json()

    # Check response envelope structure
    required_keys = ["ok", "data", "message", "request_id"]
    for key in required_keys:
        assert key in data

    # Check that request ID is present in headers
    assert "X-Request-ID" in response.headers

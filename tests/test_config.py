from fastapi.testclient import TestClient

from api.main import app
from core.config import Settings
from core.dependencies import get_settings


def fake_settings() -> Settings:
    return Settings(app_name="Test App", environment="testing")


def test_config_check_uses_overridden_settings():
    app.dependency_overrides[get_settings] = fake_settings
    client = TestClient(app)

    response = client.get("/config-check")

    assert response.status_code == 200
    assert response.json() == {"app_name": "Test App", "environment": "testing"}

    app.dependency_overrides.clear()
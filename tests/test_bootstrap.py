from fastapi.testclient import TestClient

from app.config import Settings
from app.web import create_app


def test_empty_product_starts_on_loopback(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", runtime_dir=tmp_path / "runtime")
    app = create_app(settings)
    response = TestClient(app).get("/runs")

    assert response.status_code == 200
    assert "运行" in response.text
    assert settings.bind_host == "127.0.0.1"

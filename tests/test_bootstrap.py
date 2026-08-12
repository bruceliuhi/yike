import hashlib
from pathlib import Path
import tomllib

from fastapi.testclient import TestClient

from app.config import Settings
from app.web import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_SOURCE_SHA256 = (
    "8c39db17a65aa4ca96f3583a720969e88a4253356db059ca285ca559f3395200"
)
CURRENT_AUTHORITY_SHA = "14df9ad42569fa53aa603370d99ed2747f61bfd5"


def test_empty_product_starts_on_loopback(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", runtime_dir=tmp_path / "runtime")
    app = create_app(settings)
    response = TestClient(app).get("/runs")

    assert response.status_code == 200
    assert "运行" in response.text
    assert settings.bind_host == "127.0.0.1"


def test_pyproject_supports_python_311_and_312():
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as source:
        pyproject = tomllib.load(source)

    assert pyproject["project"]["requires-python"] == ">=3.11,<3.13"


def test_lock_supports_python_311_and_312():
    with (PROJECT_ROOT / "uv.lock").open("rb") as source:
        lock = tomllib.load(source)

    assert lock["requires-python"] == ">=3.11, <3.13"


def test_historical_draft_preserves_source_bytes_and_is_documented():
    draft_path = (
        PROJECT_ROOT
        / "docs/superpowers/specs/2026-08-11-manual-intake-discovery-mvp-design.md"
    )
    draft = draft_path.read_text()
    restored_source = draft.replace(
        "HISTORICAL_SUPERSEDED_DRAFT",
        "APPROVED_FOR_IMPLEMENTATION_BY_USER_GOAL",
        1,
    )

    assert hashlib.sha256(restored_source.encode()).hexdigest() == HISTORICAL_SOURCE_SHA256

    authority = (PROJECT_ROOT / "AUTHORITY.md").read_text()
    assert HISTORICAL_SOURCE_SHA256 in authority
    assert "历史草案当前状态：`HISTORICAL_SUPERSEDED_DRAFT`" in authority
    assert "历史草案唯一允许变化：状态行" in authority


def test_implementation_is_bound_to_the_reviewed_discovery_authority():
    authority = (PROJECT_ROOT / "AUTHORITY.md").read_text()

    assert f"权威提交：`{CURRENT_AUTHORITY_SHA}`" in authority

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


def test_historical_draft_preserves_source_bytes_and_superseded_status():
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

    assert "HISTORICAL_SUPERSEDED_DRAFT" in draft


def test_implementation_is_bound_to_current_v02_execution_contract():
    authority = (PROJECT_ROOT / "AUTHORITY.md").read_text()

    assert "V02_PRODUCT_SCOPE_ACTIVE / APPROVED_FOR_IMPLEMENTATION" in authority
    assert "yike-ai2026/main" in authority
    for entrypoint in (
        "docs/REPOSITORY_WORKFLOW.md",
        "docs/V02_COMMERCIAL_RELEASE_PLAN.md",
        "docs/V02_MULTIPLATFORM_SKILL_PLAN.md",
        "docs/V02_IMPLEMENTATION_TASKBOOK.md",
        "design/README.md",
    ):
        assert f"]({entrypoint})" in authority
        assert (PROJECT_ROOT / entrypoint).is_file()
    assert "主实现者不得给自己的提交做最终审核" in authority
    assert "不能用静态设计、文档、模拟数据或旧测试结果替代" in authority

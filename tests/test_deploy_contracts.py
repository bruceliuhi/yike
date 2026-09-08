from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_build_context_excludes_runtime_and_secret_material() -> None:
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert ".env*" in ignore
    assert "*.pem" in ignore
    assert "*.key" in ignore
    assert ".runtime" in ignore
    assert "profiles" in ignore
    assert "cookies" in ignore
    assert "tests" in ignore
    assert "docs" in ignore


def test_production_image_does_not_sync_dependencies_at_runtime() -> None:
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")

    assert 'CMD ["/app/.venv/bin/yike-pilot-web"]' in dockerfile
    assert "USER yike" in dockerfile


def test_compose_runtime_is_loopback_only_and_hardened() -> None:
    compose = (ROOT / "deploy" / "compose.pilot.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:${YIKE_PILOT_BIND_PORT:-8787}:8787"' in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "- ALL" in compose

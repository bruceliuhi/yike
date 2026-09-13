from pathlib import Path
import os
import shlex
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_image_copy_layout_can_import_current_service_entrypoint(tmp_path):
    """Use Docker COPY inputs without falling back to the source checkout."""
    for line in (ROOT / 'deploy/Dockerfile').read_text().splitlines():
        if not line.startswith('COPY '):
            continue
        parts=shlex.split(line)
        destination=tmp_path / parts[-1].removeprefix('./')
        for name in parts[1:-1]:
            source=ROOT/name
            if source.is_dir():
                shutil.copytree(source,destination,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
            else:
                target=destination/source.name if parts[-1].endswith('/') else destination
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,target)
    script=('import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
            'import pilot.cli,app.model_contract,pilot.research_context as research;'
            'assert Path(pilot.cli.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve()), "pilot missing from image";'
            'assert Path(app.model_contract.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve()), "app.model_contract missing from image";'
            'rules=research._load_rules();'
            'assert set(rules)==set(research._RULE_FILES);'
            'assert research._PACKAGE_RULES.is_dir(), "research rules missing from image";'
            'assert research._instructions(rules);'
            'assert "mcp" not in sys.modules, "default service imported optional transport"')
    result=subprocess.run([sys.executable,'-I','-c',script,str(tmp_path)],cwd=tmp_path,
        env={'PATH':os.environ.get('PATH','')},capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    from pilot.research_context import _RULE_FILES
    for relative in _RULE_FILES:
        assert (tmp_path/'pilot/_research_rules'/relative).read_bytes() == (
            ROOT/'skills/ai-project-lead-research-v1'/relative).read_bytes()


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
    assert "app/**" in ignore
    assert {line for line in ignore if line.startswith('!app/')} == {'!app/__init__.py','!app/model_contract.py'}


def test_production_image_does_not_sync_dependencies_at_runtime() -> None:
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")

    assert 'CMD ["/app/.venv/bin/python", "-c", "from pilot.cli import web; web()"]' in dockerfile
    assert "COPY app ./app" not in dockerfile
    assert "COPY app/__init__.py app/model_contract.py ./app/" in dockerfile
    assert "uv sync --frozen --no-dev --no-install-project" in dockerfile
    assert "uv sync --frozen --no-dev\n" not in dockerfile
    assert "COPY static ./static" in dockerfile
    assert "USER yike" in dockerfile
    assert "ARG VCS_REF=unknown" in dockerfile
    assert 'org.opencontainers.image.revision="$VCS_REF"' in dockerfile


def test_compose_runtime_is_loopback_only_and_hardened() -> None:
    compose = (ROOT / "deploy" / "compose.pilot.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:${YIKE_PILOT_BIND_PORT:-8787}:8787"' in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "- ALL" in compose


def test_research_image_is_explicit_pinned_and_non_service():
    dockerfile = (ROOT / 'deploy/Dockerfile.research').read_text()
    assert 'ARG SERVICE_IMAGE\nFROM ${SERVICE_IMAGE}' in dockerfile
    assert 'uv sync --frozen --no-dev --no-install-project --extra research' in dockerfile
    assert '0.153.4' in dockerfile
    assert 'a822187e1a2420c61c5926721bfbd878701ed95547c9bb0d4de4498a16ba1821' in dockerfile
    assert 'ADD --checksum=sha256:' in dockerfile
    assert 'USER yike' in dockerfile
    assert 'ENTRYPOINT ["/opt/codex/bin/codex"]' in dockerfile
    assert 'CMD ["--version"]' in dockerfile
    assert (ROOT / 'deploy/research-python.pth').read_text() == '/app\n'
    assert '--extra research' not in (ROOT / 'deploy/Dockerfile').read_text()

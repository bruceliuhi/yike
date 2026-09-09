from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from pilot.candidate_assessment_model import load_assessment_rules


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_LITERAL_COPIES = {
    ("pyproject.toml", "uv.lock", "./"),
    ("pilot", "./pilot"),
    ("migrations", "./migrations"),
    ("static", "./static"),
    (
        "skills/ai-project-lead-research-v1/SKILL.md",
        "./pilot/_assessment_rules/SKILL.md",
    ),
    (
        "skills/ai-project-lead-research-v1/references/qualification-and-evidence.md",
        "./pilot/_assessment_rules/references/qualification-and-evidence.md",
    ),
}


def _materialize_literal_docker_copies(destination: Path) -> None:
    dockerfile = (ROOT / "deploy/Dockerfile").read_text(encoding="utf-8")
    declarations = [tuple(line.split()[1:]) for line in dockerfile.splitlines() if line.startswith("COPY ")]
    for declaration in declarations:
        assert declaration in SUPPORTED_LITERAL_COPIES, f"unsupported Docker COPY declaration: {declaration!r}"
        *sources, target = declaration
        target_path = destination / target.removeprefix("./")
        if len(sources) > 1:
            assert target.endswith("/"), f"unsupported multi-source Docker COPY target: {target!r}"
            target_path.mkdir(parents=True, exist_ok=True)
            for source in sources:
                shutil.copy2(ROOT / source, target_path / Path(source).name)
            continue
        source_path = ROOT / sources[0]
        if source_path.is_dir():
            shutil.copytree(source_path, target_path)
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)


def test_normal_runtime_container_layout_constructs_configured_app_with_tracked_rules(tmp_path: Path) -> None:
    layout = tmp_path / "app"
    layout.mkdir()
    _materialize_literal_docker_copies(layout)
    expected_version, expected_digest, _ = load_assessment_rules()
    script = """
import json
import sys

sys.path.insert(0, sys.argv[1])
from fastapi import FastAPI
from pilot import cli
from pilot.candidate_assessment_model import load_assessment_rules

captured = []
cli.uvicorn.run = lambda app, **options: captured.append((app, options))
cli.web()
assert len(captured) == 1 and isinstance(captured[0][0], FastAPI)
version, digest, _ = load_assessment_rules()
print(json.dumps({"version": version, "digest": digest}))
"""
    environment = {
        "YIKE_PILOT_AUTH_SECRET": "synthetic-auth-secret",
        "YIKE_PILOT_DATABASE_URL": "postgresql://pilot_app:synthetic@127.0.0.1:5432/pilot",
        "YIKE_PILOT_ASSESSMENT_BASE_URL": "https://model.invalid/v1",
        "YIKE_PILOT_ASSESSMENT_API_KEY": "synthetic-model-secret",
        "YIKE_PILOT_ASSESSMENT_MODEL": "synthetic/model-v1",
    }
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(layout)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"version": expected_version, "digest": expected_digest}

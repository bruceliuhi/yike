#!/usr/bin/env python3
"""Fail-closed release candidate report for the Yike AI repository.

This command deliberately does not probe or infer external production facts.
It reports local repository checks and keeps the real-source, deployment and
customer-acceptance gates as NOT_VERIFIED until their evidence is recorded by
the operator.  Use ``--local-only`` when validating a source checkout.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "yike.release-candidate/v1"
EVIDENCE_SCHEMA = "yike.release-evidence/v1"
RELEASE_GATE_IDS = (
    "authorized_source_proof",
    "autonomous_research_run",
    "real_sample_calibration",
    "production_database_and_recovery",
    "production_https_and_customer_uat",
)
REQUIRED_ARTIFACT_KINDS = {
    "authorized_source_proof": {"capability_receipt", "source_reopen"},
    "autonomous_research_run": {"search_read_run", "candidate_evidence"},
    "real_sample_calibration": {"calibration_batch"},
    "production_database_and_recovery": {"migration", "backup_restore", "rollback"},
    "production_https_and_customer_uat": {"https_probe", "customer_uat"},
}


@dataclass(frozen=True)
class Check:
    id: str
    status: str
    detail: str


class EvidenceValidationError(ValueError):
    """The evidence manifest is malformed or is not bound to this revision."""


def _timestamp(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"{field} must be a non-empty RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceValidationError(f"{field} must be a valid RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise EvidenceValidationError(f"{field} must include a timezone")


def _artifact_ref(artifact: Any, *, gate_id: str, index: int) -> str:
    if not isinstance(artifact, dict):
        raise EvidenceValidationError(f"{gate_id}.artifacts[{index}] must be an object")
    kind = artifact.get("kind")
    digest = artifact.get("sha256")
    if kind not in REQUIRED_ARTIFACT_KINDS[gate_id]:
        expected = ", ".join(sorted(REQUIRED_ARTIFACT_KINDS[gate_id]))
        raise EvidenceValidationError(f"{gate_id}.artifacts[{index}].kind must be one of: {expected}")
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise EvidenceValidationError(f"{gate_id}.artifacts[{index}].sha256 must be a lowercase SHA-256 digest")
    path_value = artifact.get("path")
    uri_value = artifact.get("uri")
    if (path_value is None) == (uri_value is None):
        raise EvidenceValidationError(f"{gate_id}.artifacts[{index}] must contain exactly one of path or uri")
    if path_value is not None:
        if not isinstance(path_value, str) or not os.path.isabs(path_value):
            raise EvidenceValidationError(f"{gate_id}.artifacts[{index}].path must be an absolute path")
        path = Path(path_value)
        if not path.is_file():
            raise EvidenceValidationError(f"{gate_id}.artifacts[{index}].path does not exist: {path_value}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise EvidenceValidationError(f"{gate_id}.artifacts[{index}].path SHA-256 does not match sha256")
        return path_value
    if not isinstance(uri_value, str) or not uri_value.strip() or any(char.isspace() for char in uri_value):
        raise EvidenceValidationError(f"{gate_id}.artifacts[{index}].uri must be a non-empty URI")
    parsed = urlsplit(uri_value)
    if not parsed.scheme or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise EvidenceValidationError(
            f"{gate_id}.artifacts[{index}].uri must be an uncredentialed URI without query or fragment"
        )
    return uri_value


def validate_evidence_manifest(payload: Any, *, revision: str) -> dict[str, Any]:
    """Validate a machine-checkable, revision-bound five-gate evidence manifest.

    This validates integrity and completeness of the record only. It deliberately
    does not turn an operator assertion into production or customer acceptance.
    """
    if not isinstance(payload, dict):
        raise EvidenceValidationError("manifest root must be an object")
    if payload.get("schema") != EVIDENCE_SCHEMA:
        raise EvidenceValidationError(f"schema must be {EVIDENCE_SCHEMA}")
    if payload.get("revision") != revision or not isinstance(revision, str) or len(revision) != 40:
        raise EvidenceValidationError("revision must match the current 40-character git SHA")
    _timestamp(payload.get("recorded_at"), "recorded_at")
    operator = payload.get("operator")
    if not isinstance(operator, str) or not operator.strip() or len(operator) > 200:
        raise EvidenceValidationError("operator must be a non-empty name of at most 200 characters")
    gates = payload.get("gates")
    if not isinstance(gates, dict) or set(gates) != set(RELEASE_GATE_IDS):
        raise EvidenceValidationError("gates must contain exactly the five release gate IDs")
    for gate_id in RELEASE_GATE_IDS:
        gate = gates[gate_id]
        if not isinstance(gate, dict):
            raise EvidenceValidationError(f"{gate_id} must be an object")
        if gate.get("status") != "PASS":
            raise EvidenceValidationError(f"{gate_id}.status must be PASS to record release evidence")
        _timestamp(gate.get("verified_at"), f"{gate_id}.verified_at")
        for field in ("verified_by", "environment", "notes"):
            value = gate.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 4000:
                raise EvidenceValidationError(f"{gate_id}.{field} must be a non-empty string")
        artifacts = gate.get("artifacts")
        if not isinstance(artifacts, list):
            raise EvidenceValidationError(f"{gate_id}.artifacts must be an array")
        kinds = set()
        for index, item in enumerate(artifacts):
            _artifact_ref(item, gate_id=gate_id, index=index)
            kinds.add(item["kind"])
        missing = REQUIRED_ARTIFACT_KINDS[gate_id] - kinds
        if missing:
            raise EvidenceValidationError(f"{gate_id}.artifacts missing kinds: {', '.join(sorted(missing))}")
    return payload


def _evidence_check(path: Path | None, revision: str) -> tuple[Check, dict[str, Any] | None]:
    if path is None:
        return Check("release_evidence_manifest", "NOT_PROVIDED", "use --evidence with a revision-bound manifest"), None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validated = validate_evidence_manifest(payload, revision=revision)
    except (OSError, json.JSONDecodeError, EvidenceValidationError) as exc:
        return Check("release_evidence_manifest", "FAIL", str(exc)), None
    return Check(
        "release_evidence_manifest",
        "PASS",
        f"five-gate evidence manifest is structurally valid for {revision}",
    ), validated


def _run(command: list[str], *, cwd: Path = ROOT) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _git_revision() -> tuple[str, Check]:
    code, stdout, stderr = _run(["git", "rev-parse", "HEAD"])
    if code == 0 and len(stdout) == 40:
        return stdout, Check("git_revision", "PASS", stdout)
    return "unknown", Check("git_revision", "FAIL", stderr or "cannot resolve HEAD")


def _tracked_changes() -> Check:
    code, stdout, stderr = _run(["git", "diff", "--quiet", "--ignore-submodules", "HEAD", "--"])
    if code == 0:
        return Check("tracked_worktree_clean", "PASS", "no tracked changes")
    if code == 1:
        changed = _run(["git", "diff", "--name-only", "HEAD", "--"])[1].splitlines()
        return Check(
            "tracked_worktree_clean",
            "FAIL",
            "tracked files differ: " + ", ".join(changed[:8]),
        )
    return Check("tracked_worktree_clean", "FAIL", stderr or "git diff failed")


def _diff_check() -> Check:
    code, stdout, stderr = _run(["git", "diff", "--check"])
    if code == 0:
        return Check("git_diff_check", "PASS", "no whitespace errors")
    return Check("git_diff_check", "FAIL", stderr or stdout or "git diff --check failed")


def _required_files() -> Check:
    required = (
        "scripts/cp06_validate_env.sh",
        "scripts/cp06_probe.sh",
        "scripts/secret_scan.sh",
        "docs/DEPLOYMENT_ACCEPTANCE_CP06_TEMPLATE.md",
        "docs/V02_IMPLEMENTATION_TASKBOOK.md",
        "deploy/compose.pilot.yml",
    )
    missing = [item for item in required if not (ROOT / item).is_file()]
    if missing:
        return Check("release_contract_files", "FAIL", "missing: " + ", ".join(missing))
    return Check("release_contract_files", "PASS", f"{len(required)} required files present")


def _executable_scripts() -> Check:
    paths = (ROOT / "scripts/cp06_validate_env.sh", ROOT / "scripts/cp06_probe.sh", ROOT / "scripts/secret_scan.sh")
    missing = [str(path.relative_to(ROOT)) for path in paths if not os.access(path, os.X_OK)]
    if missing:
        return Check("release_scripts_executable", "FAIL", "not executable: " + ", ".join(missing))
    return Check("release_scripts_executable", "PASS", "CP-06 and secret-scan scripts are executable")


def _static_secret_scan() -> Check:
    code, stdout, stderr = _run(["bash", "scripts/secret_scan.sh"])
    if code == 0:
        detail = stdout.splitlines()[-1] if stdout else "secret scan passed"
        return Check("secret_scan", "PASS", detail)
    return Check("secret_scan", "FAIL", stderr or stdout or "secret scan failed")


def _lead_radar_tests() -> Check:
    code, stdout, stderr = _run(
        ["python3", "-m", "unittest", "discover", "-s", "apps/lead_radar/tests", "-p", "test*.py"]
    )
    if code == 0:
        summary = (stdout or stderr).splitlines()[-1] if (stdout or stderr) else "tests passed"
        return Check("lead_radar_tests", "PASS", summary)
    return Check("lead_radar_tests", "FAIL", stderr or stdout or "Lead Radar tests failed")


def _lead_radar_web_syntax() -> Check:
    page = ROOT / "apps/lead_radar/web/index.html"
    try:
        html = page.read_text(encoding="utf-8")
        script = html.split("<script>\n", 1)[1].split("\n  </script>", 1)[0]
    except (OSError, IndexError) as exc:
        return Check("lead_radar_web_syntax", "FAIL", f"cannot extract page script: {exc}")
    try:
        result = subprocess.run(
            ["node", "--check", "-"],
            cwd=ROOT,
            input=script,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return Check("lead_radar_web_syntax", "FAIL", str(exc))
    if result.returncode == 0:
        return Check("lead_radar_web_syntax", "PASS", "embedded Lead Radar page script parses")
    return Check("lead_radar_web_syntax", "FAIL", result.stderr.strip() or "node --check failed")


def _external_gates(evidence: dict[str, Any] | None = None) -> list[Check]:
    # These are intentionally not inferred from source files, health endpoints,
    # static pages, fixtures, or environment-variable presence.
    if evidence is not None:
        return [
            Check(
                gate_id,
                "RECORDED",
                "machine-verified evidence is recorded; human release review is still required",
            )
            for gate_id in RELEASE_GATE_IDS
        ]
    return [
        Check(
            "authorized_source_proof",
            "NOT_VERIFIED",
            "requires a real authorized provider, capability receipt and reopen/save/retry proof",
        ),
        Check(
            "autonomous_research_run",
            "NOT_VERIFIED",
            "requires a real SEARCH -> READ -> candidate -> evidence run without pre-seeded URL/author",
        ),
        Check(
            "real_sample_calibration",
            "NOT_VERIFIED",
            "requires a reviewed batch of real candidates with accuracy, false-touch and reopen metrics",
        ),
        Check(
            "production_database_and_recovery",
            "NOT_VERIFIED",
            "requires target PostgreSQL migration, least privilege/RLS, backup restore and rollback evidence",
        ),
        Check(
            "production_https_and_customer_uat",
            "NOT_VERIFIED",
            "requires final-version deployment, HTTPS/runtime proof and customer acceptance on that version",
        ),
    ]


def build_report(*, run_tests: bool, evidence_path: Path | None = None) -> dict[str, Any]:
    revision, revision_check = _git_revision()
    evidence_check, evidence = _evidence_check(evidence_path, revision)
    local = [
        revision_check,
        _tracked_changes(),
        _diff_check(),
        _required_files(),
        _executable_scripts(),
        _static_secret_scan(),
    ]
    if run_tests:
        local.append(_lead_radar_tests())
    else:
        local.append(
            Check(
                "lead_radar_tests",
                "NOT_RUN",
                "use --run-tests to execute the local Lead Radar contract suite",
            )
        )
    local.append(_lead_radar_web_syntax())
    if evidence_path is not None:
        local.append(evidence_check)
    external = _external_gates(evidence)
    local_ok = all(item.status == "PASS" for item in local)
    return {
        "schema": SCHEMA,
        "revision": revision,
        "scope": "mac-and-service; Windows excluded by operator scope",
        "local": {
            "status": "PASS" if local_ok else "FAIL",
            "checks": [asdict(item) for item in local],
        },
        "external": {
            "status": "RECORDED" if evidence is not None else "NOT_VERIFIED",
            "checks": [asdict(item) for item in external],
        },
        "evidence": {
            "status": evidence_check.status if evidence_path is not None else "NOT_PROVIDED",
            "path": str(evidence_path) if evidence_path is not None else None,
        },
        "overall": "HOLD",
        "note": "A local report or structurally valid manifest is not production or customer acceptance evidence.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="return success when local repository checks pass; external gates remain NOT_VERIFIED",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="run the Lead Radar unittest contract suite (otherwise report it as NOT_RUN)",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        help="validate a revision-bound five-gate evidence manifest; external gates remain RECORDED until human review",
    )
    parser.add_argument("--json", action="store_true", help="emit one JSON report instead of text")
    args = parser.parse_args(argv)
    report = build_report(run_tests=args.run_tests, evidence_path=args.evidence)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"release-candidate revision={report['revision']}")
        print(f"local={report['local']['status']} external={report['external']['status']} overall={report['overall']}")
        for group in ("local", "external"):
            for item in report[group]["checks"]:
                print(f"[{item['status']}] {item['id']}: {item['detail']}")
        print(report["note"])
    if report["local"]["status"] != "PASS":
        return 1
    if not args.local_only:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

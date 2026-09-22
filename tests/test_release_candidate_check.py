from __future__ import annotations

import importlib.util
import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_candidate_check.py"


def _module():
    spec = importlib.util.spec_from_file_location("release_candidate_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest(module):
    revision = module._git_revision()[0]
    artifacts = {
        "authorized_source_proof": ["capability_receipt", "source_reopen", "source_save_retry"],
        "autonomous_research_run": ["search_read_run", "candidate_evidence"],
        "real_sample_calibration": ["calibration_batch", "calibration_metrics"],
        "production_database_and_recovery": ["migration", "database_acl", "backup_restore", "rollback"],
        "production_https_and_customer_uat": ["runtime_revision", "https_probe", "customer_uat"],
    }
    gates = {}
    for gate_id, kinds in artifacts.items():
        gates[gate_id] = {
            "status": "PASS",
            "verified_at": "2026-09-23T10:00:00Z",
            "verified_by": "release-test",
            "environment": "isolated-test",
            "notes": "evidence recorded for contract test",
            "artifacts": [
                {
                    "kind": kind,
                    "uri": f"https://evidence.example/{gate_id}/{kind}",
                    "sha256": "0" * 64,
                }
                for kind in kinds
            ],
        }
    return {
        "schema": "yike.release-evidence/v1",
        "revision": revision,
        "recorded_at": "2026-09-23T10:00:00Z",
        "operator": "release-test",
        "gates": gates,
    }


def test_report_is_fail_closed_for_external_gates() -> None:
    report = _module().build_report(run_tests=False)

    assert report["schema"] == "yike.release-candidate/v1"
    assert report["external"]["status"] == "NOT_VERIFIED"
    assert report["overall"] == "HOLD"
    assert {item["status"] for item in report["external"]["checks"]} == {"NOT_VERIFIED"}


def test_external_gate_names_cover_real_release_boundaries() -> None:
    report = _module().build_report(run_tests=False)
    gate_ids = {item["id"] for item in report["external"]["checks"]}

    assert {
        "authorized_source_proof",
        "autonomous_research_run",
        "real_sample_calibration",
        "production_database_and_recovery",
        "production_https_and_customer_uat",
    } <= gate_ids


def test_local_only_mode_accepts_only_a_clean_local_candidate(monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_tracked_changes", lambda: module.Check("tracked_worktree_clean", "PASS", "test"))
    monkeypatch.setattr(module, "_static_secret_scan", lambda: module.Check("secret_scan", "PASS", "test"))
    monkeypatch.setattr(module, "_lead_radar_tests", lambda: module.Check("lead_radar_tests", "PASS", "test"))

    report = module.build_report(run_tests=True)

    assert report["local"]["status"] == "PASS"
    assert report["overall"] == "HOLD"


def test_revision_bound_evidence_manifest_is_structurally_valid() -> None:
    module = _module()
    manifest = _manifest(module)

    validated = module.validate_evidence_manifest(manifest, revision=module._git_revision()[0])

    assert validated["schema"] == "yike.release-evidence/v1"


def test_evidence_manifest_rejects_revision_mismatch() -> None:
    module = _module()
    manifest = _manifest(module)
    manifest["revision"] = "f" * 40

    with pytest.raises(module.EvidenceValidationError, match="revision"):
        module.validate_evidence_manifest(manifest, revision=module._git_revision()[0])


def test_evidence_manifest_rejects_non_https_or_credentialed_uri() -> None:
    module = _module()
    manifest = _manifest(module)
    manifest["gates"]["authorized_source_proof"]["artifacts"][0]["uri"] = (
        "https://user:secret@evidence.example/capability"
    )

    with pytest.raises(module.EvidenceValidationError, match="uncredentialed HTTPS URI"):
        module.validate_evidence_manifest(manifest, revision=module._git_revision()[0])

    manifest = _manifest(module)
    manifest["gates"]["authorized_source_proof"]["artifacts"][0]["uri"] = "http://evidence.example/capability"
    with pytest.raises(module.EvidenceValidationError, match="uncredentialed HTTPS URI"):
        module.validate_evidence_manifest(manifest, revision=module._git_revision()[0])


def test_evidence_manifest_recomputes_local_artifact_digest(tmp_path: Path) -> None:
    module = _module()
    artifact = tmp_path / "capability.json"
    artifact.write_text("authorized", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = _manifest(module)
    receipt = manifest["gates"]["authorized_source_proof"]["artifacts"][0]
    receipt.pop("uri")
    receipt["path"] = str(artifact)
    receipt["sha256"] = digest

    module.validate_evidence_manifest(manifest, revision=module._git_revision()[0])
    artifact.write_text("tampered", encoding="utf-8")

    with pytest.raises(module.EvidenceValidationError, match="SHA-256"):
        module.validate_evidence_manifest(manifest, revision=module._git_revision()[0])


def test_evidence_manifest_rejects_repository_path_and_duplicate_kind() -> None:
    module = _module()
    manifest = _manifest(module)
    artifact = manifest["gates"]["authorized_source_proof"]["artifacts"][0]
    artifact.pop("uri")
    artifact["path"] = str(ROOT / "scripts" / "release_candidate_check.py")
    artifact["sha256"] = hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest()

    with pytest.raises(module.EvidenceValidationError, match="outside the repository"):
        module.validate_evidence_manifest(manifest, revision=module._git_revision()[0])

    manifest = _manifest(module)
    artifacts = manifest["gates"]["authorized_source_proof"]["artifacts"]
    artifacts.append(dict(artifacts[0]))
    with pytest.raises(module.EvidenceValidationError, match="duplicate kind"):
        module.validate_evidence_manifest(manifest, revision=module._git_revision()[0])

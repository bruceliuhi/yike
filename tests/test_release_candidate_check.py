from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_candidate_check.py"


def _module():
    spec = importlib.util.spec_from_file_location("release_candidate_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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

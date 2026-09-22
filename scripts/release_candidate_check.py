#!/usr/bin/env python3
"""Fail-closed release candidate report for the Yike AI repository.

This command deliberately does not probe or infer external production facts.
It reports local repository checks and keeps the real-source, deployment and
customer-acceptance gates as NOT_VERIFIED until their evidence is recorded by
the operator.  Use ``--local-only`` when validating a source checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "yike.release-candidate/v1"


@dataclass(frozen=True)
class Check:
    id: str
    status: str
    detail: str


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


def _external_gates() -> list[Check]:
    # These are intentionally not inferred from source files, health endpoints,
    # static pages, fixtures, or environment-variable presence.
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


def build_report(*, run_tests: bool) -> dict[str, Any]:
    revision, revision_check = _git_revision()
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
    external = _external_gates()
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
            "status": "NOT_VERIFIED",
            "checks": [asdict(item) for item in external],
        },
        "overall": "HOLD",
        "note": "A healthy local report is not production or customer acceptance evidence.",
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
    parser.add_argument("--json", action="store_true", help="emit one JSON report instead of text")
    args = parser.parse_args(argv)
    report = build_report(run_tests=args.run_tests)
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

# Packaged runtime installer report

Scope: Task 1 only, based on `f857777e9c1909a343e06e0ac0054e8b88386827`.

Implemented:

- Added the fixed offline installer module and CLI for `YIKE_WINDOWS_PORTABLE_BUNDLE_V1`.
- Bound the manifest SHA-256, schema, fixed entries, required host/runtime and outreach files.
- Added bounded manifest parsing, canonical case-insensitive inventory validation, full source/destination digest checks, link/hard-link rejection, non-overlap checks, private directory creation, manifest-last publication, and read-only validation of existing destinations.
- Added the installer to the portable host inventory and host import probe.
- The installer copies and verifies files only; it has no network, browser, subprocess, payload execution, repair, overwrite, or deletion path.

Targeted verification on macOS:

```text
/tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q \
  tests/test_windows_portable_install.py \
  tests/test_portable_outreach_imports.py \
  tests/test_windows_portable_bundle.py
17 passed, 25 skipped
```

The tests use tiny real disk payloads. Windows-only execution is enabled only through explicit test injection of the private-directory creator and ACL verifier. This does not establish actual Windows ACL, packaging, relocation, restart, or platform acceptance; those gates remain open.

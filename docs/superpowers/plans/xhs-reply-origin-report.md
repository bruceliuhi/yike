# XHS reply origin backend report

## Delivered

- Added strict `POST /api/ui/replies/sync-context` input: `requestId`, `deviceId`, and `credentialVersion` only.
- Returns the frozen `outreach-context-v1`, original claim timestamp/ID, and the exact 24-character lowercase-hex root comment ID only for the authenticated owner's confirmed `SENT` XHS `POST_COMMENT` operation.
- Revalidates the active session/device credential, confirmation/claim/result canonical hashes, their request/claim/device/context bindings, frozen owner/tenant/profile/source/connection structure, and the accepted platform receipt.
- The lookup is read-only and does not revalidate against the latest draft, profile status, or source health.

## TDD evidence

- RED: `test_sync_context_returns_only_frozen_sent_xhs_post_origin` failed with HTTP 404 because the route did not exist.
- GREEN: isolated PostgreSQL command:
  `YIKE_IDENTITY_TEST_DATABASE_URL=postgresql://postgres:***@127.0.0.1:55048/postgres YIKE_IDENTITY_TEST_APP_DATABASE_URL=postgresql://identity_app:***@127.0.0.1:55048/postgres /tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q tests/test_signed_reply_http_postgres.py`
- Result: `20 passed in 15.05s`.

## Covered rejection boundaries

- Extra client fields, wrong owner/tenant, nonexistent or valid-but-different device.
- `UNKNOWN`, `FAILED`, non-XHS/non-post operations.
- Corrupt stored hashes/bindings and non-24-lowerhex root receipt IDs.
- Profile revocation and source closure after the original send do not erase valid frozen history.

## Not verified here

- No real Xiaohongshu read or send was executed.
- No full suite, package build, Windows runtime, worker wiring, or browser/platform acceptance was run.
- This backend endpoint plus the separately reviewed reader does not by itself make customer reply sync available; worker/main integration remains outside this task.

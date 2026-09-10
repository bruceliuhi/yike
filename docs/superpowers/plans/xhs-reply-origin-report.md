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

## Review fix evidence

- Implementation fix commit: `74f7a16ff90f4cbd9c58521c9c7ce36b5f224a2d`.
- RED request-binding case: after replacing the stored confirmation's top-level `requestId` and consistently recomputing its request hash, the endpoint incorrectly returned HTTP 200.
- RED rotation case: after rotating the same active device from credential version 1 to 2, the original valid SENT operation incorrectly returned HTTP 409.
- GREEN command: `YIKE_IDENTITY_TEST_DATABASE_URL=postgresql://postgres:***@127.0.0.1:55048/postgres YIKE_IDENTITY_TEST_APP_DATABASE_URL=postgresql://identity_app:***@127.0.0.1:55048/postgres /tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q tests/test_signed_reply_http_postgres.py::test_sync_context_returns_only_frozen_sent_xhs_post_origin tests/test_signed_reply_http_postgres.py::test_sync_context_rejects_confirmation_saved_under_a_different_request_id tests/test_signed_reply_http_postgres.py::test_sync_context_uses_current_key_after_same_device_credential_rotation`.
- GREEN result: `3 passed in 2.86s`.
- The current credential version now authenticates only this read request. The immutable confirmation and claim must retain their mutually matching original credential version; a result may retain the credential version valid when that result was recorded.

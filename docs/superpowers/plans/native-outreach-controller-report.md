# Native outreach controller — Task 1

Implemented main-owned PREPARE → explicit CONFIRM → real channel check → signed 122 confirmation → existing 123 dispatch/consumer/outbox. Shared commands accept business intent only; UI fingerprint is discarded. Main verifies the RESOLVED local profile through its original VERIFY server receipt and the current CONNECTED version/account, matches saved draft snapshot hash and frozen context, and fences session changes, expiry, concurrent confirmation and cleanup failure. Recovery only reconciles, resumes the original outbox RESULT, or cancels the original queued request; it never CLAIMs.

122 uses the actual Python lightweight `OutreachContextInput`, checks `requestId` and `requestSha256`, and reuses private canonical Ed25519 code. Public service policy remains unchanged. Driver checks retain their original timestamp; expired checks require confirmed physical stop before a replacement driver. Uncertain cleanup permanently blocks further flows in that controller.

Verification: initial missing-module RED for the new intent/controller tests, followed by targeted GREEN. Final command from `desktop`:

```sh
YIKE_CONFIRMATION_PYTHON=/tmp/yike-main-merge.PZkSlU/.venv/bin/python /Users/xingheimac/.nvm/versions/node/v24.19.0/bin/node node_modules/vitest/vitest.mjs run tests/nativeOutreachController.test.ts tests/nativeOutreach.test.ts tests/outreachDispatchProtocol.test.ts tests/outreachDispatchSession.test.ts tests/serviceClient.test.ts
```

Result: 5 files, 46 tests passed, including actual Python `Confirmation.model_dump` / `signing_payload` and Ed25519 verification. Platform/server outcomes in controller tests are explicitly synthetic fixtures, not sending evidence. The Python-vector test is enabled by `YIKE_CONFIRMATION_PYTHON`; without that configured interpreter it is skipped.

Root owns the one final integrated typecheck and batch independent review. No installation, full suite, build, external send, deployment, Windows real-platform or customer UAT performed here.

# Native outreach renderer report

Task 2 follows `2026-09-12-native-outreach-flow.md`; existing modal, editor, notices and buttons are reused without a visual redesign.

- Desktop XHS comments use only `nativeOutreachCommand`. PREPARE displays main-owned original source, public account, recipient and complete saved text; a checkbox and explicit CONFIRM are required. Plain web, other platforms and samples retain the prior guarded path.
- Connected XHS comment accounts can be selected with empty capabilities; no capability is fabricated.
- Before CONFIRM, localStorage commits and reads back only `{binding, state}` under user/accountScope/opportunity/channel. Failed writes, silent writes, invalid reads and conflicting records fail closed. No body, recipient, profile, token or key is written to this ledger.
- Pending remounts do not PREPARE or retry sending. Explicit RECONCILE, RESUME_RESULT and CANCEL_QUEUED use the original binding. SENT and UNKNOWN remain protected after draft edits; only confirmed non-delivery or cancellation retires the original pending record.
- Close, unmount, identity/content/connection-registration change cancel the original flow. Late responses do not report success to a new identity or clear the original pending record. Pending metadata remains visible in the editor after modal close.

## Evidence

- First RED: native UI suite 7 failed / 1 passed (missing native preparation and empty-capability account option).
- Registration-version regression RED: 1 failed / 10 passed; same-account version change was not cancelling. Fixed by extending only the native fingerprint with platform and registration metadata.
- Final directed run: `node node_modules/vitest/vitest.mjs run tests/ui/native-outreach.test.tsx tests/ui/outreach.test.tsx tests/ui/outreach-reconciliation.test.tsx tests/ui/contact-preparation.test.tsx` — **4 files / 52 passed**. Includes 11 native renderer cases with synthetic IPC responses, not platform delivery proof.
- Owned-path `git diff --check` passed. Root owns final combined typecheck; the renderer indexed-field type diagnostic was corrected to explicit business-field keys.

No full suite, build, packaging, actual platform send or production permission change was performed. Main/controller/driver integration and independent final review belong to the root batch.

## P2 correction — explicit pre-submission failure

The independent review found that a confirmed pre-apply failure left the renderer permanently pending. The controller now supplies a distinct `NOT_SUBMITTED` result only when original CONFIRM never began 122 apply and cleanup is confirmed. The UI accepts it only from that original CONFIRM, with exact response/original-ledger binding equality and a still-PENDING record; it clears that record, resets the preview/checkbox and requires fresh explicit preparation and confirmation. Generic FAILED/CANCEL/404 and mismatched bindings never clear protection.

Focused RED: 1 failed / 1 passed (11 unrelated tests filtered). GREEN: `vitest run tests/ui/native-outreach.test.tsx -t NOT_SUBMITTED` — **2 passed / 11 filtered**. No broader rerun, typecheck or build by this subtask; root owns combined verification.

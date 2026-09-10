# Background collection worker composition

**Goal:** Connect the existing authenticated desktop execution and original candidate queue into a background collection lifecycle, without blocking cancel/login or enabling an unverified source.

**Approved direction:** Continue the user's existing lean acceptance goal autonomously. Reuse confirmed strategy, execution signing/journal and candidate journal/signing. No new backend contracts, renderer identity or generic subprocess IPC. Mac owns source mapping/backend changes. A real driver/bootstrap remains necessary before enabling collection; this coordinator must not claim a platform is ready merely because constructed.

**Architecture:** Fresh main-only worker scope captures authenticated user/session epoch and READY device. Its bound execution/candidate transports remain usable after the short authentication callback releases its mutex, but fail immediately and after every request when closed, login/logout supersedes it, or a 401 occurs. It cannot capture a later global scope. A private worker composes existing execution/candidate sessions for one selected confirmed platform run. Fresh CLAIM, timed RENEW, local cancellation/epoch loss, bounded source driver and immutable candidate upload are handled in one lifecycle; source stop is awaited before reporting local stop. Never retry a new CLAIM or re-collect to recover an unknown upload. Distinguish recorded upload from backend task completion (current backend has no terminal-completion operation).

Rejected alternatives: holding `withAuthenticatedSession` for the entire browser run blocks cancellation; direct ServiceClient calls bypass epoch guards. Add an explicit lifetime-bound scope, not a second identity controller.

Scope boundary: this lean worker accepts only `mode=once` with `schedule=null`. Monitoring/scheduling remains deferred per the user's goal; reject it before CLAIM rather than silently executing it as one-shot. This also keeps deferred schedule float canonicalization out of the worker's supported hash contract.

## Tasks

1. TDD `deviceIdentityController.openWorkerScope()` and dedicated test module. Return only to main code a scope containing session, copied READY device, bound requestExecution/requestCandidate transports, close(). Signed-out/busy/not-ready must remain explicit. Preserve existing short-lived APIs. Tests cover long scope + concurrent authenticated cancel, login invalidation, late 401/new scope, absent candidate service, explicit close and no stale global capture.
2. TDD new `desktop/src/main/collectionWorker.ts` + tests. Compose real session APIs behind injected driver/lifecycle clock; validate original START and matching platform, claim fresh using unique ID, validate lease identity/liveness, renew without overlap; stop on unknown/failed renew, cancellation/epoch/deadline, and await source stop. Upload mapped raw records with the original profile/strategy/device/connection/task/run/lease tuple; bound records; preserve recovery key on unknown. Main-only API, no new capability flags or new renderer launch path until actual driver is ready.
3. Verify targeted controller/session/worker tests and TypeScript only; independent batch spec then code/architecture/quality review. Reuse prior installer/process/candidate journal evidence; no build until executable UI chain is actually wired. Main handoff explicitly carries missing driver/bootstrap and Mac backend terminal/source capability prerequisites, not an ACK.

Current evidence: normal backend `capability_check=None`; XHS governed terminal mapper is not yet controlled and source mapping has known ID defects owned by Mac. This work does not bypass either gate. Base main `2560a40`.

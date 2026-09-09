# Task-context return final independent review

Base reviewed: `a08751d0b02d21c7d70b08f24eaaac2ca73bec8a`. The reviewed patch was committed as `315d5906efcf8550309c78579895d7b45997c17b` and preserved in merge `fcae33e62f77d38208a0b3eaf97028d337000acc`, with all eight files verified against the frozen byte hashes below. The intervening P04 commit is outside this code review.

**Limited PASS: no remaining P0/P1/P2 found in this patch.** The P09 local tab/platform reset found during independent review has been corrected. No product file was edited by this reviewer. The only added repository file is the independent test below; raw, P04 and Windows work were not modified or approved here.

## Actual independent checks

1. Reviewed five product-file diffs: App parent navigation, Connections/Settings tab handoff, P06 website/platform links and P09 return construction. `routeHref` retains the actual task path and query; URLSearchParams/encodeURIComponent preserve mode, step and repeated filter parameters. Caller handoff survives connections↔settings. Existing no-caller and invalid-caller fallbacks remain internal. The patch continues using existing `safeReturnTo` rather than adding an external-navigation path. Neither viewing scope, connecting nor returning starts a task.
2. Ran `node node_modules/vitest/vitest.mjs run tests/ui/task-context-return.test.tsx tests/ui/tasks.test.tsx`: **2 files / 21 passed**, log `/tmp/yike-task-context-return-independent.log`. This was the first reviewed URI-preservation patch, before the discovered local-selection correction. It cannot prove the final local-selection behavior.
3. Found P2: MonitorDetail stored tab/chosen only in component state. Returning from P17/P18 remounted it with search coverage and the first platform. Initial independent mock-context regression: **2 failed / 2 passed**, `/tmp/yike-monitor-return-independent-red.log`. The failed assertions check actual returned controls, not only the target URI.
4. Author's narrow fix reads only four known tabs and a platform contained in the current run, carries the user's current local selection in returnTo, and preserves all unrelated query entries. It adds no storage or task side effects. Other task status, permission and operation code is unchanged.
5. Replaced the independent regression harness with **real AppProvider asynchronous hashchange** and route-driven task unmount/remount; ran only `tests/ui/task-context-return-independent.test.tsx`: **1 file / 4 passed**, `/tmp/yike-monitor-return-real-provider-green.log`. Both device inspection and reconnect return to the actual selected platform tab and non-first platform, retaining repeated query fields and making no start/taskAction calls. Invalid tab, unknown platform and a catalog platform absent from the run fall back. The successful tests do not fake a synchronous context route change. The original RED file used a simpler mock harness, so it is retained as the original counterexample rather than represented as the identical final test source.

The existing author's 6-suite / 94 result is not rerun or added to the independent counts. No browser/native/Windows visible acceptance or real platform connection is claimed. The TEST return control exercises the same parentRoute function; actual P17 cancellation and connections/settings tabs are separately covered by the author test suite. Broader route canonicalization or backend authorization was not re-audited.

## Frozen bytes

| File | SHA-256 |
|---|---|
| `desktop/src/renderer/app/App.tsx` | `881c1d1c4abb8fcf2bebfa5820ba46658f6f106765f66164646dda1ce7685db1` |
| `desktop/src/renderer/pages/Connections.tsx` | `5fd982c6957e635de6c2af82698b2c084be4169dd69d69adfe6cc7933120c074` |
| `desktop/src/renderer/pages/Settings.tsx` | `24686fa7bd05a5a36d8b934b3ca268537cd93f78624d99132229c96bb68c980e` |
| `desktop/src/renderer/pages/TaskWizard.tsx` | `1ba665c6f98f248e9923fee059de49ab7db4fb96d5c5c19317cbac42c396c1cf` |
| `desktop/src/renderer/pages/Tasks.tsx` | `24e21c267bc9dfeec43727a3972c1f5b981bec717420dd9d8dee824ef3605228` |
| `desktop/tests/ui/task-context-return.test.tsx` | `fbb2f3d73b7a3bc3f7c8d3a09d63d0250676e9d3eaa9560e84b69c8108c8cf5f` |
| `desktop/tests/ui/tasks.test.tsx` | `5d7cd5688dc5c87cf454e08080218f51b421d14b73a4767813e2b5b885bdfc43` |
| `desktop/tests/ui/task-context-return-independent.test.tsx` | `61dbcbcf6ba9f34c41e0cdcae80a7a96fe5dc57dfd67dfcf2952f68f869efdba` |

Final product patch and independent test may be committed together, followed by the root's integrated gate/artifact checks. Visible acceptance still requires the unlocked desktop and Windows environment.

## Commit and merge binding

The reviewed patch is committed as `315d5906efcf8550309c78579895d7b45997c17b`. Normal merge `fcae33e62f77d38208a0b3eaf97028d337000acc` retains all 8 listed product/test files byte-for-byte; independently verified each Git blob SHA-256 against the frozen table. The limited PASS therefore applies to this task-context slice in both commits. The merged remote changes, final whole-suite results, new Mac artifact and visible lifecycle remain outside this report until their separate evidence is supplied.

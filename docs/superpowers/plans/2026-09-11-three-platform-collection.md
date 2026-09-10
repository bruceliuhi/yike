# Three-platform foreground collection implementation plan

> Agentic workers: use subagent-driven-development and focused TDD. Full V0.2 and its multi-platform architecture are already approved. This batch implements existing scope, not a new UI/design. One independent batch review, fixes tested only by delta.

**Goal:** A customer can select a verified XHS, Douyin or Bilibili connection and start one controlled search using the existing task and ingestion flow.

**Architecture:** Reuse existing login/profile store, foreground controller, supervised Windows source and signed candidate ingestion. Expand the explicit deployment mode; never treat login registration as collection capability. No database changes or new dependency/payload build.

**Tech stack:** Existing Electron/TypeScript/Python/PostgreSQL and pinned MediaCrawler.

## Global Constraints

- “事务不跨浏览器、模型或网络等待。”
- “密钥、Cookie、Profile、验证码和私密会话不进入 Git、业务数据库、日志或导出。”
- “平台验证码及验证挑战由用户按可用流程处理”；不绕过验证、限流或权限控制。
- “相同产品字节已通过的检查直接引用原证据；仅新修改、失败或未解决风险触发追加检查。”
- Supported platforms exactly XIAOHONGSHU/DOUYIN/BILIBILI; account rules reuse shared/platformAccount.ts and app/platform_login_worker.py. Same owner/device/platform/profile/connection/version must hold through execution. Current mode xhs-foreground-v1 remains XHS only; new opt-in mode three-platform-foreground-v1 allows the three platforms.
- This batch is one platform per foreground task, once/search, current caps100records/900seconds, no schedule/research/exclusions/links. These temporary runtime limits do not remove full multi-platform scheduling/monitoring from the goal.
- Collection guards run in the same source browser context, before/after search requests; no separate login browser or raw credential transfer. Unknown account fails, no fallback unguarded worker. Physical cleanup precedes terminal success.
- No real sends/deployment, credential reads/exports, new layout or pinned dependency modifications. Source tests do not constitute real platform or Windows proof.

### Task 1: desktop platform selection and foreground capability (implementer)

**Own:** desktop/src/shared/foregroundCollection.ts, main/collectionAccountBinding.ts, main/foregroundCollectionController.ts, main/pythonCollectionDriver.ts; renderer/domain/task.ts, renderer/services/foregroundCollection.ts, renderer/services/client.ts only where necessary; focused tests in desktop/tests/{collectionAccountBinding,foregroundCollectionController,foregroundCollectionRenderer,foregroundCollectionIntegration,pythonCollectionDriver}.test.ts and ui/foreground-collection.test.tsx. No main.ts/layout changes absent a concrete need. Root owns all Python and docs.

**Interfaces:** backend execution.support retains schema_version foreground-collection-support-v1, mode is null/xhs-foreground-v1/three-platform-foreground-v1. Native AVAILABLE response becomes `{state:'AVAILABLE',bindings:ForegroundBinding[]}` (1..3, unique platform), replacing singular binding within this same-release IPC; update its consumers/tests. Each ForegroundBinding retains exact existing fields, mode enumerates both modes and platform NativeLoginPlatform; reject legacy mode paired with a video platform. Main capabilities reads up to3 protected profile records under one authenticated scope/current rows; an unavailable platform does not suppress other verified platforms. No N-per-registration scans. START checks selected platform against current server mode, target/strategy exactly match, and uses selected privateprofile/expectedAccountPublicId. No unbound fallback. Driver expectedAccountPublicId validates selected platform; host wire field unchanged.

- [ ] Add RED checks: both video platforms resolve only matching privateprofile+currentrow+originalVERIFY; selected target reaches driver; legacy mode cannot start videos; capability attaches to correct platform/device/account/version only; invalid or duplicate bindings rejected. Use syntheticIDs and existing fixtures.
- [ ] Implement `nativeLoginPlatformSchema` / `validNativeAccount` reuse and platform-mapped renderer guard instead of fixed XHS. Example rule: `binding.platform === ({xhs:'XIAOHONGSHU',douyin:'DOUYIN',bilibili:'BILIBILI'} as const)[connection.platform]`. Return `bindings` and attach search capability individually to exact verifiedrows; preserve registration non-capability semantics. Existing collection worker's single-target constraint remains.
- [ ] Run only impacted test files, one typecheck; commit own files, write report. Do not build, rerun unchanged suites, or enable backend deployment configuration.

### Task 2: native source identity guards and opt-in support (root)

**Own:** app/platform_collection_worker.py, app/platform_login_worker.py (reuse/extract DY selfreader), app/windows_collection_host.py, app/windows_source_driver.py, pilot/foreground_collection.py; focused Python tests for these modules.

**Interfaces:** existing `expected_account_public_id` is checked using `valid_account(platform,value)`, host/driver pass private `YIKE_COLLECTION_PLATFORM` alongside identity. `_fixed_arguments(arguments, platform='XIAOHONGSHU')` verifies exact CLI platform code. Fixed imports for three governedsource classes. Existing XHS install_account_guard remains compatible; video guard wraps search/request similarly.

- [ ] RED: wrong account and account switch after source response fail without accepting data; request wrappers restored on exit; host explicitplatform validates both IDs; new policy allows3 only while legacyallowsXHSonly.
- [ ] Bilibili check uses same browser context request `GET https://api.bilibili.com/x/web-interface/nav`, no redirects, timeout10s, requires200/code0/data.isLogin===true/positive mid matching expected. This is an independent fresh selfread using browser cookies, not cached source-client headers; never log rawresponse.
- [ ] Douyin uses one auxiliary officialself page in the same sourcebrowsercontext while source searchpage is preserved. Reload `/user/self` with bounded visible publichandle check before/after each source request and before/after search. Reuse login's selfreader; close only owned selfpage in finally. This conservative initial cost is explicit; no unverified identity cache or searchpage navigation.
- [ ] Extend `_fixed_arguments` and fixed worker platform imports, while preserving governed CLI output/physical cleanup. `configured_collection_policy`: old mode→old policy; new mode→new policy; unknown→error; supportreports exactconfiguredpolicy. No environmentdefault enabling.
- [ ] Run focused synthetic worker/host/policy tests and one cross-boundary fixture if available, not fullsuite/realWindows. Record precise limitations.

### Task 3: independent review and main handoff

- [ ] Review concrete base b0d6522..sourceHEAD as one batch; fix actionable findings with targeted checks.
- [ ] Update one evidence section here and two short current-status pointers. Native account correctness and actual platform collection remain separate; no fixture counts as a real lead.
- [ ] Push normal fast-forward to yike-ai2026/main, verify parity, preserve active fullgoal. Next runtime stage: continuous monitoring and multi-platform task scheduling, then freshWindows payload/actualplatform/UAT/production gates.

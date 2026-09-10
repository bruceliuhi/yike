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

- [x] Add RED checks: both video platforms resolve only matching privateprofile+currentrow+originalVERIFY; selected target reaches driver; legacy mode cannot start videos; capability attaches to correct platform/device/account/version only; invalid or duplicate bindings rejected. Use syntheticIDs and existing fixtures.
- [x] Implement `nativeLoginPlatformSchema` / `validNativeAccount` reuse and platform-mapped renderer guard instead of fixed XHS. Example rule: `binding.platform === ({xhs:'XIAOHONGSHU',douyin:'DOUYIN',bilibili:'BILIBILI'} as const)[connection.platform]`. Return `bindings` and attach search capability individually to exact verifiedrows; preserve registration non-capability semantics. Existing collection worker's single-target constraint remains.
- [x] Run only impacted test files and necessary typecheck; commit own files, write report. Do not build, rerun unchanged suites, or enable backend deployment configuration.

### Task 2: native source identity guards and opt-in support (root)

**Own:** app/platform_collection_worker.py, app/platform_login_worker.py (reuse/extract DY selfreader), app/windows_collection_host.py, app/windows_source_driver.py, pilot/foreground_collection.py; focused Python tests for these modules.

**Interfaces:** existing `expected_account_public_id` is checked using `valid_account(platform,value)`, host/driver pass private `YIKE_COLLECTION_PLATFORM` alongside identity. `_fixed_arguments(arguments, platform='XIAOHONGSHU')` verifies exact CLI platform code. Fixed imports for three governedsource classes. Existing XHS install_account_guard remains compatible; video guard wraps search/request similarly.

- [x] RED: wrong account and account switch after source response fail without accepting data; request wrappers restored on exit; host explicitplatform validates both IDs; new policy allows3 only while legacyallowsXHSonly.
- [x] Bilibili check uses same browser context request `GET https://api.bilibili.com/x/web-interface/nav`, no redirects, timeout10s, requires200/code0/data.isLogin===true/positive mid matching expected. This is an independent fresh selfread using browser cookies, not cached source-client headers; never log rawresponse.
- [x] Douyin uses one auxiliary officialself page in the same sourcebrowsercontext while source searchpage is preserved. Reload `/user/self` with bounded visible publichandle check before/after each source request and before/after search. Reuse login's selfreader; close only owned selfpage in finally. This conservative initial cost is explicit; no unverified identity cache or searchpage navigation.
- [x] Extend `_fixed_arguments` and fixed worker platform imports, while preserving governed CLI output/physical cleanup. `configured_collection_policy`: old mode→old policy; new mode→new policy; unknown→error; supportreports exactconfiguredpolicy. No environmentdefault enabling.
- [x] Run focused synthetic worker/host/policy tests and one cross-boundary fixture if available, not fullsuite/realWindows. Record precise limitations.

### Task 3: independent review and main handoff

- [x] Review concrete base b0d6522..sourceHEAD as one batch; fix actionable findings with targeted checks.
- [x] Update one evidence section here and two short current-status pointers. Native account correctness and actual platform collection remain separate; no fixture counts as a real lead.
- [ ] Push normal fast-forward to yike-ai2026/main, verify parity, preserve active fullgoal. Next runtime stage: continuous monitoring and multi-platform task scheduling, then freshWindows payload/actualplatform/UAT/production gates.

## 实施与验证（2026-09-11）

源码批次 `b0d6522..cb7d656`：客户端 `ab8e236`；Python及策略 `3d3eac0`；兄弟模块导入隔离 `cb7d656`。现有账号/新建任务入口复用，无界面重绘或数据库迁移。服务端需明确配置 `YIKE_PILOT_COLLECTION_MODE=three-platform-foreground-v1` 才报告三平台支持，未配置仍关闭，旧 `xhs-foreground-v1` 不放大权限。每次任务仍限一个平台和一次搜索；周期监控、多平台任务调度仍待接续，不从完整 Goal 移除。

- 桌面受影响6文件 **85 passed**；后续 controller15、renderer23为重叠差量，不累加。首次类型检查发现1个ApiResult narrowing错误，修复后 `npm run typecheck` **通过**，没有重跑85项或构包。分工报告在 Git-worktree 私有 sdd 目录；误提交的临时报告已移除，不作为产品文档。
- Python新护栏 RED **10 failed**（旧host拒绝视频账号、缺失guard）。最终 `pytest -q tests/test_video_collection_guard.py tests/test_windows_collection_host.py tests/test_foreground_collection.py tests/test_platform_collection_worker.py tests/test_platform_login_multiplatform.py --tb=short` **105 passed / 3 skipped**。包含开始/响应/完成时切号、源代码吞异常后仍拒收、限流/权限/验证分类、平台协议和旧XHS策略兼容。
- 补充真实依赖验证：最初导入探针的模块路径顺序错误，暴露直接加载worker时不应把app/config.py置于runtime/config之前；现通过固定兄弟文件加载，避免全局路径污染。旧 `/tmp/yike-mediacrawler-final-installed` 实际只有0001补丁，不能作为现行双补丁XHS证据；该缓存上的安装标记/cleanup断言失败保留，不算产品通过。
- 新建隔离源码副本 `/tmp/yike-three-platform-runtime.n5Nouc`，固定commit `439509782cc2991c8ef7648e178d5847b0545798` 顺序应用仓库0001/0002补丁，**14个受控文件摘要全部匹配现行lock**；只复用现有venv，没有安装依赖/构包。`YIKE_SOURCE_INSTALLED_CHECK=该副本 pytest -q tests/test_platform_collection_worker.py -k installed --tb=short` **3 passed / 18 deselected**。这是现行source/main/client+合成浏览器/HTTP的兼容验证，POSIX不检查Windows安装标记；原Windows分支仍强制保留该校验。
- 抖音使用同一context的辅助自页，保守地逐请求核验，增加页面读取成本；尚无真实平台延迟/稳定性结果。B站自读与源client缓存Cookie分开，但仍在同一浏览器context，不导出任何Cookie。错误或切号锁定后整批拒收，即使上游捕获异常也不会恢复成成功。
- 独立整批初审 `video_collection_review` 对 `cb7d656` 给 **NO-GO**：P2 单个平台 profile 读取失败导致全部不可用；P2 抖音自页网络/HTTP错误被归为登录失效。修复集中交给同一实现者，只补相关差量，不重跑前述套件。
- 最终源码 `ad0ff04c208769ae0b2e1029bce0367f16d124bb` 修复两项P2，定向 controller **16 passed**、两Python文件 **30 passed**、类型检查通过；独立差量复核给 **source-merge GO**，没有新增P1/P2、没有重跑原套件。单个平台坏档案不影响其他有效平台，失效会话仍整体关闭；抖音导航网络/HTTP401/403/429分类及锁存保持，未知账号仍拒绝。
- 无实际扫码/真实平台采集/外发/Windows新包/生产/UAT证据，测试原文均为合成值，不得计为真实线索。

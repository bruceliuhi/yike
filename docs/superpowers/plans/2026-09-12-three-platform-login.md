# Three-platform native account connection implementation plan

> Agentic workers: use subagent-driven-development and focused TDD. Existing full V0.2/multiplatform design is approved. One independent batch review; fixes get delta checks only.

**Goal:** Customers can connect 小红书、抖音、B站 from the existing account page, with a platform-bound native identity and isolated saved profile. This is the prerequisite for expanding authenticated collection, not proof of collection or monitoring.

**Architecture:** Extend the existing Windows native login host/controller and renderer adapter, preserving original REGISTER/VERIFY receipts and current-connection checks. No second cookie store, new database table, new UI layout, or capability enablement.

**Tech stack:** TypeScript/Electron, Python, pinned governed MediaCrawler/Playwright, existing authenticated connection API.

## Global Constraints

- “事务不跨浏览器、模型或网络等待。”
- “密钥、Cookie、Profile、验证码和私密会话不进入 Git、业务数据库、日志或导出。”
- “平台验证码及验证挑战由用户按可用流程处理”；不绕过验证、限流或权限控制。
- “相同产品字节已通过的检查直接引用原证据；仅新修改、失败或未解决风险触发追加检查。”
- Platforms are exactly `XIAOHONGSHU`, `DOUYIN`, `BILIBILI`. Account ID rules: XHS `[A-Za-z0-9]{8,32}`; Bilibili positive decimal mid `[1-9][0-9]{0,19}`; Douyin own public handle `[A-Za-z0-9_.-]{1,64}` read only on official `/user/self` page. Unknown/ambiguous identity fails closed, not nickname inference.
- Main-only paths/profile/account identity. Renderer OPEN/CHECK/CANCEL supplies only platform and opaque flow. CHECK/CANCEL must match the original platform as well as flowId. Capture platform in asynchronous renderer flows, late cancellation and private profile keys.
- Reuse `windows-platform-login-v1` bounded host frames. Main sends explicit platform; Python passes it in private `YIKE_LOGIN_PLATFORM`; worker dispatches fixed platform loader only. Terminal identity validated against that platform. Existing XHS call signature defaults remain compatible, but wrong-platform values never authorize a connection.
- Successful native observation is emitted only after browser/process cleanup with original observation time. CONNECTED still requires REGISTER→VERIFY→current row exact platform/device/account/id/version; no collection/send permission implied.
- No real Windows login/collection/sends, credential exports or new payload build in this source batch.

## Observed source basis

Pinned dependency at `/tmp/yike-mediacrawler-final-installed`, HEAD `439509782cc2991c8ef7648e178d5847b0545798`, read-only. Bilibili client's existing authenticated `/x/web-interface/nav` response exposes `isLogin` and `mid`; use only explicit logged-in self response, never a creator page. Douyin live browser observation this run: homepage's “我的” links to `https://www.douyin.com/user/self`; this self page shows one public `抖音号：...` label. Only public own-profile header was inspected, no messages/private tabs. This confirms entry semantics, not the Windows worker selector or login acceptance. Do not commit observed real handle/nickname. XHS keeps existing unique “我” link method.

### Task 1: desktop multi-platform connection (implementer)

**Own:** desktop/src/shared/platformConnection.ts, new shared/platformAccount.ts; main/platformLoginDriver.ts, main/platformConnectionController.ts, main/connectionProfileStore.ts; renderer/services/platformConnection.ts; focused related tests only. Existing main.ts should not need layout/registration changes; if required explain the dependency first.

**Interfaces:** Driver `start({profileId,platform?,signal?})`, missing platform retains XHS for old internal callers. Controller always supplies selected validated platform. Shared `nativeLoginPlatformSchema`/`validNativeAccount(platform,account)` reusable by driver/controller; renderer map `xhs/douyin/bilibili` to uppercase enums (verify actual model IDs). No other platform accepted.

- [x] RED: parameterize native connection/controller tests for BILIBILI/DOUYIN with valid platform-specific account IDs; verify same textual account on different platforms yields separate protected scopes and original operations. Cross-platform CHECK/CANCEL, mismatched CONNECTED row and stale asynchronous renderer result must reject.
- [x] Implement by replacing fixed XHS constants only at connection boundaries, not outreach/collection. Keep existing per-flow cancellation and unknown-outcome recovery.
- [x] RED/GREEN driver test asserts stdin platform and rejects invalid account for that platform before success; renderer test asserts selected platform survives OPEN/CHECK/CANCEL.
- [x] Run only affected test files and one `tsc --noEmit`, commit owned files; return concise status plus evidence in task report.

### Task 2: fixed native login sources (root)

**Own:** app/platform_login_worker.py, app/windows_platform_login.py, tests/test_platform_login_worker.py, tests/test_windows_platform_login.py, optional new focused test_platform_login_multiplatform.py. Reuse already-included host files; don't modify pinned dependency/lock or packaging inventory.

**Interface:** `login_platform(*, platform, output_path)` dispatches existing `login_xhs` or fixed Bilibili/Douyin browser flow. Source uses each pinned crawler's launch/create_client/login/close methods. XHS unchanged. Bilibili uses authenticated nav response and positive mid; Douyin verifies official self page then uniquely visible anchored public-handle label. Failures sanitized through existing runtime classifier. `valid_account(platform,value)` applies exact above rules; host `_terminal(value,platform='XIAOHONGSHU')` binds result to requested platform.

- [x] Write focused failing tests for selection, account identity, self URL, ambiguous/foreign/missing account, cleanup and observed time. Test actual helper logic with explicit synthetic browser boundary, not fake product evidence.
- [x] Use fixed platform imports and governed login only; preserve timeout/cancellation/secret-free output. No search or send on login path.
- [x] Run affected Python tests. Record live-public-entry observation separately from synthetic worker tests.

### Task 3: integration and handoff

- [x] Verify root/helper platforms and account validation agree; backend connection operations already accept these platform enums, so no backend policy broadening.
- [x] One independent source review from base `9073b84`; fixes only targeted deltas. Update taskbook with exact supported connection paths and remaining collection-account guard, capability/controller expansion, monitor scheduler, real Windows/platform/UAT work.
- [ ] Fetch and push reviewed changes to main. Do not mark 01/02 parent cards or full product goal complete.

## 本批实施与证据（实际核对日期：2026-09-11，北京时间）

源批次 `9073b84..97e73b4`：桌面实现 `e7225c2`，原生 helper `97e73b4`。沿用现有 v1 协议，新增明确平台分派，不新增数据库表或开放采集能力。该计划文件名是工作条目标识，不代替实际执行日期。

- 桌面 RED 12 项原固定 XHS 失败；受影响 5 文件 GREEN **62 passed / 2 Windows-only skipped**，`npm run typecheck` 通过。命令：`npm test -- --run tests/platformConnection.test.ts tests/platformLoginDriver.test.ts tests/platformConnectionController.test.ts tests/connectionProfileStore.test.ts tests/ui/platform-connection-adapter.test.ts`。
- Python 新用例 RED 5 项缺失分派/host 拒绝；`pytest -q tests/test_platform_login_multiplatform.py tests/test_platform_login_worker.py --tb=short` **23 passed / 1 installed-runtime skipped**。
- 新增私有 host 平台环境穿透后，`pytest -q tests/test_platform_login_multiplatform.py tests/test_windows_platform_login.py -k 'not opened_then_eof and not real_pipe' --tb=short` **20 passed / 9 Windows skipped / 4 deselected**。4 个未跑项使用 Windows 路径协议，当前 POSIX 不能替代；上述计数重叠，不相加。
- Python 使用仓外既有 venv；桌面复用现有依赖。没有全量回归、构包、真实 Windows 运行、扫码登录、Cookie 导出、实际采集或发送。公开抖音自我页面入口观察与合成 worker 测试严格分开，后者不能证明真实页面选择器验收。
- 独立整批初审对 `97e73b4` 给 NO-GO：抖音 SPA 标签未就绪即检查会误报未验证。`23cae61b9dd1cff01ea775d0f01a46c1674d6e1a` 增加 10 秒有界可见等待，并在等待后重验自页 URL/唯一性/格式；延迟标签用例 RED 1 失败 → GREEN **1 passed / 6 deselected**，仅重测该差量。同一非作者 reviewer `three_platform_review` 对最终源码给 **source-merge GO**，未重复跑测试或构包。
- 非阻断 minor 保留：renderer 尚未在收到 CONNECTED 时额外比较返回平台；main 已严格核对平台、账号、设备和当前版本，不构成已发现的越平台授权路径。后续 UI 强化时处理，不因此追加当前构包。
- 后续：平台账号采集前后绑定检查 → 前台采集合同/controller/capability → 周期监控；Windows payload/真实平台/生产/UAT 仍是单独门禁。完整 Goal 和父卡继续，不能把本次源合入说成已登录或已上线。

# Foreground XHS collection flow implementation plan

> Agentic workers: use subagent-driven-development and TDD; one batch SPEC then code/quality review, delta review only after corrections. User authorized autonomous implementation; reuse unchanged verification and do not repeatedly ask approval for this existing scope.

**Goal:** Connect the existing confirmed once-search task to the governed XHS collector, durable candidate upload and honest server completion, with current account binding and no automatic contact.

**Architecture:** Reuse execution/candidate journals and signed sessions, connection profile store, collectionWorker and Python host. Main owns the background handle and original task/batch IDs; renderer receives safe status only. Source checks the expected public account within the very same browser that searches. Completion is a signed FINISH of the same lease with a verified persisted upload receipt; no new task system or renderer authority.

**Alternatives:** Treating upload as completion leaves server tasks RUNNING; direct renderer shell execution loses scope/cancellation. Extend the existing execution protocol and compose existing worker instead. No new scheduler, auto-login, send or billing.

## Chunk 1: Same-browser account binding (runtime helper)

- [x] Add fixed `app/platform_collection_worker.py` and focused tests; extend `windows_collection_host.py`/`windows_source_driver.py` with optional expected_account_public_id, required by the new XHS main path. Strict canonical8..32 alphanumeric. Existing unmapped source tests remain legacy paths, not enabled product capability.
- [x] Fixed worker imports the installed governed XHS core/client and invokes its existing normal CLI entrypoint, with an explicit adapter around the same crawler search boundary. Before search, require existing successful pong plus unique visible official self-navigation matching expected account; do not silently log in as a different account. Recheck at search request boundaries and before successful completion, never export cookies. Failure/cancel keeps original raw files and fixed errors, no empty-success substitution. No changes to installed runtime or old patch bytes, no generic shell or configurable worker code.
- [x] Extend Node pythonCollectionDriver binding with expected account, forward private field to host; worker/source tests cover no-search-on-mismatch, account change, same browser, auth challenge, no real network, actual host args/environment/cleanup. Driver files assigned to root to prevent overlap.

## Chunk 2: Server terminal success (backend helper)

- [x] Add FINISH to existing execution operation: same task/platform_run/lease/generation fields as RENEW plus upload_request_id (canonical existing candidate request key). Require owner ACTIVE device/key signature, current connection/profile/strategy, live task deadline/lease; full budget consumption is allowed for FINISH, not for new claims/uploads. Verify immutable stored candidate upload receipt/binding matches exact tenant/user/device/task/run/platform/lease/generation/connection and original request. Zero-record confirmed upload is valid; missing/wrong/unknown receipt cannot finish.
- [x] Set platform SUCCEEDED and aggregate task/run SUCCEEDED only when every platform is SUCCEEDED, otherwise RUNNING. Persist immutable FINISH receipt with task/run/platform/lease/generation/upload_request_id/records_used; status RUNNING|SUCCEEDED and stop_confirmed equals status SUCCEEDED. Claim/renew/upload cannot resurrect terminal platforms; CANCEL cannot revert completed task/platforms. Cancellation after a claimed process remains CANCELLING until stop acknowledgement exists; this batch must not call it CANCELED merely because local abort was requested.
- [x] New migration120 extends only required status/action CHECKs, no historical migrations/grants/RLS changes. Register db migration; extend shared executionOperation/Receipt and exact signing/roundtrip tests. Maintain old operation canonical signature bytes by omitting new null field when not FINISH. Tests RED/GREEN with dedicated restricted PostgreSQL, full-budget/empty upload, stale lease/account/profile/session, cancellation races, rollback after delayed final fence, immutable original request recovery. Helper owns backend execution files, new migration, shared operation/receipt and their tests; root owns collection worker/session composition.

## Chunk 3: Existing task entry -> worker -> upload (root)

- [x] Add main-only profile binding lookup by current device/platform/connection/version using protected stored original VERIFY and current connection row, never renderer profile/account claims. No reusing another service/user/device profile. Pass exact account to collection driver; raw profile remains private and not exposed by status.
- [x] Compose existing collectionWorker, executionSession/candidateSession with long-lived captured DeviceWorkerScope, durable journals/vault and fixed Python paths. Confirmed START retains existing immutable request/receipt behavior; after main verifies strategy/connection/runtime and obtains the recorded START, start one foreground worker without blocking authentication IPC. No auto-relaunch from a historical START receipt after restart; explicit user continuation must first recover original batches/terminal operation.
- [x] Add safe local collection status/cancel/recover command and reuse existing task execution panel for status and original upload recovery. No new visual layout system. Session/device change and app exit stop the actual source; upload/finish unknown remains recoverable under original request IDs. Worker only FINISHes after physical stop and confirmed original upload; empty upload success is explicitly distinguishable from source errors. Durable batch lookup prevents re-collection on unknown upload.
- [x] Keep configured source capability conservative: only exact supported once/search/XHS/platform-account configuration, no unsupported links/exclusions/research/schedule. Development runtime and backend capability configuration must both explicitly support the path; packaged bootstrapping and actual platform acceptance remain required before customer readiness. Do not flip all capabilities or claim runtime READY merely from config.
- [x] Targeted backend, source/Node/UI and real main/controller→HTTP→restrictedPG with controlled platform boundary; run one independent batch review and delta verification, integrate latest main. Build one candidate only when customer bootstrap and visible collection path actually run, not for intermediate same-byte doc updates.

Base135212a. Full Goal remains lean three-channel intake, original evidence, more-similar, short drafts, approved real send/reply and Windows acceptance then real100/30 case. No real platform account/password/challenge actions or external messages without user authority; synthetic tests are not live customer validation.

## 本批交付与验证

基线 `135212a`；本节所在提交包含本批源码。Win 独立接管，Mac 停止不再是等待条件。三个功能块已实现；运行时 helper 同批接收 Node driver/worker 所有权，避免与主进程装配重复修改。

**入口与范围：** 现有账号页完成 XHS 登录登记/VERIFY 后，在任务向导确认业务画像、关键词及策略，选择已通过本机绑定检查的小红书账号，执行一次搜索。当前最多 100 条、900 秒，不支持排除词、链接任务、持续监控或研究扩展。原文候选进入既有候选页面；任务页“本机原执行请求”可读取当前采集/服务端状态，明确确认后恢复原批次。历史回执与当前状态分别显示。

**仅开发配置：** 服务端显式 `YIKE_PILOT_COLLECTION_MODE=xhs-foreground-v1`（空值关闭、未知值启动拒绝）；设备完成正常 READY 验证；Windows 非打包客户端配置本机绝对路径 `YIKE_SOURCE_HOST_PYTHON`、`YIKE_SOURCE_PROJECT_ROOT`、`YIKE_SOURCE_RUNTIME_PATH`，沿用 `YIKE_SERVICE_URL`。主进程还实际检查安装回执/受控字节、私有 profile、原 VERIFY 与当前设备/账号/连接版本，不能仅靠环境变量或 CONNECTED 登记开启。默认通用 `task_execution` 仍为 false，没有伪造 sidecar READY，也没有启用发送能力。

**持久与停止：** source 同一浏览器的搜索/request 前后核对期望账号；物理停止后写不可变原批次再上传。确认上传后签名 FINISH，数据库核对原批次和全部执行上下文，允许刚好耗满预算/空批次，只有全部平台成功才终结任务。未知上传/完成沿原键核对，不重开采集；已有 CLAIM 的任务重启后不会自动重采。FINISH 仍要求当前有效 lease/授权，过期恢复不能伪造完成；已上传候选保留，需核对任务状态。取消已领取任务仍可能显示服务端 CANCELLING，不能把本机停止当服务器确认已停止。

**验证：** 根代理最终桌面 16 文件 201 passed、类型检查通过；Python 策略配置/Windows 来源 140 passed（含安装运行时受控主入口及真实只读探测，无跳过）。FINISH helper 131 项受影响后端回归、共享协议/签名 302 项及实际 HTTPS support 路由 1 项通过；集合有重叠，不合计成全仓。关键反例先 RED 后 GREEN，包括错账号、不完整输出、上传后未知、满预算、过期尾部回滚、旧请求 canonical、恢复并发与停止未确认。旧 pytest 私有 ACL 目录清理警告保留，未修改其权限或删除旧证据。非作者整批 SPEC 与代码/质量审核通过，无 P1/P2；最后新增真实 controller→socket HTTP→受限 PostgreSQL 集成 1 passed / 3.64 秒，无跳过：正式确认 XHS 策略与登记连接，上传提交后丢回执，重建按 CLAIM 防重采，再恢复原批次并 FINISH 成功；数据库任务/批次/观察/计量各 1，原文逐字不变、driver/POST 各一次。

**尚未交付：** 上述浏览器/平台输入受控，不是用户账号真实采集；尚无客户 bootstrap，打包版本仍关闭此路径，本批不构建另一个不能采集的安装包。历史 `candidate-1a47178` 不追认为本版本。下一步是把受控运行时接入客户启动安装，再做真实 XHS 批次与 Windows 生命周期验收，随后抖音/B站、真实多找类似/短句、批准发送与回复；Goal 保持 ACTIVE。

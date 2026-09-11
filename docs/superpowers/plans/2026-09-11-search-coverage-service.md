# 真实任务搜索覆盖接线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development；整批一次独立审核，修复只差量复核，不重复全量测试。

**Goal:** 让普通采集任务详情直接显示已有运行窗口、各平台已上传来源统计与未查范围，不把无数据或执行完成误写成无需求/全网查完。

**Architecture:** 复用真实 collection task/run/platform、不可变 batch/observation/source/version 和原策略/画像；只读快照服务接既有 R4 SearchCoverage。无需重复建资源账本；尚未定义的搜贝换算不伪造，本批不开放 research 执行。

**Tech Stack:** FastAPI/PostgreSQL + Electron fixed API + existing React/Zod UI。

## Global Constraints

- 基线 `922d6b1448c9b8a8aac5b61e8fe1165c8a86a554`，复用隔离 `/tmp/yike-v02-scope.Pwf9Fs`，保护其它工作树。依据 `docs/UI_SEARCH_COVERAGE_CONTRACT.md`，不改完整 V0.2 Goal。
- 服务端 session 决定 tenant/owner；请求 expectedScope 仅一致性校验。每次查询单一只读 REPEATABLE READ 数据快照，读取前后验证实时会话；不跨所有者展开来源。固定 POST 仅查询、不触发任务/外部调用/计量写入，no-store，稳定脱敏错误。
- 返回精确 DTO：历史 profile_version_id + 数字版本、原策略 draft_revision；窗口使用 task.created_at/deadline_at，明确这是授权运行窗口不是实际在线时长，UTC 表示固定时刻，不冒充平台搜索时间过滤器。
- 每个已配置 platform_run 一个方向，展示原确认关键词范围。未记录逐关键词/页码结束证据时，即使 FINISH/SUCCEEDED 也只能 PARTIAL；未执行 NOT_STARTED、正在执行 RUNNING、取消/截止/部分结束 PARTIAL。未完成必须说明 unchecked。网络/登录失败未经服务端证据不能猜，默认 UNKNOWN；无结果不推导 NO_QUALIFIED。
- 原始计数仅用该 run/platform 的持久上传与观察：rawContents 为已接收观察条目，independentSources 按 source_id 去重，duplicates 为该范围重复来源观察数；它们不是平台浏览总量、请求数、买方数或线索价值。requests/newCandidates/confirmedOpportunities/pendingReviews 若没有完整依据返回 null；screening UNKNOWN 并解释未聚合复核。evidence 只取相同窗口的原版本正文，最多20个来源示例并明确限量，不截断数字统计。exclusions 空（没有业务筛选证据），usage null，recovery UNKNOWN，不提供未经证据的补查恢复授权。
- 查询只支持保留完整确认策略的真实任务；历史缺关联时明确 evidence_unavailable，不补假版本。读结果失配、过期、取消不返回空成功。既有列表、取消、原上传恢复保持不变。
- 只跑新增服务/受影响 DTO、UI、固定路由测试及一次 renderer build；真实 SQL 使用现有受限角色 fixture+真实签名 ingest；合成来源不表示真实平台/UAT/生产。

### Task 1: 真实覆盖只读服务（独立实现）

**Files:** 新增 `pilot/search_coverage.py`、`pilot/search_coverage_api.py`、`tests/test_search_coverage_postgres.py`；修改 `pilot/execution_runtime.py` feed 仅增加 `profile_version` 数字版本及必要限定测试。根负责 `pilot/ui_api.py` 和 desktop，不能碰这些文件。

**Interfaces:** `SearchCoverageService(store).query(claims, request_dict)`；`register_search_coverage_api(router, service, identity, require_session_https)` 注册 POST `/search-coverage`，正文直接为 shared SearchCoverageQuery，返回 CoverageSnapshot。类型以 `desktop/src/renderer/domain/searchCoverage.ts` 为准。feed 新增数字 `profile_version` 来自业务画像版本表，不从当前画像猜。

- [ ] RED：用现有受限 PG/real_strategy_env 创建确认策略、签名 START/CLAIM/ingest，调用缺失服务应失败；断言 query 身份/任务/画像绑定和观察重复计数。
- [ ] 最小 SQL 实现固定平台方向、真实窗口/版本和有界证据；例如 `counts.rawContents == COUNT(observation_id)`、`counts.independentSources == COUNT(DISTINCT source_id)`；任何无法证明计数保持 null。
- [ ] GREEN：完成上传仍 PARTIAL、无内容 UNKNOWN、多个观察同来源计为重复、不同评论独立；跨 owner/tenant 拒绝、profile绑定冲突、读取不增任务/观察；feed数字版本来自原画像。只跑本专项及feed受影响场景。
- [ ] 仅提交自己文件（先和根协调），报告 exact commands/RED/GREEN/边界到 git-dir/sdd/search-coverage-backend-report.md。

### Task 2: 普通客户端和真实任务详情接线（根）

**Files:** `desktop/src/shared/searchCoverage.ts`、`contracts.ts`、`taskFeed.ts`；`main/servicePolicy.ts`；renderer domain/shared query复用、services/searchCoverage.ts/client.ts、pages/tasks/SearchCoverage.tsx/NativeCollectionTasks.tsx；`pilot/ui_api.py`；新增专项测试及本计划/任务书链接。

- [ ] RED：服务调用必须先校验独立 session；固定 `coverage.query` POST `/api/ui/search-coverage`，跨空间/Abort/错绑返回拒绝。普通 native task 详情应出现覆盖入口，使用 feed 原画像数字版本；旧feed缺版本明确不可用。
- [ ] 接线：`createSearchCoverageService(transport, sessionGetter)` 复用 parseCoverageSnapshot；不把renderer domain导入main，query schema置shared。SearchCoverage只要求真实task identity/profile/platform字段和刷新依赖，不伪造旧TaskRun。原任务详情/恢复/取消保留。
- [ ] 运行受影响 vitest、tsc、一次renderer build；后端注册用限定API测试和真实HTTP客户端联验，不把FakeStore单测当真实SQL。
- [ ] 独立整批审核通过后文档记录准确边界、正常推送main并核对SHA。下一阶段仍是计量规则确认与quote/reserve/run/settle、平台完整度凭证和完整产品未完成项。

## 本轮顺序判断

搜贝未定义换算，不能直接开放类似研究启动。只读审计也确认 source batch/observation 和运行硬截止已有事实，重复创建原始账本会增加负担。因此先接已批准搜索覆盖可见入口，复用这些计量基础；没有缩减或宣告完成研究执行与完整Goal。

## 实施与验证

客户端/普通任务详情 `40baea2`；服务端 `33c6622`、截止与终态语义修复 `025f65d`。独立代码/架构/质量审核 **GO**，绑定 `025f65dda05a48edfdb35ea128c64cfdd94676d5`，无阻断项。

- 入口：线索采集 → 真实任务详情 → 搜索覆盖。使用原任务画像数字版本，不从最新画像猜版本；仍能取消任务、查询本机状态和恢复原上传。
- 只读快照按平台展示授权窗口、已确认方向、已接收原内容/独立来源/重复观察和最多20份原文示例。没有完整范围、筛选或搜贝依据时显示未知；不会因任务完成就称全网查完，也不因访问未知说没有需求。
- 受影响5个前端测试文件 **40 passed / 3.45s**；类型检查通过；一次 renderer build **通过 / 326ms**。API注册专项 **1 passed**（仅证明认证/no-store/没有store调用）。初始3个缺适配反例、原任务详情缺入口、API404均先失败后修复。
- PostgreSQL/Feed专项 **7 passed / 5.81s**。实际使用受限角色、确认策略和签名 START/CLAIM/两批 ingest/FINISH；内含普通 Node24 client → HTTP/session → PostgreSQL，核对 **3次观察、2个独立来源、1次重复观察**、精确原文、画像/身份拒绝和退出失效，无 skip。来源与平台策略为合成输入，不是实际社媒采集。
- 命令：配置一次性测试库 `YIKE_IDENTITY_TEST_DATABASE_URL` / `YIKE_IDENTITY_TEST_APP_DATABASE_URL` 与 `YIKE_DEVICE_LIVE_NODE_BINARY`，运行 `python -m pytest -q tests/test_search_coverage_postgres.py tests/test_execution_feed_postgres.py`。无需平台登录，不记录凭据，不重跑全量套件。

本批不包含搜贝兑换、quote/reserve/run/settle、逐关键词结束凭证、筛选全量聚合、Windows、真实平台或生产/UAT验收；完整Goal继续ACTIVE。后续复用现有事实与本入口，不重建原始上传账本。

非阻断遗留：旧任务缺历史策略关联时目前返回 `task_not_found`，尚未细化成计划中的 `evidence_unavailable`；同样拒绝伪造证据，不影响有完整记录的正常路径。后续统一缺证据提示时处理，本轮不为该提示重复构包或测试。

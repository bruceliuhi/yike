# 定向公开板块研究 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. 按用户要求一批定向验证和一次独立整批审核。

**Goal:** 用户选择现有公开板块后能够完成对应索引研究，不再被固定最新索引阻止。

**Architecture:** 来源来自冻结策略，固定目录约束网络与提交；新能力显式协商，旧任务和无参数能力原样兼容。已有签名执行、资源配额和事务复用。

**Tech Stack:** Python/FastAPI/PostgreSQL，TypeScript/Zod/React/Electron。

## Global Constraints

设计以 `docs/superpowers/specs/2026-09-12-targeted-public-research-design.md` 为准。单源索引、每次 advance 一个新效果；不重试 UNKNOWN、不改价格、不部署、不访问无关账号或服务器；保留旧 latest 摘要和 v1 状态。新节点不声称读取评论。

### Task 1: 后端定向读取与权威绑定（独立实现者）

Files: `pilot/research_public_reader.py`, `pilot/research_candidates.py`, `pilot/research_runtime.py`, `pilot/research_runtime_config.py`, `pilot/research_execution_api.py`，必要的新 `pilot/research_source_catalog.py` 和 `app/windows_portable_inventory.py`；对应 `tests/test_research_*`。

- [ ] 先增加失败测试：qna 策略可执行；查询目录精确成功；带 outsourcing node 的 qna 返回拒绝；qna 原文提交到 latest 任务拒绝。运行 `uv run --frozen --extra dev pytest tests/test_research_runtime_config.py tests/test_research_execution_api.py -q` 观察预期失败。
- [ ] 固定目录入口 `research_source(source_id)` 只接受上述三枚 ID；descriptor 包含 endpoint/input_sha/sample_kind/collector/scope/label/version。latest 原值保持。从任务已绑定策略获取来源，读取前及 commit 事务内均核对；不得只检查允许名单。
- [ ] 读取器默认 latest 兼容内部既有调用，生产 ResearchCandidateStore.read_public 必须从权威任务派生来源。每个节点固定 URL、node.name 校验。`run_resource`/`commit_index` 使用相同来源摘要，入库 collector 不错标。
- [ ] `capability(claims, *, source_catalog_version=None)` 保留原无参形式；显式版本1返回设计精确 v2 对象。runtime 状态从 inspect 的任务快照给出真实来源，不改变旧 latest DTO。查询只读，非法 query 拒绝。
- [ ] 新节点受限 PG 路径运行确认→报价→START→原文→模型→完成与恢复，验来源 provenance/原 action 不重读、跨源提交拒绝。保存脱敏 HTTP/DTO fixture 到 `/tmp/yike-targeted-research-http.json` 给主代理消费；禁止保存令牌、签名或 DSN。
- [ ] 运行改变文件相关测试；报告路径 `/tmp/yike-targeted-research-backend-report.md`，说明 RED/GREEN、命令/结果、未完成。实现者不 commit/push，勿修改 desktop、台账或其他代理文件。

### Task 2: 客户端能力与可操作路径（主代理）

Files: `desktop/src/shared/researchRuntime.ts`, `desktop/src/shared/researchStrategies.ts`, `desktop/src/main/servicePolicy.ts`, `desktop/src/renderer/services/researchRuntime.ts`, `desktop/src/renderer/pages/TaskWizard.tsx`, `desktop/src/renderer/pages/tasks/PublicSourceSelector.tsx`, `DesktopExecutionRequests.tsx`；对应 desktop tests。

- [ ] 失败测试：旧 v1/新 v2 目录和状态精确解析；不允许错配 label/version/scope；IPC 只接受 `sourceCatalogVersion:1`；旧服务422仅一次只读降级，其他失败原样报错。
- [ ] 新目录能力和新状态用明确 Zod 分支定义，`researchAllowsSource(capability,source)` 旧 capability 只接受 latest，新 capability 按目录。renderer 请求 payload `{sourceCatalogVersion:1}`；主进程映射为固定 query，fallback 无参数仍走同一受保护 transport。
- [ ] 删除本地策略 qna/outsourcing 研究的固定拒绝；向导和启动前 fresh capability 都检查所选来源；下拉显示各板块研究专属限制，不自动换源。恢复请求行使用“所选公开板块，具体范围见研究进度”而非伪造最新标签。
- [ ] 运行 `node node_modules/vitest/vitest.mjs run tests/researchRuntime.test.ts` 与相关 UI/策略测试，`node node_modules/typescript/bin/tsc --noEmit`；消费后端实际输出。默认不重新全量构包。

### Task 3: 整批审核与集成（主代理＋独立审核者）

- [ ] 冻结产品提交；独立架构/代码/质量审核基线 `8da6d87` 到该提交，不让实现者批准自己。
- [ ] 阻断项定向修复/复审；唯一实施任务书记实际证据和保留缺口，不创建第二套完成台账。
- [ ] fetch 核对 main 无冲突后 ff 合并、push、核实本地/远端 SHA；保留 Goal ACTIVE。

## Evidence

产品候选 `d564cec0ec719bf4f17f3ae35eebfa3087a69541`；独立架构/代码/质量整批审核 **GO（仅代码集成）**，无可复现 P0/P1/P2 阻断。审核者未参与实现，检查了来源选择→报价/START→冻结快照→读取/提交→恢复与客户端展示/兼容，并复用上述受限验证，无重复全套构包。Task 1/2 实现与定向验证完成，后续文档提交不改变本产品字节。未部署、未构包、未做真实平台或客户验收。

- 后端初次 RED 4 failed/43 passed：节点 policy、目录 query、节点读取器尚不支持。另有跨来源入库错误类型 RED；补正后双向串源均拒绝且不写候选。测试工具曾出现括号、会话签名绑定和独立脚本 import 问题，修正后重新执行，不计作业务成功。
- 后端相关联合验证 141 passed（118.52秒，受限 PostgreSQL 包含在内、无 skip）；相邻判断/策略/报价合同 281 passed；末次 reader/config/API 差量 48 passed。运行器只使用自有 `yike-research-resources-task1-pg` 的 `yike_public_sampling_task1`，管理员迁移与非超级用户应用角色分离。
- 两个新节点均通过已确认策略→真实报价接口→签名 START→固定索引原文入库→模型判断入库→完成；重建 runtime 恢复不重复读取。这里“真实接口”是本地受认证 FastAPI TestClient 与受限 PG；来源及模型内容是合成 fixture，不是实网采集/TLS部署或商业效果。最终导出差量 2 passed/10 deselected。
- 客户端初次合同 RED 3项、选择/策略 RED 4项；完整向导再发现 domain/task 的 latest-only 阻断3项，修复后定向25 passed。确认页仍错误沿用普通采集的评论范围，经新增3项失败用例修复，末次向导与摘要16 passed；其他对应合同/策略/选择/进度用例通过，`tsc --noEmit`退出0。没有重复全量测试或构包。
- 实际后端 DTO 脱敏导出 `/tmp/yike-targeted-research-http.json`（21:36:37），SHA256 `780b05f31b6cb5625b31bfb8242a2c74b14cce32d467798f1401b0ff4cb08595`。客户端21:36:45以 `YIKE_TARGETED_RESEARCH_HTTP_ARTIFACT=/tmp/yike-targeted-research-http.json node node_modules/vitest/vitest.mjs run tests/targetedResearch.http.test.ts` 经正式 main service/renderer parser 消费，2 passed；其中回放基线真实 capability handler 的422，确认仅一次无参数只读降级。回放网络不冒充真实平台调用。
- 后端 `HOST_FILES` 不打包研究服务模块，故无需把新服务端目录模块塞入 Windows host；无新迁移。部署说明已更新，生产启用与收费参数仍需原有批准。

完整多源编排、跨平台研究/覆盖补查、评论深读、其它平台持续游标、Windows新包/生产/真实客户闭环仍未完成；本批不关闭这些任务，也不改变 V02_FULL_SCOPE_ACTIVE。

# 公开板块来源 Implementation Plan

> **For agentic workers:** 使用 superpowers:subagent-driven-development；根串行Git，后端与客户端按文件隔离，一次整批独立审核。

**Goal:** 普通用户选择V2EX最新或问与答板块后，所选来源贯穿确认、实际读取、候选及定时抽样。
**Architecture:** 扩展现有固定公共来源ID及可选能力目录；原策略、设备、执行、上传、监控链全部复用，不新建任务系统。
**Tech Stack:** Python/Pydantic/PostgreSQL、Electron/TypeScript/Zod/React。

## Global Constraints

以[已细化合同](../specs/2026-09-11-public-node-discovery-design.md#确定合同)为准。基线7394ecc；只扩普通采集，原搜贝研究仅最新索引。两固定ID为 `v2ex-latest-v1`、`v2ex-qna-v1`；新部署模式 `four-platform-public-node-monitor-v1`，旧模式范围不变。可选 `public_sources` 必须非空/无重复/含旧默认；本机对应 `sourceIds`，保留 `sourceId` 默认字段。没有目录时只允许默认来源。一次任务只选一个，来源变化使确认失效；固定HTTPS、1MiB/20秒/记录预算、同driver两源共享60秒冷却、无重试/翻页/跳转。不会自动部署、发送、激活试用或重复构包。只跑改动相关测试。

### Task 1: 后端合同、能力与普通HTTP/PG（独立实现者）

**Files:** `pilot/research_strategy_contract.py`、`pilot/foreground_collection.py`、`pilot/monitor_runtime.py`；新增 `tests/test_public_node_collection.py`；可扩现有 `tests/test_public_community_http_postgres.py`、`tests/test_public_monitor_postgres.py` 作为新片集成验证，不修改其它测试fixture来掩盖失败。

**Interfaces:** `publicSource: Literal['v2ex-latest-v1','v2ex-qna-v1'] | None`。新增 `four_platform_public_node_monitor_policy`，模式查找/foreground support/monitor support及monitor reserve平台允许集合均注册。新模式返回旧default及 `public_sources=['v2ex-latest-v1','v2ex-qna-v1']`；foreground仍返回 `public_monitor=True`。旧模式不返回新字段。

- [x] RED，新增定向测试观察QNA未被解析/新模式不存在；覆盖旧模式拒绝、新模式单次/合法日程允许、非法链接/账号/研究不允许。
- [x] 最小接线：普通PUBLIC_WEB解析后校验固定枚举；不把QNA改写成latest再计算摘要。新模式对原生平台委托四平台monitor政策。原 `_monitor_policy` 执行方式校验复用。研究配置明确拒绝QNA，旧无publicSource序列化不变。
- [x] 新测试加已受影响source policy/monitor合同测试一次；独立PG实际prepare/confirm/get保存QNA来源，旧模式执行拒绝/新模式可用。来源更改生成新摘要，不使用管理员直接造确认快照。
- [x] 报告 `/tmp/yike-public-node-backend-report.md`，含RED/GREEN命令和限制；不自行Git提交/部署，根统一合并。

### Task 2: 完整客户端（根）

**Files:** 新 `desktop/src/shared/publicSources.ts`；现有 `shared/{foregroundCollection,researchStrategies}.ts`、`main/{foregroundCollectionController,publicCommunityDriver}.ts`；renderer `domain/{models,task,researchStrategies,monitorCollection}.ts`、`app/taskDraft.ts`、`pages/TaskWizard.tsx`、tasks确认/详情/监控文件；相关定向测试。

**Interfaces:** 固定ID schema/标签/端点集中在 `publicSources.ts`。`publicSourceIdsSchema`和目录一致性函数用于strict capability与binding；`supportsPublicSource(support,source)`只消费经校验目录。`TaskDraft.publicSource?`保留显式来源；普通strategyPrepare只在web时绑定 `draft.publicSource ?? 'v2ex-latest-v1'`。

- [x] RED：QNA草稿/来源能力/driver用例，旧能力不能采用新选择；未知ID、空/重复目录、目录无default拒绝。
- [x] 扩shared字段及main capability/开始/恢复/监控校验到目录成员判断，不按等于默认判断；新字段缺失保持旧行为。主进程共享driver实例不变。
- [x] driver取已确认sourceId的固定URL；QNA每项验证node.name，来源版本写入collector_version。输出同external_source_id，原node/作者字段仅按已用映射处理；未知源在GET前拒绝。
- [x] 原页面web选项下加来源选择器，选项来自真实能力；旧稿默认首页，原选不可用显示明确阻断而不静默回退。草稿/模板恢复保留publicSource；变更使用现有revision/确认失效。确认/详情/监控描述使用所选标签。
- [x] 定向driver+shared+草稿/模板+监控+选择器测试和一次tsc，不跑全量。后端来件后现有HTTP/PG/Node入口扩QNA及同ID重复观察；隔离库可用时跑该条整链。

### Task 3: 接收与发布边界（根＋非作者审核）

- [x] 对照合同检查实际路径，记录定向结果和未验项；网络仅受控实际driver的一次QNA读取，不再做裸URL探测，不发消息。
- [x] 绑定代码提交，交非作者整批代码/架构/质量审核；阻断项修复后仅差量复查。
- [ ] 更新本计划证据/唯一任务书，push main并核对远端SHA；保持冻结邀请候选fbf9f94及当前线上模式不变。

## Evidence

源码 `566e810`；下列为2026-09-11本地隔离验证，不是生产/Windows/客户验收。

- Task 1/2 已实现。后端RED 7 failed/1 passed；定向合同80 passed，QNA监控隔离PG三轮1 passed；普通HTTP＋受限PG＋实际Node控制器两来源3 passed，无跳过。合成重复任务保持同source/candidate/version，仅新增观察与批次。
- 客户端初始核心RED 4 failed/35 passed；driver、renderer、controller、选择器、快照5文件92 passed。补模板/确认页/监控3文件16 passed，tsc通过。普通模板原会强制打开研究，独立RED复现后移除；测试用户隔离避免本机会话缓存串扰。未运行全量套件或构包。
- 实网只执行一次QNA固定源GET，通过实际driver、正常START/CLAIM/上传/FINISH与隔离PG；`PUBLIC_COMMUNITY_CHECK {"collectorVersion":"v2ex-qna-v1","mode":"network","records":9,"sourceId":"v2ex-qna-v1","sourceReads":1,"tasks":1}`，1 passed in 6.43s。只证明原文入库，无模型判定/意向/联系方式有效性结论，不将9条计作9商机。
- 来源切换需重新确认；旧服务目录拒绝QNA；恢复同请求不追加GET；同driver跨两来源仍共享60秒冷却。新任务重复观察测试通过新控制器生命周期运行，非运行中绕过冷却。
- 当前未部署、未构包、未外发、未发短信或激活账号。邀请候选/生产仍fbf9f94，生产旧mode不启用公开来源。搜贝研究来源范围不变；Windows与真实客户效果继续待验。
- 非作者 `public_scope_review` 独立整批审核固定源码 `566e810eb605875a27d7a7a8e27c17fb2d756c58` 及三份文档接续：PASS / GO（限定源码集成），无具体阻断项；未重复运行测试、构建或网络。本地报告 `/tmp/yike-public-node-backend-report.md`、`/tmp/yike-public-node-review.md`（本节保存可移植结果，不依赖这些临时文件）。

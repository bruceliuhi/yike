# 公开社区定时抽样接线

> 执行：subagent-driven-development；用户2026-09-11已授权在批准V02内自行细化技术方案，不再逐片等待确认。独立审核按完整批次进行。

**Goal:** 普通客户能创建并确认V2EX近期主题监控，由当前设备按既有日程执行，结果进入既有候选/原文/版本/观察链。
**Architecture:** 复用MonitorRuntime预留、签名START/CLAIM、共享采集槽、原请求恢复、候选去重；固定latest驱动不递归访问。新增显式部署模式，旧公开单次模式保持原行为。无数据库迁移、无新调度器、无发送。
**Tech Stack:** 现有Python/PostgreSQL、Electron/TypeScript、固定官方HTTPS JSON驱动。

## 约束与合同

- 新配置值 `four-platform-public-sampling-monitor-v1`。旧`four-platform-public-monitor-v1`仍只允许公开源单次采样；四原生平台行为不变，默认不启新模式。
- 新模式的foreground support保持mode=`four-platform-foreground-v1`、public_source=`v2ex-latest-v1`，另加`public_monitor:true`。monitor support保持mode=`four-platform-monitor-v1`，另加public_source=`v2ex-latest-v1`。旧模式不增加字段；旧客户端不得配套新模式上线。
- 客户端publicBinding增加可选`monitorSupported:true`，只由服务端明确public_monitor获得；缺字段不是支持监控。public-only不要求Python、平台账号或profile，仍要求真实服务身份和同一设备；混合任务逐原生账号核验，串行共用预算。
- 只允许确认配置中的publicSource=`v2ex-latest-v1`、search、无links/research；monitor必须policyVersion1的有效日程。保留原快照/哈希，不把monitor请求改写成once提交。
- 驱动默认仍拒绝monitor；主进程从已验证监控路径显式传`allowMonitor:true`，复用同一驱动实例的60秒冷却。一次轮次只有一次GET，100条/1MiB/20秒上限、取消和不重试规则不变。周期最短沿既有1小时；离线/繁忙不补跑。
- 已读内容的原发布时间不更新；变化产生新版本，重复只增加观察，不能计作新需求或新商机；读取失败不当无新增。最新列表中消失不推断需求关闭。界面明确“V2EX近期主题定时抽样，不覆盖历史/全站”。
- 无真实平台/Windows/生产证据时如实保留未验状态，不以合成输入或本机测试称上线。搜贝规则不在本批决定。

## Task 1：后端能力与预留接收（root）

Files: `pilot/foreground_collection.py`、`pilot/monitor_runtime.py`、`tests/test_public_collection_policy.py`；复用现有monitor PG测试。

- [x] 先增加新配置与monitor有效/无日程/错误来源/账号冒用/旧模式拒绝反例，跑目标测试确认RED。
- [x] 新policy对公开源复用 `_monitor_policy(..., four_platform_public_monitor_policy)`，原生源复用four_platform_monitor_policy；support仅该新函数身份增字段。
- [x] 运行 `python -m pytest -q tests/test_public_collection_policy.py tests/test_monitor_runtime_api.py tests/test_foreground_collection.py`，保留旧断言，检查新配置不修改快照。再用专用PG验证新公开目标能经过既有预留/START/CLAIM及多轮去重，不触及现有库。

## Task 2：普通客户端监控闭环（独立实现Agent）

Files: `desktop/src/shared/foregroundCollection.ts`、`desktop/src/main/{foregroundCollectionController,publicCommunityDriver,monitorCollectionController}.ts`、`desktop/src/renderer/domain/{task,monitorCollection}.ts`及必要现有TaskWizard/NativeMonitorPlans文案；对应定向tests。

- [x] 写RED：旧公开binding不能监控；新绑定可生成PUBLIC_ANONYMOUS/null连接目标；同设备public-only和混合可执行，不同设备/来源失配/旧support拒绝。
- [x] support严格识别上述增量；普通CAPABILITIES传monitorSupported；monitor validate/start按PUBLIC_ANONYMOUS分支验证配置和当前服务声明，跳过native探测但不跳过设备/策略；驱动通过显式allowMonitor复用同一实例。非monitor路径不能滥用该开关。
- [x] 贯通现有创建/接管/轮次路径与来源文案。测试真实controller-worker-driver组合（模拟外部HTTP，仅技术证据），覆盖两轮、取消、恢复不重采、旧模式和原生回归；明确新来源/变化/重复按既有候选账本统计，不自行新增乐观计数。
- [x] 目标Vitest与tsc通过，非作者审核整批差量；root统一提交到main，客户端Agent不自行push、不改后端文件/数据库、不另建页面。

## 本批完成条件

来源能力→普通监控创建与确认→到期预留/执行→候选/版本/观察的技术闭环有证据；保留旧单次/原生行为、取消/恢复/设备隔离反例。本批不等于完整MP-03/Goal完成，后续仍需真实平台多轮、Windows、部署和跨行业质量验证。

## 实施与验证

- Python先验RED：新增13项因部署模式不存在失败；实现后policy/support/API定向61项通过。真实PG链路另发现`MonitorRuntime.pulse`仍写死三平台，已按显式部署policy身份补齐四平台和公开源资格，旧模式不放开公开monitor。
- 隔离临时PostgreSQL使用完整迁移/授权清单、NOLOGIN/NOSUPERUSER/NOBYPASSRLS运行角色。`tests/test_public_monitor_postgres.py`一项三轮链路通过：真实策略确认→监控预留→设备签名START/CLAIM→候选入库→FINISH→回读；旧公开单次policy拒绝同一monitor。合成输入得到2条来源、3个正文版本、5次观察、3个批次、0个平台连接、0条商机，回执重放不新增观察，原始发布时间不刷新。
- 上述PG测试仅在专用loopback临时库执行，测试推进到期窗口，不证明真实1小时平台调度；无外网读取、真实模型、生产身份或Windows证据。新mode默认关闭，部署必须配套新客户端与新服务镜像；32c9c0c旧候选不包含本批代码。
- 客户端先验RED为5项预期失败/68通过；实现后7文件96项通过，`tsc --noEmit`通过。定向文件：`publicCommunityDriver`、`foregroundCollectionController`、`publicCollectionRenderer`、`monitorCollectionController`、`monitorCollectionRenderer`、`monitorCollectionDomain`及`ui/task-domain`。含真实controller-worker-driver的模拟HTTP/CLAIM/upload/FINISH、混合串行、旧声明拒绝、同实例单次→监控冷却、两轮驱动及已有取消/恢复反例。没有重新运行全量测试或构包；客户窗口与真实平台另验。
- 非作者`release_candidate_review`对`001741f..a656c60540f8ae78b2e9863436cb1491e9497dff`给出限定GO，无阻断P1/P2；核对创建/接管入口、资格/快照/预留、旧模式/原生兼容、恢复不重采、同实例冷却及重复观察边界。独立仅复测policy36项（通过）及差量格式；未重复整组客户端/PG、构包或实网。不代表生产发布许可，后续产品代码改动须复审差量。

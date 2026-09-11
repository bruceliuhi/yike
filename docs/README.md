# 意客AI 文档索引

运营后台与三天试用：新增 `/ops` 独立服务，管理员查看完整手机号、签发/重发/停用专属试用码；客户真实短信验证后激活，默认72小时。[运行与部署说明](../deploy/OPS_ADMIN.md)，[实施与限定证据](plans/2026-09-11-ops-trial-admin.md)。代码交付不等于已部署或短信收码完成。

**当前范围更新（2026-09-10）：** 用户要求恢复原规划完整 V0.2 全量推进，状态 `V02_FULL_SCOPE_ACTIVE`；此前精简安排及 `FULL_V1_DEFERRED` 只保留历史。完整范围见[产品计划第1.0节](V02_COMMERCIAL_RELEASE_PLAN.md#10-当前执行完整-v02-全量推进2026-09-10)，实际接续和待审工作见[实施任务书顶部](V02_IMPLEMENTATION_TASKBOOK.md)。

2026-09-09 起，跨行业完整获客版是当前产品目标；对外版本定为 V1.0 首个正式商用版，V1.1 为上线后增强且尚未启动。既有 `V02-*`/`MP-*` 编号继续用于工程追踪，不大规模重命名；详见 [V1 版本映射](V1_VERSION_MAPPING.md)。用户已明确首发面向所有行业企业，取代服务商/展台优先范围。现有客户试用与旧双平台 MVP 是实现基础。文件标题中出现“首版”“不自动发送”等旧表述时，先核对适用版本，不据此删除当前范围；历史展台样本及审核不改写为跨行业验收。

产品代码统一归入 `yike-ai2026/main`；`yike-ai` 暂时只读，治理文档迁移及归档留待产品稳定后执行。接续开发先读[仓库工作流](REPOSITORY_WORKFLOW.md)。

产品规划、销售介绍和宣传准备先看[产品手册：功能、版本与对外口径](PRODUCT_HANDBOOK.md)。它汇总完整功能、用户已批准的 V1.0/V1.1 划分、带版本的能力快照和宣传证据入口；不是已发布清单，也不取代下述产品计划与唯一实施状态台账。

## 正式开发文档

| 顺序 | 文档 | 职责 |
|---|---|---|
| 1 | [AUTHORITY](../AUTHORITY.md) | 产品目标、权威顺序、品牌、人工确认与数据安全边界 |
| 2 | [V1.0 / V02 完整获客版计划](V02_COMMERCIAL_RELEASE_PLAN.md) | 功能范围、付费闭环、任务设计与完整交付标准 |
| 3 | [多平台 Skill 方案](V02_MULTIPLATFORM_SKILL_PLAN.md) 与 [设计入口](../design/README.md) | 技术与视觉规范，不能改变上层功能范围 |
| 4 | [V1 版本映射](V1_VERSION_MAPPING.md) | V1.0/V1.1 边界、六组增量与 V02 工程任务映射；不维护进度 |
| 5 | [V1.0 / V02 实施任务书](V02_IMPLEMENTATION_TASKBOOK.md) | 唯一的当前实施状态台账；记录下一步、依赖、实现提交和验收证据 |
| 6 | [客户试用计划](CUSTOMER_PILOT_PLAN.md)、现有运行手册与历史审核 | 说明已有实现及受控运行路径，不覆盖上层目标与实施状态 |

产品计划的 V02 编号是任务定义，MP 编号是其多平台子项；[双 AI 任务板](DUAL_AGENT_TASKBOARD.md)定义 V02 小卡、建议主责、具体依赖与验收命令，不单独维护状态。实际认领、候选/集成 SHA、reviewer 与接收 ACK 只更新实施任务书，不维护两套完成状态。

共同产品 Goal 见 [AUTHORITY](../AUTHORITY.md)，CodexWin/CodexMac 执行目标及交接约定见[双 AI 协作任务板](DUAL_AGENT_TASKBOARD.md)。五类业务各两家企业、14 天试用及配置/效率/证据门槛统一在产品计划维护；文档目标不等于已启动另一任务、已设置自动唤醒或已完成产品。

[当前整合状态](INTEGRATION_STATUS.md)记录已迁入的 Skill、桌面壳、提交 SHA、验证结果和明确未整合内容，供后续 AI 接续工作时先行阅读。

原始候选服务交接见[02B上传/收件箱合同](contracts/V02_RAW_CANDIDATE_INBOX.md)和[独立验收](qa/V02_CANDIDATE_INGESTION_REVIEW.md)：在02A与执行护栏之上提供原文/版本/观察、原键重查及待判断列表，不是已评分商机DTO，也不表示真实平台或客户闭环已接通。

整体视觉基准是[20 页完整设计 R3](../design/v02-suite-r3/README.md)，当前增量是已获实现授权的[R4 六组设计](../design/v02-suite-r4/README.md)。R4 六组前端及搜贝交互已落入候选 `cbc6170`；实现、独立审核、分版本测试与 Mac 包证据见 [R4 验收](qa/ui-r4/README.md)，同状态截图和视口结果见[设计验收](../design-qa.md)。[R3 UI 实施记录](UI_R3_IMPLEMENTATION.md)保留既有历史。可选服务合同与隔离 TEST 场景不代表真实后台、平台、收费或 Windows 已验收，完整 Goal 仍在推进。

## R4 前端服务交接

以下合同说明已实现界面需要消费的服务、绑定校验与失败边界，供原责任子卡接入；不是生产接口已上线清单。缺可信账户空间或服务能力时，新路径明确不可用，既有可用服务路径继续保留。

| 合同 | 页面与重点 |
|---|---|
| [研究用量与搜贝](UI_RESEARCH_USAGE_CONTRACT.md) | P06/P19/P20：预计、最多、实际用量；版本化估算和原子启动、未知预留保护，不定义售价或余额 |
| [搜索覆盖](UI_SEARCH_COVERAGE_CONTRACT.md) | P09：运行/画像/窗口绑定，搜索完整度与筛选结果分开，未知统计不填零 |
| [覆盖补查与调整](UI_COVERAGE_PLAN_CONTRACT.md) | P09：暂停追加须新确认；终态转新草稿保留来源；未知请求恢复，不自动恢复执行 |
| [机会研究](UI_OPPORTUNITY_RESEARCH_CONTRACT.md) | P10/P11：需求分类、同来源证据时间线、已认可机会的类似研究草稿；公开样例不入客户库或发送 |
| [短句教练](UI_SHORT_COACH_CONTRACT.md) | P12：证据与可联系性约束、人工草稿保护、确认保存及未知恢复，发送仍走既有确认路径 |
| [机会简报](UI_OPPORTUNITY_BRIEF_CONTRACT.md) | P02：账户空间、业务日/时区与画像版本快照；只读导航到已有机会及跟进 |

## 当前可运行基础与部署

| 文档 | 适用范围 |
|---|---|
| [客户试用计划](CUSTOMER_PILOT_PLAN.md) | CP-01～CP-06 的既有实现与部署门禁，不是 V0.2 全部任务 |
| [客户试用运行手册](CUSTOMER_PILOT_RUNBOOK.md) | 当前已实现的管理员 provisioning、会话、复核包导入与人工跟进 |
| [应用部署说明](../deploy/README.md) | 现有服务端容器、连接隔离与生产运行要求；不是桌面发行说明 |
| [CP-06 验收模板](DEPLOYMENT_ACCEPTANCE_CP06_TEMPLATE.md) | 目标服务器、HTTPS、RLS/ACL、备份恢复、回滚与手机实测 |

运行手册只新增已经实现并验证的步骤。计划中的 API、命令和平台能力在落地前不能作为客户操作说明。

## 历史、研究与溯源

- [设计交接](V02_DESIGN_HANDOFF.md)：迁入基线与演示分支差异；当次能力快照不替代当前任务进度。
- [CP-01 证据](CP01_EVIDENCE.md)、[CP-04 浏览器验收](BROWSER_ACCEPTANCE_CP04.md)、[CP-05 质量审核](QUALITY_REVIEW_CP05.md)：各自提交/环境的历史结果，不给 V0.2 新增功能背书。
- [Skill 研究验证](SKILL_VALIDATION_CP05.md)、[展台研究记录](SKILL_VALIDATION_EXHIBITION_CP05.md)：真实来源与判断样本，不能代替自动采集和持续监控运行。
- [旧双平台运行手册](RUNBOOK.md) 与 [旧人工导入设计](superpowers/specs/2026-08-11-manual-intake-discovery-mvp-design.md)：仅用于理解和复用旧代码，不再决定客户产品范围。

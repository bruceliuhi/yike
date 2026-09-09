# 意客AI 文档索引

2026-09-09 起，跨行业完整获客版是当前产品目标；对外版本定为 V1.0 首个正式商用版，V1.1 为上线后增强且尚未启动。既有 `V02-*`/`MP-*` 编号继续用于工程追踪，不大规模重命名；详见 [V1 版本映射](V1_VERSION_MAPPING.md)。用户已明确首发面向所有行业企业，取代服务商/展台优先范围。现有客户试用与旧双平台 MVP 是实现基础。文件标题中出现“首版”“不自动发送”等旧表述时，先核对适用版本，不据此删除当前范围；历史展台样本及审核不改写为跨行业验收。

产品代码统一归入 `yike-ai2026/main`；`yike-ai` 暂时只读，治理文档迁移及归档留待产品稳定后执行。接续开发先读[仓库工作流](REPOSITORY_WORKFLOW.md)。

## 正式开发文档

| 顺序 | 文档 | 职责 |
|---|---|---|
| 1 | [AUTHORITY](../AUTHORITY.md) | 产品目标、权威顺序、品牌、人工确认与数据安全边界 |
| 2 | [V1.0 / V02 完整获客版计划](V02_COMMERCIAL_RELEASE_PLAN.md) | 功能范围、付费闭环、任务设计与完整交付标准 |
| 3 | [多平台 Skill 方案](V02_MULTIPLATFORM_SKILL_PLAN.md) 与 [设计入口](../design/README.md) | 技术与视觉规范，不能改变上层功能范围 |
| 4 | [V1 版本映射](V1_VERSION_MAPPING.md) | V1.0/V1.1 边界、六组增量与 V02 工程任务映射；不维护进度 |
| 5 | [V1.0 / V02 实施任务书](V02_IMPLEMENTATION_TASKBOOK.md) | 唯一的当前实施状态台账；记录下一步、依赖、实现提交和验收证据 |

产品计划的 V02 编号是任务定义，MP 编号是其多平台子项；[双 AI 任务板](DUAL_AGENT_TASKBOARD.md)定义 V02 小卡、建议主责、具体依赖与验收命令，不单独维护状态。实际认领、候选/集成 SHA、reviewer 与接收 ACK 只更新实施任务书，不维护两套完成状态。

共同产品 Goal 见 [AUTHORITY](../AUTHORITY.md)，CodexWin/CodexMac 执行目标及交接约定见[双 AI 协作任务板](DUAL_AGENT_TASKBOARD.md)。五类业务各两家企业、14 天试用及配置/效率/证据门槛统一在产品计划维护；文档目标不等于已启动另一任务、已设置自动唤醒或已完成产品。

[当前整合状态](INTEGRATION_STATUS.md)记录已迁入的 Skill、桌面壳、提交 SHA、验证结果和明确未整合内容，供后续 AI 接续工作时先行阅读。

当前视觉基准：[20 页完整设计 R3](../design/v02-suite-r3/README.md)。整套图册与关键状态已于 2026-09-09 获得实现授权；当前按图开发与逐页对照，进度见 [R3 UI 实施记录](UI_R3_IMPLEMENTATION.md)，不能把设计完成记成业务功能完成。

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

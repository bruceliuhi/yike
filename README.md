# 意客AI

面向服务商的商机工作台：从多平台真实需求发现、证据判断，走到确认后触达、回复与跟进。

**产品代码统一提交到 `yike-ai2026/main`。** 小范围串行改动直接在 `main` 验证、审核与提交；较大或并行开发才使用短期 `codex/<主题>` 分支，完成后合并清理。`yike-ai` 暂时为只读权威文档仓库；后续迁移安排见[仓库工作流](docs/REPOSITORY_WORKFLOW.md)。

当前开发目标是 **V0.2 完整获客版**。现有代码具备客户试用的画像、研究包导入、机会证据与人工跟进基础；新增平台连接、采集、持续监控、真实收发及 Windows 交付尚待完成，不将本说明视为已支持清单。

## 从这里开始

1. [产品与开发权威](AUTHORITY.md)：本轮确定的产品目标和必须继承的约束。
2. [实施任务书](docs/V02_IMPLEMENTATION_TASKBOOK.md)：当前状态、可以先做的工作、依赖与验收。
3. [完整获客版计划](docs/V02_COMMERCIAL_RELEASE_PLAN.md) 与 [多平台 Skill 方案](docs/V02_MULTIPLATFORM_SKILL_PLAN.md)：功能及技术分工。
4. [设计入口](design/README.md)与[20 页完整图册](design/v02-suite-r3/README.md)：八入口蓝白设计、关键状态与组件规范；整套已于 2026-09-09 获得实现授权，当前按 R3 开发。
5. [文档索引](docs/README.md)：正式文档、运行说明和历史证据的关系。

本轮已完成的选择性整合、提交 SHA、验证命令和未整合旧分支见 [当前整合状态](docs/INTEGRATION_STATUS.md)。后续 AI 先读该文件，避免重复搬运旧自动回复分支或把规则包误认为运行时。

当前代码的运行方式见 [客户试用运行手册](docs/CUSTOMER_PILOT_RUNBOOK.md)。这条受控路径还需要管理员提供访问令牌和已复核研究包，不是 V0.2 最终使用体验。旧 `app/` 双平台采集器属于复用来源，尚未接入 `pilot/` 客户数据流程。

用户已明确授权按整套 R3 图册及关键状态启动前端、交互、适配与客户端开发，授权基准和范围见[确认记录](design/v02-suite-r3/APPROVAL.md)。当前实现及运行证据见 [R3 UI 实施记录](docs/UI_R3_IMPLEMENTATION.md)；实现授权不代表页面或业务能力已验收。接口、存储、Skill 和执行器可以并行推进。缺少生产环境只阻止相应部署验收，不阻止整个产品开发。发布条件以任务书与 [CP-06 验收模板](docs/DEPLOYMENT_ACCEPTANCE_CP06_TEMPLATE.md) 为准。

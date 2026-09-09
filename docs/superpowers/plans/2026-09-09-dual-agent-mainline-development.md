# V0.2 双 AI 主线协作 Implementation Plan

> **执行定位：V0.2 协作建议，进度与编号服从 [实施任务书](../../V02_IMPLEMENTATION_TASKBOOK.md)，不构成第二套任务授权或状态台账。** 本文保留并行主线 `6f449e6` 的范围修正；实际服务端和 R3 前端从 `pilot/`、`desktop/` 继续，不能把旧 `app/` 路线作为新产品入口。前端可按既有契约独立推进，Windows 实机按用户手动执行方案验收。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `xinghetech/yike-ai2026/main` 上交付首发面向所有行业企业的 AI 商机发现与跟进工作台：自主业务建档及行业策略、多平台真实需求与证据、持续监控、复核、确认触达、回复跟进、Windows 与服务端交付全部贯通；通过跨行业、体验、价值、独立审核和部署恢复验收。共同 Goal 以 [AUTHORITY](../../../AUTHORITY.md) 为准，两端执行目标见[双 AI 任务板](../../DUAL_AGENT_TASKBOARD.md)，不另设一套完成状态。

**Architecture:** Mac Codex 负责身份、服务端事实库、调度、Skill、触达状态、集成和发布；Win Codex 负责适配器契约、前端/API client、Electron/sidecar 和 Windows 证据。两者只通过版本化 API/数据契约协作，所有外部发送仍需人工确认。

**Tech Stack:** 服务端 Python/FastAPI/PostgreSQL、受控平台执行器、版本化 Skill、既有 R3 前端、Electron、Windows 安装与回退测试。

## Global Constraints

- `yike-ai2026/main` 是唯一产品主线；小范围串行改动直接在 main 验证、审核和提交，较大或并行功能从最新 `origin/main` 建短期 `codex/<主题>` 分支，完成后合并清理。本次用户明确要求的文档/目标调整由 CodexWin 直接提交 main。
- V0.2 首发面向所有行业企业，必须覆盖账号、客户空间、多产品/服务画像、行业与销售方式策略、多平台采集、持续监控、Skill、复核、真实触达、回复跟进、Windows 交付和部署门禁。
- PostgreSQL 是正式客户库；SQLite 只可用于明确标记的本地实验。
- 未经人工确认不发送，不绕过验证码/限流/风控，不把凭据或私密会话写入仓库、数据库、日志或导出。
- mock、fixture、静态页面和 HTTP 200 不能证明真实平台、触达、回复、UAT 或商业成功。

---

## Chunk 1：接收在途成果与独立先行卡

**Files:** `AUTHORITY.md`、`docs/V02_IMPLEMENTATION_TASKBOOK.md`、`docs/DUAL_AGENT_TASKBOARD.md`；后续代码按已认领卡的实际路径执行。

- [ ] Fetch 最新 `origin/main`，记录 base SHA。
- [ ] 将 `SYNC-01` 用作每卡开工/集成检查，读取当前权威、在途认领和相关历史迁入边界；不重复旧对齐工作，不设全局等待锁。
- [ ] 在唯一任务书登记实际负责人、文件边界、候选/集成 SHA 与 ACK；本文件的勾选框是执行索引，不是第二套进度。
- [ ] 优先接收 V02-01A/B 已有候选，不把登记/遥测或会话撤销当作完整设备执行协议；最终独立审核与接收复现另记。
- [ ] Mac 保留 V02-05A 原前端工作；Win 可先认领 V02-02C 解析器或 V02-09A 构建检查。V02-09B/D 的本地进程与凭据隔离部分不等生产服务。
- [ ] 并行定义 V02-01C、V02-02A、V02-04A/B、V02-06A、V02-07A、V02-10A；检查 V02-10E 是否已有认领，不重复修复基线测试。每端默认一张主实现卡加一张复核卡。

## Chunk 2：真实采集、持续执行与研究复核

**Files:** `pilot/`、`migrations/`、`tests/`；旧 `app/` 仅作为经评估的复用来源，不建立第二套客户事实库。

- [ ] 先写身份串租户、整包事务、执行代次、坏模型输出、跨 run 绑定和未确认发送的失败测试。
- [ ] V02-01C 执行授权与 V02-02A 候选契约 ACK 后，推进 V02-02B 原始候选 API；V02-01D 正常登录/激活独立推进。
- [ ] Win 按 V02-02D-XHS/DY/BILI/ZHIHU/WEB 分别接通平台/来源，复用 V02-02C、V02-09B/D；一个平台失败不阻止其他平台，单平台通过不替代全部首发验收。
- [ ] Mac 按 V02-03A/B 完成运行/配置/单平台状态、调度恢复及多轮增量；V02-04C 完成真实研究与证据复核。先以一个可运行来源联调，再补全部首发来源。
- [ ] 保留跨行业资料/策略版本与五类反例；来源能力和触达能力分别验收。
- [ ] 每个子任务独立 commit，交 Win Codex 复核；修复后复审。
- [ ] 通过 pytest、compileall、数据库迁移和 secret scan 后再联调依赖这些新 API 的 UI/触达路径；已授权前端可以按现有契约独立推进。

## Chunk 3：R3 增量服务接入

**Files:** `desktop/src/renderer/`、`desktop/src/main/serviceClient.ts`、`desktop/src/main/servicePolicy.ts`、`desktop/src/shared/contracts.ts` 与 `desktop/tests/`。画像/任务/候选领域模型继续复用，不改回旧静态页面。

- [ ] 只依赖 Mac 发布的接口契约，不直连数据库或管理员 CLI。
- [ ] 在唯一任务书认领具体子项，接收并复现接口交接包；复用 R3 及三队列/P18管理/原生CSV导出增量，补业务建档、可编辑策略和证据/变化展示，不重做他人已交付页面。
- [ ] V02-05B/C 分别接资料画像与可编辑行业策略；V02-05D/F/G 分别接身份连接、任务操作、候选复核；V02-05E 展示证据与实质变化。
- [ ] 每条已接收接口单独验收；未知结果查询、版本冲突、失效/离线、人工修改保护都需真实服务反例，不用整体 BLOCKED 阻止局部交付。
- [ ] Mac Codex 对每个 PR 做独立复核并检查证据边界。

## Chunk 4：确认触达与回复跟进

**Files:** `pilot/`、`desktop/src/renderer/`、`tests/` 及 `desktop/tests/`。

- [ ] V02-06A/07A 的主体映射与操作契约 ACK 后，实现 V02-06B 通道适配和 V02-07B 确认队列；复用既有 Outreach 的 requestId/send/reconcile，不另造一套不兼容协议；模块测试不互等真实整链，真实收发交 V02-10B 收口。
- [ ] V02-07C 为已有三队列/确认/未知恢复 UI 接入真实服务；V02-08A/B/C 分别交付回复/跟进 API、工作台和价值/成本查询。页面不与 Mac 已在途文件并发编辑。
- [ ] 真实发送前必须人工确认；回复事件与人工登记分开记录。
- [ ] Win Codex 复核 Mac 的触达状态机，Mac 复核 Win 的跟进工作台。

## Chunk 5：Windows、部署与跨行业价值验收

**Files:** `deploy/`、`scripts/`、`docs/`、`tests/`。

- [ ] V02-09F 由 Mac 补齐生产管理服务的权限、计划、幂等原请求查询和客户备份恢复；09C/E 由 Win 复用管理UI及契约，分别验证安装/卸载/授权/备份和更新/回退。管理协调与本机更新先冻结接口、分别做反例再联验，不互等整卡；用户手动实机步骤未回传前不标通过。
- [ ] V02-10B 按 M1/M2/M3 分别锁定证据；V02-10C 验证私网 PostgreSQL、非超级用户、RLS/ACL、HTTPS、备份恢复、回滚和部署 SHA。
- [ ] 逐平台保存真实运行与来源证据；真实账号/扫码/通道缺失只在任务书相应实测子步骤记 `WAITING_INPUT`，其他工作继续。
- [ ] 锁定发布提交，由未参与相应实现的独立 reviewer 完成架构/代码/质量复核；Mac 收口功能集成，Win 不自审本人实现。
- [ ] V02-10D 按[产品计划第 7 节](../../V02_COMMERCIAL_RELEASE_PLAN.md)完成五类业务各两家企业、每家连续 14 天试用，记录配置用时、同质量人工对照、证据、实付/使用/有效回复和续费意向；不足或未达标如实记录，技术完成不等于商业成功。

各小卡的依赖、现存入口、完成证据、定向命令和单卡 RED/GREEN/审核/ACK 模板统一见[任务板](../../DUAL_AGENT_TASKBOARD.md)。新接口的完整字段、实现文件和新增测试在相应契约卡冻结，不在此索引预先编造已经存在的 API。调整任务卡不等于本轮开始执行上述开发、外发或部署。

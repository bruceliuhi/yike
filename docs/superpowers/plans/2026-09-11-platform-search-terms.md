# Platform-specific search terms implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development; root alone commits/pushes. User asks targeted tests and one independent whole-batch review, not duplicated review/build cycles.

**Goal:** 用户按平台确认不同关键词，由真实原生普通采集/监控驱动消费。

**Architecture:** 可选platformQueries绑定既有策略快照和摘要；无新API、数据库表或平行任务。沿用公共排除和预算，研究模式仍拒绝此普通采集扩展。

**Tech Stack:** Python/Pydantic/PostgreSQL + TypeScript/Zod/React/Electron。

## Global constraints

- Spec: `docs/superpowers/specs/2026-09-11-platform-search-terms-design.md`；无null、空items、重复平台、未选平台、控制字符、逗号、首尾空白、排除冲突。
- `platformQueries={version:"platform-queries-v1",items:[{platform,keywords}]}`。四个social平台，各1～20词/词1～80字符；无覆盖fallback通用词。
- 仅普通search任务；research非空/links拒绝。无字段旧快照字节不变；不放开搜贝研究/发送/部署。
- Root owns TS shared schema + renderer; implementer owns Python contract/policy/tests + pythonCollectionDriver/test. Shared helper root exports `platformSearchKeywords(configuration: StrategyConfiguration, platform: string): string[]`.

### Task 1: End-to-end per-platform query override

Files: `pilot/research_strategy_contract.py`, `pilot/foreground_collection.py` if necessary, `desktop/src/shared/researchStrategies.ts`, `desktop/src/main/pythonCollectionDriver.ts`; renderer `domain/models.ts`, `domain/task.ts`, `domain/researchStrategies.ts`, `app/taskDraft.ts`, `pages/TaskWizard.tsx`, new `pages/tasks/PlatformSearchTerms.tsx`, `pages/tasks/StrategySnapshotDetails.tsx`; focused tests adjacent to existing contract/driver/draft tests.

- [x] RED: assert a configuration with XIAOHONGSHU词“找搭建团队” and BILIBILI词“展台设计报价” round-trips; old configuration omits platformQueries. Assert duplicate/unselected platforms and invalid modes rejected. Run exact targeted new contract tests before implementation.
- [x] Python: add frozen bounded optional nested shape, omit absent field in serializer, scope validator requires item.platform in platforms. Retain existing limits and public/research policies. PG prepare-confirm-resolve must preserve map and digest differs for changed word.
- [x] TS/root: add matching strict nested shape and scope checks; helper returns `configuration.platformQueries?.items.find(item => item.platform === platform)?.keywords ?? configuration.keywords`; helper consumes validated config, driver keeps strict guards. Add TaskDraft `platformTerms` as optional social-id to Term[] map; serialize selected valid data without silent pruning, include in fingerprint, persist and validate drafts.
- [x] Driver: validate snapshot and use helper at query selection. Existing loop/quota/deadline/query-echo validation unchanged. Test two target platforms route different queries and fallback without live platform or process bypass.
- [x] UI: existing editor plus explicit per-platform opt-in/reset, edited overrides survive common suggestion regeneration. Show effective query per platform in bound receipt and errors for dormant unselected overrides. Actual TaskWizard drives PREPARE with mapping; no separate mock path.
- [x] 可达性与模板：`pages/Tasks.tsx`复用create函数显式新增普通任务按钮（新id、无research，不改原任务）；`pages/tasks/localTemplates.ts` conditions.pick纳入platformTerms。真实列表UI点击与模板往返定向RED/GREEN，旧研究创建不变。
- [x] GREEN: run new/affected contract + native query tests, TS typecheck, one restricted PG strategy lifecycle test. No business full-suite/package unless actual release candidate requested.
- [x] Root review/stage code; independent reviewer checks precise committed diff for spec/quality, fixes receive targeted recheck. Root updates evidence here/taskbook and pushes main after fetch/non-destructive sync.

## Evidence

实现提交 `6bcc8ad`，审核修复 `73d4ce9`，非作者差量复核 GO（代码候选）。Task 1 本批交付完成；真实平台和完整 Goal 不据此关闭。

- Python 合同/相邻策略验证 276 passed；原生 driver 35 passed；真实受限 PostgreSQL PREPARE→CONFIRM→resolve 1 passed。数据库证明保存与摘要绑定，不证明平台采集。
- 客户端草稿、模板、实际 TaskWizard 与策略确认共 6 文件 87 passed，TypeScript 检查退出 0。人工平台词保留、移除平台阻止确认、无覆盖回退均有定向验证。
- 首次独立审核 **NO-GO**：普通按钮只在 legacy 分支，生产原生路由不可达；覆盖事实仍只展示全局词。`73d4ce9` 修复实际 NativeCollectionTasks / NativeMonitorPlans 入口，并使普通采集草稿使用当前用户/工作空间；新增测试从 TasksPage 的实际 service 能力分支进入，RED 两失败→GREEN 两文件 12 passed，tsc 0。
- 覆盖范围按实际平台读取确认的 override，未覆盖回退通用词；两个 override 与 fallback RED 两失败→GREEN 连同相邻状态共 4 passed。仍明确没有逐词/逐页穷尽证据。
- 临时本地页面已读到实际组件首屏；未完成展开/完整浏览器主流程验收。不以此代替桌面、Windows 或真实平台验收。本批未重复构包或全套测试，未部署、未发送外部信息。
- 当前仅普通四平台采集/监控支持独立词。多源搜贝研究仍需来源许可、原生上传和结算接线；固定 V2EX 单源研究未被伪装成全网。完整 V0.2 Goal 继续。

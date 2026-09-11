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

- [ ] RED: assert a configuration with XIAOHONGSHU词“找搭建团队” and BILIBILI词“展台设计报价” round-trips; old configuration omits platformQueries. Assert duplicate/unselected platforms and invalid modes rejected. Run exact targeted new contract tests before implementation.
- [ ] Python: add frozen bounded optional nested shape, omit absent field in serializer, scope validator requires item.platform in platforms. Retain existing limits and public/research policies. PG prepare-confirm-resolve must preserve map and digest differs for changed word.
- [ ] TS/root: add matching strict nested shape and scope checks; helper returns `configuration.platformQueries?.items.find(item => item.platform === platform)?.keywords ?? configuration.keywords`; helper consumes validated config, driver keeps strict guards. Add TaskDraft `platformTerms` as optional social-id to Term[] map; serialize selected valid data without silent pruning, include in fingerprint, persist and validate drafts.
- [ ] Driver: validate snapshot and use helper at query selection. Existing loop/quota/deadline/query-echo validation unchanged. Test two target platforms route different queries and fallback without live platform or process bypass.
- [ ] UI: existing editor plus explicit per-platform opt-in/reset, edited overrides survive common suggestion regeneration. Show effective query per platform in bound receipt and errors for dormant unselected overrides. Actual TaskWizard drives PREPARE with mapping; no separate mock path.
- [ ] GREEN: run new/affected contract + native query tests, TS typecheck, one restricted PG strategy lifecycle test. No business full-suite/package unless actual release candidate requested.
- [ ] Root review/stage code; independent reviewer checks precise committed diff for spec/quality, fixes receive targeted recheck. Root updates evidence here/taskbook and pushes main after fetch/non-destructive sync.

## Evidence

Not yet implemented. Independent architecture investigation recorded existing shared-keyword loop and research isolation; conclusions above separate this executable ordinary-collection increment from the remaining multi-source research runtime.

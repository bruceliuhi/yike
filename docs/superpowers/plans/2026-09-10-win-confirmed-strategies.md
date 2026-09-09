# 用户最终配置到真实执行策略 Implementation Plan

> **For agentic workers:** REQUIRED: Use `subagent-driven-development`; tasks follow TDD and independent spec/code review. 用户允许小范围串行直接main；只改所属新文件，共享入口仍由Mac串行接收。

**Goal:** 将既有P19最终确认变成可持久读取、撤销及供Mac执行/判断同事务消费的真实策略版本，解除合成resolver依赖。

**Architecture:** 版本化公开配置→prepare待确认快照→confirm绑定整个快照→同cursor resolver。更高草稿revision替换当前指针，使旧确认不能用于新执行，历史回执不变。不调用模型/平台，不把保存/确认当采集或收费。

**Tech Stack:** Python/Pydantic/PostgreSQL/psycopg/FastAPI；复用会话、画像、执行合同及R4确认流程。

基线`a77e582`。沿用已批准[R3搜索行为](../../../design/v02-suite-r3/AI_SEARCH_CONDITIONS.md)、[R4交互](../../../design/v02-suite-r4/INTERACTION_CONTRACT.md)，不是新视觉或产品范围。承接[04B原计划](2026-09-09-win-search-suggestions.md)Chunk3，将真实策略提前与建议后台并行；完整04B/05C、监控、搜贝及类似建议的未完项不取消。

## 已核实的选择

- 主线没有生产策略表/resolver；不复用synthetic_strategy、随机策略ID、旧pilot_tasks或旧UI哈希冒充执行确认。
- TaskDraft.profileId是画像版本UUID；旧画像tenant共享而非个人owner，新策略按tenant+当前user隔离。完整画像payload摘要在prepare保存，confirm/resolve重算。
- 新迁移**114**归Win；108资料/110建议仍Win，111执行/112候选/113在途判断归Mac，均不改写。共享db/store/ui_api/web由Mac串行集成。
- 遵守[执行合同](../../contracts/V02_EXECUTION_RUNTIME.md)完整快照/hash及platform顺序。确认只表达用户意图；来源能力、设备/连接、日程调度和所有预算仍是独立执行护栏。
- 公开配置不含账号凭据、设备私钥、画像正文或任意自由字典。R4搜贝、去重来源数、模型调用数与技术记录预算分开，禁止无说明换算或假的researchContractVersion=1。

## Chunk 1：严格配置及操作合同

### Task 1：有界公开配置

**Files:** Create `pilot/research_strategy_contract.py`, `tests/test_research_strategy_contract.py`。

接口：`ResearchStrategyConfiguration`、`PrepareStrategyRequest`、`ConfirmStrategyRequest`、`RevokeStrategyRequest`、`StrategyStoreError`、`strategy_snapshot(...)`、`configuration_digest(...)`。全模型strict/frozen/extra forbid/hide_input_in_errors/revalidate_instances=always，重新验证原字段，不让model_copy绕过。

StrategyStoreError固定code/status：invalid_request422、invalid_session401、request_not_found404、strategy_not_found404、request_conflict409、draft_conflict409、strategy_conflict409、profile_unavailable409、strategy_store_unavailable503；未知code/status降为最后一种，不回显输入。snapshot helper重新校验全部六个字段；digest只对合法快照计算，不接受额外权限或非JSON内容。

`ResearchStrategyConfiguration`固定字段：

- schema_version='research-strategy-v1'；name 1..60字符；source='search'|'links'；keywords/exclusions各0..20、每项1..80可见单行严格字符串。规范化比较去重、排除包含冲突拒绝，不修改原词。search必须有keywords，links模式必须有links；按R4切换模式保留另一侧输入，所有字段参与快照，不静默清空草稿。实际执行只使用source选择的入口，不能因非生效字段仍有值而自动加搜或读取；确认适配明确展示生效入口。
- links 0..100公开URL、每项≤2048，复用02A `_validate_url(value,'PUBLIC_WEB')`冻结验证，不复制算法；保留原文、拒绝重复。不声明域名可访问或DNS重绑定已解决；真实site/平台能力另验。
- mode='once'|'monitor'；schedule可null，monitor必需。schedule固定kind daily/interval、times（0..24不重复HH:mm）、interval有限数字1..168小时、start/end合法HH:mm、timezone有效ZoneInfo；daily至少一个time。保留所有字段，不自动改时区/日程；发布环境缺tzdata明确不可用，不回退本地时区。
- research可null，否则保留R4基础设置原字段名：version=1、非空不重复demandTypes四枚举、maxSoubei正整数≤1000000、limits.sources/minutes/modelCalls各正整数≤1000000、stopAtAnyLimit=true、evidenceOrder='SOURCE_MATCH_CONTEXT'。不省略或归零未实现上限。类似/覆盖provenance缺服务端证据resolver，此合同显式拒绝额外provenance字段；后续增版本/受验证适配，不静默丢弃。
- 配置序列化UTF-8≤65536字节，拒绝非法Unicode、控制字符和非有限数。无意图推断或平台调用。

prepare字段：schema_version='strategy-confirmation-v1'；request_id/draft_id/profile_version_id规范小写UUID；draft_revision严格正整数≤2147483647；configuration；platforms（1..5合法02A枚举、无重复、保留顺序）；max_records严格1..10000；max_runtime_seconds严格1..86400。技术预算单独确认，不从sources或maxSoubei推导。

confirm字段：同schema/request_id、strategy_version_id规范UUID、configuration_sha256小写64hex、human_confirmed精确true。revoke字段：同schema/request_id、strategy_version_id；无需画像仍有效即可撤销自身策略。

`strategy_snapshot(profile_version_id,strategy_version_id,configuration,platforms,max_records,max_runtime_seconds)`输出Mac六字段快照；配置转严格JSON、platforms转list。`configuration_digest(snapshot)`按sorted keys/紧凑UTF-8/allow_nan=False计算SHA256。

- [ ] RED覆盖中文正例/三操作、bool/整数混淆/额外字段/伪造实例/重复/冲突/URL/时区/上限/Unicode；确定性快照匹配Mac，平台顺序/预算/研究设置变化都改hash。
- [ ] 命令`./.runtime/venvs/win-device-review/Scripts/python.exe -X utf8 -m pytest -q tests/test_research_strategy_contract.py`先明确缺模块失败，再最小实现及GREEN。
- [ ] 自审、独立spec与代码/架构/质量审核，只提交这两文件。

## Chunk 2：受限PostgreSQL确认与撤销

### Task 2：真实策略存储和同事务resolver

**Files:** Create `pilot/research_strategies.py`, `migrations/114_v02_research_strategies.sql`, `deploy/grant_research_strategies.sql`, `tests/test_research_strategies_postgres.py`。不改共享入口或冻结111/112/113。

`ResearchStrategyStore(database)`：prepare/confirm/revoke(claims,request)、get_receipt(claims,request_id)、get_strategy(claims,strategy_version_id)、resolve(cursor,claims,profile_version_id,strategy_version_id)。请求接受严格合同或dict；身份复用TokenClaims/SessionRegistry。

三表tenant+owner FORCE RLS、复合FK：

- pilot_research_strategy_drafts：(tenant,owner,draft_id)唯一，current_revision/current_version_id，单一当前指针。首次prepare原子创建，revision严格增加；同revision比较完整prepare绑定（profile版本及摘要、configuration、platform顺序、两个技术预算，排除新request_id及服务端strategy_version_id），全部相同才复用，否则409；较旧revision不回退。
- pilot_research_strategy_versions：服务端UUID、draft/revision/profile版本/完整profile_sha、不可变snapshot/configuration_sha、state DRAFT/CONFIRMED/REVOKED、created_at/confirmed_at/revoked_at。payload/owner/绑定/创建时间不可改；只DRAFT→CONFIRMED/REVOKED、CONFIRMED→REVOKED，不恢复撤销。
- pilot_research_strategy_operations：(tenant,owner,request_id)唯一、operation、完整原请求hash、不可变回执/created_at。无凭据或画像正文；成功操作和状态变化同事务，失败不生成成功回执。同request不同操作/内容409，原成功先重放不重做。

receipt字段固定schema_version='strategy-confirmation-v1'、request_id、operation PREPARE/CONFIRM/REVOKE、strategy_version_id、draft_id/draft_revision、profile_version_id/profile_sha256、configuration_sha256、snapshot、state、recorded_at。原receipt按原状态读取；get_strategy另返回当前state、is_current、profile_current，历史CONFIRMED不是新执行许可。

锁序session→原request advisory(11401)→画像父行/版本→draft行→version行。resolver在调用方画像锁后重查同序，仅传入cursor，不commit/新连接/网络，不锁设备/任务/原候选；autocommit cursor拒绝。定位只读不当授权，锁后复核、等待后再查墙钟/会话。

prepare核验CONFIRMED画像和payload摘要。confirm要求当前draft、DRAFT或同一已CONFIRMED版本、精确hash及仍相同CONFIRMED画像；human_confirmed不是来源已核验。更高revision prepare后旧resolver立即不可用；同配置新revision也需新确认。revoke允许画像失效/非当前版本，只撤销自己的版本；Mac CANCEL不被策略撤销阻断。

resolve验证私有owner、当前指针、CONFIRMED、画像绑定及完整原payload摘要、重算snapshot/hash；返回真正ConfirmedExecutionStrategy。不存在/非当前/撤销/未确认/画像变化统一ExecutionRuntimeError('strategy_conflict')，失效session为401；不泄露他人存在或SQL/DSN/输入。

grant仅三表必需SELECT/INSERT/UPDATE（operations无UPDATE）；拒绝DELETE/TRUNCATE/REFERENCES/TRIGGER及禁止列权限、owner/super/bypass/createrole/createdb/replication与MEMBER可切换父角色超权，沿用110已审模式，重复升级不扩大权限。

- [ ] 真实独立PG RED：prepare→confirm→resolve/原回执跨服务重启、两租户/同租户owner隔离、修改/撤销/画像内容状态变化、两会话并发、坏hash/伪造身份、FK/RLS/终态/最小grant。
- [ ] 最小实现及GREEN，验证resolver事务回滚、并发confirm不多建、prepare新revision与消费互斥、锁等待后会话过期。
- [ ] 真PG用真实策略store替换Mac合成resolver：实际Ed25519 START→CLAIM→签名原始候选上传；撤销后旧租约提交失败、CANCEL仍可用。只有来源policy明确为合成边界，不当真实来源验收。
- [ ] 独立spec和代码/架构/质量审核；随机PostgreSQL16容器精确清理，不操作客户库；记录失败/修正/候选后正常main交接。

## Chunk 3：认证入口与现有确认流程

### Task 3：HTTP与Win/Mac交接

**Files:** Create `pilot/research_strategy_api.py`, `tests/test_research_strategy_api.py`, `docs/contracts/V02_CONFIRMED_RESEARCH_STRATEGIES.md`, `docs/qa/V02-04B_CONFIRMED_STRATEGIES_WIN_REVIEW.md`。

- [ ] 独立router POST `/research-strategies/prepare|confirm|revoke`，GET `/research-strategy-operations/{request_id}`和`/research-strategies/{strategy_version_id}`。受信identity/HTTPS、JSON≤128KiB、重复key/非JSON数字/未知query拒绝、no-store/safe errors；无注入501，DB不阻塞event loop；共享build_app交Mac。
- [ ] 实际TestClient→真PG完整操作/tenant隔离，无外部调用。交接114迁移注册与strategy_resolver=store.resolve；不能因确认策略就启用实际来源。
- [ ] 05C随后接P19：单存prepare/confirm UUID/server快照hash/旧UI hash与原请求；逐字段预览核对、主动确认后CONFIRM，编辑失效、未知先查原请求，不覆盖旧R4 ledger。本合同/PG通过不计客户端已接通。
- [ ] R4全上限、搜贝真实预留/计量、monitor调度、类似/覆盖provenance、真实来源/原文证据/试用继续交付；缺失部分阻止相应执行，不取消最终范围或把测试当上线。

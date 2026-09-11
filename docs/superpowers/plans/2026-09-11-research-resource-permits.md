# 研究资源许可与受控公开读取 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for this bounded batch. User approved autonomous technical refinement within V0.2; no further design confirmation is required.

**Goal:** 让已预留研究任务可以在可信内部执行器中先取得资源许可，再执行一次受限来源读取并留下不可重复的实际动作记录。

**Architecture:** 在原任务/预留上增加内部资源事件，不开放客户端自报消耗API。每个动作有稳定UUID、输入摘要和一次性许可；并发按预留串行核算，记录失败/未知而非猜测零消耗。首个调用者为固定V2EX公开索引读取，后续候选提取/来源补证与模型worker复用同一许可；不把索引读取当全站搜索或买方识别完成。

**Tech Stack:** Python / psycopg / PostgreSQL RLS；现有ExecutionRuntime与133资源预留；复用已锁定httpx依赖的AsyncClient，以asyncio.wait_for统一约束连接/读取总截止，不采用可逐段延长的多个urllib超时。

## Global Constraints

- 仅承接已确认并由原子研究START建立的task/run/reservation；tenant/user、设备、当前画像/策略/来源/能力须重新核验。保持原session -> request -> device -> profile/strategy -> task锁顺序，不从task锁反向取profile锁。
- 不改变已有设备签名字节，不开放普通研究CLAIM/上传，不装配生产研究模式、价格或余额扣费；全量V0.2范围和Goal不变。
- `SOURCE_READ`表示一次逻辑公开页面/索引读取许可，不等于独立帖子数；`MODEL_CALL`表示一次模型调用许可。当前sources/modelCalls上限分别限制此类许可，派生界面必须注明口径。索引中看到的多条内容、后续逐条补证、入库与有效商机分别计数；不可将一次索引读取冒充一次完整研究。
- 每个动作一个单位，units不可由客户端传入。ISSUED/未知许可占用上限，不凭超时返还；本批无计费结算或安全释放。minutes限制自START起的墙钟总截止，同时不得超过原task.deadline_at。
- `research_generation=1`明确属于此新task/run的首代内部研究执行，不冒充尚未CLAIM的普通platform执行代次；不实现换代或自动重跑。恢复原action不再执行回调。
- 只留非秘密摘要、时间、状态及固定resource。状态`ISSUED/SUCCEEDED/FAILED/UNKNOWN`表示动作事实，不代表平台发送、采购或财务结算；未知不算成功，结果摘要不替代原文候选存储。
- 针对实际修改定向TDD，受限真PG验证并发/回滚与隔离；一次非作者整批审核。外部公开读取只做有边界的只读验收，合成任务身份/规则不能称客户真实UAT。

### Task 1: 内部资源账本

Files: create `pilot/research_resources.py`, next migration `134_v02_research_resources.sql`, `deploy/grant_research_resources.sql`, `tests/test_research_resources_postgres.py`; minimally register migration/grant and affected cleanup fixtures. Root owns Task2 files/docs; root串行提交。

Public Python interface (not HTTP):

```python
class ResearchResourceStore:
    def __init__(self, runtime, *, rule, research_capability): ...
    def begin(self, claims, *, task_id, run_id, action_id, resource, input_sha256): ...
    def finish(self, claims, *, task_id, run_id, action_id, permit_id, status, output_sha256=None): ...
    def get(self, claims, *, task_id, run_id, action_id): ...
```

`begin` returns `{created: bool, event: Event}`. `finish/get` return Event. Exact Event keys: `schema_version:'research-resource-v1', reservation_id, task_id, run_id, action_id, permit_id` (canonical UUIDs), `research_generation:1`, `resource:'SOURCE_READ'|'MODEL_CALL'`, `input_sha256`, `status:'ISSUED'|'SUCCEEDED'|'FAILED'|'UNKNOWN'`, `output_sha256` (SHA256 or null), `issued_at`, `deadline_at`, `finished_at` (ISO UTC, last null ifISSUED). Successful finish requires output_sha256; FAILED/UNKNOWN must have null. No raw input/output/auth token. Fixed error codes via ExecutionRuntimeError: invalid_request422, request_conflict409, resource_limit_exceeded409, task_unavailable409, capability_unavailable501, resource_unavailable503, request_not_found404, invalid_session401; preserve necessary existing fixed runtime rejection codes.

- [x] Add failing test for accepted begin/finish/get and same action replay not issuing another permit.
- [x] Persist event with tenant+owner forcedRLS, composite task/run/reservation FKs and unique action within task/run. Permit IDs unique. Immutable identity/input/issued/deadline; only one final transition fromISSUED, identical finish idempotent, different outcome/digest conflicts. Grant minimal SELECT/INSERT and required status/output/finished columns only.
- [x] Implement authenticated current-state begin: validate types/UUID/SHA; use existing session/device/strategy resolution order then locktask/run and reservation. Strategy config must match reservation and active rule digest/capability; task/run must match and be PENDING/RUNNING, notcancelled/finished. Resource counts sum all issued events of that resource regardlessoutcome. Serialize under reservation lock and check limit before insert. Deadline=min(task.deadline,task.created+reservation.minute_limit). Same action same resource/input returnscreatedFalse originalevent aftercurrentidentity check, evenexpired/stopped, ashistoryonly; changedinput/resource/task-run mismatch rejects.
- [x] Finish records outcome for a previously issued permit for current authenticated owner, including after cancellation/deadline (facts must remain recordable); no fresh profile/source/capability or current-price authorization required to record history. Use DBtime, no arbitraryclientclock, no changedidentity. Missing/crossscopeevent404. Unexpecteddatabaseerrorsfixed503. Allmutations must repeat sessionfence beforecommit.
- [x] RestrictedPG cases: sources andmodelcaps independent; concurrentdifferentaction atlastslot onlyonecreated; sameaction concurrentonlyonecreated; unknown occupiesbudget; finaloutcomeidempotent/conflict; crossuser/tenant notvisible/write; source/strategy/device/capability revoked preventsnewpermits, failed checksnowrites; cancelled/expired cannotbeginbutcanfinish/readexisting; minutes+taskdeadline; no poisonedtask/run binding; terminalsessionfence rollback. Reuse actualResearchExecutionService START fixtures and explicit synthetic rule/capability, no handinsert pretendstartedtask.
- [x] Run only newtests and affected oldatomicSTART/migration/grant tests, report exactcommands/RED/GREEN and ownedPGcontainer details. Do notcommit/stage/push.

### Task 2: 可信内部执行器与固定公开来源

Root creates `pilot/research_resource_runner.py`, `pilot/research_public_reader.py`, corresponding focusedtests.

`run_resource(store, claims, *, task_id, run_id, action_id, resource, input_sha256, action)` calls begin; ifcreatedFalse returns `{event, result:None, replayed:True}` withoutaction. Newpermit invokes callback withserverdeadline; hashes canonical boundedJSON result andfinishesSUCCEEDED. Exceptions/timeouts finishUNKNOWN withnullresultdigest; no automaticretry. Iffinish itself fails, leaveissued/unknown ratherthanreport success; fixederror notrawexception. Callbackresult returnedonlyonnewsuccess, notpersisted/reconstructed fromdigest. Recovery lackingrawdata is explicitly partial, not a regeneratedread.

`read_public_index(store, claims, *, task_id, run_id, action_id, fetcher=None)` usesconstant logicaldescriptor `v2ex-latest-index-v1`, SHA256, SOURCE_READ andrun_resource. Defaultfetch only `https://www.v2ex.com/api/topics/latest.json`, GET, no cookies/auth, no redirects, totaldeadline capped20seconds, max1MiB, application/json only, strictUTF8/JSON, top-array<=100. Return validated/sanitized publictopic fields (id,title,content,created,url) with fixedsource metadata and observedcount; neverpass arbitraryURL, invokecomment/private APIs, or retry429/captcha. Sourceoutput remainspublicrawunreviewed, notAIintent/lead. Customfetcher is test-only dependency injection, notrenderer/API input.

- [x] TDD permission-denied meanscallbacknevercalled; replay/UNKNOWNneverreruns; changedresultfinishfailure notsuccess; sequentialsource/modelinputboundaries.
- [x] Fixedreader tests actuallocalHTTPfunction behavior via controlled response fixtures: boundedbytes/type/redirect/deadline/invalidpayload; sourcefetchoccurs onlyafterbegin and isfinishedwithdigest. No externalrun claimed byfixtures.
- [x] If adapter/realPG integration succeeds, do atmostone actualfixedendpoint read under an explicitly synthetic task/quote inisolatedPG; report observedreadstatus/countonly, notnewopportunities. Failure retainedasfailure, no retryloop.

### Task 3: Acceptance and continuation

- [ ] One independent wholebatch review actualcommits; importantfindings fixedwithdirected tests only. Update thisplan's evidence andtaskbook, merge/pushmain andverify0/0clean.
- [x] Remaining work stays explicit: actualresearchsession/workerorchestration, durablecandidateevidence andstructuredAIanalysis, safeeventsettlement/release, ordinaryUIactivation, realplatform/Windows/production/crossindustryUAT. ThisbatchdoesnotshrinkGoalorreenableunmeteredresearch.

## 实施证据

基线`c63e8b4`；内部执行器/固定读取`8fb768f`，资源存储/134迁移/授权/实网验收入口`f12e12d`。非作者已只读审核实际整批`c63e8b4..f12e12d`及原session/device/strategy/task锁依赖：**限定GO，无P1/P2**。没有重复测试/构包；结论不覆盖完整研究或上线。

- Task1/Task2代码已实现。受限PG创建真实策略、签名START和预留，再调用内部资源方法；不是直接插入假启动任务。新增15项通过；受影响的既有原子START14项、execution/migration42项、空库授权2项通过，不将这些分母合并成全量回归结论。
- 执行器11项、固定读取21项，共32项定向通过（0.20s）。此前分别以未实现模块复现失败；PG测试进一步暴露reservation锁授权不足、缺逐目标connection核对及复合reservation/task/run绑定，均已修复。权限只增加必要列与owner策略，保留原不可变触发器。
- `tests/test_research_public_live_optin.py`默认跳过；仅显式`YIKE_RESEARCH_PUBLIC_LIVE=1`且使用专用测试库才运行。2026-09-11执行一次默认固定V2EX API读取，**1 passed / 4.13s**：`SUCCEEDED`、`observed_count=44`、结果摘要已持久化；同action恢复返回历史、没有第二次外网读取。真实网络与真实受限PG贯通，但身份/规则为合成夹具，44条为未判断公开帖子，不是44条商机或客户UAT。未输出原文、账号或联系方式。
- 受限PG为本批专用`yike-research-resources-task1-pg`，仅本机端口，验收后已停止（保留容器，无删除）；没有操作生产库/服务器、发送外部消息或构包。部署仍需正常迁移134与授权更新，本批不装配默认研究能力或计价规则。
- 审核保留两项非阻断备注：terminal finish相同事实的历史返回可在后续编辑时补末端会话到期复核；现有并发用例共享session，不能单独宣称验证了跨session的reservation竞争。新动作与实际写入仍有会话复核，代码已持有reservation锁；本批不为这两项扩测整套。

可复用检查入口（数据库环境变量只应指向独立测试库，凭据不写入仓库）：

```sh
python -m pytest -q tests/test_research_resource_runner.py tests/test_research_public_reader.py
python -m pytest -q tests/test_research_resources_postgres.py
YIKE_RESEARCH_PUBLIC_LIVE=1 python -m pytest -q -s tests/test_research_public_live_optin.py
```

后续优先接研究worker编排、原文证据持久化及结构化分析，再接客户端启动/结果与结算恢复。摘要无法恢复原文，当前重开只能证明动作事实；SOURCE_READ也不等于候选数。无模型调用适配器、无自动重跑或释放、无完整研究UI，不关闭R4和完整Goal。

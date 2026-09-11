# Research Candidate Evidence Implementation Plan

> **For agentic workers:** Use subagent-driven-development. User authorized technical refinement within V0.2; execute without additional design approval. Root serial commits; one independent whole-batch review, no repeated broad suites.

**Goal:** Controlled research source results persist into the existing candidate inbox and reopen through its real detail contract.

**Architecture:** Reuse candidate persistence inside the same transaction that finalizes a resource event; a distinct research execution context avoids inventing an ordinary lease. Existing upload authorization remains unchanged.

**Tech Stack:** Python/psycopg/PostgreSQL RLS, existing resource runner/httpx reader, TypeScript/Zod evidence boundary.

## Global Constraints

- Follow the design at `../specs/2026-09-11-research-candidate-evidence-design.md`. Do not enable production research, prices, model calls, external messages or ordinary research upload/CLAIM.
- Internal `on_success(event, result, output_sha256)` is called only after a fresh admitted bounded successful callback; it replaces normal finish and must commit event + candidates atomically. Failure returns fixed503 without automatic retry. Replays never invoke it.
- Research context exact keys: `kind:'research-resource-v1', device_id,task_id,run_id,platform_run_id,credential_version,access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null,reservation_id,action_id,permit_id,research_generation:1,resource:'SOURCE_READ',input_sha256,output_sha256,observed_count,accepted_count,skipped_invalid_count,skipped_budget_count`. All IDs canonicalUUID, SHA lowercase64; positive bounded credential; counts0..100, observed=accepted+invalid+budget. No lease fields. Observation request_id equals action_id, record_index<accepted_count, scope matches outer observation and PUBLIC_WEB.
- Preserve source identity/version/projection and ambiguity rules. No truncated or fabricated body. PAGE uses existing candidate validators. Same action has one batch; different action with unchanged source reuses candidate/version and appends observation. Task total record budget is enforced under original task/platform locks; source/model resource allowance unchanged.
- Only current session ownership is required to finish an already admitted action after cancellation; no new effect. New begin retains current device/profile/source/capability checks. Transactions contain no network/model call.
- Root owns runner/reader hook and TS read contract/tests/docs. Backend agent owns new service/migration/registration, shared persistence extraction and PG tests. No agent stages/commits/pushes or changes another checkout. Use apply_patch.

### Task 1: Atomic research candidates

Files: create `pilot/research_candidates.py`, `migrations/135_v02_research_candidate_binding.sql`, `tests/test_research_candidates_postgres.py`; modify `pilot/candidate_ingestion.py` only to extract/reuse its current record loop; register135 in `pilot/db.py`. Reuse existing runtime grants; add minimal grant only if a real PG failure proves necessary.

Interfaces:

```python
class ResearchCandidateStore:
    def __init__(self, resources): ... # existing ResearchResourceStore
    def commit_index(self, claims, *, event, result, output_sha256): ... # returns final resource Event
    def get_receipt(self, claims, *, task_id, run_id, action_id): ... # candidate-receipt-v1 or None
    def read_public(self, claims, *, task_id, run_id, action_id, fetcher=None): ...
```

`read_public` calls existing `read_public_index(..., on_success=callback)`, callback calls commit_index. Return `{event, receipt, replayed}` using stored receipt, not recovered raw callback data. Failed/unknown action may have receiptNone. No HTTP route is added.

- [x] RED test actual confirmed research START -> fixed synthetic source -> read_public -> real CandidateIngestionStore.list_candidates/get_candidate with exact original body/URL/time, UNVERIFIED, distinct context, same-action recovery no fetch. Use existing real_strategy_env and tests/test_research_resources_postgres.started/store; no direct fake startedtask insertion.
- [x] Add placeholder service methods to obtain behavioral RED, then minimal implementation. Extract current record persistence into shared `_persist_records` (same source lock ordering/projections/observations); ordinary ingest calls it without changing its receipt/fingerprint/authorization.
- [x] commit_index verifies canonical bounded result hash, fixed source metadata/input descriptor, source counts/time; normalize valid records with existing CandidateRecord/URL/time rules. Reject invalid envelope; skip blank/oversized individual records without editing source text. Server clock and original event issuance/deadline bound observation time. Input remains original fixed V2EX index shape, not client-supplied candidates.
- [x] One transaction: current session, task/run/platform locks, original event lock, verify exact event/permit/input/owner binding, SOURCE_READ and ISSUED; identical already committed event/batch returns historical event, differing facts conflict. Derive profile/strategy/device/credential from immutable stored task/target. Compute remaining task max_records across platforms; persist first valid records up to remaining in source order; update records_used; write immutable candidate batch/context/receipt using action UUID; update event SUCCEEDED/digest/DB finishedtime; final session fence. No new strategy/connection locks after task locks. Callback failure rolls everything back.
- [x] Migration135 deferred constraint trigger on research candidate batches requires matching resource event tenant/owner/task/run/action/permit/reservation/generation/input/output with statusSUCCEEDED and SOURCE_READ plus original platform task context. Ordinary batches unaffected. Event identity already immutable. Ensure DB rejection of wrong event/permit/digest bindings and no elevated runtime grants.
- [x] Directed PG tests: replay/no duplicate; different action reuses source and records new observation; unknown cannot become success; digest/body conflict; crossowner invisibility; event/candidate/counter rollback on final fence; cancelled action can finish fact; overall record cap; invalid record counts; ordinary signed research upload remains rejected. Run new suite plus existing candidate_ingestion PG regression and empty-migration/grants only if affected. Report commands, RED/GREEN and dedicated owned PG readiness. Do not run root opt-in live test yet.

### Task 2: Reader completion and client read boundary (root)

Files: `pilot/research_resource_runner.py`, `pilot/research_public_reader.py`, their tests; `desktop/src/shared/rawCandidateEvidence.ts`, existing corresponding tests; adapt explicitly opt-in live test to the new persisted path.

- [x] Add failing tests for `on_success(event,result,output_sha256)` receiving fresh canonical bounded output, no normal finish on that path, no call on replay/failure, commit error not returning success. Implement optional internal hook; default unchanged. Reader forwards it.
- [x] Add research context union and strict parent binding in raw candidate parser; positive new context passes, normal lease smuggling/wrong action/platform/digest/accounting fails. Keep old tests unchanged. Run only this TS test and tsc.
- [x] Update opt-in live test to use ResearchCandidateStore, read at most once, existing list/detail shows persisted UNVERIFIED original evidence, recovery returns same receipt without refetch. No model/buyer claim. Default skip stays.

### Task 3: Review, integration, continuation

- [ ] One nonauthor review of complete baseline-to-head diff; fix important findings with directed checks. Update this file's sole evidence section and taskbook/spec current status, push main and verify clean0/0. Stop only owned test PG; preserve other checkouts.
- [x] Next actual research orchestration/model analysis and client activation remain explicit; this batch adds readable evidence, not full research strategy execution, production or customerUAT.

## 实施证据

基线`ccbecd8`，设计/方案`39caa65`；root执行器完成回调与客户端只读上下文`7cc9cad`，原子候选入库/135约束/联验`6084df4`。非作者已只读审核整批实际diff及原锁/RLS/契约：**限定GO，无P1/P2**，未重复测试/构建/网络/DB。仅P3建议给live脚本增加非零原文断言，已补以防空循环假阳性；本次实测10条，原代码字节证据不受影响，不再重读外网。

- 读取完成回调5项RED（新参数尚不存在），实现后runner/reader共37项通过；不在失败或恢复路径调用完成回调，提交异常不再另发finish。
- 新研究原文客户端正例首次RED，接严格新旧执行上下文后，两份对应测试194项通过，TypeScript检查通过。不是新的客户端构包或窗口验收。
- 独立只读架构核对确认复用已有candidate持久化及复核流程；未采用另建完整结果库/观察表或伪造普通lease。合格原文留在已有versions，未纳入项只留数量，不声称其全文可恢复。
- 新受限PG16项通过（23.65s），旧候选入库回归23项通过（27.90s，含空库迁移重复及权限/重复授权）；不将定向分母合并成全产品通过。联验中修复PG对象键数函数、来源ID与普通V2EX读取兼容、满额后的重复提交误判、未来观察时间及NULL kind约束问题。没有额外提升运行时权限。
- `tests/test_research_public_live_optin.py`仅显式启用且指向专用测试库时实际触网。2026-09-11只做一次默认固定V2EX公开读取：**1 passed / 5.76s**；同事务持久化10条未判断原文（测试task记录上限为10），现有HTTP候选列表/详情逐条回读，并由真正的`rawCandidateEvidence.ts`解析全部返回值；原action恢复取得同一回执且未再次读取。不是10条商机，不是生产客户数据或客户UAT。身份/规则为合成夹具；未调用模型、对外发送或部署。
- 计量规则/生产研究/模型仍未启用，普通research CLAIM/upload保持拒绝；默认live测试跳过。下步接研究编排、结构化分析和用户启动/结果状态，不能把这一片称为完整研究执行或上线。
- 验收后已停止本批专用PG容器（保留数据容器）并移除本工作树临时node_modules软链接；依赖源、其他工作树及服务器均未变动。

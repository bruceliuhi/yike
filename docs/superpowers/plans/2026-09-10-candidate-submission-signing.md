# 候选上传签名字节接续 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development; TDD and independent spec/code/architecture/quality review. 当前已批准端到端路线的最小接线，不新增产品范围。

**Goal:** 普通客户端取得当前会话绑定的候选待签字节，签名上传并按原键恢复，不推导服务端租户或会话摘要。

**Architecture:** 完整batch复用4 MiB流式JSON入口及既有候选校验，再由ExecutionRuntime检查当前身份/owner设备/凭据，复用原候选签名域。准备不入库、不预留额度；正式上传和历史恢复不改。

**Tech Stack:** FastAPI、现有Ed25519、PostgreSQL/RLS、pytest；无迁移、新依赖、nonce或授权框架。

## Global Constraints

- 唯一新增POST `/api/ui/candidate-submission-signing-payload`，输入精确`{batch: CandidateBatch JSON}`，不接受tenant/user/session/signature/now；完整body实际字节最多4 MiB，JSON-only、任意层重复键/NaN拒绝。
- 响应精确`signing_payload/request_id/device_id/credential_version/batch_fingerprint`；原文沿用`yike-candidate-submission-v1`；fingerprint是现规范batch去掉request_id的SHA256，不是原HTTP字节或execution摘要。
- 准备只复用当前session、DB时钟校验和owner当前设备凭据；返回前重验session。不调用任务/策略/连接/来源/模型/lock_submission，不写候选、回执、执行、挑战、预算或租约。
- 正式ingest/签名校验/取消/预算/租约/final fence不变；原复合键历史回执优先恢复不变。未知结果先GET原platform_run_id/request_id，不能强制重新准备后才恢复历史。
- HTTPS、认证、Origin、no-store、稳定无敏感回显错误沿用现边界。密钥、Cookie、验证码、模型凭据不入Git/日志；测试只能使用合成身份与专用测试DB。
- Win独占desktop持钥/设备HTTP/worker/05G；Mac不并改客户端，本片不表示Win ACK、实际来源采集、真实模型效果、发送、Windows发行、生产或客户UAT。

基线`bbe2e2049ec9ed5105394d8bf4f1d7da84c42e4b`；当前工作树`codex/mac-device-authorization`，root唯一Git写入者。选完整batch的代价是正文多传一次；先避免客户端重复实现canonical/null/default规则，待真实吞吐证据再优化。最终含signature的上传envelope仍须≤4 MiB。

## Task 1: 最小准备接口（独立实现，root负责提交）

**执行状态：COMPLETE。** 核心`805aeb0`，独立Task规格/质量Approved，0 Critical/Important/Minor；root实际241项与28项跨任务HTTP/PG及未改helper/middleware核对覆盖外部验证项。[QA](../../qa/V02_CANDIDATE_SUBMISSION_SIGNING.md)记录RED、测试假设修正与冻结结果。下面步骤为原执行清单，不扩展本片授权。

**Files:** Modify `pilot/candidate_api.py`, `pilot/candidate_ingestion.py`, `pilot/execution_runtime.py`, `tests/test_candidate_ingestion_api.py`。不要改SQL、DTO、原ingest或Win文件。

**Interfaces:** Consumes `validate_candidate_batch(payload, now=self._now(cursor))`、`_active`、`_key`、`submission_signing_payload`、`batch_fingerprint`。Produces `CandidateIngestionStore.prepare_signing_payload(claims,payload)` → `ExecutionRuntime.prepare_submission_signing_payload(claims,payload)` 与上述POST。root并行负责真实HTTP/PG测试、合同、QA、交接；本任务不得操作PG/Git。

- [ ] Step 1: 先为现StoreBoundary增加记录prepare调用方法，在真实ASGI边界新增以下RED。fixture只证明传输不证明授权。

```python
def test_candidate_signing_preparation_preserves_raw_batch():
    service = StoreBoundary()
    batch = envelope()["batch"]
    response = client_for(service).post("/api/ui/candidate-submission-signing-payload",
        json={"batch": batch}, headers=headers())
    assert response.status_code == 200, response.text
    assert service.calls == [("prepare", "user-1", batch)]
    assert response.headers["cache-control"] == "no-store"
```

- [ ] Step 2: Run `uv run --frozen pytest -q tests/test_candidate_ingestion_api.py -k signing_preparation --tb=short`，观察新增route 404；记录预期RED再写生产代码。
- [ ] Step 3: API仅提取共用有界JSON reader，上传原精确envelope/signature检查保留，新envelope只接受batch dict。认证和服务调用继续threadpool，不阻塞async body reader。接线：

```python
@router.post("/candidate-submission-signing-payload")
async def signing_payload(request: Request):
    claims = await run_in_threadpool(current, request)
    body = await _submission_envelope(request)
    return await run_in_threadpool(invoke, service.prepare_signing_payload, claims, body["batch"])
```

`_submission_envelope`基于同模块共用reader，精确验证`type(body) is dict and set(body)=={"batch"} and type(body["batch"]) is dict`，否则`_invalid()`。上传仍精确`batch/signature`且decode_canonical64。Store新增：

```python
def prepare_signing_payload(self, claims, payload: dict) -> dict:
    if self.execution_runtime is None:
        raise CandidateIngestionError('capability_unavailable', 501)
    return self.execution_runtime.prepare_submission_signing_payload(claims, payload)
```

Runtime在既有prepare旁新增：

```python
def prepare_submission_signing_payload(self, claims, payload: dict) -> dict:
    with self.database.connect() as connection, connection.cursor() as cursor:
        tenant = self._active(cursor, claims)
        batch = validate_candidate_batch(payload, now=self._now(cursor))
        ex = batch.execution
        self._key(cursor, claims, tenant, ex.device_id, ex.credential_version)
        result = dict(
            signing_payload=submission_signing_payload(tenant_id=tenant, claims=claims, batch=batch),
            request_id=batch.request_id, device_id=ex.device_id,
            credential_version=ex.credential_version, batch_fingerprint=batch_fingerprint(batch),
        )
        self._active(cursor, claims)
        return result
```

- [ ] Step 4: 扩现路由测试为准备入口覆盖缺service501、无登录/撤销401、HTTP400、跨Origin403、非JSON415、4 MiB实际流超限413（含伪Content-Length）、重复键/NaN/额外权限字段422、深JSON稳定拒绝、固定异常500且正文/错误日志无秘密、无隐式重试。DTO业务校验由root真PG与既有candidate_contract测试覆盖，不在边界fixture伪称验证。
- [ ] Step 5: Run `uv run --frozen pytest -q tests/test_candidate_ingestion_api.py tests/test_candidate_contract.py tests/test_execution_api.py tests/test_execution_contract.py --tb=short`。自审后在指定report写实际RED/GREEN和文件范围，root审核提交；不可用历史通过替代本次结果。

## Task 2: 真实HTTP/PG主链与交接（root集成）

**执行状态：实现/实际验证和整片终审已完成，待最终主线推送核对。** root测试与合同`3d0ce80`，正常合入Win仅3份05G交接文档为`e47a925`，源码/测试/SQL/desktop字节未变；完整`bbe2e20..293fd24`另一位非作者终审PASS/0发现。最后主线核对事实另记，不标父卡或Goal结束。

**Files:** Create `tests/test_candidate_submission_signing_http_postgres.py`; modify `tests/test_confirmed_strategy_http_postgres.py`中候选签名helper调用；update `docs/contracts/V02_RAW_CANDIDATE_INBOX.md`, `docs/V02_IMPLEMENTATION_TASKBOOK.md`, `docs/DUAL_AGENT_TASKBOARD.md`; create `docs/qa/V02_CANDIDATE_SUBMISSION_SIGNING.md`。

**Interfaces:** Consumes Task1五字段HTTP、既有执行准备/上传/回执；Produces可复现真实ASGI/PG证据及Win接续合同，不声称socket/TLS或平台证明。

- [ ] Step 1: 复用real_strategy_env、actual CandidateIngestionStore 和执行server字节签名helper。新helper不导入submission_signing_payload，不读env.tenant/claims摘要构造签名：

```python
def signed_candidate(client, key, value):
    response = client.post("/api/ui/candidate-submission-signing-payload", json={"batch": value})
    assert response.status_code == 200, response.text
    prepared = response.json()
    return {"batch": value, "signature": encoded(key.sign(
        prepared["signing_payload"].encode("utf-8")).signature)}
```

- [ ] Step 2: 核对同session稳定、独立canonical摘要/Unicode/null、空批次、签原字节真实上传/复用原键不重复计数。拒绝同租户其他owner/跨租户/撤销/旧credential；真实设备锁等待后session过期401且不泄露原文。用admin受信查询确认候选五表/执行四表/key_requests计数和records_used/lease不变，不以RLS空查询假证无写入。
- [ ] Step 3: 换session新签名字节不同而fingerprint相同，未入库旧签名拒绝；签后改正文/request_id/execution拒绝。准备不调用strategy/source/connection；准备后取消/策略撤销/预算不足/lease过期仍在上传拒绝且零增量。设备撤销后准备拒绝，但原GET及历史POST仍恢复同回执；未安装runtime501。新增复杂边界先写预期失败，原有护栏不重写。
- [ ] Step 4: 把现真实策略→签名执行→候选→模型fixture→人工核验→共享原文HTTP链的候选签名替换为上述HTTP原字节，保留全部原断言。
- [ ] Step 5: Run专用测试DB下 `uv run --frozen pytest -q tests/test_candidate_submission_signing_http_postgres.py tests/test_confirmed_strategy_http_postgres.py tests/test_candidate_ingestion_http_postgres.py --tb=short`；root串行拥有PG，不跑无改动全仓。记录0skip和实际证据边界；独立Task review及整片final review后正常合并/推main，保留Win新提交与原工作区用户文件。更新精确QA/五字段/冻结batch/原键先查恢复与阶段状态；父卡/Goal不关闭。

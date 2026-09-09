# 执行签名字节客户端接续 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development; TDD and independent spec/code/architecture/quality review. 已批准执行方案的最小客户端接口接续，不重开产品设计。

**Goal:** 普通已登录客户端取得与当前会话绑定的执行原文字节，用本机设备钥签名并调用既有START/CLAIM/RENEW/CANCEL，不读取Cookie或猜tenant。

**Architecture:** 严格单字段HTTP envelope → 既有ExecutionRuntime短事务校验当前会话及设备凭据 → 既有canonical签名函数 → 五字段响应。准备不产生执行事实；实际操作仍由原apply判断、持久化和防重。

**Tech Stack:** FastAPI/Pydantic、现有Ed25519、PostgreSQL/RLS、pytest。无新增依赖、迁移或客户端文件。

## Global Constraints

- 客户空间、画像、任务、候选、商机、触达与跟进按服务端身份解析的 tenant_id 隔离；自用商机不进入客户空间。
- 密钥、Cookie、Profile、验证码和私密会话不进入 Git、业务数据库、日志或导出；平台登录态置于隔离的专用凭据/会话存储。
- 应用与管理员数据库连接严格分离；运行时 env 禁止携带管理员连接。迁移、provision 及当前受信研究包导入仅在管理员路径执行。
- 唯一新增入口POST `/api/ui/execution-signing-payload`，输入仅`{request: ExecutionOperation}`。沿用完整规范null输出；保留既有模型可缺省的null输入，不修改旧DTO。
- 响应精确`signing_payload/request_id/device_id/credential_version/request_sha256`；摘要是完整规范operation（含request_id）的UTF-8 canonical SHA256，与apply内部排除request_id的幂等摘要不同。
- 签名原文只由现有`execution_signing_payload`产生，保持`yike-execution-operation-v1`、ensure_ascii=False及当前session_digest。相同规范request和会话字节相同；不增加nonce、时间或表。
- 只复用`_active`和`_key`，不调用策略、连接、来源policy、任务或模型来批准准备；不创建task/run/lease/receipt/key_request、不预留UUID或预算。返回前重验会话，继续HTTPS/Origin/no-store和固定错误。
- apply、历史回执、CANCEL与来源能力默认值不变；未安装真实来源的START仍501。Win独占desktop持钥/HTTP/05E/worker，不并改；本片不代表真实采集、Windows产品消费、发送、生产或UAT完成。

来源：`docs/handoffs/V1_WIN_FUNCTION_OWNERSHIP_20260909.md`的05F请求和现`docs/contracts/V02_EXECUTION_RUNTIME.md`；基线`c3f096c`。继续现有隔离工作树与主干同步，root唯一Git写入者。父Goal保持ACTIVE。

## Task 1: 既有执行服务的准备接口（独立实现）

**Files:** Modify `pilot/execution_api.py`, `pilot/execution_runtime.py`, `tests/test_execution_api.py`; create `tests/test_execution_signing_payload.py`（纯canonical反例）。不要改SQL或Win文件。

**Interfaces:** Consumes `ExecutionOperation`, `ExecutionRuntime._active(cursor,claims)`, `_key(cursor,claims,tenant,device_id,version)`, `_operation`, `_hash`, `execution_signing_payload`。Produces `ExecutionRuntime.prepare_signing_payload(claims, request) -> dict`和上述固定POST。实际PG由Task2根代理并行负责；本任务不得运行PG。

- [x] Step 1: 在既有HTTP测试中新增RuntimeFixture.prepare_signing_payload并扩固定route测试。测试真实HTTP路由/schema/身份/安全错误，不以该fixture证明授权。首个RED示例：

```python
def test_signing_preparation_route_uses_authenticated_claims():
    runtime = RuntimeFixture()
    body = {"request": start_payload()}
    response = client_for(runtime).post("/api/ui/execution-signing-payload",
        json=body, headers=auth_headers())
    assert response.status_code == 200
    call = runtime.calls[0]
    assert call[0] == "prepare"
    assert call[1].user_id == "user-1"
    assert call[2].model_dump(mode="json") == body["request"]
    assert response.headers["cache-control"] == "no-store"
```

增加缺runtime501；无身份/撤销401、HTTP400、跨Origin403；请求/外层tenant/user/session/token/signature/extra、布尔凭据和坏shape422且不回显；异常500固定码、日志无敏感值。扩全部4种合法操作路由但不伪造执行成功。

- [x] Step 2: 已先运行新route单用例，观察404的预期失败；全文件在接线后回归。没有预期失败不得写生产代码。基线32项已通过，不复跑全仓。
- [x] Step 3: 最小接线。API新增严格`ExecutionSigningEnvelope`（与既有envelope相同Config，仅request），在现register函数增加：

```python
@router.post("/execution-signing-payload")
def signing_payload(body: ExecutionSigningEnvelope, request: Request):
    return run(request, lambda service, claims:
        service.prepare_signing_payload(claims, body.request))
```

Runtime在apply附近增加：

```python
def prepare_signing_payload(self, claims, request: ExecutionOperation) -> dict:
    request = _operation(request)
    with self.database.connect() as connection, connection.cursor() as cursor:
        tenant = self._active(cursor, claims)
        self._key(cursor, claims, tenant, request.device_id, request.credential_version)
        result = dict(
            signing_payload=execution_signing_payload(
                tenant_id=tenant, claims=claims, operation=request),
            request_id=request.request_id,
            device_id=request.device_id,
            credential_version=request.credential_version,
            request_sha256=_hash(request.model_dump(mode='json')),
        )
        self._active(cursor, claims)
        return result
```

不复制签名、锁、错误处理或另造nonce/store。不要更改已有apply获取历史回执优先于新签名校验的恢复语义。
- [x] Step 4: 纯测试核对canonical null、输入key重排等价、targets顺序/request_id改变摘要、中文外层身份保留UTF-8、换会话仅改变待签文字节。输入request维持既有ASCII字段限制；`_hash`测试只证明canonical，不证明实际服务返回（Task2承担）。非法model_copy实例由既有`_operation`重新验证，不允许布尔凭据偷换整数。
- [x] Step 5: 定向最终命令 `uv run --frozen pytest -q tests/test_execution_api.py tests/test_execution_contract.py tests/test_execution_signing_payload.py tests/test_pilot_runtime.py --tb=short`。自审后将实际RED/GREEN命令、结果、文件范围、无PG边界写入root指定报告；root提交`7d8f657`，fresh reviewer规格/质量审核均通过，跨任务检查由root实际HTTP/PG证据对应，见QA。

## Task 2: 真实HTTP/受限PG接续及Win交接（root集成）

**Files:** Create `tests/test_execution_signing_payload_http_postgres.py`; modify `tests/test_confirmed_strategy_http_postgres.py`的send_execution及`tests/test_pilot_runtime_http_postgres.py`相应调用仅用于既有主链；update原执行契约、唯一任务书、整合状态及新增QA。沿用real_strategy_env和专用受限PG，不建立第二来源resolver。

**Interfaces:** Consumes Task1实际POST和现execution-operations；Produces给Win的精确字段/原字节签名/历史回执区别及可复现QA，不替Win登记客户端ACK。

- [x] Step 1: 在生产接线前运行以下真实HTTP断言，预期404；准备好真实策略/设备后才断言，不将fixture失败当新功能RED。

```python
response = client.post("/api/ui/execution-signing-payload",
    json={"request": request.model_dump(mode="json")})
assert response.status_code == 200, response.text
prepared = response.json()
signature = encoded(env.key.sign(prepared["signing_payload"].encode("utf-8")).signature)
applied = client.post("/api/ui/execution-operations", json={
    "request": request.model_dump(mode="json"), "signature": signature})
assert applied.status_code == 200, applied.text
```

- [x] Step 2: 扩实际回归：同请求重读无写入；admin测试连接按该租户/用户数任务/run/platform/operation/key_request，不能依赖未设身份的RLS空集；source policy/resolver/model调用为0。owner/tenant/停设备/旧凭据、设备锁等待会话到期、注销拒绝分别覆盖。请求完整null/摘要与响应五字段直接核对。
- [x] Step 3: 实际新会话对尚未执行的原请求，旧签名400但新准备字节签名可用；已有成功请求新会话可GET/重放历史回执。实际START→CLAIM→RENEW→策略撤销→CANCEL沿新准备路径，保持取消与历史恢复。无真实source policy时prepare200而START501且无成功执行行；不能把fixture来源许可复制到production。
- [x] Step 4: 把既有实际策略→签名上传→模型分析→复核纳入链的执行签名改为只签API响应；客户端helper不再用tenant/claims自行构造执行原文。上传另有既有协议，本片不偷改该域。
- [x] Step 5: 执行新HTTP文件及现`test_confirmed_strategy_http_postgres.py`、`test_pilot_runtime_http_postgres.py`；所有PG串行，记录各集合不相加，必要失败修复按TDD。契约/QA和台账已更新，独立最终审核`9fc197c`及两次正常合并`12c0c95`/`cfaf4fd`全部通过，详见本片QA；合并后的Win原文读取链另由Mac实际接收。真实模型vendor、来源、Windows及M3仍独立验收。

交付收口按用户授权正常推送main及功能分支，并实时核对远端SHA；该动作的结果以实际Git回执为准，以上测试/审核完成不等于已上线。保留当前隔离工作树用于父Goal后续工作，不清理原checkout的用户改动。

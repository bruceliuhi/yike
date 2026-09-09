# V02-02A Candidate Ingestion Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现已批准 V02-02A 的可运行候选/来源能力契约，给 Win 解析器和后续02B提供明确输入、版本、重放与失败语义。

**Architecture:** 使用现有 Pydantic 2 和标准库，独立模块只做无副作用结构校验与 canonical JSON 指纹。执行上下文仍为未授权 Claim；持久化、认证、真实平台与审核另按已批准任务接入，不提前打开任何能力。

**Tech Stack:** Python 3.12、Pydantic 2.11.7、pytest 8.3.5；不改依赖锁、不用网络或数据库。

## Global Constraints

- `yike-ai2026/main` 是唯一产品主线；本卡从 `f7e71653249f2b8102be75b92dda5d3894117ae6` 建 `codex/mac-candidate-contract`，复用已有干净隔离 worktree。
- PostgreSQL 是正式客户库；本卡不增加另一事实库、不触及迁移或现有受信研究包导入。
- 未经人工确认不发送，不绕过验证码/限流/风控，不把凭据或私密会话写入仓库、数据库、日志或导出。
- mock、fixture、静态页面和 HTTP 200 不能证明真实平台、触达、回复、UAT 或商业成功。
- DTO 校验不等于授权；不引入 tenant_id/user_id/reviewer/APPROVED 或 AuthorizedExecution，不消费未获实际接收 ACK 的01A/B实现。
- 字段、限制、平台映射、hash输入与错误精确以 `docs/contracts/V02_CANDIDATE_INGESTION.md` 为本卡技术契约；不修改已批准产品范围。

## 文件与单卡交付

- 新增 `pilot/source_capabilities.py`：平台映射、冻结声明、六项独立能力。
- 新增 `pilot/candidate_contract.py`：严格数据对象、脱敏校验、来源/内容/批次指纹及纯重放比较。
- 新增 `tests/test_source_capabilities.py`、`tests/test_candidate_contract.py`：全部合成输入，逐条行为反例。
- 修改契约、实施任务书；新增 `docs/qa/V02-02A_REVIEW.md` 记录最终SHA、失败/通过、独立结论和限制。根代理维护文档，实施 Agent 仅改上述两模块及两测试。

### Task 1: 实现候选与来源契约

**Interfaces:**

```python
# pilot/source_capabilities.py
def resolve_platform(value: str, *, namespace: str) -> PlatformSpec: ...
def default_capabilities(platform: str) -> SourceCapabilities: ...
# frozen PlatformSpec: frontend_id, service_id, collector_id (str | None)
# frozen SourceCapabilities: platform + six CapabilityDeclaration fields
# CapabilityDeclaration: state, evidence_ref (opaque ID | None)

# pilot/candidate_contract.py
class CandidateContractError(ValueError):
    code: str

def validate_candidate_batch(payload: object, *, now: datetime) -> CandidateBatch: ...
def source_identity(record: CandidateRecord, platform: str) -> str: ...
def content_version(record: CandidateRecord) -> str: ...
def batch_fingerprint(batch: CandidateBatch) -> str: ...
def replay_decision(stored_fingerprint: str | None, incoming_fingerprint: str) -> str: ...
```

类型内部采用 frozen/extra-forbid 模型；records 为 tuple，嵌套模型同样冻结。对 dict/list 的公共入口进行严格类型验证，允许 JSON list 输入转换为冻结 tuple，但不要接受数字字符串、bool 或对象的隐式强转。now 必须为时区感知 datetime；异常 now 是编程错误，可抛固定 ValueError，不包含数据。

- [ ] **Step 1：写行为测试并观察 RED。** 从平台精确映射与公共匿名空批次开始，再分组加入原文/时间/重放/错误/权限伪造反例。代码示例（其他字段完整样例按契约构造）：

```python
def test_platform_namespaces_do_not_guess():
    assert resolve_platform("douyin", namespace="frontend").collector_id == "dy"
    with pytest.raises(ValueError):
        resolve_platform("dy", namespace="frontend")

def test_query_and_observation_do_not_change_content_version(record):
    changed = record.model_copy(update={"query": "第二个检索词", "observed_at": "2026-09-09T02:00:00Z"})
    assert content_version(record) == content_version(changed)

def test_replay_is_not_new_observation(batch):
    digest = batch_fingerprint(batch)
    assert replay_decision(None, digest) == "NEW"
    assert replay_decision(digest, digest) == "REPLAY"
    changed = batch.model_copy(update={"strategy_version_id": "strategy-2"})
    assert replay_decision(digest, batch_fingerprint(changed)) == "CONFLICT"
```

运行 `uv run --frozen pytest -q tests/test_source_capabilities.py tests/test_candidate_contract.py`；先观察缺少契约模块/行为的失败，不把测试拼写或环境错误当 RED。最初模块不存在可先用 importlib 检查模块不存在的断言，以正常断言失败展示缺失能力；随后实现最小部分并迭代新反例。

- [ ] **Step 2：实现严格校验与纯函数。** 采用 frozen Pydantic模型，record/body保留原文，解析时间为UTC进行比较但输出仍为原始规范字符串。hash helper 的精确算法：

```python
def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
```

哈希对象选择、重复和冲突规则逐项按契约第4节实现。PUBLIC_WEB 的来源身份始终含规范 origin，测试不同站点同一站内 ID 不碰撞。URL校验只分析形状，不做DNS/HTTP调用。公开入口捕获内部校验错误并 `raise CandidateContractError(code) from None`，不使用 `str(validation_error)` 或在公开异常中保存原 payload。处理批内冲突不写数据库。

- [ ] **Step 3：补齐并运行反例 GREEN。** 精确覆盖五组平台ID；默认六能力不能VERIFIED、缺证据的非初值声明拒绝；匿名web连接字段全空通过、混合/错误模式拒绝；bool/零/负/浮点/字符串代次拒绝；顶层与嵌套未知字段/APPROVED/tenant/reviewer/token拒绝；主帖/评论/网页的ID关系；未知时间保留null、过期原文可入站、未来/错日历/非UTC/父子时间冲突拒绝；正文空白/NUL/上限、匿名作者；token/userinfo/恶意域名/端口/私网地址/注入字符URL拒绝、B站reply片段通过；来源跨平台不合并；观察/query不改内容版本，正文/父上下文更新改版本；批内重复/不同版本分别拒绝；指纹对键顺序稳定且绑定执行/策略/画像/观察内容；相同request新内容CONFLICT；验证返回冻结嵌套对象、不修改原payload；错误str/repr不含提交的敏感样例值。不使用实际客户数据。

- [ ] **Step 4：定向回归与提交。** 运行下面命令，记录原始退出结果及绑定代码 SHA：

```sh
uv run --frozen pytest -q tests/test_candidate_contract.py tests/test_source_capabilities.py tests/test_research_import.py tests/test_research_skill_contract.py
uv run --frozen python -m compileall -q pilot tests
bash scripts/secret_scan.sh
git diff --check
git add pilot/candidate_contract.py pilot/source_capabilities.py tests/test_candidate_contract.py tests/test_source_capabilities.py
git commit -m "feat: define validated candidate ingestion contracts"
```

根代理另跑全仓验证，将主线既有时钟/权威断言失败与本卡失败分别记录；不重复V02-10E已有修复，不从 feature 偷带未接收代码使数字变绿。独立reviewer按具体风险复核，不与其他Agent共用DDL测试库。

- [ ] **Step 5：交接。** 独立审核绑定完整候选区间，修复后复审；根代理更新唯一任务书并推送候选，实际Win复现与ACK未收到前不标 DONE，不宣称正式上传API或平台已上线。

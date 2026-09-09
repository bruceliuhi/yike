# 已确认画像到搜索建议 Implementation Plan

> **For agentic workers:** REQUIRED: Use `subagent-driven-development`; steps use checkbox syntax. User has authorized direct main integration for bounded serial changes; only independent files are developed here, shared entrypoints remain Mac-owned.

**Goal:** 让客户从已确认业务画像得到有依据、可编辑、可恢复查询的真实模型搜索建议，随后接最终策略确认及真实“多找类似”，不再停留在不可用占位。

**Architecture:** 复用现有 PostgreSQL 画像和会话；独立搜索建议模型适配器、持久请求服务和 router。P06/P20 保留人工编辑，P19 只确认最终配置；建议生成不启动采集。共享入口由 Mac 接收最小补丁后串行接入。

**Tech Stack:** Python 3.11 / Pydantic / httpx / psycopg / FastAPI，后续复用 Electron IPC 与已有 React 条件编辑器，不新增依赖。

基线 `2ce6f8a8076765cdbb7122b08175cd2f01cf1abd`。产品设计已批准：[R3搜索行为](../../../design/v02-suite-r3/AI_SEARCH_CONDITIONS.md)、[R4交互](../../../design/v02-suite-r4/INTERACTION_CONTRACT.md)、[分工](../../V02_IMPLEMENTATION_TASKBOOK.md#codexwin-goal-启动与当前认领)。这是既定设计的后端实施，不新增界面或重新索取整套批准。

## 已核实的选择与边界

1. 复用已确认 `business_profile_versions.payload.description`，不先重做多业务管理；客户端 `Profile.id` 对应 `profile_version_id`，不能当业务 profile_id。
2. 不复用旧评分服务的“唯一Offer是意客AI”提示，也不调用旧 SQLite 研究流水线；复用既有 HTTPS/严格JSON/有限超时的传输模式。独立提示按当前画像生成买方表达，不把AI开发行业模板当允许名单。
3. 不采用无状态直接模型代理：必须有原请求、画像/草稿版本与结果记录，防页面刷新重复调用。完整执行策略/预算持久化随后衔接，不把建议 ID 冒充 `strategy_version_id`。
4. 初次建议发生在平台连接之前，可先生成平台无关的业务表达；输出不声称支持或已搜索任何平台。按来源定制、来源建议与可执行范围在能力接收后扩展；不能拿一个关键词数组解锁实际来源。
5. 本模型切片只接收调用者提供的description，不自行读取资料附件、内部客户库、Cookie或联系方式字段；description保留原文，并非完整脱敏器。正式外部调用前由04A/服务层核定可向受控模型披露的输入，不能因画像已确认就推定所有自由文本都允许外传。模型输出为候选表达，不是发现结果。显式手机号/邮箱/URL不得出现在搜索词；不能宣称此检查能识别所有私密名称，资料引用授权仍随04A交付。
6. 107归连接版本、108保留资料/画像、109归Mac手机号认证；任务书已登记110给04B建议请求/配额，迁移尚未创建。新迁移与grant由Win提供，`pilot/db.py`注册与`pilot/ui_api.py`/`pilot/web.py`/`pilot/store.py`改动由Mac串行整合；未ACK前不声称默认生产入口可用。

## Chunk 1：有依据的真实模型适配

### Task 1：严格结果与模型调用

**Files:** Create `pilot/search_suggestion_model.py`, `tests/test_search_suggestion_model.py` only. No existing entrypoint/renderer edits.

固定接口：

```python
RULE_VERSION = "search-suggestion-v1"
class SearchSuggestionError(Exception):
    code: str
    status: int
class SuggestionContent(BaseModel):
    keywords: list[str]  # 1..20, each 1..80 Unicode codepoints
    exclusions: list[str]  # 0..20, each 1..80
    rationale: str  # 1..1200
    evidence: list[str]  # 1..8 exact nonempty quotes from description, each <=300
    unknowns: list[str]  # 0..8, each <=300
class SearchSuggestionModel:
    model: str
    provider: str
    def generate(self, *, description: str) -> tuple[SuggestionContent, dict | None]: ...
```

- [ ] 写RED：模块缺失用明确断言；制造业与软件服务两个合成画像，传输只接收对应description；严格类型、额外字段、空白/长度/重复、排除包含搜索词冲突、无依据引用、手机号/邮箱/URL词、Unicode正文不变。
- [ ] 实现 `validate_suggestion(payload, *, description)`；description严格字符串、非空、最多8000字符且保留原文；模型schema使用strict/extra forbid；词为单行，去重键按空白合并和lower，不静默丢坏词或改变证据原文。排除词包含关系会误杀任一建议词时拒绝。不限定必须8–12词，信息不足不凑数。
- [ ] 实现 `OpenAICompatibleSearchSuggestionModel(base_url, api_key, model, timeout_seconds=30, http_client=None)`；构造参数有界，api_key repr隐藏，HTTPS或loopback HTTP，无URL凭据/query/fragment；只一次chat/completions调用、显式不重定向，默认自建HTTPTransport(retries=0)，固定输出上限2048 tokens，响应体读取中限制256KiB。http_client仅为可信内部/测试注入，注入方须提供无重试transport；公开API不能证明任意外部transport内部行为，不窥探私有字段作伪保证。外部文本只能作为user数据，不得通过画像指定模型/URL/schema/系统提示。
- [ ] 严格读取JSON对象（拒绝重复key/NaN/非JSON外围文本）、message.content与finish_reason=stop；finish_reason截断/拒绝/无效结构不作为成功。调用超时→`suggestion_result_unknown` 504；传输或服务端异常保守同类UNKNOWN；明确4xx→`suggestion_provider_rejected` 502；坏模型输出→`invalid_suggestion_result` 502；错误不含原文/响应/密钥、无暴露的异常链。
- [ ] usage只返回已校验prompt_tokens/completion_tokens/total_tokens非负严格整数且总数一致；缺失或不可靠返回null，不造零/人民币/搜贝；保留模型和规则版本供持久服务记录。
- [ ] 用httpx.MockTransport验证真实适配器请求/解析，不调用外部模型、不把替身当实际智能质量。命令：`./.runtime/venvs/win-device-review/Scripts/python.exe -X utf8 -m pytest -q tests/test_search_suggestion_model.py`；先RED再GREEN，独立规格与代码/架构/质量审核。

## Chunk 2：请求持久化与认证HTTP

### Task 2：真实受限PostgreSQL请求服务

**Files:** Create `pilot/search_suggestions.py`, `migrations/110_v02_search_suggestions.sql`, `deploy/grant_search_suggestions.sql`, `tests/test_search_suggestions_postgres.py`. Migration number registered before implementation; no edits to101–109 or shared registry.

持久层与后台分开：`SearchSuggestionStore.reserve(claims, request, *, provider, model)`返回原安全回执和仅首次预留才有的description；`finish(claims, request_id, *, content=None, usage=None, error=None)`只能将同请求PENDING转终态；`get_receipt(claims, request_id)`只读原结果并计算当前画像有效性。模型层不接claims，不知道tenant。后台包装放独立`pilot/search_suggestion_service.py`与对应测试，负责有界准入/线程和关闭，不将后台状态放内存冒充持久回执。

安全回执字段固定为request_id、draft_id、draft_revision、profile_version_id、profile_sha256、rule_version、model_provider、model_name、state、result、usage、error_code、created_at、updated_at、profile_current。result只含已验证SuggestionContent；usage只含Task1允许计量。provider/model是受控服务配置，不接受HTTP指定。UUID为规范小写，revision<=2147483647；所有读取/完成均查认证user/tenant。HTTP轮询看到旧画像结果时保留历史但不可应用，不能把profile_current当执行授权。

完成事务锁session→request→画像；reserve在其前增加tenant配额锁（两整数namespace11001，避免碰10701/会话bigint），读到当前请求即返回、不再计配额。新画像确认仍使用已有business_profiles锁，完成等待后复核墙钟会话及画像状态/摘要。已变化画像使终态FAILED/profile_changed、不写建议结果；已撤销会话不返回结果且保留原PENDING待核对。后台不会以PENDING超时触发第二次模型。

- [ ] 严格请求包含request_id/draft_id/profile_version_id规范UUID、draft_revision非负有界整数；不接受tenant、用户、description、model、费用或自由URL。同用户request_id固定绑定完整正文摘要；同ID不同正文409，同ID原结果可读取不再调用。用户切换互不读取，tenant由SessionRegistry解析。
- [ ] 请求表存受认证tenant/user/request、请求摘要、画像版本/内容摘要、草稿版本、PENDING/SUCCEEDED/FAILED/UNKNOWN、规则/模型版本、已验证结果/usage、时间和固定错误码。强制tenant+user RLS，应用仅需要SELECT/INSERT/UPDATE，无DELETE；grant拒绝特权/owner。仅合成独立PG，不能用客户库。
- [ ] 客户级配额不能在user RLS请求表聚合（会漏掉他用户）。同迁移另建tenant-only FORCE RLS的`pilot_search_suggestion_quota_events`，仅tenant_id/随机quota_event_id/created_at，无用户/请求正文/画像字段；应用仅SELECT/INSERT。每次新预留与单条配额事件同事务提交，在11001 tenant锁下以数据库墙钟计算滚动一小时及两秒间隔；所有状态都占用，重放不新增。
- [ ] reserve短事务按session→tenant配额锁→请求→business_profile锁，重新检查已确认画像与摘要，先持久PENDING再释放事务。每请求最多1次模型调用；固定工程上限同客户每小时10次、新请求间隔至少2秒（重放不计新增），不是搜贝定价。拒绝时不发起模型。
- [ ] POST只预留请求并交给本进程有界后台（最多2个工作者、最多4个已接收工作），快速返回PENDING，不让30秒模型调用占用桌面串行API队列。使用标准库线程池与有界准入，不引入另一个通用任务系统；进程关闭停止接新任务并有界等待，不能静默丢失状态。
- [ ] Task1的httpx timeout只是分阶段I/O超时，不是总调用时限。后台生产启用前必须落实总调用截止与实际退出证据（含慢速响应/关闭中调用反例），不得以取消Future或UI等待冒称底层已停止；这项生命周期保证不由独立adapter的187单测或bytes上限推导。
- [ ] 重放先查原回执且不占工作槽；新请求先非阻塞取得准入再reserve，reserve若返回旧请求立即释放槽。满载新请求拒绝且不预留配额。reserve成功后线程提交失败、排队工作被关闭取消，若服务能够确认从未调用模型则持久FAILED/dispatch_failed；已运行或进程崩溃不能冒称未调用。测试满载重放、提交失败、关闭取消与关闭后查询，不把长期PENDING当正常运行。
- [ ] 外部调用在事务外；完成短事务重新核对会话、画像版本和原请求，晚到结果不覆盖其他请求/新画像。记录成功/明确失败/未知；进程中断遗留PENDING只查询，不用同ID再次执行。模型调用后会话已撤销时不给结果，原请求保持待核对，不能以异常回滚恢复调用额度。
- [ ] 查询返回原绑定及状态；历史结果与当前画像有效性分开（`profile_current`），过期画像的结果不可伪装成当前可应用建议。不发放执行策略ID、执行许可或扣费回执。
- [ ] RED/GREEN覆盖持久重放/冲突、两租户同租户异用户、并发仅一次模型、模型期间可另开事务/撤销/换画像、未知不重试、配额及失败计数不回滚、最小权限/升级幂等。测试先创建独立库，再显式应用110和grant；不能把跳过算验证。

### Task 3：最小router与Mac交接

**Files:** Create `pilot/search_suggestion_api.py`, `tests/test_search_suggestion_api.py`, `docs/handoffs/V02-04B_SEARCH_SUGGESTIONS_WIN_TO_MAC.md`; update唯一任务书与验收记录。共享入口仅提供精确补丁说明，Mac串行整合。

- [ ] 注册函数接现有router、受信identity/HTTPS依赖与SearchSuggestionService；POST `/search-suggestions` 和 GET `/search-suggestions/{request_id}`；严格body和固定安全错误；关闭时501且不调用模型。沿用Origin和no-store，不另开放CORS。
- [ ] 真实受限PG＋TestClient覆盖画像保存/确认→建议→同请求恢复、跨身份拒绝、失效会话、HTTP/Origin安全。模型仅传输替身，单列真实供应商与真实行业质量待验收。
- [ ] 小交付review绑定SHA，main同步Mac；不得将新增表/接口文档当04B/05C整卡完成。默认入口启用须有Mac实际接收和受控模型配置，不读取或输出真实凭据。

## Chunk 3：原页面接入、最终策略与多找类似

- [ ] 05C在Mac共享客户端登录改动接收后接固定IPC操作、严格响应和持久原请求ledger，复用P06/P20人工编辑/删除保护、迟到响应过滤，P19不生成。当前main serviceClient默认12秒且全局串行、模型30秒、UI45秒：采用快速POST/有界GET轮询而不是延长整个队列等待；取消只停止UI等待，不假称撤销供应商费用。当前TaskWizard每次新UUID/useRef不能冒充持久请求恢复。加入有原文依据的建议预览，按已有设计验收，不重建布局。
- [ ] 定义并实现最终策略版本：人工最终词/排除/来源/日程/强制用量上限＋画像绑定，保存和确认幂等；变更使旧确认失效。与Mac03A最小消费契约ACK后实际执行，不能生成随机strategy ID绕过。
- [ ] 多找类似只读服务端已认可真实机会和固定来源证据版本，保留原机会与增量说明；现有opportunity API缺固定source_version，先补可消费事实，不从客户端摘要/样例猜seed。生成新草稿→用户确认→实际搜索→去重新结果，取消不执行。
- [ ] 两个不同真实业务的模型质量、真实平台新增结果与用户编辑/确认闭环另做实际验收；模型/账号/计量外部条件缺失只阻塞对应实测。Goal和04B保持未完成直到完整证据齐备。

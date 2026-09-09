# V02-02A：候选上传与来源能力契约

版本：`candidate-upload-v1`；日期：2026-09-09；负责人：CodexiMac。
依据：已批准的 [V02-02A 小卡](../DUAL_AGENT_TASKBOARD.md)、[多平台方案](../V02_MULTIPLATFORM_SKILL_PLAN.md)和 R3 `desktop/src/renderer/domain/candidates.ts`。这是采集器与未来候选 API 的数据契约，不是已接通平台或 API 的说明。实际状态仅记在[实施任务书](../V02_IMPLEMENTATION_TASKBOOK.md)。

## 1. 边界与平台映射

本卡交付无网络、无数据库的严格校验、稳定指纹、同键重放判定和来源能力登记。它不创建认证对象，不推进任务，不调用管理员导入，不生成 APPROVED 商机，也不把客户端看到的原文声明当作已经由服务端核验。

| 前端 ID | 候选服务端枚举 | 依赖内部 ID |
|---|---|---|
| xhs | XIAOHONGSHU | xhs |
| douyin | DOUYIN | dy |
| bilibili | BILIBILI | bili |
| zhihu | ZHIHU | zhihu |
| web | PUBLIC_WEB | 无（独立连接器） |

映射函数显式指定 `frontend`、`service` 或 `collector` 命名空间，不自动猜测、大小写纠正或把 dy/bili 当成前端值。未知平台拒绝，不静默归入 web。

每个平台的 `search/read_content/read_comments/monitor/send/read_replies` 六项能力分别声明，内置初值均为 `NOT_IMPLEMENTED`，表示新客户执行链尚未验收；旧采集器或人工研究不改变它。其他声明状态是 `UNVERIFIED/VERIFIED/UNAVAILABLE`，非初值须给出不包含秘密的证据引用；该引用仍只是登记资料，不自动使运行时获得权限。PUBLIC_WEB 可采用 `PUBLIC_ANONYMOUS` 读取模式，其余本契约平台只接受 `PLATFORM_ACCOUNT`；这不声称非 web 平台所有公开内容都必须登录，只限制本批客户连接器的账户运行路径。后续经验收的匿名路径需显式版本化扩展。

## 2. 未授权的执行上下文声明

`ExecutionContextClaim` 只校验结构。字段：`device_id`、`task_id`、`run_id`、`platform_run_id`、`lease_id`、`credential_version`、`execution_generation`、`access_mode`、可空 `connection_id/connection_version`。

- 标识使用非空 ASCII opaque ID，1–128 字符，允许字母、数字、`_ . : -`；必须以字母或数字开头。不接受完整 URL、token、Cookie 或本机路径代替 ID。
- 版本/代次使用 1–2147483647 的严格整数，拒绝 bool、float 和数字字符串。
- PLATFORM_ACCOUNT 必须同时有连接 ID 和版本；PUBLIC_ANONYMOUS 必须同时为空，只允许 PUBLIC_WEB。
- tenant_id、user_id、owner、reviewer、权限列表、签名密钥或实际令牌不是上传字段。服务端从产品/设备鉴权及已授予的执行租约解析这些身份。
- 本卡不选定设备算法、租约时长或凭据格式；后续 01C 将绑定这些 opaque 标识。校验通过的类型仍叫 Claim，不得命名 AuthorizedExecution。

未来 01C/02B 在短事务提交前必须校验：产品/用户有效、设备持钥及凭据版本、连接/账号版本、任务/运行/平台和画像/策略绑定、当前租约 owner/代次/过期/取消状态。PUBLIC_ANONYMOUS 免平台账号，不免产品及设备执行授权。

## 3. 上传包与原文结构

`CandidateBatch` 顶层字段固定：

| 字段 | 规则 |
|---|---|
| schema_version | 精确为 candidate-upload-v1 |
| request_id | 同上 opaque ID；未来服务按租户＋platform_run_id＋request_id 查幂等记录 |
| platform | 仅服务端枚举 |
| profile_version_id / strategy_version_id | opaque ID；不得用行业名称代替版本 |
| execution | 上述 Claim |
| records | 0–100 条，空列表表示可校验的空批次，不证明无新增或采集成功 |

每条 `CandidateRecord`：

- `kind`：POST / COMMENT / PAGE。PAGE 仅 PUBLIC_WEB；PUBLIC_WEB 的 POST/COMMENT 仍允许，用于论坛。
- `external_source_id`：非空来源公开 ID（1–256 字符）；PUBLIC_WEB 可空，此时按 public_url 作为来源身份，不生成假平台 ID。
- `external_comment_id`：COMMENT 必填（1–256 字符），其余必须空；无可靠评论 ID 的记录由采集器留作待补证，不猜造正式评论身份。
- `public_url`：1–2048 字符，http/https 绝对链接；拒绝 userinfo、控制字符、反斜杠、私网/特殊用途 IP、localhost/本地域名和非默认端口。非 PUBLIC_WEB 还须匹配其平台域名或子域，不接受 lookalike 后缀；不请求网络，不宣称通过 DNS/SSRF 验收。
- query/fragment 中拒绝命中 token/cookie/session/authorization/signature/password/secret 的参数名（忽略大小写，解析 URL 编码）；片段只接受 1–128 字符的字母数字、`_ . : -`，供无凭据的评论锚点使用。不静默去掉敏感参数后声称原链接仍可重开。
- `title`：可空，非空时 1–512 字符；`author_public_id`：可空，非空时 1–256 字符，匿名买方不因此排除。
- `body`：非纯空白原文，1–20000 字符；保持 JSON 解码后的原 Unicode 文本，不 trim 或改写，不声称等于来源 HTTP 原始字节。拒绝 NUL 及除制表/换行/回车外的控制字符。
- `published_at`：可空；`observed_at`：必填。均采用精确 `YYYY-MM-DDTHH:MM:SSZ`，必须是真实日历 UTC 时间且不晚于调用方传入的可信 `now`；发布时间不得晚于观察时间。未知发布时间保留 null，不用采集时间或父帖时间填充。不在原始入站层套 60 天商机过滤，筛选时由 Skill/复核判断时效。
- `parent`：可空；仅 COMMENT 可有。必填字段为 `external_comment_id`；`body/author_public_id/published_at/public_url` 可空，非空时边界同上。只知道父 ID 时保留关系和 null 正文，不丢弃子评论，也不编造父正文。父评论 ID 不得等于自身 ID；父发布时间若已知，不晚于已知子评论时间或观察时间。父上下文的时间不能刷新子评论时效。
- `collector_version`、`normalizer_version`：opaque ID；`query`：可空，非空时 1–500 字符，保留观察来源；不用查询内容作为同一公开对象的身份。

所有对象均拒绝未知字段。原文、父上下文是非受信业务内容，不能成为工具指令；校验器不判断买方真假/预算，不承诺能识别原文内所有秘密，调用方仍负责只上传授权公开内容且不记录 payload。

## 4. 身份、版本、批次与重放

纯函数采用 UTF-8 的 canonical JSON（sort_keys、ensure_ascii=False、紧凑分隔符）再 SHA-256，禁止依赖 Python hash 或简单冒号拼接：

- `source_identity(record, platform)`：platform、kind、来源 ID（空时 public_url）及评论 ID；PUBLIC_WEB 还必须始终加入规范 origin（scheme 小写、hostname 经 IDNA 转 ASCII 并小写、默认端口省略）。不同网站可以有相同站内 ID，不能因此合并；平台或来源不同不合并，匿名作者不能按昵称跨平台合并。
- `content_version(record)`：公开 URL、title、author、body、published_at、parent 的结构化快照。不包含 observed_at、query、collector/normalizer_version。重复观察不改版本；正文、作者、时间、定位链接或父上下文变化产生新版本。
- `batch_fingerprint(batch)`：全部校验后的上传字段，去掉 request_id。相同语义字典键顺序不影响指纹；record 顺序、观察时间、执行/画像/策略版本不同必须改变指纹。同 request_id 重试应使用原上传内容；新观察使用新 request_id。
- 单批内同一 source_identity 重复且 content_version 相同：`DUPLICATE_RECORD`；不同版本：`SOURCE_VERSION_CONFLICT`。两者都整批拒绝，不挑一条留下。跨批内容变化允许形成新版本，由02B持久化，不沿用旧不可变 Signal 的全局拒绝规则。
- `replay_decision(stored_fingerprint, incoming_fingerprint)`：无记录→NEW；同摘要→REPLAY；不同→CONFLICT。只是纯比较，不是持久幂等或并发保证；02B 必须在已认证空间的唯一约束和事务中使用。

## 5. 错误、API 接入与消费

公开校验入口 `validate_candidate_batch(payload, *, now)` 返回冻结的 CandidateBatch 或 `CandidateContractError`。外部可见错误只有稳定码：`INVALID_BATCH`、`INVALID_RECORD`、`INVALID_EXECUTION_CLAIM`、`INVALID_SOURCE_URL`、`INVALID_SOURCE_TIME`、`DUPLICATE_RECORD`、`SOURCE_VERSION_CONFLICT`。异常文本/表示不包含原文、URL、字段值、底层 Pydantic 输入或 traceback 中的 chained validation error。调用方禁止打印上传对象。

未来02B为已有 request_id 查询保存的结果，查询必须使用原租户＋原 platform_run_id＋request_id 复合键，不能换成当前运行项；已成功请求的合法产品用户仍可只读查询，不因执行租约后来失效而把原成功改成 UNKNOWN。缺少记录/响应超时不是 FAILED。与01C/03的执行授权、原请求查询协议交接后再提供 HTTP 上传，当前不新增可对外访问的路由、IPC 白名单或 capability 开关。

R3 Candidate 是展示/审核对象，不是采集上传体。id/revision/sourceVersionId/status/assessment/opportunityId/reviewedBy 等由服务端建立，设备不能填入。展示适配需明确发布时间 null→未知，不能填当前时间、父时间或伪造 ISO 时间；现有 string 字段由后续展示契约协调。本卡不改 R3 页面或夺取 Win 的适配器代码。

URL 安全入站拒绝不证明来源不存在或没有业务需求。无法安全保留回链的对象由连接器记作待补证，不计成无新增；拒绝参数名按 URL query 解析后的名称作上述敏感子串匹配，不扫普通参数值来臆测业务含义。安全检测不是凭据发现的完全保证。

接收方使用 `uv run --frozen pytest -q tests/test_candidate_contract.py tests/test_source_capabilities.py` 复现，并在任务书记录精确 SHA 与 ACK；只有 DTO/纯函数通过时不得写“已上传、已鉴权、已采集、已连接、已复核”。

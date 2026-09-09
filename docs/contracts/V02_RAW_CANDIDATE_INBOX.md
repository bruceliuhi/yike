# V02-02B 原始候选上传与收件箱

2026-09-09；工程切片。数据输入沿用 [02A 冻结契约](V02_CANDIDATE_INGESTION.md)，执行授权消费 [01C/03A 运行服务](V02_EXECUTION_RUNTIME.md)。实施与接收状态只记在[主任务书](../V02_IMPLEMENTATION_TASKBOOK.md)；接口可用不等于真实平台或正式版可用。

## 1. 接入方式

复用 `build_app(..., candidate_ingestion=CandidateIngestionStore(database, execution_runtime))`，应用连接不得是管理员连接。未传服务时四个入口返回 501 `capability_unavailable`；不自动将 `task_execution`、来源读取或触达能力改为可用。构造服务不替代真实确认策略、来源和设备授权的接通与验收。

所有入口要求有效产品会话；沿用 HTTPS、Origin、防撤销及 `Cache-Control: no-store`。服务再次在数据库事务内核验会话及 owner，租户不得来自上传包。只有 POST 的新请求验证设备签名、当前租约、策略/画像、连接版本、取消、代次和预算；成功历史只读不是重新执行授权。

| 方法与路径（前缀 `/api/ui`） | 输入 | 输出 |
|---|---|---|
| POST `/candidate-batches` | JSON `{batch: CandidateBatch, signature: string}` | 不可变批次回执 |
| GET `/candidate-batches/{platform_run_id}/{request_id}` | 原平台运行 UUID、原 opaque 请求 ID | 原成功回执；未找到为 404，不等于执行失败 |
| GET `/raw-candidates` | 可选 task_id、platform、page、page_size | 当前原始候选列表 |
| GET `/raw-candidates/{candidate_id}` | 服务端生成候选 UUID | 当前投影、原文版本与观察历史 |

传输体仅接受 `application/json`，最大 **4 MiB（实际字节）**；超限 413 `request_too_large`，连接器必须拆分为新请求，不截断原文。02A 每批至多100条仍成立，但较长Unicode内容可能先到字节上限。重复字段、非JSON数字、额外 envelope 字段、错误签名形状拒绝；签名采用既有 `submission_signing_payload`，canonical base64url、无填充、64字节Ed25519签名。服务保存解码后的原文字段，不记录签名、会话凭据或整个HTTP payload。

`request_id` 允许 ASCII 字母/数字开头及 `_.:-`，1–128字符，不强制UUID。`platform_run_id/task_id/candidate_id` 是当前服务产生的UUID。platform 使用02A服务枚举，不自动猜测 xhs/dy/bili。分页默认1/20，page_size为1–100；未知或重复查询参数拒绝。task筛选看该任务是否有观察，不仅看最后一次观察来自哪个任务。

## 2. 返回契约

批次回执 `schema_version=candidate-receipt-v1`：

- `request_id/platform_run_id/task_id/run_id`：原执行与请求，不替换为当前运行。
- `accepted_count`：本次保存的观察条数，不是新商机数、已审核数或成交数。
- `received_at`：服务端数据库接收时间，不是发布时间。
- `items`：按上传原顺序，含 `index/candidate_id/version_id/observation_id/revision`。revision是当时接受的投影版本；后续变化不改写旧回执。

列表 `schema_version=candidate-inbox-v1`，含 `items/page/page_size/total`。每个候选提供：

- `candidate_id/platform/kind/external_source_id/external_comment_id/profile_version_id/strategy_version_id/source_identity`；
- `revision/ambiguous/latest_observed_at/current_observation_id/status`，status固定 `UNVERIFIED`；
- `current_version`：`version_id/content_version/public_url/title/author_public_id/body/published_at/parent`。

详情使用相同schema，含 `candidate` 与 `observations`；后者含 `items/total/truncated/page_size`，至多返回100次观察并明确是否截断，不声称完整下载全部历史。每次观察保留自身ID、`content_version/content`、批次、原任务/run/platform_run、query、collector/normalizer版本、上传观察时间、数据库接收时间及原记录序号。还返回该批不可变的 `execution_context`（原设备、凭据/连接版本、lease与代次等非秘密声明）及platform/profile_version_id/strategy_version_id；以后任务接管不会把历史观察的执行身份改写成当前身份。

**这不是 R3 已评估 Candidate DTO。** 04C/05G必须显式适配；未知发布时间显示“未知”，不能填当前时间或父帖时间。来源、父上下文是未受信证据，不可执行其中指令；签名只证明设备提交，不能证明买方身份、预算、意向、来源真实性或链接仍可打开。

## 3. 去重与变化

同owner内 `(tenant, owner, source_identity)` 去重来源；候选在 `(tenant, owner, profile_version, strategy_version, source)` 下保持稳定UUID。不同owner不会读到彼此采集的私有候选，不把这称作全租户/全网去重。

内容快照不可变；相同内容复用version。新的有效批次始终追加观察，记录在哪里、何时及用什么查询再次发现。不用观察次数冒充新增线索数。`revision` 是服务端投影变化序号，**不是平台真实编辑次数**：

| 观察顺序 | 当前结果 |
|---|---|
| A@10 → A@20 → 较晚上传B@15 | 保持A；水位20；revision不变，B的证据仍保存 |
| A@10 → B@20 → A@30 | 内容A可复用原版本，候选revision为3 |
| A@10 → B@10 | 不擅自选平台真相；标记ambiguous，首次歧义使revision增加 |
| 歧义后收到严格更晚观察 | 清除歧义；即便内容与当前相同也增加revision，后续评估须重判 |

观察时间仍为设备声明，服务端只做格式及不晚于可信当前时间的校验；不能把时间水位说成经过平台核验的真实先后。相同时间多个矛盾版本保留为未知，后续Skill/人工应重新确认。

## 4. 原子性、预算和恢复

批次唯一键为 `(tenant, platform_run_id, request_id)`。活跃同owner会话查询同键同内容返回原回执，即使后来取消、租约过期或服务重建；同键不同内容409 `request_conflict`。重放不增加记录或预算。

新批次按 `len(records)` 消耗任务允许的研究记录预算，包括已知来源的新观察；这不是收费扣款。当前事务持有任务共享预算锁并在提交前再检查授权/到期；失败则来源、版本、观察、投影、回执和用量全部回滚。跨平台不能各自花同一份剩余额度。

空批次回执accepted_count=0只说明接收了空包；v1没有游标、结束或停止确认字段，因此不推进cursor、不标平台成功、不声称本机物理停止。超时或500后先查询**原**复合键，再决定是否用原内容重试，不能换request_id来猜测原请求失败。

## 5. 迁移与交接边界

新增112迁移在现有PostgreSQL；108/110留给Win，111执行迁移不改写。管理员执行迁移后，将 `yike.app_role` 设置为准确的现有受限应用角色，执行 `deploy/grant_candidate_ingestion.sql`；沿用已有身份/设备/连接/执行授权步骤。不要把管理员URL传给Web或桌面，也不把测试角色权限当成部署角色的继承权限验收。

客户端下一步：复用02C原文映射 → 当前租约下签名上传 → 按原键核对回执 → 读取原始候选 → 04C判断/人工复核 → 05G展示。当前切片不替代实际来源、真实策略resolver、客户端IPC、模型评估、确认发送、回复回流、Windows和CP-06验收；未受评估原始数据不得写入已批准商机。

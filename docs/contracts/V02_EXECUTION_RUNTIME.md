# 01C / 03A 执行服务接入契约

协议：`execution-runtime-v1`。负责人：CodexiMac；迁移 **111**。108（资料）和110（搜索建议持久化）保留给CodexWin。当前实施及审核状态以[任务书](../V02_IMPLEMENTATION_TASKBOOK.md)为准。

## 这段链路解决什么

把用户确认的研究配置变成持久任务、单次运行和逐平台运行；只有当前获授权设备才能领取短租约，提交结果必须属于该任务和当前执行代次。取消后立即停止接受旧执行者结果；网络重试核对原请求，不重复创建任务或延长租约。

它不执行浏览器采集，不生成AI策略，不证明平台已连接，也尚不写入原始候选。后续02B在同一事务使用提交护栏后写入候选、观察和回执。普通客户端的`task_execution`能力保持关闭，直到真实策略、来源和桌面执行器接通。

## 固定服务入口

服务端注入 `build_app(..., execution_runtime=ExecutionRuntime(...))`，没有注入时，已认证用户访问下列入口得到501；不创建替代执行器。

| 方法与路径 | 输入/输出 |
|---|---|
| POST `/api/ui/execution-signing-payload` | `{request: ExecutionOperation}`，返回本机设备待签的原文字节及请求绑定，不执行任务 |
| POST `/api/ui/execution-operations` | `{request: ExecutionOperation, signature: string}`，返回原操作回执 |
| GET `/api/ui/execution-operations/{request_id}` | 当前有效产品会话读取自己原请求的不可变回执 |
| GET `/api/ui/execution-tasks/{task_id}` | 当前有效产品会话读取自己任务的当前状态 |

沿用现有HTTPS、Origin、会话撤销和`no-store`响应；不会把签名、令牌或请求原文回显到错误。未知服务故障返回安全错误，不等于操作确定未执行；客户端应查询原请求。404仅表示没有找到可见回执，不证明此前请求失败。

这不是UI `TaskOperationsService` 的直接替代：既有研究用量/搜贝预留不是执行硬预算和签名协议。实际确认策略服务已接入普通runtime，但客户端仍须明确绑定策略、设备/连接及执行版本。各版本旧hash和本机未决记录必须原样保留。05F需要显式的新配置确认/签名适配，再接已有页面；不能仅把URL接上就开启按钮。

主线R4的`TaskDraft.research`、搜贝quote/预留摘要及`researchContractVersion=1`不能单独证明本协议必需的真实确认策略/设备授权。该前端版本号与本服务`execution-runtime-v1`不是同一协议；本片没有收费预留或扣减，record预算不能代替搜贝规则。接入时保留新旧请求各自原hash/未决记录，显式完成协议适配，不伪造估算或空间身份。

## 输入与签名

`request`包含精确协议版本、原请求UUID、设备UUID、严格整数凭据版本和操作。未知字段拒绝，不接收租户、复核人、执行权限、预算或自报成功。

- START：画像版本ID、策略版本ID、完整确认配置摘要和1～5个不重复目标平台。
- CLAIM：任务ID和逐平台运行ID。
- RENEW：在CLAIM标识外，带当前租约ID和执行代次。
- CANCEL：任务ID。策略被撤销或连接失效后，合法任务所有者仍能取消。

非该操作所需字段必须为null；目标平台使用02A服务枚举。平台账号模式绑定连接ID和版本；公开网站匿名模式只能用于PUBLIC_WEB，不伪造账号连接，也不免产品和设备认证。

签名使用既有Ed25519设备钥，签名原文通过`execution_signing_payload`生成，绑定协议域、服务端身份、会话摘要和完整操作。上传则通过`submission_signing_payload`绑定02A整包摘要。已有设备PROVE回执不是新操作签名，不是租约令牌。只读历史回执不要求旧设备继续有效，但不能凭回执执行新操作。

### 05F待签名原文接续

本次实施状态及实际证据见[签名准备QA](../qa/V02_EXECUTION_SIGNING_PAYLOAD.md)，接口约定不代替Win实际消费ACK。

`POST /api/ui/execution-signing-payload`严格只收`request`，不收外层或内层tenant/user/session/token/signature。沿用现ExecutionOperation：非本操作字段可按原模型缺省为null，规范签名原文总是包含全部字段。合法操作仍仅START/CLAIM/RENEW/CANCEL。

响应精确五字段：

- `signing_payload`：现`execution_signing_payload`生成的原字符串，`yike-execution-operation-v1`域，UTF-8、ensure_ascii=False、按key排序的紧凑JSON；包含当前服务端tenant/user/session_digest和完整规范operation。
- `request_id`、`device_id`、`credential_version`：分别等于规范请求值。
- `request_sha256`：完整规范operation（包含request_id、所有null及targets顺序）的同规则UTF-8 SHA256；不包含会话。它不是数据库排除request_id的`operation_sha256`，不能互换。

客户端主进程应把上述绑定及原文中的完整operation与已固化请求核对，再签服务器返回的原UTF-8字符串；不重新序列化，不读取Cookie或猜tenant，不复用设备BIND/PROVE的另一签名域。包含session_digest的原文不写日志/导出/业务库、不返回renderer；后端HTTP不能识别调用方进程，Win还需通过固定主进程消费落实此边界。签名准备响应与错误均沿用no-store。

准备仅在当前有效会话的短事务中校验本用户ACTIVE设备和精确凭据版本，等待后及返回前重验会话。无业务INSERT/UPDATE/DELETE，但会使用既有事务/行锁，故不是PostgreSQL READ ONLY事务。不存在准备nonce/过期时间/回执；同规范请求和会话返回同字节，换会话摘要相同而原文改变。无设备/其他owner/撤销设备404，旧或缺凭据409，会话失效401；无runtime501。

准备不查询任务、批准策略或来源，不创建任务/run/lease/执行或持钥回执，不占用UUID或预算。未安装来源的正常runtime可准备字节，但真正START仍501。实际apply完整重验；策略或连接失效不阻止原任务设备凭当前有效凭据准备CANCEL，apply再检查任务所有权。生成针对未知任务的字节既不读取其数据，也不授予操作权。

新会话下，尚未执行请求的旧签名拒绝为invalid_proof；应重新取得待签字节。已有成功UUID仍可按现合同GET或重放获取历史回执，不能把历史可读误当作旧签名获准新执行。网络未知先查原execution-operations回执；准备没有产生执行的副作用，不是发送/采集成功证据。

## Win04B需要提供的最小接入

`strategy_resolver(cursor, claims, profile_version_id, strategy_version_id)`在调用方的同一个短事务中，返回`ConfirmedExecutionStrategy`。没有生产resolver时明确不可执行；测试用合成resolver不随生产入口安装。

它必须：

1. 按当前用户/空间读取真实、已经用户确认且未撤销的策略版本，验证画像绑定。
2. 返回精确的公开研究配置、允许平台、技术记录上限和最长运行时间；确认摘要覆盖整个快照，而不是只覆盖关键词。
3. 与用户最终确认的版本和配置一致；不能从模型建议临时生成一个“已批准策略”，也不能把搜索建议请求ID当策略版本ID。
4. 只读写调用方cursor，不提交事务，不在锁内调用模型或平台。锁序与本契约一致。

快照字段：`profile_version_id`、`strategy_version_id`、`configuration`、`platforms`、`max_records`、`max_runtime_seconds`。其canonical JSON按key排序、紧凑分隔、UTF-8计算SHA-256，排除`configuration_sha256`字段本身。平台顺序是确认内容的一部分。配置必须是有界公开JSON对象，不带凭据。

这里的记录/时间上限是执行硬边界，不定义搜贝换算、套餐或收费。`max_records`计首次接收的新批次里的记录条数，包含重复观察；相同请求重放不再消耗。它不是新增客户数、商机数或成交数。

`capability_check(platform, access_mode, configuration)`是服务端固定、无网络调用的来源能力判断；必须依据实际安装和验收范围。它不接受客户端`verified=true`，公开网站必须落实到真实可读站点，不能一个web标签授权全网。

## 任务、租约与取消

START持久化不可变配置及预算，创建PENDING任务、一个run和逐平台run。它不表示采集已经发生。CLAIM才产生绑定设备/凭据/连接的租约，代次从1开始增长。每次租约最多120秒，且不超过从任务创建时间计算的确认运行期限。

重放返回原租约的原期限；续租不恢复过期租约，过期接管产生新代次，旧结果拒绝。后续重新读取策略仅证明同一确认仍有效，不能刷新原预算或任务期限。

CANCEL原子关闭结果提交及续租。如果从未授予任何执行租约，可以确认未开始执行；一旦任何平台获过租约，则保留CANCELLING和`stop_confirmed=false`。租约过期、服务器取消和客户端超时都不证明外部进程实际停止，09B的停止确认还需另外接入。

## 02B必须遵守的原子提交顺序

```text
有效会话 → 原批次幂等锁/历史回执
→ 当前设备/钥/连接/画像/策略 → task/run/platform/lease
→ 按来源身份排序写原文版本与观察
→ 记录用量和原批次回执 → 最终期限与取消核验 → 提交
```

`lock_submission(cursor, claims, batch=..., signature=...)`必须在调用方事务内使用，检查完整绑定及剩余预算；不自行提交、不写候选、不宣布任务完成。返回结果仅在当前未结束事务中有效，不能缓存到下一次事务。

写入用量后调用`recheck_submission_fence`重新检查会话、时间、代次、取消及版本，不再把本批次当新消耗计算一次。候选/观察/回执/用量任一失败，整批回滚；同原请求成功回执优先返回，不因当前租约失效否认历史成功。

空批次仅证明接收了这个批次，不证明“无新增”或任务完成。游标、完整运行终态和停止确认需要独立真实协议，不能从空数组推断。

## 验收边界

接口、合成策略与真实PostgreSQL/Ed25519测试只证明工程行为，不证明模型建议质量、平台可采、客户端自主使用或客户UAT。完整01C/03A、02B入库、05F接入、调度恢复、真实平台以及M3/CP-06继续保留。准确命令、审核与提交随本切片实际完成后写入任务书，不用本合同替代运行证据。

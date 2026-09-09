# 设备登记与本机身份恢复合同

2026-09-10；位于已批准V02-01/05D/05F的正常登录与可恢复客户端链路内。基线`5b1d7db`，这是待实施合同，不是Win已接收或真实平台已连接。

## 最小范围与选择

客户点击连接平台时，客户端必须先持久化登记request_id；网络超时只能按原请求核对，不能凭设备名称或租户设备列表认领本机。沿现有会话、设备表、公钥挑战和撤销机制补三个窄接口，不增加新的登录或执行授权体系。

采用独立的登记回执表：旧设备表没有原请求/原标签快照，公钥请求表只允许BIND/PROVE/ROTATE且绑定挑战，均不能准确保存“尚未绑定公钥的首次登记”。不扩展这些旧操作语义。历史设备NULL owner不自动迁移或认领。

## 接口

所有请求需要当前认证会话、既有HTTPS/Origin约束，响应`Cache-Control: no-store`。tenant和owner由服务端解析，不接收外传身份。旧`POST /api/ui/devices`保持兼容，但不用于新版客户端的可靠登记。

| 接口 | 输入 | 输出 |
|---|---|---|
| POST `/api/ui/device-registrations` | 精确`{request_id,device_label}` | HTTP201，原登记回执 |
| GET `/api/ui/device-registration-requests/{request_id}` | 已保存的原UUID | HTTP200，同一个原登记回执 |
| GET `/api/ui/devices/{device_id}/identity` | 本机已知device_id | HTTP200，当前owner范围内的身份状态 |

request_id/device_id使用规范小写UUID字符串。标签为严格字符串、去首尾空白后1–128个Unicode码点，拒绝NUL及无效Unicode；POST JSON原字节上限4096，拒绝未知/重复键、非对象、隐式类型转换、非有限数字及坏UTF-8。传入owner、tenant、device_id、公钥、凭据版本或时间都无效。

登记回执精确五字段：`{request_id,device_id,device_label,registered_at,state:"SUCCEEDED"}`。UUID由服务器生成；标签使用规范化后原标签；registered_at取同次数据库插入时间并以带时区ISO8601返回。它证明该原请求已登记，不证明设备当前ACTIVE、持有私钥、平台连接或执行授权。

当前身份精确四字段：`{device_id,device_status:"ACTIVE"|"REVOKED",credential_version,public_key}`。未绑定返回`0/null`，已绑定返回实际正整数版本和规范base64url Ed25519公钥。只返回当前用户拥有的已知设备；其他owner、其他租户、NULL owner和不存在设备均404 `device_unavailable`。REVOKED设备可读自己的历史公钥状态，但必须停止后续操作；此读取不替代BIND/PROVE/执行时的当前版本检查，也不作为发送批准。

## 原请求恢复与事务

登记唯一键为`(tenant_id,owner_user_id,request_id)`。同owner、同request_id、相同规范标签返回完全相同回执；不同标签409 `request_conflict`。不同owner可以分别使用同UUID，但不能读取或冒认对方结果。同标签、新UUID是另一次登记，客户端不能因此盲目重试。

设备创建与原登记记录必须同一短事务。相同原请求的多会话并发只生成一台设备，不留孤儿设备。复用既有会话事务护栏，在请求锁等待后、提交前按数据库时间重验当前会话；会话过期/撤销401 `invalid_session`，不能读旧回执逃过认证。

原请求GET不写入、不重新登记、不自动绑定。设备撤销、绑定或轮换后，原登记回执不改变。新会话仍可找回同owner原回执；客户端再读当前identity判断是否可继续，且与本地受保护密钥比对。公钥不一致时停止自动绑定/执行，不覆盖密钥或自动轮换。

未知request_id返回404 `request_not_found`。原请求查询404不证明另一个仍在途POST绝未提交；若要重试仍使用同UUID/同标签，不能换UUID。POST存储或提交确认异常返回503 `registration_outcome_unknown`；客户端先查原请求。读取存储故障返回503 `device_registration_unavailable`，不伪装成404、空状态或成功。错误和日志不包含原载荷、密钥、token或SQL异常细节。

## 存储与验收

116预留本片：`pilot_device_registrations`仅保存tenant、owner、原request_id、device_id、规范标签和数据库registered_at。复合外键指向既有owner设备；owner级强制RLS，应用仅SELECT/INSERT、无UPDATE/DELETE；可信升级脚本拒绝超级用户/BYPASSRLS/表owner。既有106等迁移不可改写。正式发布仍须独立完成CP-06实际环境授权，测试SET ROLE不替代部署验收。

交付需真实受限PG与实际认证HTTP证明：登记→BIND/PROVE→当前身份→原请求恢复；并发同请求无重复、不同标签冲突、原回执不随轮换/撤销变化、跨owner/租户/NULL owner拒绝、会话撤销与等待中过期拒绝、存储失败准确归未知。没有私钥或平台会话入库，不执行真实外联。Win实际客户端/Windows/平台仍单独验收。

# V02-01C 连接版本、操作回执与事务内检查

本切片只提供后端连接失效栅栏。REGISTER 仍为 UNVERIFIED；HTTP 成功和历史回执不证明平台登录、Windows ACK、执行许可或真实采集。正式客户库仅 PostgreSQL。测试 CONNECTED 仅由受信 SQL 写入合成记录。

## 版本规则

107 增加 `connection_version INTEGER NOT NULL DEFAULT 1`，范围 1–2147483647。升级保持原状态、账号、vault 引用不变，INSERT 只允许 1。非 SECURITY DEFINER 的 BEFORE 触发器在 device_id/platform/account_public_id/session_ref/status 任一变化，或显式请求旧版本加 1 时，恰好递增一次；无变化 UPDATE 不递增。跳跃、回退、NULL 报 `YC002 / connection_version_conflict`；最大版本后的字段变化报 `YC001 / connection_version_exhausted` 并原子回滚，不环绕、不重置。SQL 表达式自身超出 INTEGER 范围可能先触发 PostgreSQL 类型溢出，所以支持的注册服务在锁内先检查最大版本并返回稳定错误。

每次显式注册旧自然键 `(tenant,device,platform,account)` 都递增，即使 vault 引用相同；新 API 同请求重放不再次注册。首次断开递增，重复断开不变；设备撤销使受影响连接失效并递增。遥测不改变连接状态/capability。

旧 connect_platform/disconnect_platform/revoke_device 保留客户空间级管理含义。可信内部调用可省略 keyword-only claims；真实 JSON HTTP 调用传当前验证 claims，并在同一事务中检查用户匹配、会话撤销/过期及等待后数据库墙钟。这不是设备所有者执行授权。

## 严格 HTTP 请求

`POST /api/ui/connection-operations` 和 `GET /api/ui/connection-operations/{request_id}` 沿用 HTTPS、Origin、会话和 `Cache-Control: no-store`。不增加 IPC、任意 URL、capability。

POST 必须包含 request_id/action/device_id/connection_id/expected_connection_version/platform/account_public_id/session_ref。UUID 必须规范小写；不允许额外字段、强转、布尔版本、控制字符或秘密式引用。版本严格 0–2147483647；结构错误不回显输入。

REGISTER：connection_id 为 null，platform 是服务枚举精确值，账号和 opaque vault 引用满足现有约束，且不做字符串归一化。expected 0 表示自然键不存在；正数必须等于当前版本。DISCONNECT：connection_id 为规范 UUID，expected 为正数，platform/account/session_ref 全 null。

业务结果 HTTP 200 的精确形状如下，失败注册可能有全 null 的连接字段：

```json
{"request_id":"UUID","device_id":"UUID","action":"REGISTER","state":"SUCCEEDED","connection_id":"UUID","connection_version":1,"connection_status":"UNVERIFIED","error_code":null}
```

REJECTED 不变更连接，固定 error_code 为 device_unavailable/connection_unavailable/connection_version_conflict/connection_version_exhausted。结构错误 invalid_request 422，会话失效 invalid_session 401，同请求不同正文 request_conflict 409，查无回执 request_not_found 404；旧接口版本耗尽安全 409。GET 404 不证明超时操作失败，使用同请求 ID/正文重试或继续查询。

## 不可变历史回执

请求身份 `(tenant_id,owner_user_id,request_id)`。严格验证正文去掉 request_id 后以排序键、紧凑 UTF-8 JSON 计算 SHA-256，保留语义字符串。回执只保存哈希、安全固定字段、结果连接/版本/状态、创建时间，不保存 session_ref、签名、Bearer 或任意正文。

经根任务澄清，requested_device_id 仅保存调用者提交的规范 UUID，对外仍为 device_id；另有 nullable authorized_device_id，非空时必须等于请求设备，并通过 `(tenant_id,owner_user_id,authorized_device_id)` 外键指向真实所有者设备。不存在/他人设备使用 null 授权绑定，只允许 REJECTED/device_unavailable 且连接结果全 null；不引用或暴露他人设备。已归属但撤销设备保留授权绑定并拒绝。所有回执还有 `(tenant_id,owner_user_id)` 用户外键与 tenant+user FORCE RLS。失败也能持久重放，不伪造授权绑定。

锁顺序 session → 用户/请求 advisory → device → connection。请求锁使用 PostgreSQL 双整数 namespace 10701，与会话 bigint namespace 分离。历史回执检查先于活跃设备和预期版本检查，故重连、断开、撤销后同请求仍返回原结果，不续期、不改历史版本。等待后、查询回执后和提交前重检墙钟会话。变更与新回执在同一短事务提交，插入失败回滚变更，无事务外 pending 行。

应用回执仅 SELECT/INSERT，无 UPDATE/DELETE grant 或 RLS policy。管理员是受信迁移/恢复边界，不能带入应用。授权脚本拒绝缺失、超级/BYPASSRLS/CREATEROLE 角色及相关表 owner。

## 当前版本检查

`ConnectionOperationStore.lock_current(cursor, claims, *, device_id, connection_id, connection_version, platform)` 使用现有事务 cursor，不新建连接、不提交。严格验证输入，按 session → ACTIVE 所有者设备 → connection 锁顺序检查同 tenant/device/platform、精确正版本与 CONNECTED，等待后重检会话。只返回 `{connection_id,connection_version,platform,account_public_id}`。

这不是 AuthorizedExecution。未来执行层还必须在**同一结果提交事务**检查持钥/credential、任务/确认配置、run、lease、generation，不得把历史 PROVE 回执当许可。PUBLIC_ANONYMOUS 由未来执行层处理，不在此虚构已登录连接。事务不跨浏览器、模型或网络等待。

## 验证边界

专用真实 PostgreSQL 测试覆盖重复注册、触发器、同/不同请求竞态、不可变拒绝、插入失败回滚、注销先后顺序、锁等待中过期、三个旧变更与检查器的双向并发、跨租户/同租户其他所有者隔离，独立随机数据库 101–106→107 升级两次和授权两次。真实 TestClient + 受限 PostgreSQL 验证 HTTP、安全错误与旧变更等待过期回滚。

实际 Windows ACK、真实平台动作、完整 01C/03A/02B、生产/UAT 和上线 Goal 均另行验收，不由本契约或合成测试宣称完成。

# V02-01A：设备、连接登记与报告事件契约

负责人：CodexiMac。基线：`15ddb7039e385c9adbda04bfd553bf8d222e6308`。
状态：`da2a2f2` 已获本地独立复审 PASS，仍待 CodexWin 交叉验证；不是 V02-01 完成或真实平台连接证明。

## 可用接口

所有 `/api/ui` 写入继承现有登录及 Origin 检查。租户从服务端用户身份解析；客户端提交 `tenant_id` 返回 422。

| Method | Path | 请求字段 | 结果 |
|---|---|---|---|
| GET | `/api/ui/devices` | 无 | 当前租户设备元数据列表 |
| POST | `/api/ui/devices` | `device_label`，1–128 字符 | 新建 ACTIVE 设备记录；不是设备身份认证 |
| POST | `/api/ui/devices/{id}/revoke` | 无 | 撤销设备记录，同时断开其连接登记 |
| GET | `/api/ui/connections` | 无 | 连接元数据，不返回凭据引用 |
| POST | `/api/ui/connections` | `platform, device_id, account_public_id, session_ref` | 新建/更新 UNVERIFIED 登记，不可自报 CONNECTED |
| POST | `/api/ui/connections/{id}/disconnect` | 无 | 断开当前租户的连接登记 |
| POST | `/api/ui/execution-events` | `device_id, connection_id, execution_generation, event_type, payload`；可选 `task_id` | 仅附加客户端报告的遥测，不变更任务、游标、商机或业务指标 |

平台枚举：XIAOHONGSHU、DOUYIN、BILIBILI、ZHIHU、PUBLIC_WEB。枚举存在不代表已接通平台。

`session_ref` 仅为 `vault://` 开头的不透明引用；本任务不实现 vault，也不证明引用可读取。Cookie、验证码、私密会话及实际凭据禁止上传。真实连接核验及专用会话存储由后续设备认证/执行器任务实现；`platform_connections.available` 保持 false。

## 报告事件

- STARTED/CANCELLED/CONNECTION_EXPIRED/CONNECTION_REVOKED 的 payload 只能为空对象。
- COLLECTION_PROGRESS/COLLECTION_SUCCEEDED 仅接收 `raw_count`、`unique_count`，为 0～2147483647 的整数，拒绝布尔、字符串、嵌套对象和自由文本。
- COLLECTION_FAILED 仅接收固定 `error_code` 枚举，见 `pilot/identity.py`；禁止错误原文、异常对象或额外字段。
- 事件要求 ACTIVE 设备与已核验的 CONNECTED 连接，当前注册接口不能赋予此状态。提供 task_id 时，服务端及数据库均检查同租户任务存在。
- 存储短事务固定按设备、连接顺序锁定，检查撤销状态后写入。没有浏览器、模型或网络长事务。
- execution_generation 目前是客户端报告字段，不是执行租约授权。不得用于推进任务或确认结果；V02-03 必须另外校验服务端执行代次、所有者及连接授权版本。

## 未完成范围

正常客户激活/登录、服务端会话撤销、设备凭据绑定、真实平台扫码/账号核验、连接凭据更换后的旧执行失效、调度和游标 fencing、Windows sidecar 均未由本 V02-01A 候选实现。`da2a2f2` 的 token 退出仍只清除客户端 Cookie；后续 V02-01B 已另外开发[服务端撤销候选](V02_SESSION_REVOCATION.md)，其验证不能沿用 01A 的 PASS。

## 验证与交接

- `tests/test_identity_contract.py`：字段白名单、边界值、迁移唯一性及路由契约。
- `tests/test_identity_postgres.py`：专用 PostgreSQL、非超级用户 RLS、同租户外键、真实行锁并发与 HTTP API；使用合成身份，不接触平台账号。
- 测试需要 `YIKE_IDENTITY_TEST_DATABASE_URL` / `YIKE_IDENTITY_TEST_APP_DATABASE_URL` 指向专用一次性测试库，不能指向生产库。
- 未发布的 104 迁移已在本分支修订；复审应使用新空库，不在已应用旧候选迁移的数据库上覆盖 checksum。
- CodexWin 首先复核本契约及对应提交；未合并前不能把这些接口当作 main 已交付能力，也不在同一分支并发写入。

# V02-01C 服务端设备密钥持有证明

本切片只实现服务端绑定、一次性证明与双签轮换，不是完整 01C。回执是历史证据，不是 bearer token、执行许可或平台已连接证明。正常手机登录、Windows 私钥保护/传输、连接代次、lease/claim/renew/cancel、候选上传 API、真实平台操作、发行及 UAT 仍未完成；原能力标记不变。

## 接口与严格字段

沿用产品会话与同 Origin 包装，生产需要 HTTPS，全部响应 `Cache-Control: no-store`。tenant/user 仅来自服务端已验证会话。

| 接口 | 请求字段 | 返回 |
|---|---|---|
| `POST /api/ui/devices/{device_id}/key-challenges` | request_id, operation, expected_credential_version, public_key | request_id, challenge_id, signing_payload, expires_at |
| `POST /api/ui/devices/{device_id}/key-challenges/{challenge_id}/complete` | signature, previous_signature（可省略，默认 null） | 窄回执 |
| `GET /api/ui/device-key-requests/{request_id}` | 无请求体 | 窄回执 |

UUID 是 36 字符小写标准字符串。版本是严格整数 0..2147483646，拒绝布尔/字符串。公钥是 32 字节无 padding canonical base64url（43 字符），签名为 64 字节（86 字符）。拒绝额外字段、错误类型、非 canonical 编码和无效/小阶/非主子群曲线点。使用锁定 `PyNaCl==1.6.2` 的 libsodium `crypto_core_ed25519_is_valid_point` 与 `VerifyKey.verify`，无手写曲线算法。私钥只由客户端持有，服务端不生成、不接收、不存储。

- BIND：版本 0、提供公钥、尚无凭据；目标私钥签名，成功版本 1。
- PROVE：当前版本、public_key 必须显式 null；当前私钥签名，版本不变。
- ROTATE：当前版本、不同的新公钥；signature 由新私钥签名，previous_signature 由旧私钥签名，两者签相同字节，成功版本加 1。非 ROTATE 不接受 previous_signature。

## 精确签名字节

客户端直接签返回 signing_payload 的 UTF-8 原字节，不重新序列化或自行构造 payload。它是 ASCII JSON，`sort_keys=True,separators=(',',':'),ensure_ascii=True`，且仅包含：

`protocol='yike-device-proof-v1'`, `tenant_id`, `user_id`, `device_id`, `request_id`, `challenge_id`, `session_digest`, `operation`, `expected_credential_version`, `target_public_key`, `nonce`, `expires_at`。

nonce 由服务端 `secrets.token_urlsafe(32)` 生成（43 字符）。expires_at 为数据库 UTC epoch 整数秒加 120，秒精度向下取整不足 1 秒。PROVE 的 target_public_key 是创建时当前公钥。session_digest 是已验证产品令牌签名字节的非秘密撤销摘要，不是原 token。协议域、随机 nonce、持久化 challenge 与身份/会话/版本绑定防止跨请求重用；completion 不接收客户端 payload。

## 生命周期与重试

每设备最多 5 个未过期 PENDING 挑战。同 request_id/相同意图返回原挑战（先于配额检查）；同 ID 改设备、操作、版本或公钥返回 request_conflict。失败验签或版本冲突消耗为 REJECTED；过期 completion 消耗为 EXPIRED。拒绝/过期后必须新建 request_id。结构无效 HTTP 请求在服务调用前拒绝，不进入验签。

重复成功 completion 返回原回执，不重复轮换。窄回执仅含 request_id、device_id、operation、state、credential_version；未成功版本为 null。状态为 PENDING/SUCCEEDED/REJECTED/EXPIRED；未知 ID 返回 request_not_found，不捏造 FAILED。历史成功不会因设备后来撤销或轮换改写。新登录可查本人历史，但不能完成旧会话 PENDING。重启从数据库恢复；执行授权必须独立检查实时状态。

新设备 owner 来自已认证用户；历史 NULL owner 不自动认领、不能绑定。同租户他人不能绑定或查证明；既有租户管理撤销权不变。写入先锁会话身份，再锁设备，最后挑战/凭据；logout 稳定排序后先锁全部身份。等待后使用数据库 clock_timestamp 重查有效期，拒绝结果提交事务后再抛固定错误。

错误：invalid_request 422、invalid_session 401、device_unavailable 404、request_conflict/credential_conflict 409、invalid_proof 400、challenge_expired 409、challenge_limit 429、request_not_found 404、internal_error 500。既有 HTTPS/Origin 包装另有 https_required 400 与 Origin 拒绝 403。错误不回显公钥、签名、token 或 SQL。

## 运维及证据边界

先 migration 106，再显式 `deploy/grant_device_credentials.sql`，最后启新版应用；命令见[客户试用手册](../CUSTOMER_PILOT_RUNBOOK.md)。保留 101..105；运行时无 owner/BYPASSRLS、schema CREATE、pilot_users UPDATE 或新表 DELETE。新表 FORCE RLS 按 tenant + user 隔离，以组合外键固定设备 owner。只存公钥、公开挑战、撤销摘要和窄结果，不存私钥、签名、原 token 或 Cookie。

测试采用瞬时合成密钥、真实受限 PostgreSQL 与实际锁等待观测；覆盖防重放、轮换、过期、身份隔离、HTTP 和 105→106 最小权限升级，不代替 Windows、客户、真实平台或生产验收。

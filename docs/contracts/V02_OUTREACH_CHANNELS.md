# V02 触达对象与确认协议

状态：`CONTRACT_ONLY / NOT_PRODUCTION_SEND`

本文件冻结 V02-06A/07A 的后端对象边界，供真实平台适配器、发送队列和 Windows 客户端后续联调。它不代表任何平台已经接通，也不授权自动发送或绕过验证码、限流和风控。

## 对象与绑定

- `SourceObject`：公开来源对象，必须保留 `source_id`、`opportunity_id`、平台、可重开的公开 URL、作者公开 ID 和来源版本。公开 URL 不得包含 token、cookie、session、password 或 secret 参数。
- `ChannelCapability`：某个已授权连接在某时刻对 `comment` 或 `dm` 的能力状态。只有 `AVAILABLE` 且带 `connection_id` 与 `connection_version` 时，才允许建立收件人映射。
- `RecipientMapping`：服务端从来源和已验证能力解析出的收件人。平台公开 ID 是不透明字符串，不得假设为 UUID；映射必须与来源、商机、渠道、连接和连接版本完全一致。
- `DraftBinding`：待人工确认的草稿，绑定来源 ID/版本、商机、渠道、收件人、连接版本、内容版本。内容只以 SHA-256 摘要进入确认快照。

## 确认与幂等

`bind_confirmation` 只接受完全匹配的来源 ID/版本、来源作者、收件人、渠道、连接版本和草稿内容，生成有过期时间的不可变快照。确认时间之前以及过期之后均无效；连接版本、收件人、渠道、内容或版本任一变化，旧快照必须失效。后续持久层必须对 `request_id` 建立唯一约束：同一请求相同绑定可重放，绑定冲突必须拒绝，不能盲目重发。

当前 `IdempotencyRegistry` 仅是进程内契约模型，用于测试和联调，不是生产存储；生产实现必须在 PostgreSQL 事务中持久化完整快照、原始请求 ID 和状态。

## 发送结果

`SendReceipt` 采用失败关闭语义：

- `SENT` 必须明确 `confirmed=true`；
- `FAILED` 必须明确 `confirmed=true` 且 `confirmed_not_delivered=true`；
- `UNKNOWN` / `PENDING` 不得声称已确认或未送达，必须保留原请求 ID，等待原请求对账；
- 未取得平台回执时不得把页面变化、超时或本地点击当作成功。

模块只做严格校验，不执行外部网络操作，不保存账号凭据、Cookie、验证码或私信正文以外的敏感信息。

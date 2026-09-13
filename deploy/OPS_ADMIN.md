# 运营后台与三天试用

本模块独立部署，入口 `/ops`。代码集成不代表生产已部署，也不代表短信供应商已接通。

2026-09-11接续：056e258独立ops与客户SMS服务已部署，真实管理员HTTPS登录、列表/开通表单、Origin/CSRF和退出检查通过；[当前事实与未验项](../docs/qa/SERVER_137138_DEPLOYMENT.md#运营入口已部署ops2026-09-11复用056e258镜像)。未创建客户或发送SMS，不代表真实试用激活或完整客户端已交付。下方“未配置”说明保留其代码批次边界，当前以该部署记录为准。

## 运营流程

### 当前客户登录路径：手机号 + 短信验证码 + 8 位试用码

运营先登记客户并生成 8 位大写字母/数字试用码，再通过微信等渠道私下发送。客户首次登录必须同时填写手机号、6 位短信验证码和试用码；短信验证、试用码校验和权益激活在同一事务内完成。默认从首次激活起 72 小时，可设置 1–30 天。

客户激活后，后续登录只需要手机号和短信验证码。当前不再向客户展示或签发 `YA-` 临时访问码；历史临时访问码记录保留用于数据兼容，但客户服务不装配该旁路。

预登记手机号不等于验证，后台只按真实 OTP 成功后写入的 `phone_verified_at` 显示已验证。停用或到期后，旧会话也被拒绝。

升级顺序：先认证加密备份，再以受信管理员执行全部迁移，对既有受限客户角色执行 `grant_runtime.sql`，对独立运营角色重新执行 `grant_ops.sql`；必要的数据库 CONNECT 仍只向各自角色授予。先升级并验收客户服务，再升级运营服务，最后才允许运营签发新的 8 位试用码。本实现不自动部署或修改生产权限。

客户临时登录最小配置继续为现有受限 `YIKE_PILOT_DATABASE_URL`、`YIKE_PILOT_AUTH_SECRET` 与至少 32 字节的 `YIKE_PILOT_PHONE_AUTH_SECRET`，不需要新秘密或 SMS 供应商配置。必须与 ops 使用同一现有 PHONE secret，仅使用独立 HMAC 域；不得轮换原 secret 来启用此功能。无 PHONE 配置时 access-session 明确 501；SMS 无供应商时仍保持 501。ops 仍只持独立 DB/管理员密码/手机号加密密钥与共享 PHONE secret，不混入客户 DB、管理员 DB、模型或短信凭据。此次代码/隔离测试不等于真实客户或生产上线。

### 保留的短信试用流程

1. 运营登录后台，登记客户名称、完整手机号，生成 8 位专属试用码；默认激活后 3 天，可选 1–30 天。
2. 通过微信等其他渠道把码私下发给客户。码仅生成当次展示，服务端只存 HMAC，不在日志记录。
3. 客户在原登录页填写手机号、**真实短信验证码**和 8 位试用码。未登记的手机号不自动创建客户、不发送短信。
4. 真实 OTP 校验、权益激活和 OTP 一次消费同事务；失败不开通。默认从激活起 72 小时；未激活的码 30 天后失效。
5. 后续使用短信验证码登录，无须重复输入试用码。已激活的码不能续期，也不能给其他号码使用。
6. 后台看完整手机号、待激活/试用中/到期/停用、激活/到期时间。旧 hash-only 用户不能还原手机号，显示“未留存可还原手机号”。后台中的已验证状态仅对应真实短信激活路径。
7. 未激活的码丢失，可在原客户行“重发码”，确认后原码立即作废，不创建新用户；已激活/停用账号不能重发。
8. 停用须单独确认，不删除客户数据；下一次服务端会话验证会拒绝旧令牌。正在执行的请求不是强制中断语义。

## 隔离部署步骤

先备份、迁移全部 schema（含 136）并运行既有 `deploy/grant_runtime.sql`；先升级客户服务（含共享 trial 会话 gate），再启动运营服务和生成客户，不能把旧客户服务与新运营签发混用。迁移 owner 仍属于受信离线路径。

由可信数据库管理员创建**独立** `yike_ops` LOGIN 角色，使用部署系统秘密管理设置其密码，属性为 NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION；不继承客户运行角色或 schema owner。不把密码写入 SQL/Git/命令行历史。

若业务数据库已撤销 `PUBLIC CONNECT`，还须为该角色单独授予**当前业务库**的 `CONNECT`，不能恢复公共连接权限。当前部署库为 `yike`，对应 `GRANT CONNECT ON DATABASE yike TO yike_ops`；其他环境使用已核验的库名。表授权成功不证明数据库可连接。用实际运营连接构造 `OpsStore` 验证通过后才能公开入口；若角色和密钥已生成但此检查失败，保留它们并修正缺失权限，不能重跑初始化或轮换密钥。

```sh
psql "$YIKE_PILOT_ADMIN_DATABASE_URL" -X -v ON_ERROR_STOP=1 \
  -c "SELECT set_config('yike.ops_role','yike_ops',false)" \
  -f deploy/grant_ops.sql
```

运营进程需要单独的私密环境文件（0600，由部署系统注入；不要提交）：

| 名称 | 要求 |
| --- | --- |
| `YIKE_OPS_DATABASE_URL` | 私网 PostgreSQL 的独立受限运营角色连接 |
| `YIKE_OPS_ORIGIN` | 固定 HTTPS 源，不带路径或末尾斜杠，例如 `https://yike.tuokexing.net` |
| `YIKE_OPS_PASSWORD` | 至少 16 字符的独立随机运营密码；不要与客户凭据共享 |
| `YIKE_OPS_PHONE_ENCRYPTION_KEY` | 32 随机字节的 64 位十六进制编码；仅运营持有，独立安全备份 |
| `YIKE_PILOT_PHONE_AUTH_SECRET` | 至少 32 字节；与客户短信认证组件相同，用于号码与试用码 HMAC |

运营进程不能携带 `YIKE_PILOT_DATABASE_URL` 或 `YIKE_PILOT_ADMIN_DATABASE_URL`。客户服务不能携带运营数据库连接、运营密码或手机号解密密钥；代码会拒绝这些混用。密钥变更须迁移数据，不可随意重生成，否则号码绑定/试用码/解密失效。

本机或同主机反向代理方式（示例只信任 loopback 代理）：

```sh
.venv/bin/python -m uvicorn pilot.ops_web:configured_app --factory \
  --host 127.0.0.1 --port 8788 --workers 1 --no-access-log \
  --proxy-headers --forwarded-allow-ips 127.0.0.1
```

只将 `/ops` 及其子路径反向代理到该独立进程，保留真实 `Host` 并设置可信 `X-Forwarded-Proto: https`，关闭代理层访问/请求体日志和缓存，限制请求体 8KB；上游不得对公网直出。Docker 也可复用既有服务镜像覆盖启动命令，但网络/代理信任地址需按实际拓扑限制，不能填 `*`。

后台使用独立 HttpOnly/Secure/SameSite cookie（2 小时）、持久会话退出失效、固定 Origin 与 CSRF；单进程登录最多 10 次/5 分钟，部署一个 worker 并在反向代理增加持久限流/IP准入。平台运营人员拥有全局客户目录查看权，不给普通客户共享后台；不含多管理员权限分级和客户内容浏览。

## 短信通道与验收边界

现有 `SmsSender.send_code(phone,code)->bool` 协议保留。正式启动没有短信供应商时 `/api/ui/auth/sms-*` 返回 501，不假装发送。

选定供应商后，在受信部署组合中调用 `build_runtime_app(database, auth_secret=..., sms_sender=provider)`，同时配置 `YIKE_PILOT_PHONE_AUTH_SECRET`；不要从 HTTP 请求动态导入适配器、传入供应商 URL 或密钥。适配器须有有界超时、不盲目重发未知结果，只对供应商明确接收返回 True；False/异常分别保持 REJECTED/UNKNOWN。

本批不选择/购买短信供应商，不伪造真实收码，也没有手机号后四位登录或自动降级。真实收码、签名模板、生产配置、反向代理和客户验收仍须在授权部署时完成。

数据库中的完整手机号采用 SecretBox 加密，只有运营角色能读取密文、只有运营进程持有解密密钥。普通客户接口不返回手机号/试用码；运营列表不支持批量导出。页面内容始终转义、禁止缓存，历史用户手机号不可从 hash 反推。

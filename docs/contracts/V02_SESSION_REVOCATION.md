# V02-01B：服务端会话撤销

`120b938` 代码候选已获本地独立复审 PASS，详见[审核记录](../qa/V02-01B_REVIEW.md)；尚未合并 main，实际 CodexWin 交叉验证仍待完成。V02-01A 的 `da2a2f2` PASS 与本子项分开记录。

## 行为契约

- 所有客户 JSON、HTML 和开发登录桥接使用 `authenticate_session`：先验证 HMAC/到期时间，再查真实用户及 PostgreSQL 撤销记录。没有内存或纯签名 fallback；存储失败不授权。
- 新凭据带密码学随机 jti，同一用户同一秒签发的凭据彼此独立。旧的 `sub/exp` 签名格式可过渡，仍受撤销检查；两个字节完全相同的旧凭据无法区分，视为同一凭据。
- `DELETE /api/ui/session` 保留 HTTPS/Origin 防护。分别验证请求中的 Bearer、`pilot_session` Cookie；对所有有效凭据在一个事务内撤销，再返回 `authenticated:false` 并清除 Cookie。一个无效、过期或已撤销凭据不能遮蔽另一个有效凭据。
- 同一退出请求可能有不同客户的两个有效凭据，分别解析用户/租户，不复用第一个凭据的归属。重复退出幂等，不撤销该用户其他独立凭据。
- 退出事务失败返回通用服务错误，不返回注销成功、不泄漏底层错误。桌面仍可清除本机凭据，但此时必须区分“已离开本机空间”与“服务端撤销已确认”；现有客户端已有该提示。
- 撤销后不能访问客户页面/API，也不能经 `POST /session`、`POST /api/ui/session` 或开发桥接重新换 Cookie；服务重建后仍生效。

## 数据与部署

- 管理员发布作业先执行既有 `yike-pilot-migrate`，再对既有应用角色执行 `deploy/grant_session_revocations.sql` 的最小授权，之后才加载新版应用。仅迁移不代表应用可访问新表；精确命令见[运行手册](../CUSTOMER_PILOT_RUNBOOK.md)。新增迁移为 `105_v02_session_revocation.sql`，不修改已合并的历史迁移；Web 不获迁移权限。
- 该授权脚本只为新撤销表授予 SELECT/INSERT，不创建角色、不全表授权、不更改其他表权限。应用仍只需对 pilot_users 的既有 SELECT，不因普通鉴权获得用户表 UPDATE。脚本必须在受信管理员连接执行，检查目标存在且不是超级用户、BYPASSRLS、CREATEROLE 或该表 owner。
- 表仅保存 `tenant_id/user_id`、`SHA256(已经验签的原始payload段)`、到期和撤销时间。摘要不是完整 token、Cookie、明文 jti 或可登录凭据；不新增凭据导出接口。
- RLS 同时限制 tenant_id/user_id，只有 SELECT/INSERT policy，不允许应用更新或删除撤销记录。复合 FK 使存在撤销记录的用户不能修改 tenant_id 而隐藏历史撤销。当前无用户换租户功能，也没有撤销记录清理任务。
- PostgreSQL/服务器不可用时不返回登录成功；重试不能删除或解除既有撤销。未来清理任务只能删除真正过期且不再可接受的凭据记录，不按固定保存天数提前删除。

## 明确未实现

这不是短信发送/验证码验证、客户激活、设备密钥绑定、平台登录或设备离线完成；`sms_login` 和 `platform_connections` 仍为 false。长期刷新、管理员全端退出及凭据轮换也是独立工作，不能从当前 DELETE 接口推导存在。

撤销提交完成后新鉴权拒绝；此前已经鉴权的在途请求可能完成。后台任务授权、设备撤销及连接更换必须由执行器在提交结果时另外验证代次和授权版本，本子项不冒充任务取消机制。

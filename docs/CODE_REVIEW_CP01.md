# CP-01 / CP-02 代码复审记录

审查者：未参与实现的独立代码审核 Agent；三轮只读复审，绑定本分支 CP-01/CP-02 增量。

## 结果

实现级阻断已关闭：客户路径使用 `user_id -> tenant_id` 服务端解析；画像版本默认 `DRAFT`，显式确认后才允许导入；画像版本保存锁定 profile 行；来源和机会导入使用租户内唯一键及 `ON CONFLICT`；迁移使用事务级 advisory lock 和 checksum。

## 证据门禁

复审要求真实 PostgreSQL 空库、非超级用户 RLS、迁移重复执行、两个租户隔离、画像确认和并发导入证据。当前已用一次性本地 PostgreSQL 容器执行上述主路径测试；生产部署、HTTP/customer 路由未暴露 provisioning 方法、备份恢复和手机验收仍未完成，不能据此宣称上线。

## 保留限制

`provision_tenant` 与 `provision_user` 只供受信管理工具使用，后续 Web 路由必须不暴露。该初审段落记录的是当时基线；后续提交已实现来源 content version/observation、四页 UI、人工复核研究包导入和任务租约，详见 `docs/CUSTOMER_PILOT_PLAN.md` 与最新质量复核。真实平台研究和生产部署仍未由本报告证明。

复审绑定：代码安全边界与状态闭环已在 `8632b25c274644f50656fb7f7b7e45f2ff6b7701`、`eae701e078f584301b37d6b7b168e778c66fd783` 及后续健康检查提交上复核；本报告不替代目标环境的 RLS/网络 ACL 验收。

## 第四轮安全修复

质量验收发现数据库会话变量可被直连客户端伪造。客户 Web 路径现改用服务端 HMAC 短期令牌（`pilot/auth.py`），不再接受裸 `X-Pilot-User`；数据库连接要求由私网应用角色持有，RLS 仅作为数据库内层防线。直连数据库不属于客户可访问面，生产部署仍需验证网络 ACL、角色权限和密钥轮换。

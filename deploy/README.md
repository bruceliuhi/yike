# 意客 AI 应用镜像

这是应用容器骨架，不是生产上线证明。目标环境仍须单独提供私网 PostgreSQL、反向代理 HTTPS、日志脱敏、备份恢复和回滚记录。应用已关闭 Uvicorn 原始访问日志，并仅记录不含查询参数的 method/path/status。先由受信发布作业运行 `uv run --frozen yike-pilot-migrate`，再以非 owner 应用角色启动 `yike-pilot-web`；Web 进程不会执行迁移。

## 构建与运行

在仓库根目录执行：

```bash
docker build -f deploy/Dockerfile -t yike-customer-pilot:<git-sha> .
docker run --rm -p 8787:8787 \
  -e YIKE_PILOT_DATABASE_URL='postgresql://<non-superuser>:<password>@<private-db>:5432/<database>' \
  -e YIKE_PILOT_AUTH_SECRET='<secret-from-secret-manager>' \
  yike-customer-pilot:<git-sha>
```

容器不启用 `YIKE_PILOT_DEV_LOGIN`。真实用户通过 HTTPS `/session` 粘贴短期令牌换取 HttpOnly 会话 Cookie；应用不信任客户端自带的 `X-Forwarded-Proto`，反向代理必须在受信边界内覆盖并由 Uvicorn 正确解析 scheme，同时禁止应用端口公网直连。反向代理应将 `/healthz` 用作存活检查、`/readyz` 用作 PostgreSQL 就绪检查，并只通过 HTTPS 暴露用户页面。

TLS 在反向代理终止时，显式设置 `YIKE_PILOT_PROXY_HEADERS=1` 和反代实际来源的精确 `YIKE_PILOT_FORWARDED_ALLOW_IPS`（禁止 `*`）；不满足时保持代理头信任关闭。

## 生产门禁

- 启动前在目标环境运行 `scripts/cp06_validate_env.sh`；它只输出通过/失败，不打印数据库 URL、认证密钥或备份口令。该门禁会拒绝非 PostgreSQL、弱认证密钥、开发登录桥接、通配反代 allowlist 及不安全备份口令文件。
- 应用数据库账号必须是非超级用户、非 owner，只授予必要表权限；数据库不对公网开放。
- `YIKE_PILOT_AUTH_SECRET` 只能来自密钥管理，不写入镜像、仓库或日志。
- 反向代理必须关闭 query token 的访问日志，生产禁用 `__dev/session`。
- 使用仓库外、非空且仅所有者可读的 `YIKE_PILOT_BACKUP_PASSPHRASE_FILE` 完成加密 `pg_dump`、隔离恢复和旧镜像回滚演练后，才能记录 CP-06 放行；备份文件应使用 `.dump.enc` 扩展名，并保留脚本生成的 `.dump.enc.mac` HMAC-SHA256 侧车文件。恢复会先验证 MAC，再解密和执行 `pg_restore`。

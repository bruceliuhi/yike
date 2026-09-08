# 意客 AI 应用镜像

这是应用容器骨架，不是生产上线证明。目标环境仍须单独提供私网 PostgreSQL、反向代理 HTTPS、日志脱敏、备份恢复和回滚记录。应用已关闭 Uvicorn 原始访问日志，并仅记录不含查询参数的 method/path/status。

## 构建与运行

在仓库根目录执行：

```bash
docker build -f deploy/Dockerfile -t yike-customer-pilot:<git-sha> .
docker run --rm -p 8787:8787 \
  -e YIKE_PILOT_DATABASE_URL='postgresql://<non-superuser>:<password>@<private-db>:5432/<database>' \
  -e YIKE_PILOT_AUTH_SECRET='<secret-from-secret-manager>' \
  yike-customer-pilot:<git-sha>
```

容器不启用 `YIKE_PILOT_DEV_LOGIN`。反向代理应将 `/healthz` 用作存活检查、`/readyz` 用作 PostgreSQL 就绪检查，并只通过 HTTPS 暴露用户页面。

## 生产门禁

- 应用数据库账号必须是非超级用户、非 owner，只授予必要表权限；数据库不对公网开放。
- `YIKE_PILOT_AUTH_SECRET` 只能来自密钥管理，不写入镜像、仓库或日志。
- 反向代理必须关闭 query token 的访问日志，生产禁用 `__dev/session`。
- 完成加密 `pg_dump`、隔离恢复和旧镜像回滚演练后，才能记录 CP-06 放行。

# 意客 AI 应用镜像

本文件是现有 `pilot/` 服务端的部署子手册。当前开发目标与进度见 [V0.2 实施任务书](../docs/V02_IMPLEMENTATION_TASKBOOK.md)；缺少生产环境只影响相应部署验收，不阻止其他研发。下面的 Linux Web 镜像不是 Windows 客户端或平台采集执行器，不得把管理员连接、应用数据库连接或服务端签名密钥打入桌面安装包。

这是应用容器骨架，不是生产上线证明。目标环境仍须单独提供私网 PostgreSQL、反向代理 HTTPS、日志脱敏、备份恢复和回滚记录。应用已关闭 Uvicorn 原始访问日志，并仅记录不含查询参数的 method/path/status。先由受信发布作业运行 `uv run --frozen yike-pilot-migrate`，再以非 owner 应用角色启动 `yike-pilot-web`；Web 进程不会执行迁移。

V02-01A/104 与 V02-01B/105 升级必须严格按“迁移→显式最小授权→新版应用启动”执行。受信发布作业对既有应用角色运行 [grant_session_revocations.sql](grant_session_revocations.sql)：设备和连接表仅 SELECT/INSERT/UPDATE，事件表仅 SELECT/INSERT，会话撤销表仅 SELECT/INSERT。文件名为兼容既有 105 发布流程保留；脚本可重复执行，不依赖全表或默认授权。执行命令、角色选择和管理员运行环境隔离见[客户试用运行手册](../docs/CUSTOMER_PILOT_RUNBOOK.md)。仅数据库连通不证明新表权限已配置。

## 构建与运行

在仓库根目录执行：

```bash
docker build --build-arg VCS_REF="$(git rev-parse HEAD)" -f deploy/Dockerfile -t yike-customer-pilot:<git-sha> .
docker run --rm -p 127.0.0.1:8787:8787 \
  -e YIKE_PILOT_DATABASE_URL='postgresql://<non-superuser>:<password>@<private-db>:5432/<database>' \
  -e YIKE_PILOT_AUTH_SECRET='<secret-from-secret-manager>' \
  yike-customer-pilot:<git-sha>
```

目标主机也可使用受限 Compose 编排：`compose.pilot.yml` 只将应用绑定到 `127.0.0.1`，使用外部 env 文件、只读根文件系统、临时缓存、丢弃全部 Linux capabilities 并启用 `no-new-privileges`。镜像在构建阶段安装依赖，生产 CMD 直接执行已安装的 Web 入口，避免只读文件系统下运行时同步依赖。它不创建 PostgreSQL、不配置公网端口；启动前先运行 `scripts/cp06_validate_env.sh`，再由 HTTPS 反向代理转发到本机端口。

```bash
export YIKE_PILOT_IMAGE='registry.example.com/yike/customer-pilot@sha256:<64-hex-digest>'
export YIKE_PILOT_ENV_FILE='/secure/secret-store/yike-pilot.env'
set -a; . "$YIKE_PILOT_ENV_FILE"; set +a
scripts/cp06_validate_env.sh
docker compose -f deploy/compose.pilot.yml up -d
```

`YIKE_PILOT_IMAGE` 必须替换为已记录 digest 的实际镜像；`YIKE_PILOT_ENV_FILE` 必须位于 Git 仓库之外，不能提交或打印。
运行时 env 文件只允许包含应用连接和运行时密钥，禁止放入 `YIKE_PILOT_ADMIN_DATABASE_URL`；迁移、provision 和研究包导入使用独立的管理员终端/文件。

容器不启用 `YIKE_PILOT_DEV_LOGIN`。真实用户通过 HTTPS `/session` 粘贴短期令牌换取 HttpOnly 会话 Cookie；应用不信任客户端自带的 `X-Forwarded-Proto`，反向代理必须在受信边界内覆盖并由 Uvicorn 正确解析 scheme，同时禁止应用端口公网直连。反向代理应将 `/healthz` 用作存活检查、`/readyz` 用作 PostgreSQL 就绪检查，并只通过 HTTPS 暴露用户页面。

TLS 在反向代理终止时，显式设置 `YIKE_PILOT_PROXY_HEADERS=1` 和反代实际来源的精确 `YIKE_PILOT_FORWARDED_ALLOW_IPS`（禁止 `*`）；不满足时保持代理头信任关闭。

## 生产门禁

- 启动前在目标环境运行 `scripts/cp06_validate_env.sh`；它只输出通过/失败，不打印数据库 URL、认证密钥或备份口令。该门禁会拒绝非 PostgreSQL、弱认证密钥、开发登录桥接、通配或 `/0` 反代 allowlist、不安全 env 文件及不安全备份口令文件。
- 应用数据库账号必须是非超级用户、非 owner，只授予必要表权限；数据库不对公网开放。
- `YIKE_PILOT_AUTH_SECRET` 只能来自密钥管理，不写入镜像、仓库或日志。
- 反向代理必须关闭 query token 的访问日志，生产禁用 `__dev/session`。
- 使用仓库外、非空且仅所有者可读的 `YIKE_PILOT_BACKUP_PASSPHRASE_FILE` 完成加密 `pg_dump`、隔离恢复和旧镜像回滚演练后，才能记录 CP-06 放行；备份文件应使用 `.dump.enc` 扩展名，并保留脚本生成的 `.dump.enc.mac` HMAC-SHA256 侧车文件。恢复会先验证 MAC，再解密和执行 `pg_restore`。

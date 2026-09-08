# CP-01 / CP-02 当前运行证据

环境：独立临时容器 `yike-cp-final3-pg`，PostgreSQL 16 Alpine，端口 55531；不使用现有其他产品容器。

命令：

```bash
YIKE_PILOT_DATABASE_URL='postgresql://pilot:pilot@127.0.0.1:55531/pilot' \
  uv run --frozen pytest -q \
  tests/test_pilot_contracts.py tests/test_pilot_web.py \
  tests/test_research_import.py tests/test_pilot_import_cli.py \
  tests/test_pilot_provision_cli.py
```

结果：CP-01/02/03 数据层、任务租约、四页 Web（含来源状态、更新时间和匹配摘要）、失败任务提示、研究导入（含 60 天新鲜度与 URL 凭据净化）、受信 provisioning、日志脱敏、迁移职责、HTTPS 会话入口、代理头信任边界、同源状态同步、画像空值/重复提交/确认轮换、并发确认、画像变更提示、输入长度限制、非法输入和未 provisioning 用户访问 fail-closed 测试通过；最新完整命令为 `37 passed in 2.29s`（含真实 PostgreSQL 集成测试；集成测试创建一次性非超级用户 `pilot_app`，验证 RLS 过滤与旧约束升级）。当前产品专用门禁可运行 `scripts/check_customer_pilot.sh`，要求显式提供隔离 PostgreSQL URL；旧 `scripts/check.sh` 的全仓 Discovery 测试不属于本分支验收。

另外执行：

```bash
uv run --frozen python -m compileall -q pilot tests
git diff --check
```

结果：两项命令均退出码 0。

另运行 `scripts/secret_scan.sh`，结果为 `secret-scan: clean`；该静态扫描不替代目标环境日志、备份和密钥管理验收。

备份脚本已改为 `.dump.enc` 加密格式，并生成同名 `.enc.mac` HMAC-SHA256 侧车文件；恢复在解密前验证 MAC，口令只从仓库外 `YIKE_PILOT_BACKUP_PASSPHRASE_FILE` 读取。脚本语法、错误参数、未确认恢复和篡改拒绝分支已验证。真实目标库的加密备份、隔离恢复和回滚演练仍未完成。

2026-09-09 尝试构建部署镜像：

```bash
docker build --progress=plain -f deploy/Dockerfile -t yike-customer-pilot:471d9c3 .
```

结果：构建停在 `ghcr.io/astral-sh/uv:0.8.15-python3.12-bookworm-slim` 元数据拉取，约 90 秒后人工取消（退出码 130）。因此当前没有可验证的本地镜像 SHA，不能把部署骨架或 Dockerfile 视为已构建/已上线。

2026-09-09 复核构建：再次运行同一 Dockerfile，30 秒内仍停在 GHCR 元数据拉取，未生成镜像 SHA；该问题当前可稳定复现为注册表可达性阻塞，未改用未验证基础镜像替代。

随后将 `deploy/Dockerfile` 的基础层切换为固定 digest 的 Docker Hub `python:3.12-slim-bookworm`，固定安装 `uv==0.8.15`，并以 UID 10001 的非 root 用户运行应用；在容器内独立执行 `uv sync --frozen --no-dev --no-install-project` 成功，依赖安装链路可行。当前 Docker Desktop BuildKit 仍在拉取该基础层元数据阶段阻塞，尚未得到完整镜像 SHA；因此这只是可行性验证，不是构建或上线证据。

2026-09-09 本地备份/恢复演练（非目标环境）：使用两个独立的 PostgreSQL 16 容器，源库先执行 `yike-pilot-migrate`；再用真实 `pg_dump` 与 OpenSSL 生成 `/secrets/pilot.dump.enc`，恢复脚本在另一容器设置 `CONFIRM_RESTORE=YES` 成功恢复，`psql` 查询确认 `pilot_schema_meta` 中存在 `customer-pilot-v1`。演练证明脚本链路可运行，但目标库、独立备份存储、认证完整性和回滚仍未验收。

范围边界：这只证明 CP-01/CP-02 的本地数据层契约，不证明四页浏览器流程、真实平台采集、部署 HTTPS、备份恢复、真实用户试用或收入。

代码备份：Gitee `codex/customer-pilot` 分支；当前部署相关提交为 `eff28d7`（固定 Python 基础层 digest）与 `bd27338f108652e9ec43bdb4ea24fdfe4935cc77`（非 root 运行与本证据更新），两者均已与远端 SHA 对齐。更早的部署验收模板及 HTTPS-only `/healthz`、`/readyz` 探针提交为 `006ac86188e366645b002d84ca274ddde33ed447`；探针对 HTTP、userinfo、query、fragment 输入均 fail-closed。浏览器主流程记录见 `docs/BROWSER_ACCEPTANCE_CP04.md`；该分支尚未部署。

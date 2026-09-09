# CP-01 / CP-02 当前运行证据

环境：独立临时容器 `yike-cp-final3-pg`，PostgreSQL 16 Alpine，端口 55531；不使用现有其他产品容器。

命令：

```bash
YIKE_PILOT_DATABASE_URL='postgresql://<non-superuser>:<password>@127.0.0.1:55531/pilot' \
  uv run --frozen pytest -q \
  tests/test_pilot_contracts.py tests/test_pilot_web.py \
  tests/test_research_import.py tests/test_pilot_import_cli.py \
  tests/test_pilot_provision_cli.py
```

结果：CP-01/02/03 数据层、任务租约、四页 Web（含来源状态、更新时间和匹配摘要）、失败任务提示、研究导入（含 60 天新鲜度与 URL 凭据净化）、受信 provisioning、日志脱敏、迁移职责、HTTPS 会话入口、代理头信任边界、同源状态同步、画像空值/重复提交/确认轮换、并发确认、画像变更提示、输入长度限制、非法输入和未 provisioning 用户访问 fail-closed 测试通过；最新完整命令为 `39 passed in 3.11s`（含真实 PostgreSQL 集成测试；集成测试创建一次性非超级用户 `pilot_app`，验证 RLS 过滤与旧约束升级）。当前产品专用门禁可运行 `scripts/check_customer_pilot.sh`，要求显式提供隔离 PostgreSQL URL；旧 `scripts/check.sh` 的全仓 Discovery 测试不属于本分支验收。

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

2026-09-09 再次使用 Docker Desktop `desktop-linux` builder、`--load` 和固定基础层 digest 尝试完整构建；30 秒仍停在 `load metadata for docker.io/library/python:3.12-slim-bookworm@sha256:d50fb...`，随后人工取消（退出码 130）。仍无镜像 SHA，CP-06 镜像构建保持未完成。

随后发现原忽略文件位于 `deploy/.dockerignore`，与仓库根构建上下文不匹配；已改为根 `.dockerignore`，排除 `.env*`、运行目录、登录态、测试和文档。使用隔离 `DOCKER_CONFIG`、本地 Docker socket 和旧版 builder 完整构建成功，构建上下文 1.041MB；随后按 pilot-only 范围移除旧 `app` 包和运行时依赖同步，并加入 OCI 源码/提交标签。以代码提交 `25e950ebe5091c4c5272557d8bfefb17a98fa215` 构建的本地镜像 ID 为 `sha256:ee7459b3adcb84799e631d75440f466e8b8e9dc2063f9c6bd21b733ccf586d2f`，配置显示 `User=yike`、CMD 为 `/app/.venv/bin/python -c "from pilot.cli import web; web()"`，镜像标签记录该提交和 Gitee 源码地址；之后的 `587e8d2` 仅更新证据文档。在临时 PostgreSQL、只读根文件系统、`cap_drop=ALL`、`no-new-privileges` 下迁移空库并运行，`/healthz` 和 `/readyz` 均返回预期 JSON。该镜像 ID 是本机临时构建证据，不是已推送到生产仓库的镜像 digest，也不替代目标环境验收。

2026-09-09 本地备份/恢复演练（非目标环境）：使用两个独立的 PostgreSQL 16 容器，源库先执行 `yike-pilot-migrate`；再用真实 `pg_dump` 与 OpenSSL 生成 `/secrets/pilot.dump.enc`，恢复脚本在另一容器设置 `CONFIRM_RESTORE=YES` 成功恢复，`psql` 查询确认 `pilot_schema_meta` 中存在 `customer-pilot-v1`。演练证明脚本链路可运行，但目标库、独立备份存储、认证完整性和回滚仍未验收。

2026-09-09 最新代码状态 `7471fd0db627d3b0a295108b82e30f66dc598c4b`：重建 pilot-only 镜像，镜像 ID 为 `sha256:b0916befd750209149bbefb60b9f4ccf9a535a97b996ca9150cd6ff14742252e`，OCI revision 与该提交一致；在一次性 PostgreSQL、只读根文件系统、`cap_drop=ALL`、`no-new-privileges` 下执行 v1/v2 迁移并启动，`/healthz`、`/readyz` 均返回预期 JSON。该镜像仍是本机临时构建，不是生产仓库镜像或上线证明。

2026-09-09 代码提交 `3642587bb284a353ffd4d3b4ba73823a7bcd2689` 补充画像确认到研究任务的关联；重建镜像 ID 为 `sha256:7f3c6a5360410b66c13eb04f2fe642d5ff0931dfa87ac9754fe2c1f829852550`，OCI revision 与该提交一致。完整 PostgreSQL 回归为 `40 passed`，本地空库受限启动验证保持通过。

2026-09-09 当前分支 `fca816f0401cc9f4a8d65bde91c7bef17233f810` 的镜像复核：镜像 ID `sha256:22cace8671c225893804da0766f76917223dff24fd4169b91da636bb2ffa5a4b`，OCI revision 与该提交一致；镜像构建上下文排除旧 `app`，运行配置仍为非 root、只读根文件系统和 `cap_drop=ALL`。

范围边界：这只证明 CP-01/CP-02 的本地数据层契约，不证明四页浏览器流程、真实平台采集、部署 HTTPS、备份恢复、真实用户试用或收入。

代码备份：Gitee `codex/customer-pilot` 分支；历史镜像与集成证据按各段落注明对应提交，当前远端 HEAD 需以实时 `git ls-remote` 结果为准；UI 与安全头增量证据记录在 `docs/QUALITY_REVIEW_CP05.md`。`7471fd0` 收紧证据导入与重复机会边界，`3642587` 关联画像确认与研究任务，`dfa39ce` 校验生产 env 文件权限，`fca816f` 更新部署门禁文档，`a176dba` 接入客户试用页样式，`d961d4b` 补齐异常响应安全头；镜像构建使用对应代码提交并带 OCI provenance 标签，同时要求 CP-06 preflight 使用 digest 固定的镜像引用。相关部署提交包括 `eff28d7`（固定 Python 基础层 digest）、`bd27338f108652e9ec43bdb4ea24fdfe4935cc77`（非 root 运行）、`82ce5c0b284dfab5eeca5ef0999618427855a60f`（备份 HMAC 完整性）、`671964f`（CP-06 生产配置 preflight）、`6f61c98`（受限 Compose 运行文件）、`973d355`（根构建上下文及只读运行修复）与 `e47d474`（扩展敏感文件排除、loopback 示例）。产品门禁现包含备份篡改拒绝测试、digest 镜像 preflight 和部署契约单元测试。更早的部署验收模板及 HTTPS-only `/healthz`、`/readyz` 探针提交为 `006ac86188e366645b002d84ca274ddde33ed447`；探针对 HTTP、userinfo、query、fragment 输入均 fail-closed。浏览器主流程记录见 `docs/BROWSER_ACCEPTANCE_CP04.md`；该分支尚未部署。

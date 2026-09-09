# CP-05 独立质量验收记录

审查者：未参与实现的独立质量验收 Agent。实现者未参与本次结论形成。

## 结论

- 本地质量门禁：`PASS`
- CP-01～CP-04：本地证据通过
- CP-05 真实来源验证：`RULES_PASS_REAL_SAMPLING_INCOMPLETE`
- CP-06 目标环境部署：`NOT_STARTED`
- 整体上线判定：`FAIL（部署前阻断项仍存在）`

## 复核证据

独立验收在隔离 PostgreSQL 16 临时容器中执行 customer-pilot 门禁，结果为 `40 passed`；定向套件（部署契约、CP-06 preflight、备份、pilot 数据/Web、研究导入/CLI/provision）为 `48 passed, 2 skipped`。空库迁移、provisioning、短期令牌、Uvicorn 本地启动及四个客户页面探测通过：`/healthz`、`/readyz`、`/profile`、`/opportunities` 均返回预期结果，空机会池显示“今日暂无经复核机会”。`compileall`、Shell 脚本 `bash -n`、`git diff --check` 和敏感信息扫描均通过。

说明：仓库根目录的旧 Discovery 测试仍绑定历史 AUTHORITY SHA，不属于当前 customer-pilot 验收范围；本结论只采用 customer-pilot 专用门禁及定向套件，不将旧 gate 的失败误报为本产品回归。

该结论覆盖远端分支 `codex/customer-pilot` 的当前实现；原始质量快照对应 `fca816f0401cc9f4a8d65bde91c7bef17233f810`，随后 UI 与安全头增量已由本记录追加复核，当前远端分支以最新 Gitee SHA 为准。历史本地 pilot-only 镜像为 `sha256:22cace8671c225893804da0766f76917223dff24fd4169b91da636bb2ffa5a4b`，带对应旧提交 OCI revision；本轮未重建镜像。所有结果均不替代目标环境验收。

## 阻断与边界

1. CP-05 真实来源研究仍不足：当前研究规则通过，但缺少足够的当期买方样本与服务商有用/跟进/付款反馈，不能宣称持续供给或商业成立。
2. CP-06 尚未开始：缺少目标服务器、域名/HTTPS、生产 ACL、可验证镜像 SHA、生产日志抽查、目标库备份恢复、回滚和真实手机验收。
3. 目标生产 Registry、HTTPS 和部署验收仍未提供；本地镜像构建与受限 smoke 不等于已部署生产。

未关闭的部署阻断项不得降级为“上线可用”。

## 2026-09-09 UI 增量复审记录

提交 `a176dba` 将客户试用页统一接入本地静态样式，并把 `static/` 纳入生产镜像；新增页面契约覆盖样式路由、viewport 与移动端布局规则。针对 Web、部署契约、研究导入和 CP-06 preflight 的非集成定向套件结果为 `37 passed`；`compileall`、`bash -n`、`git diff --check` 与敏感信息扫描均通过。

本机浏览器 390×844 窄视口检查记录在 `docs/BROWSER_ACCEPTANCE_CP04.md`：页面无横向溢出，主按钮约 45px。该证据仍不等于真实手机验收；本轮 Docker Desktop 不可用，未新增受限容器 smoke，既有受限镜像证据仍只适用于其对应提交。

独立代码复审针对 `a176dba` 运行 `tests/test_pilot_web.py tests/test_deploy_contracts.py tests/test_pilot_contracts.py`，结果为 `24 passed, 2 skipped`；静态资源路径穿越、`.env` 和目录索引探测均为 404，未发现 P0/P1/P2。静态目录保持仅放 CSS/JS 的约束，不能放入敏感文件。

安全头修复提交 `d961d4b` 经独立复审：定向测试 `23 passed`；正常 200、401、400、404、503 以及 `raise_server_exceptions=False` 的 500 均包含五个基线安全头，`raise_server_exceptions=True` 仍保留原异常语义，未发现 P0/P1。当前分支最新提交以远端实际 SHA 为准。

提交 `eccb449` 关闭公网 `/docs`、`/redoc` 和 `/openapi.json`，并记录当期展台研究结果；定向回归为 `42 passed`，敏感信息扫描通过。独立安全复审对该提交确认文档路由为 404、CSP 含 `object-src/frame-src 'none'`、HTML `Cache-Control: no-store`，未发现 P0/P1。

## 2026-09-09 最新安全与管理员边界复审

提交 `cfb2f01`（远端分支 `codex/customer-pilot`）新增 v3 租户目录 RLS、显式 `YIKE_PILOT_ADMIN_DATABASE_URL` 管理员连接、provisioning 的新租户 GUC 绑定，以及运行时 env 文件禁止携带管理员数据库 URL。独立安全复审确认当前定向门禁为 `55 passed, 2 skipped`，`secret_scan`、`compileall`、Shell 语法和 `git diff --check` 均通过，未发现新的 P0/P1。

完整 `scripts/check_customer_pilot.sh` 在本机未启动 PostgreSQL 时为 `44 passed, 2 failed`；失败仅为两项真实 PostgreSQL integration（连接 `127.0.0.1:5432` 被拒），因此 v3 的真实空库迁移、RLS 和并发确认仍未验收。该结果不替代 CP-06 目标环境证据，CP-06 继续保持 `NOT_STARTED`。

## 2026-09-09 Origin 防护复审

提交 `763cc29` 对状态变更请求增加同源 `Origin` 校验，并将畸形 Origin 解析失败改为明确 `403`。独立安全复审确认跨源请求被拒绝、同源请求（含末尾斜杠）正常、无 Origin 的受信路径仍可用；定向套件为 `58 passed, 2 skipped`，未发现 P0/P1/P2。

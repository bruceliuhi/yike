# 101.200.137.138 部署与功能验收计划

> **For agentic workers:** REQUIRED: Use `subagent-driven-development` for independent local verification; root alone operates the remote host. Steps use checkbox syntax. User explicitly requested latest Gitee code, deployment on this server, and full functional testing.

**Goal:** 部署固定 Gitee main 源码的意客服务，完成可执行功能检查并如实交付失败与外部前置条件，不影响本机其它业务。
**Architecture:** 源码固定 `c41155b09ba8955453e8782aa4095349b13bcd8d`；远端独立 `/opt/yike-ai2026`、专用容器/网络/数据库及仓库外秘密文件。应用仅绑定 loopback，用户确认的公开 HTTPS 域名为 `yike.xingheai.net`，DNS生效后才接反代。禁止使用其它项目数据库或模型凭据。
**Tech Stack:** 仓库既有 Dockerfile/Compose、PostgreSQL 16、Nginx、Python/pytest、Node24/Vitest、Windows 客户端。

**执行状态（2026-09-11）：** 过程中接收主干来件，最终固定并实际运行 `68324820d859221a8ef625e18f6ff3fa1dcc09d6`。服务器内网部署、30项冒烟（含HTTP及管理员合成导入）与62表备份恢复校验通过；公网DNS/HTTPS、模型、真实平台与新Windows候选仍缺。全量失败与差量版本边界集中见[唯一交付记录](../../qa/SERVER_137138_DEPLOYMENT.md)，下面未勾选项不代表已验。

## Chunk 1: 同步、部署及可重复验收

### Task 1: 固定版本与只读盘点

- [x] 干净 main 从 Gitee 快进到上述 SHA，记录远端对应版本。
- [x] 通过本机已存在且与目标 IP 对应的专用 SSH identity 登录；不复制/打印私钥，不改服务器认证。
- [x] 核对现有容器、监听端口、系统及容量。Ubuntu24.04/x64，已有多个生产业务；不重启共享 Docker/Nginx，不改既有公网 PostgreSQL。

### Task 2: 隔离构建与数据库准备

Files: reuse `deploy/Dockerfile`, `deploy/compose.pilot.yml`, `deploy/grant_*.sql`, `pilot/db.py`; deployment artifacts and secrets outside Git.

- [x] 确认 `/opt/yike-ai2026` 与所选容器/网络/loopback 端口未被占用；新建独占发布目录，传输固定 SHA 的必要跟踪源码并核对归档摘要。
- [x] 构建并记录镜像 ID/digest，不升级依赖锁。专用 PG 网络与数据目录不发布公网端口，设内存/CPU上限；数据库管理员、运行角色、认证及备份秘密分别新生成到600文件，不打印。
- [x] 先完成全部注册迁移、初始最小角色授权及各增量授权；检查应用角色非owner/非superuser/non-bypass-RLS、业务表权限和重复迁移幂等。数据库测试只在另一个专用测试库执行，不能指向运行库。
- [x] 启动前从实际600 runtime env加载配置，通过 `scripts/cp06_validate_env.sh`，确保无管理员连接，并使用可由Docker解析的真实manifest digest镜像引用；若使用本机专用registry，只监听loopback，不开放公网。随后启动 loopback 应用，检查 healthz/readyz、真实运行版本、未认证拒绝、关闭开发入口/文档和脱敏日志。模型凭据未给出时如实保持模型能力不可用；不借其它业务密钥启用。

### Task 3: HTTPS 与发布

Files: isolated new server vhost only; reuse `scripts/cp06_validate_env.sh`, `docs/CUSTOMER_PILOT_RUNBOOK.md`.

- [ ] DNS生效后，核对证书/反代实际来源，独立vhost只转发意客loopback；覆盖 `X-Forwarded-Proto`、精确设置 `YIKE_PILOT_FORWARDED_ALLOW_IPS`、禁用query-token日志，验证HTTPS会话Cookie与认证。先校验配置再reload，不覆盖其他站点。缺DNS/证书时仅保留内网准备，不宣称公开部署成功。
- [ ] 执行部署门禁，记录镜像/源码、真实HTTPS健康与鉴权结果。保留旧配置和本次精确回滚指令；新建服务失败只停止意客服务，不做全局回滚。

### Task 4: 功能测试

Files: existing `tests/`, `desktop/tests/`, `desktop/package.json`; a single QA report below.

- [x] 本地 Node24 执行完整 `vitest run` 与 `tsc --noEmit`；后端完整 pytest 使用隔离测试库，列出passed/failed/skipped及前置条件，不掩盖Windows/Linux专属检查。执行完成不等于全绿，版本与剩余失败见唯一记录。
- [ ] 按已有页面/API实际核对登录、资料/画像、策略、任务、原文证据、判断、草稿、人工确认、防重、回复及跟进；记录哪些为合成自动化、真实部署HTTP、可见操作或尚缺模型/平台账号，不能相互替代。
- [ ] Windows候选须同SHA payload与客户端、绑定已可用HTTPS origin后只构包一次，再以同包验证真实服务连接和普通入口。若源runtime/域名/模型/账号前置未满足，记录未交付Windows候选及未完成全功能测试，不用Vitest或旧包替代。
- [ ] 外部模型请求需有意客专用配置和明确披露；真实平台登录/挑战由用户参与，发送需批准具体对象/内容/渠道。缺少这些条件时标明该功能未完成实测，不自动联系陌生人。
- [x] 新V2备份只对意客库执行，恢复仅用明确新建隔离库；保留文件，比较关键表数据及版本。没有旧运行版本时不冒称旧版本业务回滚演练完成。

### Task 5: 交付

Files: create `docs/qa/SERVER_137138_DEPLOYMENT.md`, minimally update current task/status pointers.

- [x] 非作者检查部署范围与最终证据，错误按影响修复/复测，不重复全量构包。最终纠正“30项全为HTTP”的口径，管理员导入单列。
- [x] 提交集中记录：入口/源码/镜像、测试结果、失败与未验项、后续所需用户输入。未完成真实客户/平台验收不标产品上线或完整Goal完成。

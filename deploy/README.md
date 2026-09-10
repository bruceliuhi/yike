# 意客 AI 应用镜像

监控计划基础（迁移126）：迁移后以受信发布作业设置既有 `yike.app_role` 并执行 [监控计划授权](grant_monitor_plans.sql)，另需原画像/策略/会话权限。普通runtime仅保存计划、暂停/恢复和历史回执，不启动采集；`ACTIVE + NOT_CONNECTED` 不能作为监控已运行。尚无周期执行器/新客户端入口，本记录不是生产部署。[接口与证据](../docs/superpowers/plans/2026-09-11-monitor-plans.md)。

本文件是现有 `pilot/` 服务端的部署子手册。当前开发目标与进度见 [V0.2 实施任务书](../docs/V02_IMPLEMENTATION_TASKBOOK.md)；缺少生产环境只影响相应部署验收，不阻止其他研发。下面的 Linux Web 镜像不是 Windows 客户端或平台采集执行器，不得把管理员连接、应用数据库连接或服务端签名密钥打入桌面安装包。

这是应用容器骨架，不是生产上线证明。目标环境仍须单独提供私网 PostgreSQL、反向代理 HTTPS、日志脱敏、备份恢复和回滚记录。应用已关闭 Uvicorn 原始访问日志，并仅记录不含查询参数的 method/path/status。先由受信发布作业运行 `uv run --frozen yike-pilot-migrate`，再以非 owner 应用角色启动 `yike-pilot-web`；Web 进程不会执行迁移。

V02-01A/104 与 V02-01B/105 升级必须严格按“迁移→显式最小授权→新版应用启动”执行。受信发布作业对既有应用角色运行 [grant_session_revocations.sql](grant_session_revocations.sql)：设备和连接表仅 SELECT/INSERT/UPDATE，事件表仅 SELECT/INSERT，会话撤销表仅 SELECT/INSERT。文件名为兼容既有 105 发布流程保留；脚本可重复执行，不依赖全表或默认授权。执行命令、角色选择和管理员运行环境隔离见[客户试用运行手册](../docs/CUSTOMER_PILOT_RUNBOOK.md)。仅数据库连通不证明新表权限已配置。

正常 Web 入口现装配已确认策略、执行历史、候选入库和复核服务，使用同一个受限应用 DB；部署前还须按已接收迁移分别运行 [执行授权](grant_execution_runtime.sql)、[候选授权](grant_candidate_ingestion.sql)、[复核授权](grant_candidate_review.sql)、[策略授权](grant_research_strategies.sql)和[原文证据授权](grant_opportunity_evidence.sql)。普通启动不自动补权限，非空管理员 DB 环境变量将导致启动拒绝；该检查不验证应用 URL 的实际角色。

人工草稿服务已接普通 Web runtime：迁移121后，管理员须以同一 `yike.app_role` 运行 [草稿授权](grant_contact_drafts.sql)，只授新表SELECT/INSERT；读取机会/画像/来源及其锁权限沿用上述授权。原UUID查回执和最新草稿接口见[07B接线计划](../docs/superpowers/plans/2026-09-10-contact-draft-persistence.md)。保存不代表发送，当前outreach能力仍关闭；本说明不是生产部署验收。

人工确认队列接普通runtime：迁移122后，同一受限角色运行[队列授权](grant_outreach_queue.sql)，新表仅SELECT/INSERT及UPDATE(state)，触发器禁止改确认内容或重启已取消请求。API见[触达合同](../docs/contracts/V02_OUTREACH_CHANNELS.md#07b-人工确认队列2026-09-10)；无派发进程，不启用outreach能力，不代表真实发送/上线。

123增加单次领取/签名结果：迁移后**同时执行队列授权和[派发授权](grant_outreach_dispatch.sql)**，后者只给新事件表SELECT/INSERT，原队列查询/取消现在也需要这些读取权限；漏授权会拒绝请求，不能按旧122部署。`YIKE_PILOT_OUTREACH_PLATFORMS`默认为空（CLAIM拒绝），仅接受逗号分隔BILIBILI/DOUYIN/XIAOHONGSHU/ZHIHU，未知值启动拒绝。正式开启需对应客户端实际渠道核验、持久消费许可及真实平台验收；本批没有开启生产配置或全局outreach能力，也没有运行发送进程。接口与UNKNOWN恢复见[增量合同](../docs/contracts/V02_OUTREACH_CHANNELS.md#07b-单次领取与结果2026-09-10)。

如需候选 ASSESS，从仓库外服务器配置同时提供 `YIKE_PILOT_ASSESSMENT_BASE_URL`、`YIKE_PILOT_ASSESSMENT_API_KEY`、`YIKE_PILOT_ASSESSMENT_MODEL`；三项全无仍可启动，部分或非法配置明确失败。启动与只读接口不探测模型。完整配置规则见[正常装配契约](../docs/contracts/V02_NORMAL_RUNTIME_COMPOSITION.md)。真实来源 policy 未接通时 START 仍不可用，短信/建议/平台收发能力仍关闭，不把 Web 存活或数据库可连当作全链就绪。

124签名回复来源：先迁移再启动新版，复用[回复事件授权](grant_reply_events.sql)的表级SELECT/INSERT、旧117授权及上述设备/队列/领取读取权限，不另授UPDATE/DELETE。新增证明列不改旧payload哈希；签名入口/证据列表见[回复合同](../docs/contracts/V02_REPLY_FOLLOWUP.md#08-新发送来源接入2026-09-10)。普通runtime仅记录设备提交并验签的观察，不自动读取私人会话、不自动回复或标记平台已读；真实连接器和客户端另验。

该镜像不安装项目wheel，因此Dockerfile另将已有两份版本化分析规则显式复制到`pilot/_assessment_rules/`，与wheel约定相同；不能遗漏后依赖开发目录补读。发行布局回归不代表已完成实际Linux镜像运行，目标环境仍按下述生产门禁验收。

## 构建与运行

资料生命周期接线（迁移125）：先迁移，再以现有 `yike.app_role` 执行 [资料授权](grant_materials.sql)，最后启用新版 Web runtime。需要既有画像只读与会话授权；新历史表只授 SELECT/INSERT，影响 token 仅允许更新消费时间。没有迁移/授权时不得把读取失败解释为空资料。资料解析复用现有三项 `YIKE_PILOT_ASSESSMENT_*` 配置，不增加一组客户密钥；未配置则解析明确失败，仍可保存资料。提取20秒子进程上限，固定客户端解析请求25秒等待，取消不等于远端未执行，原 requestId 可核对回执。资料不会自动进入对外草稿；复制到本机画像草稿的文字不可远程召回。见[资料契约](../docs/UI_MATERIALS_CONTRACT.md)。本说明不是部署执行记录。

V02-01C 连接版本切片新增 migration 107：先运行受信迁移，再显式运行 [grant_connection_operations.sql](grant_connection_operations.sql)，最后启动新应用。它只授予不可变回执 SELECT/INSERT，不给 UPDATE/DELETE、用户 UPDATE 或 schema CREATE，并拒绝缺失/高权限/owner 目标。旧连接初始化版本 1 且状态和 vault 引用不变；注册仍 UNVERIFIED，回执不是当前执行授权。管理员命令见客户试用运行手册；重放和事务边界见[连接版本契约](../docs/contracts/V02_CONNECTION_VERSIONS.md)。107 和授权均可重复执行，不能替代 104–106 授权。

V02-01C 持钥切片新增 migration 106：迁移后、启应用前，另运行 [grant_device_credentials.sql](grant_device_credentials.sql)，在同一 psql 会话设置既有受限角色 `yike.app_role`（完整命令见客户试用运行手册）。脚本只授新凭据/挑战表 SELECT/INSERT/UPDATE，可重复，不给 DELETE、pilot_users UPDATE 或 schema CREATE；Web/桌面不携带管理员连接。它不替代 104/105 旧授权，也不代表执行租约或 Windows 验收完成。

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
- 使用仓库外、属当前用户且仅所有者可读的 `YIKE_PILOT_BACKUP_PASSPHRASE_FILE` 完成加密 `pg_dump`、隔离恢复和旧镜像回滚演练后，才能记录 CP-06 放行。当前脚本需Python 3.10+；密码文件第一行1–512字节、非空白、无NUL/CR，文件不超过64KiB。备份使用`.dump.enc`并保留新`YIKE-BACKUP-MAC-V2`认证侧车。MAC key从秘密内容经独立域PBKDF2派生，恢复先认证私有密文快照再解密同一快照。旧路径密钥MAC全部拒绝，不自动升级/重签旧备份，历史数据仍保留。细节与未完成真实恢复验收见[运行手册](../docs/CUSTOMER_PILOT_RUNBOOK.md#备份与恢复演练)。

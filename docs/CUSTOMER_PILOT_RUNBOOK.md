# 意客AI 现有客户试用运行手册

2026-09-11 首次安装补齐：新数据库完成全部迁移后，使用[完整授权入口](../deploy/README.md)执行 `deploy/grant_runtime.sql`，不只运行下文三个历史增量脚本。该入口补画像基础权限并统一加载所有增量；真实空库与画像 HTTP 验证见[记录](qa/EMPTY_DATABASE_DEPLOYMENT_20260911.md)。仅 readyz200 不代表业务权限齐备。

适用范围：当前已实现的 `pilot/` 客户试用路径，不是 V0.2 最终产品使用说明。当前路径不启动旧的 B 站/抖音 SQLite 采集器，研究包需管理员导入，联系与回复由用户手动登记。

当前开发目标见 [AUTHORITY](../AUTHORITY.md) 与 [V0.2 实施任务书](V02_IMPLEMENTATION_TASKBOOK.md)。正常登录、平台连接、多平台采集与监控、真实发送及回复必须按计划实现；本手册中描述“当前不自动发送”不构成取消这些功能的范围限制。开发人员不因 CP-06 缺生产环境而停止其他可独立工作。

本手册继续只给出已经实现的命令；新客户端不得复制管理员数据库凭据或调用下述管理员导包命令，须通过计划中的受认证候选与复核 API 接入。

## 本地启动

准备一个独立 PostgreSQL 数据库，并在当前 shell 临时设置变量（不要提交 `.env`）：

```bash
export YIKE_PILOT_ADMIN_DATABASE_URL='postgresql://<admin-user>:<password>@<private-host>:5432/<database>'
export YIKE_PILOT_DATABASE_URL='postgresql://<app-user>:<password>@<private-host>:5432/<database>'
export YIKE_PILOT_AUTH_SECRET='<random-secret-kept-outside-git>'
uv run --frozen yike-pilot-migrate   # 仅由受信管理员/发布作业执行一次
# 104/105升级：替换为既有应用角色，不使用管理员角色或 PUBLIC。
psql "$YIKE_PILOT_ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SET yike.app_role = 'YOUR_EXISTING_APP_ROLE'" -f deploy/grant_session_revocations.sql
# 106 升级：迁移后另行补齐设备持钥证明的新表权限。
psql "$YIKE_PILOT_ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SET yike.app_role = 'YOUR_EXISTING_APP_ROLE'" -f deploy/grant_device_credentials.sql
# 107 升级：迁移后显式授予不可变连接操作回执 SELECT/INSERT。
psql "$YIKE_PILOT_ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SET yike.app_role = 'YOUR_EXISTING_APP_ROLE'" -f deploy/grant_connection_operations.sql
uv sync --frozen --extra dev
env -u YIKE_PILOT_ADMIN_DATABASE_URL uv run --frozen yike-pilot-web
```

反向代理或容器编排可使用 `GET /healthz` 做进程存活检查、`GET /readyz` 做 PostgreSQL 就绪检查；二者不要求用户令牌，数据库不可用时 `/readyz` 返回 503。

缺少数据库 URL 或认证密钥时，启动必须失败；不会静默退回旧 SQLite 数据库。Web 进程本身不执行迁移，生产应用角色无需 CREATE/ALTER 权限；迁移必须由受信管理员或发布作业先执行。

上述 `psql` 是受信发布环境工具，命令从仓库根目录执行；示例占位角色必须替换为应用 URL 对应的真实既有角色。该兼容脚本一次补齐 104 设备/连接/事件表与 105 会话撤销表：设备、连接仅 SELECT/INSERT/UPDATE，事件仅 SELECT/INSERT，会话撤销仅 SELECT/INSERT；幂等可重跑，不代替初次应用角色配置。已有 schema USAGE、pilot_users SELECT 及任务表所需既有权限保持不变；不增加用户表 UPDATE、设备/连接 DELETE，事件 UPDATE/DELETE 或撤销表 UPDATE/DELETE。若没有这一步，鉴权或身份登记 API 按失败关闭返回错误，不能把 `/readyz` 的数据库连通当作新表权限已验收。生产运行 env 必须单独提供，不包含管理员 URL。

若由 HTTPS 反向代理终止 TLS，设置 `YIKE_PILOT_PROXY_HEADERS=1` 与 `YIKE_PILOT_FORWARDED_ALLOW_IPS=<反代实际来源IP或CIDR>`。后者必须是精确 allowlist，禁止设为 `*`；否则保持默认代理头信任关闭。

真实用户可通过 HTTPS 打开 `/session`，粘贴管理员经安全渠道提供的短期访问令牌换取 HttpOnly、SameSite=Strict 会话 Cookie。应用不信任客户端伪造的 `X-Forwarded-Proto`；反向代理必须覆盖该头并确保应用端口不公网直连。生产不得使用 `/__dev/session`，也不得把令牌放进 URL。

客户试用应用默认关闭 FastAPI 的 `/docs`、`/redoc` 和 `/openapi.json`，不向公网暴露内部路由描述；如需本地调试，应在隔离环境临时开启，不得作为生产配置。

使用受限 Compose 时，`YIKE_PILOT_ENV_FILE` 必须是仅含应用 URL、认证密钥及运行配置的独立文件，绝不能包含 `YIKE_PILOT_ADMIN_DATABASE_URL`；管理员 URL 只在迁移/provision/import 的管理员终端或独立 env 文件中使用。先从运行时文件加载变量，再运行 preflight，确保校验值与容器实际注入值一致：`set -a; . "$YIKE_PILOT_ENV_FILE"; set +a`。该文件只允许受信管理员读取，不能提交或打印。

## 受信 provisioning

106 设备持钥证明另需上述新授权脚本：仅新凭据/挑战表 SELECT、INSERT、UPDATE，不新增 DELETE、用户 UPDATE 或 schema CREATE；两表 FORCE RLS，运行角色不能是 owner/BYPASSRLS。历史设备 owner 保持 NULL，不自动归属第一个申请者。升级可重复运行；不删除旧迁移或证明记录。API 与重启/重试约定见[设备密钥契约](contracts/V02_DEVICE_KEYS.md)。这不是 Windows 私钥保存、执行租约或平台连接验收。

107 连接版本升级保持旧连接状态、账号、vault 引用，初始化版本 1。迁移后、启新应用前运行 grant_connection_operations.sql，仅新增回执 SELECT/INSERT，无 UPDATE/DELETE、用户 UPDATE 或 schema CREATE；回执 tenant+user FORCE RLS。脚本可重复，不能替代 104–106 授权。变更/回执同事务，重放返回历史状态而非当前 readiness；详见[连接版本契约](contracts/V02_CONNECTION_VERSIONS.md)。管理员连接仅用于独立受信发布终端，不进入运行时 env。

`PilotStore.provision_tenant` 和 `provision_user` 只允许管理员脚本调用。它们不得暴露为客户 HTTP 路由。生产 provisioning/migration 必须使用独立的数据库 owner/管理员连接；Web 应用角色不能读取 `pilot_tenants` 目录，也不能创建租户。管理员生成用户后，用 `pilot.auth.issue_token()` 签发短期令牌；令牌只通过 HTTPS 或本机安全渠道交给用户。

可使用受信 CLI（仅在管理员终端执行）完成同样流程：

```bash
uv run --frozen yike-pilot-provision tenant --name '试用团队'
uv run --frozen yike-pilot-provision user --tenant-id '<tenant-id>' --email 'user@example.com'
export YIKE_PILOT_AUTH_SECRET='<random-secret-kept-outside-git>'
uv run --frozen yike-pilot-provision token --user-id '<user-id>' --ttl-seconds 3600
```

CLI 输出的令牌只应通过安全渠道交给试用用户，不写入仓库、日志或研究包。

V02-01B 会话撤销候选要求发布作业先执行 105 迁移及上面的显式最小权限授权。客户 `DELETE /api/ui/session` 将撤销本次携带的有效 Bearer/Cookie，旧凭据不能重新换取登录 Cookie；应用不可用时不宣称撤销成功。它不是管理员“全端退出”或短信登录已交付，详细边界与升级顺序见[会话撤销契约](contracts/V02_SESSION_REVOCATION.md)。

## 当前管理员研究包导入

后台 Codex＋商机研究 Skill 先输出研究包，人工核对原帖/原评论、时间、业务背景和联系路径，并将 `review_status` 设为 `APPROVED`。通过 `pilot.research_import.import_reviewed_bundle()` 导入；任何一条证据校验失败，整包在写入前拒绝。导入后用户只能看到自己租户的数据。

管理员可用命令行导入已批准的 JSON 研究包（不会开放为客户 HTTP 接口；导入命令不执行迁移，须先由受信迁移作业完成 schema）：

```bash
export YIKE_PILOT_ADMIN_DATABASE_URL='postgresql://<admin-user>:<password>@<private-host>:5432/<database>'
uv run --frozen yike-pilot-import \
  --bundle ./approved-bundle.json \
  --user-id '<provisioned-user-id>' \
  --profile-version-id '<confirmed-profile-version-id>'
```

命令不会执行迁移，只校验整包并输出 `created`、`duplicates` 和 `total`。任一条证据不合格时整包不写入；schema 必须由受信迁移作业预先完成。当前 PostgreSQL 实现先整包预校验，再在同一事务中写入全部条目、来源版本与观察记录；后续条目发生冲突或数据库错误时整包回滚。重复导入键必须匹配原画像、来源身份和公开 URL，否则拒绝，不以幂等命中掩盖 URL 冲突。隔离库验证见 [主线整合验收](qa/main-integration/REVIEW.md)。

## 当前已实现的用户路径

1. 用签名令牌打开 `/profile`，填写服务能力、地域、偏好和排除项。
2. 保存后先确认画像版本；未确认版本不能导入机会。
3. 在 `/opportunities` 查看经人工复核的机会。
4. 打开详情页核对原始证据，必要时人工标记来源为 OPEN、EXPIRED、BLOCKED 或 UNVERIFIED；复制独立的公开评论或私信草稿，系统不自动发送。
5. 在平台完成联系后回到详情页，记录真实跟进状态和备注。

## 试用前检查

- 数据库为本产品独立实例，应用角色不是超级用户，数据库不对公网开放。
- 日志、备份和导出不包含 Cookie、验证码、模型密钥或私信外的敏感数据。
- 提交前运行 `scripts/secret_scan.sh`；它只检查 Git 跟踪内容中的疑似凭据值，不能替代目标环境日志和备份抽查。
- 先用空库完成启动，再导入一份真实、已复核的研究包。
- 任何来源过期或访问受阻，页面必须提示人工复核；不能当作有效商机继续推进。

当前手册不等于生产部署证明；服务器、域名、HTTPS、备份恢复、回滚和真实手机验收需在目标环境单独记录。

## 备份与恢复演练

**2026-09-12源码修复：旧脚本的HMAC错误使用密钥文件路径字面值，未读取文件秘密，历史缺陷见[Win复核第12节](qa/WIN_CROSS_REVIEW_20260909.md)。新脚本仅创建/接受V2认证侧车，具体源码与独立审核见[修复记录](superpowers/plans/2026-09-12-backup-auth-v2.md)。旧备份必须保留但不可信，禁止自动删除、转换、重签或恢复；它们不能作为CP-06放行证据。**

以下命令仅适用于新V2备份，不是目标生产环境执行批准。需要Python 3.10+、OpenSSL、PostgreSQL客户端；目标环境使用独立、受限的备份路径：

```bash
export YIKE_PILOT_ADMIN_DATABASE_URL='postgresql://<backup-admin>:<password>@<private-db>:5432/<database>'
export YIKE_PILOT_IMAGE='registry.example.com/yike/customer-pilot@sha256:<64-hex-digest>'
export YIKE_PILOT_BACKUP_PASSPHRASE_FILE='/secure/secret-store/pilot-backup-passphrase'
# 备份/恢复只在受信管理员终端使用管理员连接；不要把这个变量加载进 Compose 运行时 env。
scripts/backup_pilot.sh /secure/backup/path/pilot-YYYYMMDD.dump.enc
CONFIRM_RESTORE=YES YIKE_RESTORE_TARGET=isolated scripts/restore_pilot.sh /secure/backup/path/pilot-YYYYMMDD.dump.enc
```

备份使用独立管理员连接，因为运行时应用角色的 RLS 和最小权限不能完成全库 `pg_dump`，也不应执行 `pg_restore --clean`。恢复前必须选定隔离数据库并人工确认；数据库目标实际取自`YIKE_PILOT_ADMIN_DATABASE_URL`，`YIKE_RESTORE_TARGET=isolated`是显式操作确认，不是脚本自动识别生产库的保护。passphrase来自仓库外、属当前用户且仅所有者可读的普通文件，禁止末级符号链接；文件上限64KiB、第一行1–512字节且非空白，无NUL/CR，与OpenSSL file密码源一致。建议使用密钥管理生成的随机高熵秘密。秘密不会作为命令参数或日志输出；改变文件路径不改变认证key，改变内容会认证失败。

新`.enc.mac`为`YIKE-BACKUP-MAC-V2\n`加32字节HMAC-SHA256。独立认证key从秘密内容和domain+密文头通过PBKDF2-HMAC-SHA256/200000次派生；加密继续AES256CBC/PBKDF2/200000次。每次操作先固定一个600权限的私有秘密快照，加密与认证（或认证与解密）只使用这个快照，避免原密钥文件轮换造成不一致。临时秘密快照与备份目标不得位于仓库内，不要把TMPDIR指向仓库；退出时精确清理本次秘密文件。

恢复先复制密文到私有目录，对该快照认证成功后解密同一快照，再执行pg_restore。新备份通过精确目标的os.link不覆盖发布；遇既有文件、目录或链接都不能改写/写入其内部。缺失/旧版/错误长度/篡改侧车均拒绝。

旧备份不执行“补一个V2侧车”来升级信任。应从已独立核实的正常数据库重新生成V2备份；若必须救援旧备份，另行人工核实来源、选择隔离目标并审批，当前脚本不提供降级开关。新源码测试仅使用fixture pg_dump/pg_restore，不证明真实数据库恢复；目标环境恢复演练和回滚镜像SHA仍须写入CP-06记录。

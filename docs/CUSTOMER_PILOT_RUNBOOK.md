# 意客 AI 客户试用运行手册

本手册只覆盖 `pilot/` 客户试用线，不启动旧的 B 站/抖音 SQLite 采集器。

## 本地启动

准备一个独立 PostgreSQL 数据库，并在当前 shell 临时设置变量（不要提交 `.env`）：

```bash
export YIKE_PILOT_DATABASE_URL='postgresql://<app-user>:<password>@<private-host>:5432/<database>'
export YIKE_PILOT_AUTH_SECRET='<random-secret-kept-outside-git>'
uv run --frozen yike-pilot-migrate   # 仅由受信管理员/发布作业执行一次
uv sync --frozen --extra dev
uv run --frozen yike-pilot-web
```

反向代理或容器编排可使用 `GET /healthz` 做进程存活检查、`GET /readyz` 做 PostgreSQL 就绪检查；二者不要求用户令牌，数据库不可用时 `/readyz` 返回 503。

缺少数据库 URL 或认证密钥时，启动必须失败；不会静默退回旧 SQLite 数据库。Web 进程本身不执行迁移，生产应用角色无需 CREATE/ALTER 权限；迁移必须由受信管理员或发布作业先执行。

真实用户可通过 HTTPS 打开 `/session`，粘贴管理员经安全渠道提供的短期访问令牌换取 HttpOnly、SameSite=Strict 会话 Cookie。应用不信任客户端伪造的 `X-Forwarded-Proto`；反向代理必须覆盖该头并确保应用端口不公网直连。生产不得使用 `/__dev/session`，也不得把令牌放进 URL。

## 受信 provisioning

`PilotStore.provision_tenant` 和 `provision_user` 只允许管理员脚本调用。它们不得暴露为客户 HTTP 路由。管理员生成用户后，用 `pilot.auth.issue_token()` 签发短期令牌；令牌只通过 HTTPS 或本机安全渠道交给用户。

可使用受信 CLI（仅在管理员终端执行）完成同样流程：

```bash
uv run --frozen yike-pilot-provision tenant --name '试用团队'
uv run --frozen yike-pilot-provision user --tenant-id '<tenant-id>' --email 'user@example.com'
export YIKE_PILOT_AUTH_SECRET='<random-secret-kept-outside-git>'
uv run --frozen yike-pilot-provision token --user-id '<user-id>' --ttl-seconds 3600
```

CLI 输出的令牌只应通过安全渠道交给试用用户，不写入仓库、日志或研究包。

## 研究包导入

后台 Codex＋商机研究 Skill 先输出研究包，人工核对原帖/原评论、时间、业务背景和联系路径，并将 `review_status` 设为 `APPROVED`。通过 `pilot.research_import.import_reviewed_bundle()` 导入；任何一条证据校验失败，整包在写入前拒绝。导入后用户只能看到自己租户的数据。

管理员可用命令行导入已批准的 JSON 研究包（不会开放为客户 HTTP 接口）：

```bash
export YIKE_PILOT_DATABASE_URL='postgresql://<app-user>:<password>@<private-host>:5432/<database>'
uv run --frozen yike-pilot-import \
  --bundle ./approved-bundle.json \
  --user-id '<provisioned-user-id>' \
  --profile-version-id '<confirmed-profile-version-id>'
```

命令会先执行迁移，再校验整包；输出 `created`、`duplicates` 和 `total`。任一条证据不合格时整包不写入。

## 用户路径

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

目标环境使用独立、受限的备份路径执行：

```bash
export YIKE_PILOT_DATABASE_URL='postgresql://<non-superuser>:<password>@<private-db>:5432/<database>'
scripts/backup_pilot.sh /secure/backup/path/pilot-YYYYMMDD.dump
CONFIRM_RESTORE=YES scripts/restore_pilot.sh /secure/backup/path/pilot-YYYYMMDD.dump
```

恢复前必须选定隔离数据库并人工确认；脚本不会自动恢复到当前生产库。演练结果、备份加密方式和回滚镜像 SHA 需写入目标环境验收记录。

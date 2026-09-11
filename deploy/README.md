# 意客 AI 应用镜像

相似研究来源合同增量（2026-09-11）：客户端与服务端须配套升级，新版确认策略可包含`research.provenance`，旧客户端严格解析器不认识该字段。无新迁移；来源核验依赖既有机会、证据和复核读取权限，整体升级使用下述完整授权入口，不只执行早期策略授权。现有32c9c0c镜像候选不包含本增量；本批未构包或部署，也未开放research执行或收费。技术范围见[来源绑定记录](../docs/superpowers/plans/2026-09-11-similar-research-provenance.md)。

首次部署或整体升级：完成本版本全部迁移后，在受信发布端使用独立管理员连接执行完整授权入口；替换为实际既有受限应用角色，Web 环境不保留管理员 URL。脚本在同一事务纳入全部增量授权，失败时不要启动新版服务；不创建角色、改密码或自动回收过宽权限。正式数据库不用 `GRANT ALL`。

```sh
psql "$YIKE_PILOT_ADMIN_DATABASE_URL" -X -v ON_ERROR_STOP=1 \
  -v app_role=YOUR_EXISTING_RESTRICTED_APP_ROLE -f deploy/grant_runtime.sql
```

发布端需要同版本 `deploy/` 文件及 psql；镜像仍仅包含服务运行代码。整体部署优先使用此入口，下文逐版本说明保留溯源。基础画像权限缺失会出现 readyz200 但画像500；本机真实空库、镜像 HTTP 保存/确认与跨租户检查见[空库记录](../docs/qa/EMPTY_DATABASE_DEPLOYMENT_20260911.md)，不等于所有业务或生产已验收。

2026-09-11镜像启动修复：只加入服务端依赖的`app/__init__.py`和`app/model_contract.py`，其余本地采集器继续排除。首次amd64构建和原CMD非root启动见[历史镜像记录](../docs/qa/SERVICE_IMAGE_STARTUP_20260911.md)。最新Win交付记录已更新至66745ef及yike.tuokexing.net HTTPS；6832482和Mac的32c9c0c候选为历史版本。实际版本、候选摘要及仍缺的模型/客户端/真实业务项统一见[服务器交付记录](../docs/qa/SERVER_137138_DEPLOYMENT.md)，本批未远程复测，不重复构建相同产品字节。

四平台接线：在原执行/策略/连接及监控迁移授权基础上，显式设置 `YIKE_PILOT_COLLECTION_MODE=four-platform-foreground-v1` 可开放小红书、抖音、B站、知乎的单次搜索；`four-platform-monitor-v1` 同时开放原policy1监控。旧xhs/three模式不新增知乎权限。客户端与固定源须包含[四平台接线](../docs/superpowers/plans/2026-09-11-four-platform-client.md#实施与验证)及0003补丁，仍要逐账号核验、同设备串行共享预算和确认接管。设置配置不是实际平台成功。服务器已有内网服务，但公开HTTPS、同源码Windows包及真实账号验收仍待完成，实际状态以服务器交付记录为准。

结构化跟进（迁移131）：先迁移，再在管理员部署连接中将 `yike.app_role` 设为既有受限应用角色，执行 [结构化授权](grant_structured_followups.sql)，最后启动新runtime。机会列表的有效跟进状态也读取新表，因此不能省略该授权。新表只SELECT/INSERT且FORCE RLS、修订不可改；旧人工表只读保留。回复已读仅意客内记录，不改原平台/设备签名；无定时通知。接口/版本/限定联验见[唯一记录](../docs/superpowers/plans/2026-09-11-structured-followup-service.md#实施与验证)，本说明不是部署执行记录。

短句教练（迁移130）：先迁移，再以既有受限 `yike.app_role` 执行 [短句授权](grant_short_coach.sql)，最后启动runtime。复用 `YIKE_PILOT_ASSESSMENT_*` 三项模型配置；无配置不能生成，不隐式外发。用户先看完整原文/人工草稿与模型披露，再确认单次调用。每天每租户50次为服务端安全上限而非收费；失败计入，原请求不重发，旧PROCESSING不能当失败重跑。模型子进程20秒截止，客户端25秒HTTP等待。当前联验只有合成来源和受控模型，不是生产部署；见[唯一记录](../docs/superpowers/plans/2026-09-11-short-coach-service.md#实施与验证)。

搜索建议未受理恢复（迁移129）：在原110＋128基础上完成129，并重新执行新版[建议请求授权](grant_search_suggestions.sql)，才启动本批runtime。新表按租户/用户FORCE RLS且只授SELECT/INSERT，拒绝与受理不能双写；旧请求仍从原接口只读恢复。没有迁移/授权时，不把读取异常或404解释为未受理。本说明是部署要求，不是实际生产执行记录；[版本与验收](../docs/superpowers/plans/2026-09-11-search-suggestion-rejection.md#实施与验证)。

公开社区受控验收配置：后端 `f1fbe80` 与客户端 `148ddba` 或其后兼容版本配套时，`YIKE_PILOT_COLLECTION_MODE=four-platform-public-monitor-v1` 可在原四账号平台之外显式开放 V2EX 近期主题匿名单次采样；不是全网/历史检索，不开放公开社区监控。新增 support 字段不兼容旧客户端，必须配套升级；默认配置未改。本机服务身份与设备绑定仍必须就绪，匿名来源不要求原生 Python 或平台登录，混合任务仍要验证各原生账号。已完成隔离真实HTTP/PG、一次实际来源读取及候选原文接口回读；测试登录/设备装配不替代生产身份、HTTPS、Electron窗口或Windows验收，生产启用仍需这些门禁；[范围与接续](../docs/superpowers/plans/2026-09-11-public-community-driver.md#真实http与postgresql接续2026-09-11)。

公开社区定时抽样增量：新版服务端与客户端配套后，显式 `YIKE_PILOT_COLLECTION_MODE=four-platform-public-sampling-monitor-v1` 才开放 V2EX 近期主题监控。旧 `four-platform-public-monitor-v1` 仍不开放公开源监控，默认环境不变。foreground support 新增 `public_monitor:true`，monitor support 新增 `public_source:v2ex-latest-v1`，旧客户端不得配套新模式。复用126/127与候选授权，无新增迁移；仍须当前服务身份和设备、已确认策略、本机接管，原生混合目标另验平台账号。最短1小时，在线每轮一次latest读取；不是历史/全站/评论覆盖，离线不补跑，同来源重复不计新商机。源码及限定技术证据见[本批计划](../docs/superpowers/plans/2026-09-11-public-community-monitor.md)。现有32c9c0c镜像不含本批代码，需后续绑定新源码构建，不得只改旧服务配置冒充接通；尚未真实平台周期、Windows或生产验收。

持续监控基础（迁移126/127）：执行 [轮次授权](grant_monitor_runtime.sql)，复用原执行/策略/连接授权。原 `YIKE_PILOT_COLLECTION_MODE=three-platform-monitor-v1` 开放三平台 policy1 监控，后续四平台及公开源增量见上文；每次 START 仍必须有原预留和设备签名，旧模式不扩大权限。客户端源码已接“新建监控→确认策略和账号→本机接管→周期执行→暂停/原请求核对”，原生平台串行共用采集槽。必须保持客户端在线；关闭后不补跑，重新打开需确认账号后接管，不能仅切环境变量就宣传持续采集。`/api/ui/monitor-runtime/support` 只报告部署能力，不证明本机环境或平台成功；`pulse.can_start=false` 维持在线并明确跳过忙碌时段。无外部发送。本批尚无新的 Windows 包/真实平台或生产验收证据，入口与版本见[客户端单一记录](../docs/superpowers/plans/2026-09-11-monitor-client.md)。

监控计划基础（迁移126）：迁移后以受信发布作业设置既有 `yike.app_role` 并执行 [监控计划授权](grant_monitor_plans.sql)，另需原画像/策略/会话权限。普通runtime仅保存计划、暂停/恢复和历史回执，不启动采集；`ACTIVE + NOT_CONNECTED` 不能作为监控已运行。尚无周期执行器/新客户端入口，本记录不是生产部署。[接口与证据](../docs/superpowers/plans/2026-09-11-monitor-plans.md)。

本文件是现有 `pilot/` 服务端的部署子手册。当前开发目标与进度见 [V0.2 实施任务书](../docs/V02_IMPLEMENTATION_TASKBOOK.md)；缺少生产环境只影响相应部署验收，不阻止其他研发。下面的 Linux Web 镜像不是 Windows 客户端或平台采集执行器，不得把管理员连接、应用数据库连接或服务端签名密钥打入桌面安装包。

这是应用容器骨架，不是生产上线证明。目标环境仍须单独提供私网 PostgreSQL、反向代理 HTTPS、日志脱敏、备份恢复和回滚记录。应用已关闭 Uvicorn 原始访问日志，并仅记录不含查询参数的 method/path/status。先由受信发布作业运行 `uv run --frozen yike-pilot-migrate`，再以非 owner 应用角色启动 `yike-pilot-web`；Web 进程不会执行迁移。

V02-01A/104 与 V02-01B/105 升级必须严格按“迁移→显式最小授权→新版应用启动”执行。受信发布作业对既有应用角色运行 [grant_session_revocations.sql](grant_session_revocations.sql)：设备和连接表仅 SELECT/INSERT/UPDATE，事件表仅 SELECT/INSERT，会话撤销表仅 SELECT/INSERT。文件名为兼容既有 105 发布流程保留；脚本可重复执行，不依赖全表或默认授权。执行命令、角色选择和管理员运行环境隔离见[客户试用运行手册](../docs/CUSTOMER_PILOT_RUNBOOK.md)。仅数据库连通不证明新表权限已配置。

正常 Web 入口现装配已确认策略、执行历史、候选入库和复核服务，使用同一个受限应用 DB；部署前还须按已接收迁移分别运行 [执行授权](grant_execution_runtime.sql)、[候选授权](grant_candidate_ingestion.sql)、[复核授权](grant_candidate_review.sql)、[策略授权](grant_research_strategies.sql)和[原文证据授权](grant_opportunity_evidence.sql)。普通启动不自动补权限，非空管理员 DB 环境变量将导致启动拒绝；该检查不验证应用 URL 的实际角色。

人工草稿服务已接普通 Web runtime：迁移121后，管理员须以同一 `yike.app_role` 运行 [草稿授权](grant_contact_drafts.sql)，只授新表SELECT/INSERT；读取机会/画像/来源及其锁权限沿用上述授权。原UUID查回执和最新草稿接口见[07B接线计划](../docs/superpowers/plans/2026-09-10-contact-draft-persistence.md)。保存不代表发送，当前outreach能力仍关闭；本说明不是生产部署验收。

人工确认队列接普通runtime：迁移122后，同一受限角色运行[队列授权](grant_outreach_queue.sql)，新表仅SELECT/INSERT及UPDATE(state)，触发器禁止改确认内容或重启已取消请求。API见[触达合同](../docs/contracts/V02_OUTREACH_CHANNELS.md#07b-人工确认队列2026-09-10)；无派发进程，不启用outreach能力，不代表真实发送/上线。

123增加单次领取/签名结果：迁移后**同时执行队列授权和[派发授权](grant_outreach_dispatch.sql)**，后者只给新事件表SELECT/INSERT，原队列查询/取消现在也需要这些读取权限；漏授权会拒绝请求，不能按旧122部署。`YIKE_PILOT_OUTREACH_PLATFORMS`默认为空（CLAIM拒绝），仅接受逗号分隔BILIBILI/DOUYIN/XIAOHONGSHU/ZHIHU，未知值启动拒绝。正式开启需对应客户端实际渠道核验、持久消费许可及真实平台验收；本批没有开启生产配置或全局outreach能力，也没有运行发送进程。接口与UNKNOWN恢复见[增量合同](../docs/contracts/V02_OUTREACH_CHANNELS.md#07b-单次领取与结果2026-09-10)。

如需候选 ASSESS，从仓库外服务器配置同时提供 `YIKE_PILOT_ASSESSMENT_BASE_URL`、`YIKE_PILOT_ASSESSMENT_API_KEY`、`YIKE_PILOT_ASSESSMENT_MODEL`；三项全无仍可启动，部分或非法配置明确失败。启动与只读接口不探测模型。完整配置规则见[正常装配契约](../docs/contracts/V02_NORMAL_RUNTIME_COMPOSITION.md)。真实来源 policy 未接通时 START 仍不可用；建议和平台收发须分别满足下述专用配置及授权，不能由评分模型配置推导开启，也不把 Web 存活或数据库可连当作全链就绪。

搜索建议服务（迁移110＋128）：先完成迁移及既有[建议请求授权](grant_search_suggestions.sql)，仍需原画像/会话权限。受控服务器独立配置 `YIKE_PILOT_SEARCH_SUGGESTION_BASE_URL`、`YIKE_PILOT_SEARCH_SUGGESTION_API_KEY`、`YIKE_PILOT_SEARCH_SUGGESTION_MODEL`；三项全无时只保留认证回执查询，部分/非法配置阻止启动。不能隐式复用评分凭据。客户端需先展示 `/api/ui/search-suggestions/preview` 返回的完整业务介绍及模型快照，再以显式授权提交；画像确认不等于允许外发。只外发该业务介绍，搜索词不是自动采集许可。POST快速返回持久原请求，最多2工作者/4已接收工作，模型总截止由现有子进程监督；UNKNOWN/PENDING只核对原请求，不重跑。关闭未确认会以固定错误报告，不伪称已停止。本批接通服务端，不代表桌面生成/采用入口已可用；版本及后续见[接续记录](../docs/superpowers/plans/2026-09-11-search-suggestion-service.md)。

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

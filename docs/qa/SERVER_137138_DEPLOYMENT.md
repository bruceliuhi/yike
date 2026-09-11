# 101.200.137.138 部署与测试交付

## 临时访问码已部署：fbf9f94（2026-09-11）

当前 customer 与独立 ops 均为 `fbf9f942df0c2be2189a98a930948f9f9b104b1b`。此节取代下文各历史时点的“当前版本”；仅解除短信投递期间的受邀登录代码阻塞，不代表客户已激活或完整产品验收。

- 用户批准显式临时访问码；代码 `159cb48` 经非作者整批 GO，后续 `fbf9f94` 仅登记证据。隔离 PG 新测试 12 passed；桌面定向 164 passed＋类型检查，末次文案后登录 36 passed。旧后端回归仍记录 107 passed / 7 个已知 fixture 权限差异，不称全绿。[实现与边界](../superpowers/plans/2026-09-11-temporary-access-login.md#evidence)。
- 一次 Linux amd64 构建、一次 Mac arm64 构包。部署镜像不可变引用 `127.0.0.1:18750/yike/server@sha256:9bfcee5099a914e7ad9358fa3d35eaeb0c4e84bc08da7f6a95352c5514eb95ab`，OCI revision 与上述源码一致。
- 切换前认证加密备份 `backups/yike-before-fbf9f94.dump.enc`＋MAC；受信一次性容器执行含 138 的 37 项迁移及 runtime/ops 最小 grants。未更换密码、PHONE/SMS、模型配置或代理策略。临时码不反推手机号验证，不自动转换既有 trial。
- 独立部署脚本审查首次发现 ops 停止/创建间的回滚空窗，修复后差量 GO；最终脚本 SHA256 `930a4dc6d06f1fb7b5fdb3e556cb238b870076ad66f5a8272c6aa06ce8d28994`。先 loopback18788 候选，再 customer18787，最后 ops18789；三次 ready 通过，CP-06 配置检查通过。两个正式容器实际 revision 一致、running、重启0。未触发回滚，不能当恢复演练。
- 公网 HTTPS capabilities 实测 `access_login / sms_login / search_suggestions` 均 available；没有调用发短信、模型或平台执行接口。旧 customer 镜像和旧 ops 停机容器 `yike-ai2026-ops-before-fbf9f94` 保留供回滚，未删除客户数据。
- 同版 Mac ZIP SHA256 `99b439b9d80f525af40a78408245726023c1aa35661a43e9630a43398b1a6ebb`；实际包以空隔离用户目录启动，固定 HTTPS 已配置、匿名 session401，临时码表单无需手机号/OTP。首次检查脚本误用旧标签而超时，修正选择器后通过，产品字节未变、未重构包。图与脚本保留在 `/tmp/yike-access-release.HLSFSw/`，仅 UI/匿名接通证据。
- **未验：** 此部署过程没有签发码、客户激活、实际 OS 会话重启恢复或真实平台收发。后续由已授权侧任务经正常 ops 明确签发，不通过 SQL 自动改发；第一次客户登录才开始72小时。用户暂无 Windows 环境，Windows 构包/安装/运行仍未验。完整 Goal 保持 ACTIVE。

## 模型已部署：b40cc3b（2026-09-11）

当前customer源码冻结 `b40cc3b357b0ac05dc2a0bf2cb946c5d725a0d38`，不是下文历史056e258。ops仍使用056e258镜像及已验的浏览器来源代理热修，未随customer重启。下面历史记录保留各次时点。

- 两批模型补丁经非作者GO；最终Turbo补丁原提交bd384b9，主线cherry-pick为b40cc3b。主线程定向34 passed、1项需独立DB的用例skipped，不重复全仓或侧任务400项。四个有界请求适配固定方舟型号，不改本地严格解析、超时、重试与主执行链。
- 两组显式 `ASSESSMENT` / `SEARCH_SUGGESTION` 配置均为北京Ark v3与 `doubao-seed-2-1-turbo-260628`，只从用户已批准的本机ARK_API_KEY经SSH stdin装配；不把来源env整份复制。旧SMS/PHONE等所有键逐字保持，新增恰好6项；ops没有模型凭据。实际应用日志未发现已配置secret/API key/DB URL明文。
- 新Linux amd64镜像仅构建一次，源归档SHA256 `dcb5afdb472ebb872465df35351a35321215133c8547319ff9f5945eb13dcf84`，镜像归档 `7391ca3858d5c8714fae92ed0e84e8fb2e615e17436e9eeeaa8ca6fc5bd57dd6`，传输后逐字校验。运行image ID `sha256:0ba5b0b91912ca4a1365da5c7b51e87dc7e7223028c0442623709eabd8570897`，私有registry不可变引用 `127.0.0.1:18750/yike/server@sha256:7354ec43ba9e1ebb6038dd346fbaa44d12e1f055ffc71dfe79eeb86f7cb22487`。
- 切换前完成认证加密DB备份 `backups/yike-before-b40cc3b.dump.enc`＋MAC；保留旧env与发布坐标。该版本相对056e258的schema/grants无差异，不重复迁移。受审一次性helper目录 `/tmp/yike-ark-release.C62CKy`；远端同字节hash已核验，独立整批和追加单次探针GO。
- 先启动loopback18788只读、非root、受资源限制的候选：ready、短信/模型能力、实际受限DB权限和模型装配通过；实际产品 `ProcessSearchSuggestionModel` 以固定合成描述走真实方舟，**11.3秒、10个关键词，严格解析通过**。不读取客户资料、不写业务库，仅一次请求。该证据不覆盖生产真实客户的全部四类模型路径，也不证明线索质量。
- 通过后停止候选，原子切换env、启动正式customer。两次CP-06配置门禁通过；正式ready、短信/搜索建议available、受限DB和装配复查通过，healthy、重启0。没有触发回滚；备份成功不是本次恢复演练。发布事实在服务器 `testdata/model-b40cc3b-deployment.json`。
- 本线程未发SMS或建客户。用户另行授权的本人手机号真实SMS/试用验证由侧任务独占执行：其回传已通过正常ops唯一创建待激活72小时trial，一次HTTP200/challenge ACCEPTED后用户未收到短信；只读QuerySendDetails得到唯一记录21:39:43提交/21:40:08回执、`SendStatus=2 / ErrCode=PORT_NOT_REGISTERED`。这是侧任务的实际查询回传，不是root重复发送/查询；短信投递失败，未消费/激活，不能算登录通过。供应商端处理待确认，保留trial与私有配置、不重复发码/建客户。不得继续使用此前“客户数0”快照推断当前数量。

### 同版Mac客户端有限验收

短信后续合并记录（侧任务回传）：用户另行授权第二指定号码单次测试，正常ops唯一预登记待激活trial并退出，只有一次sms-code请求。QuerySendDetails的唯一记录21:45:10提交/21:45:32回执，仍为 `SendStatus=2 / PORT_NOT_REGISTERED`。两号码均未读取/提交OTP、未激活，等待进程已结束；未重复发码/创建客户或改生产配置。侧任务已核对[官方签名FAQ](https://help.aliyun.com/zh/sms/user-guide/sms-signature-faq)，归因为端口企业实名报备待处理；这是侧任务查询回传，root未重复查询。后续先处理供应商报备，再按新授权测试，保留现有trial，不通过改认证绕过。

`b40cc3b`以Node24.19.0、相同package-lock依赖，设置构建期HTTPS地址后一次 `make:mac` 成功。Vite原有未来配置/弃用警告保留，未掩盖。归档检查40项资源、无.env/私钥文件；ASAR SHA256 `5eb88e8fb6322d54831faefe47a9b49bce88045719700c0a3ec41cc4352e1d4d`，ZIP SHA256 `a30b414ae1415248801df8ada58862137069b9c6555391fadefe093eef1895ec`。

实际 `.app/Contents/MacOS/YikeAI` 以独立空user-data启动（不是开发预览或仅require ASAR）：原生bridge返回serviceConfigured=true，真实HTTPS匿名session返回401；可点击登录并看到手机号、短信验证码、获取验证码按钮，未点发码。[真实包登录界面](pilot-b40/mac-sms-login.png)。临时诊断进程已退出，没有操作用户既有会话。

本地ZIP：`/tmp/yike-v02-scope.Pwf9Fs/desktop/out/make/zip/darwin/arm64/意客AI-darwin-arm64-0.2.0.zip`。Mac包仅用于服务/界面体验，**没有Windows便携平台执行器，也未做公证/分发安装验收**；不作为普通客户完整采集、触达或Windows安装包。下一步仍需冻结SHA的Windows构包与真实用户链路，不能称完整邀请试用版已完成。

## 浏览器登录来源修复（2026-09-11，54ec435）

用户反馈 `/ops/login`“请求来源不匹配”。用独立 Chrome 上下文真实填表复现：旧页面 `Referrer-Policy: no-referrer` 导致浏览器 POST `Origin: null`，被现有严格来源检查拒绝。此前 HTTP 验收手工指定 Origin，未覆盖真实浏览器行为；不能以该检查代表浏览器已验收。

- 源码改为 `same-origin`，缺失/null/跨站 Origin 仍拒绝，CSRF校验不变；新增定向测试先RED后GREEN（1 passed）。独立审核精确提交 `54ec4350de6f7d2c212e61fb4e0b0f3bfc017f14` GO。
- 当前运行镜像仍056e258。本次仅通过受审 `deploy/ops_browser_origin_hotfix.py` 原子更新既有ops两条Nginx location的响应头；父站点和原include均有精确SHA前置，备份 `ops/ops-locations-before-browser-origin.conf`，语法检查成功后graceful reload。显式保留HSTS，未变更客户服务、数据库、凭据或其他站点。
- 修复后include SHA256 `c2bca2c2185be3b86737d807f2219a3ddc995d65c59e191946998a24ae49af67`。下一次镜像包含源码修复后该代理策略等价，不得将旧镜像标为已升级。
- 公网真实Chrome重新GET登录页、从本机私有文件内存读取密码并真实点击提交：浏览器自然产生同站Origin，进入 `/ops/users`；未手工添加登录Origin。随后退出测试会话，确认受保护页重新拒绝访问。未输出密码/手机号、未创建客户、未发送短信。
- 已打开旧登录页面须重新GET页面后再提交，避免沿用旧的document策略。

## 运营入口已部署：/ops（2026-09-11，复用056e258镜像）

在下节客户短信服务已升级且健康的基础上，CodexiMac部署独立运营服务，入口 [运营后台](https://yike.tuokexing.net/ops)。没有重新构建相同字节镜像，也未改客户服务端口/环境。当前客户与ops运行代码均为056e258；main新增方舟兼容源码b18ed12尚未部署或配置模型。

- 新增专属 `yike_ops` 角色，无superuser/BYPASSRLS/CREATEDB/CREATEROLE/REPLICATION或继承关系，独立DB连接和管理员密码。仅共享原手机号HMAC密钥，不共享客户DB连接凭据、短信AccessKey或模型凭据；手机号加密密钥只进入ops。
- 第一次初始化已创建角色和0600配置，但真实连接验证失败。只读诊断发现 `has_database_privilege('yike_ops','yike','CONNECT')=false`，错误分类为permission denied；生产库此前已撤销PUBLIC CONNECT。只向该既有角色补授当前 `yike` 库CONNECT，**未重新生成/轮换任何密钥**，随后真实OpsStore构造通过，schema_create=false、profile_select=false、ciphertext_select=true。此遗漏已补入部署手册，不通过恢复PUBLIC权限解决。
- 独立容器 `yike-ai2026-ops`，镜像ID与下节一致，非root、只读根文件系统、drop-all、no-new-privileges、512MiB/0.5CPU、单worker、loopback18789；仅信任实查Docker网关172.28.0.1。客户服务继续healthy，ops重启0。没有数据库管理员凭据进入ops。
- 仅修改既有意客HTTPS站点，新增 `/ops/login` 与 `/ops` 子路径代理；实际Host透传、固定HTTPS协议、8KiB请求上限、独立限速、关闭access日志/请求及响应缓冲/代理缓存，避免解密手机号响应落入Nginx临时文件。`nginx -t` 成功后graceful reload；其他站点文件未修改。原站点备份 `ops/yike-before-ops-056e258.conf` 保留，未实际执行回退。
- 数据库认证加密备份 `backups/yike-before-ops-056e258.dump.enc` 和`.mac`、独立ops配置认证加密备份 `backups/ops-config-056e258.env.enc` 和`.mac` 均已生成。ops私有目录0700、文件0600，原手机号密钥与客户进程逐字一致；未宣称完成离站备份或本次恢复演练。
- 公网HTTP验收：初次在reload后立即执行时首屏断言失败，未保存该次状态码，不推断具体原因；外网只读复核200后，原验收脚本完整通过，未重启/重新发布。使用一个真实管理员会话验证登录、未登录拒绝、客户列表和开通表单200、Secure/HttpOnly/SameSite cookie、跨Origin及错误CSRF拒绝、退出和旧会话失效。没有生成试用客户或触发SMS；最后trial、phone binding和残留ops测试session均为0。
- 仅将管理员登录信息经SSH传入本机私有文件，未输出密码、Cookie、DSN或加密密钥。文件路径由当前任务私下交给用户，不写入仓库内容。真实容器日志未发现所检查的四项ops/phone秘密，两个进程的凭据隔离检查通过。
- 非作者部署审核修复Nginx响应缓冲落盘问题后GO；CONNECT最小增量、Host透传和密钥单行检查另经差量GO。助手与报告位于本机 `/tmp/yike-ops-release.DIwqZa/`；服务器脱敏事实记录 `/opt/yike-ai2026/testdata/ops-056e258-deployment.json`。审核与只读HTTP不等于真实客户开通/短信激活或浏览器全流程验收。

**下一步：** 先完成已授权模型选型/适配与客户端交付，再由用户本人登记真实测试手机号并在客户端收码验证。后台开放不表示整产品已可收费上线；当前未对外邀请、发码或创建客户。更晚的实测模型选择以实际配置记录为准，不默认启用此前仅用于探测的Flash250615。

## 当前部署：056e258，正式短信配置已装配（2026-09-11）

用户通过独立任务提供目标服务器PEM及阿里云密钥文件并授权配置。CodexiMac接手唯一生产写入后，实际升级到 `056e2588677ef66f2734d6635a4170e00d8c76dd`。下方66745ef是上一健康版本，不再是当前运行源码。本批未启动新的产品研究功能、未创建客户、未调用发送验证码接口、未启用模型或运营服务；**短信装配不等于实际收码或产品上线**。

- 当前服务镜像：`127.0.0.1:18750/yike/server@sha256:9f5cdfdc483802e176bdb11d4dcfa6b091026d0e4153689ea373076a2a98f335`；image ID `sha256:73a30903958e6b9b13092b2b603099b5841805948780733405a48903ee46714d`，实际OCI revision匹配上述完整SHA，架构amd64。仅构建一次，使用Git原字节源码与锁文件，未重跑旧全套测试或构建Windows。
- 原字节源码归档SHA256：`df37a379722e4c47c59c5d2b05d5f647578e1b09b13770957225356d149741d3`；导出镜像归档SHA256：`48b25d11ca3658c69389313d868cb026998f19223b5c5b10b418e3d06915bc05`。本机与服务器文件摘要逐一一致，载入后核对revision；registry digest与本机构建的OCI index digest不是同一种对象，不混写。
- 已生成认证加密备份 `/opt/yike-ai2026/backups/yike-before-056e258.dump.enc` 及 `.mac`，保留旧镜像、`ops/release-before-056e258.json` 和私有旧runtime配置。该次未实际恢复或回退，不复用历史恢复结果冒充本次演练。
- 在独立迁移容器中执行本版本**36项迁移**和完整 `grant_runtime.sql` 清单；真实数据库返回 `MIGRATIONS_AND_RESTRICTED_GRANTS_OK 36`。管理员凭据仅进入该离线迁移进程，不进入Web；迁移锁等待5秒、单语句120秒上限。schema与授权分两个事务；如果授权失败不能声称schema也已回滚。此轮两阶段均成功。
- 用户阿里云凭据只在内存解析并经已验证SSH stdin传输，无秘密argv、工具输出或本机副本。服务器候选私有env模式0600，原7项运行配置逐项保持相同。此前手机号认证密钥不存在且 `pilot_phone_bindings` 为0，才生成独立phone认证密钥；没有更换原会话签名密钥。固定签名/模板/变量按 [短信手册](../../deploy/ALIYUN_SMS.md) 装配，不设置 `DEBUG=sdk`。
- 候选loopback18788通过 `/readyz` 与 `sms_login.available=true` 后，再用候选自身真实 `yike_app` 连接执行phone/trial表零行读取、试用gate、激活列UPDATE权限及手机号密文无SELECT权限检查；全部通过后才切正式18787。正式服务再次通过同样检查。两次cp06预检通过，候选容器停止后自动移除；只替换本项目app容器，数据库和其他项目容器未变更。
- 最终容器healthy、重启0、非root、只读根文件系统、loopback绑定。核对运行环境没有管理员/ops凭据，检查实际容器日志未包含四项认证/SMS秘密。公网TLS验证开启的 `/healthz`、`/readyz`、`/api/ui/capabilities`、`/session` 均200；本机外网也回读 `sms_login.available=true`。此能力布尔值只证明适配器已装配，不能证明RAM发送权限、供应商受理或手机号归属。
- 现有 `/session` 仍是Web短期token入口；本次没有改成网页短信表单，也没有交付匹配的Windows新包。客户短信表单属于客户端；普通客户首次trial须另经运营开通，不能宣传任何手机号现在均可自助注册。
- 发布助手经非作者整批审核，四项发现（空密钥处理、残留候选、回退就绪、真实表权限检查）修复后GO。独立报告与助手在本机 `/tmp/yike-sms-release.HhqvWR/`；服务器redacted事实记录 `/opt/yike-ai2026/testdata/sms-056e258-deployment.json`，源码/镜像位于本项目artifacts及releases目录。

**接续：** 独立运营服务部署与真实测试手机号开通、用户本人实际收码/首次激活/后续登录；已获授权的火山方舟模型仍需通过产品适配器实测后配置。当前线上模型配置已只读确认为空；不能根据“有API key”标模型可用。Windows、真实平台采集/触达/回复、多源研究和跨行业客户UAT继续保持未完成。完整Goal保持进行中。

## 上一部署：66745ef ＋ yike.tuokexing.net HTTPS（2026-09-11）

本轮记录提交期间main新增公开社区监控服务代码，最终发布窗口固定到 `66745efa0e382beb3337a8ac01da23dc6cf59922`，已完成第二次差量升级。下节001741f是本轮中间版本及首次HTTPS接通证据，不是当前运行版本；后续来件不自动追认为本候选。

记录合入时再接收`f3faebe/54bae32`，仅客户端策略转换、测试和文档变化；全部Dockerfile输入及部署脚本与66745ef无差量，因此复用当前服务镜像，不重复构包。客户端修复不代表已经交付新Windows包，镜像revision仍如实为66745ef。

- 当前入口：[HTTPS登录页](https://yike.tuokexing.net/session)。保留下节已验证的新域名、证书、续期及隔离配置；仍为短期token登录。
- 当前镜像 `127.0.0.1:18750/yike/server@sha256:d693c6acf3b3d169b7414c44f49b5bcdfbf420720f46dff7bc59009ef1639964`，ID `sha256:363c99adc3256b3d69568922096f4e4c09457be2504eec310ee3bdce6a281a40`；实际OCI revision与66745ef完整SHA一致，healthy、重启0。
- 原字节源码归档SHA256 `9b34d1160ef3792308da6932a4505f4b8023e919a8b0addd5b10c728ca2a71a9`，本机与服务器一致。
- 新增公开监控代码复用其独立审核证据；在目标服务器执行策略、runtime API、前台采集及真实隔离PG多轮监控定向测试，**62 passed / 无跳过**。专用测试库`yike_public_monitor`与运行库分离，测试PG已停止。合成多轮输入不是实际平台监控；运行配置继续`four-platform-monitor-v1`，未自动打开新公开社区模式。
- 31迁移/受限授权、cp06预检、18788候选ready后切换18787均通过。最终版本重新执行**33项部署冒烟全部通过**（范围及合成导入边界同下节）；本机公网TLS校验的health/ready均200，最终容器权限、端口、秘密配置与日志检查通过。
- 升级前V2认证备份`/opt/yike-ai2026/backups/yike-before-66745ef.dump.enc`及`.mac`、`ops/release-before-66745ef.json`保留；需要应用回退可显式选择上一健康001741f完整SHA，旧镜像保留。本次无schema差量，未实际回退或恢复覆盖运行库。
- 最终原始证据：服务器`/opt/yike-ai2026/testdata/https-66745ef-smoke.json`、`https-66745ef-smoke.log`、`upgrade-66745ef-delta.xml`，本机同名副本在既有`.runtime/deployment-137138-20260911/`。临时软件包下载代理与SSH隧道已关闭。

仍缺意客专用模型与短信配置、同源Windows新包、真实平台收发与客户试用，以及任务书列明的“多找类似”正式研究启动功能。此次是新版服务部署与HTTPS可访问，不代表完整产品上线；不重复全量测试、不覆盖历史失败记录。

## 本轮中间版本：001741f 与首次 HTTPS 接通

用户明确要求更新至最新版本，并更换域名为 `yike.tuokexing.net`。两端DNS实查均指向101.200.137.138；本机main同步后固定 `001741f785098e6f323a8807a78899df9b1515ce`，**服务端已更新，公网HTTPS已接通**。下方6832482及旧域名未解析状态均为历史证据，不再是当前部署状态。

- 入口：[HTTPS登录页](https://yike.tuokexing.net/session)。浏览器已实际打开，显示“登录意客 AI”和短期令牌输入框；当前为token登录，不是短信登录或新Windows客户端交付。
- 镜像 `127.0.0.1:18750/yike/server@sha256:9e79bd3a70ef0bbd74a2939925d16493bbc940e151cf92784e4d776c911fb389`；ID `sha256:4d11fe7303b0c3f26c04f539b0c488fca19c654b907d4cda2a7cf0e79afe65f9`。实际OCI revision为001741f完整SHA，healthy，重启计数0。
- 新原字节归档SHA256 `50d9a781c3f69617af30bac05f51ff94b65818873d7261217ffe75ef8084685e`，本地与远端一致。相对6832482的服务代码差量是已审核的短句API省略字段修复；镜像已包含该修复，未再使用Mac临时路径作为远端产物。
- 31迁移及受限授权重复验证通过；启动前cp06预检通过。先在loopback18788隔离启动候选，ready通过后停止候选并切换原18787服务。数据库、服务秘密、账号隔离和关闭外发/模型的原配置保留。
- 新增独立Nginx站点 `/www/server/panel/vhost/nginx/yike.tuokexing.net.conf`，无default_server；80仅ACME挑战与308 HTTPS跳转，443代理到loopback18787，覆盖Host/XFP/XFF，access日志仅路径、不含query/认证头/Cookie。错误日志使用crit级别，不将其称为通用脱敏器。未改其他业务站点；两次新站点阶段切换均先nginx -t，再graceful reload。
- Let's Encrypt证书SAN仅新域名，有效期截至2026-12-10；certbot.timer已启用并运行，webroot `/www/wwwroot/yike-acme`；续期hook只匹配本证书，检查Nginx配置后reload。独立非作者审核三份站点/续期配置通过。限定该证书的certbot续期dry-run成功；首次遇非交互随机延迟，停止该次演练后按本机版本支持的`--no-random-sleep-on-renew`重跑，未改其他证书或全局续期设置。
- 本机外网curl及服务器CP06 HTTPS探测均health/ready200；TLS证书校验未关闭。首次在reload命令后立即探测曾遇旧证书名称不匹配；不改证书或绕过验证，稍后相同命令与外网探测通过，记录为切换时序瞬态。
- **33项部署冒烟通过**：真实公网HTTPS会话、Secure/HttpOnly/SameSite Cookie及纯Cookie鉴权、伪造XFP被覆盖、同源允许/跨源拒绝、画像保存确认、列表/原文证据/草稿、跨租户隔离、资料与跟进、注销撤销等。包括管理员合成导入去重和loopback明文登录拒绝检查，不能写成33项均为HTTP或真实获客。无真实平台/模型请求；主测试token已注销撤销，跨租户测试token有效期600秒。
- 新版部署布局及短句接口定向测试：**8 passed / 1 deselected**；未配置真实PG/Node联验的ordinary_client场景未重跑，其已绑定Mac证据仍单独保留，不将取消选择写成通过。没有重跑原全仓、没有抹掉下方历史失败。
- 升级前生成V2认证加密备份 `/opt/yike-ai2026/backups/yike-before-001741f.dump.enc`及`.mac`；旧健康镜像及 `/opt/yike-ai2026/ops/release-before-001741f.json`保留。无schema差量，需要应用回退时用既有start_application.sh显式指定6832482完整SHA；本轮未执行实际降级或恢复覆盖运行库。
- 原始新证据：服务器 `/opt/yike-ai2026/testdata/https-001741f-smoke.json`、`upgrade-001741f-delta.xml`，本机同名文件在原`.runtime/deployment-137138-20260911/`。最终实际容器权限、loopback端口、无管理员URL与构建代理变量、秘密文件权限、应用/新站点日志哨兵检查通过。

仍缺意客专用模型与短信配置、同源Windows新包、真实平台收发与客户试用；“多找类似”正式research启动也是任务书已识别的功能缺口。此次完成服务升级和HTTPS入口，不代表完整产品上线或全量测试全绿。

## 首次部署历史（6832482）

2026-09-11，执行方 CodexWin。**服务端已在目标服务器隔离运行；公网 HTTPS、Windows 新包与完整真实业务验收未完成，不能标产品上线。**

## 当前版本与入口

- Gitee `main` 部署源码：`68324820d859221a8ef625e18f6ff3fa1dcc09d6`。首次同步为 `c41155b`；过程中接收主干同一镜像修复、新安装授权与公开来源策略来件后重新固定版本，不追认旧包。
- 服务器：`101.200.137.138`，Ubuntu 24.04 / x86_64；发布目录 `/opt/yike-ai2026/releases/68324820d859221a8ef625e18f6ff3fa1dcc09d6`。
- 当前仅服务器内部 `http://127.0.0.1:18787` 可访问。`yike-ai2026-app` 为 healthy，重启计数0；`/healthz`、`/readyz` 返回200。
- 用户指定域名 `yike.xingheai.net`；本机及服务器最后核查仍无 DNS A 解析。未签发该域名证书、未启用公网 vhost，未修改其他业务站点。
- 运行镜像：`127.0.0.1:18750/yike/server@sha256:0d5070df372a600a8af638a2a52c9dcffa8c5d2ed0c9134e01bee89cdb9ff2e6`。
- 镜像ID：`sha256:3f550f25be32180eccbff35aee8152050fbbfa707540422a29c166d701707154`；实际 OCI revision 与上述源码一致。
- 最终源码归档 SHA256：`e2d2ad2b929a660df5ed0788eb65183084c5ef4fd3a2281e97962b98e2b7dfaf`。使用 `git -c core.autocrlf=false archive --output=...`，本地/服务器摘要一致。
- 提交记录时另接收 `148ddba/f007a7c` 客户端公开来源接线，已同步至本机main。比较其全部镜像输入与6832482无字节差异，故不重复构建；镜像revision仍如实保留6832482。客户端变更单独复测，不追认现有Windows包。

## 已完成的目标服务器验证

1. 独立 PostgreSQL 16、数据目录、Docker网络及运行角色。数据库无宿主端口；app仅loopback 18787，私有镜像registry仅loopback 18750。没有修改其他项目数据库、容器、认证、模型凭据或全局Docker配置。
2. 31个迁移重复执行通过；按新主干 `grant_runtime.sql` 清单执行全部增量授权。app非owner、非superuser、无BYPASSRLS/CREATEDB/CREATEROLE/角色继承，不能读租户目录和迁移元数据、不能创建schema对象。
3. 为仍注册的旧Web人工跟进接口另保留 `pilot_followups INSERT` 与 `pilot_opportunities UPDATE(intent_status,updated_at)`，不是全表授权。这一兼容边界不等于新的结构化跟进已全面实测。
4. 启动前从600权限的实际runtime配置加载，`cp06_validate_env.sh`通过。管理员配置、运行配置、认证秘密、备份秘密分离于Git之外；uid10001、只读根文件系统、cap-drop ALL、no-new-privileges和资源上限生效。
5. **目标服务器30项冒烟检查通过（含HTTP及管理员合成导入）**：health/ready、未认证拒绝、禁用开发登录和API文档、HTTP登录拒绝、受信代理scheme下会话及Cookie标志、跨Origin拒绝、画像保存/确认/读取、合成研究包导入去重、机会列表、原文摘录与短草稿、跨租户证据隐藏、Web页面、执行/监控支持接口、资料/跟进工作区读取、人工结果保存、注销撤销原token。导入去重直接调用管理员函数，不计为HTTP接口。
6. 上述HTTP使用明确合成租户和 `example.invalid` 证据，管理员导入不是平台采集。HTTPS-required接口仅由受信服务器模拟代理scheme；**没有TLS握手、公开DNS或真实客户端验证**。没有向平台发送任何消息。
7. 新V2认证加密备份已实际生成；恢复到独立测试PostgreSQL的 `yike_restore_20260911`，62张表逐表行数与完整行内容摘要一致，包含31条迁移和合成线索。未恢复覆盖运行库，没有旧运行版本可做业务回滚。备份及MAC保留于 `/opt/yike-ai2026/backups/yike-6832482-20260911.dump.enc`及其`.mac`。
8. 最终只读检查：容器无管理员URL/模型API key/构建代理变量；runtime秘密文件不向组/其他用户开放；日志无测试query sentinel及认证秘密。现有Nginx配置检查通过，仅原AIRank站点既有http2弃用警告；没有reload。

## 测试结果（不相加为一次全绿）

| 版本与范围 | 结果 | 限定 |
|---|---|---|
| c41155b Windows完整Vitest | 3516 passed / 35 failed / 26 skipped，另4个未处理错误 | 13个失败测试文件；不是完整通过 |
| c41155b Windows TypeScript | 通过 | 不代表可安装候选 |
| c41155b 业务失败定向复核 | 123 passed / 8 failed | 草稿/防重核心单元通过；页面/恢复联验仍有缺口 |
| c41155b 后端首轮全量主批 | 3266 passed / 218 failed / 207 skipped | 另身份初始模块1 failed，缺Vitest；首次导出CRLF与测试环境问题保留 |
| c41155b 修正环境与归档后的失败范围 | 119 passed / 93 failed / 0 skipped | 因随机参数ID，按失败函数重跑参数族；首次选择器失配未执行测试，不计业务失败 |
| c41155b 身份/独立画像专项 | 各1 passed | 补Node依赖、隔离测试角色基础授权；画像专项去除管理员runtime环境污染 |
| c41155b Windows/Git专属后端专项 | 6 passed | 弥补Linux路径/缺真实Git工作树场景，非真实账号采集 |
| 6832482 Linux新来件部署/策略/空库授权 | 29 passed | 使用隔离真实PG，部署COPY布局已通过 |
| 6832482 Windows公开来源driver / TypeScript | 15 passed / 类型检查通过 | 模拟fetch，无真实V2EX请求，未接为客户能力 |
| 6832482 Windows部署布局测试 | 1 failed，另26 passed | 清空子进程SystemRoot导致WinError10106；Linux同测试通过，保留Windows测试环境问题 |
| 573f553（含148ddba）公开来源客户端接线 | 6文件108 passed，类型检查通过 | 两workers，7.97秒；不覆盖旧全量35失败，不是实际平台搜索 |

剩余93项：85项旧fixture未补132材料引用权限；5项合同期待漂移（0003补丁、strategy结构、account_scope、OPEN来源状态）；3项尚需定位的真实HTTP/恢复联验失败：`test_brief_client_postgres`、`test_short_coach_client_postgres`、`test_desktop_foreground_collection_http_postgres`。不能把后3项继续归为缺Vitest，也没有修改断言或放宽生产权限以使其变绿。

Windows全量35失败主要包括：构包临时目录权限/旧expectedCommit前置、平台路径与symlink约束、异步异常断言、页面fixture与新跟进合同失配、原请求恢复测试。防重复发送相关的部分单元检查通过，不替代当前失败的完整恢复链或真实平台验收。

原始证据本机 `.runtime/deploy-tests-20260911/`、`.runtime/deployment-137138-20260911/`；服务器 `/opt/yike-ai2026/testdata/`，包含JUnit、冒烟与备份JSON和原始日志。它们不进Git，集中结论以本文件为准。两次临时测试PG已停止，tmpfs合成数据随之销毁；运行库、加密备份与测试日志保留。

## 实际遇到的问题及处置

- 服务器公开包下载很慢：使用本机回环限定的PyPI TLS隧道加速本次构建，不关闭TLS验证、不换依赖版本、不配置全局代理。构建后关闭临时隧道。
- 首次Windows `git archive`受autocrlf影响；恢复同提交Git原字节后复核迁移，不修改数据库checksum。原失败证据保留。
- c41155b实际容器漏 `app.model_contract`，启动失败并已停止；本机补回归先红后绿。推送前发现主干已有同等修复 `2d6b79b`，丢弃仅自己未推送的重复提交，采用主干实现。最终镜像实际正常启动，不扩大到本地采集器。

## 未完成与下一步

### Mac 更新镜像候选（2026-09-11，未部署）

为交付已审短句 API 修复，CodexiMac 从干净 Gitee `main@32c9c0c8af3cea5148375e9a8dcba3d4cc0fe701` 的 Git 原字节归档构建一次 Linux/amd64 候选；没有重新构建 Windows，也没有操作远端服务器。相对服务器 `6832482`，运行代码差量仅为 `pilot/short_coach_api.py` 的 `model_dump(exclude_unset=True)`，其他镜像输入未变。上方服务器版本仍然有效，不追认候选为已部署。

- 本机镜像：`yike-service-candidate:32c9c0c`；Docker image ID / OCI index digest 为 `sha256:a897e3b28891154bc9d8637025fa0005077b3957f64ac867140844d143dbd1c0`，amd64 manifest 为 `sha256:e53877da3d8f49cc10f91ce6ee9bdca84896f9a0f0b9adf2b313ac74a8377ed9`，config digest 为 `sha256:3d9e052a944be4ff9a217662c22ce4d04c85ada16183cbb37d8e7ec14cc9db51`。这些是本机构建产物标识，尚无目标 registry 可用引用。
- OCI revision 为上述完整源码 SHA；源码归档 `/tmp/yike-release-32c9c0c.riVbCD/source.tar`，SHA256 `900945d54f3601d4c469072afd8211a215024e083f11a289289cfe4270c52f92`。
- 已导出约99MiB镜像 `/tmp/yike-release-32c9c0c.riVbCD/yike-service-32c9c0c.tar`，SHA256 `190c8d50fccfb50d5947a4ab511a229511bc9a47250089afc95f5c0569cbdca7`。文件仅在本机临时目录，未上传Gitee或服务器；迁移到另一台机器前须传输并重新核对摘要，不能把本机路径当远端路径。
- 原 CMD、uid10001、无源码挂载、只读根文件系统、`network=none`、cap-drop ALL、no-new-privileges 下实际启动，重启次数0。容器内HTTP：healthz200；未接数据库的readyz503；未认证会话401；文档404；携带合成token的开发登录入口404。两次初始探测未提供正确的必需token参数，返回422；核对路由后修正探测，未修改产品或重启容器。
- 镜像内 `short_coach_api.py` SHA256 `24327ebe0d307950148ba9c3b691c405f01e856ec627b4bd496611f473815913` 与固定源码一致，包含修复；`app.model_contract` 从镜像自身加载。镜像内实际调用HTTP body解析器：CoachInput/GenerateInput两种schema均保留省略引用并可二次验证，显式null仍422；首轮探测漏Content-Type被415拒绝，补齐请求头后通过，没有调用模型/数据库。原业务回归复用 `b8c2679` 的限定验收，不重复全量测试。
- 该验证没有数据库、HTTPS、真实模型、客户端或平台收发，不能替代服务就绪或升级验收。下次有权操作服务器的一方可选择校验后加载此导出镜像，或从固定源码构建；沿原独占registry、预检、数据库与受限启动流程，先验证新版再切换，并保留原健康镜像用于回退。

后续测试共因批次 `8718c0a` 已独立GO：[分组证据](../superpowers/plans/2026-09-11-http-recovery-reconciliation.md#后续旧夹具与接口期待共因)。仅测试依赖/期待修正，不更改本文件历史失败总数或部署SHA；最后本机curl仍无法解析yike.xingheai.net。没有新增服务器部署证据。

2026-09-11 CodexiMac 接续：三项原来原因未明的 HTTP／恢复失败已在 `b8c2679` 定位并完成限定修复与独立 GO，详见[三项接续证据](../superpowers/plans/2026-09-11-http-recovery-reconciliation.md)。其中短句 API 是生产缺陷，另外两项为测试权限/期待漂移。Mac 的 6 项通过不改写上面 Win 原始失败总数；**现有服务器镜像未包含短句 API 修复，须按新 SHA 重构部署**，不是客户端纯变更免构包情形。

- DNS管理员添加 **A记录：`yike` → `101.200.137.138`**。生效后为该域名单独签证书、配置受信HTTPS反代并实测Cookie/同源策略；不得复用只覆盖主域/www的旧证书。
- 需要意客专用模型Base URL、模型名、API key，在服务器秘密文件配置。评分/短句与搜索建议有各自显式配置，不借用其他项目密钥。未配置短信服务；当前是短期token登录。
- 真实四平台账号核验、采集、模型判断与生成、“多找类似”真实结果、逐项人工批准的发送、真实回复和转化数据均未验。外发仍关闭；公共来源新能力也未启用。
- 没有与该服务同SHA、绑定可用HTTPS的Windows新候选；旧包不能替代。没有完成客户端可见UI全流程或客户试用。
- 上述测试失败需按风险修复/复测。当前只完成服务端内网部署与限定验收，不关闭完整产品Goal、CP-06/M3或UAT。

故障止损仅操作本项目：`docker stop yike-ai2026-app`；数据、秘密、源码、镜像与备份保留。没有可验旧运行镜像可回退，c41155b故障镜像不得当回滚版本。完整参数见服务器 `/opt/yike-ai2026/ops/release.json`与`start_application.sh`；后续构建必须显式固定新SHA并先迁移/授权/预检。

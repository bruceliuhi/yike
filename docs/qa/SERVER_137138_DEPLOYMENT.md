# 101.200.137.138 部署与测试交付

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

后续测试共因批次 `8718c0a` 已独立GO：[分组证据](../superpowers/plans/2026-09-11-http-recovery-reconciliation.md#后续旧夹具与接口期待共因)。仅测试依赖/期待修正，不更改本文件历史失败总数或部署SHA；最后本机curl仍无法解析yike.xingheai.net。没有新增服务器部署证据。

2026-09-11 CodexiMac 接续：三项原来原因未明的 HTTP／恢复失败已在 `b8c2679` 定位并完成限定修复与独立 GO，详见[三项接续证据](../superpowers/plans/2026-09-11-http-recovery-reconciliation.md)。其中短句 API 是生产缺陷，另外两项为测试权限/期待漂移。Mac 的 6 项通过不改写上面 Win 原始失败总数；**现有服务器镜像未包含短句 API 修复，须按新 SHA 重构部署**，不是客户端纯变更免构包情形。

- DNS管理员添加 **A记录：`yike` → `101.200.137.138`**。生效后为该域名单独签证书、配置受信HTTPS反代并实测Cookie/同源策略；不得复用只覆盖主域/www的旧证书。
- 需要意客专用模型Base URL、模型名、API key，在服务器秘密文件配置。评分/短句与搜索建议有各自显式配置，不借用其他项目密钥。未配置短信服务；当前是短期token登录。
- 真实四平台账号核验、采集、模型判断与生成、“多找类似”真实结果、逐项人工批准的发送、真实回复和转化数据均未验。外发仍关闭；公共来源新能力也未启用。
- 没有与该服务同SHA、绑定可用HTTPS的Windows新候选；旧包不能替代。没有完成客户端可见UI全流程或客户试用。
- 上述测试失败需按风险修复/复测。当前只完成服务端内网部署与限定验收，不关闭完整产品Goal、CP-06/M3或UAT。

故障止损仅操作本项目：`docker stop yike-ai2026-app`；数据、秘密、源码、镜像与备份保留。没有可验旧运行镜像可回退，c41155b故障镜像不得当回滚版本。完整参数见服务器 `/opt/yike-ai2026/ops/release.json`与`start_application.sh`；后续构建必须显式固定新SHA并先迁移/授权/预检。

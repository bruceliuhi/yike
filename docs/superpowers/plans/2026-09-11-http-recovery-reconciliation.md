# CodexWin 三项 HTTP／恢复失败接续

范围：定位 `SERVER_137138_DEPLOYMENT.md` 留下的简报、短句教练和前台采集恢复三项失败；不放宽生产权限、防重或确认规则，不重跑全仓。对应 V02-07/08/10，完整 V0.2 目标不缩减。

## 基线与复现

- CodexiMac 基线 `6cb7bb80ac234b02310cd3bc636d52663b5c93f8`，与当时 Gitee main 一致。
- 单独临时 PostgreSQL 16（仅 loopback、tmpfs、合成用户），各测试继续使用非 owner、非超级用户、非 BYPASSRLS 的运行角色；未触碰既有测试库或生产服务。
- Python pytest 启动真实 Uvicorn socket，Node 24.19.0 运行普通 service client 与实际协议层。初次只运行三份 Python 文件：**3 failed / 2 passed，7.68s**。
- 简报失败于 `service.profiles()`；短句教练失败于 `preview()`；采集恢复失败于重开 controller 后对旧 START 的返回值断言。依赖安装和 Node 调用均成功，不能归为缺少 Vitest。

## 前台恢复

旧测试要求已 CLAIM 且上传结果未知的任务重新 START 返回原成功回执；当前 controller 对已执行代次拒绝再次启动，符合已有防重单测及客户端“核对原上传”的独立入口。修改测试期待明确拒绝，并在恢复前再次检查 START/CLAIM、来源启动/停止和上传调用数量均未增加；不修改生产 controller。

后续仍通过 RECOVER 查询原批次回执并 FINISH。原测试保留：中文正文逐字回读、一个任务/批次/观察、仅 START/CLAIM/FINISH、来源与上传各一次、恢复不重新采集、加密日志和清理断言。

- 修正后该 HTTP／受限 PG 测试 **1 passed，3.50s**。
- 现有 controller 定向单测 **44 passed，376ms**，包含已 CLAIM 以及缺本地 CLAIM 但服务端代次已增加时拒绝重采。

## 简报与短句接口

- 简报：`PilotStore.list_profiles → read_references` 在受限测试角色下读取 `pilot_material_profile_references.reference_id` 失败（`InsufficientPrivilege`），对外为 HTTP 500。该夹具只装部分授权，漏掉现有生产清单中的 `grant_materials.sql`；仅补测试夹具使用这份已有授权，并保留受限角色直接读取检查。不改生产授权文件。
- 短句：原 HTTP 请求未带 `materialReferences`，`_body` 第一次验证后用 `model_dump()` 将缺省字段补成显式 `null`，service 第二次验证因此报 HTTP 422 `invalid_request`。生产修复仅为 `model_dump(exclude_unset=True)`，与服务内部现行序列化方式一致；不把显式 `null` 当作缺省接受。
- 新回归先观察缺省字段测试失败，再验证 preview/generate 两种 schema 对缺省、显式空列表、非空材料引用和显式 `null` 的行为。普通 HTTP 链继续验证预览后确认、生成及重放仅调用一次模型；模型为合成实现。
- 两份 Node 联验仅新增失败时的 HTTP 状态和格式受限错误码诊断，不记录原响应正文、请求内容或凭据。

## 证据边界

最终合并验证：三份原 Python 文件 **6 passed，8.07s**（包含新增序列化边界回归及三个实际 HTTP 子进程，均未跳过）；TypeScript `tsc --noEmit` 通过。未跑全仓、未重新构包。与首次 3 failed / 2 passed 对照，不和前面各轮结果累加。

这是 Mac 上的 HTTP／受限 PostgreSQL 与客户端协议联验；采集来源、模型、业务样本及登录均为测试夹具，不代表真实平台、生产 TLS、Windows 安装包或客户试用。不得覆盖 Win 原失败总数或把未重测项标绿。部署仍以服务器独立证据为准。

本批修改 `pilot/short_coach_api.py`，属于服务器镜像输入变化。已有 `6832482` 镜像不包含本次修复；之前“客户端变动无需重构服务器”的结论不适用于本批。后续部署须绑定新源码 SHA 重构、定向核验后切换，不能把 Git 推送写成服务器已更新。

独立架构/代码/质量复核：非实现者 `material_reference_architecture` 只读审核源码提交 `b8c267928a8ad4c023c0878c01afdc90c74cf21d`，结论 **GO，无阻断 P1/P2**。复用上述绑定版本证据，未重复测试。临时 PostgreSQL 容器已停止并销毁 tmpfs 合成数据，临时依赖软链接已移除；未删除既有测试库、依赖目录或生产数据。

## 后续：旧夹具与接口期待共因

基线 `747872a`。本批只改测试，不改产品源码、生产授权脚本、锁定依赖或镜像输入；不能据此宣称 Win 原报告中的 85/5 项已逐条关闭，因为原报告没有提供完整 nodeid 对照。

### 定位与最小修正

- 搜索建议单项先复现 `suggestion_store_unavailable`，数据库确认 `suggestion_app` 无引用元数据 SELECT；夹具补装生产清单已有 `grant_materials.sql`。
- 导入原子性先在 `save_profile → read_references` 复现 `InsufficientPrivilege`，补资料授权后进一步发现商机列表需要结构化跟进读取。仅补已有 `grant_materials.sql` 与 `grant_structured_followups.sql`，继续使用受限应用连接；没有关闭 RLS 或授予全库权限。
- 候选审核及 HTTP 的旧共享夹具同样漏这两份已有授权。先复现引用校验/候选列表失败，修正后才显露 OPEN 期待冲突与商机列表权限失败；分层修正，不将 HTTP 500 当无商机。
- 三处成功新纳入断言改为 OPEN：当前生产代码仅在近期有效 OPEN 核验、有联系路径、明确人工 INCLUDE 且首次创建时传播该状态。普通导入默认 UNVERIFIED、旧 BLOCKED 及重复纳入不复活规则不改；已有相关反例在下述 67 项通过范围内。
- 会话精确响应期待补服务器身份解析的 `account_scope={id: 原租户, version: 1}`，没有改成只比较部分字段。
- 采集器锁与 XHS 应用后哈希测试绑定完整有序 0001/0002/0003 清单，原字节哈希校验保留。使用已有 `/tmp/yike-mediacrawler-clean` 中固定上游提交，测试只克隆到临时目录，不改源、不下载。
- 搜索建议真实子进程的合成模型响应补现行严格 strategy 字段，引用逐字来自原画像；真实子进程协议不改，不将该合成响应当实际模型效果。

### 按批证据，不累加为一次全绿

| 验证范围 | 结果与说明 |
|---|---|
| 搜索建议与导入两文件，首次补资料授权后 | 72 passed / 2 failed，12.00s；搜索建议 69 项全部通过；两失败继续定位到导入列表缺结构化跟进权限。故意传入错误模型字段产生一条 Pydantic serializer warning，未屏蔽 |
| 导入、候选审核及 HTTP、完整策略 HTTP、会话单项 | 67 passed / 7 failed，52.51s；导入五项、会话、完整策略链、原文/防重/负面状态反例通过；七失败均在候选 HTTP 商机列表，缺结构化跟进读取授权 |
| 最后仅重跑受该授权修正影响的候选 HTTP 文件及两个审核单项 | 13 passed，16.58s，0 skipped；不重复前面已通过的长事务/并发组 |
| 锁清单、XHS 应用后文件哈希、真实搜索子进程三个选择器 | 3 passed，1.25s，0 skipped；最初两项 RED，XHS 起初未指定本机源而跳过，后以固定源补验并最终合并验证 |

真实 PostgreSQL 16 使用本批独立 tmpfs 容器与三个专用测试库，未操作既有数据库或生产服务。本批不跑全仓、不构包；没有真实平台或模型请求、Windows 安装、HTTPS 或客户证据。仍需接续同版本部署/Windows及跨行业真实闭环，不以修正测试替代完整产品目标。

独立非作者复核绑定 `8718c0a29cf499e6a051b0a4508eed5e4d9743ce`，`material_reference_architecture` 结论 GO，无阻断 P1/P2，未重跑测试。本批临时容器已停止，tmpfs测试数据销毁，既有库不变。同期本机对 `https://yike.xingheai.net/healthz` 的限时只读请求返回 curl 6（无法解析主机）；这是本机观测，不是权威 DNS 管理记录，不证明服务端健康变化。

### 镜像布局夹具接续（基线0bb4402）

当前Mac实测该布局测试在构造应用之前失败：固定COPY白名单遗漏现Dockerfile已有的 `app/__init__.py app/model_contract.py ./app/`。仅补精确三元组，保留其他未知COPY拒绝、隔离子进程导入/无网络启动与规则摘要断言；不修改生产镜像。修正后 `python -m pytest -q tests/test_pilot_runtime_container_layout.py tests/test_deploy_contracts.py` 为5 passed / 1.09s、0 skipped，diff check通过。此为Mac测试夹具修正，不覆盖Windows原WinError10106或其他全量失败；沿用32c9c0c服务候选，不重新构包。

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

# R3 候选代码独立审核

审核日期：2026-09-09。审核对象：**`10ab8b6cf3a9b29aa72fcdef23cd09a7b63c22e9`**。开始审核时 HEAD 与该提交一致，工作树干净。本次只新增审核记录，没有修改实现或重新运行全套测试。

## 结论与准入范围

**本审核范围内未发现新的 P0/P1 阻断，可将本轮实现、设计依据和验证资料提交 Gitee，作为 R3 前端与 macOS 候选交付。**

该结论适用于已记录的客户 pilot 接口、前端工作流及其明确的未接通状态。平台真实采集、持续监控、发送/回复、Windows 安装器和 CP-06 生产环境仍按各自门禁验收。页面和可用分支测试不构成这些服务已上线的证据。

## 独立性与检查范围

审核者没有编写下列被审实现：`pilot/ui_api.py`、Profile、Connections、Settings、Candidates、TaskWizard（含任务返回校验）、Workbench、`operationLedger.ts`、`hooks.ts`，以及所依赖的 renderer 服务映射和应用身份边界。

本审核**排除审核者自己编写的 Electron 主进程/预加载、打包脚本和 Tasks 监控详情实现**；这些实现由另一位审核者交叉检查。包的输入摘要一致性属于机械证据核对，不作为自审安全结论。审核者此前为 TaskWizard 和发送确认编写的隔离测试，也不被当作独立实现审查的替代品。

| 范围 | 实际核对与依据 |
| --- | --- |
| UI API facade | [严格输入模型](../../../pilot/ui_api.py#L20)拒绝额外字段；[会话身份](../../../pilot/ui_api.py#L113)验证签名并由服务端查询租户；[画像列表](../../../pilot/ui_api.py#L154)同时设置租户上下文和 SQL 租户谓词。保存、确认、商机、跟进复用既有 store；没有接受 renderer 的租户/管理员字段。错误不回显凭证或输入，并设 `no-store`；保留原 Origin 中间件。 |
| Profile 与资料 | [保存/确认](../../../desktop/src/renderer/pages/Profile.tsx#L203)等待实际服务结果，确认状态异常不显示已确认。资料恢复有字段、枚举、长度和文件大小校验；TXT/Markdown 读取有代次失效保护，资料明确保存为本机草稿。 |
| Connections | [连接与检查](../../../desktop/src/renderer/pages/Connections.tsx#L63)用代次丢弃过时响应；打开登录窗口不等于连接成功，检查结果须匹配当前平台并返回 `CONNECTED`。重连返回路径使用受限内部路由。 |
| Settings | [退出流程](../../../desktop/src/renderer/pages/Settings.tsx#L87)重查会话后清普通草稿；远端注销未知时保留明确提示。诊断只取版本、平台和服务配置状态。导出、恢复、设备绑定、更新不生成虚构成功结果。 |
| Candidates | [前置条件](../../../desktop/src/renderer/pages/Opportunities.tsx#L841)绑定已确认画像、候选/来源版本、五项证据和来源状态，拒绝样例入库。[提交与核对](../../../desktop/src/renderer/pages/Opportunities.tsx#L1006)检查请求 ID、候选 ID、回执及人工复核快照，一条不确定即停止继续批量写入；未知结果走只读核对。真实 adapter 仍未接通。 |
| TaskWizard | [返回校验](../../../desktop/src/renderer/pages/TaskWizard.tsx#L41)核对任务标识、名称、模式、平台集合及可选画像版本；[启动流程](../../../desktop/src/renderer/pages/TaskWizard.tsx#L294)在最终预检后再次检查当前配置与挂载状态，先持久化未决请求，再调用启动，未知/错配结果保留锁。人工词项、草稿返回与异步建议使用现有版本和请求代次保护。 |
| Workbench | [状态来源](../../../desktop/src/renderer/pages/Workbench.tsx#L14)区分读取失败、待核验和已确认；未接通队列明确说明。公开样例单独展示，不伪造成客户待办、运行量或业绩。 |
| 用户与异步数据边界 | [资源 hook](../../../desktop/src/renderer/app/hooks.ts#L11)按身份、请求代次和挂载状态接受结果，身份变化时不会先展示旧数据；[应用内容](../../../desktop/src/renderer/app/App.tsx#L490)按用户重建。普通草稿恢复检查 JSON 结构，清理会阻止旧 setter 回写。 |
| 未决操作记录 | [独立 ledger](../../../desktop/src/renderer/app/operationLedger.ts#L89)按用户存储不透明标识与状态，迁移旧记录；[清普通草稿](../../../desktop/src/renderer/app/hooks.ts#L130)保留操作锁。持久化失败会在实际启动/发送前抛错，迟到结果只更新原用户记录，不将清草稿或退出作为解锁依据。 |

## 候选绑定与已有验证

- 对 `mac-package.json` 中 **46 项构建输入**逐项读取候选提交 Git blob 并重算 SHA-256，**0 项不匹配**。输入清单摘要为 `a645ca9b4cebf207523ddffd779d743731ac6fd109c877f11ce428400f448e35`。
- 冻结后已实际运行的桌面测试为 **24 个文件、216 项通过**；本次最终代码审核没有重复执行。结果及包资源摘要见 [mac-package.json](mac-package.json)。
- 主任务提供的 pilot 定向测试为 **62 passed**；隔离本地 PostgreSQL 的 **22 项**检查包括非超级用户、无 RLS bypass、跨租户拒绝、画像/跟进持久化和外部 Origin 拒绝，见 [数据库/API 记录](postgres-api-check.json)。本审核核对了相关实现与记录，未将其扩大为生产验收。
- 主任务完成真实 `.app` 可见启动、批量词填写、保存、三步骤阻断、退出和重新打开，见 [人工验收记录](IMPLEMENTATION_REVIEW.md)。这些属于运行证据，与本次独立代码审查分别记录。
- 旧 SQLite 实验 `tests/test_web.py` 的 5 个 `D04_FACT_OUTSIDE_RUN_WINDOW` 失败，已在同 Python 环境的隔离基线和当前代码复现一致；相关旧业务无差异，见 [基线核验](legacy-web-baseline.json)。

## 保留的实际边界

1. [真实 renderer adapter](../../../desktop/src/renderer/services/client.ts#L181)仅连接当前 pilot 的会话、画像、客户商机和人工跟进。候选复核、平台连接、建议、采集/监控、发送和激活等返回明确不可用；隔离 fixture 的成功分支不能被称为实接成功。
2. 本机操作记录用于阻止普通 UI 重复提交，不能替代服务端幂等和渠道结果对账。候选复核的跨页面恢复也依赖未来服务返回持久化回执；对应约束已写入 [候选契约](../../../desktop/src/renderer/domain/candidates.ts#L126)，接入时须与真实接口共同验收。
3. 旧签名访问凭证是无状态 bearer token；退出清除当前 Cookie，不具备全局 token 撤销。Vite 跨端口代理写入仍未支持，本地浏览器实接按同 origin `/app` 方式验收，详见 [打包与联调说明](../../../desktop/docs/PACKAGING.md)。
4. Windows 安装/卸载和系统缩放、分发签名、公证、正式域名/HTTPS、生产数据库 ACL、备份恢复和回滚均不由本次审核替代；继续保留原交付门禁。

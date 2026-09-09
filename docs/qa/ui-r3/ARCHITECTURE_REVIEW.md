# R3 前端与 Mac 候选架构审核

- 审核日期：2026-09-09。
- 审核对象：`10ab8b6cf3a9b29aa72fcdef23cd09a7b63c22e9`，分支 `codex/ui-r3-desktop`。
- 审核者：独立架构 Agent `/root/design_handoff_architecture`。
- **结论：PASS，可按用户已授权范围提交前端与 macOS arm64 候选客户端。** 本审核范围未发现尚未修复的 P0/P1。此结论不扩大为完整获客业务可售、生产上线或 Windows 验收通过。

## 独立范围与排除项

本次只读审查非本审核者编写的 Electron main/preload、受控资源协议、网络与 IPC 白名单、Forge 配置、B 的持久操作记录，以及主线工作台/监控/发送确认的关键边界；最后仅新增本报告。没有重新执行整套测试、创建真实业务操作或修改运行源码。

明确排除本审核者自作的 `pilot/ui_api.py` 及注册/测试、Login/Profile/Connections/Settings 页面、CandidatesPage 与候选契约，以及 TaskWizard 的启动响应验证修复和其测试。上述内容由其他 Agent 独立交叉复核；本报告不能充当其独立通过证明。P07 及其他自作页面的视觉也不在本次独立范围内。

## 核对结果

| 审核项 | 证据与判断 |
|---|---|
| Renderer 权限 | [windowPolicy.ts](../../../desktop/src/main/windowPolicy.ts) 保持 `sandbox/contextIsolation/webSecurity=true`、Node 集成关闭、webview 关闭。只承认当前主窗口、主 frame、精确 `yike://app/index.html` 文档；hash 仅用于内部路由。 |
| 协议与资源 | [rendererAssets.ts](../../../desktop/src/main/rendererAssets.ts) 从 Vite manifest 建允许列表并检查真实文件路径。协议拒绝非 GET/HEAD、编码/路径穿越和允许列表外资源；CSP 保留 `connect-src 'none'`，不通过放宽 CSP 接业务服务。 |
| IPC 与外部动作 | [main.ts](../../../desktop/src/main/main.ts)、[preload](../../../desktop/src/preload/index.ts) 只暴露固定五个能力；每个 IPC 都核验发送者。阻止弹新窗、外部导航、重定向、webview、权限申请和下载。外链仅无内嵌凭据的 HTTP(S)，剪贴板有类型/大小限制，不提供任意 IPC、Shell 或文件读取。 |
| 服务边界 | [servicePolicy.ts](../../../desktop/src/main/servicePolicy.ts) 固定 operation、路径、方法及严格 payload，renderer 不能传任意 URL、头、租户或数据库凭据。[serviceClient.ts](../../../desktop/src/main/serviceClient.ts) 固定 HTTPS origin；HTTP 仅未打包且显式允许的开发回环。拒绝重定向、非 JSON 和超大响应，有执行超时与有界串行队列。 |
| 应用会话 | 网络使用独立无 `persist:` 的 Electron session，Cookie 不给 renderer；登录/退出串行，防止尚未完成的登录在退出后恢复 Cookie。退出请求失败仍执行本机会话清理并向调用方保留错误。此处核对桌面边界，不对本审核者自作的认证 facade 自审。 |
| 操作记录 | [operationLedger.ts](../../../desktop/src/renderer/app/operationLedger.ts) 将任务/发送待定记录与编辑草稿分离，按用户隔离，仅存 ID 与状态。先可靠写盘再允许外部动作；损坏、读写失败或迁移失败不静默置空放行。旧 sessionStorage/内存记录先迁移再删除；清草稿保留旧锁；迟到结果只更新原用户。读取了相应迁移、清草稿、切号、存储异常测试，未重跑。 |
| 工作台与监控 | [Workbench.tsx](../../../desktop/src/renderer/pages/Workbench.tsx) 已把未接队列明确显示为不可用，待联系标签中的普通商机列表有中性说明，不再由商机列表推断回复/候选为空。画像/连接/任务读取失败显示待核验。[Tasks.tsx](../../../desktop/src/renderer/pages/Tasks.tsx) 已要求读取成功后显示业务空态；本机草稿独立。平台数量/时间缺失不补零，任务操作刷新服务状态，不在本机造运行成功。 |
| 发送确认 | [Outreach.tsx](../../../desktop/src/renderer/pages/Outreach.tsx) 保留全文快照、账号/用途/对象/版本指纹、核验 token 过期、显式用户确认与发送前二次核验；未决尝试保守锁定。默认核验/发送适配器仍不可用。服务端持久幂等、实际来源版本与渠道回执查询属于接通前置，未把本机 ledger 或 `{status}` 当完整对账。 |
| 打包边界 | Forge 使用 ASAR、固定 CJS 主进程/预加载、现有品牌资源、Mac ZIP 与 Windows Squirrel 配置。代码签名、公证、自动更新与 Windows 构建/安装没有被宣称完成。 |

## 提交与包证据绑定

审核开始时 `git rev-parse HEAD` 为上述 SHA，工作树干净。对 [mac-package.json](mac-package.json) 中列出的 46 个构建输入重新计算 SHA-256，并按记录配方重算清单摘要，结果为 **46/46 一致、0 个变更、manifest 一致**。这是字节核对，不是对排除项自作代码的独立功能审核。

| 对象 | 实际核对 |
|---|---|
| 输入清单 SHA-256 | `a645ca9b4cebf207523ddffd779d743731ac6fd109c877f11ce428400f448e35` |
| 本机 `app.asar` | 文件存在；重新计算为 `fb970401b4a117e4ca0be599d9fd2d044e5b7c85e8f43d783b0cfd1607c17522`，与构建记录一致 |
| 本机 Mac ZIP | 文件存在；重新计算为 `f7719bb9c809b38d47000a04b5eb04cac84a3eb7ef3fb2a3d7460e72f7588b1a`，与构建记录一致 |

已阅读主线 [实现与可见验收记录](IMPLEMENTATION_REVIEW.md)、[交付记录](../../UI_R3_IMPLEMENTATION.md) 和包证据：216 项前端/桌面测试、实际 Electron 网络冒烟、ASAR 资源/包内运行检查，以及 Mac 可见启动、真实填写并保存本机草稿、三步配置、缺项阻止启动、退出和重新打开。上述运行由主线执行，本审核没有重新操作 CUA，也不把截图当成所有后台状态通过。

[PostgreSQL/facade 22 项记录](postgres-api-check.json) 属于隔离本机数据库证据。该链包含本审核者编写内容，独立 API/数据库结论交其他审核者；本报告仅核对交付说明没有把它扩大为生产 CP-06 或真实平台收发。原 SQLite 实验套件的 5 项既有失败已保留基线证据，未被记录为新增 UI 实现通过项。

## 保留边界

1. 用户已决定 Windows 在其电脑后续手动执行；当前 Windows 安装包未构建、安装/卸载与 100%/125%/150% 系统缩放未验收。它不是本次获授权前端/Mac 候选提交的等待条件。
2. 真实平台连接、采集/监控执行器、AI 建议、短信/试用、外发与回复仍未接通；生产 HTTPS、数据库 ACL、备份恢复、回滚及手机验收保留 CP-06。没有以缺接口为由删减完整 V0.2 目标。
3. 客户分发签名、公证、自动更新尚未完成；构建开发链 17 个 high 依赖审计项在 [依赖记录](dependency-audit.json) 如实保留，运行时依赖报告为 0。此处不把开发链审计摘要当成已修复或完整供应链保证。
4. 源码若在该 SHA 后变更，需对变更重新复核并核对构建输入/产物；仅追加审核文档不要求重复构建同一源码。

本次可以提交已授权的前端代码与 Mac 候选交付记录；不可据此宣称 Windows 已交付、真实获客闭环已验收或生产已上线。

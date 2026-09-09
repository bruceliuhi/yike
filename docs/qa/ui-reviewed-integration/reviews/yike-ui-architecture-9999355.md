# 冻结候选架构审核

- 审核日期：2026-09-10。
- 候选目录：`/tmp/yike-ui-review-20260910`。
- 候选：`99993552f1559681c8f671a57096ec23d4e9095b`。
- 基线：`a77e5828de9ecb0f3c9b60dfcebf56c96685d9bc`。
- 结论：**NEEDS_FIX，当前 SHA 存在 1 项 P1 集成边界问题，暂不作无条件批准。** 其余本轮新增范围未发现另外的 P0/P1。后续修复及主线程正在推进的原始候选接入不属于此结论。

## 范围与独立性

核对全部 105 个变更文件的差异范围，对源码、测试、构建脚本和文档作阅读审查；重点为会话草稿退出保护、P09 画像谱系、P20 规则版本与旧草稿兼容、认证连接读取及设备/连接版本隔离、Windows 源码和运行实例绑定。QA 图像只核对其用途与证据记录，未重新执行浏览器或把图像存在当成全状态视觉通过。

本审阅者曾参与 P20 初版日程模型、校验和界面实现；本报告对 P20 只检查本次整合关系及执行合同，不作为该部分唯一独立代码批准。主线程已明确由 Peirce 独立代码复核、Hubble 质量复核覆盖 P20。独立代码重点为主线程的退出保护/导航/连接接入、Peirce 的 P09 及另一作者的 Windows 脚本。

候选内未修改任何跟踪文件；`desktop/node_modules` 是现有测试依赖软链接，不属于被审源码。测试只运行于冻结目录，不使用原工作树源码。

## 阻断：注册身份在旧连接解析器中被剥离

**P1 — `desktop/src/renderer/domain/connectionDisconnect.ts:42–63`，调用影响见 `desktop/src/renderer/pages/connections/useConnectionDisconnect.ts:105、110、194–218`。**

新 `disconnectTarget()` 在第 66 行拒绝带 `registration` 的记录，但 `checkedDisconnectConnection()` 使用未包含该字段的 `z.object`，在第 60 行解析时会静默剥离设备、连接编号和版本标记。旧断开预检只继续比较平台、账号与 CONNECTED，因而可把另一个设备/版本的登记记录当成旧平台级账号并继续 `service.disconnect(platform)`。核对未决请求时，`inspect()` 也可能把剥离后的记录回写为无登记身份的旧连接行。不能依赖默认 adapter 目前 unavailable 来保证将来可用契约的身份安全。

已直接用 Node 24.19.0 导入冻结源码复现，输入为同平台/同账号、`TEST-device2`/连接 v2 的登记记录。结果为：

```json
{"directTargetRejected":true,"registrationPreserved":false,"parsedTarget":{"platform":"xhs","accountId":"TEST-account"}}
```

该实证来自本次工具输出 `7b0cc2`。最小修正：旧解析入口在任何 schema 剥离之前拒绝带 `registration` 的值；测试应覆盖 CONNECTED 预检不派发、DISCONNECTED 核对不回写旧连接行，以及已有 ACK 未决记录不会据另一设备的状态核销。应对修复后的独立子提交复核，不将修复计划当成此 SHA 已修复。

## 其余架构判断

1. **会话草稿退出：可接受。** 退出事件同步读取 sessionStorage 和内存中的任务/任务库/模板，包括页面已卸载的草稿；显式清除的墓碑不会被存储失败复活。仅窗口退出受保护，内部导航仍保留会话内容。Electron 原生对话框默认继续编辑；放弃才允许卸载。文案明确关闭客户端清除会话草稿，没有冒称跨重启持久化。此保护没有删除独立的未决操作账本。
2. **P09 画像版本：可接受。** `Profile.id` 继续表示版本行，新增实体 ID 只读取真实 `profile_id`。比较先绑定任务版本，再限制同一业务实体唯一已确认版本，不按名称、最大版本或其他业务猜测。缺谱系、重复确认、版本逆序、读取失败均保留待核对。保持历史只确认当前观察结果，换用户/空间、任务绑定或新版结果后失效；不会变更或重启原任务。
3. **P20 整合合同：可接受，独立代码批准另见前述分工。** 新 `policyVersion=1` 纳入持久化和指纹，旧缺省草稿保持原 hash，显式采用才变更。跨日窗口、端点、DST、离线不补跑均作为配置约定说明；执行服务未声明 `scheduleContractVersion=1` 时，在页面、启动预检和写入未决记录前阻断。未新增 scheduler，没有据此宣称真实按规则运行。
4. **认证连接列表：除上述旧解析交叉路径外可接受。** 固定只读 IPC/HTTP 路径由服务端会话解析用户，renderer 不能提交 tenant 或任意 URL/头；解码保留连接、设备和版本，重复连接 ID 拒绝。登记 CONNECTED 不产生执行能力；任务账号选择与启动检查排除登记记录。列表刷新/失败/换空间隐藏旧数据；多设备详情按精确连接 ID 显示。平台登录、能力核验及版本化写入继续明确未接通。
5. **Windows 绑定：架构可接受，实机未验收。** 构建要求完整预期 SHA、干净工作树和实际跟踪文件字节一致；执行输入目录额外检查忽略文件/链接，前后清单漂移不产生成功。自动阶段与人工验收分别记录。实例核对检查 EXE/ASAR 摘要、可见主窗口 PID 和启动时间，不能把旧实例算成本次包。`IDENTITY_VERIFIED` 只证明运行文件身份，不证明安装路径、安装器行为、缩放、重启或卸载，文档保留了这一边界；这也不是签名供应链证明或恶意本机篡改防护。

## 本次独立验证与证据使用

Node 24.19.0，从候选 `desktop/` 运行：

```sh
vitest run tests/ui/session-draft-exit.test.tsx tests/ui/task-profile.test.tsx tests/ui/connection-registry-client.test.ts tests/ui/connection-registry.test.tsx tests/ui/navigation.test.tsx tests/windowsSourceBinding.test.mjs tests/windowsBuildEvidence.test.mjs
```

实际 **7 文件、98 passed、4 skipped**（工具输出 `7283b1`）。跳过的是 Windows 主机/架构相关路径，不计为执行；未运行 PowerShell 或 Windows 可见验收。这些绿测未覆盖上述已实证的 registration 反例，不能覆盖阻断。

另逐项将 `docs/qa/ui-connection-registry/candidate-local.json` 的 279 项输入 SHA-256 对照冻结目录，**279/279 一致**（`50e43f`）；`git diff --check` 通过。QA 的 924 passed / 21 skipped 全量及其后 43 passed 定向，均明确是主线程原始记录，本报告未重跑该全量、不相加计数。候选输入一致只绑定既有构建盘点，不改称干净提交构建前后证明，也没有重新打开其 ASAR 或运行 Mac 包。

## 残余限制

- 本 SHA 仍需先修复并独立复核上述 P1；主线程后续变更另行绑定。
- 当前实际 HTTP/IPC 契约读取测试不等同于真实受限 PostgreSQL + HTTPS 登录贯通的连接列表验收；本轮未测真实客户、平台账号或发送。
- Windows 新候选构建、PowerShell 新入口、安装/卸载、100%/125%/150% 缩放和连续拖动仍需目标主机证据。历史 Windows 成功不能继承为本候选通过。
- 原生导出系统窗口、全部页面状态的可见操作与字体/像素一致性不能由当前自动测试或截图集合宣称完成。现有 QA 文档已明确这些限制；本报告不关闭完整 UI Goal，不宣称生产上线、计费或平台获客闭环完成。

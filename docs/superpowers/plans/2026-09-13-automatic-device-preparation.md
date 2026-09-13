# 自动连接准备：设计与实施

> 按用户 2026-09-13 确认执行“后台自动处理、前台隐藏”。使用 writing-plans、TDD 和独立审核；本批只做定向验证与一次候选构包，不重复既有全量验收。

**Goal:** 已登录客户无需勾选或输入设备信息，即可进入平台连接；重启后自动恢复。底层设备身份和执行授权不取消。

**Architecture:** AppProvider 在已确认的账号会话下挂载独立连接准备组件，调用现有受限 IPC。成功隐藏，准备中给简短状态；失败给一次显式“重试”，技术状态保留诊断。主进程合并同一会话并发准备，仍通过既有登记 journal、密钥 vault、服务端身份挑战确认 READY。账号变化、撤销、未知回执不能绕过。

**Tech Stack:** Electron / TypeScript / React / Vitest。

## 已批准设计

- 不采用仅隐藏按钮（仍阻断平台）；不采用禁用设备身份（破坏隔离与执行授权）。采用自动准备并隐藏正常技术入口。
- UI 不传 userId/deviceId/签名；身份由主进程新鲜 session.get 决定。未登录不准备。
- 新启动复用原登记和密钥、执行新证明；不抄写 READY，不生成替代设备解决撤销或密钥异常。
- 初次调用无 retry flags；未知回执不循环重发。用户点“重试”时仅针对观察到的未知类型重试同一原请求。密钥缺失/不匹配或撤销只提示支持，不自动重绑。
- AppProvider 的准备组件以服务、账号/空间、会话变化隔离异步结果。准备期间不开放依赖设备的操作，普通导航/业务资料不应被长期锁住。后台请求有超时；迟到结果不能覆盖新会话。
- 正常设置页移除核验入口、勾选及本机编号；脱敏诊断保留状态码。商业授权和平台授权保持独立，不宣称设备准备等于平台登录。
- 不修改服务端权限模型，不自动发送，不代办平台验证挑战，不改商业激活规则。

## Chunk 1: 自动准备与界面

### Task 1: 主进程并发准备

Files: `desktop/src/main/deviceIdentityController.ts`, `desktop/src/main/main.ts`, `desktop/tests/deviceIdentityController.test.ts`, `desktop/tests/deviceIdentityMain.test.ts`。

- [x] 增加自动准备入口的回归测试：同 epoch 同选项合并；不同会话不能拿旧结果；未登录/撤销/密钥错误仍拒绝；未知结果不自动加 retry flags。
- [x] 执行 vitest 定向测试确认新测试先失败。
- [x] 实现 `prepareForUse(input)`，复用 `prepare`，只共享同 epoch、同 retry 选项的 pending promise；IPC 使用该入口，原 prepare 合同保留。
- [x] 定向回归 controller/session/journal/key vault/main/worker scope/execution，确认不会更改执行前授权。

### Task 2: 用户界面（独立子任务）

Files: 新增 `desktop/src/renderer/app/DeviceConnectionPreparation.tsx`；修改 `context.tsx`、`pages/Settings.tsx`、相关错误文案；对应 UI tests。

- [x] 先写失败测试：登录后自动准备、未登录不调用、重启 remount 恢复、成功不显示核验操作、失败简单重试、撤销不可重绑、账号变化忽略迟到响应、准备期间平台操作不会误执行。
- [x] 用现有 DeviceIdentityApi 实现，不添加身份载荷。用有限等待处理 BUSY，不无限轮询；未知回执须用户点击重试。
- [x] 设置页正常区域移除手动核验；诊断只显示安全状态，不显示编号或密钥。旧隐藏入口测试改为新的业务合同，保留安全测试。
- [x] 跑 UI 定向测试与 `npm run typecheck`。

## Chunk 2: 集成与交付

- [x] 独立审核整个差量，先对照需求再审质量/边界；修复阻断再验证差量。
- [x] 运行 `npm test -- tests/deviceIdentityController.test.ts tests/deviceIdentitySession.test.ts tests/deviceWorkerScope.test.ts tests/deviceIdentityMain.test.ts tests/ui/settings.test.tsx` 及新增/受影响 UI 测试，保存真实计数。
- [x] 在 main 提交正常推送，固定源码版本构建一次 Windows 候选。Python/Chromium 依赖复用现有匹配运行环境；现行构包清单要求绑定新 SHA，已生成并验证离线 payload，不重新部署服务端。
- [ ] 安装并实际观察：保留账号/画像，重启无需设备勾选，平台连接可进入；平台本人验证及真实发送仍按用户授权边界执行。
- [x] 更新一份简短 QA 记录，明确候选版本与未完成验收，不将局部修复记为产品上线。

## 源码验证（2026-09-13）

- 主进程新增同请求合并先 RED 9 项；IPC 接线先 RED（第二调用 BUSY）；独立审核发现完成后/交付前退出的迟到 READY，独立复现并追加 RED 后修复。底层相关 370 passed / 0 skipped；最终主进程差量 133 passed。
- UI 自动准备初始 RED 19/20；服务生命周期与 BUSY 重试、弹窗内可访问恢复分别追加 RED 并修复。最终新增 27 项、UI 相关 73 项通过。
- 冻结差量整合：9 文件 194 passed / 0 failed / 0 skipped，`.runtime/auto-device-integrated-tests.json`；类型检查通过。上述集合有重叠，不相加。
- 独立 `auto_device_code_review` 对最终源文件摘要给出 GO，三个 P2 均关闭；GO 只允许提交与构包，不替代 Windows 实机/真实平台。主控制器 SHA256 `4beab8dac354dfe7001a640aa91676643917cd3040934c10ea44aa069838d145`，自动准备组件 `b7847bdc97175698247ddb6ea85fffb9102f665c224b5df79ee1c22642d72f8f`。
- 候选 3ffddbd 已构包；旧版窗口无法被自动工具激活，未启动安装，等用户关闭后直接升级同一候选。完整坐标与真实未验项见 [Windows QA](../../qa/WINDOWS_SYNC_20260912.md)。服务端 API/Python/runtime 字节未修改，不因本批重新部署服务端或重跑全量业务验收。

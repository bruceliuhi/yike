# P18 管理操作可见验收增量

2026-09-10。本轮没有修改产品代码。工作区基线为 `c23380ee61b5dd0e9183b0905067cd0d9b0007ef`，浏览器使用已有冻结源 `b8b82367b34af24da218dba3796a8945d667aaa6` 的 TEST 构建。当前主线与该冻结源的本轮管理组件无变化。完整 UI Goal 保持进行中。

## 范围与方法

通过 Codex 内置浏览器实际点击 Settings 页面与管理弹窗；路径为 `http://127.0.0.1:18794/b8b8236/?scenario=P18&state=populated&management=lifecycle#/settings`。操作真实前端组件，服务和保存回执来自 [TEST 管理生命周期](../../../desktop/tests/visual/MANAGEMENT_RECOVERY.md) 的隔离内存夹具。

没有写出导出文件、恢复客户库、下载安装程序或调用后台。页面“保存完成”仅表示处理了 TEST 保存回执。不得以本记录替代原生文件保存、实际恢复、更新签名校验或 Windows 实机验收。

## 实际走查

| 状态 | 观察结果 | 证据 |
|---|---|---|
| 导出取消 | 保留弹窗，不提示已保存；TEST 控制区说明取消且未创建文件 | [01](01-export-cancel.txt)、[02](02-cancel-receipt.txt) |
| 导出保存失败 | 显示“文件未能保存，请检查保存位置后重试”，重试按钮保留 | [03](03-export-error.txt) |
| 导出 TEST 已保存 | 收到 saved 回执后显示“客户数据导出文件已保存” | [04](04-export-test-saved.txt) |
| 下载执行 UNKNOWN | 显示待确认操作；当前执行、重新预览及回退预览禁用 | [05](05-download-unknown.txt) |
| 关闭弹窗后取消 PENDING | 原待确认记录与核对/取消入口保留 | [06](06-cancel-pending.txt) |
| 清除本机草稿 | 清草稿完成，下载待确认记录仍保留 | [07](07-after-clear-drafts.txt) |
| 核对仍 UNKNOWN | 保留待确认操作 | [08](08-lookup-unknown.txt) |
| 将 TEST 取消回执选为 CANCELLED | 仅改变下一次回执，不直接清除待确认记录 | [09](09-receipt-selection-still-locked.txt) |
| 再次取消收到 CANCELLED | 显示“原操作已取消”，移除待确认记录 | [11](11-cancel-confirmed.txt) |
| 终态后重新打开检查更新 | 可再次检查影响并预览 | [12](12-repreview-unlocked.txt) |

可见走查证明按钮、提示与待确认状态的变化；请求 ID 绑定、幂等及不能重复执行的契约由组件和服务测试补充，不从 DOM 快照推断请求次数。

## 截图与测试

[下载待确认截图](10-download-pending-1440.png) 已打开检查。实际 CSS 视口 1440×1024，DPR 约 1，文档宽 1440、高 1253；截图处于页面下方，可见待确认说明与核对/取消按钮，无横向溢出。它用于状态可见性检查，没有同状态设计参考配对，不能记作像素一致验收。临时视口覆盖已清除。

[定向测试日志](logs/management-tests.log)：3 文件、15 passed。执行 `managementRecovery.test.ts`、`managementRecovery-ui.test.tsx` 和 `isolation.test.ts`，覆盖恢复 UNKNOWN 重入、清草稿保留锁、取消未确认/终态、保存回执与隔离边界。没有重新运行全量或重新构建 Mac 包，本轮没有产品改动。

## 未完成与工具限制

恢复路径只打开了“备份与恢复”并点击文件选择，未完成选择 TEST 文件后的浏览器可见恢复链。访问原生 Codex 应用被工具拒绝：`Computer Use is not allowed to use the app 'com.openai.codex' for safety reasons.` 没有通过别名或系统脚本绕过。随后通过允许的浏览器 DOM 关闭弹窗并继续下载取消验收。恢复的组件测试通过不等于文件选择与真实恢复可见验收通过。

初次尝试用 18796 新端口启动 TEST 构建，被隔离入口限定的 18794 origin 拒绝；已关闭该临时服务。改为现有 18794 服务下的 `/b8b8236/` 子目录构建，保留原有根目录夹具。构建日志见 [首次](logs/visual-build.log) 与 [正确 origin 的子路径构建](logs/visual-build-allowed-origin.log)。未修改生产路由或隔离规则。

下一步仍需补齐恢复文件可见链、真实原生保存及服务回执验收，并继续其它页面未完成状态。Windows 安装/交互/缩放/卸载由用户手动执行并回传，仍未签收。

## 提交整合

收口时主线已前进至 `b7a4c51`，已快进保留。新增范围仅为采集器获取脚本、对应测试及集成说明，没有桌面差异；本次 UI 证据仍绑定上面的冻结源，不据此宣称真实采集验证通过。

[获取脚本契约测试](logs/incoming-fetch-contract.log) 为 1 passed，仅确认新脚本契约，不重复签收其作者的真实运行结果。限定质量复核见 [review.md](review.md)。

首次推送因远端新提交被拒绝后，正常合并 `ca1f28a` 成为 `fbcc171e002e976daabd6035aaa597d84654168f`，没有强推或冲突。新来件包含 P07 候选证据、人工来源核验、确认与原请求恢复，其作者验收见 [05G](../V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md)。这次已经存在 desktop 差异，旧截图、浏览器实例和 Mac 包仍绑定原冻结源，不追认为合并版。

合并后的本地 P18 定向回归仍为 [3 文件、15 passed](logs/management-tests-integrated.log)，类型检查 `tsc --noEmit` 退出 0（[原始空日志](logs/typecheck-integrated.log)）。这是新的限定回归，不能与前一批相加或替代 P07 作者的 Windows/全量记录。未重新构建 Mac 包，未把 Windows 浏览器 TEST 走查记作 Windows 安装包验收。

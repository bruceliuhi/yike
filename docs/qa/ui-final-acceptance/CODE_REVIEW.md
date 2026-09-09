# UI 最终验收：独立代码审核

审核人：Agent C。日期：2026-09-09。

**结论：独立范围 PASS，未发现未解决的新增 P0/P1。** 本报告绑定源码提交 **`58c8a7d3a8743f5f2eb9590e93ba8c2c66751fd9`**，比较起点为 `d2a68648570d6e89ea04a1babf7e96765d1b30b1`。写入报告前，已确认下列已审实现及相关测试与绑定提交无差异。

## 独立范围与作者边界

独立检查 A 编写的 P16 有界断开实现：`domain/connectionDisconnect.ts`、`pages/connections/useConnectionDisconnect.ts`、`DisconnectPanel.tsx`、`Connections.tsx` 接线以及 `connection-disconnects` ledger 校验；检查对应断开交互测试及 [接口限制](../../UI_CONNECTION_ACTIONS_CONTRACT.md)。同时独立检查主 Agent 在 TaskWizard P19 的 `onSettled` 清理旧错误这一行变更及其真实组件回归。

主 Agent 最初编写的 TermEditor 多行粘贴逻辑也经过 C 只读检查。C 发现“归一化后输入同值时，光标仍保留全选”的 P2；随后经主 Agent 授权，C 实现同值分支直接折叠光标并增加回归。**该窄修因此属于 C 自作代码，本报告不对其作独立批准。** 主 Agent 已报告独立复审该修复与回归通过；此处记录复核来源，不将其改写为 C 的独立结论。

排除 C 自作的 P07 持久复核恢复、P10 阶段/资料截止事实与筛选、相关 `candidate-reviews` ledger 和上述 TermEditor 同值修复；这些实现由其他 Agent 或主 Agent 独立复核。本报告不批准未列入范围的旧任务实现、后端、构建产物或部署状态。

## 结论依据

P16 在派发断开前再次核对当前服务端身份、平台和账号，要求仍为原账号且 CONNECTED。账号、用户或返回平台变化以及预检取消不会派发断开。正式派发前持久写入原用户 ledger，并重新读取同平台未决记录；持久读写失败不能绕过保护。重新连接入口也检查未决记录。

预检、断开回执和连接状态核对分别有 30 秒等待上限。取消等待、关闭弹窗、离页和身份变化不会声称撤销服务端请求。迟到的原 Promise 只可将原用户的原记录更新为 ACKNOWLEDGED，不改变新身份界面或显示成功。

解除记录必须同时满足原请求已 ACKNOWLEDGED，以及随后读到同平台 DISCONNECTED、账号为空或仍匹配原账号。单独读到未连接不能伪造原请求回执；仍连接、受限、过期、其他账号、错误平台或未知结果均不重发。清除普通草稿与重新进入页面保留未决记录，并提供只读核对入口。

P19 的新增 `action.setError("")` 位于已核对确定终态的回调中，随后仍清除原确认；REJECTED 继续增加配置版本并要求用户重新确认。回归检查了未知状态持续保留原启动记录，确定未执行后旧错误消失、确认复选框清空、启动按钮保持禁用，不自动再次启动或生成任务。

## 实际检查

执行目录 `desktop`，使用项目指定 Node 24。会话输出标识仅用于检索本轮工具结果，不是仓库内原始完整日志。

| 检查 | 结果 | 会话输出 |
| --- | --- | --- |
| `vitest run tests/ui/connection-disconnect.test.tsx tests/ui/term-editor.test.tsx tests/visual/recovery-pages.test.tsx`，加入同值粘贴回归后 | **3 文件，24 passed** | `0cb221` |
| `npm run typecheck` | 通过 | `0cb221` |
| `git diff --check` | 通过 | `0cb221` |
| 已审文件与 `58c8a7d3a8743f5f2eb9590e93ba8c2c66751fd9` 比较 | 无差异 | 报告写入前核对 |

此前同三套 23 passed 与最终 24 passed 重叠，不累加。24 项中包含 C 自作的一个 TermEditor 回归，测试通过不等于独立自审。主 Agent 另报告同提交全套 **58 文件、570 passed、1 项 Windows 跳过**及 typecheck 通过；C 未为本报告重跑全套，此结果的执行责任和证据仍归主任务。

## 限制与交付判断

现有 `disconnect(platform): Promise<void>` 不包含 expectedAccountId、连接版本或服务端 requestId。前端预检不能代替服务端原子账号校验，本机记录不能提供跨设备幂等。如果客户端重启前从未收到原 Promise 的 ACK，单靠当前连接状态无法确认历史请求终态；实现继续保留未知保护，没有提供强制清除入口。真实接入必须单独验收该边界，不能称后台恢复能力已经完成。

本报告的测试全部使用隔离 TEST 适配，没有真实平台断开、外部发送或生产入库。允许所审前端增量进入候选交付；浏览器可见效果、最终 macOS 包、Windows 安装运行以及生产服务由各自证据验收，不从本报告推导完成。

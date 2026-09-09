# 本机会话内容退出保护：限定架构复核

**结论：PASS。** 对基线 `5536bc0bf4eba8e73ca9cfaf55a16b6b795ec4c0` 上的四文件工作树增量进行非作者审核，未发现本次范围的新增 P0/P1/P2 阻断。允许继续构建与原生退出验收；不能以该结论宣称客户端已跨重启保存数据、真实服务已同步或完整 Goal 完成。

日期：2026-09-10。仅审核 `desktop/src/renderer/app/hooks.ts`、新增 `sessionContent.ts`、`sessionDraftExit.ts`、`desktop/tests/ui/session-draft-exit.test.tsx`，并只读检查对应 Profile、ContactEditor、ContactNotes、FollowupEditor 调用和已有原生退出消息。未修改产品、未提交，未操作原生 UI 或构包。

## 增量职责与边界

`sessionContentAtRisk` 是独立布尔判断：沿用任务/模板判断，追加本机资料、相对 baseline 有修改的画像、非空备注、评论或私信相对 savedContent 的修改，以及显式写入/恢复的跟进草稿。它不产生请求，不恢复数据，不校验业务真实性，不授予任何采集/发送/资料引用权限；恢复仍经 `useLocalDraft` 既有安全 JSON/调用者 schema。宽松的“是否有内容”形状检查最多影响退出提示，不能被当作有效业务 DTO。

前缀与当前页面调用匹配。画像已同步 fields/baseline 相同、评论与私信均回到 savedContent、空资料和空备注不误当未保存业务内容；另一渠道尚有修改时仍提示。列表筛选、UI 偏好及持久未知请求 ledger 不在判断范围。旧 `hasSessionTaskDrafts` 的当前引用已改为新函数，不涉及后台或客户端 IPC 合同。

全局 beforeunload 仍在退出事件边界即时读取，涵盖已卸载页面的内容；不加入内部导航 guards，也不把每次跳页改成退出确认。提示本身不展示任何旧空间草稿正文；账户/空间隔离和业务操作锁没有被合并或重分配。

## 标记、清除与恢复

- `editedDraftKeys` 与 `draftMemory` 使用同一完整 storage key，不用只含业务 ID 的弱键。setter 在 announce 前同步写入内存和标记，因此配额错误下最新输入仍进入退出保护。
- 对跟进编辑，单纯打开来自服务端的 correction 只建立初始内存值，不置写入标记；人工更改才置标记。恢复到本 hook 的初始 base 时删除标记并尝试移除持久副本；当前内存保留 base，优先于可能删除失败的旧副本，解决本次会话 undo 后仍提示的问题。
- 从存储恢复跟进时，将 saved 与当前 base 比较；确有差异才置标记。尚未挂载的持久草稿无法取得该页面的服务端 base，扫描按已有持久内容保守判断，挂载后再依实际 base 细化。这不把持久内容的自报字段当成服务端授权。
- 单 key clear、invalid-value 清理和全局 clear 同步移除标记。已有 `clearEpoch`、`draftKeyEpochs` 与 mounted/activeKey 检查保持不变，原闭包在清除、换 key 或卸载后不能重新写入。全局 clear 继续保留 legacy send/task/followup 原请求锁；风险 predicate 不把这些锁当成会话业务草稿。
- 存储读取拒绝时仍使用内存，写入拒绝时仍保留内存及标记；已明确清除的 key 由本次运行内 epoch 阻止删除失败后的重新读取。畸形 JSON 不被恢复为业务内容。

存储删除仍是可能失败的浏览器操作，这次没有新增跨 renderer reload 的持久 tombstone：如果删除被拒绝、旧 sessionStorage 仍存在，随后整页重载可重新发现旧副本。上述 epoch/内存优先保证限定于当前 renderer 生命周期；本报告不把它描述为跨重载可靠擦除或数据库备份。正常关闭窗口的会话数据丢失风险由真实退出提示表达，自动保存或外部同步并未发生。

## 独立验证

在 `desktop/` 执行：

```sh
PATH=/Users/bruce/.nvm/versions/node/v24.19.0/bin:$PATH node node_modules/vitest/vitest.mjs run tests/ui/session-draft-exit.test.tsx tests/ui/hooks.test.tsx tests/ui/followup-scope.test.tsx --reporter=dot
```

实际结果：**3 文件，51 passed**，退出码 0；时间 2026-09-10 07:30:37，工具输出 chunk `6f1b23`。覆盖即时退出读取、页面卸载、旧任务/模板、清空、存储异常、StrictMode 清理、新增业务类型、仅打开 correction、恢复跟进、undo 回 base，以及既有 hook 清除/身份和跟进 scope 回归。

该结果不与主线程测试相加；主线程正在执行的完整测试、构包和原生验收在本报告写入时未引用为完成结果。未额外运行后台、PG、平台或 Windows 检查。

## 工作树绑定

审核时尚未取得本增量最终提交号，绑定以下文件 SHA-256；后续提交应核对再附加精确 SHA：

| 文件 | SHA-256 |
|---|---|
| app/hooks.ts | `7ed8675200d4e7e566ec17be95acbf07e1362c41d558dad1be00ae9d089e19bd` |
| app/sessionContent.ts | `285a800f53aacc46f56d441b3f4560d9f19512d0a2bb8231aef99a3a1945dba5` |
| app/sessionDraftExit.ts | `6b3ca66c34ab6fb70f04fd495a35c1a1c9741fe795061a9b5f6a70b675973d89` |
| tests/ui/session-draft-exit.test.tsx | `ffea2539ad8402880a3ba329919f89aa15ee7f5ead6a09ad84cad3d933103df9` |

新包仍需实际验证“保存本机资料→关闭/退出出现确认→取消保留→明确放弃退出”，不能用 JSDOM beforeunload 或旧任务退出证据替代本次业务内容路径。

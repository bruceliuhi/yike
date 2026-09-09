# P12 双用途未保存保护：a25 实际 TEST 验收

绑定 `a25ba7b331e7712c4fba53b173cbbc704ec3e734`。主线程通过 Codex In-app Browser（IAB，browser2）/CUA 在真实 ContactEditor 中编辑两种用途；本记录独立核对 AX、事件和 1280×720 PNG。使用最终静态 TEST build，来源及运行后文件哈希见 [P04/P12 共用 build-binding](../p04/build-binding.json)、[构建日志](../logs/visual-build-final.log) 与 [源码 snapshot](../source-final-before.json)。本页代码在这些可见操作之后未变；后续修订另行绑定。

入口虽带 `recovery=send-unknown`，**本次只验证未保存退出保护，没有进入准备发送或未知发送恢复链**。对象为 TEST 合成商机，`saveContact` 只写该实例内存；公开研究样例仍是独立只读入口，没有向外发送消息或写真实客户库。

## 可见流程

1. 评论输入 `TEST 评论未保存：请问资料可以从哪里获取？`，切私信输入 `TEST 私信未保存：方便确认一下服务范围吗？`，尝试离开。保存的 [双用途退出提示 AX](two-channel-leave-guard.txt) 同时显示私信正文、评论仍未保存提示，以及“离开当前页面？”的取消/继续离开按钮。主线程取消后回到评论，内容保留。
2. 仅保存评论，再尝试离开。[other-channel-still-dirty.txt](other-channel-still-dirty.txt) 同时显示评论“已保存内容”、私信仍有未保存修改提示和退出确认。由此可证实保存当前用途不会释放另一用途的未保存保护。
3. 再次取消并切私信，[dm-retained-after-comment-save.txt](dm-retained-after-comment-save.txt) 保留原私信正文、“本机修改未同步”及禁用的准备发送按钮。主线程随后选择继续离开；新增 [leave-confirmed.txt](leave-confirmed.txt) 的实际 URL 为 `#/workbench`，AX 标题和主标题均为“商机工作台”，证实明确确认后已完成页面离开。

[events.json](events.json) 为 3 条连续事件：`opportunities`、`opportunity` 各一次读取，`saveContact` **一次**。没有 prepare、verify、send 或其它写事件。事件采样覆盖上述编辑/评论保存阶段；最终离开由新增目标页 AX 单独证明，不把离开后的页面读取硬加入这份旧事件样本。[console.json](console.json) 为 `[]`，仅代表本次采集未记录控制台消息。

## 1280×720 画面核对

已实际打开 [leave-guard-1280x720.png](leave-guard-1280x720.png)：退出弹框完整居中，标题、原因、取消、继续离开均清晰可见；背景正文/页面处于滚动位置，不是整页一屏截图。截图上方“草稿已保存到客户空间”的 toast 对应已保存的**评论**，退出保护对应仍未保存的**私信**；不能把两者并存误判为保存失败，也不能把 TEST toast 说成真实后台已保存。

背景可见公开样例的“只读”标签、TEST 横幅和短句教练服务未接通提示，没有用设计图或测试响应假称生产服务已接通。本次只验证该尺寸的退出弹框与文本保留，不作为 P12 全页逐像素对照、全部响应式尺寸、原生客户端或 Windows 通过证明。

另行发现的 P14/P15 跨空间 P1 在后续切片修复；本页证据仍保留 a25 来源，不提前绑定未来提交或新包，不代表整个前端 Goal 完成。

# 本机会话内容退出保护

基线5536bc0。上轮原生资料保存后CmdQ直接关闭的现象，本轮源码核实为退出保护仅检查task、task-library、task-templates，遗漏已保存本机资料。见旧ui-native-files记录；旧最终退出未签通过。

新增纯风险判断模块，仍由统一beforeunload走现有主进程确认，不改变设计/存储期限/登录隔离/业务提交与操作恢复权限。覆盖本机资料、画像fields相对baseline的变更、联系备注、评论/私信相对savedContent的改动（含删除），以及显式修改或从存储恢复的跟进草稿；原任务保护保留。空默认、已同步副本和界面筛选不拦截退出。

跟进纠正默认来自服务端，不按“内容非空”判定。代码审核发现改动再还原初始值会误提示P2，已补清除写标记与存储；内存内容优先于移除失败后的旧存储，防止保护状态复活。

初始tests以null作结构化草稿基线被现有hook校验清除，修复测试校验器后再验证；保留red/green历史输出，不把三处测试设置错误说成产品缺陷。最终源码为 b8b82367b34af24da218dba3796a8945d667aaa6；[最终 UI 回归](logs/final-ui-after-review.log)为82文件、1015项通过，类型/构包通过；36项独立限定审核不与主回归累加。原生交互见后续记录。

Windows、真实服务、全Goal保持各自验收，不能由本轮beforeunload模拟或Mac原生代签。

## 实际 Mac 原生验收

同路径 `desktop/out/session-content-b8b8236/意客AI.app`，独立包结构及355源码输入核对见 [包报告](reviews/package.md) 与 [清单](final-mac-package.json)。ASAR `f2cd0342c969ee19005041558fd91eccb4f79bb00735d4d8c51b09023daa5778`；ZIP 哈希见清单。产物留本机，不将大二进制提交Git。严格smoke为隔离验证，不替代下述真正操作。

1. 登录前直接在P04手动填写专用TEST资料并保存，[01](01-saved.txt)为本机草稿，未创建任务，未接客户服务。
2. CmdQ弹出真实macOS确认，[02](02-quit-confirmation.txt)与[截图](screenshots/quit-confirmation.jpg)显示放弃/继续编辑和会话清除提示。截图已实际查看，两按钮可见。
3. 点击继续编辑，[03](03-continue-editing.txt)资料仍在；重开编辑，[04](04-original-preserved.txt)核对名称与完整正文。
4. 取消编辑并切到工作台，[05](05-navigated-workbench.txt)绑定离开P04状态；再次CmdQ，[06](06-quit-after-navigation.txt)依然提示，证明保护不依赖资料页挂载。
5. 实际点击放弃更改并关闭。[运行PID2875](native-running.json)在[退出检查](native-exited.json)中已不存在。
6. 从完全相同app路径重启，[07](07-reopened-empty.txt)显示暂无资料；[新进程](native-reopened.json)绑定新PID。明确放弃后会话稿清除符合原提示；不声称永久保存或云同步。

代码审核曾指出的跟进恢复初始值误报已修，见 [代码报告](reviews/code.md)；[架构报告](reviews/architecture.md)保留存储拒绝及重新加载边界。联系、画像和跟进的广度由明确的UI/状态测试证明，原生本轮只签P04这条退出链，不扩成所有页面实际点击通过。

原始测试/构包日志保留其尾空白，差异检查仅对这类原始日志排除空白告警；产品/文档检查通过。四个原有raw草稿未纳入。整体05A与Goal继续IN_PROGRESS。

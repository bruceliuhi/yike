# P07 原文与人工复核 Windows 界面证据

2026-09-10，产品源码`5614d71`；Windows Edge，既有P07，TEST隔离内存传输，不是生产/真实HTTP/真实平台验证。

- [1440原文](final-1440-original.png)、[960原文](final-960-original.png)：本人评论、作者、来源时间/链接、父上下文分开；完整页面文本见[原文记录](final-original.json)。
- [1440确认](final-1440-confirm.png)、[960确认](final-960-confirm.png)：固定画像/来源/核验ID与依据，勾选确认，页脚完整可操作。
- [960恢复](final-960-recovered.png)、[恢复事件](final-recovery.json)：取消后重新确认；提交结果未知时不盲重试，筛选外GET原请求找到成功结果；一次INCLUDE，无旧未知错误残留。
- [960原文读取失败](final-960-raw-error.png)、[失败记录](final-raw-error.json)：明确失败，不用摘要冒充原文，不允许纳入。

截图只覆盖指定状态，不代表P11实际服务接收或客户整链；实际Node→HTTP→PostgreSQL仍待Task5。完整验证与失败历史见[05G QA](../V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md)。

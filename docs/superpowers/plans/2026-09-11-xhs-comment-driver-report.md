# 小红书主帖评论页面适配器实现报告

## 实现边界

- 新增 `XhsPostCommentChannel`，仅接收受信宿主持有的同一隔离 Playwright page。
- `check` 只读校验官方笔记页、侧栏账号、原帖作者、空白主评论编辑器和唯一发送按钮。
- `execute` 绑定同实例成功检查及完整 context 快照，单实例最多消费一次；点击前复查账号、作者、URL、正文、模式、取消和 deadline。
- 点击后只接受唯一新增顶层评论，并在 reload 后以评论 ID、账号和全文完成持久读回；否则返回 `UNKNOWN`，不重试。
- 未新增 CLI、IPC、宿主公开发送入口，也未读取 Cookie、私信、凭据或隐藏页面状态。

## 证据边界

- 浏览器 DOM 实查依据来自同日只读页面观察：`#noteContainer`、作者和评论作者 profile href、`#content-textarea`、`.content-edit`、发送按钮、顶层 `comment-24hex` 与子回复区分。页面自带 query 仅用于当前页定位，不进入 proof。
- 自动测试全部使用合成 Playwright 边界替身，没有登录或向真实平台输入、点击、发送。覆盖空白主评论绑定、取消/错账号零点击、一次点击后刷新读回成功、刷新消失为 `UNKNOWN`、重复 execute 零新增点击。
- 尚无真实发送后的 DOM 与刷新持久读回样本，状态保持 `REAL_PLATFORM_SEND_UNVERIFIED`；本批不证明宿主完整接通、真实渠道可用、其他平台/私信/回复或 Windows 实机。

## 定向验证

真实 RED 记录：首次运行本模块测试在收集阶段因 `app.xhs_comment_channel` 尚不存在而失败；后续“刷新后消失”测试曾以 `reloads == 0` 失败，定位并修正了替身未模拟点击后乐观评论的问题；最后差量测试又先观察到页面异常 `ValueError("browser detail")` 外泄，再实现固定错误归一。

`/tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q tests/test_xhs_comment_channel.py`

结果：`6 passed in 0.02s`。

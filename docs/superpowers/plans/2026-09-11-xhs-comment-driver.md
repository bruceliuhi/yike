# 小红书主帖评论页面适配

沿用已批准V02-06/07确认后真实触达，不扩产品范围；基线6ce5aee。按用户省token要求，一个实现批次、定向TDD、一次独立复核，不构包不外发。既有登录/采集隔离运行时继续复用，禁止把内置浏览器登录态搬进客户端。

## Task 1: 真实页面适配器

新增`app/xhs_comment_channel.py`与`tests/test_xhs_comment_channel.py`。提供`XhsPostCommentChannel(page, *, cancelled, now)`，page为受信执行器已打开的同一隔离Playwright页；`async check(context)`输出NativeOutreachChannel的AVAILABLE观察；`async execute(context, operation)`输出NativeOutreachOutcome。不加CLI、公开IPC或无确认发送入口。后续宿主将此对象接到现有consumer许可/消费日志；本批不能声称完整宿主接通。

- 输入在await前深拷贝，固定XIAOHONGSHU/POST/comment/POST_COMMENT、24位小写hex note/account ID、来源及页面官方HTTPS域/相同note ID、确认内容=savedContent、发送账号=connection账号、接收人=原帖作者。拒绝字段缺失/类型错误、超长正文、其他平台/回复/DM。实际context全结构见`desktop/src/main/outreachConsumer.ts`；不重新设计协议。
- check只读同一页面：官方笔记URL、唯一可见`#noteContainer`、侧栏“我”账号、原帖作者、唯一空白可编辑`#content-textarea`与唯一发送按钮；composer主评论“说点什么...”模式，已有草稿/回复模式不覆盖。输出原context/设备/连接/账号/作者及UTC检查时间，缺证返回固定错误，不输出页面内容或凭据。
- execute必须此前同实例check成功且context字节绑定一致；实例最多消费一次动作，提前取消/过期/账号、作者、页面、正文或模式变化不能点击。有效operation包含requestId/claimId UUID和带时区dispatchBefore，deadline必须未来且最多35秒。填写前再查空白主评论；填写后再检查账号/作者/URL、编辑器文字与主评论模式，再作取消和deadline检查；只调用一次真实DOM click，异常/超时不重试。
- 点击之前采样原顶层评论ID。点击后最多等待5秒，寻找唯一新增的24hex顶层评论ID，账号和全文与本次一致；仅页面乐观显示不算成功。再reload同一笔记，以同ID/账号/全文重新可见作为持久读回证据，随后SENT+ACCEPTED proof。证明sha256只对最小原事实（平台/note/账号/评论ID/内容/context摘要）规范JSON哈希，不存原文/URL参数。失配/仅toast/未找到/刷新后消失一律UNKNOWN，不宣称FAILED或再发。
- 发送后即使取消也允许保留已确认的晚回执，但不再执行其他写动作。若无法完成读回，保持UNKNOWN。每个DOM等待有界；不读Cookie、私信、网络凭据、隐藏JS状态，不触发绕过或挑战处理。

TDD：先最小正确绑定且主评论空白检查，以及取消/错账号零点击、单次点击后刷新读回成功/消失UNKNOWN、重复execute不再点击。仅执行`/tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q tests/test_xhs_comment_channel.py`，必要使用边界替身，不实际平台发送；报告区分浏览器DOM实查与合成行为测试。不要复制巨大矩阵。

## Task 2: 接现有受控运行时与审核（根）

新增`app/platform_outreach_runtime.py`异步上下文管理器`open_xhs_comment_channel(context, *, cancelled, now)`，复用`app.platform_login_worker._load_runtime`及受控crawler的launch_browser/close，固定同一隔离新page。按下方实测先导航官方作者公开主页，在`#userPostedFeeds a.cover`中匹配准确`/user/profile/authorId/noteId`原帖链接（允许链接自身query，不读出存储），唯一匹配后点击进入，再由实际适配器check后yield。找不到原帖拒绝，不点击相似内容或猜来源参数。输入在await前快照，初始化超时20秒，每步检查取消；不扫码/自动登录、不另读客户Cookie、不改runtime依赖、无CLI。清理异常固定`OUTREACH_RUNTIME_CLEANUP_FAILED`，不得据此断言未发送；调用者必须先保留execute回执。使用`tests/test_platform_outreach_runtime.py`定向检查复用页面/检查先于yield/失败取消清理，不以替身冒充平台。

将页面适配接口和既有Windows host两阶段check/execute差异写入07B合同的下一接入动作；没有宿主/TS桥接时保持发送入口关闭。审核绑定代码提交，仅检查本批；新增缺陷做差量修复。下一批接同一隔离页的受监督宿主/consumer，不追加孤立签名协议。

## 页面依据与验证边界

2026-09-11内置浏览器只读打开公开技术笔记`/explore/6a9e313a0000000026031b33`。DOM实际存在：`#noteContainer`，内部`.author-container a.name`，`#content-textarea[contenteditable=true]`（P元素），`.content-edit`初始“说点什么...”，`button`文本“发送”初始disabled；顶层`.comment-item`的`id=comment-24hex`、`a.name`作者与`.note-text`正文；子回复带`.comment-item-sub`。账号检查沿用`app/platform_collection_worker.py`的侧栏“我”定位。只采集结构，不把该技术分享作为销售线索；未输入、未评论、未读私信。浏览器URL临时来源参数不入库。

尚无真实发送后的DOM样本；刷新读回路径必须通过受控授权实测才能标渠道可用，本批仍REAL_PLATFORM_SEND_UNVERIFIED。其他平台、私信、评论回复和Windows实机不被本批替代。

直接无来源参数打开同一`/explore/6a9e313a0000000026031b33`实测跳404/300031“当前笔记暂时无法浏览”；不能把去参URL当可靠直达入口。随后从该作者公开主页精确点击相同原帖，重新出现标题、108条评论及评论框。主帖跳转链接位于`#userPostedFeeds a.cover`，path为`/user/profile/authorId/noteId`，进入后pathname恢复`/explore/noteId`。因此运行时使用主页原帖导航；没有搬运或存储临时来源参数，没有尝试验证码或访问绕过。这是已验证的只读重开路径，不是发送验收。

公开DOM进一步核对：作者及评论者`a.name`显示昵称，public ID只能由href官方路径解析，href实际带来源query；主评论框聚焦后“说点什么...”消失，`.content-edit`变成正文及无文字的emoji区域。代码须按这些实查约束，而非把替身中的昵称当ID、或强求填写后仍有placeholder。

## 本批验证

页面模块专项见[短报告](2026-09-11-xhs-comment-driver-report.md)，根不重复运行。runtime最初因缺模块出现fixture setup errors，单独缺入口断言RED后实现；改为作者主页导航的RED明确捕获旧版仍直达/explore，修后最终6项行为测试通过（已移除临时存在性断言）。途中测试替身`now`必填与生产可选不一致，已校正替身后再验证导航失败。命令：`/tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q tests/test_platform_outreach_runtime.py`，6 passed。合成Playwright边界只证明控制流程，不证明平台发送。未安装新依赖、未构包或全量回归。独立审核与代码版本待收口记录。

`c8203e9`整批独立审核NO-GO：P1取消回调未中断Playwright待点击动作；P1刷新读回未确认评论及证据节点可见/顶层作用域。差量修复中：取消/过期时关闭此执行器独占page以终止pending动作，不以仅取消Python Future替代；刷新后必须在原noteContainer内唯一可见顶层评论及其作者/正文中核对。[Playwright官方page.close文档](https://playwright.dev/python/docs/api/class-page#page-close)说明默认不运行beforeunload，等待页面关闭，并使进行中的操作中断；本批不据此声称已做真实Windows取消实验。已发生动作不能因清理失败降为未发送，仍按UNKNOWN/已确认晚回执记录，禁止重试。

最终代码`352a95723cb9acd1fd4bf67e22da9a995528be66`独立差量复核GO，两项P1关闭，无新增阻断。修复模块8 passed，runtime 6 passed原证据复用；未重复构包/全量测试。审核结论只覆盖代码候选；真实发送、Windows进程桥/main/UI、部署及跨行业UAT均未被证明。Task 1/2本批适配完成，父卡与完整Goal继续IN_PROGRESS，下一批接既有监督器与consumer的同页CHECK/EXECUTE进程桥。

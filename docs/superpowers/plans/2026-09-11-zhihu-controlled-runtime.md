# 知乎受控运行与本人账号护栏

> For agentic workers: subagent-driven-development、定向TDD、一次非作者整批审核；已批准V0.2多平台架构，无新增界面/业务范围。

**Goal:** 固定知乎源运行遵守隔离、预算、原文留存、登录身份与失败清理要求，提供下一批四平台任务接线的真实代码基础。
**Architecture:** 原固定commit顺序追加0003治理补丁，保留旧补丁；原生host继续固定参数/独占路径/有界进程，知乎登录与采集使用同context本人uid校验。服务端/桌面能力仍不自动启用。
**Tech Stack:** 固定MediaCrawler、Playwright标准Chromium、现有Python/补丁lock，无新依赖/DB/构包。

## 全局约束

- 基线28b0da6；商业代码授权已确认。无真实平台访问/外部发送/凭据读取输出，不绕验证码/限流/权限。只用已有固定源本地代码核对接口。
- 固定源接口ZhihuCrawler.context_page/browser_context/zhihu_client，ZhiHuClient.playwright_page/request/get_current_user_info；本人uid仅正ASCII数字1..20。私有原始响应不得出日志/状态，昵称/hash/id不是uid替代。
- 所有浏览器可见、Playwright bundled Chromium/defaultUA、外部已验证YIKE_PROFILE_PATH，不使用系统Chrome、CDP、stealth、代理、Cookie注入、短信、扫码代操作、自动挑战重试。正式验证/限流立即终止待人工。
- source/client请求同browsercontext的APIRequestContext，固定https官方host/API路径，禁重定向，10s超时，有界JSON正文；错误只固定类，401auth/403permission/429rate/非200及未知shape错误，5xx/network独立。404不当无评论，只有结构明确空列表可无数据。
- 初次需要登录时普通站点窗口由用户操作；仅认证未完成可有界等待，限流/权限/验证码不重试。client.pong只捕获AuthRequired，不能吞结构/网络/限流错误。
- 搜索仅search模式、一次一关键词（宿主校验），内容≤5，总候选POST+COMMENT≤100且受请求maxrecords约束；可用config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES作为这条知乎固定CLI的总候选预算，与其他平台既有语义隔离。主帖占1，空zvideo不占POST但内容读取仍占内容预算。评论根+子累计，重复/游标不前进/不完整响应不得无声成功；达到明确预算可停止但不得超额写入。
- 保留固定help/model提取正文/匿名hash，并锁定其摘要；正文不是desc/标题，视频只允许真实zhihu landing URL。用现有store_jsonl但禁止源数据日志；最后关闭context之后才报告成功，失败清理仍遵循原CLI/host规则。
- search结果体若不是明确结构则失败，不以缺data等于0；分页必须有明确结束/前进依据。评论支持既有根/子接口，不接其它私密内容或用户资料。原文/评论last_modify_ts各自真实存储时间。main对知乎POST-only必须SUCCEEDED，空视频无评论仍NO_DATA；旧三平台语义不变。

## Task 1: 固定依赖补丁（backend agent）

Files: 新vendor/patches/mediacrawler/0003-yike-zhihu-runtime.patch；新tests/test_zhihu_governed_runtime.py；私有临时源副本。Root负责lock/main仓原生host模块。

- [x] 在新的mktemp目录基于固定commit+已有0001/0002建立私有编辑副本；不改已有/tmp/yike-three-platform-runtime.n5Nouc。修改用apply_patch，最后生成差量并用apply_patch写入仓库patch。
- [x] 仅治理media_platform/zhihu/{core,client,login}.py、必要store/zhihu/__init__.py与main.py。固定类/签名供root后续import，禁止旧creator/detail/CDP路径回退。AbstractCrawler/ApiClient/Login必须可实例化。
- [x] 最小验证：有正文无评论为成功；内容+评论总预算、子评论累计、未知shape与停滞、401/403/429/404/network不会静默无数据、关闭异常不成功；实际新源模块导入、标准browser参数、受注入profile及无stdout原文。用合成page/request和固定提取器，定向一次，不PG/真实平台/构包。
- [x] 提供临时路径、最终修改文件hash清单及新patch路径，提交自身patch/tests。Root从独立新副本顺序重放3patch核对lock，测试不双跑。

## Task 2: 原生登录/源账号边界（root）

Files: app/platform_login_worker.py、platform_collection_worker.py、windows_collection_host.py、windows_source_driver.py；tests/test_zhihu_native_guard.py；vendor/mediacrawler.lock。

- [x] RED：知乎合法uid/非法uid、同context本人不符/响应后切号锁存、正式限流终止、固定CLI/host平台路由及旧三平台不扩大配置。
- [x] 增加固定知乎runtime import；read_zhihu_self_account(page)使用同context GET https://www.zhihu.com/api/v4/me、max_redirects0/timeout10000、受限body/错误分类，仅返回uid；不请求email/phone等include字段，不日志响应。
- [x] 登录使用现有privatehost OPENED/有界等待/物理cleanup规则；成功必须最后本人核验并关闭。新install_zhihu_account_guard封装search/request前后同page核验，任何失败锁存，即使源吞错误也不可成功，恢复原类方法。
- [x] 宿主仅明确ZHIHU参数支持，不改后台mode或UI可用性；CLI --platform zhihu，query/预算/visible/profile校验沿用。期望账号必经worker，无无护栏fallback。
- [x] lock追加0003与新/变更文件摘要，旧patch/依赖version不改；独立重放确认所有patches与文件匹配。精确受影响测试和治理检查，不构包。

## Task 3: 整批审核/交接

- [x] 一次非作者完整review，必要问题一波修复仅差量复审；唯一证据写本文件、任务书短链接，正常推main核SHA。
- [x] 记录仍须四平台opt-in前后端/monitor、安装payload和真实平台/Windows/UAT；不追认旧包支持知乎，不把本源模块当完整V0.2上线。

## 实施与验证

- 源码 `31256e1`：原生登录、本人账号核验、受控host和总预算；`0cbe2a9`：复用固定知乎提取器/模型/存储与API，追加0003补丁及lock。初版辅助实现进程容量错误，root接收现有文件后修复，未重做采集机制。
- 本批只做定向验证：原生相关95 passed（1.03s），新增预算1 passed（0.10s）；独立解释器源检查1 passed（5.38s），包含HTTP错误、根子评论累计、游标、真实context请求边界、登录方式、浏览器参数和关闭异常。测试是合成输入，不代表知乎实测。
- 三层补丁在独立固定commit副本成功重放；既有文件无漂移，新文件与受测字节一致，lock加载通过。保留固定help/model及存储摘要。前期测试脚本非ASCII bytes语法与临时目录工作路径错误已纠正，不算产品通过证据。不跑全套、数据库、真实平台或构包。
- 搜索当前是一个关键词的一页有界样本，最多5个内容、POST和COMMENT合计最多请求预算；不是全网穷尽。未知结构/无法提取的非空页不伪报无数据，评论按原接口节流。
- 非作者整批审核：`0cbe2a9ee6241262289b45549e16f9568e4e4c3f` GO，无阻断P1/P2，未重复测试或构包。服务端和桌面四平台能力尚未打开。

## 下一里程碑：可操作验收版本，不继续孤立适配

1. 复用原三平台登录、任务和监控流程接入知乎显式能力；定向验证改动路径，不重建公共采集机制。
2. 解决普通安装启动的客户服务配置：当前main仍只读 `YIKE_SERVICE_URL`，双击无环境配置时不可登录服务。真实HTTPS地址和测试账号须来自授权配置，不猜地址或降低认证要求。
3. 按同一源码生成Windows运行payload与安装包一次，在真实授权账号完成搜索→原帖/评论→正式候选入库→普通客户端打开详情；缺真实条件集中说明，不用mock替代。
4. Mac包仅用于适用的界面/服务验证，当前正式原生执行器是Windows，不追认Mac包已具备采集。协议正式内容和部署门禁仍须落实，自动更新增强不挡阶段试用。

本里程碑调整交付优先级，不取消完整V0.2其它功能及最终上线门禁。

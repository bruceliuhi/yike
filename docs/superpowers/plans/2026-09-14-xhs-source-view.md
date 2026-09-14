# 小红书原文查看 Implementation Plan

> 按用户已批准的范围内自主细化要求执行；使用 subagent-driven-development 分离导航与主进程接线，最终一次批次审核。main 小改串行提交，未完成接线不得称用户可用。

**Goal:** 客户从真实候选点击原文时复用本机当前账号的平台会话，定位同一原帖，不再仅把无参数链接交给未登录的系统浏览器。

**Architecture:** 原文证据仍保留无凭据canonical URL。主进程按当前用户/设备读取候选当前版本及其观察，解析同源 note ID、原查询和已知原帖作者；profile由既有加密store提供，renderer不提供路径或Cookie。受监督的只读浏览器会话复用既有profile锁及退出处理；只点击源站实际可见的精确同ID链接，临时URL参数仅在浏览器内存中。打开不写核验声明、不发送、不自动将候选入库。

**Tech Stack:** TypeScript/Electron existing identity/profile/IPC，Python existing governed Playwright runtime，Vitest/pytest targeted checks。

## 取舍与边界

- 不采用恢复含访问参数的云端候选URL：现有证据合同禁止且会扩大敏感信息流转。
- 不采用重新要求用户在系统Chrome登录作为产品默认方案：与已批准的授权持久化体验不一致，且裸URL仍未证明可访问。
- 采用同会话平台内定位：已知POST作者可复用已存在的作者主页真实链接导航；COMMENT作者不是原帖作者，不借用。未知原帖作者可使用该候选保存的原查询在平台搜索，再点击精确同一note ID的实际链接；不得打开相似内容替代。
- 所有导航前后核对官方origin、当前账号及取消状态。输入必须严格限制note ID、可选作者ID和有界查询；不把输入当selector片段或脚本。不处理验证码、不导出Cookie、不绕过源站限制。
- 仅匹配唯一可见链接；核对跳转后的原帖ID，并检查实际详情存在，404/错误/缺失不得报成功。若精确链接不在首屏，返回不可定位，不进行无界滚动或扩大采集。
- COMMENT若仅打开所属原帖，明确提示“已打开所属原帖，未定位该评论”，不称评论原文已重开，不写评论核验成功；不因此扩大为评论深采。
- 新查看入口的生命周期必须覆盖用户关闭、超时、切换账号、退出应用和profile繁忙；未知清理不伪造成功。窗口可用与来源真实性/联系权限分开。

## Chunk 1：同会话只读定位

- [x] 新建 app/xhs_source_navigation.py（可测试、无CLI、无profile读取、无Cookie/API取数/文件输出）：接收现有page及严格目标，核对账号，打开官方主页/作者页，通过页面搜索框或实际作者页链接定位唯一相同note ID；失败为固定无原始数据错误。可选query只用于原始搜索动作，明确不是换词找相似。
- [x] 新建 tests/test_xhs_source_navigation.py：先RED；合成页面覆盖同ID、带临时参数实际链接、错ID、重复/隐藏链接、未知作者查询、错误页、账号变化、取消、输入非法和原始参数不出结果。再最小实现与GREEN；仅本文件及必要现有导航测试。

## Chunk 2：客户端接线与实机

- [x] 新建 desktop/src/main/xhsSourceTarget.ts 及 desktop/tests/xhsSourceTarget.test.ts：复用现有严格rawEvidence解析，用renderer当前版本绑定比对服务端当前证据；只从精确current_observation取原查询与连接，不借其它历史记录。COMMENT作者不作为原帖作者；源URL/ID需完全匹配固定规范，参数不进入目标。先RED再实现。
- [x] 基于既有受监督host/driver增加只读查看生命周期，不复用发送上下文、不把AUTHENTICATED当原文已打开。主进程获取当前候选与profile绑定，仅传当前账号目标；新IPC由受信renderer触发；已有系统浏览器入口保留其它平台/公共网站行为。
- [x] 原文按钮接入当前candidate ID/version，打开中禁重复，结果以简单中文显示；不写来源核验、不发起发送。账户切换/退出停止会话并释放profile锁。
- [ ] 定向验证身份/目标绑定、旧版本拒绝、busy/失败/cleanup、UI接线；独立批次审核后合并构一次最新Windows候选，真实用户路径验证同条原帖可读，未通过则保留失败继续修复。

此计划不缩小发布目标：三业务任务、有效买方线索、草稿反馈及真实用户认可仍需完成；原文导航单元测试不等于平台实机成功。

## 本轮基础模块验证（未接线、未构包）

目标投影：首次缺模块无法加载，增加拒绝占位后有效RED 3失败/6通过，实现后9通过；补sourceKind区分POST/COMMENT时有效RED 2失败/7通过，最终仍9项通过（不累计重复运行）。typecheck通过。

导航：50项初始RED后50通过；检查发现泛匹配“验证码/404”会误伤正文，另以5项RED驱动修正为内容区外的精确平台提示，同时加入实际“当前笔记暂时无法浏览”提示；随后页面就绪等待新增2项RED，修复后最终66通过/13.71秒（不累计重复运行）。全部离线页面替身，未访问真实平台。候选搜索框input#search-input尚未实机验证，缺失即返回固定失败。此刻真实客户端仍638906e，不含新查看入口。

基础模块独立Spec/Quality审核GO，无P1/P2；绑定导航blob `f81e3e76ef2c206bd9b8597b3ec488031516df80`、Python测试 `62ea58634019b6409de679ce1b61cad68965e9fc`、目标解析 `b97a29b5ecb2d627af5e79484c12cdf3506b9b2b`、TS测试 `27dca827f9a01016faebc95ebe6ef8248c17811f`。该结论仅覆盖基础模块，不代表host/driver/IPC/UI或实机可读性完成；复用同字节测试证据，不重复构包。

下一接线位置已确认：main.ts attachPlatformRuntime内复用profileStore与runtime配置，identity.requestApi({operation:'candidates.rawEvidence',payload:{candidateId}})取当前证据，现有resolveCollectionAccount校验当前连接/profile。查看器须把scope当前性/AbortSignal贯穿异步步骤，并加入before-quit的停止链。不得调用outreach执行或伪造其上下文。renderer Opportunities.openSource 当前仍只有service.openExternal，需新增只读IPC后才替换小红书分支。接线及真实源站验证是必做后续，不因本轮单元测试通过而认为修复完成。

## 客户端接线批（2026-09-14；覆盖上段接线待办，实机仍未完成）

新增独立只读host/worker/driver及主进程控制器；固定协议 `windows-source-view-v1`，实际同帖详情就绪才发SOURCE_OPENED，浏览窗口最多300秒，关闭后才确认物理清理。当前scope、设备、当前候选版本及原观察连接与加密profile绑定；账号切换/应用退出停止查看。小红书原文按钮使用新IPC，评论仅开父帖明确提示；其它平台和样例保留原外链。不调用发送、核验写入或模型。

定向证据：控制器先有效RED 5失败/2通过（占位期另有未消费拒绝，测试已修正），后7通过，忙锁新增1项RED后最终8通过；host/worker最终30通过，包含意外清理中断和明确启动前锁忙的RED→GREEN；driver初始缺模块失败后40通过，再3项协议/忙锁RED→GREEN（共43项，不重复累计）。主进程/预加载/服务/UI批最初新增3项失败，其中UI替身sourceLabel不匹配先修正再取得有效RED；最终5文件68通过，其后控制器新增1项已独立通过。两项旧UI断言跟随已批准的技术ID隐藏和“记录”按钮文案更新，核验ID仍在提交体内断言，不重新暴露给用户。最终typecheck通过。

审核发现并修正：安装包固定HOST_FILES及host import probe补入3个Python模块，新增清单测试RED→GREEN 1通过；明确未启动的锁忙映射XHS_SOURCE_BUSY，不当成未知清理而锁死退出，其他未知清理仍拒绝重启。离线替身与清单检查不代表实际平台可读；下一步冻结本批、一次构包、用真实客户端点击同一原帖验证。

最终独立Spec/Quality GO（仅实现合入）：host `d7eae15dda037a735f5b7ac4196d7b47d55d55e2`，worker `5ffcd8fa0d744b4e85e783965a91662e7daf98ca`，controller `a558204e803768d68ec83313e36a8e614ae54f5e`，driver `8a2297f0a8f42faa776b4d6f68585cc2514458d6`，main `554fd62846195f653ff4703e929314be873492b5`，UI `fb807ec085733d72d3e1e72a5f8dfddaaecdf326`。两项阻断均已差量复核，无剩余P1/P2；不追认实际平台可读或产品上线。

## 6b31309 实装与实际失败（2026-09-14 10:33–10:40）

固定源码 `6b31309deb42e58c7446df31ac36765aa77b3efd`，658项桌面输入前后hash `d7a4a053f238b0ed7fc22b80bcb3d04d4a1e2153c31b15a6b34693b98c4617f3`；隔离portable检查1通过/120.89秒，Forge退出0。`D:/ykr914/make/squirrel.windows/x64/YikeAI-Setup.exe`，642865152字节，SHA256 `2724591a0ba2e2d809eff3d57a38f217e1e1e38fb40366542bee16b72b295ad5`，NotSigned。portable manifest `b595be1be8520bf4c578cc74536972ce785b656add9ac5b94787e88d36fa1ed8`；40个renderer文件及main HTTPS/pin对包一致，安装退出0，实际ASAR `142f37eff4951632f73539634e4972a5bfb3ce15eb89beb30852ec29f4e05518` 与候选一致。旧版正常退出，未删会话/线索；新UI保留登录、小红书已连接及原任务9/10已完成。服务ready返回ready，本批无服务部署。

10:38:20通过真实客户端原任务选择 `6aa6534e000000002902df7a` 点击“查看原文”，实际仍激活旧Chrome 404页，没有新source输出目录项，不是修复通过。根因：真实 `client.candidates` 将平台枚举转换为“小红书”显示标签，而新按钮只比较XIAOHONGSHU；原测试直接api.list绕过了这层转换。

差量：分支同时识别枚举与既有显示标签，不放宽主进程真实候选/平台校验；XHS测试改走真实base.candidates及模拟固定bridge。有效RED1失败（新查看调用0），修正后本文件17通过，typecheck通过。独立差量Spec/Quality GO，UI blob `0a3fcc0293abb3c8bc69e2260dbb808fb5ba05ba`、测试 `ba616b477121e94f1b44e81dfa43b8ad2167dc97`。未新增采集/判断/发送/核验记录。原帖可访问性仍未通过，下一步构建并实装修正版本；6b31309不能标为原文查看可用。当前构包合同要求payload source commit等于桌面HEAD，故不直接复用旧manifest或伪造版本。

## 6c174ac 实装与搜索定位失败（2026-09-14 10:54–11:02）

源码 `6c174acc5272f98c8a38e608ec66a2b9272f5fdb`；portable隔离检查1通过/119.68秒，658项桌面输入前后hash `c746e962b053d150997f519dc63fb88796432faad0fabe65af93d882a7b7ccff`，Forge退出0。安装包 `D:/yks914/make/squirrel.windows/x64/YikeAI-Setup.exe`，642865664字节，SHA256 `e1ed2216a16fba3ba64e1d61676ea393e97c45bf720d2ed20aecc71887554c00`，NotSigned。portable manifest `24439db9e1aad2fe62a40209e43140af5c963b5b710ebab3375bbfa3c8d257d2`；40个renderer文件及main HTTPS/pin一致，安装退出0，实际ASAR `71e3ebe7610c06fcdebb30a4eb137746c4514f8c040f39b3768ec189608966af` 与候选一致。登录、小红书连接及原任务9条线索保留，无服务部署。

10:57:37在真实客户端同任务、同 `6aa6534e000000002902df7a` 点击查看原文，已启动新Chrome for Testing窗口及source输出，不再误走旧Chrome外链。但窗口随后关闭，终态 `FAILED/XHS_SOURCE_SEARCH_UNAVAILABLE`，没有SOURCE_OPENED；输出 `a5cc694c-2510-468c-9424-42b29c5190ab`，定向现场复现 `2f480ccc-e1bd-4bd8-8f74-064ad1093eac` 同错误。UI如实显示“暂时无法定位这条原文，可稍后重试”。不能标为原文可用。

初步定位在搜索控件等待/唯一可见性分支；普通Chrome只读页面检查确有 `input#search-input.search-input`，但该浏览器未登录，不等于保存账号的实际查看窗口。后者短暂出现，Windows工具现场捕捉分别遇到窗口已关闭和Chrome窗口归属检查错误，尚未取得其搜索控件DOM证据；不得据此猜改选择器或放宽身份/来源校验。下一步取得实际窗口失败现场，修复搜索定位后继续原文→草稿→反馈及三业务验收。任务页状态区挤出“查看本次发现线索”按钮、判断时间仍显原始ISO等实机UX缺口一并保留待精简。未新增采集、判断、发送或来源核验记录；文档更新不重新构包。

搜索现场诊断增量：仅在失败后最多1秒读取控件数量/可见性，保存固定 `source-search-diagnostic-v1` schema与MISSING/HIDDEN/MULTIPLE/VISIBLE_AFTER_FAILURE/INSPECTION_FAILED原因到既有私有输出，不含页面、URL、账号或异常正文，不进入IPC/客户UI；写盘失败不改变清理。导航新增4项有效RED，worker新增1项有效RED后两个相关文件85通过/14.86秒；本地.venv启动受旧site编码问题影响，使用既有隔离Python及既有运行时测试依赖完成，未重装依赖。独立差量Spec/Quality GO，无P1/P2；导航blob `ce38a16a7e17479e075d42607a966e6934cf3f2a`、worker `1e1aa596196e3b5d18e8936eec77d288324d9273`。这是定位手段而非查看修复；须实装读取原因后再决定修复，不扩大搜索/采集范围。

## e688f2c 实装诊断（2026-09-14 11:19）

源码 `e688f2cee2bfb2834dfbf53e1257d3f4c7bf0562`；portable检查1通过/118.77秒，658项桌面输入仍为 `c746e962b053d150997f519dc63fb88796432faad0fabe65af93d882a7b7ccff`，Forge退出0。安装包 `D:/ykt914/make/squirrel.windows/x64/YikeAI-Setup.exe`，642866176字节，SHA256 `fbda500f24e1b1e6ee835b839b2f835d84dba2b8390735ea3ca357d0642923d2`。manifest `da764de09d816a0fd40ebfdec79343767d331d83f260363a3c5008c9973ae4e8`；40个renderer/main HTTPS/pin对包一致，安装退出0，实际ASAR `25fdd1cae5060e0f86e676c9dda371e7b8b5cac9b79c829f25350f0b75a14e93` 与候选一致，原登录/任务保留。

11:19:54真实客户端同任务同帖点击，输出 `13572741-6ebf-4388-a18a-6b50a88c3f29` 终态仍FAILED/SEARCH_UNAVAILABLE；本机诊断明确HIDDEN（匹配一个搜索框但不可见），不是MISSING/MULTIPLE。无SOURCE_OPENED、无新采集/模型/发送/核验记录。下一步检查该账号页面隐藏原因与真实可用导航入口，不能再猜改ID或仅增加等待；尚未修复原文查看，不关闭试用Goal。Windows窗口捕捉另受Chrome for Testing归属检查错误影响，已转为这条无原文/凭证的内部诊断；不要求用户重复授权。

## Chunk 3：已批准的实机界面减负（原文故障并未解决）

依据AUTHORITY客户界面标准及用户“所有页面技术细节隐藏、直接调整”的授权，采用原组件重排/折叠和既有日期格式化，不新建页面/状态机，不删除诊断和恢复能力。相比只改文案，默认折叠并把真实结果放前可直接减少首屏滚动；不选删除覆盖逻辑，避免丢失失败/未知证据。

- [ ] `desktop/src/renderer/pages/tasks/NativeCollectionTasks.tsx`：真实采集详情（状态、发现线索、取消/恢复）先于覆盖区；普通任务覆盖组件置于默认关闭的“查看搜索详情”details中，展开仍可检查范围/失败/用量，研究任务既有进度不变。`desktop/tests/ui/native-collection-tasks.test.tsx`先增加RED：真实详情DOM在覆盖容器前、details默认关闭且可展开、原查看线索/恢复操作仍在。仅相关文件GREEN及typecheck，不重跑全套。
- [ ] `desktop/src/renderer/pages/opportunities/CandidateAssessmentDetails.tsx`：判断时间复用既有`formatDate`，保留time.dateTime原值，客户可见文本不再原始ISO；未知/过期/草稿规则不变。现有候选UI测试增加RED验证可见文本与机器时间分离，修复后定向GREEN。无新增依赖或状态。
- [ ] 按subagent-driven-development实施、独立Spec及Quality差量审核，集中提交main；与下一实际修复批合并候选构包，原文HIDDEN不因UI通过而标已修复。以上不替代三业务真实闭环及用户认可线索门禁。

Chunk 3实现与限定验证已完成：两项有效RED后2个UI文件33项通过，typecheck通过；独立Spec/Quality GO，任务页blob `1530675e6fd2e518a40f4c5b881fb9ab8619650a`、判断详情blob `71cb3954c9940276d3009fd5f06697e995240d74`。恢复/未知/错误仍在折叠外。尚待集中提交构包及实机确认，不重复同字节检查。

## 新POST原作者定位前提（2026-09-14）

已核对固定上游store有意只存creator_hash，不是mapper漏读；本项目AUTHORITY要求公开原文/作者，既有mapper与同账号查看器支持原帖公开user_id。局部取舍：仅新采集POST保留原帖响应user.user_id的严格24位小写十六进制公开标识，缺失/非法仍None；不去匿名评论者，不扩充作者资料请求，不保留token/登录身份，不改旧数据或用hash猜作者。这是对上游匿名化的一处明确例外，并非无数据边界变化。

- [x] 最小补丁与锁摘要更新；既有POST mapper无需改动。新增8项先因缺user_id有效RED，初次GREEN尝试暴露测试缺collected_at，补齐采集包装层观察时间后，运行时及source-output两个文件98项通过/9.70秒，退出0；测试实际应用固定上游全部补丁并核对文件锁。
- [ ] 独立差量审核；与Chunk 3集中提交并构建一次候选，运行时须绑定新补丁而非复用旧锁。
- [ ] 实际客户端新POST采集后原作者页定位验证。此修复不解决旧记录缺作者，也不证明HIDDEN搜索入口或同帖网页访问已恢复；不得写为原文可用或上线通过。

独立差量Spec/Quality GO，无P1/P2：patch blob `3a15aafa118c732d58aa175dee2fcd7a1b013860`、lock `2e9e52981b3dcaa13983a8384146466dd914585f`、测试 `94f1270be55efb4ed9046fad4a05addd8f66bef2`。旧runtime输入的store hash不同，不能直接拿旧payload构新包；下一步准备绑定新锁的runtime，再集中构包，不改旧安装/会话或伪造旧探针回执。

## e5c4354 已构包实装（2026-09-14 12:00）

新建 `D:/yk-connect/runtime-e5c4354`，使用固定uv0.11.6完成新锁安装与实际本地CLI/浏览器检查（149.0.7827.55）；未复用旧安装回执。依赖下载等待期间同一进程持续存活，最终退出0。portable检查1通过/159.68秒，Forge退出0；658项桌面输入前后hash `b41aee9f33d0820bfd8397838804076e833843899b4839fea4b0ed3a350eefdd`。

EXE `D:/yku914/make/squirrel.windows/x64/YikeAI-Setup.exe`，642862592字节，SHA256 `8d21c3f6d4166ba318935b0650f897f3940f7c2df8f3ebcd31eb4fa83c4ef503`，NotSigned。manifest `a463d15eb6cfa2e7ecea8495562faa805cb30a410dbfc44bd48ffd28f8ea613c`；40个renderer及main HTTPS/pin一致，安装退出0，实际ASAR `8005fc434b2569460391d05a258f61ab9e013ca4bb7c30a4b030826eadea7b54` 与候选一致。客户端已启动，原登录及小红书连接保留；无服务端差量，不重复部署。

实际页面新建 `验收-AI原文定位-e5c4354`，AI软件定制画像、原有小红书账号、关键词“有偿求助 AI”、单次10条/300秒；已核对快照并提交一次启动。已观察到Chrome for Testing平台窗口，尚未获得最终采集/原文打开结果；不重复启动、不发送或写人工来源核验。后续须查原任务状态并从新POST核验原文，再接草稿反馈及三业务质量验收。

12:05:14创建的新任务实际完成9/10；从列表进入详情，状态和“查看本次发现线索”直接可见，两类详情默认收起。确认页没有自动转入结果页，虽任务已完成仍停留确认页，需后续修复这个实际体验缺口。

同帖 `6aa6534e000000002902df7a` 新采集版本已显示原作者 `6863dafd000000001b01be97`，没有从旧hash回填。12:07:59点击查看原文，输出 `8ddadac4-e148-41ec-bd2f-062c18901bf2/.yike-source-opened.json` 为SOURCE_OPENED，实际Chrome for Testing窗口标题“有偿有偿#gpt #ai #ppt - 小红书”，已越过此前HIDDEN搜索分支并定位同帖。Windows工具两次绑定均报“window id ... no longer belongs to Chrome; current owner is Chrome”，未取得人工可读截图，不写人工核验。12:09客户端按钮仍禁用，未见打开成功反馈；需继续确认打开事件是否及时到达客户端及窗口清理终态。该记录证明新原作者定位路径已有实际打开信号，不等于用户人工核验或完整试用通过。

### 12:20 普通任务跳转与原文反馈复查

普通TaskWizard原START路径只有保存回执，没有研究路径已有的导航回调。新增可选成功回调，在既有RECORDED绑定验证和双scope检查后进入真实任务详情；UNKNOWN保留原请求，不跳转不重发。新回归先证实RECORDED导航断言失败/UNKNOWN通过，修复后task-desktop-execution、desktop-execution、desktop-execution-list-busy共39项通过，tsc通过。独立差量Spec/Quality GO无P1/P2；审核blob为TaskWizard `9fe6896920a38f19f8774603388e6d73fa905397`、hook `515e7abdb9f27622cba99a94d69da456a732c180`、test `141abd210e1c879c7a344fb2fad0c7afaed393c2`。此修复尚未构包/安装实测。

12:17实际客户端已显示“已打开原帖”并恢复按钮，原viewer进程已退出。12:18:11再次从客户端打开同一原文，输出 `8380e01c-de14-49bf-8675-5a088122b598` 在12:18:20产生SOURCE_OPENED。后台快照仍显示按钮禁用，但主动切回意客后下一次新截图按钮已恢复；12:19:33同时核对原文浏览器与三层Python进程仍存活，排除了“必须等窗口结束才返回”的猜测。未为该猜测修改协议/计时；后台快照可能未刷新，不作为消息丢失证据。浏览器当前窗口91424438仍遇归属检查错误，未取得可读原帖截图、不写人工核验。继续推进新包实际任务导航与完整买方闭环，Goal保持ACTIVE。

### 13877eb 候选构建安装

固定源码 `13877ebf68248bdfb52f3104bb1944433c79eac5`，仅客户端变化，复用已验证runtime-e5c4354输入，新建绑定该提交的portable-13877eb-relocated。真实隔离payload检查1项通过（121.55秒）；Forge退出0，658项源码输入前后一致（`009df477142a1119f79e3f65a086b7df5ec9db088ceed63b2c43103aea9e7d68`）。40个renderer文件、主进程HTTPS与payload pin核对通过。

EXE：`D:/ykv914/make/squirrel.windows/x64/YikeAI-Setup.exe`，642865664字节，SHA256 `7e0f74088e10db7e836daf913c4b72a728c673c56d83f708651216b65fda8c7a`，NotSigned。payload manifest `e7875f8af77a9b3c2fb12607b5c38c323b92600ee07ae2e3e1b2c048cc84f17d`；包及实装ASAR均 `786b3b86662873d0cee84c7be99d76587851b1f668c08f25e6020a1e03a24b14`。正常退出时按用户既有授权丢弃本次测试会话草稿；安装器退出0。实际新窗口591248进入工作台，无需重新登录，显示小红书已连接；未写人工核验、未发送。服务端readyz正常，本次未改后端、不重复部署。仍待新包真实任务跳转与草稿/反馈完整闭环，不以安装成功标上线完成。

### 12:32 新包真实任务跳转通过，结果质量未通过

实际窗口591248新建 `验收-AI开发需求-13877eb`，既有AI软件定制画像、小红书账号1、关键词“求推荐 AI开发”、无排除词、单次10条/300秒。逐步核对并确认快照，只点击一次启动；客户端自动进入该任务详情并显示运行中，未手动导航，证实13877eb导航修复。12:32:33实际host启动，输出 `105b603a-33b4-4974-8119-5b9301bcf5f1`；随后客户端刷新显示已完成，进入本次发现线索显示8条。未重新授权、模型调用、发送或人工核验写入。

实际查看的两条评论分别为教程分享和模型连接讨论；原帖 `6aa6d968000000001203c385` 是100美元模型订阅比较求推荐，不是软件定制采购，不标为有效商机。其余候选仍需复核，当前没有新增获用户认可的买方。普通任务结果页需手动刷新才看见结束，确认页仍展开大量历史原请求；这些为后续定向体验改进候选，不借此次成功扩写为完整闭环通过。下一步优先更明确买方来源及判断/草稿/手工反馈，Goal保持ACTIVE。

### 12:38 已消费普通草稿导致新建入口回到旧模式

继续实际阅读 `6aa6b9dd000000000d024fce` 为汽车AI学习推荐，`6aa76f0d000000002a007b9a` 为软件公司的服务广告，均不是采购。随后真实点击“新建采集”却回到刚已完成的“验收-AI开发需求-13877eb”普通草稿，未进入默认研究模式；未重新提交该任务。代码确认useTaskDraft会恢复会话，普通成功路径此前只导航、不消费草稿。

修复仅在已验证普通START RECORDED与当前scope有效后消费同ID任务库草稿，并同步写入与useTaskDraft默认一致的新once研究草稿后导航；UNKNOWN保留旧草稿与原请求，不修改操作journal。新增断言先失败于仍为旧ID，修复后3个定向文件67通过、tsc通过。独立Spec/Quality GO无P1/P2（TaskWizard blob `152e00ce7ed05276d87f41030792e244e3992c98`，test `37c145993a568a6f891e86a4ff0383c8f92aa48a`）。本修复尚未构包/安装；当前已安装13877eb未追认为修复版，研究/监控成功草稿生命周期未纳入本批。新买方、研究筛选/草稿/反馈与上线验收继续，Goal ACTIVE。

12:40 同类研究路径定向复现：nativeResearch成功回执也保留旧草稿；新断言RED recorded旧ID失败，unknown/能力变化两项通过。研究成功回调补充同scope/同snapshot.id消费及默认新草稿，原研究journal与UNKNOWN恢复不变。两个相关文件22项通过、tsc通过；差量独立Spec/Quality GO无P1/P2（TaskWizard `a62c615f2e7acb918434b9144c58cac7c228cda5`，test `73135fc37a7d1f60a67fb24950c7983ffe50bb92`）。与普通路径合为一次候选构包；不把本地检查写成实机通过，监控路径不纳入本批。

### 13:01 新版实装与默认研究真实失败定位

当前客户端源码与远端main均为 `0c3211347af9c77b4a566b667ee7d176ef8cfe47`。实际安装ASAR SHA256 `f6edf645a9f5985088230c2983f6d4a0fc19bfd5e93f657fabdcb28cd8f82819` 与该候选一致；EXE为 `D:/ykw914/make/squirrel.windows/x64/YikeAI-Setup.exe`。新窗口124191718保留登录和小红书连接。实际创建研究成功后再点“新建采集”，名称和关键词为空、默认研究与100000搜贝保留，证明研究成功消费草稿的实机路径；普通成功消费路径未另跑重复任务。

通过真实界面创建 `验收-AI定制研究-0c32113`，采用已确认AI软件定制/全国线上交付画像、模型生成8个搜索词、推荐100条/900秒、公开网页自主研究、近60天、20来源/20模型调用/15分钟，估算55搜贝。确认策略后创建任务并自动导航，另点一次开始研究；未发送或重放旧请求。任务 `23c35558-274e-41a2-a5c3-86fb99bf6cea`，run `49872d1a-a355-4d1f-840e-6a6e7c636989`。

只读服务器回执确认12:57:37起6次MODEL成功、4次SEARCH成功；唯一READ为www.v2ex.com，12:58:13至12:58:19以connection_unavailable失败，12:58:30 STOPPED/no_verified_reads，0原文、0候选，无存活研究容器。最终模型称结果以供方官网/榜单/选型指南为主，V2EX外包节点不可读，然后输出空pages。客户端显示研究已暂停、候选0，实际用量仍待结算。此轮不能算价值或完整闭环通过。

新增实测待处理：建议仍偏服务名称；公开来源默认落在V2EX最新而非自主研究；确认页展开25条历史原请求；先提示估算、点击后又要求先确认策略，顺序不清。优先核对实际研究查询/返回来源/提前终稿逻辑与线上源码，不能再用换词反复跑或堆提示词替代根因调查。Goal ACTIVE；不修改旧失败记录、不将本次安装当上线。

13:07 只读追溯：四次真实query依次为“企业 AI 软件定制开发 需求 找团队”“找AI软件开发团队 定制企业应用 外包”“AI软件定制开发 询价 企业”“v2ex 外包 AI 软件定制”；各返回8–9条，主要供应商/榜单/旧讨论，尚无证据证明漏读了明确有效买方。唯一READ是宿主入口 `https://www.v2ex.com/go/outsourcing`，并非搜索结果中的具体笔记。public_search_worker直接将query发送为q，没有代码截断或替换。

线上research_stage_rules与search_suggestion_model的LF摘要分别为 `a87e0a3b974d00649da7a31644a1228460323bf3d18377d0316d7d4ed6a9a8e5` / `ddbf2de47e1843c78865589f46bcd6ea0a29cbd12198034f866a7f3ef742663c`，与main一致。实际首MODEL输入20243字符，包含“本地知识库 接手”“不只给同一品类查询追加”、connection_unavailable和本次业务上下文。排除未部署/规则漏传解释；提示词已经传到但未产生预期换场景行为。下一步需评估有界分阶段检索/候选入口选择，不再靠同一提示追加或强读无关页凑通过；所有来源真实性、预算、取消/未知门禁及零结果的诚实表达保留。
# 2026-09-14 接续：实机两处冗余说明

最新 main 仍为0c32113，实装版通过任务列表→原始线索→筛选“有偿有偿”→查看原文，出现对应标题的Chrome for Testing窗口。Sky两次窗口绑定均报“no longer belongs to Chrome; current owner is Chrome”，不能取得正文截图，未保存人工核验或宣称原文验收通过。

按用户已批准的全页去技术说明要求，本批只删TaskWizard排除词中的实现提示；Opportunities任务范围说明缩为“本次任务发现的线索（展示最新内容）。”，保留返回任务按钮、任务筛选、原文和所有实际风险/确认门禁。不新增折叠说明或修改布局。使用设计/计划技能合并记录，避免为两处文字生成多份文档。

- [x] 现有task-wizard与task-result-navigation测试先断言无旧技术文字，RED两项均按预期失败，再最小修改两处JSX。
- [x] 两个定向UI测试53通过（5.67秒），typecheck退出0，独立Spec/Quality GO；不据此宣称研究质量改善。
- [ ] 与后续候选集中构包，当前已安装0c32113不追认为含新文字。

# Windows 最新主干接续（2026-09-12）

## e1bee5a 已构包并覆盖安装（2026-09-13 08:23）

- 修复已推Gitee main，候选固定 `e1bee5aaddff0676592c2fa103ca61ed0e954aa9`。独立LF工作树构包，637项源码输入前后摘要相同 `112e6b63dc53ce5ac80d6e5f243d20ce0d8787625bdb6a77be8aac9ec5fb7e30`；Forge make退出0，既有Vite兼容/弃用警告保留。
- payload真实生成、搬迁、独立Python/Chromium验证1通过/0跳过，197.32秒；XML `.runtime/portable-release-e1bee5a-test.xml`，清单SHA256 `91b09326b10e9a620ca028952e70d390f69aea2b6e6ee6f3fa2bdb40b01b6134`。ASAR结构及40项renderer资源通过，SHA256 `94b704091a990d0a7c173f6cfe9d92d970507a8fa0e503e4dc9736b8433d01cc`。
- 安装器 `C:/yke1be/make/squirrel.windows/x64/YikeAI-Setup.exe`，642862592字节，SHA256 `2fc9f1f35b740e3b928790877cf9534047bd5cc757bfd74bfb994255dc5ade15`，仍NotSigned。旧PID31788正常退出，Setup PID21816结束（重开进程句柄未取得退出码，不能写exit0）；新安装ASAR/payload清单均匹配候选，实际启动PID23172。
- 实际新版显示已登录、AI软件定制/全国线上交付画像已确认且完整保留；未清空任何用户数据。08:24本机运行环境仍在准备，身份状态NOT_PREPARED，确认重启后的本人核验门禁仍存在。需要本人设备确认后再走正式连接CHECK，不把此前受治理源码探针AUTHENTICATED当成客户端已CONNECTED；没有真实采集/发送。服务仍2a85dbc，未随本地修复重复部署或启用新研究模式。

## 小红书已登录误拒绝已定位和修复（2026-09-13）

用户反馈已登录仍卡住。受治理、同一专用本机profile的只读探针连续三次确认：官方页面HTTP200；旧XPath匹配4个链接，精确可访问名称“我”的link只有1个，唯一可见且href符合原严格格式，无query/fragment。不是要求用户再次扫码或再次核验设备。

修正登录前后两处self定位，不放宽官方域、严格pong、唯一可见账号、href或停止后核验。新增回归先实际BLOCKED_INPUT失败；修复后worker26通过（含已安装runtime受控HTTP）。实际当前源码+原已安装runtime+已有profile，仅允许现有会话读取、禁止进入交互登录的探针返回AUTHENTICATED、valid_account=true，监督进程exit0，停止后profile核验通过；不记录账号、Cookie或原始响应，不登记连接/采集/发送。现有安装包仍0d9500b，须新包升级后确认产品连接状态，不能把探针成功当UI闭环完成。

同批关闭默认服务错误导入可选MCP的P1：仅改为导入同一中性校验函数，隔离进程先实际MCP导入失败后通过。定向合计66通过/64 POSIX跳过，补充reader+默认启动59通过；XML为`.runtime/login-import-batch.xml`及`.runtime/reader-import-green.xml`。独立差量GO，绑定worker `f2e8daabaf554d67b65aeea12332d696a68ca01f`、登录测试 `e12d411efd6c14a7b246ef3b1fa8cd837e25a12d`、research worker `91f839939838f7d8bad38ebeb8d11538cd6a92d7`、默认启动测试 `4b8d21f9e9fe36b281d7d497b465ad403e480344`。新包/新服务器镜像和39→43升级仍待验证；不重复部署当前2a85dbc服务。

来件61472b9的Windows定向129通过/1个Python回执交叉夹具未配置跳过，tsc退出0，证据`.runtime/win-incoming-61472b9.json`；不把上游新研究能力追认到旧服务或旧安装包。

## 0d9500b 本人核验后的小红书实测（2026-09-13 07:57）

本人操作后，已安装客户端实际显示“上次身份核验通过”，设备编号与前版相同；未重启、构包或代提交核验。正常连接入口成功打开小红书 Chrome for Testing 窗口，已越过 DEVICE_NOT_READY。

本轮输出 `07b6594e-f669-4d43-9a13-e65b27f2539b` 的 OPENED 标记时间07:55:58，终态07:57:16为 `BLOCKED_INPUT / PLATFORM_ACCOUNT_UNVERIFIED`。07:57:37复查原host/worker进程均已退出、浏览器窗口关闭，客户端显示“连接未完成／未能核实当前平台账号”，检查连接按钮禁用。支持本轮失败终态已反馈，不证明登录、取消或采集成功。只读安全终态字段，未读取Cookie/私钥/平台消息。

待确认用户是否已看到登录成功页面，并取得账号自链接匹配失败的具体分支证据；当前错误码可能来自自链接数量、可见性或URL格式，不凭此推断具体根因或放宽身份校验。此前后台只读UI观察持续显示“正在打开”，未排除UI辅助功能快照刷新时机，不冒称已定位新的等待缺陷。显示澄清修复7798d80已在main，仍未追认到0d9500b安装包；无真实采集、模型调用或外发。

## 固定候选0d9500b已构建并覆盖升级（2026-09-13）

- main合并内部研究来件后固定 `0d9500b29f5f35a6b7d3a7dadef9c508ee640164` 并推送。该候选包含 ed0dab1 登录只读STATUS、916df9c 小红书等待本人登录顺序、948c4f1 档案枚举后文件消失时完整重扫；三批均独立GO。后者仅原生error2的已枚举浏览器后代触发，最多三轮，ACL/根/祖先/硬链接/重解析点及严格runtime/output策略不变。[根因、RED和限定证据](../superpowers/plans/2026-09-13-browser-profile-rescan.md)。来件pilot研究资源接线未进入本地host清单，不追认其客户能力，也未重复部署server（仍2a85dbc）。
- 本批原生目录检查58通过/1跳过；登录/采集调用方57通过/1跳过（未指定真实runtime opt-in）。文件symlink权限跳过保留；旧两批相同字节沿用原定向证据，不重跑桌面全量。真实匿名官方首页200→USER_LOGIN_WAIT→35秒Job超时物理停止后即时档案核验通过；此轮未采集内部重扫次数，不冒充实际账号登录。
- 新payload `.runtime/portable-release-0d9500b-relocated`，清单SHA256 `d4ce1becebab38c95b8e8b8fc54af15ff1e7c5d887e990d13d2d53ae1a22e071`。真实构建/搬迁/独立Python与Chromium验证1通过/0跳过，133.82秒，XML `.runtime/portable-release-0d9500b-test.xml`。一次Forge make退出0；625项源码输入前后摘要一致 `4ee67bbc85d863ba6f951aa4710c7e8ebdddda1213e4edf7672f529ee7b3fbe9`，受支持Node24.19.0与短TEMP/SQUIRREL_TEMP。
- 安装器 `C:/yk0d95/make/squirrel.windows/x64/YikeAI-Setup.exe`，642855424字节，SHA256 `b58cdc08f74d1268fda589fccb93a12b387d6f19ffbcccf9416d085ff447f83c`，仍NotSigned。ASAR结构及40项renderer资源检查通过，SHA256 `79a4716f625ba451451934d83d23b91eca263c316b19dd1a9ab6b7d66034bf53`。Vite未来配置兼容/弃用警告未隐藏，不是本次构建失败。
- 实际正常退出旧安装版，Setup退出0；新安装ASAR与payload清单均匹配候选，主进程31788。computer-use读到工作台、已登录及本机运行环境已准备好；旧业务草稿完整，按用户提供的AI软件定制/全国线上交付完成画像版本1确认，页面回读已确认。无采集、模型调用或外发。
- **下一步阻点：** 新进程的设备状态仍为“尚未完成绑定核验”，停在“设备与使用授权”页，需本人核验本机身份。该重启后重复核验体验未改善，不以本批发布通过；新版安装态的平台登录STATUS/本人认证/真实采集→证据→判断→批准发送→跟进仍待验。签名和客户验收未完成，Goal ACTIVE；其他旧工作树实例未动，用户档案/历史runtime均保留。

## 固定候选2a85dbc实装与主干回归（23:48接续）

- Gitee main实际fetch确认 `2a85dbcb68b121f6e8051ccd72b29954f3f2a655`，干净LF工作树 `.worktrees/win-release-2a85dbc`。625项桌面输入构建前后摘要相同：`e20f0c568dab0da656c78c68b7e0db1ae6e0564378ffaa8babd20a2ee034a237`。本批仅一次完整Forge make，使用短TEMP/TMP/SQUIRREL_TEMP及输出目录。
- 新payload真实构建/搬迁测试 **1 passed / 0 skipped，132.10秒**，XML `.runtime/portable-release-2a85dbc-final-test.xml`。首次Git入口、随后测试venv依赖的hardlink预检拒绝均发生在生成输出前，保留失败XML；改用既有Git/bin/git.exe及经当前锁168项摘要核对的旧host依赖，不放宽门禁。清单SHA256 `a5d62db1d540bf3f7414e5147958b6a217501e4b094be12778b7aac0b49a2558`。
- Setup `C:/yk2a85/make/squirrel.windows/x64/YikeAI-Setup.exe`，SHA256 `3e8257dd62b6ee77241224f466f81c4b1dc03f6cead57495e4b9aefe8168af7e`；ASAR结构及40项renderer资源通过，SHA256 `3f7124cafad8b086315686f249be4ccda53c06347294e252c2728ccb62407111`。Setup exit0，实际安装ASAR及payload与候选相同，安装进程PID12176，账号已登录；旧画像草稿升级前已实际回查完整。仍NotSigned。
- 旧7599正常关窗后残留后台进程；确认无其平台Python/Chromium后，仅停止已核实的旧安装版4个进程，未删用户数据或操作旧工作树窗口。新安装版运行环境实际READY。新进程身份仍NOT_PREPARED；用户本人完成核验后，实际弹窗显示“上次身份核验通过”，本机编号保持49dc5d0c-28dd-4083-a26c-5d86fbcdf7e1。每次重启重复核验、外层“尚未完成绑定核验”易混淆的问题仍未修。
- 当前main桌面完整回归 **4017 passed / 0 failed / 33 skipped，共4050项**，`.runtime/windows-full-2a85dbc.json`，Node24.19.0、maxWorkers2。跳过包含需真实HTTP/PG/账号的场景、负例包optin、文件symlink及非x64分支；不能写全功能通过。其中实际Python确认签名互验已额外指定解释器补 **1 passed**，该定向命令的13项过滤跳过不增加完整回归未验总数；TypeScript通过。服务端差量4模块 **40 passed**，`.runtime/source-plan-release-2a85dbc.xml`。不相加重复样本。
- **新实机失败：**小红书两次输出目录357b18f4-99d1-4fcb-aec0-b5d97f9c9e55、beaefd6b-cbd4-4f11-9d1e-070e3b17c227均有OPENED标记，随后FAILED/PLATFORM_RESPONSE_CHANGED，未认证、无剩余平台进程；界面仍显示“等待登录”，没有主动同步终态。仅查看安全终态字段，未读取Cookie。正常取消后抖音实际浏览器窗口8652860出现，证明此时没有再被旧SOURCE_STOP_FAILED全局锁死；不能据此宣称全部ACL/平台登录验收完成。
- 抖音窗口触发Windows的Chrome for Testing网络权限提示，交由用户本人处理，不自动改系统安全设置。CUA尝试只读定位该浏览器仍报同名owner冲突；已停止该窗口自动化，未读取/提交验证码或操作认证。平台认证、真实采集→原文→判断→逐项批准联系→回复、重启后的完整体验、签名及客户验收仍未通过。服务器已同源更新，见[部署记录](SERVER_137138_DEPLOYMENT.md#当前customer2a85dbc2026-09-12-2342)。

23:51补充：用户本人关闭系统权限提示后，抖音最终为BLOCKED_INPUT/PLATFORM_AUTH_REQUIRED，界面显示等待超时，未认证；取消后无平台残留进程。B站实际窗口4000284打开后主动取消，窗口和Python/Chromium退出；随后知乎主窗口395860及附属微信登录窗口47384730出现，从意客AI取消后同样全部关闭，未操作附属认证页。新runtime清单创建/修改时间23:32:25。以上支持跨平台失败/取消后可以继续打开下一平台，不证明三平台认证或业务成功。

### 收尾主干来件 f9fc299：源码已合入，客户候选不变

本轮同步新增内部公开研究 Worker / Responses bridge，产品差量仅两个 pilot 模块及对应测试，不涉及桌面、平台连接器、迁移或部署配置。保留来件独立审核与 POSIX 证据，未将其追认到当前服务器/安装包 `2a85dbc`，不重复构包或部署。

Windows 独立锁定 research wheel 环境追加两模块测试：**26 passed / 2 failed / 21 skipped，14.93秒**，原始 `.runtime/domestic-harness-windows-f9fc299.xml` 保留。21项为云端 Worker 明确仅 POSIX 的模块跳过，不是 Windows 客户端验收通过。两个失败尚未修复：超限请求在本机收到 WinError10053 / httpx.ReadError 而非预期413响应；SSE滴流测试已收到408，但0.8秒断言包含 bridge 与模拟上游 shutdown，实际约1.03秒，需拆开响应与清理耗时进一步核验，不能直接认定真实请求突破截止时间。未修改限制、放宽断言或把失败改成跳过；此内部模块未接客户入口，后续按其 POSIX 运行范围处理，不阻塞优先排查小红书与登录终态显示。

知乎取消操作的浏览器/Python退出已核实；首次坐标点击后弹窗仍可见，随后用新UI状态定位关闭按钮才关闭。尚未区分首次输入未送达和界面问题，不能记为已证明的产品取消缺陷。业务画像草稿“AI软件定制／有明确AI软件定制开发需求的企业／全国，支持线上交付”在新安装版回读完整；尚未确认画像或启动真实采集。

## 1e554df 同步及浏览器档案核验修复（尚未入安装包）

- main 从 aa50a92 快进到 `1e554df9358bca3fd7b66652e16fffb2a60faa92`；新增公开 reader/MCP 工具在独立锁定 wheel 环境 **65 passed / 0 skipped**。两项超长参数测试最初因 Windows 环境变量32767字符限制产生4个 setup/teardown错误；补短 ids，不改输入/断言。首次editable环境中文pth被GBK解码失败保留，最终使用新建no-editable环境，未污染候选依赖。日志 `.runtime/research-tests-1e554df-20260912/research-tests-wheel-fresh.log`。
- 档案核验根因补全：并非仅Cache。真实已停止档案100个节点包含网络LPAC、同主体重复授权、文件deny execute。新增 profile 专用只读策略，仅四个固定网络子树允许经官方149源码及实机核对的固定capability；根、runtime/output、owner/links/reparse保护保留。login/source/outreach前后profile核验统一切换。设计与计划见 `docs/superpowers/specs/2026-09-12-browser-profile-acl-design.md` 和同名plans文件。
- 原生NTFS与三条host定向测试 **128 passed / 2 skipped**，XML `.runtime/windows-profile-acl-1e554df.xml`；跳过为文件symlink权限不足、真实runtime需显式optin。后者补指定实际已安装runtime独立 **1 passed**，因此只剩symlink权限项未验。新增正例先红后绿；host旧loopback夹具同步profile核验入口，另修两处旧超长参数ids。独立审核同批及追加差量GO，无P1/P2。
- 真实用户档案仅只读安全元数据复核通过，未读取Cookie内容或更改ACL。用既有已校验7599 runtime，在全新 `C:/ykt7599/yike-acl-ywdj0s8d` 合成档案运行带sandbox的headful Chromium空白页，连续两次启动→Job物理停止→档案核验均PASS；不是平台登录。探针 `.runtime/probe-browser-profile-roundtrip.py`。首次探针误把bundle父目录当runtime导致预检拒绝，修正为其runtime子目录后通过，未放宽运行环境校验。
- **交付边界：服务器和安装包仍是7599e93。**本批修复未构包、未部署；真实平台授权、安装版取消/换平台、新进程设备NOT_PREPARED体验、签名与客户完整闭环仍未完成。旧失败证据保留，不写成已对外上线。

## 7599e93候选与后续main同步（2026-09-12 22:39）

### 实际构包与升级（22:48接续）

- 补齐短 `TEMP/TMP/SQUIRREL_TEMP` 后同字节封装成功；前一次NuGet已通过但Squirrel自身解包长路径失败也保留。原产品只编译一次，封装重试均核对11231文件和固定源前后摘要。Setup `C:/yk7599/make/squirrel.windows/x64/YikeAI-Setup.exe`，642844160字节，SHA256 `b18c32e6ba6425c3eefe34c6e1efc1b9d54b1a235ef7c8e2a9ddc9bf48fed293`；nupkg SHA256 `289e216260eae22a2b485e78042452dc79af8ef953e7e642f58d81b7ac5e0bd3`。仍NotSigned。
- ASAR结构与40项renderer资源通过，SHA256 `ed74208cded25e7444e56681428d71ec183559608a8940766616187b3de37453`；payload清单SHA256 `54af2bc257f502eb23ba9641b671a0e740e1f3e5ddc3a2c2e970fd0ea8f8cbce`。短目录应用实际首次启动到READY，用户已登录；填写并保存“AI软件定制/有明确AI软件定制开发需求的企业/全国，支持线上交付”画像草稿，未确认或启动采集。
- 旧1f597f6在登录失败后的退出防护留下无窗口后台进程；实际确认没有任何平台Python/Chromium工作进程后，仅终止原已确认PID19320，未删用户文件。新候选正常退出通过。Setup PID22216 exit0，安装后ASAR及payload完全一致；实际安装版PID27912已登录、READY，runtime清单仍22:44:40，未重复安装。
- **未解决体验缺口：**新进程设备身份初始NOT_PREPARED，平台页runtime READY会让用户误以为全部就绪。实际首次打开小红书仍返回DEVICE_NOT_READY；CodexWin经正常核验面板完成当前账号本机检查，返回同一设备编号49dc5d0c-28dd-4083-a26c-5d86fbcdf7e1/READY。未绕过身份校验或读取私钥。核验后浏览器/真实登录仍继续验证，不把设备READY写成平台连接通过。
- **22:57真实平台阻断复现：**核验后安装版确实打开“小红书 - 你的生活兴趣社区 - Google Chrome for Testing”，实际运行的是短物理目录中的Chromium，输出OPENED标记；没有完成用户认证，worker终止标记为BLOCKED_INPUT/PLATFORM_AUTH_REQUIRED。等待结束后所有平台Python/Chromium进程均已退出，但下一次抖音OPEN仍被SOURCE_STOP_FAILED拦住，没有产生抖音worker，不能声称抖音已打开或平台授权通过。
- 只读安全元数据诊断确认：原小红书profile的 `Default/Cache` 被Chromium增加两个同一应用能力SID的缓存访问ACE，而 `verify_private_tree` 要求每个目录恰好只有用户/SYSTEM/Administrators三项全控ACE，因此profile校验失败；本次输出目录校验通过。没有读取Cookie/账号文件内容，没有修改ACL、删除缓存或跳过安全校验。复现脚本 `.runtime/probe-login-acl-7599e93.py`，原平台结果保留在用户目录；后续需区分浏览器缓存边界与凭据目录，修正错误归类/退出恢复后做定向实机复验。另computer-use的Chrome窗口身份匹配两次返回同名owner冲突，停止该窗口截图操作；窗口标题、进程与OPENED文件可证明浏览器出现，不证明认证页面操作成功。

- 登录启动修复已提交推送 `7599e93`，随后保留本机测试修改、快进到 `36a3f99`。新来件复用其独立审核，在Windows追加7文件 **51 passed**、类型检查通过，后端source-plan单元 **14 passed**；公开计划实网效果未验，未纳入下述固定候选。
- 固定7599e93桌面全量原始结果 **3986 passed / 4 failed / 31 pending（4021项）**，保留 `.runtime/windows-full-7599e93.json`。四处失败分别为Windows文件URL根路径、research能力夹具、画像加载时序、旧公开来源文案断言；测试修正后定向 **21 passed**、类型检查通过，独立GO。不写成全量重新通过，31项未执行仍保留。
- 后端全量初跑受CRLF归档、旧环境缺SDK/uv、旧宽授权夹具影响，中止时 **1669 passed / 38 failed / 69 errors / 24 skipped**，原XML保留。改用LF归档及独立锁依赖环境后关键批 **165 passed / 2 failed**；其中旧git历史测试在实际本机仓库 **1 passed**，授权边界改用生产形状受限测试角色，连接3模块 **69 passed**。HTTP/PG/备份/部署/采集定向批 **145 passed / 1 failed**；失败为精确capabilities集合漏掉已存在access_login，修正后该模块 **3 passed**。PG夹具改为同语句时间消除600秒等值微差，生产约束未动；两处独立GO。不相加重复样本、不宣称剩余全仓已验。
- 新固定LF工作树 `.worktrees/win-release-7599e93`、全新治理runtime `.runtime/windows-runtime-7599e93`；payload真实构建/搬迁测试 **1 passed / 0 skipped，178.28秒**，清理旧pytest临时目录权限警告保留。应用编译完成；Squirrel两次长路径和一次包装器cwd图标失败后，复用同一11231文件并全量摘要核对，改用短临时/输出目录继续制作安装器，不重复编译。此时旧安装版仍1f597f6，新包实机升级/登录窗口验证未完成。
- customer7599e93已实际部署，备份/37→39升级/受限权限/旧服务兼容/内外网ready通过，详见[部署记录](SERVER_137138_DEPLOYMENT.md)。生产配置及ops不变，无模型或平台外发；用户账号、旧runtime/profile保留。

## 同步0fe86ac与登录启动阻断（本批尚未入包）

- 按用户要求快进main到 `0fe86ac70344bd4f10f56f4d651e48dd0a33c8d5`，保留本地测试/记录。安装版仍1f597f6、customer仍5fb7d65，不追认新源码已部署。
- 安装版设备身份已实际显示READY/核验通过；小红书登录已越过设备门禁，但没有出现登录窗口，最终SOURCE_STOP_FAILED。仅检查脱敏终止标记及进程，未读Cookie或私钥。隔离空白profile复现Chromium `spawn UNKNOWN`，Windows SideBySide/WinError14001确认启动依赖解析失败。
- 同浏览器字节对照：无界面shell通过；旧逻辑目录、短逻辑目录和旧长物理目录的真实crawler有界面启动失败；短物理目录有界面启动、关闭均通过。MSIX虚拟AppData需 `realpathSync.native`，且原安装目录过长。bootstrap改为用户目录下 `r/<完整64位清单摘要>`，创建parent后解析物理路径，原源/目标校验、私有权限和停止门禁不变；旧runtime、用户账号与profile全部保留。
- TDD先2失败4通过，最终bootstrap/payload/login-driver **45 passed、tsc exit0**。原两个Node→Python夹具先因未配置解释器、随后因无editable安装缺connectors失败；夹具显式补项目根，仍验真实host parser/emitter/EOF，未扩大浏览器模拟。独立审核GO：bootstrap `e16b1dfba9ae1bb53addeaf30ca8a45ae7614a39`，测试 `54d54656cfb8c5ff409ed68fcf5e7aeb4f2a8763`，host夹具 `c4c26123a0266ca77413897a0f725163c1adcfd6`。新包实际bootstrap、登录窗口和重启复用仍待执行。
- 普通候选入库回归采用上游b2cb7f6修复，不重复修改生产代码；额外保留省略context/显式null/伪造字段和HTTP夹具回归。最新0fe86ac相关 **195 passed**。此前隔离同机真实PG上3个HTTP模块 **6 passed**、签名/租约/fence/原子/并发重放 **13 passed**，对象为28872dc加当时等价修复的隔离测试源，不冒充最新main全量PG通过。Windows跨网络初跑3失败3通过、旧测试依赖两项收集错误均保留；测试未接生产库。

## 真实用户登录接续（同一1f597f6安装包）

用户本人完成临时访问码登录后，computer-use实际观察安装版进入“客户工作空间”；正常关闭并重开同一安装版后仍保持登录，无需再次输入访问码。账号页显示本机运行环境已准备好。这补充下方构包时“未登录/未验已登录重开”的历史状态，不重复构包、不把源码main新增能力追认到旧包。

用户确定首轮业务为“AI软件定制”，地区“全国，支持线上交付”。当前画像尚未填写、确认或启动任务。用户接手小红书与抖音授权，安装版已打开“账号与授权→平台连接”；本次只读回查仍为未连接，不能提前记为授权通过。后续继续真实采集、原文证据、判断、草稿及跟进；真实评论/私信必须先确认对象、渠道和文案。签名与客户验收仍未完成。

## 候选判断页面超时修复（接续3b23658）

同步Gitee至 `3b23658` 后，实际页面调用链仍有30秒UI等待，早于主进程ASSESS的75秒预算；因此45秒成功结果会被页面丢弃。仅将首次ASSESS和明确重试的review等待延至90秒，原请求查询（含重试前GET）、人工复核和来源核验仍30秒，身份/台账/人工确认/防重复机制不变。

真实hook＋服务解析＋限时函数的回归先3 failed（两种45秒成功及90秒边界），修复后hook/候选页面/serviceClient共 **62 passed**，TypeScript exit0。覆盖requestId、retryOf、唯一子请求、超时保留PENDING及忽略晚回执；非作者 `win_test_review` 独立GO，审核blob分别 `4b27aa932bc73786c9565edf55a4419c9b16241b`、`b0741953556822371f45b379d99052dcac4c2049`。这是可控慢响应测试，不是实际模型/用户操作验收。

原3b23658 payload准备通过1项真实搬迁测试，但发现此阻断后未制作安装器；保留该产物，不混入修复后的新候选。下一步固定本次修复SHA，只构建一份同源Windows包。服务端与当前5fb7d65无产品差量，不重复部署；真实登录/平台/外发/签名/客户验收仍未完成。

### 已构建并覆盖升级：1f597f6

- 固定源码 `1f597f61a2886d84aff844dd5103b72dff585f30` 已推Gitee main，干净LF工作树 `.worktrees/win-release-1f597f6`。与上一5fb7d65的产品差量仅主进程ASSESS75秒、页面ASSESS90秒。customer保持5fb7d65，实际revision/healthy/重启0及公网 `/healthz`、`/readyz` 通过；首次误查不存在的 `/health` 返回404，改用已有部署合同端点确认，不改服务。
- 新payload `.runtime/portable-release-1f597f6-relocated`，清单SHA256 `6072ca57d74006e1143060d289be458938080e3d7f5845e2988d998d0042eccb`；真实搬迁/独立Python/Chromium检查 **1 passed / 0 skipped，200.13秒**，原始 `.runtime/portable-release-1f597f6-test.xml`。
- 一次Forge make exit0，ASAR结构与40项renderer资源通过，SHA256 `cd4ffe72db1974252d16b6196a5c7bc69355d348b37671e0255b538fe60f9b25`。安装器路径 `.worktrees/win-release-1f597f6/desktop/out/make/squirrel.windows/x64/YikeAI-Setup.exe`，642,811,904字节，SHA256 `54d3f14f77c0c0194ecc49d4227adb787ad90afc70b14b2b7a468163bc140ad7`；nupkg 646,499,070字节，SHA256 `e3c0c0a23b63ea564a835d5b738a385a52b658fa0b090aa22da562b4a3bd8060`。仍NotSigned，Vite未来配置兼容警告未作为本次阻断。
- 正常Alt+F4退出已核对的旧5fb7d65安装版，确认主进程结束及旧ASAR一致后，Setup默认路径覆盖升级exit0。安装后的ASAR/payload清单与上述摘要相同，卸载登记为意客AI/0.2.0。用户数据和历史runtime均保留；未重复卸载重装全套。
- computer-use实际打开新安装版首页，转入账号与授权，首次准备最终显示“本机运行环境已准备好”；新runtime清单创建/修改时间18:06:05，摘要与冻结清单一致。启动工具仍因MSIX映射路径报告无窗口，重新枚举后定位实际安装进程，未重复启动。新包重开未重复验，沿用旧版同字节运行机制证据，不冒充本版已登录会话恢复。真实登录与平台业务未执行，安装版留在账号页等待用户本人完成登录/平台认证，完整Goal未完成。

收尾同步 `28309ac` 原生链接输入来件：复用该批独立GO，Windows追加解析/策略/历史恢复 **TS107 passed＋tsc**、新原生URL解析 **Python84 passed**；仅两份状态文档冲突，保留双方内容，产品无冲突。源码已整合，但新链接输入代码未进入本次固定安装包或customer，不重构/重部署。实际链接采集执行器仍待开发，不写成仅待账号验收。

## Setup 实装阻断与修复接续

Gitee 再次同步至 `0b5bcbd`，无新增提交。对 `1119985` 候选执行真实 Setup 安装，文件解压完成，但卸载登记失败：旧 .NET `System.IO.Packaging.Package` 把文档站中文 ZIP 文件名解码成重复问号路径。只读打开实际 nupkg 同样复现；此前“make exit0/ZIP可读”不能代表安装成功。

修复仅影响构建：仍核验全部固定源 blob，分发时排除未打治理补丁的 `docs/*.md`、`docs/static/`、`docs/.vitepress/` 文档站文件；保留运行配置引用的 `hit_stopwords.txt`、`STZHONGS.TTF`、代码、根许可证/NOTICE及依赖。任何其他非ASCII载荷路径在创建输出前失败关闭，不静默删改代码/资源。真实WindowsBase读包回归及3个非ASCII源/补丁/依赖拒绝场景先 **4 failed**，修复后整文件 **30 passed / 1 skipped**（仅非Windows拒绝分支）。修复后的实际候选及安装证据如下，不追认旧包。

非作者 `win_test_review` 本批差量 GO，无阻断项，确认固定PIN运行引用及patch保留逻辑；未重跑同字节测试，不把fixture探针当实际运行验收。

旧 `%LOCALAPPDATA%/YikeAI/dev-runtimes` 已确认是本任务历史开发探针，完整搬至 `.runtime/legacy-dev-runtimes-before-1119985` 留存，未删除。失败安装文件及日志保留；正式用户数据 `%APPDATA%/yike-ai-desktop` 未清理。仍待实际用户登录及平台连接；不读取验证码、Cookie或用模拟登录替代。

### 修复后固定候选 a56aab2

- 源码 `a56aab299f3c256e77b065c0347589eadb1d2dc9`，干净LF工作树 `.worktrees/win-release-a56aab2`，已推Gitee main。与当前customer `1119985` 的服务/迁移/锁/桌面业务代码无差量，不重复部署；本轮公网 health/ready 均200。
- payload `.runtime/portable-release-a56aab2-relocated`，清单SHA256 `4099eebef08f6d54bf480a5458fdca350b285effd48f94ffcaf9d56102e3eebb`。真实构建/搬迁/独立Python/Chromium探针 **1 passed / 0 skipped，133.72秒**；原始 `.runtime/portable-release-a56aab2-test.xml`。最终非ASCII文件路径0，停用词和字体仍在；原输入不改。
- 一次Forge make成功；ASAR结构及40项renderer资源通过，SHA256 `3cb96091131e79a72eda110047973259665a356c418b3b1ef8ae5099aab241fb`。产物在工作树 `desktop/out/make/squirrel.windows/x64`：Setup **642,809,856字节**，SHA256 `72e921f640eb643beb5b654cf08e4cfeb452a2863294410f766b540cf57dd484`；nupkg **646,496,223字节**，SHA256 `0092701def95adf73f6dfc6fa92e79e272509604b0a39f42d3063f1bfc9e25a0`。实际旧.NET Package reader成功枚举11197 parts。仍 `NotSigned`，当前用户证书存储无可用带私钥代码签名证书。
- 失败旧安装完整搬至 `.runtime/failed-install-1119985`；新版使用普通默认安装路径及默认TEMP，真实Setup于17:04:23–17:04:39完成、exit0，卸载登记显示“意客AI / 0.2.0”，桌面与开始菜单快捷方式存在。安装后ASAR与payload清单摘要完全一致。从安装启动器打开真实首页成功；CUA首次因启动器转交到版本子目录而报未发现窗口，经重新枚举定位真实进程，不重复启动。
- computer-use实际观察首次准备至READY；正常Alt+F4退出并核实主进程退出。随后仅对本轮已核对摘要的安装版执行真实卸载（exit0，注册项移除），使用同一Setup重装（exit0，注册项恢复）；旧Squirrel自己的`.dead`残留由正常重装处理，不手动清理用户目录。工作空间中该runtime清单始终保持17:05:21创建/修改时间及原摘要。重装后重开再次READY，安装ASAR保持原摘要；再启动一个真实进程迅速exit0，原主进程保留，未产生第二业务实例。Windows的CUA返回MSIX映射路径，进程盘点/摘要与实际 `%LOCALAPPDATA%/YikeAI/app-0.2.0` 一致，不误认旧工作树窗口。

当前可操作入口：桌面“意客AI”快捷方式或上述Setup；安装版已留在“账号与授权”页。**未通过项：**真实产品登录/已登录重启、平台连接/采集/原文→判断→批准联系→回复跟进、签名、客户验收。原文代码已有实现但本次未实际采集或发送，完整Goal保持ACTIVE。不能把安装验收写成正式上线。

收尾并发同步：远端新增作者证据来件至 `911d383`，与本批文档合并，仅任务书首部记录冲突、保留双方内容。产品代码复用来件独立GO；在Windows补签名器/公开driver/作者合同/原文解析4文件 **121 passed**，后端作者合同 **29 passed**，不重跑原实网/PG采样。来件已同步源码但尚未纳入本次 `a56aab2` 安装包或 `1119985` 服务器；保持固定可验收候选，不因收尾来件追认旧包或再次构包。

## 当前同源候选5fb7d65（2026-09-12）

源码固定 `5fb7d6529d723912046f7511e163f5a1a908f87c`，干净LF工作树 `.worktrees/win-release-5fb7d65`；customer已实际部署同SHA，见[部署记录](SERVER_137138_DEPLOYMENT.md)。旧 `a56aab2` 安装验收不追认新字节；本批包含作者原文上下文及排除/观察/过期判断隐藏草稿的已审来件。

- 新payload `.runtime/portable-release-5fb7d65-relocated`，清单SHA256 `fba3f3c0b6b998222b6a1f7b79b1d9a0e1cb27099fbbbc2f6ea0e006f273eb33`，真实构建/搬迁/无开发Python依赖探针 **1 passed / 0 skipped，136.68秒**。原始 `.runtime/portable-release-5fb7d65-test.xml`；输入来自已核验旧runtime/锁，不重复下载。
- Forge首次因命令误用manifest环境变量名而在配置加载前拒绝 `PORTABLE_BUILD_INPUT_INVALID`，未进入产品构建；改正为实际 `YIKE_PORTABLE_BUNDLE_SHA256` 后一次完整make成功。未修改构建门禁。Node24.19.0、短TEMP/TMP/SQUIRREL_TEMP、内置HTTPS；ASAR结构及40项renderer资源通过，SHA256 `b604c2fd0bc6b407775b0a56254e1cf88f2cedb6f5fab0276933293cd428f7af`。
- `desktop/out/make/squirrel.windows/x64/YikeAI-Setup.exe` **642,819,584字节**，SHA256 `8bd4a38e22210654ddcee70f19c360c34d3bdeb6e60036af0eb5e58319460eea`；nupkg **646,499,743字节**，SHA256 `a9665ccc76b1437f0cc71174fd45ba8722aafdbe57b9393d61bb9c5302096704`；RELEASES SHA256 `ca80841329833f9bfe7d9d60e40e2c05b4cfee56c91bc30c3b6a5ca448635ffa`。仍NotSigned，不解除对外发布签名缺口。
- 先核旧安装ASAR摘要并正常退出，再以同一默认安装目录运行新Setup（PID30976、exit0）；这是原0.2.0→新同号候选的实际升级，注册项保持，安装后ASAR与新payload清单均完全匹配。未清理用户数据或旧runtime；旧7d3bfe7工作树窗口未操作。启动器转交后的实际进程PID27424，computer-use确认首页、平台页和首次准备→READY；新runtime清单创建/修改均17:40:32。

正常Alt+F4退出并确认PID27424结束后重开，首次命令行隐藏启动未立即形成可见窗口；通过正常启动入口唤起同一PID32256，未产生第二业务进程。computer-use核实重开后平台页再次READY，ASAR摘要不变、runtime清单仍为17:40:32及原摘要，未重复安装运行环境。界面留在账号与授权，等待用户正常登录；CUA启动器映射路径的定位错误只按实际窗口重新枚举，不当作产品未启动或盲目重复安装。

真实用户仍未登录，未代填认证界面或读取验证码/Cookie，平台连接、原文→模型→确认联系→回复仍未验。公开样例不计客户商机，升级/运行环境通过不是产品正式上线；Goal继续ACTIVE。

构包期间并发来件至 `9d85ed4`：新增 `fb28f4b` 的客户端ASSESS75秒预算（其余请求仍12秒），已有独立GO及慢provider/真实来源判断持久化证据。当前5fb7d65安装包尚未包含该必要修复，可继续登录/连接验收，不能声称AI判断超时已修复交付。下一候选须包含它；服务端镜像输入无差，不再部署服务器，不重复来件实网模型或旧安装全套。

## 2026-09-12 主干同步与剩余旧回归收口

快进同步至 `cfa9301`，保留本机未提交测试修正；来件增加作者更新语义检查与排除/观察/过期判断隐藏联系草稿，复用其独立审核，不重复真实模型调用。本批只修改12个测试/隔离视觉夹具文件，不改变产品权限、发送或构建门禁，也不重复构包。

旧全量 `a7a9c4d` 的未收口失败集合在 `b36e4a2` 上重新运行：189项中171 passed / 17 failed / 1 skipped，另有Squirrel套件导入失败；原始 `.runtime/windows-remaining-failures-b36e4a2.json` 保留。根因为旧夹具未跟随结构化跟进/四平台/公开设备绑定、文案范围及源码绑定合同更新，不以放宽产品条件解决。

修正后在 `cfa9301` 加本批差量上，旧失败集合＋来件候选证据UI共15文件 **229 passed / 0 failed / 2 skipped（共231项）**，原始 `.runtime/windows-remaining-failures-cfa9301-fixed.json`；Node24.19.0，TypeScript通过。两项跳过分别是本机文件symlink创建EPERM、仅非x64平台适用的拒绝分支；非文件/目录junction保护仍强制运行。构建失败阶段用真实临时Git提交绑定，前后源摘要一致、真实npm退出37、后续阶段不执行；此前一次临时清理EPERM未再复现，未增加重试或吞异常。

保留 legacy 日程/跟进的明确兼容测试，正常回复证据仍通过真实结构化入口展开；错误成功回执不新增POST，公开设备变更阻止启动。非作者 `win_test_review` 按12个文件SHA256完成整批独立GO，无P1/P2；定向回归及类型检查均已完成。这里仅收口该失败集合，不宣称全仓或业务端到端全绿。当前线上health/ready实测通过；已安装 `a56aab2` 与customer `1119985` 的版本不追认为最新源码。接续为冻结新同源候选、差量部署/构包及真实用户登录后的业务验收；签名、平台实采与确认外发、客户效果仍未完成，Goal保持ACTIVE。

## 上一固定候选1119985（保留历史证据）

主干从 `04ac64e` 快进到 `11a640b`，保留并接续本机六项测试文件修改。服务器经实际 SSH 核对仍为 `fbf9f942df0c2be2189a98a930948f9f9b104b1b`、healthy；同步源码不等于新版已部署。

本批仅修测试：IPC 异步拒绝断言、重建采集 START 的失败关闭期待、Windows 文件 URL/路径、发送前真实保存草稿回调。文件符号链接测试在 Windows 创建返回 EPERM 时单独跳过；非文件拒绝、目录 junction 防写和跨进程一次性消费仍强制运行。未改变产品安全逻辑。

实际受支持 Node 24.19.0 上运行 deviceIdentityMain、foregroundCollectionIntegration、outreachConsumptionJournal、portableBootstrap、visual/recovery-pages、serviceSessionVault、ui/login、ui/phoneClient：8 文件，75 passed / 1 skipped；TypeScript 通过。跳过为本机缺文件符号链接创建权限，不记为该项通过。首次 Node 24.11.1 的同结果仅为诊断，不作发行证据。非作者 win_test_review 独立审核上述全部差量 GO，无阻断项。

## 固定候选与实机接续

冻结源码 `1119985b3dc4d85d908d76b3d18c35a9928ab827`，干净LF工作树 `.worktrees/win-release-1119985`；customer已部署同SHA，[部署记录](SERVER_137138_DEPLOYMENT.md)为准。正式客户端内置 `https://yike.tuokexing.net`。

- 新payload `.runtime/portable-release-1119985-relocated`，清单SHA256 `881f4df713754ea69b560952f5e015d8669a56b72f9bfc2c5ccca32f11dffe9f`。真实生成/搬迁/无开发机Python依赖场景 **1 passed / 0 skipped，211.79秒**；原始 `.runtime/portable-release-1119985-test.xml`。原 `.venv` 中旧editable中文路径的GBK解码在pytest启动前失败，改用无editable注入的既有隔离解释器完成；未覆盖旧环境或改产品。
- 客户端仅执行一次Forge产品构建，ASAR结构、40项renderer资源校验通过，ASAR SHA256 `760e6a4dc69c1aade0df85d74c8b30be7dc954c3b3b52c3bdabcdea11792b7b5`。新包实际进程与旧 `7d3bfe7` 窗口分开核对，旧包未被关闭或追认。
- computer-use实际观察：首页、账号页、首次“正在准备”至“本机运行环境已准备好”；正常Alt+F4退出，确认原主进程退出，再打开同一个EXE，页面再次READY。默认测试实例本轮安装清单创建/修改时间均为16:35:27，重开后保持未变。首次另启的隐藏实例使用全新 `.runtime/windows-ui-1119985`，与默认目录分离。这里验证的是Forge输出EXE、真实OS运行环境准备和重开，不冒充Setup安装或已登录会话恢复。
- 安装器封装首次NuGet因长路径失败；第二次只设短TEMP/TMP，NuGet成功而Squirrel自己的解包路径仍过长。均仅失败在封装阶段，保留真实失败，不重跑产品make/package。后续重试用 `--skip-package` 复用同一ASAR/payload；同时显式短TEMP/TMP/SQUIRREL_TEMP。Squirrel专属变量依据[上游实现](https://github.com/Squirrel/Squirrel.Windows/blob/develop/src/Squirrel/Utility.cs)，不能仅设置普通TEMP宣称已解决。
- 第三次仅安装器封装成功（exit0），产物目录 `.worktrees/win-release-1119985/desktop/out/make/squirrel.windows/x64`：`YikeAI-Setup.exe` **651,582,976字节**，SHA256 `9ef0abd0a995042f4038c7dbf81fee2c5e19d837ec8f82a78ccc4d2077e01d6b`，签名状态 `NotSigned`；`YikeAI-0.2.0-full.nupkg` 655,270,485字节，SHA256 `de9dd45c7e5510af1f9573c184c0cbfe3619a8afc39ae0e32a1af422190b6e6a`，另有RELEASES。实际打开nupkg核对ASAR及payload清单与上述固定摘要完全一致。客户端没有重复构建，代码字节未改。
- 隐藏隔离测试实例已停止，测试数据和旧产物保留；可见重开实例留供正常登录。重开后仍显示READY，既有清单创建/修改时间未变；尚未验证登录会话的重启恢复。

本机Windows可用，旧交接“等待Windows环境”不再描述当前状态。未获得本轮真实登录凭据，界面保持需登录；Setup安装、已登录会话恢复、真实平台采集/原文/判断/草稿/逐项批准发送和客户效果仍须实际验收，完整Goal保持ACTIVE。默认 `%LOCALAPPDATA%/YikeAI` 已有历史dev-runtimes，不在该目录执行可能清空旧内容的Setup全新安装；需隔离安装环境后单独验收。

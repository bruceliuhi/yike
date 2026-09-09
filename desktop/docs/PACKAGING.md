# 桌面构建与验收

此目录交付 Electron 客户端和固定业务 API 桥接。它不包含采集 sidecar、平台连接器、短信登录或消息发送服务。`getRuntimeStatus()` 仍返回 `LOCAL_SERVICE_UNAVAILABLE`，不能用打包成功证明这些业务已接通。UI 和服务端的实际范围以仓库的 R3 实施记录为准。

## 构建前提

- 使用 Node.js 24 和提交的 `package-lock.json`，从 `desktop/` 执行命令。
- `npm ci` 会安装固定版本的 Electron。需要能够访问依赖和 Electron 二进制下载源。
- 不将访问凭证、数据库连接、管理员密钥或环境文件打入安装包。正式服务地址由启动进程环境固定配置。
- 本轮没有配置代码签名、macOS 公证或自动更新发布；未经对应平台验收的产物称为候选包。

## macOS arm64

在 Apple Silicon 的 macOS 上运行：

```sh
npm ci
npm run typecheck
npm test
node scripts/run-native-service-smoke.mjs
npm run make:mac
node scripts/verify-package.mjs 'out/意客AI-darwin-arm64/意客AI.app/Contents/Resources/app.asar'
node scripts/run-packaged-smoke.mjs 'out/意客AI-darwin-arm64/意客AI.app/Contents/Resources/app.asar'
```

产物：

- `out/意客AI-darwin-arm64/意客AI.app`
- `out/make/zip/darwin/arm64/意客AI-darwin-arm64-0.2.0.zip`

可以从 Finder 打开 `.app`，也可以通过下述方式为本次进程配置真实 HTTPS 服务。示例域名必须替换为实际部署的服务域名；不要把凭证写进命令或启动脚本。

```sh
YIKE_SERVICE_URL=https://customer.example \
  './out/意客AI-darwin-arm64/意客AI.app/Contents/MacOS/YikeAI'
```

需在所有旧实例退出后重新启动；已运行的单实例不会因再次启动而改变服务地址。普通 Finder 启动不自动继承终端变量。面向客户的受管理启动配置和正式域名仍需随实际交付确认。

浏览器联调应将生产 renderer bundle 挂在同一 FastAPI origin 的 `/app`，让 `/api/ui` 请求保持同源。Vite 的跨端口开发代理目前不支持写入联调：`changeOrigin` 只修改目标 Host，浏览器原始 Origin 会被服务端校验拒绝。不要通过关闭服务端 Origin 检查来绕过；本轮浏览器同源验收不等同于验证了 Vite 代理写入。

## Windows x64

在 Windows x64、Node.js 24 x64 环境中，获取要验收的代码提交，然后从仓库的 `desktop/` 目录用 PowerShell 运行：

```powershell
./scripts/build-windows.ps1
```

脚本执行安装依赖、类型检查、单元测试、原生网络冒烟、Squirrel 安装包构建、ASAR 校验、包内启动冒烟和产物 SHA-256。安装程序为 `out/make/squirrel.windows/x64/YikeAI-Setup.exe`；同时保留 `.nupkg` 和 `RELEASES`。

每次运行会生成独立目录 `out/windows-evidence/<运行编号>/`，控制台会显示该位置。其中：

- `windows-build.json` 记录当前 Git 提交与 dirty 状态、Node/操作系统版本及架构、锁文件 SHA-256、每个阶段的状态和退出码，以及实际产物的大小和 SHA-256。无法读取 Git 时明确记为 `null`；不要将带本地改动的构建当成提交的精确产物。
- `WINDOWS_ACCEPTANCE.md` 来自[人工验收模板](WINDOWS_ACCEPTANCE_TEMPLATE.md)，安装、可见启动、任务草稿、退出、重启、单实例、卸载及 100%/125%/150% 显示缩放均默认 `UNTESTED`。自动构建成功不会自动勾选人工项目。

依赖安装或后续阶段失败会保留报告和实际退出码，尚未执行的阶段为 `NOT_RUN`。缺少 Node 24 时 PowerShell 入口也会尝试写入预检失败报告。报告目录不可写等初始化故障只能在控制台提示；强制终止进程可能留下 `IN_PROGRESS`/`RUNNING`，这同样不是成功证据。证据文件不采集环境变量、Cookie、凭证、原始构建日志或异常全文。

完成构建后，只运行报告对应的本次安装包，逐项实际检查并填写人工表。回传同一运行目录中的 JSON、人工表及必要的脱敏截图；失败也回传 JSON，没有安装包的项目保持 `UNTESTED`。不要回传 `.env`、平台会话、用户数据目录、`node_modules` 或完整控制台日志。自动报告中的 `BUILD_SUCCEEDED` 只表示构建及自动检查通过，不能替代 Windows 实机与产品功能验收。

Squirrel 的 `--squirrel-install`、更新和卸载事件由 `electron-squirrel-startup` 处理。主程序名固定为 `YikeAI.exe`，AppUserModelId 为 `com.squirrel.YikeAI.YikeAI`。

Squirrel.Windows 的官方构建宿主为 Windows，或安装 Mono 和 Wine 的 Linux；不支持本机 macOS 直接制作安装程序。因此只有在上述脚本于可用宿主成功执行并实际验收后，才能报告 Windows 安装包已交付。[官方构建要求](https://www.electronforge.io/config/makers/squirrel.windows)

### Windows 证据脚本的本机验证

2026-09-09 在 macOS / Node 24.19.0 上，`node --check scripts/windows-build-evidence.mjs` 通过；`npm test -- tests/windowsBuildEvidence.test.mjs` 为 **7 passed**。测试使用隔离临时目录中的真实文件和 Git 提交，检查 SHA-256、失败退出码、阶段持久化、产物路径边界及人工状态保持未验收。实际运行 Node 入口返回退出码 1，生成 `WINDOWS_X64_NODE24_REQUIRED` 报告，后续 8 个阶段均为 `NOT_RUN`；记录见 [windows-evidence-writer-check.json](../../docs/qa/ui-r3/windows-evidence-writer-check.json)。

本机未安装 PowerShell，`.ps1` 的解析、Node 缺失兜底、Windows 构建及人工验收都尚未在 Windows 执行。本记录不宣称 Windows 包已经生成或验证，也不改变上次 macOS 包的构建摘要。

## 服务连接和会话边界

- `YIKE_SERVICE_URL` 只接受 HTTPS origin，禁止账号密码、路径前缀、查询参数和片段。未配置或不合法时返回 `SERVICE_NOT_CONFIGURED`。
- 只有未打包的开发进程，同时显式设置 `YIKE_ALLOW_LOOPBACK_HTTP=1`，才接受 `http://localhost`、`http://127.0.0.1` 或 IPv6 loopback。已打包客户端不接受 HTTP，即使设置此开关。
- 服务地址不能从 renderer 修改。renderer 只提交固定 operation 和经过主进程校验的 payload，不能传路径、请求头、租户或管理员凭证。
- 独立、无 `persist:` 前缀的 Electron session 保存内存 Cookie；客户端退出后不保留登录 Cookie。登录 token 只在请求时使用，不落盘。
- 主进程以真实配置服务的 Origin 发起请求；服务端 Origin 检查保持有效。请求拒绝重定向、非 JSON、超过 2 MiB 的响应及超过 12 秒的网络执行；串行队列最多 16 项。Electron 43 对手动重定向可能表现为 `SERVICE_UNAVAILABLE`，仍不会访问跳转目标。
- 退出登录在服务不可达时也会清除该内存会话；服务端退出失败仍作为失败返回，不能谎报远端操作成功。
- 未决任务启动、未决发送和已确认发送版本使用按用户隔离的本机操作记录，仅保存不透明操作标识和状态。清除普通草稿或退出登录不会删除这些记录；无法可靠写入记录时不会发起新的发送或启动。该记录不替代服务端幂等与渠道结果核验。
- `openExternal` 只允许无内嵌凭据的 HTTP(S) URL。`copyText` 只接受非空、无 NUL、最多 20,000 字符文本。两者都验证发送者为当前主窗口主 frame，并明确返回成功或错误。
- `saveExport` 只接受 `{format: 'csv' | 'backup-json', name, content}`；两端校验安全文件名、非空无 NUL 文本和 UTF-8 最大 2 MiB，备份还须是 JSON 顶层对象。主进程验证当前主窗口主 frame，只允许一个保存窗口，用户取消和写入失败分别返回固定状态；回执不包含绝对路径。扩展名固定 `.csv` 或 `.yike-backup.json`，renderer 不能指定目录、任意路径或文件类型。选择路径后仍校验完整后缀，避免追加后缀后覆盖未经确认的另一个文件。实际写入临时文件并替换完成后才返回 `saved`；全局浏览器下载仍被禁止。
- 浏览器端导出只返回 `initiated`（下载已发起），不能证明文件落盘；缺少原生保存接口的桌面端不会回退到已被禁止的浏览器下载。CSV 数据仍排除公开样例并转义公式前缀。原生 [保存窗口的过滤器](https://www.electronjs.org/docs/latest/api/dialog)使用 `csv`/`json` 裸扩展名，备份完整后缀由主进程另行强制。

固定 API：

| Operation | 方法和路径 | Payload |
| --- | --- | --- |
| session.get / login / logout | GET / POST / DELETE `/api/ui/session` | login: `{token}`，最多 8192 字符 |
| profiles.list / save | GET / POST `/api/ui/profiles` | save: `{description}`，非空且最多 8000 字符 |
| profiles.confirm | POST `/api/ui/profiles/{version_id}/confirm` | `{version_id}`，路径由主进程构造，服务请求无 body |
| opportunities.list / get | GET `/api/ui/opportunities` 或 `/{id}` | get: `{id}` |
| followups.list / add | GET / POST `/api/ui/followups` | add: `{opportunity_id,status,note}` |
| capabilities.get | GET `/api/ui/capabilities` | 无 |

ID 限制为 1–128 个字母、数字和安全标点（`_`、`-`、`.`、`:`，首字符仅字母数字、`_`、`-`）。服务端新建 UUID 可直接使用；含其他字符的历史 TEXT ID 不能通过本客户端桥接，迁移前需核对。跟进状态只接受现有六项 `CONTACTED`、`REPLIED`、`MEETING`、`QUOTED`、`LOST`、`WON`，备注非空且最多 8000 字符。

## 验收证据的范围

`verify-package.mjs` 验证 CJS 入口、预加载、完整 Vite 资源清单、实际 ASAR 字节摘要，并拒绝携带常见环境/私钥文件。它不启动 UI、不验证安装器、不证明服务端上线。

`run-native-service-smoke.mjs` 使用临时本机 HTTP 测试服务和临时用户目录，不启动浏览器窗口、不使用客户数据，验证实际 Electron Origin、Cookie 往返、会话隔离、不跟随跳转、退出清理。它不替代 HTTPS 部署验收和真实用户登录。

`run-packaged-smoke.mjs` 使用同版本 Electron 和临时用户目录，加载候选 ASAR 内的真实主进程、预加载和页面，验证隐藏窗口渲染、安全设置、固定 IPC 和未连接状态。新导出检查替换该测试进程的保存窗口回执，仍通过真实 IPC 和 writer 将 CSV/备份写入临时目录，核对字节与取消/拒绝状态；不保存到用户选定目录。它不修改 ASAR，不访问真实服务，不修改剪贴板，不打开外链；它也不替代 Finder/安装器启动、可见窗口、人工保存窗口和真实操作验收。该新增检查需在含保存接口的新 ASAR 上执行，不能套用下述历史包的结果。

## 2026-09-09 最终 macOS 候选包

本次在代码冻结后的工作树构建，基线为 `5929de671d314748f621a1992c646acee5622f67`；候选提交尚由主任务收口。逐文件构建输入摘要、产物字节数、资源清单与检查结果见 [mac-package.json](../../docs/qa/ui-r3/mac-package.json)。这份记录不将基线提交误作全部新增源码的提交。

| 检查 | 实际结果 |
| --- | --- |
| 构建环境 | macOS 26.5.2 arm64；Node 24.19.0；npm 10.8.2；Electron 43.4.1 |
| `npm test` | 24 个测试文件，216 个测试通过 |
| 原生网络冒烟 | 实际 Origin、Cookie 往返、会话隔离、重定向拒绝、退出清理通过 |
| `npm run make:mac` | `.app` 与 0.2.0 arm64 ZIP 构建成功 |
| ASAR 校验 | CJS 主入口、预加载、21 项 renderer 资源及字节摘要通过 |
| 包内启动冒烟 | 真实包内页面、安全 IPC、未连接状态、取消关闭与确认退出通过 |
| ZIP 与图标 | CRC 通过，ZIP 内 ASAR 与 `.app` 一致，图标与批准的 ICNS 字节一致 |
| 依赖覆盖 | 实装 `tar@7.5.22`、`tmp@0.2.7`；本机构建路径通过，Windows 仍需单独验证 |

最终产物摘要：

- ZIP（122,384,080 字节）：`f7719bb9c809b38d47000a04b5eb04cac84a3eb7ef3fb2a3d7460e72f7588b1a`
- ASAR（1,462,923 字节）：`fb970401b4a117e4ca0be599d9fd2d044e5b7c85e8f43d783b0cfd1607c17522`
- 构建输入清单：`a645ca9b4cebf207523ddffd779d743731ac6fd109c877f11ce428400f448e35`

Forge/Vite 的 `inlineDynamicImports` 与运行时 `fs.Stats` 各产生一项弃用提示；对应命令均正常退出。主任务随后进行真实 `.app` 可见验收。Windows 安装器、分发签名、公证和 CP-06 生产服务验收仍未由本次构建完成。

## 候选包交付验收清单

候选包最终验收至少记录：

1. `.app` 或 Windows 安装器的 SHA-256、构建主机和架构、依赖锁文件版本。
2. 新用户环境安装、首次启动、应用名称和资源加载、关闭/重新打开、单实例、正常退出；Windows 补卸载和快捷方式。
3. 1440×1024、1280×720、最小 960×600 窗口的实际页面与缩放。工作区小于默认值时窗口按当前屏幕工作区收敛。
4. 未配置服务、服务不可达、真实 HTTPS 服务登录/退出、权限不足、来源链接打开、剪贴板失败与成功状态。
5. 真实客户数据与公开样例的操作边界；自动采集、触达、监控等未接通功能保持未接通状态。
6. 客户外发前的签名、公证、安装系统提示和更新策略，以及服务端 CP-06 的实际环境证据。当前未实现自动更新，不记录虚构更新成功。

## 旧实验测试的基线核验

2026-09-09 在同一 `.venv/bin/python` 下，将 `5929de671d314748f621a1992c646acee5622f67` 的代码归档到隔离目录，并于同一系统时钟的 07:53:17–19 UTC 连续执行 `python -m pytest tests/test_web.py -q --tb=short --color=no`。基线和当前均为 **5 failed, 6 passed**，5 个失败均是 `sqlite3.IntegrityError: D04_FACT_OUTSIDE_RUN_WINDOW`；`git diff 5929de6 -- app tests/test_web.py` 为空。该旧 SQLite 实验失败在本轮之前已经存在，本轮没有修改旧业务来改变结果。

失败用例为 `test_signal_filters_use_persisted_score_review_query_and_outreach`、`test_detail_posts_review_draft_and_manual_outreach_then_redirects`、`test_followup_posts_response_interview_and_quote_facts`、`test_csv_export_has_visible_facts_and_no_model_or_secret_columns`、`test_metrics_page_ignores_browser_supplied_counts_and_decision`。原始输出与两个实际模块路径记录在构建工作目录的 `out/verification/legacy-web-baseline.json` 和对应 `*-test-web.log`；客户 pilot 的验证范围仍需单独执行 `tests/test_ui_api.py` 与 `tests/test_pilot_web.py`。

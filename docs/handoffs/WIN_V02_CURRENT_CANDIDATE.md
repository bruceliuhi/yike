# CodexWin：完整 V0.2 当前候选接续

状态：`WAITING_FOR_WINDOWS_ENVIRONMENT / NOT_EXECUTED`。2026-09-11 用户明确确认暂时没有可用 Windows 环境；此单由 CodexiMac 准备，不代表 Win 已接收、启动或通过。完整 V0.2 Goal 不变，服务端非依赖工作继续，不用 Mac 或模拟结果代替 Windows 实机验收。

## 固定一次候选，避免追着文档反复构包

- 本次产品基线：**`b40cc3b357b0ac05dc2a0bf2cb946c5d725a0d38`**，已在 `yike-ai2026/main`，亦为当前customer部署源码。包含正式短信/试用、四平台及公开来源相关客户端、模型适配和Windows同源构包门禁。使用该提交的干净独立工作树；不要切换、清理或覆盖另一任务的工作树。旧交接基线 `c834408` / `23d1793` 仅保留为历史，不能替代本次冻结候选。
- 本文后续的纯文档提交不改变候选字节。若必须接收产品修复，登记新的完整 SHA 与实际影响，再仅重验受影响步骤。
- 旧 `e2b75ce` payload（清单 `90f5eca4…`）缺后续安装器及触达模块；旧 `1a47178` Setup 也不是当前产品。保留历史产物，不复用其摘要宣称本次通过。
- 新 payload 和 Electron 必须来自上述同一产品基线。构建器自动核对清单摘要、payload干净声明及40位源码SHA与实际Git HEAD相等，当前工作树含已跟踪或未跟踪改动、来源Git不可用均拒绝。构包前仍核对 `source.project_commit` 与固定候选，避免两端同时选错版本。这不是全部依赖或构建输入的证明，也未在客户运行时增加Git要求。[门禁限定验证](../superpowers/plans/2026-09-11-portable-source-binding.md#实施与验证)。

## 1. 生成一次新 payload

在真实 Windows x64 上执行。构建机需要已锁定的采集运行时、CPython 3.11、项目 host 依赖与 Node 24；这些是构建机要求，不是客户安装要求。不升级锁、不导出登录态、不访问平台。

先核实并设置以下绝对路径，未具备时只回报缺项，不猜路径：

| 环境变量 | 输入 |
| --- | --- |
| `YIKE_PORTABLE_SOURCE_RUNTIME` | 已通过既有安装校验的 MediaCrawler runtime |
| `YIKE_PORTABLE_PYTHON_HOME` | 真实 CPython home，不是 venv 启动器 |
| `YIKE_PORTABLE_HOST_SITE_PACKAGES` | 符合当前 `uv.lock` 的 host 包目录 |
| `YIKE_PORTABLE_DESTINATION` | 尚不存在、末级 ASCII 名以 `portable-` 开头的新目录；同级 `-relocated` 目录也须不存在 |
| `YIKE_PORTABLE_GIT` | 已验证的 Git 可执行文件；不要使用已知被硬链接规则拒绝的入口 |

用 Win 当前项目测试解释器，在固定工作树根运行唯一生成/搬迁场景（此命令实际写入新产物，并非普通单元测试）：

```powershell
python -X utf8 -m pytest tests/test_windows_portable_bundle_local.py::test_real_portable_bundle_has_no_developer_python_dependency -q
if ($LASTEXITCODE -ne 0) { throw 'PORTABLE_BUILD_OR_RELOCATION_FAILED' }
```

必须 `1 passed / 0 skipped`；缺环境导致 skipped 不是成功。该场景生成、搬迁并复核同一 payload，不再额外重复 retained 测试。失败后不覆盖/删除半成品；先定位失败。只有产物字节未变且修复仅影响测试时，才使用既有 retained 场景复核，不重生成 1GB 运行包。

## 2. 绑定一次 Windows 安装候选

PowerShell 中 `$candidateRoot` 为上述 `-relocated` 的实际绝对目录；`$candidateManifest` 从其 `bundle-manifest.json` 读取。先检查 `source.project_dirty` 为 false、`source.project_commit` 等于固定基线；目录/输入来源无误后执行：

```powershell
$env:YIKE_PORTABLE_BUNDLE_PATH = $candidateRoot
$env:YIKE_PORTABLE_BUNDLE_SHA256 = (Get-FileHash -LiteralPath (Join-Path $candidateRoot 'bundle-manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant()
$env:YIKE_RELEASE_SERVICE_URL = 'https://yike.tuokexing.net'
# Python payload builder使用显式Git；Electron source门禁经PATH查找同一个Git。
$yikeBuildGitDirectory = Split-Path -Parent $env:YIKE_PORTABLE_GIT
$env:PATH = "$yikeBuildGitDirectory;$env:PATH"
$yikeResolvedBuildGit = (Get-Command git -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
if ([IO.Path]::GetFullPath($yikeResolvedBuildGit) -ne [IO.Path]::GetFullPath($env:YIKE_PORTABLE_GIT)) { throw 'PORTABLE_BUILD_GIT_MISMATCH' }
npm --prefix desktop ci
if ($LASTEXITCODE -ne 0) { throw 'DESKTOP_DEPENDENCIES_FAILED' }
Push-Location desktop
try {
  npm run make:win
  if ($LASTEXITCODE -ne 0) { throw 'WINDOWS_MAKE_FAILED' }
} finally { Pop-Location }
```

依赖已与同一锁完全一致时可复用，不重复 `npm ci`。不先单独执行 package/renderer build 再 make。必须在 Windows 运行，不能用 Mac 交叉构包替代；固定资源摘要由 Forge/Vite 写入 main。构包后保存实际 Setup、ASAR、payload 清单 SHA256、完整源码 SHA 和签名状态，记录真实产物路径，不沿用旧候选文件名或摘要。

`YIKE_RELEASE_SERVICE_URL`是公开HTTPS构建输入，不是密钥；缺失时当前 `make` 会以 `RELEASE_SERVICE_URL_REQUIRED` 拒绝。不可用仅开发态生效的 `YIKE_SERVICE_URL` 代替，不把API key、手机号、短信码或管理员凭据带入构包环境/产物。以上先生成固定安装候选；需要统一证据脚本时使用同一SHA的 `scripts/build-windows.ps1 -ExpectedCommit b40cc3b357b0ac05dc2a0bf2cb946c5d725a0d38`，不要在已make后无变化再次运行完整构包流程。

## 3. 用同一包做最小实机交付验收

在专用测试 Windows 用户/隔离测试环境执行，避免覆盖已有客户安装和 profile；删除、卸载或重置已有数据不属于本交接授权。

1. 安装并启动：没有开发机 Python/Git 环境变量也能显示准备状态；只有私有安装完成且控制器装配完成才 READY。记录真实安装方式与结果，未签名如实标注。
2. 准备期间关闭：确认进程退出；重启遇到不完整目标应明确失败，不覆盖半成品或伪报可用。此分支用独立测试用户/环境，不破坏已成功实例。
3. 成功实例正常退出再重开：复核同一 payload，保留应用状态，无重复安装/残留进程。以上只验证 Windows 交付，不证明平台或服务已通。
4. 连接既定HTTPS服务：customer已部署同一b40cc3b，模型已配置，四平台监控模式已装配；[当前部署证据](../qa/SERVER_137138_DEPLOYMENT.md#模型已部署b40cc3b2026-09-11)。仍需从正式包真实登录，不以管理员导入token代替客户短信/试用。当前两个已授权号码的短信投递均因 `PORT_NOT_REGISTERED` 失败，待供应商报备处理；先完成不依赖登录的安装/启动/恢复，不再换号码试发或重复建trial。
5. 有授权账号且真实短信登录完成后，逐平台验收连接→单次发现→原文候选→模型判断与人工复核→短草稿保存→明确确认后的联系→结果/跟进登记→退出与重启恢复。分别登记小红书/抖音/B站/知乎通过、失败或未验；一平台成功不替代四平台。模型建议仅在用户确认披露后验证，平台执行不得绕过验证或风控。
6. 持续监控在同包验证一个到期轮次及暂停/恢复，检查原请求恢复不重采。真实发送另需明确目标/内容批准；若未批准，停在确认前，标记触达/回复尚未实证，不能发测试广告充数。

## 回传与分工

Win 只回传一份短记录：源码 SHA、payload 清单 SHA、Setup/ASAR SHA、签名状态、实际执行的步骤与结果、首个失败的固定错误码/脱敏截图、未验项及所需输入。不得回传 Cookie、密钥、完整私人消息或 profile 文件。集中追加到本文；历史证据保留在原记录，不复制全套。

Mac 负责服务端接收和具体修复；Win 负责该候选的真实生成/安装/原生流程。遇到可复现代码缺陷，在 `codex/<主题>` 做最小修复，经另一端或独立非作者审核后合入 main；不重复重写已接通的资料、搜索、监控、草稿、跟进服务。

当前仅完成交接准备，没有 Win 实际 ACK 或新产物。商业规则、更多来源、生产恢复与跨行业客户试用仍按完整任务书推进；此候选不是完整 V0.2 上线结论。

2026-09-11 对b40cc3b的独立限定核对：未发现无需真实Windows环境即可确认的普通用户first-run代码阻断；发现payload的显式Git与make的PATH Git前提不同，已在上述命令显式对齐。客户运行时仍无需Git。本次只是源码/流程核对，未生成Win包或执行实机步骤。

参考：[离线包原验收](../superpowers/plans/2026-09-10-win-portable-runtime.md)、[正式 bootstrap](../superpowers/plans/2026-09-12-packaged-runtime-bootstrap.md)、[当前整合状态](../INTEGRATION_STATUS.md)。

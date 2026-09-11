# CodexWin：完整 V0.2 当前候选接续

状态：`READY_FOR_WINDOWS_EXECUTION / NOT_EXECUTED`。此单由 CodexiMac 准备，不代表 Win 已接收、启动或通过。完整 V0.2 Goal 不变。

## 固定一次候选，避免追着文档反复构包

- 本次产品基线：`c8344082b3e483b7c8d86b54017725d0c95ad2a4`，位于 `yike-ai2026/main`。包含独立业务画像、资料引用、行业策略进入任务及候选模型、Windows同源构包门禁。使用该提交的干净独立工作树；不要切换、清理或覆盖另一任务的工作树。原交接基线 `23d1793` 仅保留为历史，不代表这些新增功能。
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
npm --prefix desktop ci
if ($LASTEXITCODE -ne 0) { throw 'DESKTOP_DEPENDENCIES_FAILED' }
Push-Location desktop
try {
  npm run make:win
  if ($LASTEXITCODE -ne 0) { throw 'WINDOWS_MAKE_FAILED' }
} finally { Pop-Location }
```

依赖已与同一锁完全一致时可复用，不重复 `npm ci`。不先单独执行 package/renderer build 再 make。必须在 Windows 运行，不能用 Mac 交叉构包替代；固定资源摘要由 Forge/Vite 写入 main。构包后保存实际 Setup、ASAR、payload 清单 SHA256、完整源码 SHA 和签名状态，记录真实产物路径，不沿用旧候选文件名或摘要。

## 3. 用同一包做最小实机交付验收

在专用测试 Windows 用户/隔离测试环境执行，避免覆盖已有客户安装和 profile；删除、卸载或重置已有数据不属于本交接授权。

1. 安装并启动：没有开发机 Python/Git 环境变量也能显示准备状态；只有私有安装完成且控制器装配完成才 READY。记录真实安装方式与结果，未签名如实标注。
2. 准备期间关闭：确认进程退出；重启遇到不完整目标应明确失败，不覆盖半成品或伪报可用。此分支用独立测试用户/环境，不破坏已成功实例。
3. 成功实例正常退出再重开：复核同一 payload，保留应用状态，无重复安装/残留进程。以上只验证 Windows 交付，不证明平台或服务已通。
4. 连接受控测试服务：服务端需同步对应代码/迁移并通过原配置门禁；不把缺 API、缺 migration 或未授权来源当作“包正常即可通过”。测试环境地址、凭据由已有授权通道提供，不入 Git。
5. 有授权账号后，逐平台验收连接→单次发现→原文候选→人工复核→短草稿保存→跟进登记→首页到期展示。分别登记小红书/抖音/B站通过、失败或未验；一平台成功不替代三平台。模型建议仅在用户确认披露、有效模型配置后验证。
6. 持续监控在同包验证一个到期轮次及暂停/恢复，检查原请求恢复不重采。真实发送另需明确目标/内容批准；若未批准，停在确认前，标记触达/回复尚未实证，不能发测试广告充数。

## 回传与分工

Win 只回传一份短记录：源码 SHA、payload 清单 SHA、Setup/ASAR SHA、签名状态、实际执行的步骤与结果、首个失败的固定错误码/脱敏截图、未验项及所需输入。不得回传 Cookie、密钥、完整私人消息或 profile 文件。集中追加到本文；历史证据保留在原记录，不复制全套。

Mac 负责服务端接收和具体修复；Win 负责该候选的真实生成/安装/原生流程。遇到可复现代码缺陷，在 `codex/<主题>` 做最小修复，经另一端或独立非作者审核后合入 main；不重复重写已接通的资料、搜索、监控、草稿、跟进服务。

当前仅完成交接准备，没有 Win 实际 ACK 或新产物。商业规则、更多来源、生产恢复与跨行业客户试用仍按完整任务书推进；此候选不是完整 V0.2 上线结论。

参考：[离线包原验收](../superpowers/plans/2026-09-10-win-portable-runtime.md)、[正式 bootstrap](../superpowers/plans/2026-09-12-packaged-runtime-bootstrap.md)、[当前整合状态](../INTEGRATION_STATUS.md)。

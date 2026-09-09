# CodexWin 开发与交叉复核记录

日期：2026-09-09。执行环境为 Windows x64、CPython 3.11.14；临时 PostgreSQL 16.15 通过本机 Docker 运行。各项绑定不同提交，不把不同集合的通过数相加。实际卡状态及 ACK 以[唯一任务书](../V02_IMPLEMENTATION_TASKBOOK.md)为准。

## 1. V02-02C 纯解析器切片

- 基线 `022b0fbb4163f21628f70d6f3fe02b483afdcca3`，代码 `e368b5a9f036b41d4cfd59d6a6b7de9bb852e2a7`。
- 抖音/B站纯解析与类型移入 `connectors`，旧入口重导出同一对象；不加载旧 `app` / `pilot` / SQLite / PostgreSQL。平台名称只做严格映射，不宣称来源已接通。旧解析结果仍为 `verifiable=False`。
- TDD：导入/兼容 RED 为 8 failed、31 passed、42 deselected；平台映射 RED 为 37 failed、8 deselected。最终定向 76 passed、42 deselected，根代理独立复跑通过；compileall 与 wheel 构建通过。wheel 六个包文件与源码匹配，隔离导入通过。
- 独立规格审核 `collaboration_assessment`、架构/代码/质量审核 `api_contract_gaps` 均绑定该提交 PASS，没有未决 P1/P2。实现者为 `source_parser_impl`，不是最终 reviewer。
- 命令：`./.runtime/venvs/win-dev/Scripts/python.exe -m pytest -q tests/test_connector_parsers.py tests/test_d03_remediation.py -k "connector or adapters or normalize_time or bilibili"`。wheel：`uv build --wheel --out-dir .runtime/parser-dist`。
- 02A 候选 DTO、上传与真实平台样例未接收，02C 不标 DONE。合成 fixture 不冒充真实采集证据。

## 2. Windows 构建与已确认问题

`e01e99ad15b10c629d2202a1093fbdf56f4fc496` 修复 PowerShell 在 PATH 有两个 Node 时将路径数组当作命令执行的问题。新增真实双 Node 路径、空格参数、工作目录、退出 0/37 的回归；RED 后 GREEN，相关 8 项通过。独立 reviewer `win_contract_readiness` PASS。

该版本完整运行 `desktop/scripts/build-windows.ps1` 的结果：

| 阶段 | 结果 |
|---|---|
| preflight / dependencies / typecheck | PASS |
| unit-tests | PASS，37 文件 / 363 项 |
| native-smoke | PASS |
| make-win | FAIL：Squirrel 的 rcedit 对 Setup.exe 报 `Unable to load file` |
| artifacts / archive-check / packaged-smoke | NOT_RUN |
| 安装、可见运行、卸载、缩放 | UNTESTED |

原始证据：`desktop/out/windows-evidence/2026-09-09T10-25-27-908Z-743650fc/windows-build.json`，SHA256 `3361907fe2c3625cb8ade12d87e790a77410938925c65094f632268db5d1d4d7`。源码 `dirty: true` 如实记录当时尚未提交的本次文档，desktop 源码相对锁定版本无变化。残留 Setup.exe 不是验收通过的安装包，报告 `artifacts=[]`。

独立 reviewer 在新临时目录复制相同 Setup.exe，保持工具、图标和中文元数据相同：目标 EXE 为 ASCII 路径两组成功、中文路径两组失败；图标路径是否中文不影响结果。原始产物未修改。诊断结果 SHA256 `f33e984b5bb9641a65a061968e7d3d83858c1a67d0810b5bcad29545a314191d`，本机原始文件在临时目录 `yike-rcedit-diagnostic-922016fed879454eb14c093728412dc6/results.json`。

按[staging 修复计划](../superpowers/plans/2026-09-09-win-squirrel-staging.md)完成代码切片 `e9983ed`：只在新建、受校验的 ASCII 临时目录运行原 Squirrel maker，再校验并回拷产物；不改变中文产品名称、图标或资源编辑。系统 TEMP 本身非 ASCII 时明确拒绝，单独指定 staging 不能掩盖上游仍使用系统 TEMP 的限制。未对原 make 输出目录执行递归删除。

第一轮独立审核发现两个 P2，均保留反例后修复：后续文件复制失败会造成旧产物混合；路径穿越测试此前被 path.join 预先归一化。修复先备份并校验全部旧目标，任何回拷失败均恢复本次已尝试的文件；没有旧文件时只删除本次新增项。若恢复本身失败，明确失败并保留有摘要的备份及恢复清单，不清理唯一恢复副本。新增只读失败、复制途中源文件消失、回滚也失败的真实文件系统反例均 RED→GREEN；路径反例保留原始 `..`，且归一化终点实际存在。

独立 `win_contract_readiness` 复审 PASS（无未决 P1/P2），Node 24.19.0 运行两个相关文件 **30 passed**，`tsc --noEmit` 通过；根代理另跑 staging 文件 **22 passed**。复审后冻结 SHA256：maker `76dc22e3051d05798569ecacd7b60d4b6a3e6f2c418a76a08532d64b7104fe4f`、staging 测试 `72b5a90f2738c92cda841f7f15f97386b273a4e4a520b3b0b2d2200d578b81c5`、Forge 配置 `2f827b08ac037e41aa29b63b2c425645e4fd2b83ad7e798d7b3aa308b7cbc73f`。这些单测不等于真实 Squirrel 构建成功；完整链待运行时一致性修复后重新执行，旧失败证据不变。

独立问题：runner 使用 Node 24.19.0，但系统 npm.cmd 实际选择同目录 Node 24.11.1，低于锁定 jsdom 的 24.15 最低版本。不能只记录 runner 版本便声称所有步骤运行时一致。完整安装另报告 17 high；见[依赖风险](BUILD_DEPENDENCY_AUDIT_20260909.md)，未运行自动依赖升级或放宽发行门禁。

## 3. V02-10E Windows 基线复核

代码候选 `475166ac27e6d84ef019d669cc15cb9aec578ae4`，不可变审查快照 `e577f4bfc7549fc10180a08e72b38768701242f3`。独立 reviewer `collaboration_assessment`，只读审查，没有修改生产代码或测试。

| 实际运行 | 结果 |
|---|---|
| main `e01e99a` 全仓 Python，未配置 PG | 420 passed、226 failed、7 skipped、7 errors |
| clock 快照 Windows 全仓，未配置 PG | 566 passed、58 failed、7 skipped |
| 原生时钟反例独立重跑 | 34 passed、126 deselected |
| 新时钟 fixture 独立重跑 | 16 passed |
| 受时钟修改影响的九个测试文件 | 374 passed、0 failed |

613 个同名用例比较：168 failure→passed、7 error→passed、375 passed→passed、56 failure→failure、7 skipped→skipped，原通过变失败为 0。集合另有 45 个仅 main 存在的解析器用例、16 个候选新增时钟用例及两组改名 bootstrap；不能直接以总数差当作回归数量。

剩余 Windows 失败已复现的类别：WSL Bash 缺 `/bin/bash`、直接执行 `.sh` 的 WinError 193、符号链接权限 WinError 1314、缺少 `os.killpg`、Windows chmod 不提供旧 POSIX 0700 语义、GBK 默认解码、autocrlf 改变补丁工作树字节。bootstrap 以 `-X utf8` 定向诊断为 5 passed；Git 原始 LF 补丁摘要与锁文件一致。不能为过门禁关闭隔离或放宽权限检查。

基线 XML `.runtime/win-main-e01e99a-regression.xml` SHA256 `a0018d6c9e6cae61e68827e9c8a1e89d01200215cdeab1a64564705b25e9107e`；候选 XML `.runtime/win-clock-e577-regression.xml` SHA256 `cf1080aec3a733a77133fb75ea5db17ed94a86ddadbc12b5e1308cfd2d86818ae`。本机保留原始证据，未将 skip 计为通过。限定接收的是测试时钟修复，不是 Windows 全仓可用或 V02-10 产品整链完成。

## 4. V02-01A/B 最新组合交叉接收

Mac 原候选 `8553491` 的身份 PG 验证曾得到 147 passed、2 skipped；该历史结果不覆盖后续授权修复。最新锁定代码为 `222119e0b41b86b65867a92e14d3ed00dede4e7d`，本机新的空数据库、独立身份/通用试用数据库与受限应用角色，串行执行[交接命令](../handoffs/V02-01_MAC_TO_WIN.md)：136 passed、0 skipped。

独立代码 reviewer `api_contract_gaps` 确认权限升级先拒绝特权/owner，仅授予四张身份表实际需要的权限，未增加用户表 UPDATE；没有发现新增 P1。但冻结契约第26行错误地公开 `STARTED/CANCELLED`，校验器只支持 `COLLECTION_STARTED/COLLECTION_CANCELLED`，是客户端按文档调用会失败的 P2。`222119e` 未直接获得完整契约 ACK。

最小更正提交 `f42ea909c9eb36791a3a557acb9afaef7fecf403`（父 `222119e`），由 `source_parser_impl` 在独立 detached 快照只更正文档两名称和添加一致性测试；没有改动 Mac 工作分支。RED 为 1 failed、17 deselected，GREEN 为 18 passed。测试读取真实文档、比对全部七个事件并调用校验器，确认旧名称及 `REGISTER` 拒绝。独立 `api_contract_gaps` 在该 SHA 复跑 18 passed，P2 已解除；`pilot/`、`migrations/`、`deploy/` Git 对象与父提交完全相同。CodexWin 对 `f42ea909` 的登记/遥测、持久会话撤销及最小权限升级给出限定范围 ACK。

全量首次运行 642 passed、58 failed、5 errors、0 skipped。5 errors 来自本次测试环境尚未创建 pilot_app，不归咎于产品代码；修正环境的复跑另行记录，保留首次 XML `.runtime/identity-full-222119e.xml`，SHA256 `d561258c237b9ec538f7b3bf5027e9a040786981f3afe36bd89762658b7ca6fe`。交接定向原始 XML `.runtime/identity-targeted-222119e.xml` SHA256 `d5c9dc347c5dccfce09df5ce62d60be91301832d0ed35347e40b298afe522a9a`。

修正临时库角色、使用另一个新空容器串行重跑 `222119e`：定向 136 passed / 0 skipped，全量 **647 passed、58 failed、0 errors、0 skipped**（705 项）。58 个失败名称与独立 clock 快照的失败集合完全相同，身份、撤销、升级和全部 PostgreSQL 用例没有失败；这不是 Windows 全仓通过。重跑证据：`.runtime/identity-targeted-222119e-retry.xml` SHA256 `58661228ade589e8acb799fcf42ef2b313b30153a3e2b0c117f3aa96da2c4903`；`.runtime/identity-full-222119e-retry.xml` SHA256 `3572b24eb03f84986ed2fcabd3ecbb3364475fe7957f4872c7cfea46ac57dffa`。没有用后一次覆盖前一次失败证据。

Windows实际复现环境：仓库根 `.runtime/venvs/win-dev/Scripts/python.exe` 为非editable CPython 3.11.14；当前目录为 `.worktrees/review-identity-222119e`，HEAD严格等于 `222119e0b41b86b65867a92e14d3ed00dede4e7d`。只用一次性loopback PostgreSQL的两个独立库（win_pilot / win_identity），预建专用pilot管理员及非超级用户/NOBYPASSRLS的pilot_app；身份fixture创建identity_app，应用URL使用各自对应角色。全量前须配置以下四个测试变量，不可使用现有客户/生产库；真实连接串不落盘：

- `YIKE_PILOT_ADMIN_DATABASE_URL`、`YIKE_PILOT_DATABASE_URL`：同一通用试用测试库、不同管理员/应用角色。
- `YIKE_IDENTITY_TEST_DATABASE_URL`、`YIKE_IDENTITY_TEST_APP_DATABASE_URL`：另一个身份测试库、不同管理员/应用角色。

以下与本轮实际pytest调用一致；使用新输出后缀避免覆盖历史XML，从仓库根执行，并在测试后丢弃本次合成数据库：

```powershell
$reviewRepo = (git rev-parse --show-toplevel).Trim()
$reviewPython = Join-Path $reviewRepo '.runtime/venvs/win-dev/Scripts/python.exe'
$reviewOutput = Join-Path $reviewRepo ('.runtime/identity-repro-' + [guid]::NewGuid().ToString('N'))
Push-Location (Join-Path $reviewRepo '.worktrees/review-identity-222119e')
try {
  if ((git rev-parse HEAD).Trim() -ne '222119e0b41b86b65867a92e14d3ed00dede4e7d') { throw 'Wrong review SHA' }
  & $reviewPython -m pytest -q --tb=short -r s tests/test_identity_contract.py tests/test_identity_postgres.py tests/test_session_auth.py tests/test_session_revocation_postgres.py tests/test_session_upgrade_postgres.py tests/test_ui_api.py tests/test_pilot_web.py "--junitxml=$reviewOutput-targeted.xml"
  # 该环境下全量预期暴露58个既有Windows缺口，非预期绿色命令。
  & $reviewPython -m pytest -q --tb=no "--junitxml=$reviewOutput-full.xml"
} finally { Pop-Location }
```

这些旧进程组反例在Windows可能遗留测试Python子进程；本次根据对应pytest临时目录核实归属后清理，不结束其他Python或开发任务。原环境搭建/容器清理脚本仅保留在本机 `.runtime/review-identity-222119e.ps1`，不把任何测试或生产凭据纳入Git。

整合前工作树定向验证（解析器、身份契约、会话、UI、clock、bootstrap）以显式 `-X utf8` 得到 161 passed；该参数解决测试文档默认解码问题，不放宽生产校验。身份子树与 `f42ea909`、解析器与 `e01e99a` 均逐树核对无差异。任务书和任务板的合并冲突保留最新 main 的细化卡片与已有认领，不恢复旧整项分配。独立 `api_contract_gaps` 核对暂存区及原始XML后PASS，正常合并提交为 `bea5c7dd2e6860fadd965e094e4fbd2bc5e515cc`。secret-scan对已跟踪工作树为clean（Git Bash读取Git原始LF脚本执行）。

本轮使用 computer-use 查看 Docker 错误并退出故障进程。确认仅运行端点异常后，将原 `Docker/run` 目录可恢复地改名为 `run.codex-backup-20260909`，没有点击恢复出厂或删除镜像、卷、用户配置；引擎恢复为 28.3.2。一次性 PostgreSQL 仅绑定 loopback 随机端口、使用 tmpfs，结束后停止并清理本次测试容器及合成数据；不访问生产数据库、平台登录态或真实客户数据。

本机 Python 因中文 editable 路径遇到 GBK 解码失败，使用 `uv sync --frozen --extra dev --no-editable` 创建 `.runtime/venvs/win-dev`，不改全局 Python。测试在冻结源码目录执行。Windows 不支持旧进程组测试的清理路径，已按测试临时目录精确核实并停止本次遗留进程，没有终止其他开发任务。

上述代码/数据库证据不能证明设备持钥认证、正常手机号登录、真实平台连接、采集/发送/回复、Windows 生命周期、生产部署或客户试用。Goal 保持 ACTIVE。

## 5. V02-02A 来源契约交叉接收与最新UI整合

冻结Mac候选 `e4d1695749f037bcafa13f77e703544b67b25c09`，根代理在detached工作树以非editable CPython3.11.14运行候选/来源、旧纯解析器、研究导入和Skill五文件，182 passed。独立 `win_contract_readiness` 在两契约文件126 passed后另行发现P2：Python内建IDNA2003将 `faß.example` 与 `fass.example`合并，两个不同网站相同站内ID发生错误冲突；等价IPv6压缩/展开写法则漏去重。根代理实际复现两者，原候选不直接接收。

按[更正计划](../superpowers/plans/2026-09-09-candidate-origin-erratum.md)，`supplychain_readiness` 在另一个detached快照更正，未改Mac工作分支。新增37反例先21 failed/16 passed，修复后37 passed；共用host规范化采用ipaddress和非过渡UTS46，原public_url快照不变，特殊用途/私网及Unicode等价点绕过继续拒绝。idna3.18由已有传递依赖提升直接声明，锁定包节点/摘要无升级。

更正提交 `d14594f042b094885f439477d376399cfd3e5ab5`，独立 `windows_bootstrap_fix` 实现/规格/质量复审PASS，无未决P1/P2；其额外公开入口反例覆盖不同网站、同站Unicode/A-label/IP表示及禁止I/O。实现者、reviewer和根代理各自定向221 passed（不相加），compileall、`uv lock --check --offline`、diffcheck通过。2026-09-09 CodexWin限定ACK此SHA，仅解锁DTO/纯函数与02C原始字段映射；main正常集成 `95285dd04966d213bc1ba4dc12aa62975d18f758`。

根代理最新实际命令在 `.worktrees/review-candidate-idna`：

```powershell
& 'C:/Users/bruce/AI/意客AI2026/.runtime/venvs/win-dev/Scripts/python.exe' -X utf8 -m pytest -q tests/test_candidate_contract.py tests/test_source_capabilities.py tests/test_connector_parsers.py tests/test_research_import.py tests/test_pilot_import_cli.py tests/test_research_skill_contract.py --junitxml=C:/Users/bruce/AI/意客AI2026/.runtime/win-candidate-idna-fixed.xml
uv lock --check --offline
```

原e4的182集合未含2项导入CLI，新集合另增37反例，不能直接把总数差当成修复失败数。旧XML `.runtime/win-candidate-e4d1695-targeted.xml` SHA256 `d8a213de823107af13399d88fbbb8520dfd006f911b1c933b5aaa4ade7ef4f67`；新XML `.runtime/win-candidate-idna-fixed.xml` SHA256 `921ead0cc9d00106edb5769489f926c9fd8a0232e530d4f4d8ecfcb76b75ee7b`，保留两份。尚无HTTP上传、授权租约、持久事务或真实来源证明；旧Normalizer的trim/必填作者不等于新契约完整适配。

同期远端 `0a3ccf70efb569c39b3f91a558ab4b39140fd2f1` 纳入Mac前端流程/品牌及02A最终交接记录。正常整合到 `37592ed36e7979147bdc187d57dabe6801d3b02b`，只解决任务书冲突：保留Mac02C接收、Win09A状态和双方全部代码。`supplychain_readiness` 独立核对index中UI与0a、候选模块与d145完全一致；未把未暂存runtime修复混入。根代理在Windows以Node24.19执行 `vitest run tests/ui tests/taskOperations.test.ts`：39文件/423 passed，随后typecheck通过。此结果不取代Mac493/1skip或完整Windows构建；P10字段与品牌截图限制仍按[Mac审核](ui-flow-completion/REVIEW.md)保留。远端两原始日志自带空行/尾空格，未改写其字节；排除这两日志的集成diffcheck通过。

## 6. 统一运行时与整合后完整Windows构建

运行时修复 `0b79a6884b5a4047a06c396d8af5a5cca0da7f12`：首项Node最低要求24.15；直接用选定Node运行npm CLI，按真实npm-prefix语义定位，不再用npm.cmd选择另一个Node。只修改子进程环境副本，报告只序列化6个白名单字段；package/lock仅根engines改变，依赖节点未升级。

作者 `windows_bootstrap_fix` / PS子执行者 `runtime_bootstrap`，独立reviewer `win_contract_readiness`。原evidence三反例RED，runtime实际CLI与范围/环境反例RED，PS真实无Node/首项24.11拒绝RED后修复。第一次34项通过仍被独立审核发现P2：11个实际x64 Node夹具未隔离Mac ARM适用范围。修复仅测试门禁，生产限制不放宽；新增8项选择矩阵有4 failed/4 passed的逻辑RED，不能称为实际Mac执行。最终独立42 passed/2 skipped，原Windows34项均实际通过；2个新skip是当前x64主机不适用的非x64/不支持Windows宿主拒绝分支。根代理连同staging复跑64 passed/2 skipped，typecheck通过。没有真实Mac ARM或Windows ARM复跑证据。

整合后Python候选/来源/解析/导入/身份/会话/UI十文件：316 passed（2.02s）；`.runtime/win-integrated-candidate-ui.xml` SHA256 `54f0c561da5e1e0b32ee99869cd6f6cdb9f7a3f2752478188493466d287a8564`。与此前PG全量不是同一集合，不以316替代真实数据库或58个既有Windows失败的处置。

从干净提交 **`f4d4a560993a4c02d897e60712f4f51b0265c9f1`** 实际执行完整脚本；仅当前PowerShell进程的PATH前置已选Node目录，不改机器设置。报告 `dirty=false`、Node24.19.0、npm11.6.2、`adjacent-local`、`selected-node-direct-cli`；Node和CLI摘要均记录，未出现旧Node依赖engine警告。

| 阶段 | 本次结果 |
|---|---|
| preflight / dependencies / typecheck | PASSED |
| unit-tests | PASSED，52文件 / 550 passed / 2明确skipped，69.84s |
| native-smoke | PASSED，实际Electron Origin、内存Cookie、会话隔离、拒绝重定向及退出清理 |
| make-win / artifacts | PASSED，Squirrel中文工作区已通过staging制作；产物记录不等于发行通过 |
| archive-check | FAILED，校验脚本误报主入口不存在，后续定位为Windows ASAR查询路径分隔符不匹配 |
| packaged-smoke | NOT_RUN |
| 安装、可见运行、卸载、缩放 | UNTESTED |

550/2及69.84s来自根代理完整构建控制台（exec session 9670），不是JSON内置计数字段；JSON仅记录阶段状态和退出码，未另存本次控制台原始日志。

失败报告 `desktop/out/windows-evidence/2026-09-09T11-31-01-267Z-c0ae1c30/windows-build.json` SHA256 `583f8377901f1ee5af20cd075711b323f8bb9a2bc61eb0a34aaab4c8476f422a`，未覆盖旧make失败报告。其ASAR SHA256 `aee5e624987dd99f4b6b820d92003e2f00a1c5904a5aaac23b01af55a702a52a`，Setup SHA256 `dbea9147ff5aed17b0851b74bd3e079ae7e8ef25c550da3b9439610e12d149b1`；均为**全链失败候选，不提供安装验收或发布批准**。

根代理只读列出该ASAR实际42个条目，并用 `path.normalize` 查询同一未修改归档，读取主入口80406字节、preload502字节、index584字节。原入口确实存在，不归咎于Vite漏打包；应按[校验器修复计划](../superpowers/plans/2026-09-09-win-asar-verification.md)补真实ASAR/CLI反例，不修改归档或跳过检查。npm仍报告17 high及已有弃用/git完整性警告，Vite仍有旧选项弃用警告；不视为随打包路径或运行时修复自动关闭。Goal保持ACTIVE。

## 7. ASAR修复后Windows自动链通过，保留夹具清理缺口

修复提交 `3c16faca1fb243652f70d08327a30ddc771fc1ef` 仅在ASAR读取边界加入 `path.normalize`，新增18项真实归档/实际CLI测试，固定CJS、原始manifest白名单、非空资源和秘密文件拒绝规则不变。作者 `windows_bootstrap_fix` 的完整包正例在旧实现明确RED；修复后与renderer回归共21 passed。独立 `win_contract_readiness` 规格/架构/代码/质量PASS，实际21项/typecheck通过；root再跑21项通过（exec 2e6355），typecheck/secret scan通过。原归档重新校验32项资源，SHA仍为aee5e624…，未修改旧失败JSON或以改包让检查通过。

根代理合跑五个相关文件时曾出现1 failed/84 passed/2 skipped（19:44:29，exec 3c807d）：`windowsBuildRuntime.test.mjs` 的真实dependency-exit测试在afterEach清理临时Node时EPERM。只读确认残留Node非ReadOnly、ACL无deny，未发现从该临时路径运行的进程；AvlVDu夹具与bundled源Node共享同一NTFS File ID，当前夹具优先hardlink，不是独立文件。未捕获故障时句柄，不能认定具体占用者或杀毒软件；历史临时目录保留，不绕过删除限制。按[夹具隔离计划](../superpowers/plans/2026-09-09-win-runtime-fixture-isolation.md)继续，不靠重跑成功抹去此缺口。

随后从干净 **3c16fac** 运行完整脚本（exec session17526）：**53文件/568 passed/2 skipped**，66.37s，计数来自控制台chunk d1943d；所有9个自动阶段PASSED，包含Squirrel制作、ASAR 32资源校验和真实包内Electron冒烟，最终exit0。冒烟覆盖实际main/preload/renderer、沙箱/自定义协议、IPC拒绝、未配置服务、隔离临时文件CSV/备份导出及取消、未保存退出确认；保存/退出对话框在隔离进程被替代，**不构成用户手动安装或可见交互验收**。本轮通过不证明前述间歇夹具清理已修好。

成功报告 `desktop/out/windows-evidence/2026-09-09T11-45-38-367Z-cc8227d5/windows-build.json` SHA256 `0126fed3ba69286e7b82a7aec4934be8956e61cebba0bf4d243e02574dcf2599`；ASAR SHA256 `aee5e624987dd99f4b6b820d92003e2f00a1c5904a5aaac23b01af55a702a52a`；本轮Setup SHA256 `25b6465e7c69228f8f14e233bc84681088b152586353e98621420c986f371220`。Setup因重新制作与上一失败候选不同，不把旧Setup摘要回填为本轮。人工11项仍UNTESTED，17 high仍未消除，正式签名/安装更新/真实业务不在此次通过范围。已正常推送main 3c16fac并用ls-remote核验；Goal继续ACTIVE。

## 8. 独立Node夹具与第二次完整自动链

`84c4b6ff2c5f117a7303da59cdc4f14b74309207` 只改runtime测试：每个Node夹具独立copy，新增source/A/B文件身份、nlink及摘要检查和真实IPC A存活时清理B的反例。身份测试原hardlink明确RED（3个路径仅1个文件对象），不是EPERM确定性复现。作者 `windows_bootstrap_fix`，独立 `win_contract_readiness` 规格/架构/代码/质量PASS，实际runtime34 passed/1架构skip、typecheck通过；root五文件87 passed/2 skip（exec 142658，11.65s），另行typecheck通过。

根代理从干净84c4b6f再次完整构建（session50349，结果chunk b346b2）：53文件/**570 passed/2明确skipped**、67.12s；9自动阶段全部PASSED、exit0，含原生与包内冒烟。报告 `desktop/out/windows-evidence/2026-09-09T11-58-05-200Z-3c0d0702/windows-build.json` SHA256 `a4051e39ed44b5def7ed642480db2ba0b7e0fcdc69f09983e32c16aeaabd38cb`。本轮ASAR仍为aee5e624…；Setup SHA256 `3b1c89810ab89081d345a1ad06679366c6120c1439b2c1ebdc971b527fb11155`。人工11项仍UNTESTED，17 high仍在，不重写旧报告。

作者及root分别检查：新增runtime临时目录/子进程无遗留，历史AvlVDu/Mk7kCl仍原样保留；未调整权限或删除共享原Node。此修复证明文件隔离与本轮清理边界，不宣称所有Windows环境永无间歇故障。与3c16相比仅新增2个测试，不把总数差当产品功能数量。

## 9. 新设备持钥后端的Windows限定接收

Mac后续 `65d867640ea216769adb5f947f5dea8fb7b31a35` 含 `c3702c0` 设备持钥切片，代码已进入远端main但未因此自动ACK。Win保留冻结detached检出 `.worktrees/review-device-65d8676`，以独立非editable CPython3.11.14/PyNaCl1.6.2/cffi2.1.1环境按lock安装，不污染原win-dev环境。

独立 `supplychain_readiness` 核对严格Ed25519点/编码、UTF-8原字节、双签轮换、session→device锁序、数据库实时到期、owner/FK/RLS和显式最小授权，未发现P0/P1/P2；本机纯协议/身份/会话三文件53 passed（包含先跑的20项，不累加）。额外合成点/编码反例通过。发现两处非阻断文案：Origin中间件403不属于路由no-store JSON，以及session_digest实际为encoded payload字节SHA256；本次修正文档，不改变签名协议或HTTP行为。

root独立使用官方PostgreSQL16.15一次性Docker实例（127.0.0.1随机端口、tmpfs、`--rm`），在新win_pilot/win_identity库和NOSUPERUSER/NOBYPASSRLS角色下验证。新设备测试先于旧identity夹具运行；另外升级测试自己建立最小角色/105库，重复106及显式grant，验证无users UPDATE、新表DELETE、schema CREATE，不能把后续旧夹具的宽授权当作本次最小权限证明。

| 验证 | 本次Windows结果 |
|---|---|
| 7文件设备/身份/会话PG定向 | **123 passed，19.29s，0 skip**；exec 8e9c6a |
| 全仓Python（同65d，`-X utf8`） | **908 passed / 54 failed / 0 error / 0 skip**，92.99s，962总计；exec 1204f4，退出1 |
| 旧失败集合对比 | 54全部属于原222的58个既有Windows失败，无新增失败名；少的4个在原222加`-X utf8`复跑也通过（exec 9db32e，4 passed），不归因设备功能修复 |
| Windows真实Node→HTTP→PG | Node24.19本机生成且仅在内存持有私钥；实际loopback HTTP调用绑定/证明/双签换钥/成功重放/旧钥拒绝/历史回执，受限角色实际落PG；两轮通过，第二轮exec 228505 |
| 主线整合定向 | staged集成后8文件323 passed，1.76s，exec 123f91；不同于123/962集合，不相加 |

定向XML `.runtime/device-targeted-65d8676.xml` SHA256 `2d15ad8a8a34e60129cdb331e0390c5fb263f2bbbffdd69a6bd93ec6b32a46e5`；全量 `.runtime/device-full-65d8676.xml` SHA256 `44393e5cb3c3180a8ce9d9cb6da1b6b049c8b1f311f34b52d8a9d3266679dd08`。不把Mac旧925测试数复制为Win或65d全量结果；新65d还包括Win此前37个IDNA反例。

Node探针只导出公开key/signature，产品测试token经stdin传入；子进程env只留系统/临时目录字段，不继承数据库或服务端密钥。临时服务明确使用仅loopback开发HTTP，不等于生产TLS或私钥落盘验收。工具在 `.runtime/review-device-65d8676.ps1`、`review-device-probe.py`、`review-device-node.mjs`。独立 `windows_bootstrap_fix` 发现原工具stop失败仅警告的P2，root改为失败退出并核对精确容器消失；新ProbeOnly轮再次通过并确认移除，不覆盖第一轮XML。第一次容器亦已独立查无残留。旧POSIX supervisor失败留下的本轮pytest-15子进程经精确命令行/ID核查后终止，未碰其他服务；未删除其测试文件。

正常集成提交 **`f9255603435862d8e8ead60b0357851c8c9e3075`**。独立 `win_contract_readiness` 核对index：Mac19非任务书blob与65d完全一致，desktop与84c完全一致，唯一任务书同时保留双方状态。CodexWin于2026-09-09对**65d中的持钥后端子链限定ACK**，以本次勘误契约为消费说明；父01C仍IN_PROGRESS。尚无连接版本/执行租约/领取续租取消/结果提交授权、02B上传或09D私钥安全存储，不据此激活平台capability；真实安装、收发、生产和客户UAT仍未验收，Goal继续ACTIVE。

## 10. 最新Mac前端交叉审核及Windows重新构建

追加接收远端 **`9e27723b4513d184438da44628017c237e895fe0`**，其中前端候选 **`58c8a7d3a8743f5f2eb9590e93ba8c2c66751fd9`**，Mac构建基线b89df6c及其最终整合证据见[UI验收](ui-final-acceptance/REVIEW.md)。Win冻结detached副本独立检查，不把Mac的626/21、20页截图、120视口记录称为本机实测，也不沿用旧84c的570项作为新UI构建结果。

`win_contract_readiness` 独立审核P07原请求/摘要持久保护、P16断连状态机及身份切换；`windows_bootstrap_fix` 只读辅审P10四锚点事实、期限/导出、TermEditor/client和视觉入口隔离，范围内无新增P1/P2。默认候选服务不可用、断连接口无服务端原子账号版本/请求查询、本机ledger非跨设备幂等等限制保留；此为前端切片接收，不是这些后台功能上线。

root在合并内容上实际执行：UI新增相关10文件 **99 passed / 6.81s**（exec4e835f），Python UI/session/identity/device/candidate五文件 **239 passed / 1.08s**（exec62feb6），TypeScript检查exit0（570a42），secret scan clean（684449）。不同集合不相加。后端/迁移/依赖锁与65d无变化，沿用第9节版本绑定的真实PG结果而非重报一次全量。

正常合并提交 **`4454a453d09b7e83d48c16b5650ad8a486466d32`**，亲本d027d77和9e27723。独立`supplychain_readiness`核对合并index PASS：Mac全部UI和证据保留，desktop相对9e仅多Win已审runtime隔离测试；三个文档冲突保留Mac925/962历史、最新05A行与Win01C限定ACK/09证据。两文首段明确历史时点，不把旧“未接收”覆盖新ACK。R4仍是`PROPOSAL_PENDING_CONFIRMATION`，不批准新实现或改动V0.2 Goal。

root从干净4454a45执行完整`desktop/scripts/build-windows.ps1`（session13080）：Windows11 x64，Node24.19.0/npm11.6.2，报告`dirty=false`；**61文件 / 647 passed / 2明确架构skipped**，68.40s（控制台chunkd7bde3）。9自动阶段全部PASSED、exit0（最终chunk468b42），含锁定安装、类型检查、原生会话传输、Squirrel、32项ASAR资源校验和实际包内main/preload/renderer冒烟。包内测试仍按第7节隔离替代对话框，不能当人工安装/可见流程通过。

| 当前产物或报告 | SHA-256 |
|---|---|
| `desktop/out/windows-evidence/2026-09-09T12-24-49-635Z-617145af/windows-build.json` | `5ebf191addd13ee26d70137d1afbda45748a113775f2261f6277fe5d7ccb741e` |
| `desktop/out/意客AI-win32-x64/resources/app.asar`，1615399字节 | `6f22e47ff71220c842cbc50d36bca0b81799d10971ec91836dd4dde43bea85a0` |
| `desktop/out/make/squirrel.windows/x64/YikeAI-Setup.exe`，146782208字节 | `17a01bc93eb86d8933345179f47a5fb2d7d292524a16c05120a5580ef9cf1078` |

额外只读检查实际新ASAR 42条目/24文本条目：无tests目录；3个已在RecoveryControls原文确认存在的TEST控制标记，在包内均无匹配（exece96bc7）。此为指定路径/标记检查，与独立源码隔离审核相互补充，不冒充全部模块图验证。安装包Authenticode实际`NotSigned`（exec4cb10f）。同目录人工表11项仍UNTESTED，17 high及已有依赖/构建弃用警告保留。

范围`git diff --check`有6个原始UI QA日志尾空行/尾空格，逐一确认与远端原始blob相同；排除这6份原始日志后代码/文档差异检查通过。不改写日志以制造全范围clean；此前失败报告保持原样。05A/09及整体产品未DONE，真实业务、人工安装/更新/缩放、生产与客户UAT另验。

## 11. 54个既有Windows失败的只读分类

`windows_bootstrap_fix` 结合第9节全量XML与冻结65d源码分类（`supplychain_readiness`辅核shell入口）；相关实现至4454a45无差异。本次只读分析未复跑/修复这54项，不把“旧失败”或平台差异一律解释为可忽略。

| 共同阻塞或环境假设 | 数量 | 证据与下一步边界 |
|---|---:|---|
| 私有目录精确POSIX权限门禁 | 27 | `app/collector.py:716` 的chmod/700检查，失败由362处映射；阻止后续运行时验证/子进程启动。CLI/collector/D03多项缺文件或未触发中断是下游表现，不能称安全隔离已验证；XML未保留底层异常，不保证只改权限后27项全绿。Windows需实际ACL方案 |
| 取消/超时进程树 | 2 | `app/collector.py:135` 直接依赖os.killpg，Windows无此分支；测试亦含POSIX假设。需Windows真实子孙进程清理证据，不能仅kill父进程或skip |
| 锁定补丁checkout字节改变 | 1 | `tests/test_collector.py:508`；实际i/lf w/crlf，原字节摘要不等于lock，仅在内存恢复LF后精确匹配。建议限定.gitattributes及真实autocrlf检出回归，不改锁摘要、不放宽校验 |
| 原生直接执行.sh | 11 | `tests/test_vendor_packaging.py:38` 一类WinError193；尚未运行包装器业务逻辑 |
| PATH选择不可用WSL Bash | 10 | backup 2项、CP06 8项，缺/bin/bash；服务端Linux流程仍需在适用环境实际验收，不能记业务通过 |
| 创建symlink缺特权 | 3 | collector 1项、vendor 2项，fixture阶段WinError1314；未验证产品重定向防护，需明确能力条件及Windows重解析点反例 |

合计54。采集器测试使用旧SQLite实验路径，暴露真实兼容缺口但不是PostgreSQL设备持钥新增回归。原始XML摘要和908/54结果仍以第9节为准，不将分类作为关闭V02-10E或发行门禁的证据。

## 12. 额外确认的备份完整性P1：未修复，阻断CP-06放行

只读分类中`supplychain_readiness`发现，`windows_bootstrap_fix`交叉确认：`scripts/backup_pilot.sh:54`及`restore_pilot.sh:50`调用`openssl dgst -sha256 -mac HMAC -macopt "key:file:$passphrase_file"`。该参数实际将`file:`加文件路径的字符串作为HMAC密钥，而不是读取秘密文件内容。AES加密另用`enc -pass file:...`，本发现不代表明文已经泄露，但现有侧车不能提供所宣称的秘密密钥认证。

root独立使用本地Git OpenSSL、固定TEST消息及根本不存在的`/TEST-NONEXISTENT-PATH/backup-passphrase`进行最小反例：命令exit0，输出严格等于Python标准库以字面`file:/TEST-NONEXISTENT-PATH/backup-passphrase`为key计算的HMAC-SHA256（exec5cc3ac）。独立`supplychain_readiness`另用OpenSSL3.0.16和.NET标准HMAC复现同类不存在路径反例（exec8af699）。均未读取真实秘密/备份或访问数据库。知道或猜到路径者可对改变后的密文重算相同方案的侧车，不需要知道加密口令即可伪造这层MAC。

这是4454a45继承的既有脚本问题，不是设备/UI新增回归，也不是54个Windows入口失败直接证明的结果。当前两个backup测试只验证生成sidecar及不重算MAC的简单尾部篡改，未覆盖秘密内容绑定、换路径恢复或路径密钥伪造；原通过数不能将本项关闭。**状态：P1已复现、修复未实现，CP-06备份恢复认证门禁不通过。**

下一优先级：测试先覆盖上述反例，再独立审核不将秘密放入命令行/日志的版本化认证实现及历史备份处理规则；不得自动接受旧的路径MAC当作可信备份，不删除既有备份、不自动恢复生产库。修复后另需适用Linux环境的真实脚本/隔离PG恢复演练，本轮Windows桌面绿色构建不替代此验证。

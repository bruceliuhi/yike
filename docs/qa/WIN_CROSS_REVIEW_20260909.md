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

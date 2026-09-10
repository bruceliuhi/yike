# Windows 离线采集运行包实施计划

> **For agentic workers:** REQUIRED: Use `subagent-driven-development`; steps use checkbox syntax. 用户已授权 Win 独立推进正常实现决定。本计划沿已批准客户 Windows 交付范围执行，不重复请求方案确认。

**Goal:** 生成能搬到新目录独立运行的离线采集 payload，供客户端首次启动安装使用，不要求客户安装 Python、Git 或 uv。

**Architecture:** 构建机从已核验的固定版本采集运行时、明确 Python home 和项目源文件生成新目录。采集器保持原锁定依赖；host 使用项目锁定的少量依赖，避免借打包无意升级。最终清单覆盖全部输出文件，探针仅验证本地加载/Chromium，不登录、不采集、不发送。下一批才把此产物接到 Electron 安装及现有连接页。

**Tech Stack:** Windows CPython 3.11、既有私有目录/Job 监督器、Playwright bundled Chromium、pytest、Electron Forge 后续消费。

## 设计及本批边界

- 不直接复制虚拟环境启动器：当前 `pyvenv.cfg` 指向开发机的绝对 Python home。复制真实解释器、DLL、标准库并生成固定相对 `._pth`，不读取客户 PYTHONPATH、注册表或用户 site-packages。该隔离机制依据 [Python 官方 Windows 文档](https://docs.python.org/3.11/using/windows.html#finding-modules)。
- 两个启动位置共享可复制的标准库来源，但 host 与 crawler 使用各自依赖目录。crawler 入口仍为 `runtime/.venv/Scripts/python.exe`；host 为 `host/python.exe`。`project/` 只放固定 host 模块及治理文件。不要复制整个后端或工作区。
- source/runtime 与输出目录互不嵌套；新目录独占创建，私有 ACL、拒绝重解析点/硬链接。失败保留半成品但不发布完成清单，不删除/覆盖已有运行时、账号 profile 或客户文件。
- 上游源码用固定 Git tracked 集合与补丁清单约束；只构建机用 Git。依赖文件按明确安装包/版本集合复制，排除 pycache、venv 启动器、Git 历史、安装缓存、cookie/profile、采集数据、临时文件和真实环境配置。保留许可与版本溯源。
- 输出 `bundle-manifest.json` 包含 schema、源码/治理版本、各相对文件路径/大小/SHA256、固定入口和实际本地探针结果。清单不是平台已就绪或安装器认证；后续 Forge 必须把清单摘要绑定到 ASAR 内，运行前复核。
- 不修改当前 packaged 门禁，不做下载器、自动更新、服务端部署或 UI 重构。本批 payload 不是可给客户试用的完整安装包。

## Chunk 1: 可搬迁产物生成与验证

### Task 1: 固定输入与文件集合

**Files:** 新建 `app/windows_portable_bundle.py`（构建编排）、按需 `app/windows_portable_inventory.py`（固定集合/清单）；测试 `tests/test_windows_portable_bundle.py`。复用 `app/windows_runtime_install.py`、`app/windows_private_directory.py`，仅在实际兼容问题有失败用例后修改既有文件。

- [x] 写失败用例：不存在生成器；输入重叠、已有目标、非法路径、源码/依赖版本不匹配、重解析点/硬链接、私密路径不能进入输出。
- [x] 运行 `python -X utf8 -m pytest tests/test_windows_portable_bundle.py -q`，确认针对缺失行为失败。
- [x] 实现显式绝对参数 `project_root / installed_runtime / python_home / host_site_packages / destination / git_executable`，不搜索 PATH，不读取/打印凭据。固定输入核验完成后才写新目标。
- [x] 生成 `host/`、`project/`、`runtime/`；crawler 保持治理源文件和原依赖版本，host 保持项目依赖版本。固定 `_pth` 不启用任意 site hook。对子进程显式禁止字节码写入，避免验证后污染只读产物。
- [x] 相同定向测试转绿；自查无旧路径残留和运行时秘密文件，列明精确依赖及字节规模。

### Task 2: 实际搬迁和本地探针

**Files:** 同上生成器；新建 `tests/test_windows_portable_bundle_local.py`（明确 Windows/显式环境输入的真实本地验证，不把跳过当通过）。

- [x] 写失败用例：必须在不同输出位置，清空开发机 PATH/PYTHONHOME/PYTHONPATH、关闭用户 site 下通过 host 入口导入和固定 CLI help；缺失/改动依赖必须失败。
- [x] 实现有界本地 probe：host/source/login 模块加载；crawler `main.py --help`；复用 `run_supervised_process` 和本地 Chromium about:blank Unicode 检查，不访问外部平台。记录物理退出与真实版本。
- [x] 只有三类探针通过且全量输出摘要完成才独占发布清单；probe 失败、超时/取消不发布。输出仅固定错误码，不转储子进程日志。
- [x] 在新的私有目录实际生成并执行上述探针，记录来源、清单摘要、入口、字节量；复核搬迁后的解释器与模块路径均在新 payload 内，未回退原开发机 Python。
- [x] 非作者一次先规格后代码/质量审核，修复只重验差量；本批不跑全量后端、不构建尚未接 bootstrap 的无效客户安装包。主干提交承载本记录，远端提交是否成功以 Git 推送结果为准。

## 本批交付与验证（2026-09-10 恢复后）

用户“没完成的部分 完成后提交gitee”恢复上一暂停 WIP。本批关闭离线运行包及回复持久层修复，不代表产品整体完成。提交前同步并保留 `8f8da34` 的完整 V0.2 目标；回复两文件与其接收的 `4c683ac` 字节完全一致，Mac 最新受限 PG 复验另有 **55 passed / 0 skipped**，见[回复 QA](../../qa/V02_REPLY_PERSISTENCE_CONTRACT.md#mac-接收-win-回复修复2026-09-10)。不重复修改或重验该来件，不覆盖 Mac 未提交工作；Win 运行包交付边界以上述本批为准。

- **源码：** `96bb371` 保留 WIP，`e2b75ce9e731becb8ee84ed25290df3c20128639` 修复两项外部 wheel RECORD 的精确包名/版本/路径映射；`eff571ff9a84a769bcebab629807dff98e8cec38` 仅修正实际搬迁测试。host 六包、crawler 90 包不升级，清单逐项记录版本。独立规格/代码/质量审核覆盖本批产品与测试，差量只审变动文件。
- **运行包：** 由干净 `e2b75ce` 生成一次，随后实际重命名整个目录为 `C:/Users/bruce/AI/意客AI2026/.runtime/portable-candidate-20260910-01-relocated`；原生成目录已不存在。包含 11,197 个清单文件、1,277,939,567 字节（不含清单自身）；清单 SHA256 `90f5eca489eaf0c8b6176fb57bdf4068f98906a0306ea601d6550765d8dfa2bd`。本地产物不提交 Git，也不是客户安装包。
- **入口：** `host/python.exe`、`runtime/.venv/Scripts/python.exe`，分别通过相对 `_pth` 加载本包项目及依赖。实际 Python `3.11.14`、Chromium `149.0.7827.55`，CLI help 包含 `xhs/dy/bili`。本地探针不访问平台。构建显式用 `C:/Program Files/Git/bin/git.exe`；`cmd/git.exe` 硬链接被拒绝，未放宽规则。
- **定向结果：** portable 单元 **26 passed / 3.16s**。真实生成时三类探针通过、清单发布、目录搬迁成功；独立复验最初因测试误删 Windows 必需的 `SystemRoot`、`USERNAME`、`PATHEXT` 失败，修正仅限测试环境。最终对同一清单运行 `tests/test_windows_portable_bundle_local.py::test_explicit_retained_portable_bundle`：**1 passed / 0 skipped / 11.00s**，覆盖私有 ACL、全量摘要、污染 Python 环境下隔离导入、搬迁后真实 CLI/Chromium及探针后摘要不变。PATH 仅含 System32 和本包自带 Node 目录，未回退开发机 Python/Node；未因测试修复重构相同 payload。
- **回复修复：** `pilot/reply_store.py` 与 `tests/test_reply_store_postgres.py` 保持 `96bb371` 相同字节，关闭首次登记 42501、更正 revision 冲突、跨归属更正、并发去重及非授权已读修改；独立审核 Approved。复用暂停前 **66 passed / 6.51s，其中 32 项真实受限 PostgreSQL**（工具证据 `b4c0c3`）。本轮相同六文件复测 **34 passed / 32 fixture ConnectionTimeout**：`docker-desktop` 停止，但 Docker 后端仍监听 58031，TCP可达不代表PG可用。未绕过权限、重启共享 Docker/WSL 或把超时写成通过。非PG 34项与历史66项不累加。

复验同一运行包必须显式给出 `YIKE_PORTABLE_EXISTING` 和上述 `YIKE_PORTABLE_EXISTING_MANIFEST_SHA256`，选中 retained 测试；首次生成测试仍要求全部显式构建输入、新目标和新 pytest 临时目录，不覆盖既有产物。历史 RED、环境失败和暂停记录继续保留。

## 接续（不计本批完成）

Electron 从绑定摘要的离线 payload 异步安装到客户私有新目录，现有连接页显示准备/可用/失败，退出等待安装与浏览器停止；配置成功才创建登录/采集控制器。完成此路径后再冻结一次实际安装候选，验证安装、登录入口、退出重开及真实账号批次。服务端地址、用户登录与真实发送审批仍分别遵守既有边界。

### 2026-09-12 Mac触达来件的离线包接收修复

基线`7085f2a`。代码已接原生确认/触达，但旧HOST_FILES没有4个触达模块，新构建也会遗漏；旧host探针未导入它们，不能证明新功能可随包运行。Mac仅串行补本次触达必需的4个固定文件与host导入探针，同时更新原搬迁验收的导入集合；不改Win安装器/ACL/Job/依赖版本，不复制整个产品仓库。

新增`tests/test_portable_outreach_imports.py`将真实HOST_FILES复制到隔离项目目录，以`-I -B`子进程实际导入4个模块并核对所有app/pilot/connectors来源。先RED复现`ModuleNotFoundError: app.windows_platform_outreach`，补清单后1项PASS；不是mock导入，也不是Windows二进制/Chromium验收。没有重跑全套或重新生成1GB运行包。旧`90f5eca4...`产物不含这些模块，仍仅作为原采集包历史证据；触达版必须由新源码生成新清单，再按原真实搬迁流程验收，不能复用旧摘要宣称支持触达。独立代码/依赖闭包/探针兼容审核在`433a479001070e3d640686c65abc5ba8a3a996d0`结论GO、0阻断，审核不重跑测试或构包。

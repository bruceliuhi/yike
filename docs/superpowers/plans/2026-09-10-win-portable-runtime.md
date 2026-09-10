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

- [ ] 写失败用例：不存在生成器；输入重叠、已有目标、非法路径、源码/依赖版本不匹配、重解析点/硬链接、私密路径不能进入输出。
- [ ] 运行 `python -X utf8 -m pytest tests/test_windows_portable_bundle.py -q`，确认针对缺失行为失败。
- [ ] 实现显式绝对参数 `project_root / installed_runtime / python_home / host_site_packages / destination / git_executable`，不搜索 PATH，不读取/打印凭据。固定输入核验完成后才写新目标。
- [ ] 生成 `host/`、`project/`、`runtime/`；crawler 保持治理源文件和原依赖版本，host 保持项目依赖版本。固定 `_pth` 不启用任意 site hook。对子进程显式禁止字节码写入，避免验证后污染只读产物。
- [ ] 相同定向测试转绿；自查无旧路径残留和运行时秘密文件，列明精确依赖及字节规模。

### Task 2: 实际搬迁和本地探针

**Files:** 同上生成器；新建 `tests/test_windows_portable_bundle_local.py`（明确 Windows/显式环境输入的真实本地验证，不把跳过当通过）。

- [ ] 写失败用例：必须在不同输出位置，清空开发机 PATH/PYTHONHOME/PYTHONPATH、关闭用户 site 下通过 host 入口导入和固定 CLI help；缺失/改动依赖必须失败。
- [ ] 实现有界本地 probe：host/source/login 模块加载；crawler `main.py --help`；复用 `run_supervised_process` 和本地 Chromium about:blank Unicode 检查，不访问外部平台。记录物理退出与真实版本。
- [ ] 只有三类探针通过且全量输出摘要完成才独占发布清单；probe 失败、超时/取消不发布。输出仅固定错误码，不转储子进程日志。
- [ ] 在新的私有目录实际生成并执行上述探针，记录来源、清单摘要、入口、字节量；复核搬迁后的解释器与模块路径均在新 payload 内，未回退原开发机 Python。
- [ ] 非作者一次先规格后代码/质量审核，修复只重验差量；定向验证后正常提交 main。本批不跑全量后端、不构建尚未接 bootstrap 的无效客户安装包。

## 接续（不计本批完成）

Electron 从绑定摘要的离线 payload 异步安装到客户私有新目录，现有连接页显示准备/可用/失败，退出等待安装与浏览器停止；配置成功才创建登录/采集控制器。完成此路径后再冻结一次实际安装候选，验证安装、登录入口、退出重开及真实账号批次。服务端地址、用户登录与真实发送审批仍分别遵守既有边界。

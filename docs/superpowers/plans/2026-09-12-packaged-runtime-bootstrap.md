# 正式Windows离线运行包接线

Base `28e063a`。执行既有Windows离线交付设计的接续，不增加下载器/升级器/外发授权。目标是正式包无需开发环境变量即可异步准备运行时，并把准备/失败/可用反馈给客户。用户要求省token：只跑变化路径，一次整批独立审核，修复只差量审核，不在Mac伪造Windows验收。

## Global Constraints

- 离线payload仍为既有`YIKE_WINDOWS_PORTABLE_BUNDLE_V1`，不增加第二种采集器、不更改依赖；清单SHA256编译进main/ASAR。构建显式提供payload路径与摘要，正式Windows构建缺失即失败；客户不能以环境变量更换运行时。
- 执行任何payload解释器之前，main逐文件复核绑定清单、固定入口、全部摘要/大小/路径及未列出文件，拒绝符号链接/硬链接/路径越界。代码包来源可读，客户安装目标必须使用现有Windows私有ACL创建；不读取账户秘密。
- 使用已完整核验的payload自带host/python执行固定安装模块；安装仅复制/核验，不启动浏览器、子进程、平台或网络。输出仅固定READY/FAILED结构。stdin不接任意代码；参数只有固定包根、新目标、绑定SHA256。
- 目标按manifest摘要命名置于userData下，父目录由main创建；既有目标只复核，不覆盖/修复/删除。新目标独占私有创建；中断留半成品，明确失败，不采用或启动半成品。复制完清单最后发布，所有文件复核/ACL完成后才READY。
- 安装进程仅自身（无进程树）；退出中止并等待物理close，超时清理未知阻止启用与退出门禁放行。异步初始化不阻塞窗口；准备完成且应用未退出才装配现有登录/采集/触达controllers。不放宽原平台实际发送allowlist。
- 这批只使正式包具备源码路径；真实Windows新payload、安装包/搬迁/重启及平台仍需原实机验收，旧payload摘要不是新能力证据。

## Task 1 — Python私有安装器（独立实现）

专属`app/windows_portable_install.py`、`tests/test_windows_portable_install.py`，必要`app/windows_portable_inventory.py`只将安装器加入HOST_FILES、`app/windows_portable_bundle.py`只在hostprobe导入安装器。不要修改desktop或治理文件。

实现`install_portable_bundle(source, destination, manifest_sha256)`及固定模块CLI `python -B -X utf8 -m app.windows_portable_install --source <root> --destination <root> --manifest-sha256 <sha>`。只win32可运行；复用windows_private_directory.create_private_directory/verify_private_tree，拒绝重解析点/硬链接，固定ENTRIES及清单schema。source可为正常包资源ACL，不能要求source是private ACL。先解析绑定manifest（上限16MiB、文件数50000、每文件<=512MiB、总量<=4GiB），只允许规范相对路径，大小非负整数、SHA256，大小写折叠不重复，必须含固定host/runtime解释器及4个触达模块/本安装器；拒绝manifest自列。检查source完整文件集合与逐项摘要，无未列出文件（仅manifest例外）、无link。路径与目标不重叠。

新destination父目录已经存在。使用原私有ACL构造整个新树（逐层新建private），文件xb并逐块复制/复核，manifest最后xb发布；随后verify_private_tree/完整摘要再次复核。已有目标只核验同摘要、固定完整树与ACL，失败不修复。错误对外固定`PORTABLE_INSTALL_FAILED`、不输出路径/环境/原异常；成功stdout一行`{"state":"READY","manifestSha256":"..."}`，失败一行`{"state":"FAILED","error":"PORTABLE_INSTALL_FAILED"}`并非零退出。禁止调用外部子进程/浏览器/网络。

测试用极小真实磁盘payload复现缺失/篡改/多余/路径逃逸/中断半成品/已有目标不覆盖；非Windows实际拒绝，WindowsACL边界允许测试注入但不标实机通过。report同目录`packaged-runtime-installer-report.md`，只提交自己文件。

## Task 2 — build绑定与Node bootstrap（根代理）

新增desktop共享portableManifest校验/文件复核、main bootstrap及定向tests；Forge explicit `YIKE_PORTABLE_BUNDLE_PATH`/`YIKE_PORTABLE_BUNDLE_SHA256`绑定复制到resources，因packager原extraResource保持源目录名，Vite将受限ASCII资源目录名与digest一起编译进常量；客户不能替换两者。开发start模式原配置保留。安装器固定上述CLI，用清洁环境，不继承Python/Git/数据库变量；有界stdout/超时/close与取消。返回原PlatformLoginDriverOptions固定子路径。正式包不使用env配置。状态GET专用只读IPC（NOT_REQUIRED/PREPARING/READY/FAILED），不给renderer传路径/摘要替换参数。

## Task 3 — existing main/UI组合（根代理）

提取现main控制器装配函数复用开发/正式配置；创建窗口后开始bootstrap，READY后才装配，不自动平台登录或执行采集。退出等待bootstrap停止。原Settings平台连接区展示准备/失败/可用提示，失败建议重启核对或联系支持，不给盲修复按钮；其他平台页面现有布局不重构。最终定向测试+类型检查、独立整批审核、normal push main。未实机的门禁继续开放待办、不标产品上线。

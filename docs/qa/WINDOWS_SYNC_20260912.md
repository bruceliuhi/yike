# Windows 最新主干接续（2026-09-12）

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

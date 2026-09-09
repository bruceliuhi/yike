# V02-09A 构建运行时一致性修复

> **For agentic workers:** Use `subagent-driven-development` for independent review, or `executing-plans` when helpers are unavailable. Keep this slice separate from Squirrel staging.

**Goal:** Windows自动构建使用同一个已选择的Node运行runner、npm和当前生命周期脚本，并准确执行锁定依赖要求的 `>=24.15.0 <25` 门禁。不能把外层24.19记录当作实际npm的24.11。

**Architecture:** Node runner根据Windows PATH中的npm.cmd位置、其npm-prefix.js及实际安装布局定位npm-cli.js，使用 `process.execPath` 直接调用。只给子进程传递前置该Node目录的环境副本，不修改机器PATH或npm配置，不执行npm.cmd shell来启动外层npm。保留npm的global-prefix优先规则及当前固定构建命令，不为未来嵌套npm命令添加临时shim。预检失败照常留下结构化报告；探测失败关闭，不记录配置、环境或异常全文。

**Tech stack:** Node stdlib / PowerShell / Vitest，依赖版本不变，只同步package与lock根包的Node engines字段。

## 实施与验证

1. 新增独立runtime模块及测试：真实Node子进程检验execPath、生命周期node路径、空格路径、退出码、PATH大小写合并；npm本地与global-prefix发现、缺CLI/坏输出时关闭。先获得明确RED，不以只断言mock被调用替代运行事实。
2. 对齐PowerShell与Node预检的24.15最低版本；保留缺Node证据和第一个Node选择语义。现有真实双Node测试使用满足最低版本的测试二进制；另加24.11和24.14拒绝、24.15/24.19接受及25拒绝的反例。
3. 在 `windows-build-evidence.mjs` 接入统一命令执行，记录最小npm运行版本/启动方式而不保存本机路径或环境。版本探测及安装/测试执行失败仍准确标为失败；不能带错误runtime继续构建。
4. 更新构建说明、package.json和package-lock.json根engines，独立复核后运行相关测试、typecheck及完整Windows链。只接受相应阶段的真实结果，17 high依赖风险另卡处理。

文件边界：`desktop/scripts/windows-build-runtime.mjs`、`windows-build-evidence.mjs`、`build-windows.ps1`，对应runtime/证据/bootstrap测试，package及lock根engines和PACKAGING.md。不修改staging maker/forge、业务UI、身份服务或迁移。

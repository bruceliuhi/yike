# V02-09A Windows Squirrel 中文工作区修复

> **For agentic workers:** Use `subagent-driven-development`; implementation and final review must be different agents.

**Goal:** 使已确认的中文源码路径下 Squirrel 打包失败得到最小、可验证修复，保留原产品名、安装文件名和证据位置；不代表安装、更新或产品上线完成。

**Architecture:** 仅在 Windows maker 边界将 Squirrel `makeDir` 指向本次独立的 ASCII staging 目录。成功后验证产物为普通文件，再按原目录结构复制到 Forge 提供的输出位置并返回实际路径。失败不得将残缺包作为成功产物。必须同时验证原 Maker 自己使用的 `os.tmpdir()` 为 ASCII：其复制的 `Squirrel.exe` 也会经 rcedit 编辑；非 ASCII 系统临时目录时明确拒绝，即使显式 staging 根目录为 ASCII 也不能伪称支持。可配置 staging 根目录只改变输出暂存位置，不改全局 TEMP、安装依赖版本或关闭资源编辑。仅清理已验证归属本次的 staging 子目录。

**Tech stack:** 现有 Electron Forge MakerSquirrel、Node 24、TypeScript / Vitest。

## 已批准范围与实测原因

依据用户持续开发 Goal 与 V02-09A。`e01e99a` 在 preflight、安装依赖、typecheck、363 单测、native-smoke 之后，make-win 失败。独立 2×2 真实 rcedit 对照证实仅目标 EXE 路径含中文触发 `Unable to load file`；图标中文路径可用。修复不触及 Mac UI、服务端和身份候选。

## 执行

1. 新增窄 maker 适配模块和测试（`desktop/build/`、`desktop/tests/`），按现有 MakerSquirrel API 检查参数/返回路径。先验证中文输出与 ASCII staging 的 RED。
2. 实现上述 staging、成功回拷、失败传播与仅本次临时目录清理，接入 `desktop/forge.config.ts`。测试成功回拷字节/哈希、失败不交付、路径越界/重解析点拒绝、ASCII 空格路径和无合法 staging 根目录时明确失败；非 ASCII `os.tmpdir()` 即使有显式 ASCII staging 仍须在调用原 Maker 前拒绝。
3. typecheck 与相关测试 GREEN；复用真实 rcedit 路径对照，记录二进制与产物 SHA。独立 reviewer 审核候选。
4. 根代理重跑完整 Windows 自动构建链，将新结果和此前失败分别保存。安装/可见启动/卸载/缩放仍单独验收。

选定 Node 与 npm.cmd 实际运行时不一致、最低 Node 要求及依赖漏洞是独立问题，另行测试修复，不归因于此次 rcedit 失败。

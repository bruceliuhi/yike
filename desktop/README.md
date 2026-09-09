# 意客 AI 桌面壳候选

该目录迁入自本地 `codex/self-use-auto-public-reply-v1` 的安全 Electron 壳，用作 V0.2 的 V02-09 / DP-D01 可行性基础。

当前只提供：

- `yike://app` 本地协议和白名单资源加载；
- sandbox、context isolation、无 Node 集成；
- 最小 preload API 和运行时状态占位；
- Electron Forge/Vite 构建配置。

当前不宣称：

- sidecar 或平台执行器已实现；
- Windows 新机安装、更新回退、休眠恢复已验收；
- 客户登录、平台连接、真实采集或真实触达已接通。

桌面壳不得持有服务端数据库、管理员连接或签名密钥。后续接入 V02-01 协议前，必须单独完成依赖安装、类型检查、打包和真实 Windows 验收。

# 意客 AI 桌面客户端候选

该目录包含 Electron 主进程、受限 preload API 桥接与已授权 R3/R4 React 页面。现有服务和未接通能力见 [R4 实现验收](../docs/qa/ui-r4/README.md)；界面、TEST 适配和自动测试不等同于平台采集、真实消息或搜贝计量已经接通。

构建与人工交付入口见 [PACKAGING](docs/PACKAGING.md)。Windows 用户以最终交付的完整 SHA 运行 `scripts/build-windows.ps1 -ExpectedCommit <SHA>`，对本次安装的主窗口运行 `scripts/verify-windows-install.ps1`，再填写生成的人工验收表。Mac 验证不能替代 Windows 缩放、安装/卸载和可见操作。

客户端不保存服务端数据库或管理员连接，不携带签名私钥。Windows 候选、签名和业务服务状态以对应提交的证据为准；历史桌面壳说明不代表当前实现范围。

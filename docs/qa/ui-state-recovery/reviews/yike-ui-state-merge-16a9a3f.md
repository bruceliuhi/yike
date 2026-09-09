# 16a9a3f 合并增量独立代码审核

- 审核日期：2026-09-10（Asia/Shanghai）。
- 候选：`16a9a3f4f2915f39d3650bf25c50dec24a6c0ea6`。
- 双亲：`bbdd235c99c8a1930860500e5ef36020d5c17c85`、`ff623eda1d7c037a279517ca668ecc467af0cecc`；共同基线 `a9d18db99255a7fe272e24a9260095462a1e3612`。
- 结论：**限定本次合并增量 PASS，未发现新增 P0/P1 或阻止合入的问题。** 这是代码整合结论，不是设备签名生产接通或 Windows 实机验收结论。

## 范围与检查

第一双亲到候选新增 8 个 desktop 文件：`deviceKeyVault.ts`、`deviceProofSigner.ts`、`shared/deviceProof.ts`，对应 3 个单元测试，以及 2 个 Windows 原生探针脚本；另有 5 个文档增量。现有 desktop 文件没有修改。核对双亲后，单方修改均完整保留；双方修改的任务书同时保留本轮 Mac 恢复状态进展、原验收边界和 Windows 新认领内容。

新增模块仅相互引用，现有 main、preload、renderer、service client、共享 IPC 契约及打包配置没有导入它们，也未增加签名 IPC。密钥库要求保护服务可用，按服务 origin／用户／设备隔离，写入使用排他创建和同步，异常不自动替换未知密钥。签名入口验证服务端挑战及请求、用户、设备、公钥、版本和到期绑定；本次增量不包含真实 HTTP 绑定、签名提交或任务启动接线。

`git diff --check` 通过。未审查或纳入 4 个未提交 raw candidate 草稿；未修改产品源码、启动原生应用或重建安装包。

## 实际验证

- 本审核独立执行 `npm run typecheck`：退出码 0。日志：[merge-16a9a3f-code-typecheck.log](../logs/merge-16a9a3f-code-typecheck.log)。
- 本审核独立执行 3 个新增测试文件：**85 passed，3 files passed，退出码 0**。日志：[merge-16a9a3f-code-tests.log](../logs/merge-16a9a3f-code-tests.log)。
- 核查主线程执行的合并全量日志及绑定记录：**1206 passed、22 skipped；104 files passed、1 skipped**。这是主线程执行、本人读取核对的结果，不与上述 85 项累加。记录：[全量日志](../final/merge-16a9-tests.log)、[调用记录](../final/merge-16a9-test-invocation.json)、[325 文件输入快照](../final/merge-16a9-test-source.json)。

## 现有包与交付边界

逐项比较原包记录的 177 个生产／构建输入，均未变化；新增文件没有进入现有生产导入图，因此本次没有重包。实际磁盘产物仍匹配原 [release-mac-package.json](../final/release-mac-package.json)：

- ASAR SHA-256：`79a52de9d645378e0903fd93c4f49ac4c9ce703592fc1b537875708b372c86fa`。
- ZIP SHA-256：`75d4f8b269e8ecef2b7211d267447189bea7f940e9d1fc3e0ee8b814b185de32`。

包继续绑定 `f18a922b778f437400de8165e67b162fea028724` 的构建输入及既有后续等价性记录；**不能将该包称为已接入新增设备持钥／签名能力**。新增模块的合并测试通过也不替代重新接线后的构建和真实平台验收。

本审核未重跑 Windows 原生探针；其作者／远端记录见 [V02_DEVICE_SIGNING_CLIENT_WIN_REVIEW.md](../../V02_DEVICE_SIGNING_CLIENT_WIN_REVIEW.md)，不冒称本审核独立实测。原 Mac 包仍无 Developer ID 签名／公证，原生可见验收仍限定 [NATIVE_ACCEPTANCE.md](../final/NATIVE_ACCEPTANCE.md) 所记录范围。本报告不批准真实设备注册、平台外发、Windows 安装包交付或完整 05F。

## 16a 之后的测试断言窄修

另以非作者身份核对根代理提交 `369a0494a71faf355e8c9cbb2c55505a4c80850e`（父提交为本报告 16a 候选）：仅 `desktop/tests/deviceKeyVault.test.ts` 添加 `createPrivateKey` 导入，并将 PEM 头正则断言改为实际解析密钥、以 PKCS8 PEM 重新导出后与原字符串精确相等。此断言加强格式有效性检查，原密文隔离、公钥对应、真实签名验证和重新打开持钥库的断言均保留；产品源码、扫描器及包输入没有修改。该窄修 **PASS**，前述产品合并结论可继承到此提交。

已读取根代理窄修后执行的 [33 项通过日志](../logs/device-key-encoding-assertion.log)，未重复计算为本人独立执行或 16a 原树的全量结果。原 PEM 头测试字符串曾触发扫描器误报，本报告不宣称未修的 16a 原树 `secret_scan` clean；修后扫描证据由最终提交门禁另行记录。

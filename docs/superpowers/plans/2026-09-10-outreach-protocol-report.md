# 07B Task 1 私有派发协议短报告

- 文件：`desktop/src/main/outreachDispatchProtocol.ts`、`desktop/src/main/outreachDispatchSigner.ts`、`desktop/tests/outreachDispatchProtocol.test.ts`。
- 定向结果：`vitest run tests/outreachDispatchProtocol.test.ts`，18 passed；本任务实现后单次 `tsc --noEmit` 退出 0，根任务随后已合跑最终类型检查。
- Python 对照：用 Python 3.12 的真实 `DispatchRequest.model_validate/model_dump` 与 `signing_payload` 生成 CLAIM 字节，SHA-256 为 `e635edfb9f1120abd1c8ed038496e722ecb20ae1a0b50d125e9469c1c250ea56`；测试固定该向量，覆盖 `resultId/outcome` 的 null 展开、Unicode 与原 UTF-8 字节签名。
- 边界：仅允许三个固定私有 operation 和固定路径；Ed25519 公私钥、设备 scope、服务 origin、user/tenant、session digest、完整 request 与 Python canonical bytes 均校验。固定错误码不泄露底层密钥或路径诊断。
- 未证明：测试中的平台回执仅为协议 fixture；未操作真实平台，不证明真实发送、平台接收或端到端上线。

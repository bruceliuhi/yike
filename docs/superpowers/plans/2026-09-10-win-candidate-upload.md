# Win 候选上传接续 Implementation Plan

> **For agentic workers:** Use subagent-driven-development and TDD. 用户要求每批一次独立SPEC→架构/代码/质量审核、定向验证；不逐小改构包或重复全量。

**Goal:** 将已批准候选签名接续合同接到Win产品ServiceClient和主进程持钥模块，完成实际Node→HTTP→PG上传与原复合键查询。

**Architecture:** 复用现私有设备/执行队列和设备vault模式；新增私有候选通道，不开放renderer或任意签名。完整batch先严格规范化、冻结并核对摘要；签服务器原UTF-8字节。真实worker、持久批次恢复和UI装配继续后续，不以本模块冒充采集可用。

**Tech Stack:** 现Node24/TypeScript/Zod/Ed25519，现FastAPI/专属PG测试，无新依赖或后端改动。

依据：`docs/contracts/V02_RAW_CANDIDATE_INBOX.md`、`2026-09-10-candidate-submission-signing.md` 已批准最小接线。base `00989b3`，隔离 `.worktrees/win-candidate-upload`。Win独占以下desktop模块及新集成测试；Mac在途映射、回复、后端/SQL不动。

## Chunk 1：固定通道与签名消费

### Task 1：候选传输形状及签名器（独立实现）

Files: 新 `desktop/src/shared/candidateSubmission.ts`、`desktop/src/main/candidateProofSigner.ts`、`desktop/tests/candidateSubmission.test.ts`、`desktop/tests/candidateProofSigner.test.ts`；不改其它文件。

- [ ] 先写RED：`candidateSubmissionSchema` 接完整candidate-upload-v1模型，1～128 opaque键、五平台、执行字段、0～100 records、所有原文/null/parent/default严格保留；拒绝未知字段、无效整数、代理项、缺connection_id、超长正文。结构与 `pilot/candidate_contract.py` 一致，UTF-8正文不NFC/trim，不凭URL授能力；服务器保留来源/时钟/关系权威校验。
- [ ] 最小实现只规范化现模型的connection_version及parent可选字段为null；记录正文保持原字节。传输层检查含签名最终envelope不超过4MiB；不截断或自动分包。
- [ ] RED→GREEN实现 `signCandidateSubmission({key,prepared,expected:{serviceOrigin,userId,batch}}):{batch,signature}`。签名准备五字段精确；原文精确域yike-candidate-submission-v1、tenant/user/session_digest/request_id/batch_fingerprint。摘要按规范batch去request_id、Python ensure_ascii=False/sorted/compact JSON计算；严格canonical原文拒重复键/额外字段/错域/错用户/错请求/错摘要/错设备或版本，key服务/用户/设备作用域及实际Ed25519公钥一致。返回固定错误CANDIDATE_PROOF_SIGNING_FAILED，不回显正文/密钥。
- [ ] Unicode/空包/default/null/字段变更/请求变更/顺序变更、伪密钥及异常反例；签原服务器bytes，不签重建字符串；候选与执行签名域不能混用。`node node_modules/vitest/vitest.mjs run tests/candidateSubmission.test.ts tests/candidateProofSigner.test.ts`，记录真实RED/GREEN。

### Task 2：ServiceClient固定候选通道（root）

Files: 新 `desktop/src/main/candidateServicePolicy.ts`、`desktop/tests/candidateServiceClient.test.ts`；修改 `desktop/src/main/serviceClient.ts`。

- [ ] RED：`requestCandidate` 存在；candidate.prepare POST /api/ui/candidate-submission-signing-payload `{batch}`、candidate.apply POST /api/ui/candidate-batches `{batch,signature}`、candidate.receipt GET /api/ui/candidate-batches/{platform_run_id}/{request_id}。receipt平台运行UUID、request opaque键严格并URL编码；原public requestApi全部拒绝。
- [ ] 实现 `validatedCandidateOperation(input)`，共用现16项排队/超时/响应界限及session cookie。每个请求在入队前parse/snapshot；错误固定，不打印正文，4MiB检查包括envelope及签名。无重试/批次新ID/来源开关。
- [ ] 定向队列、已排队输入变更、非法字段/签名/路径、Unicode实际字节边界与原设备/执行兼容。运行 `node node_modules/vitest/vitest.mjs run tests/candidateServiceClient.test.ts tests/serviceClient.test.ts`。

### Task 3：真实HTTP/PG接收和一次整批审核（root）

Files: 新 `desktop/tests/integration/candidate-upload-live.test.ts`、`tests/test_desktop_candidate_upload_http_postgres.py`；简短交接/任务书引用。

- [ ] 先写实际产品接口尚缺的RED。复用real_strategy_env和现socket uvicorn fixture，合成有效设备/来源与已确认策略，不向Node传DB/admin凭据。Node产品ServiceClient+signer完成当前租约下prepare/apply，模拟成功响应丢失后仅GET原复合键，核对唯一回执/原文与数据库一次观察/预算消耗；换会话拒旧签名，历史查询不强制准备。
- [ ] 完整通道GREEN、`tsc --noEmit`、原受影响兼容；专属随机PG容器只本轮创建并finally移除。记录fixture范围，不声称真实平台/TLS/Windows发行。
- [ ] 非作者对冻结树先SPEC后架构/代码/质量一次审核；修复只复核差量。正常main集成、保留Mac来件。内部通道无新用户入口，不构包；原用户Goal不关闭。

# Windows 原始批次持久恢复 Implementation Plan

> For agentic workers: use subagent-driven-development and TDD. 用户已批准独立推进；按要求整批一次SPEC→代码/架构/质量审核、差量验证，不重复构包。

**Goal:** 为真实worker接入提供原文批次先持久化、再签名上传及重启原键恢复；不将工程片冒充真实平台完成。

**Architecture:** 沿既有 executionJournal/executionSession 的主进程私有模式，复用 candidateSubmission DTO、candidateProofSigner、ServiceClient 和 DeviceKeyProtection。原始batch按服务/用户/原platform_run_id+request_id隔离且不可变；不保存签名、会话摘要或私钥。默认恢复只GET，明确retry且原GET 404 request_not_found才重签同一batch；服务端仍是租约/取消/版本权威。正常历史GET不要求密钥或签名准备。

**Tech Stack:** Node24、TypeScript、Zod、现文件保护接口与FastAPI/专用PG；不新增依赖/迁移/UI/任意IPC。Base e520850；Mac保留来源映射、候选/执行后端和回复。

## Chunk 1：批次恢复贯通

### Task 1：不可变批次journal（helper）

Files: 新 `desktop/src/main/candidateJournal.ts`、`desktop/tests/candidateJournal.test.ts`。

- [ ] RED→GREEN：导出 CandidateJournalScope {serviceOrigin,userId}、CandidateBatchKey {platformRunId,requestId}，CandidateJournal.persist(scope,batch)->{batch,created}，read(scope,key)->batch|null，list(scope)->CandidateBatchKey[]；createCandidateJournal({directory,protection})。key原platformRunId规范UUID，requestId沿DTO opaque 1..128；文件名hash(scope)+hash(key)，不含原ID和原文、不发生Windows大小写碰撞。
- [ ] 每次入口先严格parse/deep snapshot冻结；批次JSON加86字符canonical签名的最终HTTP envelope≤4MiB；磁盘密文上限8MiB，明文有界。作用域合法HTTPS或显式loopback源；无保护失败关闭。不改原文字节/null/顺序。
- [ ] write wx+fsync，已有文件核对规范scope/key/batch且不覆盖；部分/损坏文件原样保留并报固定错误。按文件共享队列，真实磁盘跨factory重启、并发冲突、错scope、文件替换/符号链接、保护异常和输入迟到变更均覆盖。read使用有界读取；list流式至多1000键，超出明确报错，不截断；不一次加载1000个4MiB正文。list从固定前缀文件逐个核验并取键，异常不伪报空。不新增清理/删除接口。
- [ ] 定向运行 Node24 `node_modules/vitest/vitest.mjs run tests/candidateJournal.test.ts`；保留RED/GREEN及实际磁盘范围。

### Task 2：回执绑定和私有上传会话（root）

Files: 新 `desktop/src/shared/candidateReceipt.ts`、`desktop/src/main/candidateSession.ts` 与对应tests；调整现 `desktop/tests/integration/candidate-upload-live.test.ts` 消费新模块。

- [ ] RED→GREEN：parseCandidateReceipt(raw,batch)严格验证candidate-receipt-v1、四原ID、accepted_count等于records.length、index精确0..N−1及合法UUID三类ID/revision、真实ISO接收时间（兼容PG偏移与微秒）；observation_id唯一，candidate_id/version_id允许相同来源重复观察。不把accepted_count当新商机数。错误固定、不泄露原文。
- [ ] createCandidateSession({serviceOrigin,journal,vault,transport})提供submit(session,batch)、recover(session,key,retry=false)、list(session)。session沿DeviceIdentitySessionInput，所有异步前后及最终return重验isCurrent；同实例BUSY。submit先persist，created才prepare/sign/apply；已存在只GET。recover先读原batch，404仅明确retry可重签原batch，未找到本地返回NOT_FOUND；不分包/新ID/自动重试。密钥仅新提交时读取、主进程scope强绑定。RECORDED仅合法回执，其他HTTP/坏success为UNKNOWN；本地FAILED/KEY_MISSING不证明远端未执行。
- [ ] 原文snapshot、持久失败零网络、重启恢复零prepare、404/坏回执/错scope、会话变化每等待点、返回前microtask、BUSY与无key历史恢复定向测试；真实HTTP/PG原测试改为真实磁盘journal+session上传丢回执、重建factory后GET和一次保存计量，保留原旧签名拒绝用例。
- [ ] 根定向Node tests、tsc及单个实际HTTP/PG；非作者整批冻结树审核，正常main提交推送并只写一段交接。未改变用户入口不构包，worker/运行时/真实平台及Goal未完成。

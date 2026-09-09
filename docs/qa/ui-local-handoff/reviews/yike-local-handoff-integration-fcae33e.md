# 本机资料与任务返回增量：合并兼容性复核

## 结论与绑定

**限定集成复核 PASS：未发现本次合并引入的 P0/P1/P2 阻断，可进入主线程最终测试、构包和正常交付收口。** 本结论不提前代表主线程正在运行的全量或包验证通过。

- 精确合并：`fcae33e62f77d38208a0b3eaf97028d337000acc`。
- 本地父提交：`315d5906efcf8550309c78579895d7b45997c17b`，包含已审 P04 `d66d487a0f731d917ea65aeb2d6af51536e6cf10` 及 P09/平台/设备返回上下文增量。
- 远端父提交：`bbe2e2049ec9ed5105394d8bf4f1d7da84c42e4b`。
- 共同基线：`a08751d0b02d21c7d70b08f24eaaac2ca73bec8a`。
- 仓库：`/Users/bruce/Developer/work/yike-ai-product-design`。

本审核人不是本次 P04 产品实现、P09 返回修复、Win 固定原文客户端或执行签名字节实现的作者；只做下面的精确合并及接口边界核对，不替代各切片自己的代码审核。

## 两侧字节保留

使用 Git 对两个父提交相对共同基线的改动路径及 blob ID 逐一比对：

| 检查 | 实际结果 |
|---|---|
| 本地改变文件 | 17 个 |
| 远端改变文件 | 38 个 |
| 两侧共同改变文件 | 0 个 |
| 本地独有改动在合并中 blob 不一致 | 0 个 |
| 远端独有改动在合并中 blob 不一致 | 0 个 |
| P04 提交全部 9 文件与合并中对应文件 | 全部一致 |
| 合并 `pilot/` 树与远端父提交 | 一致 |

因此双方产品、测试和文档均保持原字节，没有人工解决源码冲突或偷偷覆盖某一侧。对合并差异执行 `git diff --check` 通过；`desktop/`、`pilot/` 和两个整合/任务书文档未发现 Git 冲突标记。未跟踪的四个 raw 候选辅助文件不属于该合并，也未计入本次功能接收。

## 固定原文详情与 P14/P15 的兼容性

1. `YikeService.opportunity(id, signal?)` 的第二参数可选。既有 P14/P15 单参数调用保持兼容；模型新增独立可选 `sourceEvidence`，不改既有 `sourceEvidenceVersion`、`sourceObservedAt` 或画像 ID。
2. 普通详情客户端现在要求响应的机会 ID 精确匹配请求，且明确包含 `source_evidence`。字段缺失、损坏、身份错配抛出固定 `INVALID_SERVICE_RESPONSE` 和“原文证据响应不完整，请重新读取。”，不会用旧列表补出虚构详情或擅自制造 `NOT_CAPTURED`。
3. 列表可省略完整证据，代表未加载；合法详情可明确返回 `UNAVAILABLE/NOT_CAPTURED`。服务端 `PilotStore.get_opportunity()` 经 `evidence_view()` 返回此字段，与新详情要求一致。该检查只通过阅读源码和来件证据核对，没有重跑 PostgreSQL。
4. `useRelatedReplies()` 先读取精确详情。详情失败时目标资源显示可重试错误，不产生可用 target；带目标的回复查询不派发，失败不被改成“未匹配回复”。`RelatedReplies` 继续保留原目标和错误。`FollowupEditor` 保存/纠正前也先读取精确详情；新证据错误在写入之前中止，原输入和跟进原请求机制不因本次合并而改变。
5. 浏览器 GET 在调用方提供 `signal` 时透传到 fetch；桌面 IPC 只在调用前和接收后检查取消，没有新增物理取消协议。P14/P15 现有单参数调用仍依赖自身有界等待、身份代次和结果采用保护；本报告不宣称它们已经通过新参数物理取消网络请求。
6. 只读检查了来件 `client.test.ts` 的详情缺证据/损坏/错 ID/显式未留存及取消用例，以及 P14 的详情失败不查询回复用例。已有测试分别证明客户端拒绝和页面拒绝路径；本次没有把它们说成新增端到端实跑。

来件对 `ContactEditor.tsx` 的改动仅将旧 excerpt 的标题改为“旧版摘录（非固定原文）”/样例标题；本机草稿保存、发送核验和防重未被替换。P04 和 P09 文件没有受到这批详情模块覆盖。

## 执行签名准备不等于桌面任务执行

已阅读 `docs/qa/V02_EXECUTION_SIGNING_PAYLOAD.md` 和 `docs/contracts/V02_EXECUTION_RUNTIME.md`，并核对新增 API/runtime 差异。新 `POST /api/ui/execution-signing-payload` 生成现有签名域的完整原文和绑定，不执行 START、不创建任务或占用预算。设备/凭据及会话校验保留；apply 仍单独进行执行授权。

`TaskOperationsService`、既有研究用量/搜贝确认、前端原请求 hash 与未决记录未被本次来件替换。合同明确执行协议和研究协议不同，真正接入仍需主进程签名与显式适配；未因“可以取得签名字节”开启桌面执行按钮，也没有把来源能力缺失变成成功。

## 证据归属与限制

- 本次新执行仅为只读 Git、差异、源码/合同和来件 QA 核对，没有重跑 PG、GUI、全量测试或构包。
- P04 独立 5 文件 / 40 passed、真实 RED 与类型检查保留在 `/tmp/yike-material-local-review-d66d487.md`；P04 9 文件字节与该候选一致，原限定结论可继承。40 项不能算作本次整合树新跑，也不与其他测试数相加。
- 来件 `docs/qa/V02-05E_SOURCE_EVIDENCE_CLIENT_WIN_REVIEW.md` 和 `docs/qa/V02_EXECUTION_SIGNING_PAYLOAD.md` 已阅读，保留作者、独立审核者、Windows 浏览器、Mac 接收、真实受限 PG 和合成来源各自范围。本审核人不接管这些运行证据的归属。
- 主线程正在进行的 tracked 桌面全量与隔离 archive 包仍以最终原始日志为准；本报告不引用尚未完成结果。锁屏下未完成的原生可见状态、真实资料/平台/收发、Windows 发行和完整 Goal 都不因此关闭。

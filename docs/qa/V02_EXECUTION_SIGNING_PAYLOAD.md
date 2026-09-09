# 执行签名字节接续验收

日期：2026-09-10。基线`c3f096c`，实施认领`eb507bf`；对应05F已提出的普通客户端执行原文缺口，不是新产品范围。计划见[实施步骤](../superpowers/plans/2026-09-10-execution-signing-payload.md)，字段见[执行合同](../contracts/V02_EXECUTION_RUNTIME.md#05f待签名原文接续)。

## 当前状态与原始失败

最小生产接线`7d8f657`连同集成测试/文档`956ecfe`及两行测试修正`9fc197c`，已通过独立最终审核；推送核验另记，不表示允许生产执行。用户完整Goal保持ACTIVE，Win负责自己的设备/HTTP/原文详情/来源消费，Mac本片不替Win签收。

- 干净`c3f096c`相关基线：`uv run --frozen pytest -q tests/test_execution_api.py tests/test_execution_contract.py --tb=short`，**32 passed /0.58s**。
- 根代理新增实际HTTP/受限PG回归，真实策略与设备准备成功后请求新入口：**1 failed /1.19s**，预期200得到404 Not Found。不是缺数据库、错误fixture或模型造成的失败。
- 真实成功路径只签服务端返回字符串，客户端helper不再根据tenant/claims自行构造执行签名；上传原有独立签名协议不由此改变。

## 实现者定向验证

实现者在新路由尚不存在时运行首个HTTP用例，实际 **1 failed /0.37s**（404 != 200）；最小接线后该用例与canonical测试 **7 passed /0.32s**。最终指定覆盖命令：

```sh
uv run --frozen pytest -q tests/test_execution_api.py tests/test_execution_contract.py tests/test_execution_signing_payload.py tests/test_pilot_runtime.py --tb=short
```

实际 **69 passed /1.27s /0 skipped**，无warning或failure。覆盖严格输入及四操作路由、身份/HTTPS/Origin/撤销、固定安全错误和canonical null/中文/顺序/会话反例。该集合属于HTTP传输和纯规范验证，不冒充真实PG；与下面root集合不相加。

## 证据边界

实际PostgreSQL/HTTPS语义测试客户端/Ed25519用于验证当前认证、准备与执行/历史恢复；受限角色通过已有专用测试fixture设置，不能替代生产独立登录/ACL验证。来源policy为fixture明确合成边界，模型若参与既有链也为本地HTTP受控返回；不证明实际平台采集、商用模型质量、Windows调用、外部收发、生产部署或客户UAT。

纯HTTP fixture只证明传输/schema/错误；不会写成实际设备授权。准备不调用来源、模型或预算，不改变task_execution能力；普通CLI无实际source policy时START仍须拒绝。测试集合分别记录，不相加。

## 根代理实际集成

在两处最小生产接线后，根代理执行：

```sh
uv run --frozen pytest -q tests/test_execution_signing_payload_http_postgres.py tests/test_confirmed_strategy_http_postgres.py tests/test_pilot_runtime_http_postgres.py --tb=short
```

专用测试PG连接仅在进程环境注入，未写入仓库。实际结果 **15 passed /16.53s /0 skipped**，包含新11项和既有4项；未重复无变化桌面/原生/全仓测试。证明范围：

- 当前有效HTTP会话调用新入口取得五字段响应，完整null和规范请求摘要吻合；同请求重复准备字节相同。真正START只签响应原UTF-8，客户端不再拼执行tenant/claims。
- 真实START→CLAIM→RENEW→策略撤销→CANCEL；租约已授予后的取消仍是CANCELLING/stop_confirmed=false，不误记实际外部进程已停止。
- 同租户不同owner、跨tenant、撤销设备、旧凭据和不存在设备拒绝；准备与错误不写执行事实。任务/run/platform/operation/key_request计数由受信测试连接按租户直接检查，且现有持钥请求非空，避免RLS空结果伪证。
- 实际占用设备行锁并观察PG锁等待，当前会话到期后释放锁，接口返回401。注销后的新准备拒绝；新会话对未执行原请求的旧签名400，重新准备可执行。已有成功UUID在另一有效会话仍可GET/重放历史，未再次建任务。
- 对四种合法操作（含未知task ID）的准备禁止调用策略/连接/任务/来源回调，证明准备不是预执行；能力仍关闭。正常CLI实际装配可准备，但缺来源policy时首次START501，无新增执行行。
- 既有策略→签名上传→模型分析→人工来源核验/纳入→固定原文/历史恢复链中的执行签名现从真实API获取。候选上传仍使用其独立既有签名协议；本片不宣称已经补齐Windows上传原文或worker。

以上是本次root实跑，不是独立审核者重跑。规格/代码/架构/质量审核及最终提交另记；来源fixture与本地provider的合成边界保持不变。

## 独立任务审核

新审核者对`eb507bf..7d8f657`完整变更做规格和质量审核：**Spec compliant / Approved，0 Critical / Important / Minor**，未重复套件。已确认最小路由、五字段、完整摘要、原签名域及只读设备校验；未修改apply或另造授权。

两项跨任务待核实已由root现有证据对应：会话/全局错误/no-store由69项传输测试与15项真实HTTP/PG的撤销、等锁过期断言覆盖；历史恢复、撤销策略后的CANCEL及默认START501由同一15项实际链覆盖。不是把未展开的旧代码当审核者已重审，也不以测试替代生产或Win消费验收。整个增量的最终独立代码/架构/质量审核仍待收口。

## 最终审核修正

独立终审对`eb507bf..956ecfe`提出一项Minor：摘要变体测试同时随机生成device_id，三个摘要不同不足以单独证明targets顺序或request_id的影响。root核对后以`9fc197c`固定两个变体的device_id与原始请求一致，仅两行测试修改。随后`uv run --frozen pytest -q tests/test_execution_signing_payload.py --tb=short`实际 **6 passed /0.18s /0 skipped**；未改产品源码，也未重跑不变的PG集合。

独立审核者随后仅复核两行delta，原Minor关闭。完整`eb507bf..9fc197c`最终**Spec / Code / Architecture / Quality PASS，Ready to merge YES，0项未关闭发现**。上文待审核为历史时点，不据此重跑已通过的相同代码。root可按授权正常同步、推送并核对远端SHA；任何新的源码或冲突合并另做影响范围验证。此后仅登记本次实际审核/交付的文档不改变已审代码快照。

## 并发主线保留与合并验证

首次普通推送`3fb4673`时，功能分支成功，main因同期UI来件`a08751d`而非快进拒绝；未强推。随后普通合并为`12c0c95`，唯一整合状态文本冲突逐段保留双方记录。实际`git diff --exit-code 3fb4673 HEAD -- pilot tests deploy migrations`与`git diff --exit-code a08751d HEAD -- desktop`均退出0，证明双方源码完整保留。

root在该合并树运行以下受影响UI文件，再执行类型检查：

```sh
npm run test -- tests/ui/followup-completion.test.tsx tests/ui/followup-reply-entry.test.tsx tests/ui/followup-reply-flow.test.tsx tests/ui/followup-routing.test.tsx tests/ui/followup-scope.test.tsx tests/ui/followups.test.tsx tests/ui/task-template-research.test.tsx tests/ui/workbench-queue-scope.test.tsx
npm run typecheck
```

实际 **8文件 /80 passed /10.14s /0 skipped**，类型检查退出0；源码/Markdown/JSON差异格式及凭据扫描通过。不是对方1253项桌面记录的重新执行，也未重复不变的PG、构包或原生验收。[来件原QA](ui-reply-entry/README.md)及独立报告保持各自身份与锁屏/真实回复服务未验边界；根代理仅接收其兼容性，不冒认作者或产品验收。合并独立复核和实际最终远端核验另记。

独立合并兼容性复核对精确`12c0c95`为**PASS，0项未关闭发现**，已确认双方产品字节保留，现followup/模板协议不消费或替代执行签名。该通过绑定此合并，不预先包含之后新增的远端变更。

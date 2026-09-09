# 执行签名字节接续验收

日期：2026-09-10。基线`c3f096c`，实施认领`eb507bf`；对应05F已提出的普通客户端执行原文缺口，不是新产品范围。计划见[实施步骤](../superpowers/plans/2026-09-10-execution-signing-payload.md)，字段见[执行合同](../contracts/V02_EXECUTION_RUNTIME.md#05f待签名原文接续)。

## 当前状态与原始失败

最小生产接线已提交为`7d8f657`，独立审核及整合待收口；不表示允许生产执行。用户完整Goal保持ACTIVE，Win负责自己的设备/HTTP/原文详情/来源消费，Mac本片不替Win签收。

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

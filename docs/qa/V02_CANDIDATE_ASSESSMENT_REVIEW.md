# V02-04C 判断与人工复核验收记录

2026-09-10；工程切片独立终审在`c2b46ed`通过，待Win实际接收与真实来源闭环；04C父卡及整个产品未完成。

范围：[04C实施计划](../superpowers/plans/2026-09-09-candidate-assessment-review-slice.md)及[接口合同](../contracts/V02_CANDIDATE_REVIEW.md)。产品仍以完整用户闭环为先，本片不新增高级后台或发送权限。

## 已有代码证据

| 部分 | 精确代码 | 验证与边界 |
|---|---|---|
| 版本化Skill模型与逐字依据 | `c372c3f0859f27d196dff5f61ec613cd8767b2c2` | 独立spec/quality PASS；180个定向测试，367个含既有search模型的组合回归；两组非相加。使用本机HTTP、DNS中止及离线wheel，不是付费模型质量证明。 |
| 认证HTTP边界 | `88fafa9e049117a265eb2fe164532e2e34dcee65` | 110个边界及相关API测试通过；认证、64KiB严格JSON、原请求查询和默认关闭能力。该组使用服务边界替身。 |
| 私有PG判断/来源核验/复核入库 | `2eba50ad7ac9e37d97760242adec056e3e125262` | 实现者37个真实受限PG测试通过；独立复核发现下述P2，不能按37个通过宣称独立验收完成。 |
| HTTP → 默认独立模型进程 → PG → 旧商机读取 | `2eba50a`加根代理端到端测试 | 根代理5个测试通过，9.00秒，0跳过。provider是本机真实HTTP测试服务；不注入内部http_client、不替换SQL或业务服务。 |
| PG列表一致性修正 | `fe2be00573b41a82fddbeea3b537d4f8f29a4307` | Task2独立复审spec/quality PASS，剩余发现0；实现者最终43个真实受限PG测试通过，26.90秒，0跳过；原独立反例1个通过，1.62秒。替代当前37项状态，不相加。 |
| 最终HTTP/PG相关集成 | `5b08386966a28733db03df0a4296f0ee79761659` | 根代理8个通过，10.92秒，0跳过（5个新增review＋3个既有raw HTTP）；会话76544退出0。命令见下文。 |

根代理最终定向命令：`.venv/bin/python -m pytest tests/test_candidate_review_http_postgres.py tests/test_candidate_ingestion_http_postgres.py -q --tb=short`，使用专用受限测试PG；凭据不保存到仓库。随后正常合并Win `4dc2142`为`6950cba1d44d51a13f43391f7669f6273a267237`，本片服务、模型、API及上述测试字节未变；不称合并后重跑全量。

模型与接口用例的数量不能累加成客户样本、有效线索或回复数量。测试账号、策略、原文和provider响应均为合成数据；服务操作使用新建的最小受限NOLOGIN角色，管理账号仅建库/授权/清理测试数据。

## 独立复核与修复

- Task1原先的分阶段网络超时允许慢速滴流；随后异步取消仍被原生DNS执行器拖住。最终采用固定、受控、单次模型子进程，时限到终止并回收；敏感输入仅有界stdin，最小环境，调用前核对规则摘要，父进程重验输出。两条Important在`c372c3f`独立复审关闭。OS终止/回收调度开销不是额外继续执行的时限。
- Task2原P2：列表逐候选的strategy resolver在READ COMMITTED下可能读取不同版本。独立真实PG反例计数为`2 → 1 → 0`，1 failed，1.71秒。`fe2be00`采用外层当前身份护栏＋内层同一REPEATABLE READ数据视图修复，原反例未经修改转为`2 → 2 → 0`，1 passed，1.62秒。六个新增回归覆盖策略混读、等锁期间撤销、令牌真实过期、读后撤销、resolver合法行锁及序列化冲突/锁释放；独立精确复审关闭此P2。

## 本片不等于这些已完成

- 不等于真实平台采集、真实模型效果、有效项目、外部发送、回复或客户付费。
- 人工HUMAN_REOPENED是用户声明；新商机仍UNVERIFIED，模型或人工入库都不授予发送权限。
- Win尚未实际接收来源核验步骤、扩展响应及原操作恢复，旧P07类型/hash不能直接当成新接口适配。
- 真实确认策略resolver、生产模型与资料处理授权、平台样本、生产配置/空库/浏览器主流程及客户UAT仍需逐项验证；默认能力不启用。
- provider token usage当前未持久化，不显示为0成本；只保存实际模型调用预约次数。
- 当前列表仍在SQL读取owner全部候选及成功请求后投影分页；尚无大数据量性能承诺。独立审核允许作为小规模端到端验证的已知优化项，不能宣称已实现数据库有界分页。
- 列表暂用两个局部数据库连接；resolver仅用传入cursor，无另开连接/重复认证锁/网络操作。此成本适用于有界小规模试用，不代表扩容验证。
- Win搜索组件及其独立证据已随`4dc2142`保留，110尚未注册共享运行入口，114归Win真实确认策略；本次合并不是Mac对Win组件的完整实际消费ACK。
- 原文证据的共享商机固定版本/观察/结构化引用投影与Win05G呈现仍需接续；当前私有分析绑定不等于PH-F06端到端完成。

## 整片终审与最终修正

独立非实现者`candidate_assessment_final_review`完整审阅`4dc2142..916d0d8`，最初发现两项P2并拒绝合入；以下修正后对精确`c2b46ed7d4158e4257644d126c58758a491bb47b`重新审核，规格/代码/架构/质量PASS，剩余Critical/Important/新Minor均0。

1. 原文OPEN但联系路径NONE仍能INCLUDE：独立真实PG反例1 failed/1.35s，公开回归1 failed/1.38s。修正只在消费核验时要求COMMENT/DM/PUBLIC_CONTACT；OPEN/NONE仍可如实记录，旧可联系核验不能覆盖最新NONE，新DM核验可恢复纳入。
2. 原请求回放等锁后未重新校验当前登录：三个操作反例3 failed/6.30s。修正后还暴露继承的invalid_session被误映射503、缓存别名等锁过期仍提交；分别以1 failed/1.22s、1 failed/2.34s固定。现在等锁后及回放前检查身份，缓存别名提交前同样检查，保留域错误401，非域的提交回执丢失仍按未知结果处理。原回执不变、不新增模型调用。

第一次不完整修正保留为3 passed/1 failed（6.59s）；对应相关集合54 passed/1 failed（43.97s），不是当前通过结果。最终源代码的6个定向反例**6 passed/9.02s**（会话94621），最终相关命令**56 passed/45.12s/0 skipped**（会话6494退出0）：`.venv/bin/python -m pytest tests/test_candidate_review_postgres.py tests/test_candidate_review_http_postgres.py tests/test_candidate_ingestion_http_postgres.py -q --tb=short`。其中48个core＋8个HTTP，不是56个新增测试，不与早期43/8相加。

随后正常合入Win真实策略主线`36fef5b`为`4d04cd1d55b3b92de5f20378e9bb777f298db41b`，仅整合状态文档冲突，双方原文均保留。本片源码/共享入口/113及相关测试与c2相同；Win新增8个代码/测试/SQL文件与36相同。Mac在该合并树定向运行Win新合同与HTTP：**233 passed/1.38s/0 skipped**（会话53304退出0）；不是Win PG重跑、114接线或实际消费ACK。110/114仍未注册默认入口，实际接线作为下一片继续。

此前02B、执行器、Windows及客户验收证据保持各自原版本，不用本片测试替代。合并后未重复未改的模型、桌面或完整后台套件。

## 05G原确认回执补齐（2026-09-10）

基线`7b640c9a6b58211ea025d120984bbc27112e2ef4`；CodexiMac代码候选`9d9e965`。响应Win的[最小接口请求](../handoffs/V1_WIN_FUNCTION_OWNERSHIP_20260909.md#05g接线及设备恢复的最小服务缺口2026-09-10c88b64b核查)，不扩展其独立设备恢复请求。

生产改动只有`pilot/candidate_review.py`一行：新决策回执投影已校验的`request.sourceVerificationId`。已存在的来源核验、载荷指纹、不可变保存、原请求恢复、事务及授权机制不改；无新表、迁移、capability或桌面改动。旧回执仍保持缺字段，不向当前核验求值。

TDD与故障记录：

- 写入新增断言后、修复前：7 failed / 3 deselected，9.67s，均为成功响应缺`sourceVerificationId`；这是本缺口的RED。
- 一行修复后第一次：3 passed / 4 failed / 3 deselected，9.55s。两个测试错误分别是读取错误响应时误用顶层`code`，以及尝试UPDATE不可变历史回执；不视为产品新缺陷。改为既有`detail.code`及仅在专用合成数据中INSERT旧形状记录，没有禁用触发器或放宽生产保护。
- 最终定向：7 passed / 3 deselected，10.67s。命令：`uv run --frozen pytest -q tests/test_candidate_review_http_postgres.py -k 'human_check_and_review or exclude_receipt or legacy_decision_receipt'`。
- API/固定原文纯边界：46 passed，0.84s。命令：`uv run --frozen pytest -q tests/test_candidate_review_api.py tests/test_opportunity_evidence.py`。

回归覆盖新INCLUDE原值、EXCLUDE省略/null/有ID三种形态、重复POST不重复入库、同requestId改ID冲突、服务重建后GET恢复、原文变化后的历史决策，以及新核验出现后旧缺字段回执的POST/GET/当前与历史列表仍原样。每个HTTP场景只发生一次本地模型调用；人工纳入不授权发送。

冻结代码`9d9e965`相关批次：`uv run --frozen pytest -q tests/test_candidate_review_http_postgres.py tests/test_candidate_review_postgres.py tests/test_opportunity_evidence_postgres.py tests/test_confirmed_strategy_review_postgres.py`，**101 passed，80.64s，0 skipped**（执行会话65186退出0）。含原文固定入库、实际确认策略消费和原复核保护；与前述7项重叠，不相加，不冒充全仓回归。`git diff --check`通过；独立最终审核待记录。

PG测试使用已有专用隔离库与NOLOGIN/NOSUPERUSER/NOBYPASSRLS应用角色；管理连接仅设置和清理合成fixture。ASGI、SQL、核验/决策、恢复为真实代码；普通review测试的来源、策略collaborator及本机HTTP模型响应是合成输入，confirmed-strategy专项实际使用持久策略服务。不是真实平台、付费模型质量、Windows客户端接收、外部发送、部署或客户UAT证据。

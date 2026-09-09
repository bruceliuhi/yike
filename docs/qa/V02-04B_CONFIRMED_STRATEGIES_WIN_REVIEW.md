# 04B 真实确认策略：Windows 限定验收

2026-09-10；认领基线 `4dc2142`，实现计划见[确认策略计划](../superpowers/plans/2026-09-10-win-confirmed-strategies.md)，消费及共享入口见[接入合同](../contracts/V02_CONFIRMED_RESEARCH_STRATEGIES.md)。本片提前交付真实策略，供Mac执行和04C判断消费；不是建议后台、05C客户端、实际来源或整个04B完成。

## 交付与独立审核

- 合同提交 `0678383`：严格公开配置/三种请求、完整六字段快照与摘要，保留R4非生效输入。独立 `evidence_ui_readonly` 先规格PASS（本人182项实跑），再代码/架构/质量PASS（另4个循环/深度/非JSON探针）；Critical/Important/Minor均无。
- HTTP提交 `808f44b`：五个认证入口、原请求读取、有限JSON解析和安全错误。独立 `strategy_contract_impl` 非本片作者，先规格PASS（本人47项实跑），再代码/架构/质量审核并复核差量；最终无未解决Critical/Important/Minor。没有自动注册共享app。
- 策略store/114/grant/48项PG测试提交 `eadcd2c35aa6fde660b70fb79e98150dd178fc46`：独立 `strategy_contract_impl` 先规格PASS，再代码/架构/质量PASS，Critical/Important/Minor均无；追踪实际Mac执行和候选上传调用，测试执行证据引用根代理，不冒充审核者实跑。本片实现者为 `store_lock_audit`，没有自签最终审核。

## 实际验证与失败历史

本次仅运行新合同、HTTP及相关执行/候选消费，不重跑无关桌面全仓或打包；以下集合有重叠，不能相加为产品成绩。

| 执行者与集合 | 真实结果 | 范围 |
|---|---|---|
| 合同实现者，合同及既有候选/执行纯合同 | 348 passed / 0 skipped | 六字段协议兼容；不是PG或真实平台 |
| 根代理，最终合同＋HTTP | 233 passed / 0 skipped，1.57s | 182合同＋51HTTP/解析边界 |
| store实现者，最终合同＋受限PG | 230 passed / 0 skipped，15.02s | 182合同＋48真实PG |
| 根代理，最终合同＋受限PG复核 | 230 passed / 0 skipped，15.04s | 同一48项真实PG独立进程重跑，不另加到上行 |

Windows PowerShell 7，专用Python venv，PostgreSQL 16随机一次性容器，tmpfs数据、随机秘密、仅127.0.0.1映射；管理员迁移和受限应用角色分离。两次最终PG脚本均退出0、`EXACT_TEMP_POSTGRES_REMOVAL_CONFIRMED`。没有访问客户库、公开模型/平台或发送消息；没有保留本次测试数据库。

测试入口：`tests/test_research_strategy_contract.py`、`tests/test_research_strategy_api.py`、`tests/test_research_strategies_postgres.py`。PG模块需要**新的一次性数据库**的 `YIKE_RESEARCH_STRATEGY_TEST_DATABASE_URL` 和 `YIKE_RESEARCH_STRATEGY_TEST_APP_DATABASE_URL`；夹具限定loopback、数据库名`win_research_strategy`和角色`strategy_app`，不能指向客户库。未设置环境时PG明确skip，skip不计验收通过；本次实际运行0 skip。

保留的失败与修正：

- 合同最初缺模块RED；固定错误码默认状态初版不正确，额外9项先4 failed/5 passed，再修复到182项合同通过。
- HTTP最初缺模块RED，首次完整45 passed/2 failed暴露上述错误映射，合同修复后通过。质量审核指出旧重复JSON键反例本身缺必填字段，不能证明拒绝重复键：新增两个**其余字段完全合法**的顶层/嵌套反例，暂移除检测时2 failed（实际错误地200），恢复原实现后2 passed。未将测试漏洞误称生产实现漏检。
- TestClient会聚合迭代请求体，原用例更名准确描述总长度/假Content-Length；另固定真实Starlette `Request.receive` 三条ASGI消息，131072字节接受、131073拒绝且不再读取后续消息。独立复核2 passed；生产代码未因该测试补充改变。
- store最初32项缺模块RED，再32 GREEN。自审两个有效反例RED：相同revision中Python的`1 == 1.0`不能替代完整JSON摘要比较；resolver错画像不能跟随另一个画像加锁。修复为规范JSON比较及错绑定早拒绝，最终48项PG通过。
- 第一次使用旧Windows PowerShell 5启动PG脚本因中文路径编码失败，发生在pytest开始前；精确临时容器已清理。后续使用PowerShell 7，未将这次基础环境错误写成用例通过。

## 消费证据及适用限制

48项实际PG覆盖prepare→confirm→同cursor resolve、重建服务读取原回执、撤销/更高revision/画像状态与正文变化失效、不同会话并发、确认时间不被重置、锁等待后过期、调用方回滚、失败后三表原子回滚、两租户及同租户不同owner、FORCE RLS/复合FK/终态、MEMBER和列权限。

其中一次真实调用Mac `ExecutionRuntime`、`DeviceCredentialStore`、`CandidateIngestionStore`：实际Ed25519签名START→CLAIM→候选入库；撤销真实策略后旧租约新提交被拒绝、records_used仍为1、CANCEL仍可用。这里的能力policy和原始候选是明确标记的合成输入，证明的是Win真实策略与Mac执行/入库的消费兼容，不证明真实采集或整个Mac执行/候选卡已被Win接收。

三个HTTP→受限PG用例实际使用原会话认证与Origin中间件，验证prepare/confirm/查询/revoke、坏hash不改状态、跨owner和tenant不可见、重建store恢复以及logout后401；没有用TransportStore替代这些持久层结论。独立HTTP的TransportStore仅覆盖传输边界。

## 审核绑定的文件摘要

SHA256为审核时工作树实际文件字节（Windows检出可能与Git换行表示不同）；提交归属见上文，未修改冻结111/112或共享db/store/ui_api/web。

| 文件 | SHA256 |
|---|---|
| pilot/research_strategy_contract.py | `f950a70d2dd5aa64da72ad90d853bccf94dcdace9b72696667acd7ee9cae8b2a` |
| tests/test_research_strategy_contract.py | `51b8e9a3d4bb34c332535ceaacfb976424524b60052abeb22d3e4a18896d28d6` |
| pilot/research_strategy_api.py | `34012a6f1047af38489ca6dd7594315179c2692c42bfaec12689738da728809b` |
| tests/test_research_strategy_api.py | `3596152d0648ff1aea3ab7f0be27e76c2f35ead0e5a62fe9dc3a38fcdd6a10a1` |
| pilot/research_strategies.py | `9a635488f67c2020dd86341afedd1132154da1eccb5724b79d8732e7b5fa298e` |
| migrations/114_v02_research_strategies.sql | `2f971d11f252ea525c0e29920c73f448007650a546a687d7cf17c13d9ac23ae3` |
| deploy/grant_research_strategies.sql | `f048672989bc48339382ea980ab72c606ac2e915d63fa6d8f7e37580b0a7c8d1` |
| tests/test_research_strategies_postgres.py | `be52bc0176ddb0ff79d66228a4e0e1ab2f4166f8e235bc7a06d189d0da504ef3` |

## 仍需继续

Mac串行注册114/router、真实消费ACK；Win建议后台/外发授权及05C的服务快照预览和原请求恢复；完整研究上限、搜贝计量、监控调度、类似/覆盖证据来源校验；实际来源、原文判断与呈现、确认联系、回复跟进、Windows发行和客户试用。当前能力默认仍不启用，不以测试替代客户端体验或市场效果，不移走首发原文证据、多找类似、短句建联；整体Goal继续。

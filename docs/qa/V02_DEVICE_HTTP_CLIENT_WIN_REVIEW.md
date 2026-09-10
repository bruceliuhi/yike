# 05D/05F 设备 HTTP 客户端 Win 接收

## 范围与基线

2026-09-10，基线`4f36cc2`，正常快进保留Mac本次PostgreSQL验收记录。按[设备HTTP计划](../superpowers/plans/2026-09-10-win-device-http-client.md)Chunk1接严格登记/身份DTO和主进程六固定操作；后续原请求持久恢复、产品装配、真实HTTP/PG、实际平台与Windows生命周期不由本片代签。

Win仅修改desktop独占模块和本文/现有任务书/交接；Mac设备、执行、回复后端不改。公开renderer API不新增设备操作，没有通用签名IPC、自动重试或ROTATE入口。登记成功与持钥证明历史回执都不代表当前可执行身份。

## 实施前检查

- Chunk1计划由非作者审核Approved，无阻断项；后续Chunk2仍待实现。
- Node24运行原`deviceProof/deviceProofSigner/deviceKeyVault/serviceClient/servicePolicy`五文件：95 passed / 0 skipped，451ms。这是原模块基线，不是新增功能验证。

## 当前状态

Chunk1限定工程片通过，代码`eb43216`；05D/05F父卡及完整Goal仍IN_PROGRESS。原请求持久恢复、当前会话BIND/PROVE、产品装配和实际设备HTTP/Windows证据仍待Chunk2，不提前标记整卡完成。

## Task1 登记与身份协议

作者先运行可导入stub：112项中99项断言失败、13项通过；实现后DTO112项及原proof37项共同通过，类型检查通过。根代理另跑DTO、proof、signer、vault、serviceClient、servicePolicy、preload、windowPolicy八文件：212 passed / 0 skipped，455ms。集合重叠，不累计。

非作者SPEC审核PASS，独立运行DTO112项通过。覆盖Python strip/Unicode码点、4096序列化字节（规范化前）、严格五字段登记回执和四字段当前身份、原请求/标签/设备匹配、固定错误。不把SUCCEEDED或REVOKED历史记录当执行权限。

本层接收已解析对象，不能还原被JSON解析器吞掉的重复键；原始HTTP JSON重复键/坏UTF-8仍由现有服务端入口拒绝。当前DTO及定向测试并非真实设备登记HTTP或平台接通证据。

Task1独立代码/架构/质量审核PASS，无可操作发现；审核者另跑DTO+proof两文件149项通过（191ms）。

## Task2 六项私有固定传输

新`requestDevice`只在main对象内供后续协调器调用，公开`request`仍拒绝全部设备操作。新policy只接受登记/原登记查询/当前身份/挑战/完成/原密钥回执六操作，先校验与序列化，再与公开登录/退出共用一个队列及16项上限。原HTTP执行器未改，路径字段不混入POST正文，不自动重试、不开放ROTATE。

作者可导入stub先跑130项，其中20失败/110通过；首轮超时测试等待未进入的fetch超时，增加fetch-start断言后重跑20项有效断言失败，然后GREEN。最终作者六文件304项及类型检查通过。非作者SPEC审核PASS，独立130项新传输及6项原传输通过；不与作者/根代理集合累计。

合入`8bff266`前的根代理定向命令：

```text
Node24 vitest run tests/deviceRegistration.test.ts tests/deviceProof.test.ts tests/deviceProofSigner.test.ts tests/deviceKeyVault.test.ts tests/deviceServiceClient.test.ts tests/serviceClient.test.ts tests/servicePolicy.test.ts tests/preload.test.ts tests/windowPolicy.test.ts
```

该轮结果：9文件342 passed / 0 skipped，504ms；`tsc --noEmit` exit0。该轮快进前另确认`preload/shared contracts/public servicePolicy/pilot/deploy`相对`4f36cc2`没有差异；不描述后续合入Mac授权脚本后的状态。

为复核共享队列未破坏已有候选闭环，根代理在一次性PostgreSQL运行现`tests/test_desktop_candidate_review_http_postgres.py`：实际Node客户端→socket HTTP→受限PG **3 passed / 0 skipped，9.61s**，精确测试容器移除已确认。它验证候选读取/判断/原请求恢复及隔离回归，不是新设备六接口的实际HTTP接收；新设备完整BIND/PROVE、重启恢复与产品装配仍属于Chunk2。

## 最终独立审核与整合

非作者对冻结五文件完成代码/架构/质量终审：PASS，无P1/P2或其他可操作问题；独立运行计划指定五文件289项通过（295ms），类型检查exit0。五文件摘要与提交`eb43216`对应产品字节一致，未修改公开桥、页面或Mac后端。

提交前正常快进Mac `8bff266`，保留其连接/会话授权脚本及验收文档；Win五文件字节未受影响。整合后根代理重新运行同九文件，342 passed / 0 skipped（494ms）。Mac新增SQL单独复核，不把其主干存在视为Win已验收。

代码提交`eb43216`后，同一个候选实际Node→HTTP→受限PG命令复验3 passed / 0 skipped（9.02s），专用临时容器移除已确认；与先前3项重叠不相加。这不单独验证新增授权差异，也不关闭下面P2。

## 入站Mac授权差异：P2待作者收口

独立只读审核`4f36cc2..8bff266`：`deploy/grant_connection_operations.sql`增加任务表SELECT/INSERT/UPDATE，有实际租约路径使用，未发现本差异阻断项。`deploy/grant_session_revocations.sql:29`新增UPDATE/DELETE仅为使RLS测试返回零行而非ACL错误；`pilot/sessions.py`正常业务只需SELECT/INSERT。建议Mac保持正式SELECT/INSERT，测试接受ACL拒绝，或由专属测试fixture临时授予权限验证RLS。

该项记P2未关闭，不批准其正式授权扩展；105仍FORCE RLS且仅SELECT/INSERT policy，未发现当前撤销复活/跨租户漏洞，不误报实际泄漏。Win不抢改Mac后端，通过任务书和交接请求其原作者串行修正；这一发现与Win五文件Chunk1审核PASS分开记录。

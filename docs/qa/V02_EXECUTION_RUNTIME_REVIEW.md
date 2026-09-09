# 01C / 03A 执行服务切片验收

日期：2026-09-09。计划基线 `ecd20e1`，正常保留 Win 主线后代码基线 `639b17d`。核心实现 `990ebca8bc27452f5ef0db1409de6da08ae1baab`；HTTP 与交接候选 `25d393bcb9dcb128e832f3c8a34f2a29c7020b19`。完整01C/03A、真实采集和客户闭环尚未完成。

## 本次完成的边界

后端可持久创建单次任务与逐平台运行，设备以新请求签名领取/续租/取消，读取原请求回执和当前任务状态。取消立即阻止旧结果提交，但执行过的任务保留“停止待确认”。HTTP 重试和服务实例重建不丢原请求记录。02B可以在自己的候选入库事务中调用提交护栏及最终核验。

这不是采集器：没有候选上传/存储、实际平台搜索、worker停止确认、持续调度或生产确认策略。没有生产resolver/capability时501且不建任务；`task_execution`仍关闭。协议及Win接入要求见[执行契约](../contracts/V02_EXECUTION_RUNTIME.md)。迁移111归Mac，108/110继续预留Win，不改已发布迁移。

## 实际验证记录

所有 PostgreSQL 用例在专用本地测试库串行执行，使用真实Ed25519签名和受限角色；策略及来源可用性注入为明确合成夹具，不代表真实模型/平台。只记录环境变量名 `YIKE_IDENTITY_TEST_DATABASE_URL`、`YIKE_IDENTITY_TEST_APP_DATABASE_URL`，不入库连接秘密。

| 执行者 / 代码范围 | 命令与实际结果 | 证明范围 |
|---|---|---|
| execution_runtime_implementation / 核心990ebca | `uv run --frozen pytest -q tests/test_execution_contract.py tests/test_execution_runtime_postgres.py`：60 passed，17.55s，0 skipped | 签名/身份/并发/租约/取消/预算/最终提交护栏，真实空库迁移两次、RLS和授权；不含平台调用 |
| CodexiMac / HTTP及受影响后端，随后提交25d393b | 下列13文件：415 passed，33.00s，0 skipped | 含真实HTTP→受限PG两测、服务重建后查询、取消后旧结果拒绝、旧105升级及既有会话/设备/连接/候选契约 |
| CodexiMac / Win模型e26c7a3限定接收 | `uv run --frozen pytest -q tests/test_search_suggestion_model.py`：187 passed，0.22s | 已读模型源码及Win审核，传输替身，不是实际provider、策略持久化或建议质量实测 |

```text
tests/test_execution_api.py tests/test_execution_http_postgres.py
tests/test_ui_api.py tests/test_pilot_web.py tests/test_phone_api.py
tests/test_session_auth.py tests/test_session_revocation_postgres.py
tests/test_device_keys.py tests/test_device_credentials_postgres.py
tests/test_connection_versions.py tests/test_connection_versions_postgres.py
tests/test_candidate_contract.py tests/test_source_capabilities.py
```

415集合先于核心最终空库用例及类型标注收口运行；HTTP/guard生产逻辑当时已是提交后的字节。之后核心最终60单独验证，不将集合相加，也不声称重新全仓/桌面测试。HTTP层合成传输14测与真实PG2测是上述集合子集。

## RED与修正（不覆盖历史失败）

- 新模块最初缺失；HTTP默认路由最初404而非501，新增注入参数及固定路由后进入边界测试。
- 首次核心实现29通过/6失败：共享触发器引用非当前表字段，改为按表分支；既有测试应用角色历史宽UPDATE不符合最小权限前提，新增唯一NOLOGIN/NOBYPASSRLS角色及显式SET ROLE检验，不修改或冒充清理既有角色。
- HTTP strict模型不能接收JSON数组（8失败/65通过），由显式数组冻结为tuple修正；不是放松未知字段和严格整数校验。
- 新反例依次发现并修复：None上传签名绕过、确认上限超出硬边界、回执INSERT等待越过任务期限、嵌套DTO复制后被序列化强制转换、不可用状态409而非501。
- 首轮真实HTTP/旧升级组合1通过/2失败：501问题如上；旧105夹具错误运行了后续111，改为明确105迁移前缀，仍验证缺旧owner列、完整升级两次及最小授权。窄复测1通过0.89s，随后进入415集合。
- 未发布111开发中，仅为重放当前DDL删除专用测试库中精确的本迁移checksum行；没有截断共享表。最终另建唯一空数据库迁移两次独立验明，清理仅限本轮具名测试库/角色/租户。

## 独立审核

`execution_runtime_task_review` 对精确990ebca七文件及关联契约只读审核：**规格PASS、代码质量PASS，无已确认阻断缺陷**。没有重跑相同PG集合，也没有把作者测试计成审核者实跑。

`execution_slice_final_review` 对精确639b17d..25d393b整片进行独立只读审核：**规格、代码、架构、质量限定PASS，无需修复的P1/P2**。另执行diff检查通过，不重复运行已冻结的60/415集合。结论不覆盖未实现生产依赖。

两项非阻断后续已保留：02B相关测试补双平台、不同会话共享预算的并发反例；部署核验实际角色有效权限及继承，不能以临时最小角色代替真实角色验收。现有共享任务锁/aggregate trigger的静态实现未发现错误。

## 下一步及不得推导的结论

1. Mac02B：原批次回执优先、同事务签名护栏/来源版本/观察/用量/回执/最终核验；空批次不冒充完整运行结束。
2. Win04B：持久化真正已确认策略/资源上限及同事务resolver；05F接新请求签名，不把旧TaskDraft或R4搜贝估算直接映射成执行授权。
3. 实际来源及worker接通后验两条独立来源和至少一条真实收发路径，再进行明确范围的邀请试用。高级管理/统计/自动更新后排，数据隔离、防重、确认、预算与基本恢复不后排。

没有真实策略、实平台采集、消息、客户UAT、发行或付费效果的新证据。既有CP-06备份认证P1及生产/Windows门禁仍保留，完整Goal保持ACTIVE。

## 保留R4前端的正常整合

随后正常合并主线9291963，形成 `e5b4bcccdb69478ebb43d0c45e2a430bd60b2172`，父提交25d393b与9291963；没有代码冲突。`pilot/migrations/deploy/tests`与25d393b逐字节一致，`desktop`与9291963逐字节一致。根代理读取已有R4独立审核和[14aa73e整合证据](ui-r4/README.md#最新主线合入与再验证)：845通过/21条件跳过、类型/构建/ASAR冒烟等属于原任务运行，不当作本轮重跑或客户实测，不重复相同桌面套件。

新R4的`researchContractVersion=1`、搜贝估算/预留与空间绑定仍是前端合同，不是本片`execution-runtime-v1`执行授权。后续05F须桥接真实确认策略、资源上限、可信身份、签名及原请求；本片没有计费预留/扣减能力，不能把record上限当搜贝余额。合并后生产能力继续关闭。

`execution_slice_final_review`对精确e5b4bcc追加限定合并复核PASS：独立确认双方代码零差异、实际父提交、R4前端协议与执行协议无暗接、生产客户端仍不可执行。仅建议更新契约，承认已有research/usage且不将其当执行授权；本文及合同已按该建议更新。没有重复R4全套，也没有把本次源码合并当新安装包或平台验收。

# V02-02B 候选入库工程切片验收

2026-09-09，CodexiMac；计划/认领783c638，核心 **cf86c56672019d4eb153cd483791a4f67f6fe76a**，HTTP/读取合同 **9c49a507ede77e608be3765de6913698bf007697**，最终修正/独立验收 **07431cac919ffe610bb144bdca9e648ec9825f30**。见[实施计划](../superpowers/plans/2026-09-09-candidate-ingestion-slice.md)、[接口交接](../contracts/V02_RAW_CANDIDATE_INBOX.md)和[唯一任务书](../V02_IMPLEMENTATION_TASKBOOK.md)。

## 本轮可验证的动作

有效产品会话＋持钥设备在已确认策略和有效租约下提交合成原文 → 同事务核验/入库/研究记录预算 → 返回不可变回执 → 按任务读原始候选列表/详情 → 用原复合键恢复原结果。新批次在取消、撤销、过期或错绑定后拒绝，不留下半条候选或已消耗的预算。

五张新表在原PostgreSQL内，不另建数据库。内容版本和每次观察分开；同内容重复不冒充新增线索，较晚上传的旧观察不覆盖新内容，同秒矛盾保留歧义；原设备/lease/代次等执行上下文在接管后仍可追查。所有原始候选为UNVERIFIED，尚未进入Skill判断或已批准机会。

## 测试证据（集合不相加）

专用本地 PostgreSQL，测试执行使用每次创建的 NOLOGIN/NOSUPERUSER/NOBYPASSRLS 限权角色，经 SET ROLE 运行；管理员只用于迁移、合成数据准备/回收和限定故障注入。环境变量使用 `YIKE_IDENTITY_TEST_DATABASE_URL` 和 `YIKE_IDENTITY_TEST_APP_DATABASE_URL`，此处不保存连接值。来源、策略与设备用测试数据，真实Ed25519签名和数据库事务不是替身。

| 锁定内容 | 命令/结果 | 证明与不证明 |
|---|---|---|
| 核心最终cf86c56 | `uv run --frozen pytest -q tests/test_candidate_ingestion_postgres.py`：**21 passed，18.90s，0 skipped** | 真PG重放/冲突/双会话并发、共享预算、RLS、原文/时间/父关系、回滚、历史身份、旧任务筛选及100条观察截断 |
| 同字节核心关联回归，之后仅收紧测试 | `uv run --frozen pytest -q tests/test_candidate_ingestion_postgres.py tests/test_execution_runtime_postgres.py tests/test_candidate_contract.py`：**211 passed，41.00s，0 skipped** | 现有执行/DTO消费，空库全迁移两遍；不冒充实际部署权限或平台运行 |
| HTTP/core9c49a50 | 下方受影响回归：**316 passed，11.27s，0 skipped** | 三条真实HTTP→签名→受限PG新路径及既有认证/撤销/升级；其余隔离HTTP边界双只检查传输，不算采集证据 |
| 静态检查 | `git diff --check`、相关Python `compileall -q`：exit0 | 没有重跑未变的桌面构包和完整前端套件 |

最终316命令：

```sh
uv run --frozen pytest -q \
  tests/test_candidate_ingestion_http_postgres.py \
  tests/test_candidate_ingestion_api.py \
  tests/test_execution_api.py tests/test_execution_http_postgres.py \
  tests/test_ui_api.py tests/test_candidate_contract.py tests/test_source_capabilities.py \
  tests/test_identity_contract.py tests/test_session_auth.py \
  tests/test_session_revocation_postgres.py tests/test_session_upgrade_postgres.py
```

## RED 与修正保留

1. 核心先写失败用例：缺入库服务，1 failed；首轮实现后8 passed。数据库错策略绑定独立反例先DID NOT RAISE，再由延迟约束修正为通过；最终反例改用合法record index，避免用另一项限制误判绑定保护。
2. 原执行上下文反例先KeyError，再持久化非秘密execution_context；任务重新接管后仍保持旧上下文。
3. HTTP先缺build_app接入参数，1 failed；实现后边界相关81 passed，扩展纯/认证/来源246 passed。这两轮不是最终整合数，不与316累加。
4. 首轮真实HTTP为2 passed/1 failed：新测试错误假设无效签名应401/403，原已接收 `device_keys.verify_signature` 实际规定400 `invalid_proof`。核对原实现及既有测试后，将断言改为精确400及错误码；没有改协议或放宽生产校验。
5. 一次命令误写不存在的 `test_session_revocation.py`，exit4且0 tests；随后rg定位正式文件并执行上述316集合。不是测试通过。

112迁移只在未发布、专用合成测试数据库内演进；实现者曾确认新表为空后重建该组新表并重置该迁移测试校验记录。最终代码包含新空数据库完整迁移两遍测试；这不授权改写已部署迁移。111、108/110所有权与其他历史迁移保持不变。

## 独立审核

- `candidate_core_review` 对 **cf86c56**：SPEC / CODE / ARCH / QUALITY限定通过，无Critical/Important；只读核验了运行服务/session委托和真实限权fixture，没有重复跑套件。
- `candidate_slice_final_review` 对 **9c49a50**：其余范围未发现阻断，提出一项P2，结论CHANGES_REQUIRED。原列表/详情分别读取count与内容，另一有效会话在100→101观察边界入库时可能返回100条、total=100、truncated=false，违反明确截断提示合同。根代理核对默认READ COMMITTED和会话级锁后接受此问题，限定修正为同一SQL快照；该候选没有在修正前推送main，后续精确复审见下文。

核心审核初判上述并发计数为P3；整片审核给出100→101隐藏截断的具体反例，故升级为本轮须修的P2，不以初审PASS绕过。没有改为REPEATABLE READ事务或削弱会话撤销检查。尚无逐SQL语句故障注入或并发同键不同内容的单独用例；已覆盖整事务最终fence回滚、同键顺序冲突和双有效会话并发同体重放，不能把这些称作穷尽故障测试。

### P2修正证据

修正 **07431cac919ffe610bb144bdca9e648ec9825f30** 仅涉及入库服务的两个读取方法与专项测试。列表同一SQL内统计匹配ID/时间并仅取该页正文；详情同一SQL内读取当前版本、窄计数与最多100条历史。起止会话检查仍使用实时READ COMMITTED检查，不让撤销检查停留在旧事务快照。

双有效会话真实签名入库的测试先复现2 failed/21 deselected（9.62s）：详情旧投影与新历史不一致，列表total1/items2；修正后同命令 `uv run --frozen pytest -q tests/test_candidate_ingestion_postgres.py -k read_snapshot` 为2 passed/21 deselected（9.54s）。包含100→101数量/截断提示以及越界空页仍保留正确total的断言；测试插入点只在测试数据库游标包装器内，无生产hook。

修正后执行 `uv run --frozen pytest -q tests/test_candidate_ingestion_postgres.py tests/test_candidate_ingestion_http_postgres.py tests/test_candidate_ingestion_api.py`：**57 passed，31.75s，0 skipped**；compileall和diff检查通过。该结果绑定07431ca，不把先前316或211说成在此SHA重新跑过，也不将集合相加。

根代理另在同一冻结代码复现两项 `read_snapshot` 反例与 `tests/test_candidate_ingestion_http_postgres.py` 全部三项：**5 passed，11.90s，0 skipped**。非实现者 `candidate_slice_final_review` 完整复审到07431ca，结论 **CANDIDATE_SLICE_SPEC_CODE_ARCH_QUALITY_PASS**，P2关闭、无剩余Critical/Important/Minor；批准该工程切片集成，不等于平台或客户验收。所有私有报告保留在本工作树gitdir的sdd目录，不在公开报告存凭据或私密数据。

## 下一接入与发布边界

Win消费02C映射和本片上传/原回执/原始读接口；Mac继续04C判断/复核与收发主链。04B真实确认策略resolver、05F显式新签名适配、02D/09B真实来源/worker、05G原始到展示对象适配仍需接通。测试注入的策略和来源不会打开生产capability。

没有真实平台采集、真实模型判断、短信收码、客户UAT、Windows实机或生产部署证据，完整Goal保持进行中。M3/CP-06及实际部署角色继承权限检查、既有备份认证P1不因分期而取消。此次新增API也不授权自动外联。

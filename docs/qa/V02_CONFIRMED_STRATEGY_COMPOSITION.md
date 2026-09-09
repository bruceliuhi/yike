# 真实确认策略与候选链路接入验收

日期：2026-09-10。基线：`aba7f4f6d24daa5800c3a54348d6521c2b2b6e66`；认领计划：`ab6407d`。

本记录只验收[两项组合接入](../superpowers/plans/2026-09-10-confirmed-strategy-composition.md)。使用真实受限 PostgreSQL、真实会话及设备签名协议、真实策略持久层；来源授权 policy、候选内容及本地 provider 响应均是明确测试边界。没有实际平台采集、买方需求或模型质量、发送/回复、客户试用、Windows 或部署证据。

## 初始故障

独立架构核查确认：候选列表外层认证事务持有会话 advisory fence；内层 repeatable-read 事务调用实际 `ResearchStrategyStore.resolve` 再取同一 fence，导致应用级自等待。旧合成 resolver 不取该锁，因此旧单模块测试没有发现组合故障。

根代理在隔离数据库以实际 prepare/confirm、签名 START/CLAIM/候选上传、分析、来源核验及 INCLUDE 复现：纳入成功后查询 `status=IMPORTED`，应有一条却返回零条。测试使用 300ms lock timeout、2s statement timeout 将等待限制在有限时间内；列表把策略服务不可用误判为策略过期。初次探针的画像版本固定为1导致 `profile_conflict`，校正为新建画像的实际版本后才得到目标故障；该夹具问题不作为产品缺陷。

命令为 `.venv/bin/python -m pytest -q -c pyproject.toml <private-sdd>/test_real_strategy_review_probe.py --tb=short`，显式注入专用测试库连接；结果 **1 failed / 1.99s**，失败断言为 `page['total'] == 1`（实际0）。私有诊断文件和测试连接不进入仓库。

## 验收范围

| 用户动作 / 边界 | 本片必须验证 | 不代表什么 |
|---|---|---|
| 确认研究任务 | 共享认证入口保存并确认真实策略版本 | 已获平台权限、已启动采集 |
| 带回候选 | 真实策略约束签名任务和原始记录上传 | 来源内容来自真实平台 |
| 分析并人工纳入 | 固定原始版本、模型边界、来源核验和人工决策保持一致 | 模型建议就是人工批准、允许自动发信 |
| 正常/历史查看 | 同一只读快照显示正确状态；历史回执不是新授权 | 当前策略撤销后仍可继续执行 |
| 撤销、过期或服务异常 | 当前写入拒绝；原回执可核对；异常不能伪装成“零条机会” | 无限重试、绕过会话或来源门禁 |

既有迁移111–114不改写，默认不可用能力不开启。

## Task 1：列表读取与执行授权分离

提交 **0c14b339f3255f73bec2409161d5e65b1a723716**。只改两个服务、三个测试文件及两份接入合同。新增显式 `read_snapshot` / `strategy_snapshot_reader`；列表内层为只读 repeatable-read，外层保留读取前后的实时身份检查。执行与人工写入仍走原 `resolve`，普通快照不是执行授权。无 reader 不回退；策略冲突、身份失效与服务不可用分别保持409、401、503含义。

- 新测试首个 RED：缺失 `read_snapshot`，**1 failed / 1.12s**。与上方原始组合故障分开记录。
- 初次新模块 GREEN：**33 passed / 23.03s**；随后增加完整画像重新哈希和撤销两项反例，并复用纯画像验证 helper。
- 最终覆盖命令：`.venv/bin/python -m pytest -q tests/test_confirmed_strategy_review_postgres.py tests/test_candidate_review_postgres.py tests/test_candidate_review_http_postgres.py`；**88 passed / 67.47s / 0 skipped**。包含35项实际策略组合反例，不与前面重叠集合相加。
- 独立规格和代码质量审核绑定精确0c14b33：**PASS，无 Critical/Important/Minor**。审核核对源码和原始测试记录，未重复跑同一套测试，不代表实际来源或客户验收。

正常合入已发布主线 `a31069f` 为 **cda69fb**，无代码冲突；保留对方前端与本片后端。新前端的独立接入审核另发现画像版本被旧 mapper 默认成v1及确认摘要可能选错账号；这些问题的定向修复与实际结论另记，不把历史未提交构包的924/903测试记录升级成本片的测试证明。

## Task 2：共享入口与完整签名接口链

提交 **f4e9b71804077c7b9235bb56821156f649a84c99**。只改共享db/web/ui_api三处薄接线和四个测试文件；114原SQL摘要仍为 `2f971d11f252ea525c0e29920c73f448007650a546a687d7cf17c13d9ac23ae3`。新参数默认None，认证后未注入服务返回501，原HTTPS/Origin/身份/no-store沿用。历史测试中手动注册的第二套相同路由已改成消费共享入口，避免被默认关闭的路由遮蔽。

所有命令使用已锁定环境 `uv run --frozen pytest`，PG连接仅按命令注入测试库，不写入仓库。

| 检查 | 命令中的测试文件 | 结果 |
|---|---|---|
| 共享入口RED | `tests/test_confirmed_strategy_composition.py` | 3 failed / 0.37s；114缺注册、build_app缺参数 |
| 旧二次router暴露问题 | `tests/test_research_strategy_api.py` | 43 failed、8 passed / 1.33s；默认路由遮蔽旧手工测试router |
| 共享入口/原transport修正 | 上述两文件分别运行 | 3 passed / 0.34s；51 passed / 1.36s，不相加成独立全量 |
| 首次真实组合HTTP | `tests/test_confirmed_strategy_http_postgres.py` | 2 passed / 4.05s |
| 独立全新PG安装/原策略 | `tests/test_research_strategies_postgres.py` | 48 passed / 14.21s / 0skip；全新隔离PG16容器，重复迁移/授权及原策略回归 |
| 最终受影响纯契约/路由 | `test_confirmed_strategy_composition.py`、`test_research_strategy_contract.py`、`test_research_strategy_api.py`、`test_identity_contract.py`、`test_ui_api.py`、`test_execution_api.py`、`test_candidate_ingestion_api.py`、`test_candidate_review_api.py`，均在`tests/` | 369 passed / 3.44s / 0skip |
| 最终真实/签名HTTP相关 | `test_confirmed_strategy_http_postgres.py`、`test_execution_http_postgres.py`、`test_candidate_ingestion_http_postgres.py`、`test_candidate_review_http_postgres.py`，均在`tests/` | 12 passed / 15.11s / 0skip |

覆盖：通过共享HTTP新建/确认实际策略→真实签名START/CLAIM→原始上传→本地provider边界分析→人工来源核验→INCLUDE→正常/历史列表。撤销后新分析及旧租约新上传被拒绝；原策略/执行/上传/分析/核验/复核回执仍可读取；退出后拒绝读取。既有实际策略模块还验证撤销后的CANCEL。受限角色只保留原授权所需权利，不获DELETE/TRUNCATE/角色owner/schema CREATE。

测试集合有重叠，不相加。全新测试容器完成后已停止，数据保留且未用于产品环境；未重复运行整仓或构包。完整独立接入审核绑定下方冻结组合提交；本节工程通过不替代M3。

## 同期主线前端接入修正

正常保留 `a31069f` 的全部前端后，独立代码/架构/质量审核发现一项Important和一项Minor；由非原作者的修正代理完成 **3898c3e370b81ec42f8f74416e105c12dc53804b**，只改mapper、确认摘要及三个测试文件：

1. 原始画像版本严格为正安全整数，拒绝缺失、0、字符串、bool等非法事实；版本行ID、已提供的实体ID和status亦须有效。不再用 `Number(version)||1` 编造“当前v1”。真正缺失的实体关联仍允许呈现，但关系为UNKNOWN。
2. 确认页显示所选账号的非登记连接；精确账号的过期/断开状态仍如实呈现。不用同平台第一条记录代替当前账号，登记记录不授权执行，公开网站同样不能由登记记录推导可用。

TDD：三个定向文件先 **20 failed / 25 passed**，实现后 **45/45 passed**。最终 Node **24.19.0** 下运行 `npm test -- --run tests/ui/client.test.ts tests/ui/task-confirmation-summary.test.tsx tests/ui/task-profile.test.tsx tests/ui/task-wizard.test.tsx tests/ui/task-start-contract.test.tsx tests/ui/task-actions.test.tsx tests/taskOperations.test.ts`：**7文件 / 107 passed**；`npm run typecheck`通过。未重跑全桌面或构包。

原独立审核人针对精确3898c3e复审：**PASS，两项发现关闭，无新增发现**；核对五文件完整修改和关联接口，未重复上述测试。此处不升级原生/Mac包、Windows、实际接口、平台或完整UI Goal验收。

## 根代理原故障复测

冻结代码3898c3e后，以原私有探针仅切换到显式实际snapshot reader，重走原先“已纳入但列表零条”的组合：**1 passed / 1.49s**。仍为真实策略/签名/受限PG、合成来源与模型边界；没有重复88项集合。它验证原始故障已消失，与下方独立审核分开记录。

## 最终独立组合审核与限定接收

非实现者`confirmed_strategy_final_review`完整审查 **a31069fead15f395e7b4ec93c9c91e441beea798..3898c3e370b81ec42f8f74416e105c12dc53804b** 的19文件、1,946行自有增量，核对完整计划、实现/前序审核记录及认证、只读reader、授权锁、迁移/授权和桌面映射/账号选择的具名风险。

结论：**Task 2规格、代码、架构、质量均PASS；0 Critical / 0 Important / 0 Minor，可合入此限定工程片。** 独立diff-check通过，确认111–114 SQL无变化、审核基线为冻结代码的祖先。审核未重跑已覆盖测试，前述执行结果仍属于实现者/根代理证据，不冒称独立复跑。

CodexiMac据此限定ACK Win的实际确认策略后端接入：持久策略、共享API、签名执行/上传和人工判断列表已组成工程链；不是Win客户端消费ACK，也不将04B/04C父卡或Goal标DONE。生产、真实来源、真实模型质量、Windows/原生/构包、发送/回复、客户UAT及收费仍未获得本片证明。下一步保留共享机会固定原文证据和Win实际来源/客户端接入，不重复扩大基础治理。

审核绑定上述代码SHA；随后的提交只整理合同、任务书及QA，不把新提交描述为重新构包或全仓复跑。主线推送和远端SHA一致性由根代理另行核验，不由只读代码审核代为证明。

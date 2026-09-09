# 固定原文证据：工程接入验收

日期：2026-09-10。基线`aac3fe9c6cc926108d70a551b90bc3e133984880`，认领`c0a2430`，首次纳入绑定细化`fdc1a55`；核心`26502ee`，共享HTTP断言`9c71e3b`。依据[计划](../superpowers/plans/2026-09-10-opportunity-source-evidence.md)和[客户端接入合同](../contracts/V02_OPPORTUNITY_SOURCE_EVIDENCE.md)。

当前实现者与根代理定向测试已完成，`26502ee`独立任务审核规格符合/质量批准，0项发现；整体集成终审仍在收口。真实来源、正式模型效果、Win客户端、实际收发、生产与客户UAT未获得本片证明。测试使用真实受限PG、实际策略和签名协议，但来源内容及本地模型响应是明确的合成测试输入。

## 已观察的缺口与初始RED

旧商机详情只返回人工摘要、摘录和共享来源的当前字段；没有人工纳入时固定的原始内容版本、观察与逐字引用。私有候选保存了这些信息，但不能把其完整请求快照或全部观察历史直接共享。

独立只读预检确认在既有INCLUDE事务末端保存一条最小共享快照可复用当前数据与锁；无需修改既有111–114 SQL或用户界面。COMMENT的原帖标题、本人正文和父评论正文可能来自三个主体；同内容的新观察不改变内容版本，因此必须明示选择纳入时当前同版本观察，而不是伪称之前预览时间已绑定。

根代理在实现前扩展既有`test_shared_http_actual_strategy_signed_review_and_revocation_chain`：仍通过共享HTTP实际prepare/confirm、签名START/CLAIM/上传、本地provider分析、人工核验、INCLUDE，再请求商机详情。

```sh
.venv/bin/python -m pytest -q tests/test_confirmed_strategy_http_postgres.py::test_shared_http_actual_strategy_signed_review_and_revocation_chain --tb=short
```

专用测试库仅按命令注入环境，连接不写入仓库。结果：**1 failed / 2.26s**，`KeyError: 'source_evidence'`。纳入成功并返回200后缺少详情证据字段；不是数据库、登录、fixture版本或平台故障。

## 接收口径

新证据必须与首次人工纳入原子保存，重复/历史不替换；同空间只共享批准的公开内容，跨空间拒绝，私有画像引文与搜索历史不泄漏。正常详情读与证据在同SQL快照；确无记录才NOT_CAPTURED，损坏或读取失败不能假装没有证据。新表最小权限与首次IMPORTED绑定、不可变保护一并验证。

实现者提供精确提交、纯投影及实际PG反例；根代理验证共享HTTP路径；独立审核核对对应提交与证据。测试集合不累加冒充全仓，未变代码不重复跑整套桌面/构包。完成后的实际结果在下节追加，父卡/Goal状态仅由唯一任务书记录。

## 实现者测试记录

纯投影从缺模块RED开始，首轮9通过；修正为实际内容摘要并增加不匹配反例后10通过；加入重新计算摘要后仍含非法标量/时间/版本的损坏反例，先4失败、10通过，再14通过。固定内容摘要使用实际原始内容的canonical SHA256，不能以格式正确的占位hash代替。PG最初实际纳入后读取缺少`source_evidence`，1失败/1.69s；新增表、授权、生产者与读取后，先1项通过/1.55s，再扩展8项PG专项通过/8.60s。

实现者最终命令：

```sh
.venv/bin/python -m pytest -q tests/test_opportunity_evidence.py tests/test_opportunity_evidence_postgres.py tests/test_candidate_review_postgres.py tests/test_confirmed_strategy_review_postgres.py
```

实际结果：**105 passed / 66.45s / 0 skipped / 0 failed**。覆盖真实受限PG首次纳入、原请求/重复纳入、后续原文变化、评论主体、同空间共享/跨空间拒绝、旧记录未留存、损坏报错、写入失败整单回滚，以及已有策略/复核边界。此集合与上述专项重叠，不相加。

## 根代理共享HTTP验证

```sh
.venv/bin/python -m pytest -q tests/test_confirmed_strategy_http_postgres.py tests/test_candidate_review_http_postgres.py tests/test_ui_api.py tests/test_pilot_web.py --tb=short
```

实际 **69 passed / 13.53s / 0 skipped / 0 failed**。原先失败的共享HTTP链现验证原始内容版本、正文、选中观察及实际接收时间、模型分析ID和公开引用；同空间同事取得相同固定证据但看不到私有候选，其他空间404，撤销策略后历史证据不变，注销后401，响应保持no-store。未修改生产HTTP处理器，不用测试专属路由覆盖旧接口；该数量包含既有UI与web回归，不等于69次真实平台采集。

## 正常合入并行主线

正常合入`4251e75`为`a128044`，无冲突；核心`26502ee`九文件逐字节不变。保留Win05C策略传输/显式确认与原UUID恢复、Mac已审React/CSP与原生smoke修正，以及Win日程policyVersion兼容。根代理读入站QA和精确后端增量，并执行新增影响面：

- `pytest -q tests/test_research_strategy_contract.py tests/test_confirmed_strategy_http_postgres.py --tb=short`：**196 passed / 5.75s / 0 skipped**，其中共享HTTP实际受限PG链仍取得固定证据；不是196个平台用例。
- desktop的`researchStrategies`、`researchStrategyTransport`、`strategyConfirmation`、`ui/strategy-confirmation-hook`、`ui/operation-ledger`五文件：**75 passed / 2.03s**；`tsc --noEmit` exit0。

沿用[Win已审证据](V02-05C_STRATEGY_CLIENT_WIN_REVIEW.md)和[Mac原生候选证据](ui-reviewed-integration/README.md)的原始版本边界，不把同一代码重复构包。本轮未重跑真实Node→PG桥接、Mac原生生命周期或Windows安装；没有把历史包绑定到新增客户端代码。05C页面接线与05G原文显示仍未完成。

## 独立任务审核

非实现者`opportunity_evidence_task_review`对`fdc1a55..26502ee`九文件完成规格与代码质量审核：**SPEC compliant / QUALITY Approved，Critical、Important、Minor均0项**。额外核对新builder与既有入库协议的合法空值、非空限制和canonical内容摘要兼容，未发现新投影缩窄合法输入。审核只读，没有复跑105项或把执行者结果改记为独立实跑。

审核指出根HTTP、合入后的组合、部署授权与远端同步需另外提供证据：前两项由本页69/196及合并树核对覆盖；受信授权脚本仅有实际受限测试，未作为生产安装；最终推送以实际远端SHA核验为准。本文不以任务审核代替整体集成终审。

## 下一步可用性缺口

正常`pilot/cli.py:web`入口尚未构造已注册的策略、执行、候选与复核服务。本片验证的是明确注入真实组件的HTTP组合，不能把它称为客户默认启动已经可用。下一主线是受信正常运行装配与Win来源/客户端接入；缺真实来源policy或模型配置时继续明确不可用，不因实例化成功自动开启能力。Win05G/05E消费本DTO、05F签名执行、实际来源、确认后收发及客户验收继续按原子卡推进，不新增一套页面。

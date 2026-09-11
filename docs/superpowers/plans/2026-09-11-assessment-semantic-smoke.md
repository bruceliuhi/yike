# 商机判断小样本语义检查 Implementation Plan

**Goal:** 在继续邀请试用前，用当前实际模型找出“把非买方当商机”的明显风险；归入 V02-04/10，不改变产品范围。
**Architecture:** 复用现有候选判断适配器与隔离子进程，不新增评估服务、数据库或客户入口。六个冻结的合成用例；运行前显式 opt-in，最多每例一次调用，不重试。
**Tech Stack:** Python、pytest、现有 OpenAICompatibleCandidateAssessmentModel。

## 设计与边界

采用真实模型＋小型反例集。仅继续 mock 检查不能证明语义；直接大批真实买方评测会混入采集、权限和标注噪声，本轮不采用。现有用户授权允许 V0.2 内技术细化及已批准方舟模型；不另行部署、不触达、不消费客户试用。

六例固定为：AI开发采购、展台搭建采购、同行广告、个人招聘、评论只夸父帖、AI需求投给展台画像。前两例应匹配且有本人意向，但核验缺失仍 REVIEW；后四例不得成为分级可联系买方。画像只描述合成服务，不包含客户资料。用例不能训练或改写为通过。

模型仅使用 `YIKE_ASSESSMENT_LIVE=1` 与显式环境凭据；配置不进仓、不输出。使用已批准的北京 Ark 与 Turbo 型号，正常 worker 单次超时沿用30秒。每例输出固定case ID、有限枚举判断、规则摘要、模型名及已验证token用量；不打印provider原始错误、请求头或密钥。提供端返回失败或无结果仍记录失败，不能记成功/零成本。

这不是准确率基准、商机数量或客户UAT。通过只排除这些明显反例；失败须保留，再定位当前合同/提示词/校验的原因。未知发布时间/打开状态不靠合成日期伪装已验。

## 执行（根串行，最后一次独立审核）

- [x] 新增 `tests/test_assessment_semantic_live_optin.py`，默认无外部调用；六例输入及预期先冻结。显式开启后每例调用现有 `assess(description,content,industry_strategy)` 一次，以实际结果检查，失败不自动重试。
- [x] 先验证无opt-in六例全部跳过；再以已授权本机密钥仅在进程环境装配，执行一次六例实际worker检查，记录全部结果及用量是否可得。不得让 pytest 失败打印密钥或原provider包。
- [x] 本次没有语义检查失败；不修改运行规则或放宽预期。首次用例把COMMENT写成SOCIAL_COMMENT，在任何模型调用前按实际枚举修正并补离线合同检查。
- [x] 非作者审核用例、运行边界及结果解读，更新唯一任务书；本批提交按正常快进推main，不部署或构包。

## Evidence

测试源码 `f6a95a6`，基线 `51f635a`。未更改生产模型/Skill/采集或发送代码。

- 默认命令 `python -m pytest -q tests/test_assessment_semantic_live_optin.py`：1 passed / 6 skipped in 0.16s；实网检查默认关闭。
- 明确 opt-in 后，同文件执行 `pytest -q -s --tb=no`：**7 passed in 94.98s**，其中1个离线合同检查、6次实际模型调用；未用重试插件或重跑失败，当前worker30秒边界不变。批准的密钥仅由仓库外一次性helper读入子进程环境，不入文件/报告/argv。
- 模型 `doubao-seed-2-1-turbo-260628`；规则摘要 `45f24d725e8e7203ee935c11a8198b1c01f66fbac890cd7f950d74347bd14eb0`；六次provider有效token合计39,466，不是费用/搜贝或成本估算。

| 冻结合成用例 | 业务匹配 / 意向 | 决策 / 等级 | token |
|---|---|---|---:|
| AI开发采购 | HIGH / HIGH | REVIEW / S | 6,652 |
| 展台搭建采购 | HIGH / HIGH | REVIEW / S | 6,563 |
| 同行广告 | LOW / LOW | EXCLUDE / null | 6,481 |
| 全职招聘 | LOW / LOW | EXCLUDE / null | 6,612 |
| 评论仅夸父帖 | HIGH / LOW | OBSERVE / null | 6,698 |
| AI需求＋展台画像 | LOW / HIGH | EXCLUDE / null | 6,460 |

全部结果经过现有结构/逐字引用校验；没有直接发送建议。只说明当前模型在这六个固定合成样本上未触发预先设定的误判条件，不能宣传100%准确、真实获客已有效或所有维度语义均已验证；草稿吸引力/回复率不在本检查结论内。跨行业真实样本盲标、持续供给和客户试用仍缺证据。本批不扩人工标注为已完成UAT，也不因本检查通过继续调提示词。

非作者 `public_scope_review` 对 `f6a95a68d978f6a0e5bdcbebb8a3f66a4a597d8e` 用例/计划、既有adapter边界和本次实际结果独立审核PASS，无阻断。复用既有调用结果，未重复运行模型。报告 `/tmp/yike-assessment-semantic-review.md`；本节及上表保存可移植结论。

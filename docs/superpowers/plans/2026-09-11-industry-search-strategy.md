# 行业搜索策略 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development；执行已批准 V02-04/05 的来源/需求表达/依据/反例要求，复用搜索建议确认弹窗。

**Goal:** 在真实搜索建议服务返回可核对的跨行业策略，而不是只有词表；建议不冒充实际商机、平台能力或已采用任务规则。

**Architecture:** 现有搜索回执协议v1保持兼容，在result增加可选strategy。当前实际模型适配器要求新版结构输出；历史和第三方旧模型结果无strategy时维持旧解释。策略版本与画像/模型/结果一起存入原不可变回执，不新建数据库表或执行器。

**Tech Stack:** Pydantic/httpx、现有PostgreSQL回执、Zod/React。

## Global Constraints

- “行业模板不是允许名单”；不按固定行业标签禁止其它业务。
- “建议输出与原始候选/商机分开，必须由用户确认最终配置后执行”；“不能自动增加连接平台、监控频率或费用预算”。
- 真实画像证据逐字引用；策略方向和待寻找信号是建议，不是已存在买方事实。缺失角色/销售方式返回null，不补造。
- 不新增模型调用、资料披露、真实平台搜索或发送；模型调用仍经原预览/确认链。
- 用户要求节省token：小范围RED/GREEN，一次独立整批审核，无全量测试或构包；修复只验证差量。

### Task 1: 可保存、可验证的策略结果

**Files:** pilot/search_suggestion_model.py、pilot/search_suggestions.py（仅必要serialization）；tests/test_industry_search_strategy.py。

**Interfaces:** `strategy` 可选于旧 SuggestionContent。存在时严格对象：
```json
{"version":"industry-search-strategy-v1","buyerRole":null,"salesMotion":null,
 "sourceTypes":["SOCIAL_POST"],"intentSignals":["正在寻找供应商"],
 "counterSignals":["同行服务广告"],"basis":["画像逐字引用"]}
```
buyerRole/salesMotion为null或最多120字符的画像明确角色/销售方式；非空值必须逐字出现在description中。sourceTypes为1–5个不重复枚举SOCIAL_POST/COMMENT/PROCUREMENT/COMPANY_UPDATE/INDUSTRY_SITE，只建议内容类型、不授权平台。intentSignals为1–5条，counterSignals为0–5条，每条1–160字符，去空白去重检查但不改保存值；basis为1–8条1–300字符逐字画像引用。禁止额外字段和无效版本。所有文字复用现有非空/控制字符约束。

- [ ] RED：合法新策略保存往返、角色/方式/依据伪造或未知版本拒绝，旧无strategy结果往返不增加空字段。
- [ ] 新增严格策略类型、嵌套可选兼容validation。当前OpenAI-compatible适配器用单独required-strategy输出schema，并在实际响应中强制strategy存在；仍复用原httpx/用量/异常/披露链，不让旧mock生成器等价于新适配器质量证据。
- [ ] 更新系统规则：分别从产品/业务问题、买方角色、交易/交付方式构思词组；项目服务、制造贸易、本地生活、软件数字服务、零售品牌仅作方法举例；可自定义，不填虚构采购事实；rationale解释sourceTypes建议，unknowns列画像缺失。新策略version写入结果；外层search-suggestion-v1仅为旧回执协议，不改历史。
- [ ] 定向模型transport测试验证实际请求schema及响应结构；复用旧解析测试，仅新受影响项。报告限定离线结构证据，提交后端，不push/amend。

### Task 2: 原搜索建议弹窗展示

**Files:** desktop/src/shared/searchSuggestions.ts、renderer/pages/tasks/SearchSuggestionPanel.tsx；desktop/tests/ui/industry-search-strategy.test.tsx。

- [ ] RED：新结构schema接受合法strategy、拒绝多余权限字段；现有弹窗显示角色/销售方式/来源类型/信号/反例/原文依据；未知显示“画像未说明”，旧结果仍可显示，采用只传原回执而不添加平台授权。
- [ ] 添加兼容可选strategy及对应类型；复用现有Modal中简单分节/列表，不新页面、不改变外发确认。醒目标记“策略建议，尚未执行”；来源类型不是支持平台，不把PROCUREMENT变成投标执行。
- [ ] 定向新UI/schema + 既有搜索结果兼容用例；typecheck一次。完成后独立审核，单一证据更新并按授权合入main。

## 实施与验证

基线9d5503e，待实施。本批仅落实可解释建议层；策略独立编辑及随最终任务配置/候选判断完整采用尚需接续，不据此关闭V02-04/05、跨行业效果或上线Goal。

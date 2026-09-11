# 作者更新完整纵向交付计划

> 使用subagent-driven-development执行；用户要求压缩重复审核，整批一次非作者审核。

**Goal:** 固定项目源的作者更新进入普通候选原文和模型判断。
**Architecture:** 按[设计](../specs/2026-09-11-public-author-context-design.md)的唯一字段合同复用JSON内容版本、普通执行和确认，不建第二线索库。
**Tech Stack:** Python/Pydantic/PostgreSQL；TypeScript/Zod/React/Node fetch。

## Global Constraints

全部精确字段、限制及枚举以设计为准。旧任务不扩请求/权限；旧内容hash不变；不部署/构包/发送，不调用付费模型。先RED后实现；非作者审核一次整批。工作树已隔离且干净，基线11a640b。

## Task 1: 后端合同与模型/能力

- [ ] 在tests新增source_context合法/错配/超限/旧hash/模型引用的定向失败测试。
- [ ] 修改pilot/candidate_contract.py、candidate_ingestion.py持久可选上下文；candidate_review.py投影author_updates/scope；candidate_assessment_model.py严格验证与引用/规则版本。未携上下文的旧输入保留旧字段。
- [ ] pilot/research_strategy_contract.py、foreground_collection.py、monitor_runtime.py及模式CLI注册增加新源/新模式；旧mode目录不能扩大；research拒绝新源。
- [ ] 跑涉及的新测试/旧模型和来源合同；一次隔离PG上下文版本联验。无真实模型请求。报告具体命令及结果。

## Task 2: 客户端与真实来源

- [ ] 先新增publicCommunityDriver/上传与raw evidence/模型DTO/原文视图定向测试并见RED。
- [ ] shared source_context独立schema复用于上传/raw；内容对照和时间检查纳入context；candidateReviewApi引用允许author_updates索引。
- [ ] source目录/任务限制支持显式新源；driver有界索引+作者回复读取，保留统一deadline/bytes/cooldown；原文视图显示更新/缺口，来源label暴露范围。
- [ ] 定向vitest和tsc；一次真实只读driver，不以mock或模型判断代替真实数据证据。

## Task 3: 整合

- [ ] 对照两端合同及旧值字节，定向HTTP/PG/TS联验；不全量构包。
- [ ] 非作者审核固定提交，必要差量修复后更新任务书并正常快进main；实际来源/Windows/生产范围逐项说明。

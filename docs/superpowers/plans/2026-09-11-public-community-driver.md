# MP-03 公开社区读取驱动接续

沿用已批准的 V02_MULTIPLATFORM_SKILL_PLAN 第三方公开 API/RSS 路线及 PUBLIC_ANONYMOUS 协议，不新增产品范围，不宣称开通全网。首片仅实现 CollectionDriver 的 V2EX 近期主题适配；未接客户入口前能力保持关闭。

## 决策与证据

官方旧 API 说明 <https://www.v2ex.com/p/7v9tec53> 指明 latest 无需认证、默认每 IP 每小时 120 次，并反对内容农场用途；新 API <https://www.v2ex.com/help/api> 要求 PAT。2026-09-11 本机一次无登录 GET latest 实际得到 42 条和原始 content/title/created/id/url 字段；仅证明该时刻入口可读，不是高意向、稳定覆盖或商业数据再分发授权。

选择固定官方 HTTPS latest 端点及本地关键词/排除词筛选，保留正文和 created，不读取用户主页、私信、评论、PAT/Cookie；不走未授权全文历史搜索。暂不做任意 URL 或递归网站采集，避免把新 SSRF/重定向/分页边界混进首片。界面接线时必须明确“V2EX 近期主题，有界采样，不覆盖历史/全站”；默认不公开转载原文或出售数据集。

## 本片实施

1. 新独立 driver 复用 CollectionDriver 输入/停止句柄和 CandidateRecord，验证 PUBLIC_WEB/PUBLIC_ANONYMOUS、已确认一次搜索快照与预算，拒绝账号连接、monitor、links、research。
2. 一次 GET，禁重定向/凭据/自动重试，20 秒以内截止，响应流 1MiB 上限、最多100个主题。错误、限流、异常正文不冒充零结果；取消等待请求结束，不入库。
3. 最多检查所分配记录预算内的主题，再按原始标题/正文筛选；保留原文，主题id及作者公开id不等于认证身份。观察时间独立于发布时间，不使用 last_touched 刷新需求时效。
4. 定向反例覆盖原文/日期/URL、过滤及预算、拒绝其他来源配置、重定向/429/大响应、取消。一次真实读取只记录数量/字段与适用范围，不输出敏感信息或计作客户商机。
5. 非作者独立审核后合入 main，下一片接匿名能力结构与普通TaskWizard→START→现有worker→候选详情。后续再接周期监控、站点扩展及实际质量验证，不能以驱动单测标 MP-03/Goal 完成。

账号平台链不修改；本片不启用服务器 capability、不发送消息、不创建假账号、不迁移数据库、不重新构包。

## 实施与限定验证

源码 `f0f0f8474472ed14073739e1567d0af8f3822a94` 已实现独立 driver。先记录缺少实现的14项 RED；补实现后14项通过及 TypeScript 检查通过，再补响应体停滞截止反例，最终15项全部通过（0.231秒）。未跑全量业务测试或构包。

非作者 `material_reference_architecture` 对该完整源码 SHA 独立审核 GO，无本片阻断 P1/P2；只审核独立驱动，不替 TaskWizard、服务端策略或 MP-03 整体验收。审核未重复测试或联网。

一次实际 Node 运行（Vite SSR 仅负责载入 TypeScript，未替换 fetch）调用同一驱动，关键词为“AI／需求”、检查上限100，返回11条有原始发布时间的 PAGE 记录。该探针使用本机构造的执行形状，不是服务端真实 START/CLAIM，也未调用客户数据库、发送平台消息或验证客户登录。结果是未判定的来源记录，不能称为11条商机或用户流程已通过；正文与用户资料未写入验证文档。

下一片文件接线：`shared/foregroundCollection.ts` 区分匿名能力与账号 binding；`foregroundCollectionController.ts` 按 PUBLIC_ANONYMOUS 跳过账号 profile/Python 探测，仍使用原设备 scope 和 worker；`domain/task.ts` 与 TaskWizard 展示确切站点范围、无需账号但必须确认来源。复用既有执行、上传、恢复和人工复核，不另造执行协议。

### 后端策略接续（2026-09-11）

源码 `f1fbe80b0d973475c6d351e6aeca32b1c0a8dee2` 增加显式 `four-platform-public-monitor-v1` 策略：PUBLIC_WEB仅允许PUBLIC_ANONYMOUS、确认配置中的 `publicSource=v2ex-latest-v1`、单次搜索及无schedule/research/links。旧四账号平台和监控行为保持；公开社区监控仍不开放。新字段缺省时序列化不增加null字段，保留旧确认快照及哈希；`research_platforms` 的访问模式已修正为PUBLIC_ANONYMOUS。

主Agent复核命令：`python -m pytest -q tests/test_public_collection_policy.py tests/test_foreground_collection.py tests/test_research_strategy_contract.py tests/test_monitor_runtime_api.py`，242 passed / 0.79s，另有diff check通过。测试使用合成配置和接口替身，不是PostgreSQL、平台或客户端端到端验收；未重复构包或全量测试。

非作者 `material_reference_architecture` 对该源码SHA只读独立审核Ready to merge: Yes，无阻断P1/P2。默认环境配置未修改。**现客户端严格support schema尚不接受新增public_source，部署不得启用新模式，直到客户端协议、确认、执行接线完成并验证。** 本次只提交默认未启用的后端能力，不代表普通用户已能采集公开社区或MP-03已完成。

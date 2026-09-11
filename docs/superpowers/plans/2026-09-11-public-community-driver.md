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

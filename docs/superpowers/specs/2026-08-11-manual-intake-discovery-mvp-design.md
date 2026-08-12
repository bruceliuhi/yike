# 意客 AI DISCOVERY MVP 人工导入设计

> 状态：`HISTORICAL_SUPERSEDED_DRAFT`
> 日期：2026-08-11
> 用户目标：推进到开发完成，可以收集线索
> 工作区：`/Users/xingheimac/Developer/Work/意客AI-MVP`
> 证据边界：独立市场发现工具，不是意客 AI V0.3、R1、R2 或商业上线证据

## 1. 决策

本 MVP 使用“人工发现、结构化导入、本地处理”的路线：

```text
操作人在 B 站网页手动发现公开业务信号
-> 手动复制必要文本和原链接
-> 本地单条表单、CSV 或 JSONL 导入
-> 规范化、去重和来源观察记录
-> 可选 AI 评分
-> 人工复核与联系草稿
-> 人工联系和事实登记
-> SQLite 指标与脱敏导出
```

应用不得请求、抓取或解析 B 站网页，不提供爬虫、浏览器扩展、DOM 抽取、隐蔽接口调用、Cookie 导入、代理轮换或自动联系。未来只有取得覆盖目标数据的书面许可或官方 API 授权，并经过新的设计批准，才能增加平台适配器。

## 2. 成功标准

### 2.1 本轮开发完成

同时满足以下条件时状态为 `MVP_TECH_READY_MANUAL_INTAKE`：

1. 在空目录用锁定依赖可重复安装并启动。
2. SQLite migration 可在空库运行，并拒绝不兼容 schema。
3. 单条表单、CSV 和 JSONL 都能导入人工提供的公开信号。
4. 重复导入不新增 Signal，但保留新的 observation。
5. 每条 Signal 保留查询、来源 URL、正文摘要、父上下文和导入时间。
6. 模型未配置或输出无效时失败关闭，不生成 A/B；线索仍可人工复核。
7. 页面可完成“创建实验 -> 导入 -> 查看 -> 复核 -> 草稿 -> 登记联系/回复”。
8. 指标只从事实行计算，请求不能直接注入计数。
9. 服务只监听 `127.0.0.1`，日志、数据库和导出不包含 Secret、Cookie、Token 或 Profile。
10. 自动测试、compile、前端语法、Secret 扫描、空库 HTTP 主流程和 `git diff --check` 通过。

`MVP_TECH_READY_MANUAL_INTAKE` 只证明工具可运行。至少一条由用户亲自从公开页面复制并导入、且原链接可人工重开的记录，才能证明 `REAL_MANUAL_INTAKE_PROVEN`。

### 2.2 14 天业务门槛

后续真实实验仍使用以下门槛，但不属于本轮“开发完成”的替代证据：

- 至少 300 条可人工重新核验的唯一公开 Signal；
- 至少 100 条人工复核；
- 至少 40 条 AI A/B 候选完成人工复核，精确率不低于 50%；
- 至少 30 次合规人工联系；
- 至少 5 次有效回复、2 次需求访谈、1 个明确方案或报价机会；
- 无平台处罚、账号异常、误发、重复联系或敏感信息事故。

达标只产生 `PROCEED_TO_V03_REVIEW`，不自动激活 V0.3。

## 3. 范围

### 3.1 必须包含

- Python 3.11、uv、SQLite、FastAPI、Jinja2 和少量原生 JavaScript。
- 一个活动 `mvp_run`，冻结初始关键词、Prompt 和 Schema 摘要。
- 单条、CSV、JSONL 人工导入。
- 规范化、双层去重、来源观察和稳定错误码。
- OpenAI-compatible 可选评分器与严格 JSON Schema。
- 人工复核、草稿、联系、回复、访谈和报价事实。
- 运行、线索、线索详情、跟进、指标五个本地页面。
- CSV/JSON 脱敏导出、数据保留和不可变结论记录。

### 3.2 明确不做

- 不向 B 站或其他内容平台发起任何采集请求。
- 不读取浏览器 DOM、Cookie、Storage、二维码、验证码或 Profile。
- 不自动发送评论、私信、邮件或企业微信消息。
- 不部署公网，不做多租户、移动端、计费、CRM 同步或 Windows 安装包。
- 不把 fixture、模拟回复或 AI 推断计入真实业务指标。

## 4. 导入契约

### 4.1 必填字段

- `query_cluster`
- `query_text`
- `source_url`：`https`，主机必须是 `bilibili.com` 或其子域
- `source_title`
- `signal_body`
- `author_public_id`
- `published_at`：带时区 ISO 8601

### 4.2 可选字段

- `external_video_id`
- `external_comment_id`
- `parent_external_id`
- `parent_body`
- `comment_url`
- `author_public_name`
- `explicit_industry`

CSV 使用 UTF-8 头行；JSONL 每行一个对象。未知字段拒绝，正文为空拒绝，非 B 站 URL 拒绝。单文件上限 2 MiB、1000 行；文件只在请求内存中解析，不保存原始上传副本。

### 4.3 去重与 observation

Signal 业务键按优先顺序固定：

1. 存在 `external_comment_id` 时：`platform + external_comment_id`。
2. 否则：规范化 `comment_url/source_url + author_public_id + body_sha256`。

重复业务键复用原 Signal，不覆盖原文；每次导入新增 `signal_observation`，记录 `mvp_run_id`、导入批次、查询簇、查询词、观察时间和输入摘要。若相同外部 ID 对应不同正文，整条记录失败为 `SIGNAL_IDENTITY_CONFLICT`。

## 5. 数据模型

所有主表使用 SQLite 外键、CHECK 约束和 UTC 时间；显示按 `Asia/Shanghai` 转换。

### 5.1 实验和配置

- `mvp_runs`：`run_id`、`status(DRAFT|ACTIVE|FROZEN|COMPLETED)`、`timezone`、`started_at`、`ends_at`、`config_sha256`、`final_decision`、`finalized_at`、`final_report_sha256`。
- 同时最多一个 `ACTIVE` run；`FROZEN/COMPLETED` 的配置和事实不允许更新。
- `keyword_versions`：版本、关键词 JSON、来源理由、创建时间和摘要。

### 5.2 导入与证据

- `import_batches`：批次 ID、run、格式、总行数、成功/重复/失败数、状态和错误摘要。
- `sources`：平台、视频 ID、标题、规范 URL、作者公开标识和发布时间。
- `signals`：source、评论 ID、父评论 ID/正文、作者公开标识、正文、时间、正文 SHA、行业和可核验状态。
- `signal_observations`：run、batch、signal、查询簇/词、观察时间和输入摘要。

### 5.3 评分和人工真值

- `score_runs`：run、signal、模型/Prompt/Schema 版本、0–12 分、A/B/C/D、置信度、理由 JSON、状态和 Token 用量。
- `human_reviews`：run、signal、`score_run_id` 可空、人工标签、原因、备注、开始/结束和有效处理秒数。
- AI 精确率只统计绑定到具体成功 `score_run_id` 且该评分第一次展示给操作人的唯一 Signal；同一 Signal/run 只计一次。

### 5.4 草稿和业务事实

- `draft_runs`：run、signal、模型版本、Prompt 版本、原草稿、状态和时间。
- `outreach_actions`：run、signal、draft、唯一联系主体键、人工批准文本、渠道、公开商务入口 URL、发送时间、证据摘要、状态。
- 同一 run、同一联系主体最多一条首次联系；跟进通过 `parent_outreach_id` 关联且不增加首次联系数。
- `response_events`：outreach、事件类型、摘要、发生时间、证据摘要、核验时间。
- `interviews`：response、计划/完成时间、五项问题摘要和下一步。
- `quote_opportunities`：可绑定 response 或 interview，至少一者存在；保存范围摘要、同意接收价格、核验时间。
- `activity_sessions`：复核/草稿的开始、暂停、恢复、完成，用于人工时间指标。
- `daily_snapshots`：run、自然日、事实摘要、风险事件和内容摘要。

## 6. AI 契约

评分沿用 0–12 分和 A/B/C/D 规则，模型必须返回严格 JSON。应用校验：

- 分项和总分一致；
- A/B 不得命中硬排除项；
- evidence 只能是输入正文的短片段；
- 不得补造公司、职位、预算或联系方式；
- 超时、429、5xx、非 JSON、未知枚举或 Schema 错误均保存失败 `score_run`，不降级为 A/B。

模型配置只来自运行环境：`DISCOVERY_MODEL_BASE_URL`、`DISCOVERY_MODEL_API_KEY`、`DISCOVERY_MODEL_NAME`。API Key 不写入 SQLite、日志、页面或导出。未配置时显示 `MODEL_NOT_CONFIGURED`。

## 7. 页面和 API

- `/runs`：创建/查看当前实验和配置摘要。
- `/imports`：单条表单、CSV/JSONL 上传和批次结果。
- `/signals`：筛选和排序。
- `/signals/{id}`：证据、评分、人工复核、草稿和联系登记。
- `/followups`：已联系、回复、访谈、报价及下一步。
- `/metrics`：技术、信号质量和业务结果三栏。
- `/exports/daily.json`、`/exports/signals.csv`：脱敏导出。

所有写 API 使用表单或 JSON 大小限制、同源校验和稳定错误码；应用不提供平台 URL 的服务器端抓取或预览。

## 8. 互斥终态

按以下优先级只生成一个结论：

1. 任何安全、平台处罚、重复骚扰或敏感信息事故：`STOP_DISCOVERY`。
2. 外部权限、人工输入或模型长期不可用导致样本门槛无法评估：`BLOCKED_INPUT`。
3. 达到全部成功门槛：`PROCEED_TO_V03_REVIEW`。
4. 命中止损门槛：`STOP_DISCOVERY`。
5. 已到 Day 14 或用户提前结束但不属于以上：`REVISE_MVP`。

最终结论在单事务中写入 `final_decision/finalized_at/final_report_sha256`，之后数据库触发器拒绝修改该 run 的事实。调整必须创建新 run。

## 9. 安全和隐私

- 只处理操作人明确复制的最小公开信息。
- 页面显示处理目的、保留期、删除方式和联系邮箱占位配置；真实运行前必须配置实际联系人。
- 按作者公开 ID 支持查找、反对处理和删除；删除同时覆盖导出与下次备份。
- 不推断敏感属性，不从头像、姓名或地域推断行业。
- 不在 B 站回复中发送促销垃圾信息；联系只由人逐条决定，并优先使用对方明确公开的商务入口。
- 默认 30 天后删除未联系正文；摘要哈希和聚合计数可保留。已联系事实按本次决策所需期限保留，并可按请求删除。

## 10. 验收

### 自动门禁

- migration、run 唯一性和冻结不可变；
- CSV/JSONL/schema/大小限制；
- URL、时间、正文、父上下文规范化；
- 双层去重、identity conflict 和 observation 保留；
- 模型严格输出与失败关闭；
- 评分—人工复核版本绑定；
- 联系主体去重和事实因果链；
- 指标注入拒绝；
- Secret 扫描和回环监听；
- 空库 FastAPI 主流程。

### 本地运行验收

1. 创建一个 ACTIVE run。
2. 导入一条 `SIMULATION_ONLY` 测试记录并验证完整页面流程。
3. 清除模拟库。
4. 由用户人工提供一条真实公开记录，导入后人工重开原链接并标记 `source_verified_at`。
5. 保存脱敏验收摘要，不保存网页截图、Cookie 或完整 Profile。

未完成第 4 步时只能声明 `MVP_TECH_READY_MANUAL_INTAKE`，不能声明 `REAL_MANUAL_INTAKE_PROVEN`。

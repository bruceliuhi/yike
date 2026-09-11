# 知乎原文与评论入库适配

> For agentic workers: use subagent-driven-development and targeted TDD. 复用已批准V0.2多平台方案；一次整批独立审核，修复只跑差量。

**Goal:** 固定依赖的知乎回答/文章原文与评论可保真进入现有候选DTO，为后续真实采集接线提供可运行的数据适配，不只增加平台名称。
**Architecture:** 停止写入后的受限JSONL读取→按内容类型+ID精确关联→纯转换→既有CandidateBatch校验。账号、运行、上传、模型、复核权限均不由解析授予。
**Tech Stack:** Python标准库、现有Pydantic契约与固定MediaCrawler模型；无新依赖/迁移/UI。

## Global Constraints

- 全量V0.2保持，base e8ddd707ad885c2eae2d327f732988c4df3714b1。此批不启用知乎执行能力，不把解析成功当真实平台证明。
- 固定源模型为 content_id/content_type/content_text/content_url/question_id/title/created_time/updated_time/last_modify_ts；comment_id/parent_comment_id/content/publish_time/content_id/content_type/last_modify_ts。creator_hash和masked nickname不是公开身份，一律不转换为author_public_id。
- 唯一来源ID `answer:<id>` / `article:<id>` / `zvideo:<id>`，防不同类型数字ID碰撞。回答URL仅接受精确https://www.zhihu.com/question/<question_id>/answer/<id>，文章仅https://zhuanlan.zhihu.com/p/<id>，视频仅https://www.zhihu.com/zvideo/<id>；不虚构评论深链，COMMENT沿用真实所属页URL并保留评论ID。
- 原文逐字保留；content_text为空的zvideo不生成POST，但仍可承载有正文评论；answer/article无正文明确失败，不用desc/标题冒充正文。视频外链不扩大允许站点。原文/评论单独发布时间；0/空/缺省表示未知，不以updated_time或收到时间刷新。观察时间来自本人源存储last_modify_ts，不补当前时间。
- comment.parent_comment_id空/0/null表示无父评论，有合法ID时仅保留ID、其它上下文未知；若提供同批父评论，不能因此跨来源拼接。ID只收正ASCII整数串或整数，不收bool/浮点/前导零。
- 读取沿用现有路径、文件/总字节/单行上限、重复键与非有限数、文件变更、防链接检查。知乎目录zhihu/jsonl；停止后的完整内容/评论文件配对，内容键含类型，孤儿/冲突/重复评论拒绝整批。输出POST原始项 `{content:raw}` 与COMMENT `{content:raw,comment:raw}`；每个生成对象自身补collected_at。合计不得超过请求max_records(1..100)，不截断。旧三平台输出与限制不变。
- build_comment_batch兼容既有调用名，对ZHIHU路由到独立纯mapper；新records允许POST/COMMENT。Source URL只是源声明，仍UNVERIFIED，不能直接变成已认可商机或收件人。

## Task 1: 纯候选映射（backend agent）

**Files:** 新connectors/zhihu_mapping.py；connectors/candidate_mapping.py仅ZHIHU路由；tests/test_zhihu_candidate_mapping.py。
**Interface:** `map_zhihu_record(raw, collector_version, query) -> dict`返回既有CandidateRecord shape，失败复用CandidateMappingError（避免循环：子模块内部局部import或由调用方统一转固定错误）。build_comment_batch仍调用validate_candidate_batch(payload,now=now)。只接受上文精确字段关系，未知身份/null；raw不修改、不记录。

- [ ] RED：回答/文章同ID区分；原文及评论body/时间独立；匿名hash不冒作者；错误URL/类型/关联/父ID/未来时间拒绝；视频无正文不造POST。
- [ ] 最小实现独立mapper与dispatch，不修改其它平台解析规则或启用采集器。
- [ ] 固定Python运行新文件及旧mapper中平台拒绝/关键兼容目标，不全套；提交自身文件，私有sdd报告。

## Task 2: 停写JSONL到候选对象（root）

**Files:** app/collection_output.py；新tests/test_zhihu_collection_output.py；旧test_collection_output.py仅更新ZHIHU不再属于拒绝列表。
**Interface:** `read_collection_output(path,'ZHIHU',max_records)`沿用签名，返回上述完整有界rawlist。按(type,id)关联；源内容及评论last_modify_ts分别进入collected_at；其它平台不变。

- [ ] RED：真实固定字段的两类同ID主帖/评论、孤儿/冲突、合计上限、无正文视频、未知时间、路径/文件安全复用。
- [ ] 最小分支扩展读取器，不复制文件系统安全层；独立内容键，先完整校验再返回。
- [ ] 一次新reader→真实mapper→CandidateBatch合成联验和受影响原reader定向检查，不启动PG/平台/构包。

## Task 3: 独立审核与接续

- [ ] 非作者审核base到完整源码；有具体问题才加最窄反例，一波修复后差量审核。
- [ ] 唯一证据写此计划，更新任务书短链接并正常推送main核SHA。知乎仍未启用；后续必须完成固定依赖受控patch、同context本人身份核验、登录和四平台opt-in策略、客户端/monitor接线与真实平台验收；不省略公开网站来源或完整Goal其它门禁。

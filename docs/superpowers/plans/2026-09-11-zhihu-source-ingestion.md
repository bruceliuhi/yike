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

- [x] RED：回答/文章同ID区分；原文及评论body/时间独立；匿名hash不冒作者；错误URL/类型/关联/父ID/未来时间拒绝；视频无正文不造POST。
- [x] 最小实现独立mapper与dispatch，不修改其它平台解析规则或启用采集器。
- [x] 固定Python运行新mapper及reader到正式DTO联验，不全套；旧mapper分支未修改，由独立审核核对，不将其声明为重新实跑。提交自身文件，私有sdd报告。

## Task 2: 停写JSONL到候选对象（root）

**Files:** app/collection_output.py；新tests/test_zhihu_collection_output.py；旧test_collection_output.py仅更新ZHIHU不再属于拒绝列表。
**Interface:** `read_collection_output(path,'ZHIHU',max_records)`沿用签名，返回上述完整有界rawlist。按(type,id)关联；源内容及评论last_modify_ts分别进入collected_at；其它平台不变。

- [x] RED：真实固定字段的两类同ID主帖/评论、孤儿/冲突、合计上限、无正文视频、未知时间、路径/文件安全复用。
- [x] 最小分支扩展读取器，不复制文件系统安全层；独立内容键，先完整校验再返回。
- [x] 新reader→真实mapper→CandidateBatch合成联验和受影响原reader定向检查；固定Windows HOST_FILES包含新mapper，仅静态清单验证，不启动PG/平台/构包。

## Task 3: 独立审核与接续

- [x] 非作者审核base到完整源码，复用定向证据，无阻断发现。
- [x] 唯一证据写此计划，更新任务书短链接，主线推送结果以任务最终回执为准。知乎仍未启用；后续必须完成固定依赖受控patch、同context本人身份核验、登录和四平台opt-in策略、客户端/monitor接线与真实平台验收；不省略公开网站来源或完整Goal其它门禁。

## 实施与验证

基线 `e8ddd70`，计划 `ce1e76d`，reader `edab35f`，mapper `cc519b5`，Windows固定清单 `e9e755c`。

- 新reader初始3失败/7通过；实现后9通过/1联验暂未选中（0.04s）。原reader受影响文件77通过/1Windows原生junction检查跳过（0.20s）。
- 新mapper初始因模块缺失无法收集；初次合并reader联验19通过。预接线补测暴露6失败：空视频评论被拒、bool/浮点误判未知、非字符串类型泄露异常；修复后新mapper+reader包含正式CandidateBatch联验共25通过（0.15s）。
- 固定Windows打包清单遗漏新模块的断言先失败，补一行后仅该项1通过（0.03s）；没有执行构包。Python编译与diff-check通过；没有全量测试、PG或前端测试。
- 独立整批审核 `e9e755c43a02c069f6f4a30099130fbe4dee1b04` GO，包含固定portable清单；无阻断发现，没有重复测试或构包。全部输入是基于本地固定依赖字段的合成数据；无真实知乎账号/浏览器/网络/平台、生产、Windows运行或客户验收。商业代码授权已由AUTHORITY确认，不重复索取；平台访问权限仍独立按运行门禁处理。
- 后续执行接线参考私有sdd/zhihu-source-feasibility.md。旧三平台执行模式、开关、账号及服务端授权不变；本批不能用于宣称知乎已可搜索或发送。

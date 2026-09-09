# V02-02C 原始评论到候选契约 Implementation Plan

> **For agentic workers:** REQUIRED: Use `subagent-driven-development` if the current harness supports helper agents; otherwise use `executing-plans`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 执行已认领02C及已ACK的02A原始字段映射，接通抖音/B站现有原始评论信封到正式候选校验，保留原文、匿名作者、未知时间和父上下文；不冒充真实采集/上传完成。

**Architecture:** 新增独立`connectors/candidate_mapping.py`，不改旧NormalizedSignal、服务端合同或共享入口。公开`build_comment_batch`接收明确服务端平台枚举、原始信封列表、request/profile/strategy版本、调用方execution声明、collector_version、可空query及可信now；构造candidate-upload-v1后调用现有`validate_candidate_batch`。不生成身份、租约或APPROVED状态，不改变能力登记。

**Tech Stack:** Python 3.11、stdlib、已锁定Pydantic/候选校验器、pytest。基线6780582，规范为[02A合同](../../contracts/V02_CANDIDATE_INGESTION.md)及[接收差异](../../handoffs/V02-02A_MAC_TO_WIN.md)。这是已确认接口的实现步骤，不增加产品流程或重新设计R4。

## Chunk 1：原始映射及正式消费

### Task 1：独立映射实现与定向反例

**Files:** 新增`connectors/candidate_mapping.py`、`tests/test_candidate_mapping.py`。不修改`connectors/__init__.py`、旧解析器、pilot、迁移或renderer；根代理登记任务书与审核证据。

- [x] 测试先行，先以明确断言证明新入口缺失；两平台使用已有合成格式fixture，不称实际采集。
- [x] `build_comment_batch(*, platform, raw_records, request_id, profile_version_id, strategy_version_id, execution, collector_version, query=None, now)`返回正式冻结CandidateBatch。仅DOUYIN/BILIBILI，不猜别名；raw_records必须列表且0–100条，坏条目整批拒绝，不静默丢弃。
- [x] 每项为显式`content`主帖/`comment`评论mapping。从原始字段读取，不先调旧normalize函数。ID使用既有规范数字字符串或可无损转十进制的严格正整数，拒绝bool/float；评论所属主帖核对和已提供URL的对象定位沿用现有平台规则；缺链接才由已校验ID构造既有标准回链。已提供但不安全/错对象链接拒绝，不能清洗后替换。任何缺失可靠评论ID不猜造。
- [x] 保留正文/父正文原Unicode与首尾空白；可用正文别名按现有平台字段定义读取；存在互相冲突的同义字段则拒绝，不选择一个静默丢掉。title/公开作者可空；title与desc可能含义不同，优先保留title、缺失才采用desc，不要求二者相等但校验已提供类型。不把昵称、主帖作者或内部哈希猜成评论公开ID；作者不同ID命名空间不当同义字段比较，Douyin按sec_uid→user_id→uid、Bili按mid→user_id选明确公开标识，值不trim且已有字段类型错误拒绝；creator_hash仅是旧实验字段，不成为新的公开身份。
- [x] 发布时间只取评论create_time/published_at，未知保留null；collected_at必须由原始记录提供。时间接受严格整数epoch秒或精确UTC文本，拒绝bool/float/非法时间，不回退父时间或now。未来/先后关系交正式校验。别名冲突按转换后语义判定。
- [x] parent ID由平台现有父ID字段读取，明确0哨兵→null；有父ID但缺正文保留ID和null。父正文/公开作者/发布时间/链接仅来自明确parent_*字段，不继承主帖或子评论值；有父正文但缺关系ID拒绝待补证。父URL核对父评论定位，关系自指及时间顺序由正式合同拒绝。
- [x] 输出白名单不夹带原始payload、Cookie、内部哈希或自报权限；normalizer_version使用固定可版本化标识。异常只给稳定错误码，无原文/URL/输入值和异常链，调用方不得打印payload。
- [x] 用正式校验器覆盖批内重复/同源版本冲突、execution坏声明、0条空批、100/101边界、输入不变、重复构造指纹稳定、观察变化不改内容版本、正文/父上下文变化改版本。
- [x] 先运行`./.runtime/venvs/win-device-review/Scripts/python.exe -X utf8 -m pytest -q tests/test_candidate_mapping.py`观察RED，再实现并GREEN。不做网络/DB调用；纯包原导入契约保持。

## Chunk 2：消费检查、交接与集成

### Task 2：根代理消费验证及独立审核

**Files:** 根代理可新增`tests/test_candidate_mapping_boundary.py`补消费反例；修改唯一任务书及Win审核记录，不改变Mac认领。

- [x] 独立从原始合成信封调用映射→正式JSON往返验证→source_identity/content_version/batch_fingerprint，验证不绕过正式校验、不会伪装成已授权或已复核。
- [x] 定向回归：`tests/test_candidate_mapping*.py tests/test_candidate_contract.py tests/test_source_capabilities.py tests/test_connector_parsers.py`，以及旧解析相关测试；按实际结果记录，不为此重跑Windows打包/全PG。
- [x] 检查wheel包含新增模块且旧纯包入口不加载app/数据库；只验证包内容，不把wheel当sidecar或平台就绪。
- [ ] 先独立规格复核，再独立代码/架构/质量复核；修复及复审后正常提交main，fetch保留Mac并发提交、按影响复核再push。绑定候选SHA和证据，02C仍IN_PROGRESS。
- [ ] 后续接入真实原始采集输出/02B上传及xhs/zhihu/web、主帖/网页适配；本轮仅完成现有两平台评论路径的正式消费准备，不以合成fixture解锁真实capability。

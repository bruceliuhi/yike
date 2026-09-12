# B站内容与作者链接端到端执行计划

> **For agentic workers:** 使用执行计划/TDD；原生运行时、TS链路与Python主机按文件互斥分工，固定提交后一次独立整批审核。

**Goal:** 在原四平台搜索和公开社区能力之外，真正接通B站视频／作者链接的采集、正文及评论候选、原确认策略绑定、一次任务／周期任务。完整V0.2和其他三平台链接执行不被替代。

**Architecture:** 新显式服务器模式声明B站links能力；主进程从已确认快照生成上一批严格链接计划，逐目标启动固定Python host。host/worker校验目标并包住受控runtime的collect_links入口，同浏览器本人身份逐请求核对。只在清理子进程完成、终态与有界文件一致后映射POST/COMMENT并签名上传；原文不是人工核验结果。

**Tech Stack:** 既有Electron/TS、Python3.11、Pydantic、固定MediaCrawler PIN及追加patch；不升级依赖、不加采集代理、不部署、不真实外发。

## Global constraints / 固定接口

- 上游PIN不变：439509782cc2991c8ef7648e178d5847b0545798。只加新patch，更新锁/治理摘要；既有patch不改。不得操作共享runtime副本；使用本任务独占 `/tmp/yike-native-links-vendor.l75kHY/runtime`（已从PIN应用前三patch，未装依赖、未运行平台）。
- 本批原生links仅BILIBILI；其余平台的search不变。不得声明四平台links已实现，不做任意URL抓取。识别用上一批parse_native_collection_link/parseNativeCollectionLink。实际B站video目标还须满足已有映射BV格式；格式或响应身份不符即失败，不猜测别的内容。
- host协议仍windows-source-host-v1，新增可选字段native_link（严格四字段platform/kind/external_id/canonical_url，必须与parse canonical_url逐字段完全相同）。有native_link时仅BILIBILI、query必须null、expected_account_public_id必填；无该字段沿用旧search协议，不接受显式null伪装扩展。
- collect_windows_source增加native_link=None参数；有目标时上述约束在任何进程创建前核对。固定CLI detail用 --specified_id=<canonical_url>，creator用 --creator_id=<canonical_url>；不传--keywords，不开shell。worker重新核对固定参数和平台，不能从未受控运行入口兜底。
- worker的账号guard增加entry_method关键字（默认search，唯一另一值collect_links）；非search mode必须wrap collect_links入口与原client.request。身份变更/风控必须粘滞失败，即便内部捕获异常也不能返回成功；安装/退出必须还原类方法。
- B站runtime.start仅把detail/creator交给collect_links；该函数不调用旧无界作者遍历或profile/media路径。detail只读一个video，creator只读一个作者视频列表页且取最多max_contents个不同内容。creator每个实际View.owner.mid必须等于请求作者；detail View.bvid必须等于请求BV。请求失败不吞成空集。不持久化额外作者私人资料。
- 全任务既有100records/900seconds不放宽。每个host link子调用含POST＋COMMENT共同计数；max_contents=min(5,max(1,max_records//2))，detail恒为1；每篇comment上限=max(0,(max_records-max_contents)//max_contents)。零comment预算不发评论请求。所有正文先入有界结果，再评论，超限不是静默截断。
- host逐目标必须共享父任务总预算和截止时间，目标数大于分配records预算先拒绝，不默默跳过目标。query=null不伪装关键词；完整原始链接保留已确认任务快照。
- read_collection_output新增keyword collection_mode='search'；新detail/creator仅B站，读取对应前缀的contents/comments并返回POST（{content}）与COMMENT（{content,comment}），总量<=max_records；其他模式文件不能混作本次成功。旧search语义不变。
- build_comment_batch对B站{content}新增POST映射，复用严格ID/URL/时间和正式CandidateBatch；其他现有raw COMMENT不变。不开放自报审核／发送权限。B站链接可用裸原生URL，不涉及修改XHS候选URL秘密规则。
- 固定新部署模式four-platform-public-bili-links-monitor-v1继承project-monitor的所有搜索／公开板块；仅另开B站links。foreground和monitor support响应新增native_links:['BILIBILI']；旧模式不返回。客户端AVAILABLE新增linkPlatforms:['BILIBILI']可选，不能由renderer自报。
- 新模式不开research执行，不变更确认发送。Windows/实际平台/UAT必须另取真实证据。现有安装候选不随本批自动重构或追认。

## Task 1：受控B站运行时（独立runtime Agent）

所有权：新增vendor/patches/mediacrawler/0004-yike-bili-links.patch，更新vendor/mediacrawler.lock及必要配套治理manifest；新增tests/test_bili_link_runtime.py。只编辑独占runtime的必要B站core/main用于生成patch，测试可从应用patch后的实际函数执行，不用全文字符串存在断言冒充运行。

- [ ] 先写离线行为RED：detail/creator实际View身份核对、有界单页、正文保存、comment0不读、评论共享上限、异常不吞、main终态识别对应POST输出。
- [ ] 实现collect_links，沿用标准可见浏览器和既有client方法。main的成功检测对B站detail/creator含contents，search不变。
- [ ] 生成追加patch、按真实文件SHA更新治理摘要；目标验证patch从PIN依序可应用、锁校验和离线runtime行为。无安装平台浏览器或请求平台。

## Task 2：主机及正式候选（CodexiMac）

所有权：app/windows_collection_host.py、app/windows_source_driver.py、app/platform_collection_worker.py、app/collection_output.py、app/windows_portable_inventory.py、connectors/candidate_mapping.py；对应tests/test_windows_collection_host.py、test_windows_source_driver.py、test_platform_collection_worker.py、test_collection_output.py及candidate mapping定向测试。

- [ ] RED固定host目标/身份/模式字段、CLI边界、guard入口和粘滞失败、真实JSONL→POST/COMMENT映射及计数。
- [ ] 新native_link目标通过上一批纯解析严格核对；portable HOST_FILES加入pilot/native_collection_links.py；worker直接脚本模式使用明确的同项目文件路径加载该纯模块，不从用户PATH发现代码。
- [ ] 仅实现上面固定模式、预算和输出接口；保留旧query调用字节与行为。旧search全部定向回归。

## Task 3：服务端声明与客户端接线（客户端 Agent＋root服务端）

TS所有权：pythonCollectionDriver、foregroundCollectionController、shared foreground/monitor schemas、renderer foreground/monitor/task eligibility及对应tests。Python服务端由root修改pilot/foreground_collection.py和monitor_collection.py等实际support实现及定向tests，接口严格按上方native_links字段。

- [ ] RED：旧支持不启动links，新支持只启动匹配B站；目标query=null/四字段/身份传入host，全目标预算共享且验证结果query=null；一次/monitor可走同一确认链；错误范围未spawn。
- [ ] renderer仅依据main AVAILABLE linkPlatforms标记B站links支持；其他平台仍搜索；保留完整配置摘要/连接身份/取消/恢复/上传约束。
- [ ] 新服务器mode继承全部旧搜索与public-source范围，仅新增B站links的once/monitor，无research和匿名native links。

## 最终验收与边界

- [ ] 相关单元／真实文件边界测试与TS类型检查；尽量复用既有回归，不重复整仓构包/模型样本。
- [ ] 整批非作者审核绑定SHA；修复后定向复核，正常同步main。
- [ ] 未有Windows＋真实B站账号读取前，明确“执行代码已接通、真实平台待验”，不声称新增客户机会或正式上线。

## Evidence

尚未实施；上轮输入批28309ac已推main。本批完整功能未完成，不能因局部test通过开放capability。

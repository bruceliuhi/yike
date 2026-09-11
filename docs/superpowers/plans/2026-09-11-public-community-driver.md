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

### 客户端接线（当前工作片）

沿用上述批准方案，新增匿名 `publicBinding`，不创建虚构账号或连接记录。客户端只有从已认证设备scope取得显式来源能力，才把公开网站显示为V2EX近期主题；用户确认的配置包含固定publicSource，来源/设备变化须重新核对。只允许单次关键词采样、共享上限100条/900秒，不开放历史、全站、评论及公开社区持续监控。既有四账号平台与匿名来源可同设备串行，共享记录预算。

主进程在服务配置就绪时创建同一foreground controller，不再等待Python/profile；原生bootstrap随后只安装native配置，不重建正在运行的controller。匿名来源复用原START、CLAIM、候选上传、FINISH和原请求恢复；已领取过的来源不可重采，取消发生在平台间时不启动下一个来源。来源driver逐任务核验确认标识，单一controller内共享60秒请求冷却，失败也不立即重试；不是跨设备/IP全局配额保证。

同时修正新建单次任务把定时配置带入确认快照的问题：新once准备为schedule:null，monitor保持原计划；旧已保存快照与哈希不改写，不兼容旧草稿须重新准备并主动确认。界面复用现有任务向导和策略确认区，不重做设计。

本片验收以来源/设备确认、独立于native运行时、混合共享预算、取消与复核证据传输为重点。组合测试中的服务回执和来源响应为替身，不能写成真实HTTP、PostgreSQL、平台或客户端到端验收。默认部署模式仍不修改；只有配套客户端/服务端版本通过真实业务验证后才能发布该能力，旧客户端不能消费新增support字段。

源码 `148ddba46169b1f5eb18fcbc048a88fd53863186` 已通过非作者 `material_reference_architecture` 绑定SHA的独立审核，Ready to merge: Yes，无阻断P1/P2。主Agent最终运行12个定向文件211 passed（6.53秒），TypeScript `tsc --noEmit` 与diff check通过，未构包或运行全量测试。测试文件为foregroundCollectionController、publicCommunityDriver、collectionWorker、monitorCollectionController、portableBootstrap、publicCollectionRenderer、foregroundCollectionRenderer、researchStrategies，以及ui下strategy-confirmation、task-desktop-execution、task-wizard、task-domain。

包含真实controller→worker→driver组合，在替身边界验证START→CLAIM→读取→上传原文及来源→FINISH的顺序；另验证renderer新native单次配置可被controller接受、public/mixed设备确认、平台间取消、缺source但重算hash仍拒绝、60秒冷却。最初controller新增用例3项失败后实现通过；新增来源冷却用例先失败后通过，renderer与once新配置亦有RED→GREEN。没有把这些替身回执算作真实数据库或平台证据。

下一片优先复用现有空库部署/执行HTTP测试设施，在隔离真实服务与PostgreSQL验证配套版本的确认、START、候选入库/详情与拒绝边界；再接Windows、真实平台及跨行业效果。不重复实现已接UI/执行协议，不回头构建无域名的正式包。完整Goal与MP-03保持进行中。

### 真实HTTP与PostgreSQL接续（2026-09-11）

验收脚本 `7891cc8f640d1c1d30b0dcd339df7366c8e49aed` 复用现有隔离fixture；生产代码仍为 `148ddba`，本片没有修改运行逻辑。独立临时PostgreSQL 16使用tmpfs及仅loopback端口，与现有三个PG容器隔离。运行真实迁移、完整grant_runtime清单与受限角色（非superuser/非bypassrls），以普通 `build_runtime_app` 启动真实Uvicorn socket；不使用TestClient、替换策略resolver或伪造服务回执。

Node 24运行实际service client、执行/候选签名与加密journal、foreground controller、worker及公开driver。经真实HTTP准备/确认策略、读取来源能力，完成START→CLAIM→候选上传→FINISH，再经候选列表与rawEvidence接口逐条核对原文、发布时间、来源版本及观察归属。重建controller后原START不重复读取来源；同租户其他用户及外租户候选列表均为空，未创建平台账号、模型评估、商机或外部消息。

限定结果：

- 合成来源模式：最终1 passed / 3.62秒；使用同一driver，仅其fetch返回1条明确合成PAGE。
- 显式 `YIKE_PUBLIC_COMMUNITY_NETWORK=1`：默认global fetch一次读取固定V2EX端点，36条未判定PAGE实际入库并逐条接口回读，1 passed / 6.00秒。关键词“AI／的”仅用于技术链路取样，不是有效商机筛选；36条不能计作高意向线索。未重试外网请求。
- TypeScript检查及diff check通过。初次运行曾因Node测试尚未落盘而失败，不是产品缺陷；随后tsc发现测试ApiResult缺少显式收窄，补4处固定脱敏失败分支后用合成来源重验。真实网络运行的成功路径和生产代码未改变，未为测试类型修正再次请求平台。

复现入口为 `tests/test_public_community_http_postgres.py`；要求独立测试库的两个YIKE_IDENTITY_TEST数据库变量和Node24位置，凭据只在进程环境传递，不写文档或仓库。`71867b8`增加迁移fixture之前的专用本机库限制：两URL必须指向127.0.0.1上的yike_public_flow，避免误连其他库。只有显式NETWORK=1才访问外网；默认全量测试未配置独立数据库时跳过，跳过不算验收。本轮指定运行均没有跳过。

证据边界：服务使用测试用户、临时dev login令牌和已注册设备fixture；Node端identity prepare及加密保护器是测试装配，数据库连接以SET ROLE验证权限。没有验证生产登录、真实OS keychain、HTTPS、Electron窗口渲染、Windows安装或客户使用；不得将接口回读称为Windows界面验收。下一步接同版本普通客户端窗口/Windows与部署验收，并继续公开来源持续监控、更多站点及实际行业需求质量验证。

非作者 `material_reference_architecture` 分别对网络验收脚本`7891cc8`和最终专用库保护`71867b8`只读审核GO，无阻断P1/P2，未重复网络或测试。全授权脚本内容真实执行，但不新增psql元命令入口验收成绩。临时服务已退出、专用tmpfs PG容器已移除，本轮候选/测试账号及临时加密日志均已删除，不可恢复；现有三个PG容器与用户数据未操作。仓库仅保留脚本与脱敏统计，不保存真实帖子正文或认证信息。

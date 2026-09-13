# 启动页任务记录短暂忙碌恢复

范围：用户既定自主推进及验收优先要求，串行main、一批定向验证及独立审核。只修启动页重复出现的任务记录首次加载失败，不改任务提交/取消/恢复或账号主进程的互斥保护。

证据：实装1549c18连续真实新任务都在确认页出现“本机原请求尚未读取成功”，手工只读刷新后恢复。代码deviceIdentityController.withAuthenticatedSession在设备准备或其它鉴权操作中返回BUSY，executionController将该结果原样交给LIST/RESEARCH_LIST。useDesktopExecution.refresh把一次BUSY立即视为读取失败，并且没有自动再读。未抓取本机真实IPC负载，因此BUSY是源码与可复现合同路径，不声称已记录每次实机失败的具体回执。

设计：仅LIST/RESEARCH_LIST收到明确BUSY时，按250/500/1000ms等待后再读，最多各4次。每次由原call校验当前账号scope及响应合同；账号切换/卸载后不再发送旧查询。FAILED、SIGNED_OUT、SESSION_CHANGED、网络异常、未知、超时等不自动重试；读不全仍阻止新建，不能假设空历史。START、CANCEL、RECOVER、RESEARCH_START、RESEARCH_RECOVER完全不使用该等待逻辑。选择局部读重试而不是删除鉴权互斥、假定空列表或跨页面重写队列。

- [x] 新增desktop/tests/ui/desktop-execution-list-busy.test.tsx：真实hook/合成服务回执，RED 3失败5通过；两类BUSY立即报错，持续BUSY只读1次。
- [x] desktop/src/renderer/pages/tasks/useDesktopExecution.ts增加私有列表调用，原状态/防重/普通变更通路不变。
- [x] 新用例10项与既有TaskWizard17项共27通过/3.97秒，typecheck通过；独立审核GO。与后续实际体验修复合批构一个新Windows候选，不逐行构包。
- [ ] 新候选构包/安装及首次读取的实机验证；当前运行的1549c18尚未包含本hook改动。

研究主线另有独立真实失败：90f58d1任务ce4f5bda-4290-4169-98e2-a9598e714e33于17:54:05从实装UI创建、17:54:28启动、17:55:02 STOPPED/no_verified_reads。4MODEL/2SEARCH成功，1次V2EX READ连接失败，0原文/候选。模型实际收到新增买方与来源切换指令（持久MODEL四次payload固定标记均存在），但两个实际查询仍偏AI品类，随后建议“后续补充其它来源”而提前结束；未证明改进效果。暂停同类盲测，不重复旧任务或升级为试用通过；下一步需针对工具返回与实际查询选择验证，原文/候选/草稿/反馈和三业务门禁仍未完成。

独立review_buyer_discovery本批GO，绑定hook blob `c66c53bc08ed8adb33fdf4afece2cb3bff3c1087`、test blob `07b8dfbc7d5eea0ea826b2e1511a454f2fb4364a`。等待计时器不主动取消，但在当前最多1秒等待后检查旧scope并退出；不会继续旧查询或把迟到状态写入新账号。本批不改变主进程鉴权，审核/测试不等于已实装。

客户端终态核查：研究区已显示暂停，但同页原采集状态仍待执行；进入“查看原文与分析”后实际待复核列表0条，没有生成草稿或反馈。保留状态不一致、覆盖面板过时/时区及技术说明冗余为同一个后续Windows体验批次，不以任务结束视为完成。下一轮研究诊断优先做一次“具体买方业务/寻源短语”和现有品类种子对照，保持同一真实画像、服务版本和预算；明确区分人工调整查询的诊断与客户只描述业务的自动体验，不能以人工挑选来源证明全自动达标。

## 18:13 研究状态展示合批修复

main已同步至a0f30e4，工作树原先干净。生产只读复查ce4任务仍STOPPED/no_verified_reads，研究容器已无运行项，没有重放。实际已安装页面仍0线索；两次Computer Use输入均检测到用户操作，已暂停界面输入，没有创建对照任务。

已定位NativeCollectionTasks把采集入库账本PENDING当研究当前状态，并对研究调用普通SearchCoverage。现研究详情仅由原ResearchProgress展示真实研究状态，不查询普通覆盖；列表研究行链接至研究进度，折叠的平台状态明确标为入库状态。普通采集、取消/未知警告、权限和恢复不改。no_verified_reads改成无可核对原文的简洁解释，不说没有市场需求；若同时有UNKNOWN，原核对提示仍覆盖新建建议。

测试最初研究夹具的汇总计数不一致，修正后RED明确3项预期失败/34通过；实现后37通过/3.50秒，补齐夹具capability类型后typecheck通过。独立review_buyer_discovery GO，绑定NativeCollectionTasks blob d9d8ece8984d85ab4b87e5c9b04f0aa907cf8997、presentation f1bfece73d4e9e015b6d5dd61daa21e70943bdb1、两测试406690605be02f4a8bb6c331c662593cf897d652/a36103eeaca9da385ede12b40ab3c159f072cb13。此刻尚未新构包或安装，真实搜索词对照、原文候选/草稿反馈仍未完成。

## Windows统一候选ba15af7（封装中，未安装）

产品ba15af7cc2205654dbe0aa360eef63608103cbcc已推main，包含a0f只读BUSY恢复。复用已干净的D:/yk-connect/lf-source隔离工作区冻结该提交，没有重装依赖。内置运行环境43727已exit0，独立运行/完整性检查1通过121.40秒，保留D:/yk-connect/portable-ba15af7-relocated。

唯一Forge封装61466仍运行，实际node22080及nuget36648持续读写；不得因等待无新日志重复构建。输出D:/ykh913，临时根D:/ykht913、D:/ykhx913、D:/ykhs913。桌面650源码manifest fc31bbf6f3786f2f716cd9f0aae8ecf54d0d5ee50fc5c102b730bd302c681575；已生成ASAR 3664ec2cbab4bad7df5d19ef9f938901d623af759344dac0f8000121b596ccdd。40个renderer文件与固定构建目录逐字节一致，main正式HTTPS和载荷pin核对通过，载荷manifest ab59027cce0966df63a500f758030e2fae625cdfcc32bbe309162f74083a7454。尚不能把中间ASAR写成EXE封装成功，需等待61466终态、核对最终产物，再安装/实机复查。旧安装1549c18未关闭，用户输入期间不抢窗口。

研究诊断追加：只读读取ce4首次MODEL已持久上下文，10个query_seeds确实全部是AI软件定制品类/服务商词（例如AI软件定制开发、全国AI软件开发、企业AI定制开发服务商），意向信号为询价/比较/替换，60天、无排除词。上游搜索建议系统提示本已有买方问题/交付物要求，不能把“未生成买方表达”误说为完全缺指令；下一次仍按同画像/限额的人工短句对照查影响，不再盲加提示词。此处无新模型/搜索调用、无候选/草稿/反馈。

## ba15af7实际安装与新默认额度接续

Forge61466已exit0，最终EXE D:/ykh913/make/squirrel.windows/x64/YikeAI-Setup.exe，642855424字节，SHA256 6d29ca53a5a6ced7e052bc897091609a081dceae42dbf4df10970234a13f38ee，NotSigned。原生UI放弃测试草稿并关闭旧版后，同包已启动新版。CIM运行路径为C:/Users/bruce/AppData/Local/YikeAI/app-0.2.0/YikeAI.exe；Computer Use报告应用缓存别名，两路径读取的ASAR都与上述候选3664ec2c一致，不据此推断丢失数据或重复安装。Setup/Update进程已退出，新GUI保持运行；PowerShell Start-Process -Wait的32598仍等待子进程树，尚未取得该会话exitcode，不重启安装器。

实机已确认登录、小红书连接、五个历史任务保留；列表改为查看研究进度，ce4详情显示无可核对原文，不再有普通PENDING/旧覆盖。已填写“验收-AI定制买方短句-0913”及10个买方短句，未选择来源/提交/开始。之后检测到用户输入而暂停，没有新增研究调用。

用户新增要求默认10万搜贝：方案仅将defaultResearchSettings.maxSoubei改为100000（协议现有上限1000000），保留旧任务/手工额度、所有实际资源上限和估算/确认绑定；不新增计费、充值或模型预算。新增默认/面板/旧草稿测试，夹具改用独立owner避免清理后的旧key复活保护；RED3失败1通过后，默认、用量、模板和动态UI共32通过/4.99秒，typecheck通过。独立review_buyer_discovery GO，绑定researchUsage blob 943e3a20bed75e2ab9566cfcfc94825f80cbf580及测试bb5be761c801c4be4e28598b93d15dbb6fcc2ee6；此改动不在刚安装的ba15af7中，下一候选需包含该差量，不把手填额度追认为新版默认体验。

main并发整合：e66587d推送被正常拒绝，fetch发现Mac来件2b643ca把同默认设100万；普通merge保留双方检查和注释，按本任务用户10万示例统一为100000，并同步来件测试期望。受影响sourcePlan/default UI差量9通过2.54秒，未重跑不变的用量/模板整套。没有可直达Mac的本地任务入口，主干记录作为交接；勿再分别实现不同额度默认值。

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

## 18:52 新版实装与买方短句真实对照

main正常合并7842532宣传文件后推至3de1b35d5d26ca171bfdfcc32f360f7116ccfd3c；冻结同提交到既有干净LF工作区，不重复既有产品测试。载荷24988 exit0，实际隔离运行检查1通过187.62秒；Forge30715 exit0，同源651文件manifest 19e2eb37e1fdf50f1fad4fad2d6cac37db0d245e7fb248d43212134cd82d5516，构建前后不变。唯一新EXE为D:/yki913/make/squirrel.windows/x64/YikeAI-Setup.exe，642852864字节，SHA256 090f9e4182f4348720630684ffc22dbf8b5f506cb1d11227cddfaf3f69377685，NotSigned。40个renderer文件与冻结构建一致；main正式HTTPS/载荷pin通过，payload manifest 7566abf3a40d5539dde4019e0b1078ce8eb6e39688841a783560bf99e8bb27cb。

已正常关闭ba15客户端并清除本轮未启动测试草稿（用户已授权测试草稿无需保留），旧安装等待32598取得exit0。新安装90798的Setup/Update进程已退出，GUI正常运行；该PowerShell -Wait仍随GUI子进程等待，不重复安装。实装app.asar为536c1c33e34a72865111179fc07f8aa688da1d8fb61d94fb01a94e771f8003b8，与新候选一致。实际窗口45025618，登录/小红书连接保留，新建任务未经额度编辑即显示100000；确认页沿用同值。原文状态修复仍有效，首次本机任务记录未再报读取失败。服务器customer/research仍90f58d1，健康、HTTPS readyz200；本批仅桌面差量不重新部署。

真实UI新任务“验收-AI定制买方短句-0913”，task 980dc5e6-f6f1-41a5-b891-699556f3132a，run cac912ab-7746-4045-b16e-ec0f6bfc3e48，generation1。同一AI软件定制画像、公开网页自主研究、近60天；仅人工配置10个买方短句，与旧品类词对照。快照现场确认20来源/15分钟/20模型及100记录/900秒不变，搜贝上限100000，资源上限估算55。策略确认、估算、创建和开始均由真实客户端操作，非后台脚本创建。

18:51:15起执行，18:51:58 STOPPED/no_verified_reads：6 MODEL、5 SEARCH成功，1 READ失败connection_unavailable，0成功原文/候选，已无活动研究容器。真实查询已采用“企业知识库 找人开发 外包”“智能客服 找开发团队 外包 需求”等，证明人工种子被使用，但结果仍主要供方/教程。唯一READ为https://www.v2ex.com/go/outsourcing，失败后有4次成功搜索（含电鸭入口），没有读取其它站就输出空pages；模型总结自称6次搜索与账本5次不符，以账本为准。客户端真实显示研究暂停和无可核对原文，不把0READ当市场无需求，不重放原任务。

这次对照否定“只换买方搜索词就能恢复完整流程”。只读源码定位：ResponsesBridge仅第一次MODEL强制工具，之后允许终稿；Codex正常turn.completed后broker因无成功READ记失败，不是预算/时长/取消停止。已有指令包含相关入口早读、受阻换站，不能继续当成单纯缺少提示词。下一步先用已持久回执和受控测试定位研究规划/提前终稿的执行约束，保留合法零结果、权限/未知和原限制，不盲增提示或强读无关页。研究价值闭环、草稿反馈、三业务及用户认可候选仍未通过，Goal ACTIVE。

### 18:58 主线来件与发布风险交接（给CodexiMac）

本轮记录提交14262c8推送时发现并行来件9996dff/bef0d7d/72b43f5。已正常合并，保留UTC报价日期/客户端前移时钟兼容；定向后端报价16通过0.47秒、UI报价与默认21通过19.12秒。独立审核对72b43f5新增fallback NO-GO：time导入为函数却调用time.monotonic；broker返回时已撤销许可；硬编码AI查询违背多行业确认画像；任意读页机械ASSESS/q1并覆盖原runtime_failed。该fallback仅在没有任何搜索时触发，也不能解决本次5次搜索后的失败。

已仅撤回新增50行，worker精确恢复3de1b35基线blob 72388b96a2f6d9c2a4c89669a445d3175e36da97，不移除许可撤销、不另添兜底。独立差量GO；服务端报价blob 9796befd01bfba1181c5a1014e30eabae141cd0b、客户端报价cf93d6bde7471edecfcec1977ccb9a9f4e38302c。服务端仍验证签名及精确300秒时效，前端时钟兼容不放宽执行授权。

18:56只读发现另一端已将customer更新到72b43f5：容器59ee326ee8912886bc7b7c6088c071e5924ddee773269048c397b88b164d5865、镜像7384b51270ccb162fc72eb18f2dc9c66de1ff8d6f2a00e521366c1a4c26d0ed8，worker SHA256 fd32f91171843b119172d12b4fcd8efdf5130732b4331537c3d4eccc81c52f62；broker仍d6fb62ee/6b692bd1（90f58d1）。Win未覆盖此次并行部署，**线上尚未包含本次撤回，下一步先按共享发布锁/当前容器/活动任务核对后安全更新customer**。本机窗口45025618仍安装3de1b35，不包含新报价客户端差量，不把旧包标成最新main。当前没有可直达Mac的本地任务入口，以上作为主干交接；请勿重复部署72b43f5或重加该fallback，不重放已停止980dc5e6。

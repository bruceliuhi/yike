# 自主研究首次动作约束

用户已授权范围内自行细化开发，按验收优先串行main、一批定向验证和一次独立审核，不另起确认或重复构包。

真实前提：47eb746客户端任务e90292be只完成一次MODEL，两个工具均存在但tool_choice=auto，模型把“需要先搜索”作为json_schema最终结果返回。没有SEARCH/READ；旧任务不重放。

目标：已确认自主研究的首次请求须选择已允许的搜索或读页工具，不只返回计划；后续可正常完成、报告无结果或访问失败。保持调用/来源/时间预算与账本、取消及未知边界。

设计：ResponsesBridge增加内部布尔require_initial_tool，默认false；仅受控且绑定研究上下文的worker启用。首次实际准入MODEL设置tool_choice=required并由原账本持久化同一payload；其余请求原样，未暴露任何有效工具时拒绝而非直接转发。保持终稿schema，不添加补发循环、不调用隐式搜索。相比加强提示词更明确；相比每轮强制工具不会阻止合法结束或强制无关读页。供应商是否遵循须真实验证，不能由合成测试代替。

- [x] tests/test_research_first_action.py：真实loopback桥接配合合成供应商，先RED（新参数不存在，5失败/1通过），实现后验证首required、后续auto、schema/业务不变、预算不扩和默认兼容。
- [x] pilot/responses_bridge.py及pilot/codex_research_worker.py最小实现，定向pytest与必要worker接线检查。
- [ ] 独立整批审核、提交main；按产品差量统一候选，真实客户端新任务验证搜索→原文，不回写旧失败。

当前不因本批重做已有回收/安装测试；初次本机请求读取与覆盖时区显示作为同一交付批次的已知体验缺口保留。

验证：首次动作+effect合同50通过；接入真实effect_input/effect_result校验后，Windows桥接相关12通过/5.62秒。隔离Linux镜像无网络、只读根、非root、无客户/密钥挂载，首次动作与worker有/无编译上下文的实际入口9通过/2.85秒；provider和工具结果是合成，worker执行为真实子进程，不等于供应商实网。首次Linux测试仅因测试辅助py.py缺失未能启动，补齐离线测试依赖后通过，没有修改产品依赖。主干6423c43官网来件已快进整合，不影响本批产品字节。

独立整批审核review_first_action：基线6423c432，四文件差量可提交，无P1/P2；仅代码放行。effect合同44项追加检查通过/0.43秒。尚未部署、构包或实网验证本修复，完整Goal继续。

## 16:45 同源服务部署接续

修复096768b，正常合并官网来件后1549c18fdfdad54ee1f13b72a08441bc7c8e10b2已推main。以Git归档SHA256 `5fd1b2251d915c596ab059fca43f4b1d127dcdb421233f35a8ad91894c591218`构建客户与研究两个不可变候选；各196文件逐字节核验、依赖/源文件集合兼容检查通过，没有下载依赖。构建78502 exit0。

复用已审发布脚本，只替换版本/镜像常量；发布锁、现有容器身份、无运行研究检查、原环境/挂载/端口检查及失败恢复逻辑不改。预检通过后16:45:30实际切换：

- 客户镜像 `sha256:f395646af372198532fd823b4147dd5f79a86ba18aa9012e040d3e33d6f3767f`，容器 `4d7745fc7be21d573b954627fb879463ba391b74ff9a387ee0e58bf81ce10702`。
- 研究/broker镜像 `sha256:3d5622a2c14f94a6babdae803f69ee85eab15a5b07d65ebe84999859d3ee0635`，容器 `27395b8680d0e9b9a7f579082cda1f0032f1eb90139c786b2cdd645ed6a66e3e`。
- 两者revision1549c18、running/restarts0/只读非root；broker无网络。私有socket、客户18787、公网readyz200；ops原容器未变且18789为200。旧47镜像/数据/正式失败任务保留，未触发实际回滚。

Windows同源载荷47197已exit0，1通过/459.88秒，保留D:/yk-connect/portable-1549c18-relocated。Forge91784仍在封装EXE（实际nuget子进程28760持续I/O），唯一输出D:/ykg913；不重复启动，尚未安装此版本。首次required的真实模型结果与客户价值闭环未通过，不以部署替代验收。

封装入口核对桌面649个源码的manifestSha256为`7659879b31a9db02aeec50dc40855d43f42319e5bcb64f3c9953cd7ab56c557c`，与47版本完全一致；app/vendor/依赖同样无差量。为利用封装等待，重开现有47安装版连接1549c18服务，UI已进入新建任务并填写“验收-AI定制首次搜索-0913”；未确认策略、未创建正式任务、未开始研究，不记作真实闭环通过。随后工具检测用户输入/窗口移动，暂停输入；另发现非本轮启动的D:/ykt913旧安装器窗口，未关闭/接管。待其终态且窗口稳定后再继续，不叠加安装。当前活跃清理任务已收到本轮构建目录保护清单。

## 17:05起：真实首次搜索、Windows实装及数据库遗漏

以上等待为历史状态。Forge91784已exit0，固定1549c18产物 `D:/ykg913/make/squirrel.windows/x64/YikeAI-Setup.exe`（642852352字节，SHA256 `1fa60336fd0ada417fabf283272d30e87e7bf46035f7a37dd5c2fe3e5c75ab10`，未签名）。关闭旧安装失败窗口及仅测试会话草稿后，本批Setup58594 exit0。实际C:/Users/bruce/AppData/Local/YikeAI/app-0.2.0/resources/app.asar与候选同为`6d28fd467c0a07dcdf3d9ce017fa5f9d09089bdb82f82183647a67e430a6921f`；原生新版工作台、登录、小红书连接、正式任务列表与暂停详情已实查保留。

实际UI创建“验收-AI定制首次搜索-0913”，任务`38d1428b-7e2c-4714-8ae4-c059197ce5cc`，run`fffb91ff-53fd-45f5-9742-ead941f3fd55`。首次MODEL的required真实产生搜索；4MODEL/3SEARCH成功，17:05:44首次READ www.v2ex.com，17:05:50 STOPPED/runtime_failed，READ仍ISSUED，无成功原文或新候选。该任务创建时桌面为同649源码旧安装，之后由新实装只读查询，不追认新安装创建，也不重放原任务。

已核对READ/事件截止均17:20:03，排除此次租约到期；同时间段PostgreSQL日志明确违反`research_effect_final_result`。143的journal CHECK和deferred pair仅接受旧3种失败，遗漏host现已识别的connection_unavailable。新增146同时扩展两处精确JSON白名单，不改143，不回写旧失败，保留RLS/双表绑定/UNKNOWN及防重。真实隔离PG先RED1失败61通过，再迁移后62通过。

另发现重复migrate会先重放143而拒绝已保存新回执，新增回归再次RED1失败62通过。现仅bootstrap迁移账本，摘要一致的已应用版本跳过，不一致仍报错，未应用版本在原advisory锁及同一事务执行。补回执后再次升级、摘要不符回滚、空库两次及旧115前缀升级。最终66通过/27.98秒（77043），无模型或客户数据。一次测试夹具误把app URL指向superuser导致附加升级用例初始化失败；修正为专用受限testapp后通过，原journal用例本来使用受限RoleDatabase。一次性测试容器/网络已删除，合成源码留存。

独立review_read_schema首审重复迁移P2已修复，差量复审GO；摘要绑定db.py `45beb83c90d0d3a72addc9e8f826acf5d1b3cd303f84fc32b5730760f9aca086`、146 `9a21f6bcbaff9da8733b2c539fd39f7f69f506b3fcf522b9ad4c69ae7e827561`。本节此刻数据库修复尚未部署；发布必须使用新管理迁移入口，不能用旧runner重放历史DDL作回滚。仅服务端迁移差量，不重复构Windows包。真实原文/候选、三业务及用户认可仍待验，完整Goal ACTIVE。

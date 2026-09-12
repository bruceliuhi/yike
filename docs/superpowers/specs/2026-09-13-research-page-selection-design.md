# 研究材料与候选分离

授权：AUTHORITY.md记录的2026-09-11既定V02范围内自主设计/实现授权。本批不新增外联、生产部署或收费授权。

## 问题与选择

动态研究当前对所有成功READ发布候选并调用普通判断。真实探针曾把供方定价文章读入；本地Skill则把索引、广告当研究材料，继续寻找本人项目。

选择复用研究Agent的最后一次回答，输出结构化逐页筛选；宿主以同任务持久READ证据验证，再在既有批次回执中记录筛选。拒绝两个替代：每页另加分类模型会增加调用成本；关键词/URL黑名单会误杀行业和评论需求。筛选是可追溯模型判断，不是已核验的采购事实。

## 合同

最终严格JSON：`{"schema_version":"research-page-selection-v1","summary":"…","pages":[{"url":"https://…","content_sha256":"…","decision":"ASSESS","reason":"POSSIBLE_DEMAND","quote":"原文逐字片段"}]}`。

- 根键和页面键精确匹配；不接受围栏、重复JSON键、NaN/Infinity或尾随文本。summary为1–2000字符；总UTF-8最多512KiB；pages最多100项。
- 每一成功读取的唯一(url, content_sha256)必须且只能出现一次。搜索摘要、未读URL、错误hash、漏页、重复页一律拒收。相同版本的重复READ可共用一条决策，但每条持久回执保留序号。
- url必须等于标准化后的原文URL；content_sha256必须等于持久原文的摘要；quote为1–400字符非空逐字片段，必须包含在原文text中，不从搜索摘要、标题或模型推断补齐。
- ASSESS理由只有POSSIBLE_DEMAND或UNCERTAIN。BACKGROUND理由只有INDEX、VENDOR_CONTENT、NO_BUYER_SIGNAL、STALE_OR_CLOSED、IRRELEVANT。理由为模型判断；无法确定时ASSESS/UNCERTAIN。不因预算、直联方式缺失或匿名身份排除；混合页面含可能买方评论时保留ASSESS。
- BACKGROUND不是永久排除、不是零市场需求；ASSESS不是高意向、不是复核通过，仍走原普通判断/本人补证/人工确认。

## 执行与持久化

1. 编译研究规则加入本合同指令、版本后缀`/page-selection-v1`；该指令进入现有规则hash。旧上下文不静默续跑。普通只读/无研究上下文内部调用保持旧总结路径。
2. 带研究上下文的事件观察允许至512KiB的最终消息（仍受现有2MiB事件边界），支持最大来源预算；旧路径保留16000字符限制。不增加网络调用或工具权限。
3. 动态runtime在mission COMPLETED后校验返回research_binding，加载持久成功READ，严格解析并核对所有筛选。无效时STOPPED/research_selection_invalid；不得fallback为全选，也不得宣称筛选完成/没有机会。
4. 候选store接受可选的内部selection参数，针对持久READ再次验证。未传参数的既有内部发布保持兼容；显式空/坏值拒绝。带选择时，execution_context增加`page_selection`和`skipped_background_count`，参与原有fingerprint。page_selection存放精确版本化逐页决策（含quote），不替代原文。回放必须检查传入决策与已存决策相同；有无selection的变化也冲突。
5. BACKGROUND生成accepted_count=0、items=[]的可追溯批次；不创建候选源/版本/观察，不消耗max_records，不调用普通判断。保留READ原文、原资源消耗和筛选理由，不计invalid/budget跳过。
6. ASSESS照旧保留完整PAGE、UNKNOWN作者/日期、相同普通判断及取消/代次/权限/额度检查。过大原文不截断。选中数量可能为0；只在全部操作确实终态且已有完成门禁通过时完成研究，不能升级为商机成功。

无新数据库表/列，无客户API字段变化。已确认既有135触发器固定20键且旧计数等式不能承载筛选账本，因此新增144仅替换该约束函数：20键旧路径及权限不变，22键路径绑定成功READ原文、逐字quote和背景计数。既有运行状态的实际读页数、候选数与判断数保持各自含义；筛选记录保存在租户隔离批次和原始journal。前端专门筛选详情视图不在本批，不能宣传已可在界面逐页查看全部背景理由。

现有进度说明需要两处窄文本适配：动态v4完成、acceptedOriginals=0且discovery.reads.succeeded>0时说明实际已读页数及未选入待分析候选，不写成未读取；research_selection_invalid停止时说明原文保留、筛选未完成，不代表没有机会。不改变页面布局、API计数或新建任务/未知请求处理规则。

## 验收

纯合同测试涵盖所有缺失/伪造/重复/额外/边界输入和版本hash；实际worker合成进程确认合同传递及新旧消息大小边界。隔离非超级用户PG验证背景0候选/0记录额度、幂等与冲突、原文quote/hash匹配、租户/代次/取消保护；runtime混合页仅ASSESS触发普通判断，全部背景可完成且0判断，畸形/漏页在发布前停止。复用旧护栏回归，只跑相关文件；一批独立审核。

这些证明控制流和账本，不证明筛选准确率、商业价值或已恢复本地Skill效果。通过后再运行一个新的有界真实来源对照；旧UNKNOWN或受限平台不重试。

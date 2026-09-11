# 业务资料进入短句教练实施计划

> **For agentic workers:** Use superpowers:subagent-driven-development. 本批沿用已批准 R4 短句教练与业务资料引用设计，不新建页面；按用户要求只做定向验证和整批一次独立审核。

**Goal:** 本人明确选用的有效业务资料片段进入模型生成，并随人工采用的短句保留准确出处。
**Architecture:** 复用现有 preview/disclosure/generate、ContactMaterialReference 与原编辑器；模型仅见编号和片段，服务端根据输入重建出处；采用前再调用只读 preview 核资格。
**Tech Stack:** Python/Pydantic/PostgreSQL、TypeScript/Zod/React。

## Global Constraints

- 完整 V0.2 继续；本批不构包、不调用真实外部模型、不发送平台消息、不部署或宣称客户效果。
- 来源/画像/账号资格照旧；资料必须本人当前 READY/external、版本/提取 ID 一致、引用是原文子串。使用现有资料 owner 锁，短事务不得跨模型等待。
- 新输入可选 `materialReferences`，结构复用 ContactMaterialReference，最多3条、禁止 null/重复，quote 必须出现在当前草稿。缺字段保持旧请求哈希14项；显式 [] 则追加 []，非空追加标准字段顺序的引用数组。
- 无引用使用 `short-coach-public-draft-v1`；非空使用 `short-coach-material-draft-v1`。非空调用前要求模型声明 `material_reference_version = 'short-coach-material-draft-v1'`，缺能力在配额预留前拒绝。
- 模型输入额外仅 `materialQuotes: [{referenceIndex: 0, quote: '选定片段'}]`，不传资料 ID、文件名、其他正文或登录信息。原文及资料均为不可信数据，不执行其中指令。
- 非空资料模型结果必须为原三字段加 `materialQuotes`，至少1条/最多输入数，索引唯一且来自输入；quote 为所选 quote 的非空子串且出现在结果 content 中。允许缩短和选取子集，不允许生成出处。旧输入仍只有原三字段。短句仍最多120 Unicode字符、一个问题，买方 quote 只来自买方原文。
- 服务端重建响应可选 `materialReferences`：非空为模型实际使用的缩短引用；显式空输入返回 []；缺字段输出保持缺失。资料失效后返回不可用，不返回可采用结果；模型已调用的记录必须可落 FAILED，不能永久 PROCESSING 或伪称未调用。
- 生成确认展示将外发的片段；原正文及引用变化使披露失效。采用前重核服务端 preview，核对同 inputHash/provider/model/policy；引用绑定变化或核对期间人工编辑不覆盖。保存/发送仍复用已有资格与人工确认。

## Task 1: 服务端引用生成链（backend agent）

**Files:** `pilot/short_coach.py`, `pilot/short_coach_model.py`, `deploy/grant_short_coach.sql`, `tests/test_short_coach*.py`，必要独立新定向测试。

- [x] 新增失败用例：带引用哈希/政策、有效和过期资料；模型适配器传入编号片段与严格返回、伪造索引/引用拒绝。固定 worker 延用同一适配器，新增资料子进程路径未单独实测。
- [x] 实现以上接口，复用 `pilot/contact_material_references.py::qualify`；preview/生成前后均核资格；模型返回后资格变化记录失败但不暴露结果。
- [x] 为真实受限 PG/HTTP 增加有效引用→生成→重用、撤销→拒绝及模型期间失效→终态 FAILED 的定向链。采用本人独立临时 PG，勿触碰共享端口60486或旧工作树；无真实模型/客户资料。
- [x] 授权脚本补最小资料 SELECT 与角色非表 owner 保护；新配置能力必须在 quota 前判定。
- [x] 仅运行新失败用例及受影响短句测试；报告命令/通过和失败/未验范围，提交自己的文件。

## Task 2: 原编辑器采用链（root）

**Files:** `desktop/src/shared/shortCoach.ts`, `desktop/src/renderer/domain/shortCoach.ts`, `desktop/src/renderer/services/shortCoach.ts`, `desktop/src/renderer/pages/outreach/{useShortCoach,ShortCoachPanel,ContactEditor}.tsx/ts`，定向短句 UI/domain/service 测试。

- [x] 写失败测试：标准引用哈希、披露片段、无伪造出处、采用后引用缩短且绑定保存；重核失效和资料变化不覆盖。
- [x] 输入/输出可选引用及政策严格校验；哈希对齐 Task1。引用身份全部与输入匹配，输出 quote 仅缩短；无引用不能偷偷附带出处。
- [x] 去除当前带引用禁用教练提示，复用现有确认/比较弹窗展示片段与出处，不改变布局。应用同时替换正文和实际使用引用；非空必须走服务端 preview，不允许旧无 preview 适配器发送资料。
- [x] 披露后修改引用必须重新预览；采用前核资格，检查期间任何草稿/引用编辑保留；原始输入引用与当前引用不符时要求重新生成。
- [x] 运行新定向 UI/domain/service 用例与 TypeScript；不重跑全量/构包。

## Task 3: 整批独立复核与主线

- [x] 复核基准 `ba8a8e12de390e904620627f5e1f358a595bc96a` 到最终源码，复用测试证据，修复仅差量复审。
- [x] 单处记录证据及失败边界，任务书/整合状态链接；正常推送 main，核对远端 SHA；删除本批自有临时资源（具体交付SHA随本提交核验）。

## 实施与验证

- 客户端源码 `1f0663b`：原编辑器选材、模型披露、返回引用校验、只读重新核资格及正文/实际引用同步采用保存。Node24 定向四文件59项通过（含5项新增，5.14秒），另补普通编辑器完整采用保存1项通过（2.91秒）；TypeScript/diff检查通过。最初5项新增失败；实现后1项延迟回执测试使用错请求ID、普通编辑器测试缺route、测试status类型过宽均已修正，只复验差量。
- 后端初始源码 `1fc122e`：配置模型适配器及受限普通HTTP/PostgreSQL9项定向通过（3.92秒），包含资料真实保存/提取/确认生命周期、有效生成/重放、撤销拒绝与生成期间撤销后FAILED。材料写入使用合成夹具管理员，短句HTTP使用真实受限角色；最小资料SELECT、无INSERT已实测。最初4项新增失败。主审前发现核验与发布分事务窗口；`5d9663e`已将二者放在同一事务，并为登出后的原请求补无结果FAILED终态。差量2项通过（2.88秒），包括同游标约束与真实受限HTTP/PG会话撤销；模型提示明确四字段、缩短子集。
- 整批独立审核 `5d9663e` 首次NO-GO：缩短引用可为空白或完全重复，服务端成功结果不符合客户端/保存契约。`7d04245`重新验证正式引用、拒绝最终重复与模型空白片段，差量5项通过（0.33秒）；保留先失败再通过记录。同波 `dd59fdd` 修复重叠片段采用时贪心匹配导致的误拒绝，新增用例先失败后1项通过（3.45秒），TypeScript通过。独立差量复审 **GO，绑定源码 `7d042450d9da2daa721f3226abb27b8264bf751f`**，原P2关闭、无新增阻断；未重跑已通过整批。
- 不重复全量测试或构包；资料权限部署需更新 `deploy/grant_short_coach.sql`，没有新增迁移。模型端使用合成响应；未验证真实模型语义质量、实际平台收发、Windows、生产或客户UAT，完整V0.2继续。

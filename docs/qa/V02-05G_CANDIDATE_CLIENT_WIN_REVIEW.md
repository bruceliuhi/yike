# 05G 真实候选客户端 Win 验收记录

日期：2026-09-10。原基线`c88b64b`，计划/认领`11eeb32`，正常保留Mac执行签名来件后为`0eab72a`。[实施计划](../superpowers/plans/2026-09-10-win-candidate-review-client.md)沿现有R3/R4接P07，不另做演示页。

## 当前边界

IN_PROGRESS：候选合同和固定传输已完成限定工程片，实际产品组合启用读取；完整P07判断、人工来源核验、确认和恢复未验收。已完成的商机固定原文展示属于[05E](V02-05E_SOURCE_EVIDENCE_CLIENT_WIN_REVIEW.md)，不借其测试宣称本片完成。

新INCLUDE必须完整匹配原sourceVerificationId。先前在main给Mac[最小补充请求](../handoffs/V1_WIN_FUNCTION_OWNERSHIP_20260909.md#05g接线及设备恢复的最小服务缺口2026-09-10c88b64b核查)后，Mac以`9d9e965`补齐原ID，新EXCLUDE省略/null返回null；Win已快进到`2d799bc`并独立核对修复和原指纹语义。旧回执保持可读，不凭当前核验补写。设备恢复服务/合同也已由Mac交付，不再当作无接口缺口；实际Win接收另验，不能借静态核对记ACK。

## 基线和交接检查

- Win在`c88b64b`运行Node24 `node node_modules/vitest/vitest.mjs run tests/ui/candidate tests/serviceClient.test.ts --maxWorkers=4`：3文件、37 passed、0 skipped，6.35s。仅为改动前基线。
- 计划独立复核修正精确分页、五种回执/别名恢复和中文平台映射后，规格及两项依赖交接通过；`11eeb32`已正常提交，合并Mac `bbe2e20`为`0eab72a`后推送main，未向不可见Mac运行任务冒称直发或取得新依赖ACK。
- 独立兼容性审核绑定`0eab72a9fe293a8e11e136434327537d3a62f69f`：PASS、0项发现。相对Mac来件仅有Win三份文档，相对共同基线desktop生产源码未变；双方认领完整保留。执行准备与原设备BIND/PROVE为不同签名域，不能复用签名器冒称已接入。
- Win根代理在`0eab72a`运行`.runtime/venvs/win-device-review/Scripts/python.exe -X utf8 -m pytest -q tests/test_execution_api.py tests/test_execution_contract.py tests/test_execution_signing_payload.py tests/test_pilot_runtime.py --tb=short`：69 passed、0 skipped，1.28s。这是新来件HTTP/纯协议兼容性检查，非真实PG、Win实际签名或本片候选客户端验收；不与旧基线相加。

## 后续验收

接线顺序另经独立核对：旧P07切换画像会直接产生新ASSESS且未持久化。Task2因此只在产品组合启用候选读取，写factory可独立验证但旧reviewCandidate保持不可用；Task3/4明确按钮及恢复完成后才启用写入。此门禁不是把完整P07降级为只读交付。

每个新增实现先记录有效RED，再记录GREEN和非作者规格/代码/架构/质量结论。实际产品Node→认证HTTP→受限PG、Windows界面及生产TEST排除在完成后分别登记，不预填通过。合成来源/模型仅验证工程链路，真实平台、正常模型效果、确认收发、发行与客户试用和完整Goal均继续。

## Task1 协议实现与反例

根代理在`2d799bc`上新增共享候选边界、专属测试和合成夹具。前一实现helper句柄已消失且未留下代码，未继续把它当运行任务等待；实现由根代理接续，非作者审核继续单独执行。

- 可导入拒绝stub的首次定向：39项中8 failed/31 passed，正向查询、写入和完整响应因缺实现而失败，不是缺文件/依赖造成的错误。最小实现后39 passed、tsc退出0。
- 根代理补“stale标记不能掩盖decision内分析版本不一致”反例：1 failed/39 passed；补完整绑定后40 passed。
- 独立SPEC找到实际后端body前120字符为空白时的title fallback误拒：新增反例1 failed/40 passed，修复保留原值后41 passed。
- 独立SPEC继续发现历史列表内同类混版本及JS trim/Python strip差异：新增反例2 failed/41 passed；使用Python空白集合仅比较不改写原值、始终核对分析绑定和策略后43 passed、tsc退出0。
- 审核者关于正则尾随LF的初步推测经其本机Node探针否定并主动撤回，没有据推测改代码或登记为修复。上述失败均保留各自时点，不将首次失败写为通过。

独立SPEC定点复审PASS，四个只读探针证实原三项关闭；随后独立代码/架构/质量PASS，0 Critical/Important/Minor，额外五个探针覆盖EXCLUDE三态、固定错误和冻结输入不变。审核绑定共享源码SHA256 `9F85367CFC837D60E48CE5AAB0028BAB2DE1434DD0798401D1E3D04AB259C171`，测试 `E7519E329877617822E4396DDF1F40FECB8A0FC308C361744309F543563FE1B7`，夹具 `8EE31EED58342ABD640DED4C61513B51D3CBE5211D9D806675D057EDE50E4EB3`。

根代理在相同字节上执行Node24 `node node_modules/vitest/vitest.mjs run tests/candidateReviewApi.test.ts tests/ui/candidate tests/serviceClient.test.ts --maxWorkers=4`：**4文件80 passed、0 skipped、0 worker错误，54.97s**；类型检查退出0。与43项重叠，不相加；审核者未冒称重跑root套件。

以上只完成纯候选协议，不是HTTP/PG或客户可用证据。生产组合不提前打开旧页面的隐式ASSESS，继续Task2～5。

## Task2 固定传输与实际候选读取

Task1提交`c4fdf01`后正常合入Mac到`d45699b`。该合入包含资料草稿、任务返回等桌面改动；原推送命令中相对c4的desktop差异检查非零但PowerShell继续执行推送，不将其记成“desktop未变化”或合入前验证。随后根代理实际执行相关8文件103项（7.66s）与类型检查，覆盖本片读取和新来件资料/任务返回；测试归属是合入后的当前工作树。

- 四个固定操作`candidates.list/review/verifySource/request`复用认证队列、严格schema、Origin和响应上限；新增factory严格解析并匹配原请求，保留字段省略/null、原文及未知时间，取消只防止迟到采用，不承诺终止服务器执行。
- 实际`service.candidates`已读取真实入口；只有显示标签映射为中文。旧`reviewCandidate`继续501，尚不安装产品写服务，避免旧页面换画像隐式调用模型；两处nullable来源URL调用点增加保护。
- 根代理有效RED为2 failed/40 passed：固定操作尚不可用、真实读取仍501。最小接线后主进程5项通过。helper factory首次57项RED→GREEN，Date/Map/getter反例3项RED→最终64项GREEN；没有为减少失败而跳过用例。
- 扩展相关回归首次1 failed/197 passed：旧UI测试仍假定读取总是本地501。已改为明确模拟后端501，检查错误透传且仅一次GET；旧复核仍501且不POST。最终根代理在清理无关格式改动后，Node24实际运行9文件**198 passed/0 skipped，5.28s**；另5文件策略传输/固定原文/确认发送/对账**115 passed/0 skipped，4.48s**。不同命令范围分别记录，不累计为唯一测试数。
- `tsc --noEmit`退出0。真实renderer生产排除构建4779 transformed/4778 graph modules，manifestHarnessReferences=0、failures=[]；existingAsarChecked=false，不冒称Windows安装包验收。
- 独立SPEC先PASS，随后独立代码/架构/质量PASS，0 Critical/Important/Minor；审核者不冒称复跑根代理套件。绑定base`d45699b`的11文件排序哈希清单摘要（相对路径、空格、大写SHA256，LF连接无末尾换行）`932669C6C6C68C6B360FEE0E90C6F40F45C03D7EEC270FB558A4506007943186`。

复验命令（desktop目录，Node24）：

```text
node node_modules/vitest/vitest.mjs run tests/candidateReviewApi.test.ts tests/candidateReviewService.test.ts tests/serviceClient.test.ts tests/servicePolicy.test.ts tests/ui/client.test.ts tests/ui/candidate tests/ui/connections.test.tsx tests/ui/outreach.test.tsx --maxWorkers=4
node node_modules/vitest/vitest.mjs run tests/researchStrategyTransport.test.ts tests/opportunitySourceEvidence.test.ts tests/ui/fixed-source-evidence.test.tsx tests/ui/send-confirmation.test.tsx tests/ui/outreach-reconciliation.test.tsx --maxWorkers=4
node node_modules/typescript/bin/tsc --noEmit
node tests/visual/verify-production-exclusion.mjs
```

仅Task2工程片通过：没有真实PG消费、完整P07人工确认、真实平台/模型效果、确认收发或客户试用证据。继续Task3原始正文/评论上下文及原请求恢复，再接Task4页面显式操作；原文证据、多找类似、短句建联和整体Goal均不缩减。

### Task2 主干整合

Task2源码提交`60b2523`；正常保留Mac来件`83e76be`形成`81f725424eb37e8541e2b2809e0182c40348f496`。来件仅reply_store的SQL JSON参数编码、两项隔离测试夹具和整合记录；独立兼容复核PASS，无desktop/候选合同/迁移交叠。`git diff --exit-code 60b2523 81f7254 -- desktop`退出0，故上述本片桌面测试与构建绑定字节未变。

Win根代理实际执行Python `-X utf8 -m pytest -q tests/test_reply_store.py tests/test_reply_contract.py tests/test_import_atomicity.py tests/test_pilot_contracts.py --tb=short`：**24 passed / 7 skipped，0.44s**。7项因未注入一次性PG环境而明确跳过，此处只收纯边界兼容性，不接受实际PG或Mac文档测试数字为Win实测；实际PG留待Task5。凭据扫描clean、diff check通过，双方源码及认领保留。

## Task3 原始证据与操作恢复基础

基线`b1b2cba`；Task3a原文边界和Task3b恢复域为两个独立helper，root负责固定接线、hook、共享ledger和最终验证。只接既有服务，不改Mac后端、判断模型或发送模块。

### 原始证据读取

- `rawCandidateEvidence`完整保留原始候选/版本/最多100条观察及原执行身份。COMMENT自身正文/作者与原帖标题/父评论分开，发布时间null不补造，观察和接收另存；截断窗口可不含当前观察，若包含必须精确核对。实际`profileId`来自raw.profile_version_id，不冒称从raw核对numeric profileVersion。
- helper有效拒绝stub RED1项；边界158 failed/9 passed；时间一致性4 failed/168 passed；最终172项GREEN，联合已审协议215项通过。期间全桌面tsc遇并行ledger测试类型错误，已如实报告；并行作者修复后root最终全桌面检查通过。
- root固定GET RED1 failed/5 passed→6 passed；factory RED3 failed/67 passed→70 passed；真实客户端组合RED1 failed/37 passed→38 passed。只有candidateId进入固定IPC payload；实际产品仅新增只读属性，未安装candidateReview写服务。
- 独立SPEC与代码/架构/质量PASS，0 Critical/Important/Minor；独立6个只读探针通过。绑定11文件排序哈希清单摘要`47A3B0776B9DE48A89F808A81782EE1F30E3E374E10DDC00DA2890C58CA02E30`（算法同Task2）。raw源码SHA256 `A3052998E72F8CE3213C99C8E9EF5A245C4A167E21A40F41779A0FC91E3A0F98`。

### 原请求恢复

- 独立新版scope保存原请求摘要与字段存在性标记，原文、人工依据及回执正文均不落本机操作账本；旧scope/hash字节不改。实际producer的invocationRequestId是模型调用标识而非用户请求ID，新记录额外保留该opaque ID以正确构造显式retryOf，不放宽原requestId匹配。
- helper可导入stub有效RED53项→53 passed；实际producer终态反例2 failed→55 passed。FAILED/RECORDED不能被后到结果降级。root hook首次stub9项失败，其中3项最初直接读不存在记录导致TypeError，补明确长度断言后有效9项断言RED→9 passed；不将原TypeError当产品缺陷。
- root补旧未决账本绕过反例1 failed/9 passed→10 passed；中间一次括号拼写造成transform失败，无测试执行，修正后通过。扩展错误/退出/账号/空间/显式重试/超时后19项通过。
- root再查慢hash并发：一窗口已完成，另一窗口旧确认可能再次POST。首次探针误将原提交和恢复两次hash都挂起，造成超时和后续测试干扰（11 failed/9 passed）；修正只挂第一次后获得有效产品RED1 failed/19 passed。提交前新增同scope/candidate条目快照CAS，任何在途变化包含RECORDED都使旧确认失效；最终20 passed，类型检查通过。此为普通同机交互防重，不替代服务端跨设备幂等。
- Task3b独立SPEC及慢hash定点复审PASS，随后代码/架构/质量PASS，0 Critical/Important/Minor。独立慢hash1项/其余19未选，以及字段存在性/别名/终态4项/其余51未选分别通过，不冒称全组重跑。绑定5文件排序哈希清单摘要`7C4038FE514E94F22D031C00345B699416C31CC0BBFA5399C7318C830892312F`（算法同Task2）。

### 根代理最终验证

在最终格式化后的代码执行Node24：**14文件546 passed / 0 skipped，5.34s**，覆盖新raw/恢复/固定传输及旧候选、operation ledger、策略恢复和确认发送/对账；各阶段结果不相加。`tsc --noEmit`退出0。生产renderer排除构建4781 transformed/4780 graph modules、manifestHarnessReferences=0、failures=[]，existingAsarChecked=false。凭据扫描clean、diff check通过。

```text
node node_modules/vitest/vitest.mjs run tests/rawCandidateEvidence.test.ts tests/candidateRequestOperation.test.ts tests/candidateReviewApi.test.ts tests/candidateReviewService.test.ts tests/serviceClient.test.ts tests/servicePolicy.test.ts tests/ui/client.test.ts tests/ui/candidate tests/ui/operation-ledger.test.tsx tests/ui/strategy-confirmation-hook.test.tsx tests/ui/outreach-reconciliation.test.tsx tests/ui/send-confirmation.test.tsx --maxWorkers=4
```

当前仅基础模块和只读产品接线。完整P07显式判断/来源核验/确认入库尚待Task4；实际Node→HTTP→受限PG验证核验ID、Windows双视口及用户整链仍待Task5。没有实际平台采集、模型收费、发送、生产部署或客户试用操作，不将05G/PH-F06或完整Goal标DONE。

### Task3 主干整合

源码提交`323c786`，正常保留Mac `797d0b1`形成`8d24e67e99b0afd0c49b40b66fa62a2b972c6099`。来件91文件主要是Mac可视/native证据，生产差异仅两份device GRANT的6行；desktop与pilot源码不变，独立限定兼容复核PASS，无P0/P1/P2合入阻断。`git diff --exit-code 323c786 8d24e67 -- desktop`退出0，546项、类型与生产构建仍绑定相同产品字节。

独立审核保留非阻断部署提醒：device credentials授权脚本的owner guard尚未包含新增授权的connections/session_revocations表，GRANT本身不授予表所有权；后续独立部署需按既有session授权脚本验证两表非应用角色所有。此处没有执行生产授权、扩展安全工程或冒充新PG接收。Mac本轮截图/包/PG数字各保留其原版本与执行归属，不作为Win或新P07实际验收。

Win根代理对合入版本执行Python `-X utf8 -m pytest -q tests/test_device_keys.py tests/test_device_registration.py --tb=short`：38 passed/0 skipped，0.16s。仅纯设备/登记兼容检查，不证明SQL grants已在Windows PG实际应用；此前单独18项是其子集，不累计。

## Task4 P07 原文证据与完整人工流程

基线`f1a1c33`。沿已有P07接入真实候选服务，不另建产品演示页。当前本人原文与父帖/父评论分开，原始发布时间、观察时间、接收时间和来源版本分别展示；逐字正文保留换行并转义，未知时间不补造。四维判断、引用出处、反证/未知、模型/规则版本和未发送短句独立展示，缺分析不伪造等级或草稿。

绑定画像只选择、不自动调用模型；显式ASSESS、人工来源核验、确认纳入/排除统一走先持久化原请求再POST。来源核验展示完整定位、摘录、核验人/时间/ID/requestId；未核实、过期、无联系路径不能纳入。INCLUDE固定核验ID和全部确认字段，任何编辑需重确。旧样例、批量和旧账本保留；结果未知先GET原请求，不盲重发。核对成功给出现有P11入口，不授权发送。

### 反例与独立审核

- 原文面板stub有效RED9→最终12项；来源核验stub RED19，加回执定位/摘录反例2→最终21项。隔离视觉入口stub RED5，加中文平台显示RED1→6项。
- P07初始有效RED3（绑定画像、禁止隐式调用、缺人工表单）；随后筛选ABA/原文失败RED2、未知请求锁RED1、策略失配/画像ABA RED2、刷新按钮RED1、晚到核验/决策版本变化RED2均修复。最终15项涵盖用户确认、回执丢失后筛选外GET恢复及不重复写入；不把后补覆盖冒称先失败测试。
- 独立SPEC、代码/架构/质量审核发现4个P2：核验回执定位/摘录遗漏、ASSESS策略失配、画像往返保留确认、晚到响应跨新版本采用；均修复并复审PASS，0开放项。独立111项、视觉相关21项为不同阶段批次，不累计。
- Windows浏览器发现恢复成功仍留旧“未知”错误，增加有效RED1→GREEN1；只在已核对非空结果后清理旧提示。独立最终差量PASS，定向1 passed/14未选；当前`Opportunities.tsx` SHA256=`0342E429B6CD90A808FBBE38BBBA9EFA2CCFFD4E0693FA1B8DEF8D15D37531D4`。

### 根代理验证与边界

最终提示修复后，Node24相关回归**20文件612 passed/0 skipped，8.85s**。包含Task3同组加视觉入口隔离、原文/来源/P07和既有弹窗；不与先前546项累计。此前类型检查退出0，生产TEST排除4787 transformed/4786 graph modules、manifestHarnessReferences=0、failures=[]，existingAsarChecked=false；主干合入后另记最终复验。

Windows Edge真实浏览器已在1440×1000和960×600检查原文、完整确认弹窗、取消/重新确认、成功入口、回执丢失及筛选外原请求恢复、原文读取明确失败。数据/平台/模型为TEST隔离，真实浏览器不等于真实后端整链；浏览器不执行外部来源访问或发送。最终合入及提示修复后复验单独记录。

Task4产品写入口现已安装；**Task5实际Node→HTTP→受限PostgreSQL仍未执行**，sourceVerificationId服务回执接收、真实来源/模型/收发、安装发行及客户试用仍不能冒称完成。05G/PH-F06/整体Goal保持IN_PROGRESS。

### Task4 主干整合与最终复验

源码`90c1feb`，正常保留Mac`81adccb`合入`5614d71`。仅整合状态顶部并行记录冲突，保留双方全部文字。Mac弹窗可访问性、迁移110注册、会话内容退出保护均保留；两段来件分别经独立限定兼容审核PASS，不将Mac原生包或PG证据计为Win。

扩大到全部UI与候选合同/服务/视觉隔离后首次93文件：1421 passed/2 failed。失败明确是工作台候选定位两项旧断言未包含新增AbortSignal第二参数；只补`expect.any(AbortSignal)`，精确ID/分页和切换时清除选择/确认的断言未减弱，独立适配审核PASS。最终同批**93文件1423 passed/0 skipped，53.36s**，不是与612项相加。Node24 `tsc --noEmit`退出0；生产排除构建4788 transformed/4787 graph modules、manifestHarnessReferences=0、failures=[]，existingAsarChecked=false。Win Python身份合同**19 passed/0 skipped，0.35s**（含110注册），不是实际PG执行。

最终合入产品字节在Windows Edge以1440×1000/960×600复验原文与确认弹窗，960重新执行取消→重新勾选→提交丢回执→筛选外GET恢复：事件恰好一次ASSESS、VERIFY、INCLUDE、GET_REQUEST，成功后无旧未知提示，scrollWidth=960。原文读取失败场景只LIST/RAW、无摘要替代且不能纳入。截图与页面/事件记录见[candidate-p07-win](candidate-p07-win/README.md)。全部是明确标识的TEST内存传输，未调用实际平台、模型或客户库。

自己的源码/文档diff检查和凭据扫描通过。合入Mac历史验收日志与刻意空白fixture的diff check报告原有尾随空白，原证据按字节保留，未替别人清洗历史记录。

## Task5 Windows 实际客户端 HTTP 与 PostgreSQL 接收

日期2026-09-10，产品基线`ca1f28a`。新增`tests/test_desktop_candidate_review_http_postgres.py`与`desktop/tests/integration/candidate-review-live.test.ts`，没有修改生产API、授权或客户端行为。不是重复纯DTO/mock验证：实际renderer service经过主进程固定ServiceClient、Origin/session队列、socket HTTP、共享build_app、受限PG与真实已确认策略；平台原始输入和模型输出为合成边界，原始上传复用签名执行/候选链。

### 实际检查

- Node24读取当前候选与本人COMMENT原文/父上下文→显式ASSESS→人工OPEN核验→INCLUDE。实际服务成功提交后，仅在fetch边界丢弃回执；GET原请求恢复正确`sourceVerificationId`，没有恢复时自动POST。另显式原ID重放和新ID重复纳入，数据库仅1商机、2决策记录、1分析、1核验，模型调用1次。
- 实际P11服务读取固定原文、本人作者与父作者、逐字引用、画像/来源版本；原发布时间与观察时间刻意不同，Node比对raw当前观察ID、观察/接收时间，Python再核对原始版本/观察数据库行和固定证据摘要。核验ID在原决策回执持久化中验证，不强行加入本来不含私有核验ID的共享P11快照。
- 同租户其他用户看不到私有候选/原文/原请求，不能写候选；共享P11投影仍按既定租户权限可读。其他租户不可读P11。退出后的读取、写入和原请求恢复均401；跨租户写入按既定先校验画像顺序返回`409 profile_unavailable`，同租户非owner为`404 candidate_not_found`。
- 同一一次性数据库中的独立租户夹具案例分别经真实签名上传改变来源，或确认新版画像；旧来源核验和旧INCLUDE均409，未新增商机/复核记录，不再次调用模型。
- 子Node仅允许系统运行环境及本轮HTTP测试值，不含数据库URL/管理员连接/服务端secret。token不进argv/日志，失败输出脱敏；HTTP线程和Node进程均有退出界限。受限角色明确非superuser/BYPASSRLS，候选review表RLS实际有效。

### 失败、审核与最终执行

无环境时Python3 skipped、Node1 skipped只证明门禁，不算联调通过。首次真实运行**1 failed/2 passed**：主流程走到跨租户拒绝写入，测试误期待404，实际服务先校验租户画像而返回409。核对`CandidateReviewStore._capture`后修正精确状态/错误码，未放宽生产拒绝或断言为任意失败。初始TS类型名拼写与raw绑定字段拼写在运行前类型/源码核对修正，不计产品RED。

独立SPEC发现时间来源覆盖P2：原夹具发布时间与观察时间相同，不能抓混用。补独立时间和raw/P11/数据库三方精确比对后SPEC复审PASS，代码/架构/质量另审PASS、0 Critical/Important/Minor。审核绑定Python SHA256 `55041f5868edc91e051cb3d149c3d736e186c68d626861c573d885e7a01db5d6`、Node SHA256 `69816dc2cbce91adbaec29c73a2d6b22d90959d795c8a37db486a56b0eea2080`。这是新验收代码，不把对已有产品补覆盖冒称新产品TDD实现。

根代理重建一次性PostgreSQL16隔离库，最终**3 passed/0 skipped，9.26s**；其中父Python实际执行5次Node子用例（flow一次、两个prepare/stale各两次），不相加成8项独立测试。`EXACT_TEMP_POSTGRES_REMOVAL_CONFIRMED`确认本轮专用容器已移除。Node24相关**20文件613 passed/0 skipped，8.64s**；类型退出0，生产排除构建4788 transformed/4787 graph modules、manifestHarnessReferences=0、failures=[]、existingAsarChecked=false。此前Task4的1423项不是本轮全量重跑。

可复验入口（专用PG、应用角色和Node24路径通过私有进程环境配置，不填写凭据到命令行）：

```text
python -X utf8 -m pytest -q -p no:cacheprovider --tb=short -r s tests/test_desktop_candidate_review_http_postgres.py
```

使用既有`YIKE_IDENTITY_TEST_DATABASE_URL`/`YIKE_IDENTITY_TEST_APP_DATABASE_URL`测试fixture与`YIKE_CANDIDATE_LIVE_NODE_BINARY`。没有专用环境会明确skip，不以skip作为门禁通过；不得指向生产库。

### Windows运行环境修复与边界

本机Docker原未启动；启动后Computer Use读取错误：`dockerInference`运行时套接字无法访问。正常退出失败后经官方`docker desktop stop --force`停止异常进程，确认停止后把专用run目录移至同级`run.before-candidate-review-20260910`保留，再启动成功，服务端28.3.2。未恢复出厂、删除镜像/业务卷或停止恢复后的其他业务容器。备份为本机运行文件，不入Git。测试结束只清理精确创建的临时PG。

Task1～5限定客户端工程接收已具备证据，Mac原核验ID字段修复取得Win实际消费ACK。**05G整卡、真实来源/收费模型、确认联系/回复、Windows安装发行、生产及客户试用仍未完成，整体Goal不关闭。** 后续Win继续已分配的设备HTTP/原请求恢复与来源worker，再接确认联系和回复；不把这次测试接收当产品可上线。

### Task5 最终主干接收

源码与验收提交`c0bd9f0`，正常保留远端`21f82c0`形成`152abaa11c40e9fbb5f44e39ef62a784b63c62d0`。来件净变更只含P18等历史验收文档；其间迁移改动已由原作者撤回，最终`git diff --exit-code c0bd9f0 HEAD -- desktop tests pilot migrations`退出0，未覆盖双方源码。产品源码也与基线`ca1f28a`相同，旧UI/构建证据不重新冒签。

合入后Win重新启动专用PG跑当前3案例：**3 passed/0 skipped，8.92s**，再次确认精确临时容器移除；不得与前次3项累计。凭据扫描clean、当前diff检查通过，受影响产品与测试字节未变。独立最终文档/提交边界复核PASS；其中“独立新数据库案例”的非阻断措辞已纠正为同库独立租户夹具，避免夸大隔离层级。

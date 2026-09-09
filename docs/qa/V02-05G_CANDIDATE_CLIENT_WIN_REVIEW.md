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

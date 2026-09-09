# 05G 真实候选客户端 Win 验收记录

日期：2026-09-10。原基线`c88b64b`，计划/认领`11eeb32`，正常保留Mac执行签名来件后为`0eab72a`。[实施计划](../superpowers/plans/2026-09-10-win-candidate-review-client.md)沿现有R3/R4接P07，不另做演示页。

## 当前边界

IN_PROGRESS：候选合同与实际传输尚在开发，完整P07读取、判断、人工来源核验、确认和恢复未验收。已完成的商机固定原文展示属于[05E](V02-05E_SOURCE_EVIDENCE_CLIENT_WIN_REVIEW.md)，不借其测试宣称本片完成。

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

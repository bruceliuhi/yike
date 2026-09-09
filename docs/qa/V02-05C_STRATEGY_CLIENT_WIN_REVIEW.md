# 05C 真实策略客户端分片验收

2026-09-10，CodexWin。实施基线36fef5b，正常保留Mac前端a31069f及后续共享接线aac3fe9。本文绑定本次13文件基础传输/兼容增量，不把在途原请求控制器、P19接线或整个05C标完成；[计划](../superpowers/plans/2026-09-10-win-strategy-client.md)继续执行。

## 本次交付与边界

- Task1：完整草稿→严格公开配置，保留两种来源输入、日程/研究设置、平台顺序和显式技术预算；严格核对原请求和完整服务端回执。SHA只作服务端绑定，不复制另一语言的浮点序列化算法。
- Task2：5固定IPC和单次真实service调用，保留认证、Origin、HTTP限制及错误边界；不接受任意路径、身份或额外权限。
- 新旧日程：新policyVersion=1参与摘要，旧六字段JSON/请求SHA不变；仅新版间隔相同起止拒绝，不授予调度或执行能力。
- 真实Node24→renderer service→固定主进程传输→共享FastAPI→受限PG，没有业务响应mock。使用实际newTaskDraft映射，覆盖prepare/confirm、换版409与新revision、旧回执不变、旧策略非当前、撤销和注销401。

测试身份、画像和来源内容是合成输入；仅绑定127.0.0.1的临时测试服务使用既有开发HTTP选项。没有外部平台/模型调用、真实联系、生产HTTPS、发行包或客户试用证据。策略确认不是原文证据；后者仍按[Win/Mac交接](../handoffs/V1_WIN_FUNCTION_OWNERSHIP_20260909.md#原文证据接入补充2026-09-10)实接。

## 失败与修正

1. Task1初始13项12失败/1通过；缺能力断言后实现。Task2初始14项13失败/1通过；固定路径/严格输入后通过。兼容补充初始3失败/7通过，旧形状与必填新版本联合模型修正后192项通过。
2. 独立审核发现两个P2：fc/fd开头的普通域名被误判ULA；v1间隔相同起止被接受。新反例TS 2失败/15通过、Python 2失败/2通过（190未选）后修正；旧日程保持原值。补充请求SHA断言首次误用局部_hash造成NameError，已改为明确JSON参考字节，不当产品缺陷。
3. 合入Mac共享router后，旧Node测试手动追加同路径router被默认501遮蔽：1失败/48未选，1.85s。改为消费共享build_app；第一次路径计数遗漏独立operations前缀，4不等于5属于测试错误；修正后实际Node桥接1通过/48未选，2.55s，未跳过。

## 最终根代理验证

Windows PowerShell7；Node24.19.0，Python使用`.runtime/venvs/win-device-review/Scripts/python.exe -X utf8`。PG16为每次独立临时容器，loopback端口、随机凭据；只对核实ID/名字的容器清理，最终均`EXACT_TEMP_POSTGRES_REMOVAL_CONFIRMED`，Node不接收数据库凭据。

| 检查 | 命令 / 范围 | 结果 |
|---|---|---|
| 合同/共享HTTP | `python -m pytest -q -p no:cacheprovider tests/test_research_strategy_contract.py tests/test_research_strategy_api.py tests/test_confirmed_strategy_composition.py` | 248 passed / 1.72s |
| 合同/真实PG/实际Node | 本地专用PG脚本运行`tests/test_research_strategy_contract.py tests/test_research_strategies_postgres.py`，显式提供Node24路径 | 243 passed / 17.31s / 0skip |
| Mac实际策略/判断组合复核 | 同样隔离PG执行`tests/test_confirmed_strategy_review_postgres.py tests/test_confirmed_strategy_http_postgres.py` | 37 passed / 30.83s / 0skip |
| 桌面增量/既有门禁 | `node node_modules/vitest/vitest.mjs run tests/researchStrategies.test.ts tests/researchStrategyTransport.test.ts tests/servicePolicy.test.ts tests/serviceClient.test.ts tests/ui/client.test.ts tests/ui/task-confirmation-summary.test.tsx tests/ui/task-profile.test.tsx tests/ui/task-wizard.test.tsx tests/ui/task-start-contract.test.tsx tests/ui/task-actions.test.tsx tests/taskOperations.test.ts` | 11文件146 passed / 5.92s |
| 类型 | `node node_modules/typescript/bin/tsc --noEmit`（desktop） | exit0 |

集合重叠不相加；桌面测试和类型检查时工作树同时含未接页面的Task3在途模块，不能据此升级Task3为已审核/已交付。这里没有再次全仓测试或构包。

## 独立审核与源码绑定

Task1/兼容：`store_lock_audit`独立规格及代码/架构/质量PASS，两P2关闭；TS17与Python194实际复跑通过，旧六字段嵌套配置/请求JSON与SHA保持不变。Task2：`strategy_client_plan_review`规格及代码/架构/质量PASS；Mac增量168872a..aac3fe9与当前client/Node共享入口整合再获同一非作者复审PASS，未运行PG，不冒称根代理执行证据为独立复跑。原Task2其它6文件未改。冻结源码SHA256：

```text
desktop/src/shared/researchStrategies.ts 33C49AB129064C3765094DE01343E97006270608B9BDC7F8CABACBA241501BBA
desktop/src/renderer/domain/researchStrategies.ts C711B51AF34250A36092923B6D9648C0EE909B5A23AFE2F0A5D68164BFE898B7
desktop/tests/researchStrategies.test.ts 4E23F98B18A23412F95D14E27B99035ED9CDD8C483641C0FAB15642BC73A0653
pilot/research_strategy_contract.py 21C5AAA9D24DE849F418C3A04F0662D351664AF9CDFF896C07B2AA85E66EFE16
tests/test_research_strategy_contract.py B261599221D0B4790AAB9B497C25983B0AB2A24E9D455E6EFCB4A291B58AF48C
desktop/src/renderer/services/client.ts D78EA8039E1F2176CAECB87FACA6EAF2BFD3EE322B0D4CD66444E955EB096CCF
tests/test_research_strategies_postgres.py 5F4C924F034F77E9C3A13BD2D787C296E99BBDF75EC526DE95AA9C7F1F24A610
```

后续：Task3原UUID恢复及显式确认→Task4 P06/P20保护上限和P19只读快照→05F签名执行/05G候选/05E原文证据。原文证据、多找类似、短句建联不后置；Mac继续权限受控证据投影和原收发责任。默认未验收能力不开启，Goal保持ACTIVE。

## 后续主线整合与Task3原请求恢复

Task1/2已提交`62af2ea`，正常合入Mac `1c56fc5`为`2a66fc1`并推送main，远端SHA已实际核对。Mac React单实例/Zod解释执行/CSP与smoke收紧增量经独立规格及代码/架构/质量PASS；根代理整合后5文件45 passed / 3 skipped / 904ms。3项为未提供真实坏包/原生fixture的条件测试，不作为原生通过；类型与renderer构建exit0（4765模块/253ms）。构建时含Task3在途ledger，不是干净发布包，未做Windows安装或真实原生验收。

Task3以`2a66fc1`为提交基线，只增加原请求记录/domain、页面hook及测试，既有ledger增加专属scope和只读即时getter；旧调用者前两项解构、旧启动指纹及账本格式保留。正文/资料/完整回执不进ledger；用户点击才prepare/confirm/revoke，先保存再POST；reload/编辑/切账号不恢复本地勾选。丢失草稿时以调用前保存的原请求SHA核对服务端历史，`historyReceipt`只读，不变成新许可。

TDD与修正：纯domain6项、ledger新增1项、hook首批7项分别先RED后GREEN。hook显示状态的TypeScript联合推断错误由明确State类型修正；新增同用户空间/服务切换测试复现迟到recheck仍返回true，改为检查当前作用域。独立SPEC再发现共享ledger撤销未失活、已核对历史未暴露、retry未先查询三项P2；新用例6失败/17通过后修正为精确activationRecord绑定、返回前读取最新持久记录、独立historyReceipt，以及先查原operation。唯精确request_not_found/404、原摘要仍匹配、持久记录可靠时，用户显式重试才同UUID POST；503/超时不重发。新增getter先1失败后15通过，验证无需等待React重渲染即可看到新锁且损坏不读旧内存冒充。

最终根代理：`node node_modules/vitest/vitest.mjs run tests/strategyConfirmation.test.ts tests/ui/strategy-confirmation-hook.test.tsx tests/ui/operation-ledger.test.tsx tests/ui/task-start-contract.test.tsx tests/ui/task-recovery.test.tsx tests/ui/tasks-draft-resume.test.tsx tests/ui/outreach-reconciliation.test.tsx tests/ui/followup-ledger.test.tsx tests/ui/candidates.test.tsx tests/ui/r4-coverage-plan.test.tsx`（desktop）为**10文件135 passed / 7.31s**，typecheck exit0。独立测试补充作者最后hook23通过/1.74s，不与135相加；其最初fake-timer设置导致一次测试超时，调整为真实初始化后测试30秒等待，不当产品缺陷。以上只证明UI控制器与既有门禁；Task4页面尚未调用该hook。

独立`strategy_client_plan_review`已完成Task3规格及代码/架构/质量复审PASS，三P2关闭，无新增阻断；本轮只读审核未复跑测试或PG，执行证据仍归根代理/测试作者。冻结6文件：

```text
desktop/src/renderer/domain/strategyConfirmation.ts 55253AA39A19EC71D6DDA3CFF6F8DAF344A1D845699343691805A1CA8581D6FF
desktop/src/renderer/pages/tasks/useStrategyConfirmation.ts 2F4D1AF0AEC79F0AAF3E126F35F828AC657410C877D986C1026D641CFA492969
desktop/tests/strategyConfirmation.test.ts 8974BC34A0655099779901681109A60F930C9F32F5AACDF38E4EF37DFA42C11F
desktop/tests/ui/strategy-confirmation-hook.test.tsx 9085868A7CF8EEE6E7B4561E8E6CDC1F3B954F04644B59FC0170AA1E9D8681DD
desktop/src/renderer/app/operationLedger.ts 3E83E9AA9ADC5E51E2AF37867E3AF4E5A8EE16518F634C367CF08AC895FC09C8
desktop/tests/ui/operation-ledger.test.tsx 10C9F2A31304B575B2F7A016C29EF8D1F0ACF1837FCCCAC6E4E901406B91ECA6
```

下一动作仍是Task4 P06/P20/P19接线和实际视口走查；整个05C、原文证据实接、来源/签名执行、收发与Goal没有提前完成。

## Task4 现有确认页接线（基线4251e75）

上述Task4未开始/未接线为先前时点。本片新增可选executionLimits草稿字段与高级输入，明确采用建议100条/900秒后才写入；空值保留、范围校验、不从搜贝换算。编辑增加revision，旧taskFingerprint与启动协议不改。P19使用Task3控制器：点击准备→完整服务端快照→勾选复核→显式确认；查询/原键重试/撤销和历史只读继续受原账本校验。全部绑定配置可展开，包含非生效来源、单次保留但不调度的日程、所有研究设置、平台顺序及执行上限。

独立实施前契约核对明确：当前没有05F签名适配，新服务存在时必须在按钮和start处理函数拦旧startTask/taskOperations.start，且不写旧启动账本；不能把当前策略recheck当签名执行授权。旧注入适配没有新服务时保持原受控路径。确认勾选绑定已展示回执ID/策略ID/双SHA和当前草稿，不由历史查询自动恢复。

测试与失败：实际TaskWizard测试首个RED为缺准备按钮，后实现；执行上限schema4个反例、组件/helper4个行为反例先失败后修正，测试重复role查询歧义和6条nullable TypeScript错误分别修正，不当产品安全漏洞。13项新增页面测试覆盖主动确认、完整字段、501/不完整服务不降级、丢回包查询、同UUID重试、重载再确认、撤销未知、改名/真实修改上限保留其他配置且修订递增；新增预算接线项在已有实现首次通过，不伪报RED。隔离visual夹具先无有效配置失败，后严格回执往返通过；不触达任何外部来源。

根代理最新检查（Node24.19，desktop）：

| 范围 | 结果 |
|---|---|
| strategy-confirmation(当时12项)/strategy-execution-limits/strategy-confirmation-hook/strategyConfirmation/task-wizard/task-start-contract/task-recovery/tasks-draft-resume/r4-coverage-plan，以及tests/visual | 16文件156 passed / 7.65s |
| 最终strategy-confirmation(13项)+task-confirmation-summary+r4-research-usage | 3文件34 passed / 5.27s |
| tsc --noEmit；生产renderer build | exit0；4770模块/245ms |
| tests/visual/verify-production-exclusion.mjs | graph4769，manifestHarnessReferences=0，failures=[]；existingAsarChecked=false，不是安装包验收 |

重叠集合不相加；没有无关全仓复跑。Task1/2实际Node→共享HTTP→PG源码本片未修改，继续引用62af2ea及上节绑定的真实往返，不声称本轮再次运行PG。页面用实际生产组件/控制器与显式内存服务测试；尚无真实来源、计量、签名启动或客户试用成绩。

真实Edge隔离入口`?scenario=P19&strategy=confirm`已操作准备、展开全部配置、勾选/确认、返回编辑记录37→38、切持续监控并返回P19，确认失效且913秒和Asia/Shanghai保留。1440×1000：root1440、main1232/1232；960×600：root960、main776/776、展开details728/728，未见横向溢出；小窗口控件可见、长摘要换行，保留既有滚动/固定页脚。仅favicon404，无页面运行异常；首次HMR因编辑触发测试草稿beforeunload，接受后重新走查。浏览器及本次Vite已关闭。截图/原始快照保留在本机忽略目录`.runtime/output/playwright/strategy-confirmation-20260910/`，并非跨设备已接收：

```text
page-2026-09-09T18-10-57-287Z.png 26F87A6BCE05C62BA5462A228F2E6990F8B09EAE1225557E67CA817649CEA8BB
page-2026-09-09T18-11-13-729Z.png 6BB7B53B34FD8B558731F71C20E49C309EA5D2698279831A46969A64739A9390
page-2026-09-09T18-12-59-521Z.png 6199E74D3289D58E0E22807D0CC192168BB1CBF910F444177C2F1E2F303443F4
```

Task4独立`strategy_client_plan_review`已完成SPEC及代码/架构/质量两阶段PASS，无需修复的P1/P2；审核者只读源码和测试设计，未冒充根代理的实际运行。15个改动/新文件已逐一SHA256核对，以下列核心绑定；结论不覆盖05F、原文证据展示或整个05C完成：

```text
desktop/src/renderer/pages/TaskWizard.tsx 4F2877DE54E1AE28CB491BA31455BA82615BE8E66CD7B2E86E38E185EDBFBE36
desktop/src/renderer/pages/tasks/StrategyConfirmationPanel.tsx 1685873BC936A9AFE63BDF93B6FF6BEE3540B68FC6DED8A5DDC5A4AE592F8626
desktop/src/renderer/pages/tasks/StrategySnapshotDetails.tsx 2167FD5694C01DA082FCB704D467D83938A93BAF033479E0344CCFEFC9B27526
desktop/src/renderer/pages/tasks/TaskConfirmationSummary.tsx 521251DC911A8CF7DFE3F196183C996D141C415D9E204F04877A97274D7CE0A4
desktop/src/renderer/domain/strategyExecutionLimits.ts 73EE736554DB0E2ADAECDB0BF51CF8DF01275B6B0FD46B591FCCE72ADD275169
desktop/src/renderer/pages/tasks/StrategyExecutionLimits.tsx C5A3387279B9F523DAC481E04E6DF6C8B025782AB20DCC8BAB476C1E810D78CB
desktop/tests/ui/strategy-confirmation.test.tsx 9AADBA926E2FE8649EFE3809A1AE47CDB76548D4F34101D62D1F4F696BFEC78C
desktop/tests/visual/strategy.ts 101EDF07FA980791CB3EFC1B476C698989867146E5EA0CBA665F4FFB2946B148
```

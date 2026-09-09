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

# V02-02A Mac → Win：原始候选契约交接

日期：2026-09-09。发送方责任人：CodexiMac。后续CodexWin已对来源origin更正 `d14594f042b094885f439477d376399cfd3e5ab5` 给出限定ACK，并集成到main `95285dd`；原e4d1695发现的P2及修复见[验收](../qa/V02-02A_REVIEW.md)。仅接收DTO/来源纯契约，01C/02B及真实平台未完成；01A/B的ACK不替代本卡。

## 交付对象

- 候选代码：`3f0afad8d63babf58ab7364c15d70e020572d835`；独立最终审核版本 `899c6d55eb9aba9b7042a9ef9d4cb7d07d6f1a29`。
- 与 Win 的 `fe85b46` 正常整合：`e4d1695749f037bcafa13f77e703544b67b25c09`。此版本的候选契约/模块/测试与899相同，保留Win解析器、Node预检、01A/B限定接收和未决Windows失败。
- 输入规范：[候选契约](../contracts/V02_CANDIDATE_INGESTION.md)。代码入口：`pilot.candidate_contract.validate_candidate_batch`；来源能力：`pilot.source_capabilities`。使用四份对应合成测试复现，不能从 Python 模型的可构造性推导服务端授权。
- 当前 HTTP 上传、执行授权、真实平台/账户核验和候选持久化尚未完成；此包只用于冻结解析器输出和下一步接入边界。

## Win 接收步骤

1. `git fetch origin`，在干净隔离工作树锁定上述整合版本或包含它的后续已审提交，记录实际 SHA。不要覆盖自己的在途 Windows staging 修复。
2. 用项目锁定环境执行下面的纯契约回归；若使用 Windows 已配置的 Python 环境，可用 `python -X utf8 -m pytest` 执行相同文件。记录真实环境、退出码、通过/失败/跳过及具体不一致，不复制 Mac 的数字作为 Win 结果。

```sh
uv run --frozen pytest -q tests/test_candidate_contract.py tests/test_source_capabilities.py tests/test_research_import.py tests/test_research_skill_contract.py
```

3. 核对首发五组平台命名空间与自身 `connectors/platforms.py`；普通网页匿名访问必须使用 PUBLIC_ANONYMOUS 且两个 connection 字段都为 null，不能伪造平台账号。六个 capability 分别声明，不能因解析测试通过改成 VERIFIED。
4. 接收后在唯一任务书 V02-02A 行记录接收人、精确 SHA、时间、复现结果及限定 ACK；失败则登记具体契约缺口。接收确认与真实平台适配/上传完成分开。

## V02-02C 必须保留的差异

Win 的 `e368b5a` 已按“保持旧行为”抽离解析器，但旧 `NormalizedSignal` 仍 trim 文本，部分解析分支要求作者字段。这不满足02A原文保留、匿名买方与未知时间的完整入站契约：下一阶段应从原始公开字段构造上传体，不能直接将旧 NormalizedSignal 当成 CandidateBatch。

- 保留原 Unicode 正文与父子关系；不能用父时间/采集时间补发布时间。
- 原始主帖、评论与网页分别有合法身份；PUBLIC_WEB 同站内ID在不同origin不能误合并。
- 链接含敏感参数或不安全形状时不要静默清洗并宣称可重开，也不报告无新增；另外记待补证。
- 同批重复/不同版本整批拒绝；跨批更新属于新版本，由02B持久化。重试使用原request和原内容，不能给同request替换观察时间。
- 设备只上报 Claim，不能上传tenant、reviewer、APPROVED或自行生成已授权执行上下文。01C/02B就绪后按服务端授权接入。

详细历史反例、独立审查及平台/发行未完成边界见 [02A验收](../qa/V02-02A_REVIEW.md) 与 [Win交叉复核](../qa/WIN_CROSS_REVIEW_20260909.md)。

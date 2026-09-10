# 已确认排除词贯通采集

基线：`490f56e9c18b701a16c3e4b60d68b2cdd8620eb4`。本批落实已批准的 [搜索条件设计](../../../design/v02-suite-r3/AI_SEARCH_CONDITIONS.md)，不改变完整 V0.2 目标。

## 断点与验收

搜索建议允许排除词，但普通任务/UI、服务端能力、原生 controller、Python driver 适配层都拒绝非空排除词；采用有效建议后无法启动。修复必须贯穿各层，不能仅隐藏错误或静默删除用户条件。

## Global Constraints

- 已确认策略及其摘要保持原样；只读取确认快照里的排除词，不能接受 renderer 临时覆盖。
- 三平台既有单次和受控监控搜索支持排除词；其他模式、账号核验、上限、取消、恢复和权限围栏保持。
- 本机适配层在来源 schema 校验及去重冲突检查之后过滤。POST 匹配正文或标题；COMMENT 只匹配自身正文，不匹配父帖、作者、URL、query。每个字段分别匹配，不跨字段拼接；按 Unicode NFC、非地区化小写的字面子串匹配，不解释正则。
- 原文、标题、链接、query 不改写。原始返回记录先扣除本轮采集预算，过滤/重复不返还预算，不扩大补采。正常全部排除是成功空结果，不是来源失败，也不是有效商机。
- 旧无排除词行为不变。所有重复来源的内容冲突（包括将被过滤者）仍拒收，不因过滤绕过冲突保护。
- UI 简短说明本机返回后过滤及评论主体边界；不声称平台搜索原生支持这些排除词。不新增平台或改变布局。
- 无外部模型/平台调用、客户数据或消息发送；定向测试、一次独立审核、一次 renderer build，均不是 Windows/真实平台/UAT 证据。

## Task 1: TypeScript 执行和用户入口

在现有 `desktop/src/main/pythonCollectionDriver.ts` 中实现上述过滤；解除 `foregroundCollectionController.ts` 三处和 `renderer/domain/task.ts` 的非空排除词拒绝，保留其他条件。在任务关键词/排除词现有编辑区域加入准确短说明，复用既有组件。

先写最少失败用例再实现：POST 标题/正文、COMMENT 自身/父帖区分、NFC/大小写、全部排除且不补采、被排除重复版本仍冲突。补现有 controller/domain 测试验证非空排除词确能进入原执行路径（单次及监控），避免只测孤立过滤函数。测试仅改动相关文件；执行 tsc，不重复构包，根代理完成唯一 build。

根代理独立负责 Python `pilot/foreground_collection.py` 与其测试，以及文档/整合。双方不要改对方文件。提交前通知根代理；仅 add 本任务显式文件，不 amend、不推送。最终提供源码 SHA、精确测试命令/结果及边界。

## 实施与验证

源码：Python `65c574f`；TS `54e577bf87fe3b8ab8c05ccb77fdd89afd0d6428`；补齐旧断言/空结果用例后的候选 `8ec10057a28c24aa2ebf49a583eb720704323cd1`。普通任务中的合法排除词现可通过既有单次/受控监控入口，原生 driver 执行上述过滤。后端只准入合法配置，不声称平台支持负关键词搜索。

- Python：`python -m pytest tests/test_foreground_collection.py -q`，初始 2 failed/18 passed，修复后 20 passed。
- TS：`vitest run tests/pythonCollectionDriver.test.ts tests/foregroundCollectionController.test.ts tests/ui/task-domain.test.ts tests/ui/task-wizard.test.tsx`，87 passed。先出现缺实现失败及测试 API 命名错误，修正后通过。
- 补测：`pythonCollectionDriver.test.ts -t "returns a successful empty result"`，1 passed/30 未选；`foregroundCollectionRenderer.test.ts`，22 passed。后者修正遗留“不支持排除词”的过时断言，不重跑无关集合。
- `tsc --noEmit` 通过；`vite build --config vite.renderer.config.ts` 在 `8ec1005` 一次通过，仅 renderer 构建，不是 Windows 安装包。
- 独立审核：非作者 `collection_exclusions_final_review` 对完整 `490f56e..8ec1005` 给出规格/代码/架构质量 GO，无阻断；复用上述定向证据，未重复测试或构包。本批不重复 PostgreSQL/迁移/全量套件，无平台/模型/客户数据操作，不替代真实来源、Windows、生产或跨行业 UAT。完整 Goal 保持进行中。

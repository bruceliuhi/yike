# 原生链接输入与范围校验实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans; TS/Python 实现可按互不重叠文件分工，整批一次独立审核。

**Goal:** 让新建纯链接任务在准备阶段得到一致、严格的原生目标识别与范围校验，保留历史快照，不提前开启采集。

**Architecture:** 独立纯函数解析公开原生 URL，按选中平台生成目标计划；只在新任务 PREPARE 使用范围校验。快照／回执结构不加字段，执行 capability 保持关闭。

**Tech Stack:** Python 标准库＋Pydantic；TypeScript＋Zod；pytest、Vitest。

## Global Constraints

- 采用相邻 design 的精确路由、长度和脱敏约束，所有错误只含固定代码 INVALID_NATIVE_COLLECTION_LINK / INVALID_NATIVE_LINK_SCOPE，不回显 URL。
- 输出四字段 platform、kind、external_id、canonical_url。不联网、不解析 DNS、不执行上游、不访问账号。
- 双端共用 tests/fixtures/native_collection_links.json 的正反例。原配置 bytes 和历史 snapshot 哈希不改写。
- 无 capability、生产、外发或 Windows 已通过声明。

### Task 1：双端纯函数与新建任务校验

文件：创建 pilot/native_collection_links.py、desktop/src/shared/nativeCollectionLinks.ts、tests/fixtures/native_collection_links.json、tests/test_native_collection_links.py、desktop/tests/nativeCollectionLinks.test.ts；修改 pilot/research_strategy_contract.py 和 desktop/src/shared/researchStrategies.ts。历史恢复分离同时涉及 desktop/src/renderer/domain/researchStrategies.ts、desktop/src/renderer/domain/strategyConfirmation.ts 与 desktop/tests/strategyConfirmation.test.ts。

接口：Python parse_native_collection_link(value) -> dict；plan_native_collection_links(platforms, links) -> tuple[dict,...]。TS parseNativeCollectionLink(value: unknown) -> NativeCollectionLink；planNativeCollectionLinks(platforms: readonly string[], links: readonly string[]) -> NativeCollectionLink[]。无导入数据库、运行时或 UI。

- [x] 创建共用 fixture：每平台内容和作者、知乎三类内容、XHS 双参数／无参数、跟踪参数归一化；反例覆盖短链、主机混淆、路径越界、编码分隔符、重复／秘密参数。
- [x] 编写并运行失败测试：逐例精确比对输出；同目标不同 query 拒绝；选错平台、缺少已选平台、超数量拒绝。
  ```python
  assert parse_native_collection_link(case['url']) == case['expected']
  with pytest.raises(ValueError, match='^INVALID_NATIVE_LINK_SCOPE$'):
      plan_native_collection_links(['DOUYIN'], ['https://www.bilibili.com/video/BV1d54y1g7db'])
  ```
- [x] 实现 design 中白名单解析；固定错误，不打印输入；XHS 参数在精确原生路由通过后才允许。
- [x] Python PrepareStrategyRequest after validator 与 TS prepareStrategySchema refinement 对 source=links/research=null 调用计划；snapshot 不套用新准备门禁。Python check_links 对可解析 XHS 签名链接采用狭窄例外，其余仍走旧 URL 校验。
- [x] 定向验证：pytest tests/test_native_collection_links.py tests/test_research_strategy_contract.py；Vitest nativeCollectionLinks.test.ts researchStrategies.test.ts；tsc --noEmit。
- [x] 固定提交后独立审核整批，修复必要问题，更新任务书；按既定流程合入 main。

## 后续交付接口

下一批执行器只能使用本批明确的 kind 与 canonical_url，仍须复核确认快照。工作清单与安全要求见相邻设计“后续批次的执行要求”；运行时的具体 patch 实施计划必须在读完各平台受控源码后另写，不把本输入计划冒充完整执行计划。

## Evidence

Python RED：纯链接抖音任务错误接受 B站 URL；合法 XHS 签名公开链接在 PREPARE 被旧 token 检查拒绝（2 failed）；纯规划器的功能存在断言失败（1 setup error）。GREEN：`/tmp/yike-aliyun-sdk.DYc7GB/venv/bin/python -m pytest -q tests/test_native_collection_links.py tests/test_research_strategy_contract.py`，最终共289 passed（84新＋205原契约，0.44秒）。所有输入离线，不读取浏览器、秘密或平台，也没有模型调用。

TS RED：新测试因模块尚不存在而失败，原 researchStrategies 21 passed；GREEN：Node24.19.0 执行 `node_modules/vitest/vitest.mjs run tests/nativeCollectionLinks.test.ts tests/researchStrategies.test.ts`，2 files / 100 tests passed（268ms）。根执行同版 `node_modules/typescript/bin/tsc --noEmit`，exit0 无诊断；`git diff --check` 通过。TS 实现与测试由独立客户端 Agent 完成，最终审核另由非实现者进行。

首次独立整批审查固定 `c94d8f2`，NO-GO：1个P2、无P1。新建原生门禁被历史请求摘要／回执恢复复用，导致旧版合法普通链接的 pending 无法恢复；快照结构可读的测试不足以覆盖实际恢复链。非实现者离线最小反例证实，未联网、未重跑整套。按设计分离历史严格结构与新动作门禁，修复／复核接续记录在下方；首次失败不删除。

修复：`prepareStrategyRecordSchema` 保留历史 exact 结构，用于原请求摘要和回执匹配／恢复；新建记录、PREPARE重试及 renderer/main POST 保持新门禁。旧 pending 按独立 canonical 摘要的真实恢复函数回归，先1 failed/6 passed，再3文件107 passed；恢复修复后 tsc exit0。根另发现公开参数编码可能让短输入变成超过2048字符的 canonical URL，两端各一个定向失败确认后补输出长度检查。最终合并改动的目标验证：Python289 passed（0.52秒）、TS3文件107 passed（391ms），不重复模型/数据库/构包。

本输入批没有任何链接采集执行、生产或 Windows 验收证据。

最终独立复核固定 `f695667c16e81208ee9d679c74bb05fc3b48de04`：GO，可合 main；原P2关闭，无新增P1/P2，复用定向测试和类型检查，不重复运行。该结论只覆盖输入与历史恢复，不覆盖后续执行器。远端 `3b23658` 的纯Windows/部署交接已正常合并，未覆盖其同源候选证据；当前固定安装包不因此自动更新。

收尾同步远端 `1f597f6`：Win侧已独立GO的页面ASSESS90秒等待修复，与本批文件不重叠；沿用其62项及类型检查证据，在合并结果仅补实际hook文件25 passed（1.83秒）。这是受控延迟响应，不是实网模型或客户UAT。两端源码正常合并，未在本任务重新部署或构包。

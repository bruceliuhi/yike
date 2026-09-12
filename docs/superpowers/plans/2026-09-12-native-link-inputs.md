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

文件：创建 pilot/native_collection_links.py、desktop/src/shared/nativeCollectionLinks.ts、tests/fixtures/native_collection_links.json、tests/test_native_collection_links.py、desktop/tests/nativeCollectionLinks.test.ts；修改 pilot/research_strategy_contract.py 和 desktop/src/shared/researchStrategies.ts。

接口：Python parse_native_collection_link(value) -> dict；plan_native_collection_links(platforms, links) -> tuple[dict,...]。TS parseNativeCollectionLink(value: unknown) -> NativeCollectionLink；planNativeCollectionLinks(platforms: readonly string[], links: readonly string[]) -> NativeCollectionLink[]。无导入数据库、运行时或 UI。

- [ ] 创建共用 fixture：每平台内容和作者、知乎三类内容、XHS 双参数／无参数、跟踪参数归一化；反例覆盖短链、主机混淆、路径越界、编码分隔符、重复／秘密参数。
- [ ] 编写并运行失败测试：逐例精确比对输出；同目标不同 query 拒绝；选错平台、缺少已选平台、超数量拒绝。
  ```python
  assert parse_native_collection_link(case['url']) == case['expected']
  with pytest.raises(ValueError, match='^INVALID_NATIVE_LINK_SCOPE$'):
      plan_native_collection_links(['DOUYIN'], ['https://www.bilibili.com/video/BV1d54y1g7db'])
  ```
- [ ] 实现 design 中白名单解析；固定错误，不打印输入；XHS 参数在精确原生路由通过后才允许。
- [ ] Python PrepareStrategyRequest after validator 与 TS prepareStrategySchema refinement 对 source=links/research=null 调用计划；snapshot 不套用新准备门禁。Python check_links 对可解析 XHS 签名链接采用狭窄例外，其余仍走旧 URL 校验。
- [ ] 定向验证：pytest tests/test_native_collection_links.py tests/test_research_strategy_contract.py；Vitest nativeCollectionLinks.test.ts researchStrategies.test.ts；tsc --noEmit。
- [ ] 固定提交后独立审核整批，修复必要问题，更新任务书并正常推送 main。

## 后续交付接口

下一批执行器只能使用本批明确的 kind 与 canonical_url，仍须复核确认快照。工作清单与安全要求见相邻设计“后续批次的执行要求”；运行时的具体 patch 实施计划必须在读完各平台受控源码后另写，不把本输入计划冒充完整执行计划。

## Evidence

尚未执行测试或完成独立审核；尚未支持链接实际采集。

# 待办、模板与独立回复入口验收

日期：2026-09-10。归属 V02-05A；保持已确认 R3/R4 页面结构、品牌与平台 Logo。最终源码候选 **4eb1bb88b97d5f1d9ff3db569d80f9d9e79855b4**。本片完成前端交互与构包，Mac 锁屏使新增页面的可见对照尚未执行；05A 与完整 Goal 继续进行。

## 实际变化

| 页面 | 已实现行为 |
| --- | --- |
| P02 工作台 | 同一用户切客户空间或空间版本，旧待办立即失效；迟到的旧请求不能覆盖新空间或提供旧对象入口。 |
| P05 任务模板 | 保留人工需求类型、搜贝、来源/时间/模型调用及执行上限；旧报价、授权、请求与溯源不随模板复用。仍生成新任务并重新估算、确认；祖先未决请求保护保留。 |
| P14 关联回复 | 新增轻量商机选择器。精确商机详情验证后可读匹配回复，不要求先有人工记录，也不以列表漏项判为无权。明确选择无目标才读未匹配集合；详情失败不扩大查询。 |
| P14/P15 跟进 | 通道读取和人工记录各自处理失败；可从已验证回复目标添加事实，保存和取消保留目标与标签。日期、标签或商机选择不被迟到列表覆盖；已读不虚构人工登记。 |

生产仍使用原人工 facade；可选结构化回复服务尚未接入生产。真实回流、已读同步、服务端原请求幂等及提醒不能由 TEST 夹具证明。开发规则见[跟进契约](../../UI_FOLLOWUP_CONTRACT.md)与[任务模板契约](../../UI_TASK_OPERATIONS_CONTRACT.md)。四个未提交 raw 辅助草稿未纳入本片。

## 最终候选验证

- **108 文件通过 / 1 文件跳过，1253 passed / 22 skipped**：[完整日志](logs/final-full-tests.log)、[精确调用](final-test-invocation.json)、[330 项桌面输入](final-test-source.json)。包含实际坏 ASAR 反例；这是桌面范围，不是全仓或真实服务验收。
- [类型检查](logs/final-typecheck.log)、[Mac arm64 构包](logs/final-mac-build.log)、[严格包内 smoke](logs/final-packaged-smoke.log)、[生产 TEST 排除](logs/final-production-exclusion.log)通过。
- 从 `git archive 4eb1bb8` 在独立目录构建；[构建输入](final-build-inputs.json)逐项与提交字节相同。构包没有覆盖此前正在运行的旧 `.app`。当前构建包保存在 `desktop/out/reply-entry-4eb1bb8/`，未将二进制加入 Git。
- [包结构](final-package-structure.json)与[包绑定](final-mac-package.json)核对：ASAR `72b597705c7fde8a1bd80a5b3134c48373a453658dca0c8f87cc0fdf56056c99`；ZIP `c203b93e9212d0af93ddff3bdc8ac6fed17cf9cba2a606ed270ee24b357d99d7`；ZIP 内 ASAR 与 `.app` 相同。
- 严格 smoke 运行真实包内 main/preload/renderer，核对实际页面、隔离设置、固定 IPC 与临时文件写入；其中对话框为测试替身，不替代原生文件选择器或用户可见退出验收。

## 独立审核与失败保留

1. **098ce6b 工作台**：作者 Popper，[非作者审核](reviews/yike-workbench-scope-independent-098ce6b.md) 4 项通过。旧实现的[4 项失败](logs/yike-workbench-queue-scope-red-20260910.log)和[相关通过](logs/yike-workbench-queue-scope-green-20260910.log)保留。
2. **dd09d0f 模板**：作者 Hubble，[非作者审核](reviews/yike-template-research-review-dd09d0f.md) 20 项通过。[原 7 项失败](logs/yike-template-research-red.log)及[相关 86 项通过](logs/yike-template-research-green.log)各自保留，不相加。
3. **53d506b 回复入口**：root 实现；Peirce 的独立入口反例在原 `27ed499` 为[12 失败 / 1 通过](logs/yike-followup-reply-entry-red-27ed499.log.gz)。旧夹具补齐精确详情接口后通过；[首次集成失败](logs/yike-reply-integration-first.log.gz)未删除。路由标签异步覆盖的[失败](logs/yike-reply-target-final-first.log)修正后[70 项通过](logs/yike-reply-target-final-second.log)。[架构审核](reviews/yike-reply-architecture-53d506b.md)的 21 项范围不包含后来发现的日期反例。
4. **4eb1bb8 最终修复**：独立[日期晚到反例](logs/yike-reply-final-review-date-red-53d506b.log)揭示窄 P2，root 把路由重置移到同步意图处理，并使本地交互阻止旧列表重新定位。[75 项独立定向](logs/yike-reply-final-review-green.log)、[最终代码](reviews/yike-reply-code-4eb1bb8.md)及[架构差量](reviews/yike-reply-architecture-final-4eb1bb8.md)限定复核通过，本片无剩余已发现 P0/P1/P2；不表示整个产品没有缺口。

正常保留远端 `eb507bf` 为 **ffd7d80**，未改对方后台/部署代码。[兼容性记录](reviews/yike-reply-architecture-53d506b.md)核对双方历史和文件。该修复前候选的[1248 passed / 22 skipped](logs/full-tests.log)、[调用](test-invocation.json)、[输入](test-source.json)、[构包](logs/mac-build.log)和[smoke](logs/packaged-smoke.log)只是历史结果，不当作 4eb 的最终验收。后台新增的真实 PostgreSQL/HTTP 检查属于原责任人，本片未替代复验。

[最终交付质量核对](reviews/yike-reply-quality-4eb1bb8.md)限定 PASS：独立验证输入、包字节、ZIP 内 ASAR、渲染资源、压缩原件与本地链接；不重测或扩大真实服务、可见交互、Windows 的验收范围。

## 待补可见验收

本轮 `cua.getState()` 返回 Mac 锁屏、自动解锁失败；没有绕过锁屏或复用旧图作为新截图。新增 P14 选择器尚无同视口同状态的参考/实际对照；所有旧图保持其原提交及构建绑定。

新增 TEST 场景参数 `?scenario=P14&state=populated&capabilities=complete&followup=replies-only`，初始人工列表为空，匹配与未匹配回复分开；[28 项测试](logs/yike-followup-replies-only-tests.log)与类型通过。最终4eb的[隔离视觉构建](logs/final-visual-build.log)和[静态入口绑定](test-preview-build.json)已更新到18794，旧构建另存保留。这仅为后续可见验收准备的内存场景，尚未在浏览器实际走完。

解锁后依次核对：无人工记录查看匹配回复、切换未匹配集合、已读不新增人工行、添加/取消/保存返回、迟到列表不重置过滤；再做目标分辨率下同状态对照及新 `.app` 冷启动/退出/重启。当前 HTTP 可达、编译和包内 smoke 均不能替代这些可见检查。Windows 实机、真实结构化回复、签名公证与完整页面状态矩阵仍分别待验。

两份较长失败日志以 gzip 无损保存，[摘要与往返校验](compressed-logs.json)保留解压字节和哈希；其余原始日志保留工具输出的行尾空格和空行；源码、Markdown 与 JSON 单独执行差异格式检查，不改写失败证据。

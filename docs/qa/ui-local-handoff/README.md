# 本机资料与任务返回上下文验收

日期：2026-09-10。范围为 05A 已批准页面的日常交互修复。产品候选为 **fcae33e62f77d38208a0b3eaf97028d337000acc**（P04 `d66d487`、任务返回 `315d590`，正常合入远端 `bbe2e20`）。最终测试提交 **d816a9d5eb56ed9dd178fc42937bbd47d8227a7c** 仅调整旧测试的计时起点，产品字节不变。构包阶段 Mac 锁屏，本片完整可见验收尚未完成；用户再次“继续”后桌面已恢复可操作，接续可见核验。

## 本片行为

- P04：保存首个画像后，本机资料仍可查看、编辑和删除。“带入当前画像”仅预填编辑窗，人工保存才同步；取消不写，原稿保留。重复带入同一目标使用同 materialId 和当前 expectedVersion，不自动解析或提升引用权限。
- P06/P09/P16/P18：查看平台范围、连接账号或检查执行设备后，可沿原任务返回；保留步骤、监控模式、重复查询参数及任务 ID。P09 的原标签与选中平台由独立 AppProvider/hashchange 往返反例验证，非法值只回退到本任务实际支持的平台及已知标签。
- 保持既有 R3/R4 布局和组件，不增加新导航页。资料服务仍为可选契约，普通生产适配器尚未提供；隔离 TEST 验证不代表真实同步后端已上线。

## 原始失败与修复过程

- P04 独立真实组件反例：保存首画像后找不到原本机资料，1 failed。原日志 [RED](logs/yike-material-local-handoff-red-20260910.log)；修复后的初步相关 [64 项](logs/yike-local-handoff-focused.log) 与 [类型检查](logs/yike-local-handoff-typecheck.log)通过，最终候选另记。
- 任务返回最初 2 项失败：[RED](logs/yike-task-context-return-red-a08751d.log)。初步 [94 项通过](logs/yike-task-context-return-focused-a08751d.log)只证明路由及任务草稿。独立复核再发现 P09 内部 tab/platform 重置，[原 2 失败 / 2 通过](logs/yike-monitor-return-independent-red.log)保留；修复后 [真实 AppProvider 4 项](logs/yike-monitor-return-real-provider-green.log)与作者相关 [94 项](logs/yike-task-context-return-focused-final-a08751d.log)通过。初次独立 RED 使用 mock context，最终改成真实 AppProvider 异步卸载/重挂，不把它们冒充完全相同的测试源码。

## 可见验收边界

构包与源码审核阶段 CUA 返回 Mac 锁屏且自动解锁失败；用户再次“继续”后，getState 与产品 getTab 已成功，锁屏条件已解除。没有绕过锁屏、把 HTTP 可达当作页面检查，或用旧图绑定新提交。P04 资料带入、P09 实际往返、新原文证据及最新包冷启动/退出/重启仍待接续同状态、同视口可见验收；Windows 安装/实机和真实渠道分别待验。

已有 [Windows 手工验收模板](../../../desktop/docs/WINDOWS_ACCEPTANCE_TEMPLATE.md) 与构建脚本继续沿用。完整 05A/Goal 不因本片通过而关闭。

## 独立审核

- [P04 独立审核](reviews/yike-material-local-review-d66d487.md)：5 套 / 40 passed，初次、重复带入、取消与空间切换保护通过；首次测试点击 loading 中的 disabled 按钮属于夹具准备问题，调整为等待可点击后触发。
- [任务返回独立审核](reviews/yike-task-context-return-final-review.md)：发现并关闭 P09 局部选择重置，315d590 与整合提交的 8 项受审文件字节相同。
- [整合兼容审核](reviews/yike-local-handoff-integration-fcae33e.md)：本地 17 / 来件 38 文件无交叉覆盖；双方字节保留。真实客户端详情现要求 source_evidence，缺失或损坏显示读取失败，P14 不转为无匹配或扩大查询。签名准备不替代客户端执行、搜贝扣费或真实来源。

这些审核分别绑定各自范围；对方原文/签名的真实 PostgreSQL、Windows 浏览器记录保留原作者归属，未在本片重跑或冒认。

## Mac 产物与预览

从 `git archive fcae33e` 在独立目录构包；[342 项桌面输入](final-build-inputs.json)逐项与提交相同。[类型检查](logs/final-typecheck.log)、[Mac arm64 构包](logs/final-mac-build.log)、[严格包内 smoke](logs/final-packaged-smoke.log)和[生产 TEST/fixture 排除](logs/final-production-exclusion.log)通过。[包绑定](final-mac-package.json)记录 ASAR `6ef0d95e89d0f7f3653d3f21eb35d8884d60f876f2778b36857be723f80874e0`、ZIP `5ff63633c3b32178a4d982b6b50ba18e8f154280b8d716dcf98a09e4d54259ea`，ZIP 内 ASAR 相同。产物保存在 `desktop/out/local-handoff-fcae33e/`，没有覆盖旧运行实例或把二进制提交 Git。

包内 smoke 运行实际打包 main/preload/renderer 与 IPC、临时导出文件和退出保护；其中原生对话框为隔离测试替身，不能替代用户可见启动/退出或文件选择器验收。[37 项隔离 TEST 预览资源](test-preview-build.json)已绑定 fcae33e，18794 返回 200，旧构建另存；这也不是可见验收。资料入口 `?scenario=P04&state=populated&capabilities=complete`，P09 和 P14 继续沿已有 TEST 场景走查。

## 完整测试首轮失败

整合首次 **113 文件通过 / 2 文件跳过 / 1 文件失败，1339 passed / 23 skipped / 1 failed**：[原始日志](logs/integration-first-full-tests.log)、[精确调用](integration-first-test-invocation.json)、[输入快照](integration-first-test-source.json)。唯一失败是旧短句教练保存超时用例，第 568 行未出现超时说明；不能把首轮记为通过。原样单文件重跑 [31 项通过](logs/yike-short-coach-timeout-isolated-fcae33e.log)，后续准确原因、修正和最终整合结果另记，保留此次失败。

## 最终整合结果

首轮失败用例在 snapshotDigest 真实 WebCrypto 完成前就开始推进假时钟；保存请求的 30 秒计时可能尚未开始。仅修改该用例：等待真实 saveContact 派发信号，再断言 29,999 ms 尚未超时、增加 2 ms 才超时，保留 PENDING、迟到结果、重开与不重发全部断言。[作者说明](reviews/yike-short-coach-timeout-ready-fcae33e.md)、[独立测试差量审核](reviews/yike-short-coach-timeout-independent.md)分别保留；独立只选中 1 项通过/30 项名称过滤，不把后者当运行通过。修正不调整产品超时、mock WebCrypto 或跳过原断言。

最终提交 **d816a9d** 的完整受控桌面集合为 **114 文件通过 / 2 文件跳过，1340 passed / 23 skipped / 0 failed**：[日志](logs/final-full-tests.log)、[精确调用](final-test-invocation.json)、[342 项输入快照](final-test-source.json)。包含真实坏 ASAR 反例；新 live 原文读取用例在无指定数据库环境时明确跳过，不把对方实际 PG 结果记为此次通过。四个未提交 raw 辅助草稿未纳入受控测试或产品。

[唯一差量绑定](test-only-change-binding.json)证明 fcae33e 至 d816a9d 只有该测试文件变化，生产源码、资源和构建配置相同；因此保留 fcae33e 的已验证包，不重新打包不变产品。类型检查和[凭据扫描](logs/yike-local-handoff-secret-scan.log)通过。[最终独立交付质量核对](reviews/yike-local-handoff-quality-d816a9d.md)限定 PASS：输入/Git/实际 ASAR 与 ZIP、资源、链接及失败记录均核对一致，不扩大 Mac 可见、Windows、真实资料/回复服务或整产品上线的范围。

## 后续并发主线接收

首次普通推送因另一端推进 main 而非快进拒绝，没有强推。先正常保留 0eab72a 的三份 Win 认领文档为 249bc77，再接收 2d799bc 为 **eda1e2f0d6d2f7e4667f1e2684b5017b3cf74455**；唯一整合状态文本冲突逐段保留双方进度。独立[限定兼容复核](reviews/yike-local-handoff-incoming-2d799bc.md)通过：desktop 与 d816a9d 字节相同，pilot/migrations/deploy/tests 与来件相同。本任务不重做对方后端，也不把新独立合同当成已接通发送/回复。

根在 eda1e2f 做有界纯接收：[候选签名/登记/触达/回复合同 88 项](logs/incoming-eda1e2f-contract-tests.log)、[旧候选/设备密钥/UI 路由 90 项](logs/incoming-eda1e2f-legacy-tests.log)分别通过，不含真实 PostgreSQL。来件触达持久层的 MAJOR FOLLOW-UP、117 实库迁移/ACL和真实渠道未验边界保留，不能把本文兼容通过解读为该骨架已可生产使用。

此后用户继续触发新的实际可见检查。P04 空态留白精修和新包属于后续视觉切片，另录 `ui-visible-local-handoff`；本文件的 fcae33e/d816a9d 产物绑定不变。

后续可见结果已单独登记于[8af本片验收](../ui-visible-local-handoff/README.md)：本机稿首屏、任务/平台返回、无人工记录回复入口及新包原生退出重启已执行；本文件先前“待验”为原时点，不再视为当前零证据。旧804日志为文件未找到，并未执行32项；真实32项属于d5后的四文件定向，见新记录，不追认旧尝试。

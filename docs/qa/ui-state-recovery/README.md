# 资料、联系草稿与未知结果恢复验收

日期：2026-09-10。归属 V02-05A，继续已授权 R3/R4、搜贝及原平台 Logo；不改已有产品定位，也不把测试夹具作为客户服务。

## 本批完成与证据

首个源码候选为 **a25ba7b331e7712c4fba53b173cbbc704ec3e734**。随后正常保留远端策略确认接线 `22bae22`，合并为 `0b05e98`；只有视觉 TEST 入口的 imports 发生冲突，双方控制器均保留。跟进页隔离及存储失败修复已收敛为 **f18a922b778f437400de8165e67b162fea028724**，源码限定审核通过；最终全量及新包已完成下述限定验收。

| 页面 / 用户动作 | 本批实际变化与验收 |
|---|---|
| P04 资料与案例 | 同一账号切换客户空间或空间版本，草稿、资料请求和未知原操作独立。无法绑定空间的历史请求保留原编号并阻止误查。保存、解析、核对、撤销、移除使用真实页面组件；[CUA 操作与事件](p04/README.md)证明取消保留、未知锁不重复执行、原请求核对后解除。 |
| P06 平台状态 | 复选框的可访问名称和可见状态使用相同文字，解决原生页显示“读取失败”但无障碍名称仍为“读取中”的问题。构包内最终可见复验另行绑定。 |
| P12/P13 联系草稿 | 同时保护评论和私信未保存输入；只保存一个渠道不会放弃另一个。原文证据版本变化使旧核验失效；匹配原发送请求的明确终态才能清除对应发送错误。[双渠道可见流程](p12/README.md)只保存 TEST 草稿，没有执行发送。 |
| P18 版本与数据 | 沿用已有真实设置页；新增隔离 TEST 状态控制，用于验证取消/失败、恢复未知、清草稿和取消下载生命周期。[P18 记录](p18/README.md)明确模拟文件保存和真实原生文件选择器的区别。 |

跨空间修复以有界异步回执、精确请求绑定和可恢复存储为依据，未增加资料后台或发送后台。P04 历史 v1 锁不擅自迁入当前空间；点号标识碰撞及静默存储失败均有反例。

## a25 候选验证

| 检查 | 实际结果 |
|---|---|
| 最终受控前端测试 | [92 文件，1007 passed / 21 skipped](logs/final-tests.log)；包含实际坏 ASAR 反例，排除四个未提交 raw 辅助草稿。前一快照的 [1005/21](logs/tracked-tests.log)发生在点号标识修正之前，不当作最终结果。 |
| 类型与构包 | [typecheck](logs/final-typecheck.log)、[make:mac](logs/mac-build.log)、[严格 smoke](logs/packaged-smoke.log)、[服务桥 smoke](logs/native-service-smoke.log)、[生产 TEST 排除](logs/production-exclusion.log)均通过。 |
| 绑定 | [构建前](source-final-before.json)和[构建后](source-final-after.json)296 项与 a25 源码一致；[模块及输出](native/input-graph-check.json)、[包内字节](native/bundle-bytes-check.json)和[中间包摘要](native/mac-package.json)分开保存。 |
| 独立审核 | [架构](reviews/yike-ui-state-architecture-a25ba7b.md)、[代码](reviews/yike-ui-state-code-a25ba7b.md)、[质量](reviews/yike-ui-state-quality-a25ba7b.md)精确绑定候选；每名作者负责的模块由其他人交叉审核。 |

a25 包明确为**中间候选**。P14/P15 后续发现的同账号切空间 P1 已在 f18 源码范围收敛，但 a25 包不含这些修复；不得把该中间包作为最终交付或把已有 1007 项替代新修复的回归。最终包的独立绑定与有限可见 macOS 结果见下节。

## f18 跟进源码与 495 可见记录

[独立质量审核](reviews/yike-ui-state-quality-f18a922.md) 精确绑定 f18，涵盖 90d 初次 owner 隔离、495 存储失败保护及 f18 旧 facade 成功 ACK。独立 archive 候选运行 [6 套 56 项回归](logs/yike-followup-independent-f18-tests.log)通过：先清草稿不删除未读取的旧 session 锁，终态先可靠保存提交稿确认标记，删稿失败保留标记，人工后续修改不被原成功回执清除。源码范围无剩余 P0/P1；此处不代替主线程最终全量或新包验收，也不将重叠测试数量相加。

[P14/P15 可见记录](p14/README.md) 包含取消保留、新登记、两次纠正、真实日历选择 9 月 11 日、撤销保留历史和合成回复标已读。其静态 [37 文件构建哈希](p14/build-binding.json) 对应 **495**，不能与 f18 或最终生产包混用。前两次日期工具 fill 未进入 React 状态，只有真实日历操作后的 9 月 11 日 09:00 为成功保存证据；不把 15 日 DOM 显示记作已保存。

P14 UNKNOWN 可见链未执行。有效商机已有匹配回复、但尚无人工跟进记录时，回复入口仍缺独立选择路径（P2），留后续功能切片；不能靠虚构人工记录或扩大回复查询范围解决。完整 Goal 未完成。

## 最终集成与新包

提交时远端新增 `ff623ed`，普通 push 被拒绝后正常合并为 **16a9a3f4f2915f39d3650bf25c50dec24a6c0ea6**，没有强推或覆盖。此新集成的[全量回归](final/merge-16a9-tests.log)为 **104 文件通过 / 1 文件跳过，1206 passed / 22 skipped**；[325 文件源码](final/merge-16a9-test-source.json)和[完整命令](final/merge-16a9-test-invocation.json)单独绑定。下面 1121 项是 c88 的先前候选，不混同、不相加。

新增的 Win 持钥/签名模块尚未导入产品 main/preload/renderer 入口，[原范围与 Windows 证据](../V02_DEVICE_SIGNING_CLIENT_WIN_REVIEW.md)保持独立。现有 Mac 包仍为 f18 运行路径；不重写其摘要为 16a，也不宣称设备 BIND/PROVE 已接入。合并保留双方任务台账，后端没有本批额外修改。

[16a 合并独立复核](reviews/yike-ui-state-merge-16a9a3f.md)通过，新增模块 85 项及类型检查独立通过。随后 `369a049` 仅将测试中的私钥 PEM 头正则改为实际解析并重新导出 PKCS8 PEM 后逐字比较，保留更严格的编码校验，避免凭据扫描把测试断言当密钥。该差量[33 项通过](logs/device-key-encoding-assertion.log)、[类型检查通过](logs/device-key-encoding-typecheck.log)，扫描 clean；不把 16a 旧树扫描或全量结果回填为该提交重新执行，产品及包字节未变。

后端/文档主线 `a9d18db` 正常合入为 `07d4b85`，[合并审核](reviews/yike-ui-state-merge-07d4b85.md)确认 desktop 与 f18 相同、后端与远端相同。产品源码经[非作者代码及架构复核](reviews/yike-followup-code-f18a922.md)与[质量审核](reviews/yike-ui-state-quality-f18a922.md)，未发现本片剩余 P0/P1。

- 最终 **c88c9e20934c536a600d67dfe2ba2f7a02dd6404** 的 [全量回归](final/release-verified-tests.log)：101 文件通过、1 文件跳过，**1121 passed / 22 skipped**。包含实际坏 ASAR 反例；执行命令与源码分别记录于[调用记录](final/release-verified-test-invocation.json)和[源码哈希](final/release-verified-test-source.json)，四个未提交 raw 草稿排除。
- [构包摘要](final/release-mac-package.json)绑定产品 f18；后续 c59/c88 只修测试等待，生产字节不变。[typecheck](final/release-typecheck.log)、[make:mac](final/release-mac-build.log)、[严格 smoke](final/release-packaged-smoke.log)、[服务桥](final/release-native-service-smoke.log)及[生产 TEST 排除](final/release-production-exclusion.log)通过。ASAR `79a52de9d645378e0903fd93c4f49ac4c9ce703592fc1b537875708b372c86fa`，ZIP `75d4f8b269e8ecef2b7211d267447189bea7f940e9d1fc3e0ee8b814b185de32`。
- [原生可见验收](final/NATIVE_ACCEPTANCE.md)：实际新包冷启动、创建任务、五平台 AX/可见状态一致。随后 Mac 自动锁屏，未完成新包输入/退出/重启检查；保留旧包证据原版本，不把旧链移到新包。未完成 Apple Developer ID 签名/公证及 Windows 实机验收。

失败记录保留：495 的 [ASAR 未写完读取失败](final/tests.log)由 `5d9476f` 等待输出流 finish 修复；f18 的[跟进计时竞态](final/release-tests.log)由 `c59cf1b` 等待真实 mutate 派发修复；c59 的[文件选择会话初始化竞态](final/release-final-tests.log)由 `c88c9e2` 等待会话 effect 与已选择终态修复。原产品哈希、超时、防重及文件读取断言未移除，旧失败不回填为通过，各轮测试不相加。

原始 stdout 日志和 AX 文本保留工具输出的末尾空行、行尾空格，不为差异格式检查改写已绑定证据。源码/Markdown/JSON 的差异检查通过；仓库凭据扫描 clean。

## 视觉与证据边界

P04 添加资料抽屉以 1484×1060 实际 CSS 视口与 R3 P04 原图置于同一次图像输入比较。208px 导航、60px 顶栏、28px 内容间距及 24/16/14 字号遵循 DESIGN_SYSTEM 的规范；生成图的导航和字体比例不当作覆盖该规范的新要求。下划线内容页签、线性空态图标和资料版本栏与生成图有差异，因此不宣称像素完全一致。

P04 恢复和 P12 草稿提醒在 1280×720 操作；P18 同视口的长预览需要纵向滚动。截图原样保存，未修改 DOM 或拼接画面。IAB 既有 125% 缩放由临时设备度量补偿，实际 CSS 宽高另核对；这不是 Windows 的 125% 缩放验收。`capture-calibration/` 及 P18 旧裁切图是失败/校准证据，不计入完整布局通过。

P18 的静态 freeze 在 P04 最后两个点号修复文件之前，P04/P12 使用 a25 的后续 freeze，各自事后产物哈希独立保存。这些哈希不冒称具备未记录的构建前证明。内存回执、TEST 文件和测试来源只证明前端条件路径；真实平台、资料解析、研究计量、实际发送/回复、客户备份恢复等仍须对应后台及授权环境。

完整 P01–P20 视觉/状态矩阵、Windows 安装/缩放/重启/卸载、签名公证与生产环境仍未全部验收。完整 Goal 与 05A 保持进行中。

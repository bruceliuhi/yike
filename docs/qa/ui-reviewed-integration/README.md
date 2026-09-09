# 前端复审、主干整合与 Mac 冷启动修复

日期：2026-09-10。归属 V02-05A。R3/R4 的既有授权、搜贝用量边界和当前平台 Logo 继续有效。完整 Goal 保持进行中。

## 最新主干合并与验证

正常整合 `500af8d` 与远端 `aac3fe9`，源码快照为 **`4eca41301e599a431e06808d2b717926a094bbb5`**。完整保留 React/CSP/smoke 修复、远端真实策略组合与 `3898c3e` 的画像版本/确认账号修正；只对四份交接文档合成双方记录。[精确集成独立复核](reviews/yike-ui-integration-4eca413.md)通过。

| 验证 | 本合并快照的实际结果 |
|---|---|
| 受控桌面测试 | [88 文件 / 964 passed / 21 skipped](merged/tracked-tests.log)，不包含四个未提交 raw 草稿 |
| 类型 / 构包 / 严格 smoke | [typecheck](merged/typecheck.log)、[Mac 构包](merged/make-mac.log)、[严格 smoke](merged/packaged-smoke.log)通过；smoke 中系统 dialog 为隔离替身 |
| 生产模块和输入绑定 | [一个 React 且无 TEST/raw](merged/module-graph.log)；[285 个输入、39 个构建文件](merged/source-binding.json)与本快照及 ASAR 一致，属于构建后字节核对 |
| 本包可见原生增量 | [冷启动工作台、任务表单、平台连接](merged/native-routes.md)及[进程/打开的 ASAR](merged/native-process.json)，只读访问，不代表真实服务或完整生命周期已通过 |

当前 Mac arm64 ZIP 路径为 `desktop/out/make/zip/darwin/arm64/意客AI-darwin-arm64-0.2.0.zip`，SHA-256 **`c5fdf73d28ae5a62ac04d3ccf3367db4c3db5ddc11a98ba130c5690d7fcc2d65`**；ASAR SHA-256 **`d7f2d2c0cc4b0cfa3f3034b0074287a66ef00097d827d8f599e52c6f578006af`**，详见[包结构](merged/package.json)。[独立质量复核](reviews/yike-ui-quality-4eca413.md)核对 ZIP 内 ASAR、构建文件、源码和证据边界。未签名/公证，Windows 仍由用户后续实机验收。

以下 944 项及 aec0 包保留为上一修复快照的历史证据，不能与当前包混用。

## 上一修复快照 8ddafab 的验证

修复源码为 `8ddafab6cc4cea21c244dcf1f052bf04defe8e87`。renderer 统一 React 实例，并在加载业务 schema 前配置 Zod 解释执行，避免严格 CSP 下生成代码的探针；没有放宽 CSP 或停用数据校验。smoke 增加真实工作台结构、稳定状态、控制台错误和完成凭据检查；已用原坏包、提前退出及真实 Electron console.error 验证拒绝路径。

| 验证 | 本次实际结果 |
|---|---|
| 受控桌面测试 | [87 文件 / 944 passed / 21 skipped](fix/tracked-tests.log)，含实际坏包反例；不含四个未提交 raw 文件的测试 |
| 定向与类型 | [24 项](fix/targeted-tests.log)、[typecheck](fix/typecheck.log)通过；集合有重叠，不相加 |
| Mac 构包与严格 smoke | [构包](fix/make-mac.log)、[严格 smoke](fix/packaged-smoke.log)通过；smoke 文件选择/退出 dialog 为隔离替身，真实 IPC/临时文件写入保留 |
| 生产模块 | [模块图](fix/module-graph.log)：一个 React dispatcher，TEST 与四个 raw 草稿模块均未进入产物 |
| 源码/产物绑定 | [284 个受控输入、39 个构建文件与 ASAR 核对](fix/source-binding.json)，[包结构](fix/package.json)；构建后核对，不宣称干净构建前后 provenance |
| 真实原生可见链 | [最终 aec0 包操作记录](fix/native-lifecycle.md)：工作台→草稿名称/50搜贝→离页退出提醒→继续保留→明确放弃 exit 0→同目录重启草稿0；[重启进程与可执行文件](fix/native-process.json) |

该修复快照当时的 Mac arm64 包位于 `desktop/out/make/zip/darwin/arm64/意客AI-darwin-arm64-0.2.0.zip`，SHA-256 `c4b179b7e491ff872cdb809f20c555fe4dc5c1d4819ad16a6c09b5e9961f96a2`；ASAR SHA-256 `aec0b946be4ca147e940e3c4ec1f3c0652104585be843ff69ebf95f2869da50d`。包未获得正式签名/公证或 Windows 实机验收。

修复的独立审核见 [架构](reviews/yike-ui-architecture-8ddafab.md)、[代码](reviews/yike-ui-code-8ddafab.md)、[质量](reviews/yike-ui-quality-8ddafab.md)。代码审核者排除本人编写的 smoke，其代码由架构和质量审核者独立覆盖。

## 已整合范围

本地候选 `99993552f1559681c8f671a57096ec23d4e9095b` 冻结后完成独立架构、代码和质量审核。审核发现旧断开操作的解码会丢弃登记连接的 device/version 身份；修复 `e70c3a1d048f0f3d6b13bf74805eb60ad4a587cf` 在解析前拒绝任何带 registration 的响应，未知原请求继续保留。三项精确复审通过后，正常保留远端 `ab6407d`，形成已推送的 `a31069fead15f395e7b4ec93c9c91e441beea798`。

该批包含会话草稿退出保护、P09 画像版本核对、监控日程契约与导航、连接列表真实只读 API/IPC 及 Windows 来源绑定脚本。连接登记不等于执行能力，未接通的服务不显示假成功。

审核原文见 [architecture](reviews/yike-ui-architecture-e70c3a1.md)、[code](reviews/yike-ui-code-e70c3a1.md)、[quality](reviews/yike-ui-quality-e70c3a1.md) 和 [main 整合](reviews/yike-ui-integration-a31069f.md)。三名 Agent 各自参与过的模块由其他非作者交叉覆盖，作者不为自己的模块作唯一最终批准。首次 9999355 审核及修复前结果一并保留于 reviews。

## 初次构包的失败边界

`initial-a310/` 保留整合后 84 文件 / 927 passed / 21 skipped、类型检查、构包及当时 smoke 的原始结果。279 个受控源文件与提交一致，39 个构建文件与 ASAR 相同，详见 [source-binding](initial-a310/source-binding.json)。这只是构建后输入核对，不是干净环境的构建前后证明，也未覆盖依赖目录异常。

初次 ASAR `29d93a50535cdd2cebc01304c4166d4fee8f3fc09a2184d43db2d736f06d21d6`、ZIP `3f9e802db169d8e1ad082639894279604aa2710acc3fabda504827ee6efda735` **不能作为可用交付包**。实际可见冷启动停在“页面未能打开”，[原生截图](initial-a310/native-startup-failure.png)及[控制台日志](initial-a310/native-startup-failure.log)记录了空 React dispatcher 错误。

原因是本次共享依赖准备后出现 `desktop/node_modules/node_modules` 自指符号链接。Forge 默认保留符号链接路径，应用与 react-dom 因不同路径载入两份 React；[实际模块图](initial-a310/duplicate-react-modules.json)记录了不同 ID 指向同一真实文件。已仅移除该自指链接，保留正常依赖和审核目录。renderer 显式统一真实路径及 React 依赖，并以隔离链接布局的生产构建验证防止复发。

中间 `befacea` 包的 React 启动和原生操作已经恢复，但加强的 smoke 又准确报告 Zod 动态代码探针的 CSP 错误。`react-only/` 保留该次失败、对应包摘要与原生记录；最终修复启用 jitless 后才通过严格 smoke。各版本不能混用。

旧 smoke 只搜索“商机工作台”，错误恢复页上的按钮也会命中；Electron 43 控制台错误的事件参数读取也有遗漏。因此旧 smoke PASS 不证明此包页面已打开。修复要求旧坏包被拒绝、新包实际页面结构和交互通过，原始失败不能被覆盖。独立 [产物复核](reviews/yike-ui-artifact-a31069f.md)分别记录字节一致与启动阻断。

## 后续接口交接

[候选适配审计](reviews/candidate-adapter-a31069f.md)只读核对了新 04C 接口。P07 主列表应消费已评估候选，保留搜索、状态筛选和原请求恢复；raw 读取仅辅助固定原文版本和观察历史。INCLUDE 回执缺少原 sourceVerificationId，尚不能据当前最新核验猜补原确认 hash；需按 04C/05G 既有责任补齐版本化快照及分析/核验请求恢复，不重复或抢改已认领接口。

四个本地 raw 辅助文件尚未接线、未纳入已提交产品。本目录的初次测试明确排除其 13 项隔离测试，构建模块图也验证它们未进入生产包。

## 未完成项

P04、P14/P15、P18 等剩余可见状态与全部设计差异仍需按原台账验收；真实平台、模型/计量、触达与回复按对应接口工作推进。当前记录不替代 Windows 实际安装、缩放、退出重启与卸载，不代表签名/公证、生产部署或正式商用完成。

实际任务表单还观察到平台读取失败时，复选框的无障碍名称仍含“读取中”，可见文字则为“读取失败”；这是后续 05A 状态文案一致性修正项，不算当前构包修复已解决。旧审核报告中的文件路径保留原记录时点；本目录现按 initial-a310、react-only、fix、merged 分开存放证据。

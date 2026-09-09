# 4eca413 合并包增量质量复核

2026-09-10。绑定源码 `4eca41301e599a431e06808d2b717926a094bbb5`，此前修复候选为 `8ddafab6cc4cea21c244dcf1f052bf04defe8e87`。仅只读核对合并包字节、日志和实际可见证据；未重新跑全量、修改源码或操作原生界面。

**限定 PASS：本次增量产物与可见路由证据未发现新的 P0/P1 阻断，可继续提交/推送此候选。** `8dd` 已审的 8 个 React/bootstrap/smoke 修复及回归文件在本次合并后逐文件无差异，原代码审查可继承。合并新增的 profile mapper/任务摘要及对应测试属于另外已审范围；本报告不冒称重新审核所有新增后端/策略实现或文档合并。

## 源码与产物

- `merged/source-binding.json` 的全部 **285 个受控 desktop 输入**，与提交文件集合、当前文件字节、SHA-256、Git blob 均一致；无缺失、多余或不匹配。desktop tree 为 `bb63ddb78b00e3a44cc3175dc3c74025e58fcf33`。
- 当前 **39 个构建文件**逐字节等于 ASAR 内文件；`merged/package.json` 的 **36 个 renderer 资源哈希**全部匹配。
- ZIP 内只有一个 `Contents/Resources/app.asar`，其字节等于当前 ASAR。以下两项 SHA/大小已由审核者重新计算，亦与 source-binding 及 package 清单一致。

| 产物 | 字节数 | SHA-256 |
| --- | ---: | --- |
| 合并包 ASAR | 1,769,534 | `d7f2d2c0cc4b0cfa3f3034b0074287a66ef00097d827d8f599e52c6f578006af` |
| Mac arm64 ZIP | 122,472,394 | `c5fdf73d28ae5a62ac04d3ccf3367db4c3db5ddc11a98ba130c5690d7fcc2d65` |

- ASAR 目录未见 tests 或未提交 raw 模块路径；`merged/module-graph.log` 为本合并包构图，记录 4,760 模块、排除命中 0、单一 React 生产模块。四个未提交 raw 草稿不计为本包功能。文件名检查本身不替代生产图检查。
- 清单保持构建后受控源码与构建字节核对的范围，未声称干净构建前后取证或完全可重现构建。

## 本轮测试日志

独立读取 [merged 证据目录](/Users/bruce/Developer/work/yike-ai-product-design/docs/qa/ui-reviewed-integration/merged)：**88 个文件 / 964 passed / 21 skipped**；typecheck 无错误，构包及加强后的 packaged smoke PASS。本审核不重复全量，旧 8dd 的 944 项和本轮 964 项不能相加，跳过项仍未通过。

smoke 继续是临时 userData、隐藏 Electron 和替代 dialog 的有限集成验证；实际 IPC 与临时文件写入不等于实际原生保存选择器。其退出模拟也不能将旧包真实退出链移绑到此包。

## 原生可见范围与历史归属

已实际查看 `merged/native-workbench.png` 并读取完整 AX：本合并包冷启动显示完整工作台、公开研究样例、登录及平台待连接状态，未出现“页面未能打开”。客户服务未配置，截图未把登录或连接记为成功。

另外实际查看 `merged/native-task-form.png`、`native-connections.png`，并读取两份完整 AX：任务表单懒加载成功，名称、画像、搜索词/排除词、平台范围、运行方式及搜贝上限可见；账号连接页列出各平台及明确的客户服务未连接提示。未进行任务保存/执行、授权或发送，也未把待检查能力当成功。任务表单截图未覆盖下方全部控件，完整 AX 有保存/下一步入口；本次不据此宣称所有控件均已实际点击、全部纵向范围可见或通过设计图逐项对照。

独立实时 `ps`/`lsof` 确认 PID 20667 存活，命令与 `native-process.json` 一致，实际打开的 `.app/Contents/MacOS/YikeAI` 和 `app.asar` 路径与记录一致；重新计算 ASAR 仍为 `d7f2d2c0…`。三页证据确属当前合并包的有限原生路由验收。

本合并包未重复完整真实退出重启链；该链继续属于 `fix/` 的 `8dd/aec0b946…`。`native-routes.md` 准确保留该边界。`initial-a310/29d93a5…` 仍是坏包，`react-only/befacea…` 仍是中间包，其失败/通过边界不改写。

Windows 实机、签名/公证、所有页面/状态、真实客户服务与平台执行、搜贝计量和触达回复仍不在本报告通过范围。既存无障碍标签“读取中/读取失败”问题继续属于后续 05A；整体前端 Goal 不因此完成。

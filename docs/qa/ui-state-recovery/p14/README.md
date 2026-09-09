# P14/P15 实际可见跟进链

本次操作由主线程使用 **Codex In-app Browser（IAB，browser2）/CUA** 完成，入口为 `?scenario=P15&state=populated&capabilities=complete`。页面组件真实运行，`makeVisualFollowup` 只读写当前实例的 TEST 内存，不接触客户库、平台消息或网络。

静态构建绑定 **`49545344fd1091a8c019d923c207db00dbc70368`**，日志为 [final/visual-build.log](../final/visual-build.log)。[build-binding.json](build-binding.json) 在重建前保存 37 文件完整哈希和 Vite manifest，保留不覆盖。它是运行后的输出采集，不反推未留存的运行前哈希。后续 `f18a922…` 抽出终态收尾并补旧 facade 的成功 ACK，结构化分支也产生字节变化；**本页截图仍只绑定 495，不能改写为 f18 的重新可见验收**。

## 已保存的状态证据

| 实际路径 | 留存证据 | 结果与边界 |
| --- | --- | --- |
| 输入备注/下一步 → 取消关闭 → 关闭确认内取消 | [close-confirmation.txt](close-confirmation.txt) | 嵌套关闭确认与原表单输入同时存在；主线程取消后继续编辑，没有把未保存关闭直接当提交。该文件为 DOM 可访问快照，其余多数文件是原生 AX 文本，不统一冒称同一种捕获方式。 |
| 保存新人工记录并查看“全部” | [created-record.txt](created-record.txt) | 新记录与原 TEST 记录同时存在，备注/下一步保留；该次下次跟进为空，不能写成已保存日期。 |
| 纠正备注并填写原因 | [correction-filled.txt](correction-filled.txt)、[corrected-record.txt](corrected-record.txt) | 新记录保留纠正原记录 ID 和原因；原登记仍显示“已纠正”，没有删除历史。第一次纠正后的下次跟进仍为空。 |
| 用实际日期选择器设置并再次纠正 | [date-picker-saved.txt](date-picker-saved.txt) | 主线程打开日历 popup，通过 Right + Return 选择 **2026-09-11**，填写原因并保存。列表和人工记录均显示 **2026/9/11 09:00:00**；成功日期是 11 日。 |
| 撤销确认先取消、再明确确认 | [revoke-cancelled.txt](revoke-cancelled.txt)、[revoked-history.txt](revoked-history.txt) | 取消后仍有效、可纠正/撤销；再次确认后显示“已撤销”和撤销原因，历史记录与日期继续保留。 |
| 查看同商机关联回复并标已读 | [reply-read.txt](reply-read.txt)、[1280×720 PNG](reply-read-1280x720.png) | 通道回复显示“已读”、TEST 来源说明和合成发送记录 ID；不是实际平台回流消息。 |

### 日期工具路径差异

前两次使用 Playwright `fill` 操作 date 控件，DOM/AX 可显示输入值，但主线程确认当时未进入 React 状态，随后新建/第一次纠正记录的下次日期为空。`correction-filled.txt` 的 `2026-09-15` 只是该次控件显示，**不是 15 日保存成功证据**。

随后使用真实日历 UI 的 popup、方向键与 Return，最终服务返回和列表显示为 11 日 09:00。本记录不修改旧 AX，也不把工具填值未触发状态推断为产品日期逻辑缺陷；这次可见成功证据只支持日历 UI 路径。

## 独立核对与尚未覆盖

- 本审核者读取全部上述快照并实际打开 1280×720 PNG。图中蓝白壳、筛选、记录表与关联回复两栏可读；记录和负责人在窄表格内换行，未见水平裁断。主线程实测 CSS 1280×720、scrollWidth 1280；不外推其它分辨率和系统缩放。
- [console.json](console.json) 为 `[]`，仅代表此次采集未记录控制台消息。
- `makeVisualFollowup` 没有向 harness 事件列表记录 mutation，因此**没有可用的逐请求次数日志**。本记录按可见状态描述操作，不虚构“执行仅一次”的事件证明。
- P14 UNKNOWN 的实际可见恢复链尚未执行；现有原请求/存储/跨空间单元测试不能替代该可见状态验收。匹配回复进入人工跟进的快捷入口 P2 仍留后续切片。
- 同用户切空间、身份版本变化、存储写失败和旧 facade 的新 ACK 路径本次未作 CUA 验收；f18 最终源码审核与定向测试另见 [质量报告](../reviews/yike-ui-state-quality-f18a922.md)。495 静态图不代表 f18 新包或可见原生 UAT。

补充测试清场边界：P04 的 `applied-profile-visible.txt` 仍记录当时“未保存画像草稿”；主线程后来手动点击保存草稿用于退出 dirty 状态。该后续手动清场不改变原证据时点，也不是资料应用自动保存或自动确认画像。

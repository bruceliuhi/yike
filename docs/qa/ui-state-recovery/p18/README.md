# P18 TEST 管理恢复链证据

本目录记录主线程通过 Codex In-app Browser（IAB，browser2）/CUA 操作真实 Settings 组件的有限验收，以及本审核者对原事件、AX 文本和四张 PNG 的核对。入口为 `http://127.0.0.1:18794/?scenario=P18&state=populated&management=lifecycle#/settings`。**服务、导出回执和管理动作均为固定 TEST 空间的隔离内存实现。没有导出文件落盘、客户库恢复、设备绑定或安装包下载；未验证 Windows。**

本文件是证据整理，不是作者对自己 P18 实现的独立放行。该实现由 Popper 非作者审查并独立运行三套 15 项；候选绑定的审核报告在整合记录中另行归档。

## 静态构建与最终源码的区别

- 本次 P18 操作使用 P04 最后点号 ID 修正前冻结的 visual build。重建前已保存 [build-binding.json](build-binding.json)：37 个文件、0 个符号链接，含每文件字节数/SHA-256及完整 Vite manifest。它是**运行后的文件采集**，不能回推未保存的运行前构建哈希。
- 当时保存的 [source-before.json](../source-before.json) 有 296 项源码输入，基于 `1c56fc5734c738558067979c99c2fdd23d307552`；不是已提交 a25 的完整构建证明。
- [source-final-before.json](../source-final-before.json) 明确绑定 `a25ba7b331e7712c4fba53b173cbbc704ec3e734`，296 项输入已逐项核对 `git show` 字节，0 项不同。它与旧源码 snapshot 只差 `materialOperationStorage.ts` 和其测试，P18 切片未改。**不能据此将旧 visual build 改称 a25 完整构建。**
- 最终 [final-tests.log](../logs/final-tests.log) 为 **92 文件，1007 passed / 21 skipped**；旧 `tracked-tests.log` 的 1005/21 仍保留其原 snapshot 边界。本审核者没有重跑全量，也没有把重叠的定向测试相加。

## 可见路径与原请求次数

[events.json](events.json) 保存同一内存实例 14 条连续事件。事件记录请求/动作次数，未为每条 query 保存返回状态；返回状态应同时参照以下 AX 和主线程实际操作记录，不凭事件名称猜测。

| 路径 | 已留存证据 | 核对结果 |
| --- | --- | --- |
| 导出取消 | [导出弹框 AX](export-cancelled.txt)、[模拟取消回执 AX](export-cancelled-receipt.txt)、events 1–2 | 生成 CSV 一次、模拟 save 回执 `cancelled` 一次；取消没有显示保存成功。 |
| 模拟保存成功 | [AX](export-saved.txt)、[PNG](export-saved.png)、events 3–4 | 第二次生成 CSV、模拟 save `saved`；产品显示“客户数据导出文件已保存”。顶部 TEST 横幅明确“不写文件”，不是实际保存验收。 |
| 模拟保存失败 | [AX](export-failed.txt)、events 5–6 | 第三次生成 CSV、模拟 save `error`；弹框保留“文件未能保存，请检查保存位置后重试”和重试入口。 |
| 恢复预览 | [AX](restore-confirmation.txt)、[PNG](restore-confirmation-1280x720.png)、event 7 | 主线程通过浏览器文件选择器选择仓库 TEST 备份文件。留存画面证明已选文件名、TEST 空间/设备及影响预览；勾选前恢复按钮 disabled。没有保存文件选择器本身的截图，因此不将本目录当作原生保存框验收。 |
| 恢复 UNKNOWN 与清草稿 | [AX](restore-unknown-after-clear.txt)、[PNG](restore-unknown-after-clear.png)、events 8–9 | 提交一次恢复，关闭弹框、核对原请求仍未知；清本机草稿后待确认恢复仍存在，同时提示草稿已清除。 |
| 原恢复请求明确未执行 | [AX](restore-confirmed-not-executed.txt)、event 10 | 主线程将 TEST 查询结果选为 FAILED，重新点击产品页原请求查询后，显示“原请求已确认未执行”，待确认区移除；未重新执行恢复。 |
| 下载取消待处理 | [AX](cancel-pending.txt)、events 11–13 | 预览、执行一次 TEST 下载，UNKNOWN 后取消回执为 PENDING；仍显示待确认操作、原请求核对和取消下载入口。 |
| 下载取消已确认 | [AX](cancel-confirmed.txt)、event 14 | TEST 取消结果改为 CANCELLED 后，再次点产品页取消原请求；显示“原操作已取消”，待确认区移除。没有第二次下载执行。 |

恢复原请求 `b8d25d3b-2bc6-4be4-a317-034144db42ea`：**execute 1 次、query 2 次**；准备计划 `TEST-plan-bd6cad49-bf84-45a0-9783-20a61aa6188d`。下载原请求 `5e56966a-96f6-4bd5-8c86-a71c886d8d3c`：**execute 1 次、cancel 2 次（PENDING/CANCELLED 各一次）**；准备计划 `TEST-plan-bc3e75f5-69ac-466a-9ed8-1c86b602b607`。导出三次分别对应取消、模拟成功、模拟失败，无额外管理执行事件。

主线程操作记录包含“改变 TEST 选择器后仍须产品页查询/取消”，这一机制另有真实组件定向回归；本目录没有每次选择器改变后、点击查询前的独立截图，不能把事件日志扩大解释为已捕获每个中间画面。

## 截图适用范围

四张原图均已实际打开核对：

- `export-cancelled.png` 是早期放大裁切截图，只留下部分导出弹框，**不用于完整页面布局或取消结果判定**。保留原始文件，取消结果以 AX 和事件为准。
- `export-saved.png` 清楚显示 TEST 横幅与保存成功提示；页面处于滚动位置，不是全部账号设置的一屏截图。
- `restore-confirmation-1280x720.png` 清楚显示文件选择和预览上半部分、固定关闭按钮；影响表、勾选及恢复操作在滚动区域下方，完整控件见 AX，**不宣称均在同一屏可见**。
- `restore-unknown-after-clear.png` 同时显示“本机草稿已清除”提示和“待确认操作”区标题；下方原请求操作行不在截图视口内，AX 仍记录“恢复客户数据 结果待确认/核对原操作”。

本目录未覆盖恢复 SUCCEEDED 的实际可见分支、真实客户空间服务、浏览器刷新后的后台持久化、原生保存框或 Windows 安装/缩放链。纯内存状态在刷新/重新构建后重建，不能将该重建当作管理操作终态。

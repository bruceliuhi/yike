# P07 Mac 交互与新版客户端

2026-09-10，固定源码 `0d17cf708e371fd61e502d168b8bd67d308f69e1`。本次接收已合入主线的候选证据与人工核验实现，重新构建 Mac arm64 客户端并完成以下限定验收，没有修改产品源码。完整 UI Goal、真实客户服务链及 Windows 安装验收仍未完成。

## 本地交付物

- App：`desktop/out/candidate-mac-0d17cf7/意客AI.app`
- ZIP：`desktop/out/candidate-mac-0d17cf7/意客AI-darwin-arm64-0.2.0.zip`
- ASAR SHA-256：`750ea0f759c10a6786ba2544e05c01f49af945211d4622854f59e3c75901698e`
- ZIP SHA-256：`d34f571e9c91054a705775863d8cb4ac14d4f9bcb50a8c0c027466ae9f260dd3`

包从 `git archive 0d17cf7` 的隔离目录构建，365 个已跟踪 desktop 输入逐字节匹配该提交，未包含四个未跟踪 rawCandidate 草稿。[输入清单](final-build-inputs.json)、[包清单](final-mac-package.json)、[包结构](final-package-structure.json)分别保留来源、摘要及实际产物路径。构建产物留在本机，Git 仅纳入验收记录；未发布签名发行包。

类型检查、Mac make、严格包内 smoke 与生产 TEST 排除均退出 0，见 [typecheck](logs/final-typecheck.log)、[make](logs/final-mac-build.log)、[smoke](logs/final-packaged-smoke.log)、[排除检查](logs/final-production-exclusion.log)。排除检查实际读了本次 ASAR，`existingAsarChecked=true`，`failures=[]`。没有再次运行全量测试；P07 作者的测试与 Windows 浏览器验收见 [05G 原记录](../V02-05G_CANDIDATE_CLIENT_WIN_REVIEW.md)，不冒称本次 Mac 重跑或真实服务验收。

## P07 浏览器交互

通过内置浏览器打开同一冻结源码的 `http://127.0.0.1:18794/0d17cf7/?scenario=P07&candidateReview=recovery`，使用真实页面组件及隔离 TEST 内存回执：

1. [原文状态](01-original.txt)区分当前评论作者、评论原文、原帖标题和父评论；未做 AI 判断时不生成结论。
2. 显式“按画像重新判断”，填写带 TEST 标识的来源定位与逐字摘录，选择来源状态及联系路径、勾选人工核对，再保存来源核验。没有打开外部来源，所填内容只验证 TEST 表单，不代表实际人工来源认证。
3. [确认弹窗](02-confirm.txt)保留画像、来源版本、来源核验 ID 和五项依据；取消后重新打开仍需勾选确认。
4. 在 CSS **960×600** 下实际点击取消、重开、勾选、提交。弹窗实测 x=170、y=28、宽620、高544；文档宽960，无横向溢出。[有效截图](03-confirm-960.png)已打开检查，标题、五项依据、勾选、取消及提交按钮完整可见。
5. 提交返回 [UNKNOWN](04-unknown.txt)，排除/入库禁用。将来源筛选改为抖音使列表为空后，仍可核对原 INCLUDE 请求；[核对成功](05-recovered.txt)后清除旧未知提示并显示查看商机入口。不从 DOM 推断实际请求次数；本次没有业务 HTTP 或客户入库。
6. 重建隔离实例的 `candidateReview=raw-error` 路径显示 [原文读取失败](10-raw-error.txt)，没有以摘要冒充原文；实际点击“重试”后 [仍失败且确认入库禁用](11-raw-error-retry.txt)。

截图范围有限，不代表全页、全部分辨率或同状态像素一致验收。首次截图 `01-original-first-1200x853.png` 的实际 CSS 尺寸为1200×853，未计入目标分辨率验收；`02-confirm-1440-rejected-compositor.png` 在切换浏览器模拟视口后出现右侧重复绘制，明确作废，不能用作1440像素一致证据。该时 DOM 只有一个 nav；之后960截图正常。临时视口覆盖已清除，未改页面样式掩盖截图问题。

## 实际原生客户端

先正常退出旧 b8b8236 客户端并确认旧 PID 4743 不存在，再打开本次 App。中途启动调用被会话中断；恢复后确认新旧包均无主进程才重新启动，没有在旧进程上冒验新包。

- [冷启动](06-native-start.txt)实际加载 `yike://app/index.html`，无开发服务器依赖。
- 点击线索采集 → 查看原始线索；[未登录状态](07-native-candidates-signed-out.txt)显示登录入口，没有客户候选。[原生截图](07-native-candidates-signed-out.jpg)已实际查看。
- 切换 [公开研究样例](08-native-sample-boundary.txt)，样例不能绑定客户画像、不能排除或确认入库。
- `super+q` 正常退出，进程查询无本次 App 主进程；再次打开同一 App，显示 [工作台初始状态](09-native-restart.txt)。重启 PID **29140** 的可执行路径与 ASAR 摘要核对见 [进程身份](native-restart-identity.json)。

原生这条链没有客户登录、来源访问、判断、入库、发送或备份恢复；有数据的 P07 表单链仅在隔离浏览器完成，不互相替代。本次没有新增草稿，因此不借此重复签收上轮有草稿退出保护。

## 工具中断与剩余验收

原生快捷键最初调用参数不合接口，读取最新工具文档后改为 `super+q` 才实际退出；截图后索引失效的一次标签点击未生效，重新读取 AX 再操作。JPG 头识别后使用正确扩展名保存。

会话中断后原18794静态服务器 PID58682仍在监听，但浏览器和curl均返回空响应，已正常终止该已确认失效的本任务服务，再用相同脚本、目录、端口启动并将日志输出到文件。旧错误页为 data URL，工具 URL 策略拒绝访问，没有绕过该页；新建允许的本地 HTTP 页面后成功继续。首次原文重试定位误用了不存在的按钮名，读取 DOM 后使用页面实际“重试”，只有后者计入结果。

原生文件保存/恢复、真实客户数据整链、其它页面剩余状态、完整设计配对及 Windows 安装启动/退出/卸载继续待验。此前 P18 完成项见 [管理状态记录](../ui-management-visible/README.md)。独立限定包与证据复核见 [review.md](review.md)。

差异检查仅在原生样例 AX 文本和 Forge 构建日志各发现一处原始尾随空格；保留原始输出，不为通过格式检查改写证据。手写 Markdown 无格式错误。

提交前正常合并远端 `602f9e9` 为 `160fbd5`。renderer 未变，新来件为主进程私有设备传输及后端验收记录；[本地定向](logs/integrated-transport-tests.log) 3文件248项通过，[类型检查](logs/integrated-typecheck.log)退出0。Mac包仍绑定0d17cf7，不包含后续私有设备传输；不重复构包或代签来件真实服务结果。用户要求加快验收版交付，后续按仓库新效率约定只追加受影响检查。

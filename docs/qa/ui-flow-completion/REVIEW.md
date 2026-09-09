# 前端流程补齐与平台品牌交付

2026-09-09。流程代码 `237a5b2`，品牌代码 `1c15673`；最新远端 `9077383` 的身份/会话与测试时钟工作已通过正常合并保留，整合提交 `3228962`。全部产品代码最终进入 `yike-ai2026/main`，本轮短期分支仅用于并行收尾；没有修改只读文档仓库 `yike-ai`。

最终再次正常合并远端 `fe85b46`，得到 `58622ef`，保留Win解析器、双Node预检修复和接收证据。独立Agent确认两侧历史及97项Mac构建输入不变；只解决整合文档的文字冲突，保留最新Win ACK和此前Mac环境说明。19:06最终前端为 **50文件、493 passed、1 skipped**；跳过项为必须在Windows运行的PowerShell回归。合并后UI/会话/身份/解析器定向 **140 passed**。数值覆盖相应前轮，不能累加。

## 本轮实现

- 业务资料保存、解析、人工核对、应用画像、引用撤销与移除影响；四个可选服务契约将完整前端和实际后端能力区分。
- 工作台四队列、精确候选目标、联系准备搜索/排序和本机会话备注；样例过滤、超时和目标切换隔离。
- 跟进事实、负责人/日期筛选、通道回复与人工登记分离、已读、纠正/撤销和未知操作核对；兼容现有人工登记接口。
- 任务操作及启动回执绑定 ID/修订/哈希/模式；未知请求核对、列表筛选/分页、监控事件、草稿展开及会话模板。复用模板不能绕过来源草稿未知启动锁。
- 原平台 Logo 本地打包、统一平台标签，覆盖监控/连接与线索、商机、触达来源。公开网站及未知来源使用通用图标并保留原名称。

实际后台接入按 [资料](../../UI_MATERIALS_CONTRACT.md)、[跟进](../../UI_FOLLOWUP_CONTRACT.md)、[任务操作](../../UI_TASK_OPERATIONS_CONTRACT.md)、[工作台](../../UI_WORKBENCH_CONTRACT.md)执行。生产默认 facade 不会启用 TEST 内存服务；此次不是平台采集或发送上线。

## 验证

| 检查 | 当前结果 |
|---|---|
| 全部前端 | 50文件、493 passed、1 Windows专属项skipped；typecheck通过，品牌审核绑定1c15673，最终输出见final-tests.log |
| 合并后的UI/会话/身份/解析器定向 | 140 passed；未以此宣称生产数据库升级通过 |
| 安全与差异 | secret_scan clean、git diff --check通过 |
| Mac构建 | arm64、0.2.0，构建97项输入与1c15673逐字节一致 |
| 包内冒烟 | 真实ASAR main/preload/renderer启动、sandbox/协议/固定IPC、文件临时写入/取消、退出保护通过；保存对话框仅在隔离测试进程替代 |
| 生产排除 | manifest harness引用0，实际新ASAR检查通过 |
| 可见Mac | 新包启动至yike://app/index.html工作台；用户随后操作到线索采集。未继续打断用户操作来做可见退出/重启；隔离进程退出链已通过 |
| 视觉 | 20页已逐图检查；品牌增量部分大尺寸截图捕获异常，未记为最终视觉全通过。正常视口图标可见 |

精确源码/ZIP/ASAR哈希和版本见 [mac-package.json](mac-package.json)，原始检查见 `mac-build.log`、`package-check.json`、`packaged-smoke.log`、`production-exclusion.log`。ZIP在 `desktop/out/make/zip/darwin/arm64/意客AI-darwin-arm64-0.2.0.zip`，不将二进制提交Git。

独立范围：[架构](ARCHITECTURE_REVIEW.md)、[代码](CODE_REVIEW.md)、[质量](QUALITY_REVIEW.md)、[品牌](PLATFORM_REVIEW.md)。每份报告排除本人自作模块的批准，保留历史发现和修复证据。截图、实际交互及限制集中在 [design-qa](design-qa.md)。

Windows由用户按 [打包手册](../../../desktop/docs/PACKAGING.md)执行脚本回传，当前没有Windows安装/卸载或系统缩放通过证据。签名、公证、自动更新发布、生产部署未完成；完整Goal继续保留进行中。

本次同步收到的[Windows交叉记录](../WIN_CROSS_REVIEW_20260909.md)已报告较早源码的构建尝试：make-win在中文路径Squirrel处理失败，安装/可见运行/卸载仍UNTESTED；不能把该旧包的测试数作为本轮新UI的Windows验收。

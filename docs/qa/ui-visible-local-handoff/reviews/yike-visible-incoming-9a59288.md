# 9a59288 来件与 bd4b86a 合并接收复核

- 日期：2026-09-10。
- 来件范围：`83e76be9e00a627af2286b52e0087966b812831d` → `9a59288531cab7be0df9b6934fc3dc61e181c072`；最终合并：`bd4b86a846a3703b9954a6c81e633a81ec1d11b4`。
- 合并双亲：本地 `4d57f2804a2a216f90f0921c2ccd78178996ad2e`、远端 `9a59288531cab7be0df9b6934fc3dc61e181c072`。
- 结论：**限定接收 PASS；未发现新增 P0/P1 或此次合并阻断。** 本结论针对来件兼容与合并保留，不是完整候选复核写入链、生产后端或新客户端包验收。

## Git 对象与本批页面

独立读取 Git 对象确认：来件 15 个变化路径在合并结果中全部与远端 blob 相同（不匹配 0）；本地单方 82 个变化路径全部与本地父 blob 相同（不匹配 0）。`git diff 9a59288 bd4b86a -- desktop pilot tests` 为空。P04 Profile/资料子模块、P06 TaskWizard、P09 Tasks/任务子模块、P14 Followups/跟进子模块及 routes 相对本地父没有改动；此前返回上下文、资料空间保护、精确商机回复定位实现均保留。

## 接入与页面兼容

1. `desktop/src/renderer/services/client.ts:238–254` 实际安装严格解码后的候选读取：调用 `createCandidateReviewService(request).list`，只把已验证的平台枚举映射为页面名称。没有将 raw 数据伪装成已评估候选；assessment、历史绑定、来源核验等其余字段随 DTO 保留。旧页面写入仍明确 unavailable，未因读取接线自动进行判断、核验或确认。
2. `desktop/src/main/servicePolicy.ts` 的四个操作使用固定枚举、严格 payload schema、固定 HTTP 方法/路径；renderer 不能指定任意 URL/header。沿用现有认证 transport 与权限错误；新 service 不自行重试，取消/晚到返回在解码前后检查。原请求核对支持固定 requestId，以及 candidate/binding/原请求内容约束；INCLUDE 核验 ID 与 verifySource 原字段匹配，不能省略或替换后当作同一回执。
3. `desktop/src/renderer/pages/Opportunities.tsx:1065–1071,1413–1416,1709–1712` 对 nullable URL 保持一致：来源信息缺失阻断复核、空 URL 不调用外部打开、查看原文按钮禁用。旧精确候选及原 requestId 查询继续使用指定 id；本次没有增加全库回退查询或跨目标恢复。

## 验证归属和交付边界

本 Agent 执行的是只读源码/Git 对象复核，未重跑测试、PG 或 GUI。读取主线程在最终合并树上执行的记录：`docs/qa/ui-visible-local-handoff/logs/incoming-9a-desktop-tests.log` 为 9 文件 / 198 passed / 2.49 秒；同目录 typecheck 记录 exit 0。生产 renderer 排除记录为 4778 graph modules、0 harness references、failures=[]。这些是**主线程执行、此处核阅**的结果。

本次真实运行图已变化（候选读取 factory/client 和 main 固定操作接线进入运行路径）。现有 8af8eaf Mac 包与可见 TEST bundle 继续保持旧版本绑定；生产排除日志即使记录 existingAsarChecked=true，也只表明检查了磁盘上的旧包，不能据此将该 ASAR 追认为 bd4b86a/9a59288 新产物。本次未构包，不扩大为真实候选写入、人工作业完整链或 Windows 实机验收通过。

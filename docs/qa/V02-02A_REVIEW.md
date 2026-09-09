# V02-02A 候选与来源能力契约验收

日期：2026-09-09。主实现责任：CodexiMac。工作分支：`codex/mac-candidate-contract`，起点 `f7e71653249f2b8102be75b92dda5d3894117ae6`。

## 边界

本卡实现独立、无网络/数据库副作用的候选上传体校验、来源能力声明、身份/内容/批次指纹及重放比较，契约见 [V02_CANDIDATE_INGESTION](../contracts/V02_CANDIDATE_INGESTION.md)。

- 五组平台 ID 映射不等于接通五个平台。六项能力默认 NOT_IMPLEMENTED，声明也不授予运行权限。
- 执行上下文是未认证 Claim，不是执行租约。租户、复核人与 APPROVED 不能从设备上传体注入。
- 未知发布时间保留 null；来源身份、内容版本和观察分开，公共网站身份包含规范 origin，匿名作者不按昵称合并。
- 同批重复/冲突整批拒绝；纯重放比较不等于数据库持久幂等。
- URL 仅做离线形状检查，不进行 DNS、跳转或 SSRF 运行验证；不安全回链需由连接器另记待补证，不能报告没有需求。
- 未实现 HTTP 上传、认证、候选持久化、实际采集、Skill 运行、审核接口或 UI 接入，未发生真实 CodexWin 接收 ACK。

## 实施与失败记录

1. 契约/实施计划：`8b48dda`，独立模块实现：`90efa8566482a7b0d8aa93b2cb4434f183ef4c49`，架构澄清：`1369566`。
2. 实施者先做模块缺失正常断言 RED（2 failed），随后行为反例 RED（57 failed）；首轮实现暴露两项时间错误码分类问题（55 passed / 2 failed），修复后契约59项通过。此为合成数据测试，不是平台测试。
3. `90efa856` 定向命令 `uv run --frozen pytest -q tests/test_candidate_contract.py tests/test_source_capabilities.py tests/test_research_import.py tests/test_research_skill_contract.py`：**70 passed in 0.13s**。compileall、secret scan、diff check 通过。
4. 独立架构与任务审核对 `1369566` 判定 **REQUEST_CHANGES**：错误 platform 类型漏出 TypeError；尾点 localhost/非规范数字 IP 被放行；父评论空 URL 跳过校验。另有 IP 异常文本耦合问题。审核者仅针对代码疑点运行合成反例，不重复全套或数据库测试。
5. 旧分支基线 `8b48dda` 在候选代码完成前的 bootstrap/D04 检查为 **93 failed / 51 passed**，原因是旧 authority 文案及旧时间夹具使用墙钟；已有 V02-10E 修复随后在 main `5d3373d` 合入。本卡不重复修改旧时钟测试，须整合最新 main 后重新运行整体回归。这个旧基线失败不是新候选代码的通过证据。
6. 主实现协调者补充定向复现：公开入口接受含 U+007F/U+0085/U+009F 的正文，遗漏既有控制字符限制；与上述修复同批补反例，技术文档明确 C0/DEL/C1 及 TAB/LF/CR 例外，不静默改写原文。
7. 修复 `40a491b7e31b09b808f5af833dba95f2fca44eeb` 的定向回归 **95 passed in 0.13s**；URL/platform/父URL反例 RED 9项，DEL/C1反例 RED 6项，修复后分别通过；compileall/secret scan/diff check 通过。对 `d89779f` 复审确认这些修复，但仍判定 **REQUEST_CHANGES**：hostname 在 IDNA 之前去尾点及缺少百分号策略，允许 Unicode 等价点号/编码后的 localhost/IP。审核者通过4个离线反例确认，要求共用规范化并补回归。
8. 第二轮修复 `37d86958cb895d742f98dbff84c50092718834a0`：编码/等价点号反例 RED 17项，聚焦 GREEN 22项，定向回归 **115 passed in 0.13s**。`device_authorization_architecture` 对含文档版本 `1374ef7` 的 task review 判定规格通过、质量 Approved，无未闭合发现；范围仍为本卡纯契约。
9. 整合最新 main `9077383` 后形成 `65e0c3f3f5f69ba72939f3c2344fd6ff8b030f64`；仅任务书冲突，保留最新身份回执及本卡登记。根代理独占专用测试 PostgreSQL，全部四个测试库连接变量均配置，全量 **809 passed in 47.30s、0 skipped**；compileall、`node --check static/app.js`、secret scan、diff check 均 exit 0。既有旧基线时钟失败已由主线修复消除，没有重写相同修复。
10. 独立最终审核 `candidate_final_review` 对 `9077383..65e0c3f` 判定 **REQUEST_CHANGES**：`is_global` 仍可接受组播 IP，URL 控制字符检查遗漏 C1。两项均由完整公开入口离线反例证实；不是实际 SSRF、真实平台或生产事件。全量809项未覆盖这两个缺口，必须补反例、修复和复审后才可推送本卡代码。
11. 同批补充 root 的时间格式反例：正则 `\d` 与 strptime 可接受非 ASCII 数字年份，违反规范 UTC 字符串边界；必须整条拒绝，不悄悄转换原始发布时间。最终修复一并覆盖发布、观察和父时间，正常 ASCII 值保持不变。

## 当前结论

上述审核问题正在按 RED→GREEN 修复并复审；尚不据此放行当前分支。最终精确 SHA、全量回归和独立结论待下方补录。实际 Win 接收、01C 执行授权及02B 上传仍是后续交付，不得从本卡的纯契约测试推导完成。

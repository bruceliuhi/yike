# Browser Profile ACL Implementation Plan

> **For agentic workers:** Use subagent-driven-development for independent tasks; keep this small security-boundary change serial and request focused independent review. User requires compressed verification and records.

**Goal:** 允许受控 Chromium 正常生成的档案权限，消除平台登录的错误阻断。

**Architecture:** profile 专用策略共享现有句柄遍历；strict runtime/output 入口不改变。只读验证，不修复或删除用户档案。

**Tech Stack:** Python ctypes / Windows NTFS / pytest。

## Chunk 1: Profile policy and acceptance

- [x] `tests/test_windows_private_directory.py` 添加真实 NTFS fixture：重复 grant、deny execute、四类网络路径及子节点；测试新入口接受且通用入口仍拒绝。反例覆盖未知 capability、路径越界、掩码提升、根权限、链接、不完整基础权限。
- [x] 运行 `python -m pytest -q tests/test_windows_private_directory.py`，确认新增正例因缺少入口失败。
- [x] `app/windows_private_directory.py` 最小提取遍历入口；新增 `verify_browser_profile_tree`；根 strict，后代允许 spec 中精确例外，其余 fail closed。
- [x] `app/windows_platform_login.py`、`app/windows_source_driver.py`、`app/windows_platform_outreach.py` 仅 profile 验证改为专用入口；补 login host 实际档案 ACL fixture 回归。
- [x] 运行三类 host 和私有目录定向测试；只读复核已停止实机档案。独立审核同一批差异，集中修正。
- [x] 更新 `docs/qa/WINDOWS_SYNC_20260912.md` 并提交 main（2a85dbc）；当时标明尚未构包/实机 UI 回测，不宣称上线。后续同源构包、安装、回归及实际平台失败按同一QA记录接续，不追认未通过项。

## Parallel acceptance task

- [x] 新同步公开 reader 的 Windows pytest 超长 case id 已红；只补短 ids 并验证。research optional SDK 用独立环境按锁安装后做协议测试，避免污染候选运行环境。

证据集中于 `docs/qa/WINDOWS_SYNC_20260912.md`：本批128通过、两项条件跳过中的runtime optin另补1通过；公开研究65通过；隔离真实Chromium两轮通过。设计及实现同批独立GO。产品候选构包及安装版真实平台授权不在上述通过范围。

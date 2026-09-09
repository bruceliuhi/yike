# 会话内容退出保护：独立代码审核

日期：2026-09-10。基线 `5536bc0bf4eba8e73ca9cfaf55a16b6b795ec4c0`，审核其上未提交的 `app/sessionContent.ts`、`app/hooks.ts`、`app/sessionDraftExit.ts` 与 `tests/ui/session-draft-exit.test.tsx`。本 Agent 非实现及测试作者，未改产品代码或提交 Git。

**最终限定代码 PASS：未发现剩余 P0/P1/P2。** 四类内容与原任务保护代码通过；独立指出的跟进改回原值误提示已窄修并复核关闭。以下保留原问题和验证过程，不将其列为当前未解决问题。

## 已核对的边界

- 资料键/字段与 Profile 实际保存规则匹配：有非空 name/text 的本机资料即属关闭丢失风险。服务端资料不在此键中；本机副本仍保留时继续提示合理，不等同于重复提交。
- 画像仅比较当前五个真实编辑字段与 baseline；保存/载入后相等不提示。评论和私信分别与 savedContent 比较，删除到空串仍识别为修改；只保存其中一类不会抹掉另一类风险。备注仅非空本机文本触发，列表筛选等偏好不触发。
- beforeunload 事件边界重新读快照，页面卸载后仍检查会话稿；未把本机制加入内部路由 guards，不额外阻止切页。先读存储再用内存覆盖，写入失败仍能保护内存内容。
- clear/clearAll 保留原 clearEpoch/keyEpoch 防复活规则；主动清除后不再提醒。原 sessionTaskContentAtRisk 原样作为第一分支，任务/模板行为不退化；操作锁不因本次提醒判定而被清除。
- followup:v3 新增 written 标记可区别“只打开默认服务端记录”和“真正写入/恢复的会话稿”；清除与完成提交调用原 clear 后解除。但 written 不是差异比较，存在下项。

## 已关闭 P2：跟进改回原值仍被当作未保存内容

位置：`app/hooks.ts:149–156,322–325`、`app/sessionContent.ts:36–39`。

最小状态路径：打开已有跟进更正 → 修改 note → 手动改回原 note → 关闭抽屉。`FollowupEditor.tsx:126` 此时 edited=false，内容与已登记服务端 initial 相同；但显式 setter 已留下 editedDraftKeys 及持久键，退出扫描仍判 true。仅调用同值 setter 也会触发。建议基于当前基线区分已恢复原值，覆盖“更改→恢复 initial→关闭/退出”反例，避免把保守提示描述成无误报。

修复后 followup setter 与当前 base 相等时清除 written 标记并尝试移除持久稿；已有内存值时扫描器仅采用内存标记，旧 sessionStorage 即使删除失败也不会在本会话重新制造退出风险。读取恢复稿时与当前 base 比较后标记，真实恢复稿仍受保护。clear/clearAll 原 keyEpoch 与内存清除机制保持，提交后清除不被旧存储重新覆盖。

## 独立验证与限制

Node 24 执行 `node node_modules/vitest/vitest.mjs run tests/ui/session-draft-exit.test.tsx tests/ui/hooks.test.tsx`：最终独立 **2 文件 / 36 passed，exit 0**，日志 `/tmp/yike-session-content-final-code-tests.log`。新增反例覆盖“编辑→恢复 initial→卸载”，含 removeItem 抛错仍不误报；恢复跟进稿、提交 clear、仅内存修改、默认更正、清除/失败和任务行为保持绿色。此前 33/35 passed 是重叠历史检查，不累加。

本结论仅覆盖代码及 jsdom beforeunload；没有执行原生退出/取消/重启、构包、真实服务或 Windows 验收，也不声称所有未纳入的业务草稿均已覆盖。

## 本次输入 SHA-256

- sessionContent.ts：`285a800f53aacc46f56d441b3f4560d9f19512d0a2bb8231aef99a3a1945dba5`
- hooks.ts：`7ed8675200d4e7e566ec17be95acbf07e1362c41d558dad1be00ae9d089e19bd`
- sessionDraftExit.ts：`6b3ca66c34ab6fb70f04fd495a35c1a1c9741fe795061a9b5f6a70b675973d89`
- session-draft-exit.test.tsx：`ffea2539ad8402880a3ba329919f89aa15ee7f5ead6a09ad84cad3d933103df9`

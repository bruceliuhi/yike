# P14/P15 90d06d1 冻结增量代码预审

候选：`90d06d1f317afc2ea1953b63d77844b98b539a2b`；基线：`0b05e98926e7e18858f0ab8e5780e49a3500ab4c`。范围为此提交九文件，未读取并行未提交修复作为本候选证据。

**结论：暂不批准最终收口。已知两项存储边界需精确差量修复后复审；除这些已报告问题外，未发现新的 P0/P1 或其它明确跨空间绕过路径。**

## 已验证的边界

- FollowupsPage 按 service、followup adapter、认证、用户、accountScope ID/版本建立页面 remount 边界；空间变更时旧记录、弹窗和表单立即退出，重新读取当前空间的数据。
- P15 草稿使用包含完整空间身份的 v3 key。返回原空间可以恢复该空间草稿，同用户另空间或同空间新版本不会继承正文。
- useFollowupOperation 在预检之后、派发之前、回执与核对的收尾阶段检查捕获的身份。旧空间迟到结果不触发当前提示、跳转或锁清除；返回原空间时仍核对原 requestId。
- v2 durable envelope 包含用户、空间/版本和原 binding；写入后回读校验再派发。拒绝不匹配 owner/key、被替换的原请求、错误回执绑定和不确定终态。legacy 无绑定请求保留原 ID，不能在当前空间自动认领；同空间旧版本和未标空间保守阻塞。
- 记录更正/撤销/标已读仍经过原商机、画像和原记录版本预检；未新增后台能力或真实外联动作。原稿后续人工修改不会因成功恢复标记被当作同一提交稿清掉。

## 仍需收口的已知问题

1. 未先打开 P14 时，旧 session-only `followup-operations` 记录尚未迁移；`clearLocalDrafts` 的旧锁保留集合不含它，可能清掉原请求保护。必须先保留原 ID，不能将未知请求默认为失败或按当前空间归属迁移。
2. SUCCEEDED 收尾当前通过 `useLocalDraft` 写 hash ACK；该 helper 对 sessionStorage 写入异常采用内存降级，而后仍删除 durable 原锁，刷新后可能丢去重标记。必须可靠保存 ACK 后才移除原 durable 保护。还需覆盖同一收尾链的草稿 clear() 失败：不能在未可靠删除已提交稿时继续清 ACK，否则旧稿刷新复活可形成新 UUID 重复保存。

第 1、2 项由 Hubble 先报告；本审核者确认代码路径，并补充第 2 项中草稿清理失败的同链测试要求。当前绿色用例不覆盖上述故障，不能用 49 passed 宣称它们关闭。

## 独立实际测试

从提交 `git archive 90d06d1 desktop` 建立隔离临时目录，仅链接已有 node_modules，避免在途修改污染结果。Node 24.19，运行：

```text
node node_modules/vitest/vitest.mjs run \
  tests/ui/followup-scope.test.tsx \
  tests/ui/followup-operation-storage.test.ts \
  tests/ui/followup-completion.test.tsx \
  tests/ui/followup-routing.test.tsx \
  tests/ui/followups.test.tsx \
  tests/ui/followup-ledger.test.tsx
```

结果：**6 文件、49 passed、exit 0**，2.18 秒；日志 `/tmp/yike-followup-code-90d06d1-tests.log`。未跑全套前端、构包或 GUI 验收；未修改产品源码。

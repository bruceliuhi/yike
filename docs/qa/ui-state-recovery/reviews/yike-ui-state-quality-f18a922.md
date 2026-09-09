# f18a922 P14/P15 独立限定质量审核

候选：**`f18a922b778f437400de8165e67b162fea028724`**。本切片基线 `0b05e98926e7e18858f0ab8e5780e49a3500ab4c`，包含 `90d06d1` 初次隔离、`4954534` 存储失败收口和 `f18a922` 旧 facade 成功确认增量。

**源码范围限定 PASS，无剩余 P0/P1 阻断。** 本审核者为这些新增隔离/恢复改动的非作者；仅审本切片的 Followups、FollowupEditor、RelatedReplies、useFollowupOperation、followupOperationStorage、hooks 中旧 followup 键保护增量和对应契约/测试。既有模块中的本审核者历史实现不作为此次独立自批对象。最终全量、新 Mac 包及实际可见原生验收仍待新候选证据，不能沿用 a25 中间包或 495 截图冒称完成。

## 关键边界核对

1. 页面/编辑器、列表/回复、预检按服务实例、认证状态、userId、可信空间 ID/version 隔离。迟到预检不再派发；旧空间迟到成功不清原锁、当前草稿、不发成功提示或导航。原请求需回到精确 owner 核对。
2. 新锁使用 v2 owner 封套、完整六元绑定、写入回读、删除原请求比对和删除后回读。旧 v1 不猜当前空间；scope 缺失或同空间旧版本保留为历史阻塞，其它已知空间不冒称本空间请求。
3. 初审发现的“先清草稿、后首次读取旧 session 锁”已修：全局清理保护 followup 前缀；首次读取再可靠迁入原用户旧持久 ledger，仍未绑定当前空间。失败不误核销历史锁。
4. 初审发现的“成功 ACK 写失败却先清原锁”已修：成功确认先将精确草稿 key/hash 标记写 sessionStorage 并回读一致，再发布内存、删除 durable 原锁；抛错、静默不写或上下文失效均保留原锁。原稿删除不可核验时不消费 ACK，因此旧稿再出现仍受防重复保护。
5. P15 对成功恢复稿同时核对空间、草稿键及完整表单 hash；效果路径和快速保存路径都检查。原未知稿的人工作后修改不匹配旧 hash，仍保留；FAILED 稿不自动清除。没有把确认旧请求当作清空所有新草稿的授权。
6. f18 将相同可靠收尾应用到真实旧 `addFollowup` facade：收到成功但本机 ACK/清锁失败时明确区分服务器返回和本机确认故障，保留保护，不伪造不存在的 operation 查询能力。直接成功的原稿删除失败也保留 ACK。
7. `UI_FOLLOWUP_CONTRACT.md` 与上述最终代码一致：前端锁/草稿 hash 是恢复元数据，服务端仍须重验归属、幂等和事务；未宣称结构化回复/提醒/后台已上线。

## 实际独立验证

为避免共享工作树的后续变更误绑，使用 `git archive f18a922 desktop` 解到 `/tmp/yike-followup-review-f18-ihihb50c`，只链接已安装 node_modules，不构包、不运行生产服务。Node 24.19.0 执行：

```sh
npx vitest run tests/ui/followup-completion.test.tsx tests/ui/followup-scope.test.tsx tests/ui/followup-operation-storage.test.ts tests/ui/followup-ledger.test.tsx tests/ui/followup-routing.test.tsx tests/ui/followups.test.tsx
```

实际 **6 文件、56 passed**，原始日志 [yike-followup-independent-f18-tests.log](../logs/yike-followup-independent-f18-tests.log)。覆盖精确空间/历史锁、先清再读、成功 ACK 抛错/静默不写、删稿失败、新人工改稿、legacy 成功异常、原有创建/纠正/撤销/已读与路由。没有将作者 72 项、此次 56 项或旧全量数字相加。`git diff 0b05e98 f18a922 --check` 通过。文档本地链接检查无缺失。

## 可见与交付限制

P14/P15 已有 IAB/CUA 正常保存、纠正、日历选择、撤销和标已读证据，但使用 **495** 静态 TEST build；结构化分支在 f18 被抽到共用收尾 helper，虽保留该分支语义，截图仍不改绑为 f18 重新执行。可见 UNKNOWN 和匹配回复的人工跟进入口 P2 仍需后续验收/切片；后者不是本次跨空间 P1 已关闭的同义词。

本报告关闭限定源码范围内的跨空间和已提交稿重复风险，不宣称所有页面/业务状态、新原生包、Windows 安装缩放或生产服务已通过。最终产物必须另行核对 commit、输入与 ASAR/ZIP，并保留实际原生可见证据。

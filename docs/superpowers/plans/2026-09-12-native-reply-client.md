# 原生回复同步接普通跟进页

Base `654dacf`；沿批准V0.2回复链路，使用现有读取/签名/证据模块。只测改动路径，整批一次独立审核，不构包或真实平台操作。

## Global Constraints

- Renderer只发 `{action:'SYNC',opportunityId,requestId}`，不得提交正文、根评论、设备、路径或签名。新私有IPC `desktop:native-reply`；preload `nativeReplyCommand`。main从原SENT sync-context取原context/claim/root，确认owner/device/摘要/当前profile及连接receipt后才打开只读driver。
- CHECK→READ_REPLIES→实际停止清理→逐条签名入库；不调用execute、不读私信、不改已读、不自动轮询。完整/部分读取明确区别；失败不是零回复。主进程同一时刻一个同步，取消/退出/身份变化后不再上报，清理失败须保持阻塞并报告SOURCE_STOP_FAILED。
- 返回 `{state:'SYNCED',requestId,coverage:'COMPLETE'|'PARTIAL',observed:number,recorded:number}` 或 `{state:'FAILED',error,recorded:number}`；error枚举 INVALID_REQUEST/BUSY/SESSION_CHANGED/DEVICE_NOT_READY/CONNECTION_CHANGED/SOURCE_UNAVAILABLE/SOURCE_STOP_FAILED/REPLY_SYNC_FAILED。recorded是成功核实的入库回执数，包含服务端去重，绝不声称净新增；中途失败保留计数。
- 事件由main把真实batch绑定原context生成，每次生成新UUID，原请求/租户/画像/来源固定；保存回复后核对返回原文/关联及设备证明，接受语义去重返回原event_id/observed_at，不增加重复事实。观察到编辑冲突时停并显示失败，不自动捏造更正。
- 当前读取只支持XHS原POST_COMMENT；其他平台保持证据展示。原上下文不依赖当前草稿或画像是否已换。profile注册/VERIFY/CONNECTED仍须原账号及连接版本匹配；不读已归档其他profile。

### Task 1: 普通跟进页同步意图（独立代理）

Own `desktop/src/shared/nativeReply.ts`、contracts.ts、preload/index.ts、renderer/pages/followups/NativeReplySync.tsx及ReplyEvidencePanel.tsx、新定向UI测试。不得改main或其他代理文件。

- shared严格Zod命令和上述结果类型，export NATIVE_REPLY_CHANNEL。DesktopBridge增加optional nativeReplyCommand，preload fixed invoke；不要把replies.source/prepare/record放公共API。
- 现ReplyEvidencePanel加载证据后或空证据也显示小红书同步入口。来源requestId是同用户/tenant/商机/comment本机nativeOutreachLedger记录（PENDING也可提交给main核验，文案不称已发），及已加载当前商机XHS/comment平台证据的outreach_request_id，去重。没有原请求则解释需先完成并核实原生联系，不能让用户填ID。localStorage仅hint，main必须再核实。
- 点击只传SYNC三字段；每个原请求有明确按钮，运行时禁止重复点。成功显示完整/部分范围、读取条数、保存核实条数（含去重，不称新线索/新回复）；失败展示固定中文错误，不显示原始异常，保留已保存数并刷新证据。所有有效结果触发onSynced=resource.reload。
- 身份/商机切换、卸载后不显示旧返回；检查返回requestId和结果schema，未知返回显示未确认。sample/未登录/非XHS不调用，browser没有native方法给出桌面入口说明。保留现有来源证明说明。
- 用定向测试RED→GREEN验证空证据但原ledger可同步、精确payload、部分成功、失败、无方法/样例、切换旧返回不串页；不全测不构包。提交owned文件并把简短结果写本任务brief对应report，root统一审核。

### Task 2: main身份/profile/来源装配（root）

- 创建nativeReplyController，复用scope、vault、profileStore和driver；严格context签名摘要与owner/device/opportunity匹配；从服务端认证上下文得tenant，不接受renderer身份。
- 原profile VERIFY receipt与当前CONNECTED匹配原连接；check匹配context/账号/对象/时间；读取batch后stop物理清理确认才prepare/record。所有await前后检查身份、abort、当前device版本，timer保障无scope signal变化的注销也停止；app quit等待controller停止与running结束。
- 事件使用原outreach requestId（不是draft.binding.requestId），服务端去重回执可保留原UUID/观察时间。只返回计数不通过IPC返回私有上下文正文。
- main attachPlatformRuntime、trustedSender IPC和shutdown接线。修复deviceIdentityController认证DTO接收当前后端account_scope（严格验证已提供字段，兼容原不带字段会话），定向真实形状测试防止当前所有worker打不开。
- 定向controller/原deviceIdentity测试与一次tsc，最后整批独立审核和main推送。Windows新包/实际XHS/部署/UAT未验证，不标完整Goal完成。

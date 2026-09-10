# 07B Task 1：不可变加密结果记录报告

## 结果

- 新增 `desktop/src/main/outreachResultOutbox.ts` 与定向测试 `desktop/tests/outreachResultOutbox.test.ts`。
- 以可信绝对目录、OS `DeviceKeyProtection`、按 scope/requestId 哈希文件名和 `wx` 排他创建持久化结果元数据；文件与 POSIX 目录均执行同步。
- 重建 outbox 后仍读取原 `resultId` 与原 `outcome`；相同记录幂等重放，claim/device/context/resultId/outcome 任一变化均冲突且不覆盖。
- 只接受 123 语义下具有明确投递事实的 `SENT` / `FAILED`。`UNKNOWN` 不落盘，避免未知占位阻断后续明确结果恢复。
- 密文不保存正文、Cookie、私钥或签名；损坏、解密失败、符号链接及存储失败均失败关闭，并使用固定错误码，不泄露底层路径或 OS 错误。

## 接口

- `OutreachResultRecord`: `requestId`、`claimId`、`deviceId`、`contextSha256`、`resultId`、`outcome: NativeOutreachOutcome`。
- `OutreachResultOutbox.read(scope, requestId): Promise<OutreachResultRecord | null>`。
- `OutreachResultOutbox.put(scope, record): Promise<OutreachResultRecord>`。
- `createOutreachResultOutbox({directory, protection})`；scope 直接复用 `OutreachConsumptionScope` 的 origin/user/tenant，不绑定 session 或 credentialVersion。

## 验证与边界

- 定向命令：`/Users/xingheimac/.nvm/versions/node/v24.19.0/bin/node ./node_modules/vitest/vitest.mjs run tests/outreachResultOutbox.test.ts`。
- 覆盖落盘重建、scope/request 隔离、输入快照、字段冲突、并发排他创建、损坏失败关闭、无明文、符号链接与存储/保护失败。
- 本任务未改旧文件、未执行真实平台操作、未构包、未提交或推送。该工程防护不等于 Windows 实机、所有断电场景、真实 driver/main/UI 或部署验收已完成。

## 类型修正记录

- 原统一 `tsc --noEmit` 失败：测试 fixture 中 `outcome.confirmed` / `confirmedNotDelivered` 被拓宽为 `boolean`，不满足 `NativeOutreachOutcome` 的 literal `true` 类型；本地首次补返回类型后仍由 `tests/outreachResultOutbox.test.ts:114` 报同类 `TS2322`。
- 仅将测试 fixture 的两个事实布尔值收窄为 `true as const`，没有修改生产约束或使用宽泛 cast 遮掩错误。
- 修后命令：`/Users/xingheimac/.nvm/versions/node/v24.19.0/bin/node ./node_modules/typescript/bin/tsc --noEmit`，退出码 `0`、无输出。
- 修正前已完成的 outbox 运行测试仍为 `9 passed`；本次为纯类型收窄，按分工未重复运行该专项。

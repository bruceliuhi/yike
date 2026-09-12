# 公开来源跨轮抽样轮换

用户9月11日已授权V0.2内自主细化。当前基线 `c8c272a`，实际公开项目driver每轮在关键词过滤前取index前3项；不是平台需求只有3条。目标是在原请求/字节/时间预算内扩大当前列表覆盖，并定期重新读取作者回复。

## 选择及边界

选择“已持久化批次驱动轮换”，不使用内存计数（重启丢失），也不把原生平台页码硬套到动态公开index（不是真实游标）。本轮只接既有三个PUBLIC_WEB固定源，原生四平台的真实分页游标、离开index的已留存来源公平复查仍属完整Goal后续项。

成功读取并上传的批次是读取进度，任务FINISH是执行终态，两者分开。包含0条匹配的有效批次；上传前失败/取消无批次不推进；COMMIT成功但回包/FINISH丢失，原文已保存，下一轮不得忘掉该进度。原有未知结果恢复和发送门禁不变。

## 数据与协议

不新建游标表，不改candidate上传形状/回执。服务端在CLAIM事务中，按当前task找到本人的monitor occurrence和plan，计算同owner/plan/profile/strategy/PUBLIC_WEB匿名来源下、排除当前platform_run的已落库批次不同platform_run数量。不可按records、observations或request数量计数；不按暂停/恢复revision清零。publicSource来自不可变配置，不接受客户端自报plan/source/round。

请求可选 `public_sampling_version:1`，只允许CLAIM，缺省序列化不增加null字段，旧签名/日志字节不变。仅该显式请求的CLAIM回执增加 `public_sampling:{schema_version:"public-sampling-round-v1",plan_id,source_id,round}`。round为0..2147483647；source_id为既有公开源ID。回执通过既有操作日志原子留存，重放CLAIM固定原round。RENEW不带新字段，不改变正在执行的抽样输入。

协商复用只读 `GET /execution-support?sampling_version=1`：新服务仅在已支持public_monitor时增加 `public_sampling:"committed-round-v1"`。无query旧请求原样返回；新客户端只在monitor含PUBLIC_WEB时询问。已核旧handler忽略query，故会返回旧形状而保持旧读取行为；无网络/解析降级重试。只有明确capability才在CLAIM opt-in，不能将UNKNOWN租约换请求重试。

## 抽样规则

每轮始终重新读固定index。预算b仍为公开项目 `min(3,maxRecords)`，其他源为maxRecords；总index最多100项、最多1MiB、20秒、60秒冷却不变。无协商/一次性任务完全保留旧取前b行为。

有round时：空列表返回空；b覆盖全列表则读取全部。b>=2保留最新index[0]，从剩余列表按 `round*(b-1) % (length-1)` 环形读取b-1项；同轮不重复。b=1时偶数轮读最新，奇数轮依次轮换剩余。例如稳定7项、b=3，前三轮为 `[0,1,2] → [0,3,4] → [0,5,6]`，下一轮重新复查。先按预算选择，再按原关键词/排除过滤；不能为凑条数扩大读取。每个被选择的匹配项目仍正常读取作者回复，不以主帖正文相同为由跳过。

这是动态列表内的有界抽样，不保证全站覆盖，插入/删除/重排仍可能重复或漏读。未读到不等于无需求。账户/策略/来源隔离、真实原文、作者更新时间含义、取消/限流和原子上传约束保持。

## 验收

真实受限PG和正式签名链证明轮数随批次COMMIT推进、空批推进、同run/请求重放不双计、FINISH丢失不抹进度、未上传不推进、其他owner/plan/策略不串用、CLAIM重放固定；客户端验证协商/旧协议/固定输入/预算/作者重复读取/三轮覆盖与回绕。合成来源不得计成真实新商机。定向测试后一次整批独立审核；不部署、构包或外部发送。

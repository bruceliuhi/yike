# 三平台原任务恢复：实际 HTTP/PostgreSQL 联验

基线 `dc075af780dc623472a32f2d1cbf64f94261c7f5`。不新增产品范围，验证上一批跨层实际接线；来源内容仍为合成数据，绝不作为平台/Windows/商业证据。

## Task 1: 一个有真实协议约束的贯通场景

复用 `tests/test_desktop_foreground_collection_http_postgres.py` 中的真实策略/账号登记/签名原生controller、loopback HTTP、受限PostgreSQL fixture，新增一个单独三平台场景（可以新建专用 Python/TS integration 文件，避免重写旧单平台用例）。测试仅运行新增案例。

- 真正保存/确认三平台策略及三条本人连接，使用显式 `three-platform-foreground-v1` 能力；平台顺序 XHS→抖音→B站，与 execution.task 按字母返回顺序不同。
- 真实Node identity/session/signing/journals/controller→socket HTTP→真实后端策略/执行/候选存储→受限PG，不替换resolver、执行服务、签名或候选上传。只有来源driver返回已标注合成内容；每次driver接收绑定的平台账号、独立profile和固定预算都检查。
- 总预算设置可证明均分与余数分配，driver返回不超过分配额的原文记录；每个平台仅启动一次、原文不变。
- 第二个平台真实candidate POST落库后丢失响应，第三个平台不能启动。停止/重建controller后，RECOVER只查原批次并完成原FINISH，不重采；再显式resumeStart，读真实乱序task与前缀RUNNING/false回执后仅启动第三个平台。
- 最后真数据库验证同一任务SUCCEEDED、3个平台都SUCCEEDED、原START只有一条、没有重复候选批次/观察、前缀CLAIM/FINISH无重复。本次返回源记录预算合计不超过原总额。
- 不伪造成功输出，不吞测试失败，必须无skip。环境变量若缺失可按现有fixtures跳过，但本次验收必须实际运行。不能把测试admin连接传给Node客户端；私有session/签名key不得出现在输出、日志或Git。
- 只写测试文件；如发现产品缺陷，向根报告根因与最小修复，不自行扩大修改。根负责隔离PG、文档与最终提交。共享现有 `yike-identity-contract-pg` 不可碰。
- 一次独立审核测试有效性，不重复产品构包或已有全量测试；无真实平台/模型/消息/生产调用。

## 状态

进行中。新证据尚未取得；目标与已有代码验收边界保持。

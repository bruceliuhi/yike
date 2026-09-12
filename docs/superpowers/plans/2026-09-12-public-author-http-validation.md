# 作者更新普通链路验证

**Goal:** 验证已实现作者源通过普通确认、签名上传、HTTP原文回读与客户端严格解析；不把单层测试当完整链路。
**Architecture:** 复用已有 `tests/test_public_community_http_postgres.py` 和 `desktop/tests/integration/public-community-live.test.ts`；仅扩显式测试来源，不改产品权限或生产配置。设计沿用 `2026-09-11-public-author-context-design.md`，已获范围内自行细化授权。
**Tech Stack:** 既有Python/Uvicorn/隔离PG、Node24/TypeScript客户端。

按 brainstorming/writing-plans 收敛：不新建另一测试框架，不直接管理员导入；选择现有实际HTTP链，因为前轮PG未用实际客户端schema重验导致遗漏nullable回归。本片只补跨边界验证，模型效果后续单独记录，不做新模型接口。

- [x] 新source参数采用新mode、最多3篇，合成fetch提供分开的topic和作者reply；断言固定总请求数/回复保留/无重复采集。
- [x] 原文回读调用 `parseRawCandidateEvidence`，逐条对照source_context，不只检查几个主帖字段；输出只留sourceID、回复数量等元数据，不输出正文/凭据。
- [x] 默认合成新source一次实际HTTP/PG客户端链；非零样本才有链路结论。任何缺陷先保留失败，再最小修复。
- [x] `YIKE_PUBLIC_COMMUNITY_NETWORK=1` 仅新source一次真实读取，不重试失败或为凑量补读；最多3篇/4GET。零结果记不充分，不宣布商机或链路通过。
- [x] 独立审核固定提交；合主线但不部署/构包/外发。保留实际账号、OS密钥库、Windows、客户价值的未验边界。

命令：`pytest -q -s tests/test_public_community_http_postgres.py -k outsourcing`，仅显式本机专用 `/yike_public_flow` 数据库，子进程不得携带数据库环境。真实读取增加NETWORK=1，其余合同不变。不得重跑旧latest/qna实网。新增断言代码核心：`expect(content.source_context).toEqual(record.source_context)` 和 `parseRawCandidateEvidence(response.data, expected)`；三源能力目录与服务器真实结果一致。

## 实施证据

源码 `6dc4e30`；日志隐私差量 `bc9fc72`，非作者整批及差量GO。深比较最终使用 `isDeepStrictEqual` 后断言布尔，防止失败日志打印真实作者正文；不改变判等语义。

- 首次合成fixture未支持outsourcing节点，FAILED；补齐后实际上传变为UPLOAD_UNKNOWN。追踪发现 `candidateProofSigner.canonicalJson` 不支持boolean，新context中的布尔字段导致签名前失败。旧驱动/PG单层检查与前批独立审核均未覆盖这一实际交界，不追认前批为整链可用。
- 新增true/false读取范围签名单测先2失败；产品仅增加原生boolean编码，严格schema、设备/用户/批次绑定不变。整签名单测52 passed，包含旧固定哈希与修改后拒签；`tsc --noEmit`通过。
- 合成实际HTTP/受限PG：1 passed / 3 deselected，5.56s。用例内部2个任务、同1来源候选；保留作者1条、读取回复2条，第三方正文不保存。重复任务复用候选/版本并追加观察；同进程重建controller/journal恢复不重读，不是真实进程或Windows重启。
- 唯一实网：同命令显式NETWORK=1，1 passed / 3 deselected，9.50s。固定索引1次＋回复3次，取得3条候选，经普通准备/确认/签名上传/完成、列表及严格原文回读；无外发。元数据：1240702已读0/预期0/作者0；1240655已读2/预期2/作者2；1240435已读2/预期2/作者1。本次计数相符，附言仍未读；不是3条合格商机。
- 来源正文只在隔离库和测试进程流转，fixture结束清理，本批保留上述来源ID和计数证据，不为补正文或日志重抓。本片没有实际模型调用，因此未验证作者结束声明是否影响模型结果。下一次语义验收应在同一次实际采样的fixture清理前调用已有模型路径，保留最小判断/引用摘要，不先删输入再重抓。
- 未构包、部署、读客户数据、发送消息或SMS。隔离PG容器测试后停止；主线同步不代表客户服务已更新。

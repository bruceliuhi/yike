# 后端来件 2d799bc：限定整合兼容复核

## 精确结论

**限定整合兼容 PASS，未发现影响本轮 P04、任务返回上下文、现有 P14/P15 或桌面包的新增合并阻断。** 这不是对全部新后端代码或新触达持久层的生产批准。

- 来件：`2d799bc4b6a228c908c9eef1e2f86a4a130cc0d0`。
- 来件比较基线：`0eab72a9fe293a8e11e136434327537d3a62f69f`。
- 最终合并：`eda1e2f0d6d2f7e4667f1e2684b5017b3cf74455`。
- 实际本地父提交：`249bc77a8ed94bcc9fb1c31c7fd6e079c61d1717`；远端父提交为上述 `2d799bc`。
- 仓库：`/Users/bruce/Developer/work/yike-ai-product-design`。

审核人仅只读核对源码、接口、Git 字节和来件 QA，未改后端/桌面，未重跑 PostgreSQL、平台或生产测试，也未重做 GUI、全桌面或构包。

## 合并及本地字节

来件相对 `0eab72a` 为 39 文件、3382 行新增/14 行删除，全部位于后端、数据库授权/迁移、Python 测试或文档，`desktop/` 零变化。

实际 Git 逐树核对：

- 合并 `desktop/` 与本地父及 `d816a9d` 完全相同，树 ID `ab09e3e3c86820e38189965d03e56da76197c211`；`desktop/src` 与 `fcae33e` 相同。因此未因来件改变既有桌面产物输入。
- `pilot/`、`migrations/`、`deploy/`、`tests/` 分别与 `2d799bc` 完全相同，没有重写来件实现。
- 已审 P04 `d66d487` 全部 9 个文件与合并中的对应文件相同，原独立 40 项测试结论仍按原候选继承，不改称本次重跑。
- 双方共同改动仅 `docs/INTEGRATION_STATUS.md`、`docs/V02_IMPLEMENTATION_TASKBOOK.md`。唯一需人工处理的整合状态开头已保留本地资料/返回验收和远端来源核验/设备登记记录；任务书正常合并。两个文档分别保留两个父提交的原行序列。
- 合并差异格式检查通过，指定源码及共享文档无 Git 冲突标记。

本次没有把原 ASAR/ZIP 证据改称新后端实际运行验收。主线程后续若再改 P04 布局，将属于新的桌面字节，不能继承本报告的产物不变断言。

## 四类来件的接口影响

### 1. 候选待签字节：805aeb0

`candidate_api.py` 抽出原 4 MiB 有界 JSON 读取逻辑，原 `candidate-batches` 上传仍要求原 `{batch, signature}`；新 `candidate-submission-signing-payload` 只接 `{batch}`。签名准备经既有 runtime 校验当前会话、规范 batch、当前设备/凭据，并返回原签名域字节及绑定；未替换正式 ingest、历史回执优先恢复或执行授权。

该路由与桌面 P04 资料保存、returnTo 路由和既有 UI `TaskOperationsService` 不共用协议。当前桌面没有新增调用；不能把获得候选签名原文视为已采集、已上传或已执行。

### 2. 原来源核验 ID 回执：9d9e965

生产改动仅将已验证的 `request.sourceVerificationId` 加入新决策回执的 `review` 投影。原字段、请求指纹、不可变回执和原请求恢复机制未改；历史缺该字段回执不向当前核验补值。

此增量供新 05G 候选复核接入使用，现桌面旧 Candidate/Review 模型不能自动当成该后端 DTO。当前未新增 desktop adapter，不影响 P14 的普通商机详情或原请求跟进恢复；不能因字段现在存在就视为 05G 客户端已验收。

### 3. 可恢复设备登记：a6f68dd

新增登记 POST、按原 request ID 查询登记回执和 owner 范围当前 identity GET；旧设备登记、公钥挑战和证明路由保留。登记回执与当前设备状态分开，历史成功不等于当前持钥、平台连接或任务授权。116 为新增迁移和受限授权，不改旧迁移内容。

当前 P16/P18 继续原可选接口和本机状态管理，未被新服务注册或字段名隐式替代；本轮任务返回参数也没有变化。真实桌面消费还需保存原请求/本机设备 ID、比对密钥与凭据版本，并接现有未知恢复流程。本审核未做此后续实现或签收。

### 4. 触达/回复合同与确认持久层

`outreach_contract.py`、`outreach_store.py`、`reply_contract.py` 是新独立模块。Git 查询未见它们被当前普通 UI 路由、桌面 `OutreachService`、`FollowupService` 或旧 facade 装配；`pilot/db.py` 仅将 117 确认表迁移加入序列。因此当前 P12/P13/P14/P15 的发送、未匹配回复、人工登记和原请求锁不会因这些文件存在而改用新协议。

未来接入需要显式适配，不能直接替换：新回复事件要求 UUID 类型的域身份和原发送请求，当前人工跟进可没有既往平台发送；新连接 `AVAILABLE` 能力、连接 ID/版本和确认快照也不是旧 UI 状态的直接别名。它们的独立进程内 registry 不是生产幂等，确认持久层目前也不是已接通发送队列。

**必须保留来件原限制：** `docs/qa/V02_OUTREACH_PERSISTENCE_CONTRACT.md` 仅记录 12 项纯函数/快照测试、编译和 `PASS WITH MAJOR FOLLOW-UP`。其 PostgreSQL 迁移执行、受限角色、并发、回滚、会话恢复及正式路由授权尚未验证。该重大后续工作不影响当前未挂载桌面路径，但本报告不批准将该 store 用于真实发送。117 已进入迁移列表，正式环境迁移和权限仍须另验。

## QA 归属与建议接收检查

已阅读并保留以下来件 QA 的各自归属：

- `V02_CANDIDATE_SUBMISSION_SIGNING.md`：241 项纯边界与 28 项真实 ASGI/受限 PG分开；含最初 404 RED 和测试 fixture 修正；独立整片终审 PASS。来源、策略输入仍有合成边界。
- `V02_CANDIDATE_ASSESSMENT_REVIEW.md` 的 9d9e965 小节：101 项相关真实 HTTP/PG、46 项纯边界及独立复核分别记录；不向历史缺字段回执回填。
- `V02_DEVICE_REGISTRATION_RECOVERY.md`：登记/密钥、受限 PG、HTTP 与纯边界各自记录；独立审为 PASS WITH MINOR，空行修正后差异检查通过；不是 Windows 消费或真实平台验收。
- `V02_OUTREACH_PERSISTENCE_CONTRACT.md`：仅工程骨架及纯合同，明确保留 MAJOR FOLLOW-UP。新 reply 合同是进程内模型，不冒报回复回流。

由于既有 candidate JSON helper 被抽取、设备 API 增加路由且迁移序列新增，建议主线程做一次有界纯接收集合，不重复 PG：

```sh
uv run --frozen pytest -q \
  tests/test_candidate_ingestion_api.py \
  tests/test_candidate_review_api.py \
  tests/test_device_registration.py \
  tests/test_device_keys.py \
  tests/test_ui_api.py \
  tests/test_outreach_contract.py \
  tests/test_outreach_store.py \
  tests/test_reply_contract.py
```

这是建议而非本审核人已执行结果；若主线程运行，应另绑定其实际日志和退出码。既有桌面、原生、生产平台、发送/回复、Windows 发行、CP-06 与完整 Goal 的未完成范围保持不变。

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
- 双方共同改动仅 `docs/INTEGRATION_STATUS.md`、`docs/V02_IMPLEMENTATION_TASKBOOK.md`。唯一需人工处理的整合状态开头已保留本地资料/返回验收和远端来源核验/设备登记记录；整合状态原记录保留双方行序列；任务书保留本地最新 05A 行和远端最新 06/07/08 行，替换各自过时行，其余新增历史与认领保留，未宣称完整 Goal 完成。
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


## 后续来件 804dece 的限定追加

追加来件：`804dece8d63bcf128d3dde6b0e974d502402eb6f`，比较基线为 `2d799bc`。本节先绑定来件对象；最终合并 SHA 另补，不把移动工作树当作该对象。

实际差异为 11 文件、318 行新增/3 行删除；`desktop/` 零变化。新增 `ReplyEventStore`、118 迁移与独立 SELECT/INSERT 授权脚本，`pilot/db.py` 注册该迁移。源码检索未见 `ReplyEventStore` 或 reply 合同被普通 UI 路由、P14/P15 facade、桌面可选回复/跟进服务装配。因而本次来件仍不改变当前 P14 精确详情授权、人工登记、回复目标与原请求锁的执行路径，限定 UI 合并兼容没有新增阻断。

`docs/qa/V02_REPLY_PERSISTENCE_CONTRACT.md` 记录的是 reply/outreach 四个纯测试文件合跑 **32 passed**、编译与差异检查；本审核未执行这些检查，不与上一批数字相加。新 QA 明确没有 PostgreSQL 实例，未证明迁移、RLS、并发恢复/冲突、回滚、会话撤销、角色授权或真实平台回流；正式服务还须在同一事务核对商机/来源/画像/发送请求归属及纠正目标。原 outreach QA 的 **MAJOR FOLLOW-UP** 仍保留。本节也不签收新持久层为正式可用服务。

还需保留一个具体后续实现问题：`pilot/reply_store.py:95–112` 对平台回复先按原来源/发送请求/平台/公开回复 ID 读取最新行，再在新 `event_id` 且内容变化时拒绝 `duplicate_reply_conflict`。因此对已有 ACTIVE 回复提交新 ID 的 CORRECTED/VOID 追加事件，当前会进入冲突分支；进程内 `ReplyEventRegistry` 新增的 HISTORY 分支并没有在 store 中同步实现。正式挂载前须统一该存储行为与 `V02_REPLY_FOLLOWUP.md` 的追加历史合同并补相应真实持久层验证。这是未接入后端候选的功能限制，不是当前桌面 P14/P15 的新运行回归。

结论仍为 **限定现有 UI 兼容 PASS，后端持久层接通前保留上述未完成项**。本节没有生产、Windows、GUI、真实回复或全 Goal 完成声明。

## 独立 P04 空态增量（单独来源）

另独立只读核对 `8af8eafba0faef68ae48ea76f3d5d4a70c7b06c8`：相对 `eda1e2f` 仅 `MaterialsWorkspace.tsx` 5 行新增/1 行删除。已读取空同步列表且本机草稿非空时，原大空态改为一行提示；无本机草稿仍用原 Empty。带入、编辑、稳定资料 ID、已存在版本、解析中禁用和取消语义均未改。此窄改无新增 P0/P1/P2；33 项定向与类型检查来自非本审核人的执行，未重跑，视觉以主线程同视口验收为准。

该提交确实改变桌面源文件，因此前文 `eda1e2f` 的桌面不变断言只适用于其精确提交；后续产物须按 `8af8eaf` 或其后同树提交重新绑定。


## 最终推送对象绑定：d5ee8c2

最终对象：**`d5ee8c27532ff15436eaa2bcfeafca1a9e0e86a0`**。本审核以 Git 对象只读核对，限定整合兼容结论为 **PASS，无影响已审桌面路径的新增合并阻断**。

- 先正常合并 `804dece8d63bcf128d3dde6b0e974d502402eb6f`，得到 `5d48b5c37deee6b720d922508439aac0037ebf4c`；它的本地父为 `a4dccbac7e75f2a55263c79838fd39f0aa829867`。
- 最终 `d5ee8c2` 两个父提交为上述 `5d48b5c` 与 `92fd168164003ce0f9a5b810dee2145b411970da`。8af、804 和 92fd 三个来源均为最终对象祖先，未改写来源历史。
- 最终 `desktop/` 与 `8af8eaf` 逐树完全相同，树 ID 为 `ba8d3346645fc3c6b38aaa77038f48a7379273fe`；最终 `pilot/`、`migrations/`、`deploy/`、`tests/` 分别与 `92fd168` 完全相同。
- 最后一轮相对本地父仅四个来件文件：`pilot/reply_store.py` 与三份整合/合同/QA 文档。差异检查通过，原本地 P04/05A 记录与远端回复持久层边界保留。

92fd 的产品增量只有 `ReplyEventStore.record` 中 12 行同事务关联检查：平台回复必须找到同 owner、原发送 request ID 的确认记录，且商机和来源匹配，否则返回 `reply_origin_unavailable`。它未新增普通运行路由或 desktop adapter；最终对象的检索仍只有 store 自身定义/导出。持久“确认”也不等于已经实际发送或实际收到回复，原来源/画像/纠正目标、真实数据库和真实回流的剩余门禁未关闭。804 节指出的 correction 新 ID 与当前 store 去重分支不一致仍未由这 12 行修复，继续列为正式接通前的后续项。

主线程另报告已执行 eda 的 88/90 项纯接收集合。先前 summary 将来件作者的 32 项误记为主线程 804 接收结果：旧 `incoming-804dece-reply-tests.log` 实际为文件未找到 / no tests，原失败保留，不能记作通过。主线程现于精确 `d5ee8c2` 新执行 reply/outreach 四个纯测试文件，实际 **32 passed / 0.14s**，日志为 `docs/qa/ui-visible-local-handoff/logs/incoming-d5ee8c2-reply-outreach-tests.log`。以上主线程执行归属经本次说明更正；本审核未重跑、未加总，也不将其当作 PG 证据，前述来件作者各自结果保持原归属。主线程已报告普通推送和 ls-remote 核验成功；此处独立确认的是本地精确对象及其源字节，而非另执行网络推送。

原生 8af 包的新冷启动、取消退出、会话草稿保存和确认退出由主线程继续记录，重启及其余可见验收按实际后续证据签收。本报告不替其完成 GUI、Windows、生产服务或完整 Goal 验收。

# V02-01C 设备持钥子链验收记录

日期：2026-09-09。实施者：device_key_implementation；CodexiMac负责整体集成与复跑。候选代码 `c3702c07cd334fd745905ddd7f4d7b697edb27c0`，基线 main `0a3ccf70efb569c39b3f91a558ab4b39140fd2f1`。独立任务审核已通过，整分支最终审核仍待完成；未合入main、尚无实际CodexWin接收。

## 本轮交付与边界

- 已实现后端设备owner、Ed25519公钥绑定、一次性持钥检查、双签名换钥、持久请求回执及三个真实HTTP路由；[协议](../contracts/V02_DEVICE_KEYS.md)给出准确字节/错误/时效。
- 会话撤销和凭据操作共用事务级session锁，随后锁设备/请求/凭据；锁等待后按数据库实时时钟重新核验，防止等锁期间失效仍提交。旧设备owner为NULL时不允许抢绑。
- 新106迁移与独立最小授权脚本；101～105没有改写。现有桌面、连接器和平台capability没有改变；原登记仍不是真实连接。
- 仍未完成01C连接版本、执行租约/领取/续租/取消及结果提交授权；也未完成02B候选上传、Windows私钥存储/往返、短信登录、真实平台、生产及客户UAT。持钥成功回执不是可重复使用的执行授权。

## 可复核结果

环境：本机macOS，Python3.12.13、PyNaCl1.6.2、Node24.19.0；专用本地PostgreSQL测试库与非超级用户应用角色。所有用户、设备、密钥和挑战均为合成测试数据；不代表真实客户/平台身份。

| 验证 | 结果与版本边界 |
|---|---|
| 改动前身份/会话基线 | 57 passed in11.64s，exit0 |
| 实现者最终定向 | 新设备文件＋既有身份/会话7文件，123 passed in17.37s，0跳过，exit0 |
| CodexiMac独立完整后端 | 在c3702c0相同代码上，925 passed in56.74s，0跳过，exit0 |
| 编译/静态/秘密检查 | compileall app/pilot/connectors/tests、node --check static/app.js、secret_scan、diff --check均exit0 |
| 实际Node→Python字节探针 | Node生成临时Ed25519密钥，签原UTF8字节，PyNaCl严格公钥检查和验签成功；仅公开key/payload/signature通过管道，私钥未导出 |
| 非改动检查 | desktop/、connectors/、迁移101～105与基线完全一致；不借旧桌面测试数声称本轮已重跑 |

完整后端命令为 `uv run --frozen pytest -q --tb=short`；运行环境同时显式设置 `YIKE_PILOT_ADMIN_DATABASE_URL`、`YIKE_PILOT_DATABASE_URL`、`YIKE_IDENTITY_TEST_DATABASE_URL`、`YIKE_IDENTITY_TEST_APP_DATABASE_URL` 指向专用测试库。不把凭据值写入本记录；未设置测试数据库导致跳过时不能复述本次0跳过结论。

定向复现：

```sh
uv sync --frozen --extra dev
uv run --frozen pytest -q tests/test_device_keys.py tests/test_device_credentials_postgres.py tests/test_identity_contract.py tests/test_identity_postgres.py tests/test_session_auth.py tests/test_session_revocation_postgres.py tests/test_session_upgrade_postgres.py
```

## 反例与修复历史

1. 两新增模块不存在时测试收集失败，作为实现前RED记录；23项初步通过不代替后续完整验收。
2. 初选cryptography50.0.1仅验签不足以证明持钥：单位元公钥（首字节01其余0）和可无私钥构造的签名验证任意挑战成功，专门回归出现DID NOT RAISE。改为PyNaCl1.6.2的主子群/规范点检查再验签，同反例被拒绝。没有自行实现曲线或维护弱点黑名单；[PyNaCl签名接口](https://pynacl.readthedocs.io/en/latest/signing/)是所用库接口依据。
3. 请求行锁等待后，历史成功重放曾遗漏会话到期复查；真实PG等待反例失败后，补请求/凭据锁后的复查，再通过定向回归。不能将历史成功回填为从未发生缺陷。
4. 独立随机测试库从101～105升级106两次、授权两次，真实注册/BIND成功；角色没有用户UPDATE、表DELETE或schema CREATE。用真实Lock wait_event证明退出/设备撤销与提交的双向竞争、同/不同请求绑定/换钥竞争及等锁期间到期；没有用单纯sleep代替锁证据。测试仅清理自己创建的确切临时数据库/角色。

整秒expiry采用数据库当前秒向下取整后+120，因此真实有效时间可比120秒短不到1秒；有效格式但签名错误会消耗挑战，格式错误在DTO层拒绝、不消费挑战。HTTP回执可用于同用户新会话查历史，不能让新会话完成旧会话的待处理挑战。

## 独立审核

device_authorization_architecture 对精确c3702c0及完整任务brief/report/diff作只读审核：Spec Compliance通过、Task Quality通过，Critical/Important/Minor均无具体问题。检查了严格公钥点校验、双钥轮换/回执、session→device锁序、owner、复合FK/FORCE RLS与最小授权；另外只查继承的Origin/no-store与共享会话调用点。审核者未重复PG测试，也未以提供的925项结果冒充自己实测。

整分支最终审核与main整合证据在完成后追加；Windows须记录自己的环境与ACK，不能复制上述Mac测试结果当作验收。[交接包](../handoffs/V02-01C_DEVICE_KEYS_MAC_TO_WIN.md)说明实际消费步骤及未完成边界。

## 后续Win限定接收与主线整合

原文“尚未main/Win未接收”为候选时点记录。CodexWin冻结复核 **65d867640ea216769adb5f947f5dea8fb7b31a35**（含c370及此前Win来源身份修复），实际Windows PG定向123 passed；完整962项为908 passed/54既有Windows失败/0跳过。新增的真实Node→loopback HTTP→受限PG证明签名字节、绑定/双签换钥/重放/拒绝可消费，不等于生产TLS或Windows私钥持久化。独立代码/架构/质量及合入复核通过后，正常集成 **f9255603435862d8e8ead60b0357851c8c9e3075**，对本后端子链限定ACK；01C执行授权剩余部分继续。两处契约文案勘误不改变代码行为，Win原始摘要、旧失败和验证工具修复见[Win复核第9节](WIN_CROSS_REVIEW_20260909.md)。不将本次不同集合相加或覆盖此前Mac925证据。

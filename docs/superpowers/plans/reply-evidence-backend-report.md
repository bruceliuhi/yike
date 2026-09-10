# 回复证据 revision 后端报告

基线：`7046171d70cf925d4892a9cd9f8994ac4e493804`

## 变更

- `evidence_row` 顶层返回数据库保存的 `revision`。
- signed record、语义去重返回与 `list_evidence` 查询都显式选择同一行的 `revision`。
- 未修改签名载荷、事件 payload、hash、migration 或 desktop 文件。

## 定向验证

- TDD RED：纯投影用例失败于缺失顶层 `revision`（`KeyError`）。
- TDD GREEN：纯投影用例 `1 passed`。
- 受影响 HTTP/PG 用例已断言首次记录 revision 1、同事件已读修订 revision 2、人工记录 revision 1，以及重复观察复用原输出。
- 当前环境未配置 fixture 链所需的 `YIKE_IDENTITY_TEST_DATABASE_URL` 与 `YIKE_IDENTITY_TEST_APP_DATABASE_URL`；定向 HTTP/PG 命令结果为 `4 skipped`，不得解释为真实 PostgreSQL 通过。

未运行全量测试，遵循本任务的节省 token 与定向验证要求。

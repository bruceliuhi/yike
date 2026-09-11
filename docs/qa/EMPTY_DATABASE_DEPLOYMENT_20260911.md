# 全新数据库部署检查（本机隔离环境）

代码：`d83a281321dd03a7d55c30c42d82ec2f673e72ed`；独立非实现者 `material_reference_architecture` 对 `aaab7c9..d83a281` 审核 GO，无 P1/P2。仅首次安装权限修复，不改变产品范围。

复用镜像 `yike-service-candidate:2d6b79b`，镜像摘要、源码与原始构建见[镜像记录](SERVICE_IMAGE_STARTUP_20260911.md)。本次没有重建镜像，新增 SQL 由受信发布端运行，不混入 Web 管理员配置。

## 实际检查与缺陷

- 新建独立 internal Docker 网络及 PostgreSQL 16 Alpine，数据仅在本次 tmpfs；未使用现有数据库、平台会话或客户数据，没有开放宿主数据库端口。
- 镜像内 `pilot.cli.migrate` 完成全新库迁移，返回 `{"status":"migrated"}`；实际迁移账本 31 条。
- 创建无 superuser/BYPASSRLS/CREATEDB/CREATEROLE 权限的应用角色，补 schema USAGE、用户只读和全部 21 个既有增量授权。
- 原镜像、原 CMD、非 root、只读根目录、禁提权、无 capabilities 启动；只提供应用数据库 URL 和本次合成认证配置，不提供管理员 URL。
- `/healthz`、`/readyz`、认证 `/api/ui/session` 都为 200，但 `/api/ui/profiles` 为 500。权限查询确认 `business_profiles` SELECT/INSERT 缺失；回归同样得到 `InsufficientPrivilege: permission denied for table business_profiles`。

**数据库可连不等于新部署可以使用业务功能。** `/readyz` 当前只检查 `SELECT 1`，不是迁移、权限、模型、平台或上线验收。

## 修复及验证

- 基础画像授权补用户 SELECT；画像和版本 SELECT/INSERT；仅画像 name 与版本 status/approved_at 可更新。任务权限仍归既有连接授权管理。
- 对可到达的高权限角色、对象所有者、schema CREATE、用户写入、不可变画像列 UPDATE 等拒绝执行，不自动删除管理员已有授权。
- `grant_runtime.sql` 在同一个管理员事务按顺序运行全部 22 个授权文件，出错退出；不创建角色或改密码。
- 实际 psql 执行完整入口成功并 COMMIT。失败时整批回滚由事务结构及独立审核核对，不冒充已运行的 psql 故障注入。
- 镜像真实 HTTP 再验：health/ready/session、画像初始列表、保存、确认、保存后列表、另一租户空列表，均 200；不重启应用、不重建镜像。
- 最终真实 PG 定向回归 **2 tests / OK，0.396 秒**：保存/确认/重复授权/数据保留/跨租户读取与 ACL；预存不可变列 UPDATE 授权拒绝。按发布清单加载 SQL，并检查所有增量文件被唯一纳入。
- 首次修复的重复授权检查发现旧连接授权允许任务 UPDATE，因此去掉基础画像脚本对旧任务权限的重复管理后通过；未扩大画像 payload 修改权限。
- 实际查询：应用角色的 superuser/BYPASSRLS/CREATEDB/CREATEROLE 均 false；用户、画像、画像版本三表 RLS 与 FORCE RLS 均 true。

复现测试：在有服务依赖的运行环境执行 `python tests/test_empty_deployment_grants.py`，显式提供 `YIKE_EMPTY_DEPLOYMENT_TEST_DATABASE_URL`（仅隔离且已迁移的测试库）。本次在原服务镜像中通过只读挂载本版本 tests/deploy 执行。无配置时跳过不能计为通过。测试创建随机角色及合成租户/用户；角色退出清理，合成记录随一次性数据库销毁，不用于客户或共享验收库。

## 边界

检查结束已停止并自动移除本次 Web/PG 容器、移除本次 internal 网络；tmpfs 合成数据随容器销毁。原有三个数据库容器未操作，复用的服务镜像保留。

这是本机镜像＋真实 PostgreSQL 检查，不是生产服务器、HTTPS、短信登录、真实平台搜索/收发、Windows 或客户试用证据。旧页面、管理员导入及其他业务不由画像检查自动验收。正式上线仍需原 CP-06/M3 门禁。

正式执行顺序：独立数据库与受限角色 → 管理员迁移 → 同版本完整授权 → 仅应用配置启动 Web → HTTPS 与真实客户端业务验收。过宽的既有权限先由管理员核查，不用整库授权使检查变绿。

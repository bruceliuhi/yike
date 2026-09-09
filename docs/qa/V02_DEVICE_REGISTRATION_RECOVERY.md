# 设备登记恢复限定验收

日期：2026-09-10；基线`5b1d7dbe29cf45c2d029e511272d0c7875f62b70`。
合同/计划及116认领`930d991c3f9a91a3648ff18b21d87a6e90449f8a`已正常推送main和工作分支，live ls-remote核对main同SHA。这是实现分工和接口约定，不是代码交付证明。

## 本片所补用户动作

客户端先保存登记request_id，登记断线或超时后查原请求，找回原device_id；再查看本机当前身份，衔接已有BIND/PROVE。原回执不能被当作当前设备仍有效或已经连接平台。旧`POST /devices`保持兼容，新版不按标签/租户列表认领本机。

## 根代理已执行证据

- 改动前相关纯边界：`uv run --frozen pytest -q tests/test_device_keys.py tests/test_ui_api.py`，**58 passed/1.02s**（会话32610退出0）。
- 新真实HTTP/PG回归在实现前：`uv run --frozen pytest -q tests/test_device_registration_http_postgres.py`，**1 failed/0.70s**；有效认证POST `/api/ui/device-registrations` 预期201、实际404，原文为`{"detail":"Not Found"}`，作为缺失接口RED。
- 测试使用已有专用PostgreSQL，实际查询identity_app角色为非超级用户、无BYPASSRLS、无CREATEROLE。管理员连接只用于受控合成数据设置/清理；没有读取或保存用户真实设备密钥、平台会话、短信或私信。

## 实现后验收记录（提交`422f5ebddd71ae0c1f9d2bad92c9fa8f5c535ed9`）

- 实现者专项：纯登记/密钥 **38 passed**；登记受限PostgreSQL **7 passed**；既有设备密钥PostgreSQL **28 passed**。
- root独立HTTP＋登记PG回归：**29 passed/8.64s**。
- root受影响非PG回归（登记、密钥、UI、Web）：**100 passed/1.50s**。
- 最终独立审查：**PASS WITH MINOR**，0 Critical/Important；修复测试文件末尾空行后重新检查`git diff --check`通过。

以上工程测试使用合成租户/用户和受控故障注入；没有把缺少真实平台账号、Windows客户端或客户数据的部分计为通过。

## 当前边界

本片代码和迁移已完成并同步远端，但只证明可恢复登记的工程链。Win客户端消费、实际Windows运行、真实平台连接/执行、外部发送、生产配置与客户UAT仍未完成。本片不启capability，不代记后面几项通过。

最终需区分：真实HTTP/Ed25519/受限PG工程链、Win客户端消费、实际Windows运行、真实平台连接/执行、外部发送、生产配置与客户UAT。本片不启capability，不代记后面几项通过。

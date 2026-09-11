# 临时访问码登录 Implementation Plan

> **For agentic workers:** 使用 subagent-driven-development；后台由独立实现者开发，根任务负责客户端与集成，非作者最终审核。

**Goal:** 解除短信投递阻断，让受邀客户以专属临时码进入原有隔离工作台。

**Architecture:** 复用现有试用与会话，新增显式认证用途与受限访问码入口，不创建第二套账号体系。

**Tech Stack:** PostgreSQL、Python/FastAPI、Electron/TypeScript/React。

## Global Constraints

- 老SMS试用码不能单独登录；临时码高熵、只存HMAC摘要、错误尝试持久限流。
- 首次成功起72小时、再登不延期、停用和到期阻断现有会话；不绕过pilot_trial_allowed。
- 不把临时登录当手机号验证；显式记录用途与认证来源。既有失败trial只经后台显式改发。
- 凭据不入日志/URL/普通存储；仅安全cookie持久化。无真实短信发送、无新增收费/外联。
- 不修改其他在途代码、不部署生产；根任务统一提交/部署/单次构包。

## Task 1: 后台与服务端（独立实现者）

范围：pilot临时访问认证新模块、trial/ops/phone登录必要改动、auth token必要来源字段、runtime/web/ui_api接线、138迁移及db注册和受限grant、对应Python测试。不得修改desktop。

接口：`POST /api/ui/auth/access-session` body `{access_code: string}`，现有session视图及cookie。错误 `access_auth_failed`(401)、`auth_rate_limited`(429)、`capability_unavailable`(501)。后台正常界面显式签发/改发临时码；旧SMS路径保留。复用PHONE secret独立HMAC域，无需新供应商配置。

- [ ] RED：真实PG首次激活/并发再次登录不延期、旧trial码拒绝、错码持久限流、停用到期旧session无效、两租户隔离、未验证标记。
- [ ] 实现最小schema/store/API/ops链路，显式用途隔离、原子激活、受限RLS；无需手机号填写的客户登录。
- [ ] 定向运行新测试及原test_ops_trials/test_phone_api/phone_auth/auth/session受影响子集，报告具体命令/结果；不跑全套或真实SMS。
- [ ] 写 /tmp/yike-temporary-access-backend-report.md，根任务统一commit，报告不包含任何凭据。

## Task 2: 桌面及整批验收（根任务）

文件：desktop/src/shared/contracts.ts、main/servicePolicy.ts、renderer/services/contracts.ts/client.ts、pages/Login.tsx、对应测试。

- [ ] RED：固定操作仅接受access_code、表单无需phone/OTP、成功刷新真实会话、错误/超时不误导航。
- [ ] 增加 `loginAccess(code)` 和固定IPC `session.loginAccess`，显式临时登录入口及敏感表单；沿用现有视觉组件、SMS入口和安全cookie。
- [ ] 定向前端测试/tsc；真实服务集成与非作者整批审核。用户要求节省测试，不重复全量suite。
- [ ] main推送并核对SHA；绑定版本部署与单次Mac构包，当前Window环境缺失如实记录。

## Evidence

2026-09-11 实现候选 `159cb48`（尚未部署）：

- 后端新测试在隔离 PostgreSQL 上 `tests/test_temporary_access.py`：12 passed；包含原子激活、重登不延期、旧码拒绝、撤销竞态和租户隔离。根任务使用 `YIKE_OPS_TEST_DATABASE_URL` 复验 12 passed；未提供此变量的两次运行均为 skipped，不计成功。
- 后端一次受影响回归为 107 passed / 7 failed。7 项为原 revocation fixture 期待 UPDATE/DELETE 返回零行，而现有生产最小授权先拒绝语句的已知差异；没有为测试扩大权限，不能写成全绿。
- 桌面五份定向测试 164 passed，类型检查通过；最终文案调整后两份登录测试 36 passed。普通重启的认证持久化使用操作系统加密会话缓存，不保存访问码。
- 实际浏览器 1280×720 临时码表单可见，无手机号/OTP字段；此项没有执行网络登录，不等于真实客户验收。
- 非作者 `platform_query_full_review` 对 `33a2b53..159cb48061edafa436d3e282705a4dcec5fc6218` 整批只读审核为 GO，无阻塞 P1/P2；核对用途/隔离/期限/固定 IPC/加密缓存和迁移授权。main 推送、生产迁移/升级和新包验收仍待完成，代码 GO 不代替实际包重启或客户验收。
- 用户确认暂无 Windows 环境；Windows 安装、运行及会话恢复仍未验收，不以 Mac 结果代替。

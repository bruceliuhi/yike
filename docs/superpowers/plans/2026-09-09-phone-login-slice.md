# 已开通客户手机号登录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已批准 P01 的手机号验证码入口接到可验证的认证服务，不再要求已开通客户手动交换 CLI token。

**Architecture:** 复用既有客户空间与会话；受信管理员绑定手机号 HMAC 到既有用户，运行时仅通过受限 PostgreSQL 角色访问认证状态。验证码预留、发送确认和一次性消费用短事务，供应商调用在事务外；未验收的短信供应商不接入正式启动入口。

**Tech Stack:** Python/FastAPI/psycopg/PostgreSQL；既有 Electron 白名单和 TypeScript 服务适配器，不增加依赖。

## Global Constraints

- 复用已批准 P01 手机号＋验证码＋可选试用码，不改密码登录，不新建视觉设计。
- 本切片只登录已预开通且已绑定手机号的既有用户，不自动注册、收费或分配试用权益。非空试用码明确不可用，不静默忽略。
- 原手机号、验证码、供应商凭据不进入业务数据库、日志、Git 或响应；认证表只存独立认证密钥 HMAC、时间和受限状态。
- HTTP 运行时禁止管理员连接；不扩大 pilot_users 的 SELECT，不改变 101–107，108 预留 Win，本切片登记 109。
- 供应商调用在事务外；未知结果不自动重发；冷却与失败尝试不因异常回滚。并发最多消费一次。
- 未验收短信供应商时生产启动仍 sms_login=false，不靠一个环境变量宣称可用；测试替身不是短信收码或上线证据。
- Mac 只改本计划路径；Win 的04A/B及05B/C不重写；共享入口由Mac串行接入。

## 已批准需求与实现边界

来源：AUTHORITY、任务书01D、`docs/handoffs/V02-01_MAC_TO_WIN.md`和R3 P01契约。独立只读架构预检 `phone_auth_preflight` 已确认：现有用户只能受信预开通；手机号映射是必要认证工程，匿名注册/试用权益不能从现有表推导。

选择“预开通用户＋独立认证服务”而非扩大业务库权限或接入未选定供应商。这样可完成真实数据库与HTTP链路，并把供应商集成作为明确的后续外部条件。当前不改变账号商业模式。

### Task 1: 持久手机号认证核心

**Files:** Create `pilot/phone_auth.py`, `migrations/109_v02_phone_login.sql`, `deploy/grant_phone_login.sql`, `tests/test_phone_auth.py`, `tests/test_phone_auth_postgres.py`; Modify `pilot/db.py` migration registry only.

**Interfaces:**

```python
class PhoneAuthError(ValueError):
    code: str  # invalid_phone, invalid_code, auth_rate_limited, phone_auth_failed

class PhoneAuthStore:
    def __init__(self, database, secret: bytes): ...  # >=32 bytes, repr-safe
    def bind_user(self, phone: str, user_id: str) -> None: ...  # admin-only, no HTTP
    def reserve(self, phone: str, peer: str): ...  # reservation: challenge_id, code, eligible
    def settle(self, phone: str, challenge_id: str, state: str) -> None: ...
    def consume(self, phone: str, code: str) -> str: ...  # server-resolved user_id
```

独立 HMAC 域为 phone、peer、otp（otp绑定phone指纹、challenge和login用途）；国内手机号ASCII `1[0-9]{10}`，OTP为6位ASCII数字；入参严格有界。使用随机6位码和随机challenge UUID，常量时间比对。绑定表由管理员写，应用仅按指纹或当前用户读；challenge与rate表FORCE RLS，按请求认证上下文匹配，不给无上下文全表访问。绑定同一号码到另一用户拒绝；同一用户不隐式增加多个号码或改绑。

冷却60秒、OTP有效300秒、每challenge最多5次失败、phone每小时3次、peer每小时10次、全服务每小时100次，作为当前工程硬上限而非售价/承诺。数据库时钟为准。所有预留在固定命名空间10901短事务锁下检查再提交；全局配额与phone/peer限额都持久化。未知号码也走相同限额与固定响应流程，但不调用供应商；不得通过状态响应列出已注册号码。发送状态PENDING/ACCEPTED/REJECTED/UNKNOWN，只有当前未过期ACCEPTED码可消费；失败计数先提交再返回通用认证错误。重发替换旧challenge，旧发送确认不能覆盖新challenge。

- [ ] 写测试并确认RED：严格输入/密钥、摘要无敏感值、迁移幂等与最小角色、无上下文读取为空、应用不能绑定、号码不能串用户、冷却/配额持久化、5次失败持久化、超时/旧回执、两线程仅一次消费。使用合成号码，真实隔离PG。
- [ ] 最小实现并跑GREEN：`uv run --frozen pytest -q tests/test_phone_auth.py tests/test_phone_auth_postgres.py`；数据库未配置的skip不能称已验证。
- [ ] 提交并交独立审核，报告RED/GREEN及环境，不能写已支持真实短信。

### Task 2: P01 HTTP与桌面服务接入

**Files:** Create `pilot/phone_api.py`, `tests/test_phone_api.py`; Modify `pilot/ui_api.py`, `pilot/web.py`, `desktop/src/shared/contracts.ts`, `desktop/src/main/servicePolicy.ts`, `desktop/src/renderer/services/client.ts`; add relevant targeted tests. No page-layout edits.

**Interfaces:** `register_phone_api(router, auth_store, sender, auth_secret, require_https)`；sender为内部适配器，仅提供 `send_code(phone, code)->bool`（明确供应商接收true、明确拒绝false；异常为UNKNOWN），不从HTTP提交URL/模板/密钥。`build_app(..., phone_auth=None, sms_sender=None)`只有受控依赖注入同时完整时注册测试/集成链路；正式CLI不传入，capability仍false。

```text
POST /api/ui/auth/sms-code {phone} -> {retry_after:60}
POST /api/ui/auth/sms-session {phone,code,trial_code?} -> {authenticated:true,user_id}
```

验证码请求成功响应只表示流程受理，不声称送达；未知号码走相同响应且不发送。provider错误落UNKNOWN、不重试、不返回原始异常。成功登录由服务端映射身份、再次确认既有用户有效，签发已有短期HttpOnly/Secure/SameSite=strict cookie，不向renderer返回token；原退出/撤销复用。无供应商两端返回501，错误/到期码401；非空试用码501。请求额外user/tenant字段422；HTTPS及Origin防护不变。桌面只新增固定操作 `session.requestCode`、`session.loginPhone`，禁止任意URL和参数；严格校验响应retry_after及登录身份，失败不假成功。

- [ ] 写RED：默认关闭；HTTPS/Origin/严格body；请求→供应商调用→真实PG消费→session读取→退出拒绝旧cookie；错误码、未知号码、超时不重发、试用码不可用；客户端映射与恶意字段拒绝。
- [ ] 实现后运行目标Python/desktop服务策略和登录相关测试、typecheck/build，按影响补会话回归。测试短信替身仅验证代码调用，不作为供应商实测。
- [ ] 更新01D交接与唯一任务书，列清真实供应商、签名/模板、凭据、手机收码、激活/到期和Windows ACK缺口；独立整体审核后正常整合main，不升级整卡DONE。

# Temporary invited login implementation plan

状态更新：用户后续提供已通过阿里云模板 SMS_512095645 与签名；本计划暂停，尚未写入生产代码。改为正式SMS适配器，不启动迁移138或后四位入口。下面清单仅保留设计历史。

> **For agentic workers:** Use superpowers:subagent-driven-development. Root alone stages/commits/pushes. User asks targeted validation and one whole-batch independent review, not repeated builds.

**Goal:** 短信尚未申请完成时，受邀新体验客户可从正式客户端登录并进入原业务工作台。

**Architecture:** 新邀请秘密独立认证，后四位只校对号码；预开通/租户/体验期限/会话复用运营模块。普通 SMS 路径不降级。基于精确已提交的迁移136基础增量，不改另一工作区未提交代码。

**Tech Stack:** Python/FastAPI/Pydantic/PostgreSQL；TypeScript/Zod/React，沿用当前页面样式和 Electron 固定 IPC。

## Global constraints

- Spec: `docs/superpowers/specs/2026-09-11-temporary-invited-login-design.md`，包含独立红队五项约束。
- 仅新 trial，独立随机192bit邀请秘密，摘要域 `invited-login-v1`；建议展示前缀 `YKI-`，与 `YK-` 权益码区分。没有邀请秘密时绝不只凭号码/后四位登录。
- 请求严格 `{phone: /^1[0-9]{10}$/, last_four: /^[0-9]{4}$/, invitation_code: /^YKI-[A-Za-z0-9_-]{32}$/}`，后四位等于phone.slice(-4)。不接受 user/tenant 身份参数。
- 独立 `/auth/invited-capability` 与 `/auth/invited-session`；默认能力关闭，无短信供应商也不修改 `sms_login`。只有显式启用且未过部署截止时可接受临时入口。真实服务器开关与部署必须单独记录。
- 有界失败持久限流，不在失败抛异常时回滚；未知号码同样占用额度。凭证、手机号不出日志/响应。Cookie与原正式会话一致。
- 撤销邀请=停用整个trial，旧会话下一次验证拒绝；不开激活后重发/复活。新会话TTL≤min(3600,邀请有效期,权益期限,部署截止剩余秒数)。

### Task 1: 受邀认证与客户端闭环

**Files:** 新增 `desktop/src/shared/invitedLogin.ts`、`desktop/src/renderer/pages/login/InvitedLoginForm.tsx`、`desktop/tests/ui/invited-login.test.tsx`；新增 `pilot/invited_login.py`、`pilot/invited_login_api.py`、`migrations/138_v02_invited_login.sql`、`deploy/grant_invited_login.sql`、`tests/test_invited_login.py`、`tests/test_invited_login_postgres.py`。运营精确候选集成后才修改其认证/运营文件：`pilot/ops_store.py`、`pilot/ops_web.py`、`pilot/ops_views.py`、`pilot/runtime.py`、`pilot/ui_api.py`、`pilot/web.py`、`pilot/db.py`、`desktop/src/renderer/pages/Login.tsx`、`desktop/src/renderer/services/{contracts,client}.ts`、`desktop/src/{shared/contracts,main/servicePolicy}.ts` 及对应测试。

**Interfaces:**

```ts
type InvitedLoginInput = {phone:string; last_four:string; invitation_code:string};
// Zod strict request schema. Public capability contains only available:boolean.
// Parent retains existing performLogin and real refreshSession validation.
type InvitedLoginFormProps = {
  busy:boolean; error:string;
  submit:(input:InvitedLoginInput)=>Promise<void>;
};
```

```python
# Service resolves user only from a verified invitation; no normal session token is an invitation.
@dataclass(frozen=True)
class InvitedLoginGrant:
    user_id: str
    ttl_seconds: int

# consume(phone,last_four,invitation_code,peer) -> InvitedLoginGrant
# It uses current DB time after acquiring row locks and commits failed-attempt budgets before raising.
```

- [ ] 写共享请求与独立表单 RED：正确输入提交一次；仅后四位、错配号码、Unicode数字、缺秘密、额外身份字段拒绝；秘密password/no autocomplete、不写storage、无获取短信按钮，繁忙不可提交。实现绿色后保留组件，直到真实Login接线测试通过才称客户端入口完成。
- [ ] 集成运营136精确提交并独立复核其证据；不复制未提交文件。迁移138追加新邀请字段/认证来源与独立限流状态，不改136校验和。运营创建新trial同事务可签发邀请；历史正式/管理员/历史trial不能补发。
- [ ] 后端 RED：无邀请码、错号/错秘密/错四位、未开关/到期、非trial/撤销拒绝；首次激活成功、再次登录不续期、两个消费者不会延长权益、旧token撤销/过期后拒绝；失败计数持久；普通SMS不降级。用真实受限独立PG验证，不用合成store替代权限/事务验证。
- [ ] 最小服务实现：独立邀请摘要验证与事务激活，不调用OTP消费伪造身份；权限来源记录INVITED。有效结果提交后按边界TTL签正常Cookie，再由原session解析租户。API保持HTTPS/Origin/no-store、严格body和统一失败；临时能力截止后动态false。
- [ ] 接真实runtime/运营开关与部署说明；客户端新增固定IPC操作并严格解析能力/会话，只在独立能力available时显示“受邀体验登录”。用户主动切换，不因SMS错误自动选中；提交后走原performLogin→refreshSession→workbench，不另造成功跳转。
- [ ] 跑定向新增PG/认证回归、UI/IPC测试和tsc；一次整批非作者审核精确提交，问题修复只增量复测。更新任务书和本记录、串行推main；是否部署以真实服务器操作/版本及体验账号验收为准。

## Evidence

实施中。未启用线上入口，未取得真实体验账号验收。

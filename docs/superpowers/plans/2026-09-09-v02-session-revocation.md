# V02-01B 服务端会话撤销实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 实施已批准 V02-01 中“退出撤销”的可独立验收子项，使已退出凭据不能继续访问或重新登录。

**Architecture:** 保留服务端 HMAC 与现有登录入口；新增随机凭据标识及 PostgreSQL 撤销记录。JSON、HTML、开发桥接共用撤销检查，业务 Store 通过独立会话模块使用非超级用户应用连接。只有不可用于登录的摘要入库。

**Tech Stack:** Python/FastAPI、psycopg、PostgreSQL、现有 Electron HTTPS client。

## Global Constraints

- 沿用已批准的手机号验证码设计，不新增密码/社交登录。短信提供方接通与激活在独立子项验收，当前 sms_login 保持 false。
- 不改变 Origin/HTTPS 检查，不存原始 token、Cookie、验证码或服务端密钥。
- 仅当前请求携带的凭据被撤销；同时携带 Bearer 和 Cookie 时分别核验并在一个事务内撤销，不能误撤销同人其他会话。
- 旧签名 token 可过渡，但同样受撤销检查；无效/过期退出幂等，存储失败不能返回退出成功。
- 撤销提交完成后的新请求必须拒绝；此前已经鉴权的在途请求不保证取消。设备认证、worker 授权代次和真实平台会话不由该子项完成。

## Task 1: 凭据解析与撤销键

**Files:** `pilot/auth.py`、`tests/test_session_auth.py`。

**Interfaces:** 保留 `issue_token` / `verify_token`；增加 `verify_token_claims(token, secret, now=None)` 返回不可含原 token 的 `TokenClaims(user_id, expires_at, revocation_key)`。

- [x] 先运行并看到同秒签发不唯一的失败：
  ```python
  assert issue_token('user-1', 'test-secret', now=100) != issue_token('user-1', 'test-secret', now=100)
  ```
- [x] 增加随机 jti；核验字符串边界、整数到期时间、签名与畸形输入，保留兼容纯 `sub/exp` 的旧签名。
- [x] 撤销键为已验签的签名 payload SHA256，不按可变 padding 的整个凭据字符串计算；测试等效签名编码不能逃过撤销。
- [x] `uv run --frozen pytest -q tests/test_session_auth.py`，15 passed。

## Task 2: PostgreSQL 撤销及全部入口接入

**Files:** 新增 `migrations/105_v02_session_revocation.sql`、`pilot/sessions.py`；修改 `pilot/db.py`、`pilot/store.py`、`pilot/web.py`、`pilot/ui_api.py`；测试 `tests/test_identity_postgres.py`、现有 Web/UI 测试替身。

**Interfaces:** `PilotSessionRegistry.authenticate(claims) -> tenant_id`，`revoke(claims_list) -> None`；路由通过 `authenticate_session(store, token, secret)` 返回服务端身份。`revoke_session_tokens` 只提交核验后的 claims。

- [x] 真实隔离 PostgreSQL 先观察以下回放被错误接受：
  ```python
  client.delete('/api/ui/session', headers=headers)
  assert client.get('/api/ui/session', headers=headers).status_code == 401
  assert client.get('/profile', headers=headers).status_code == 401
  assert client.post('/api/ui/session', json={'token': token}).status_code == 401
  ```
- [x] 新增同租户/用户复合外键及双条件 RLS（tenant_id + user_id）。撤销记录 INSERT 幂等且不允许应用 UPDATE/DELETE policy；只存摘要、归属及到期/撤销时间。
- [x] 全部 HTTP 鉴权及交换入口执行相同检查；签名有效但未开通仍 403。退出数据库失败返回错误且不声明服务端已退出。
- [x] 验证重建服务、旧 token、两个租户、同秒新会话、重复退出、Bearer/Cookie 双凭据和数据库不可用。
- [x] 定向组合测试、secret scan、diff check；`120b938` 获独立复审 PASS，147 passed/2 skipped；最小权限升级测试及修复过程见 `docs/qa/V02-01B_REVIEW.md`。实际 CodexWin 交叉验证仍待完成。

## 完成判定

本子项可以通过，但整个 V02-01、短信登录、平台连接、Windows、生产及客户 UAT 仍分别待验收。不得将本地单测或合成身份测试写成真实客户登录证明。CodexWin 交叉验证未发生前保持未合并候选。

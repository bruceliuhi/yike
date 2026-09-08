from __future__ import annotations

from html import escape
from fastapi import Cookie, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
from pilot.auth import InvalidPilotToken, verify_token


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)}</title><body><nav><a href='/profile'>业务画像</a> · <a href='/opportunities'>今日机会</a> · <a href='/followups'>跟进反馈</a></nav><main>{body}</main></body></html>")


def build_app(store, *, auth_secret: str, dev_login: bool = False) -> FastAPI:
    app = FastAPI(title="意客 AI 客户试用")
    access_logger = logging.getLogger("yike.pilot.access")

    class RedactedAccessLogMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            access_logger.info("%s %s %s", request.method, request.url.path, response.status_code)
            return response

    app.add_middleware(RedactedAccessLogMiddleware)

    @app.get("/healthz")
    def healthz():
        return JSONResponse({"status": "ok"})

    @app.get("/readyz")
    def readyz():
        try:
            with store.database.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
        except Exception:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ready"})

    def user(authorization: str | None, session: str | None = None) -> str:
        token = authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else session
        if not token:
            raise HTTPException(status_code=401, detail="Bearer pilot token is required")
        try:
            return verify_token(token, auth_secret)
        except InvalidPilotToken as error:
            raise HTTPException(status_code=401, detail="invalid pilot token") from error

    @app.get("/", response_class=HTMLResponse)
    def home():
        return RedirectResponse("/profile", status_code=303)

    @app.get("/__dev/session")
    def dev_session(request: Request, token: str):
        if not dev_login or request.client is None or request.client.host not in ("127.0.0.1", "::1", "testclient"):
            raise HTTPException(status_code=404, detail="not found")
        try:
            verify_token(token, auth_secret)
        except InvalidPilotToken as error:
            raise HTTPException(status_code=401, detail="invalid pilot token") from error
        response = RedirectResponse("/profile", status_code=303)
        response.set_cookie("pilot_session", token, httponly=True, secure=request.url.scheme == "https", samesite="strict", max_age=3600)
        return response

    @app.get("/session", response_class=HTMLResponse)
    def session_form():
        return _page("登录意客 AI", "<h1>登录意客 AI</h1><p>请粘贴管理员通过安全渠道提供的短期访问令牌。</p><form method='post' action='/session'><input name='token' type='password' autocomplete='off' required placeholder='短期访问令牌'><button>继续</button></form>")

    @app.post("/session")
    def session_exchange(request: Request, token: str = Form(...)):
        # The app does not trust client-supplied forwarding headers. Configure the
        # reverse proxy/Uvicorn proxy-header boundary before exposing this route.
        scheme = request.url.scheme
        if not dev_login and scheme != "https":
            raise HTTPException(status_code=400, detail="session exchange requires HTTPS")
        try:
            verify_token(token, auth_secret)
        except InvalidPilotToken as error:
            raise HTTPException(status_code=401, detail="invalid pilot token") from error
        response = RedirectResponse("/profile", status_code=303)
        response.set_cookie("pilot_session", token, httponly=True, secure=scheme == "https", samesite="strict", max_age=3600)
        return response

    @app.get("/profile", response_class=HTMLResponse)
    def profile(authorization: str | None = Header(default=None), session: str | None = Cookie(default=None, alias="pilot_session")):
        user(authorization, session)
        return _page("业务画像", "<h1>描述你的业务</h1><p>例如：展台设计搭建、服务地域、项目偏好和排除项。</p><p>当前首个验证行业：展台搭建。</p><form method='post'><textarea name='payload' rows='5' placeholder='请输入服务、地域、客单价和不接的项目'></textarea><button>保存为待确认版本</button></form>")

    @app.post("/profile", response_class=HTMLResponse)
    def save_profile(payload: str = Form(...), authorization: str | None = Header(default=None), session: str | None = Cookie(default=None, alias="pilot_session")):
        user_id = user(authorization, session)
        result = store.save_profile(user_id, {"description": payload})
        return _page("画像待确认", f"<h1>画像版本 {result['version']} 已保存</h1><p>这是待确认版本，确认后才会用于导入机会。</p><form method='post' action='/profile/{result['version_id']}/confirm'><button>确认这个版本</button></form>")

    @app.post("/profile/{version_id}/confirm")
    def confirm_profile(version_id: str, authorization: str | None = Header(default=None), session: str | None = Cookie(default=None, alias="pilot_session")):
        user_id = user(authorization, session)
        store.confirm_profile(user_id, version_id)
        return RedirectResponse("/opportunities", status_code=303)

    @app.get("/opportunities", response_class=HTMLResponse)
    def opportunities(authorization: str | None = Header(default=None), session: str | None = Cookie(default=None, alias="pilot_session")):
        user_id = user(authorization, session)
        rows = store.list_opportunities(user_id)
        failed_tasks = store.list_failed_tasks(user_id)
        task_warning = "" if not failed_tasks else "<p><strong>后台研究任务失败：请人工检查任务后再导入新的复核研究包。</strong></p>"
        if not rows:
            return _page("今日机会", f"<h1>今日暂无经复核机会</h1>{task_warning}<p>后台研究完成并人工复核后，机会会出现在这里。</p>")
        items = "".join(
            f"<li><a href='/opportunities/{escape(str(r['opportunity_id']), quote=True)}'>{escape(str(r['title']))}</a>｜"
            f"{escape(str(r['buyer']))}｜意向 {escape(str(r['intent_status']))}｜来源 {escape(str(r.get('source_status') or 'UNVERIFIED'))}｜"
            f"更新时间 {escape(str(r.get('updated_at') or '未知'))}｜{escape(str(r.get('summary') or r.get('public_excerpt') or '暂无摘要'))}</li>"
            for r in rows
        )
        return _page("今日机会", f"<h1>今日值得联系</h1>{task_warning}<ul>{items}</ul>")

    @app.get("/followups", response_class=HTMLResponse)
    def followups(authorization: str | None = Header(default=None), session: str | None = Cookie(default=None, alias="pilot_session")):
        user_id = user(authorization, session)
        rows = store.list_all_followups(user_id)
        if not rows:
            return _page("跟进反馈", "<h1>跟进反馈</h1><p>还没有记录。联系后在机会详情页登记真实结果。</p>")
        items = "".join(
            f"<li><a href='/opportunities/{escape(str(row['opportunity_id']), quote=True)}'>{escape(str(row['title']))}</a>｜"
            f"{escape(str(row['status']))}｜{escape(str(row['note']))}</li>"
            for row in rows
        )
        return _page("跟进反馈", f"<h1>跟进反馈</h1><ul>{items}</ul>")

    @app.get("/opportunities/{opportunity_id}", response_class=HTMLResponse)
    def opportunity(opportunity_id: str, authorization: str | None = Header(default=None), session: str | None = Cookie(default=None, alias="pilot_session")):
        user_id = user(authorization, session)
        row = store.get_opportunity(user_id, opportunity_id)
        opp_id = escape(str(opportunity_id), quote=True)
        followups = store.list_followups(user_id, opportunity_id)
        history = "".join(f"<li>{escape(str(item['status']))}：{escape(str(item['note']))}</li>" for item in followups)
        source_status = str(row["source_status"])
        warning = ""
        if source_status == "EXPIRED":
            warning = "<p><strong>来源已过期：先人工重新打开原文，确认仍在寻源后再联系。</strong></p>"
        elif source_status == "BLOCKED":
            warning = "<p><strong>来源暂时受阻：暂不建议联系，需人工处理访问问题。</strong></p>"
        elif source_status == "UNVERIFIED":
            warning = "<p><strong>来源尚未核验：先人工打开原文并确认需求仍有效，再联系。</strong></p>"
        source_url = str(row.get("public_url") or "")
        source_link = f"<a href='{escape(source_url, quote=True)}' rel='noreferrer'>打开原文</a>" if source_url else "原文链接缺失"
        published = escape(str(row.get("published_at") or "未知"))
        platform = escape(str(row.get("source_platform") or "未知"))
        excerpt = escape(str(row.get("public_excerpt") or "未提供公开摘录"))
        status_options = "".join(f"<option value='{value}'{' selected' if value == source_status else ''}>{value}</option>" for value in ("OPEN", "EXPIRED", "BLOCKED", "UNVERIFIED"))
        return _page(str(row["title"]), f"<h1>{escape(str(row['title']))}</h1><p>买方：{escape(str(row['buyer']))}</p><p>{escape(str(row['summary']))}</p><h2>原始证据</h2><p>平台：{platform}｜发布时间：{published}｜{source_link}</p><blockquote>{excerpt}</blockquote><p>联系入口：{escape(str(row['contact_path']))}</p>{warning}<form method='post' action='/opportunities/{opp_id}/source-status'><label>来源状态<select name='status'>{status_options}</select></label><button>保存来源状态</button></form><h2>公开评论草稿</h2><p>{escape(str(row['draft_comment']))}</p><h2>私信草稿</h2><p>{escape(str(row['draft_dm']))}</p><p><strong>仅供人工复制，不自动发送。</strong></p><h2>跟进记录</h2><ul>{history or '<li>暂无记录</li>'}</ul><form method='post' action='/opportunities/{opp_id}/followups'><label>状态<select name='status'><option value='CONTACTED'>已联系</option><option value='REPLIED'>已回复</option><option value='MEETING'>已约会议</option><option value='QUOTED'>已报价</option><option value='LOST'>已失单</option><option value='WON'>已成交</option></select></label><textarea name='note' required placeholder='记录真实发生的联系结果'></textarea><button>保存跟进</button></form>")

    @app.post("/opportunities/{opportunity_id}/source-status")
    def source_status(opportunity_id: str, status: str = Form(...), authorization: str | None = Header(default=None), session: str | None = Cookie(default=None, alias="pilot_session")):
        user_id = user(authorization, session)
        store.set_source_status(user_id, opportunity_id, status)
        return RedirectResponse(f"/opportunities/{opportunity_id}", status_code=303)

    @app.post("/opportunities/{opportunity_id}/followups")
    def followup(opportunity_id: str, status: str = Form(...), note: str = Form(...), authorization: str | None = Header(default=None), session: str | None = Cookie(default=None, alias="pilot_session")):
        user_id = user(authorization, session)
        store.record_followup(user_id, opportunity_id, status, note)
        return RedirectResponse(f"/opportunities/{opportunity_id}", status_code=303)

    return app

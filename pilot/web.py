from __future__ import annotations

from html import escape
from fastapi import Cookie, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pilot.auth import InvalidPilotToken, verify_token


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)}</title><body><nav><a href='/profile'>业务画像</a> · <a href='/opportunities'>今日机会</a></nav><main>{body}</main></body></html>")


def build_app(store, *, auth_secret: str, dev_login: bool = False) -> FastAPI:
    app = FastAPI(title="意客 AI 客户试用")

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
        response.set_cookie("pilot_session", token, httponly=True, samesite="strict", max_age=3600)
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
        if not rows:
            return _page("今日机会", "<h1>今日暂无经复核机会</h1><p>后台研究完成并人工复核后，机会会出现在这里。</p>")
        items = "".join(f"<li><a href='/opportunities/{escape(str(r['opportunity_id']), quote=True)}'>{escape(str(r['title']))}</a>｜{escape(str(r['buyer']))}｜{escape(str(r['intent_status']))}</li>" for r in rows)
        return _page("今日机会", f"<h1>今日值得联系</h1><ul>{items}</ul>")

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
        return _page(str(row["title"]), f"<h1>{escape(str(row['title']))}</h1><p>买方：{escape(str(row['buyer']))}</p><p>{escape(str(row['summary']))}</p><p>联系入口：{escape(str(row['contact_path']))}</p>{warning}<h2>公开评论草稿</h2><p>{escape(str(row['draft_comment']))}</p><h2>私信草稿</h2><p>{escape(str(row['draft_dm']))}</p><p><strong>仅供人工复制，不自动发送。</strong></p><h2>跟进记录</h2><ul>{history or '<li>暂无记录</li>'}</ul><form method='post' action='/opportunities/{opp_id}/followups'><label>状态<select name='status'><option value='CONTACTED'>已联系</option><option value='REPLIED'>已回复</option><option value='MEETING'>已约会议</option><option value='QUOTED'>已报价</option><option value='LOST'>已失单</option><option value='WON'>已成交</option></select></label><textarea name='note' required placeholder='记录真实发生的联系结果'></textarea><button>保存跟进</button></form>")

    @app.post("/opportunities/{opportunity_id}/followups")
    def followup(opportunity_id: str, status: str = Form(...), note: str = Form(...), authorization: str | None = Header(default=None), session: str | None = Cookie(default=None, alias="pilot_session")):
        user_id = user(authorization, session)
        store.record_followup(user_id, opportunity_id, status, note)
        return RedirectResponse(f"/opportunities/{opportunity_id}", status_code=303)

    return app

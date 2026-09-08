from __future__ import annotations

from fastapi import FastAPI, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pilot.auth import InvalidPilotToken, verify_token


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{title}</title><body><nav><a href='/profile'>业务画像</a> · <a href='/opportunities'>今日机会</a></nav><main>{body}</main></body></html>")


def build_app(store, *, auth_secret: str) -> FastAPI:
    app = FastAPI(title="意客 AI 客户试用")

    def user(authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Bearer pilot token is required")
        try:
            return verify_token(authorization[7:].strip(), auth_secret)
        except InvalidPilotToken as error:
            raise HTTPException(status_code=401, detail="invalid pilot token") from error

    @app.get("/", response_class=HTMLResponse)
    def home():
        return RedirectResponse("/profile", status_code=303)

    @app.get("/profile", response_class=HTMLResponse)
    def profile(authorization: str | None = Header(default=None)):
        user(authorization)
        return _page("业务画像", "<h1>描述你的业务</h1><p>例如：展台设计搭建、服务地域、项目偏好和排除项。</p><p>当前首个验证行业：展台搭建。</p><form method='post'><textarea name='payload' rows='5' placeholder='请输入服务、地域、客单价和不接的项目'></textarea><button>保存为待确认版本</button></form>")

    @app.post("/profile", response_class=HTMLResponse)
    def save_profile(payload: str = Form(...), authorization: str | None = Header(default=None)):
        user_id = user(authorization)
        result = store.save_profile(user_id, {"description": payload})
        return _page("画像待确认", f"<h1>画像版本 {result['version']} 已保存</h1><p>这是待确认版本，确认后才会用于导入机会。</p><form method='post' action='/profile/{result['version_id']}/confirm'><button>确认这个版本</button></form>")

    @app.post("/profile/{version_id}/confirm")
    def confirm_profile(version_id: str, authorization: str | None = Header(default=None)):
        user_id = user(authorization)
        store.confirm_profile(user_id, version_id)
        return RedirectResponse("/opportunities", status_code=303)

    @app.get("/opportunities", response_class=HTMLResponse)
    def opportunities(authorization: str | None = Header(default=None)):
        user_id = user(authorization)
        rows = store.list_opportunities(user_id)
        if not rows:
            return _page("今日机会", "<h1>今日暂无经复核机会</h1><p>后台研究完成并人工复核后，机会会出现在这里。</p>")
        items = "".join(f"<li><a href='/opportunities/{r['opportunity_id']}'>{r['title']}</a>｜{r['buyer']}｜{r['intent_status']}</li>" for r in rows)
        return _page("今日机会", f"<h1>今日值得联系</h1><ul>{items}</ul>")

    @app.get("/opportunities/{opportunity_id}", response_class=HTMLResponse)
    def opportunity(opportunity_id: str, authorization: str | None = Header(default=None)):
        user_id = user(authorization)
        row = store.get_opportunity(user_id, opportunity_id)
        return _page(row["title"], f"<h1>{row['title']}</h1><p>买方：{row['buyer']}</p><p>{row['summary']}</p><p>联系入口：{row['contact_path']}</p><h2>公开评论草稿</h2><p>{row['draft_comment']}</p><h2>私信草稿</h2><p>{row['draft_dm']}</p><p><strong>仅供人工复制，不自动发送。</strong></p><form method='post' action='/opportunities/{opportunity_id}/followups'><input type='hidden' name='status' value='CONTACTED'><textarea name='note' required placeholder='记录你实际的联系结果'></textarea><button>记录已人工联系</button></form>")

    @app.post("/opportunities/{opportunity_id}/followups")
    def followup(opportunity_id: str, status: str = Form(...), note: str = Form(...), authorization: str | None = Header(default=None)):
        user_id = user(authorization)
        store.record_followup(user_id, opportunity_id, status, note)
        return RedirectResponse(f"/opportunities/{opportunity_id}", status_code=303)

    return app

"""Small server-rendered operator workspace; no external assets or scripts."""
from datetime import timezone, timedelta
from html import escape

from fastapi.responses import HTMLResponse


CSS = '''
:root{font-family:system-ui,-apple-system,"PingFang SC",sans-serif;color:#19283b;background:#f5f7fb;font-size:15px}
*{box-sizing:border-box}body{margin:0}header{height:76px;background:white;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:48px;padding:0 5vw}
header strong{font-size:23px;color:#1761ca}nav{display:flex;gap:28px}a{color:#1761ca;text-decoration:none}a:hover{text-decoration:underline}
main{max-width:1240px;margin:44px auto;padding:0 28px}h1{font-size:28px;margin:0 0 12px}h2{font-size:20px}p{line-height:1.7}.muted,small{color:#617187}
.logout{margin-left:auto}button,.button{border:0;background:#1761ca;color:white;padding:11px 20px;border-radius:6px;cursor:pointer;font:inherit;display:inline-block}
button:hover,.button:hover{background:#104eaa}button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid #8bb9fc;outline-offset:3px}
.secondary{background:#eaf0f8;color:#254465}.danger{background:#a82727}label{display:block;margin:22px 0 8px;font-weight:600}input{display:block;font:inherit;padding:12px;border:1px solid #bac7d8;border-radius:5px;width:100%;background:white}
.form{max-width:460px}form p{margin-top:24px}.notice{padding:16px 0;border-bottom:2px solid #1761ca}.error{color:#a82727}.code{font:20px ui-monospace,monospace;overflow-wrap:anywhere;padding:20px;background:#eaf0f8;user-select:all}
.table-wrap{overflow-x:auto;background:white;margin:28px 0}table{border-collapse:collapse;width:100%;min-width:880px;text-align:left}th,td{padding:17px 16px;border-bottom:1px solid #e6ecf3}th{font-size:13px;color:#617187;background:#f9fbfe}td small{display:block;margin-top:7px}.actions{display:flex;gap:20px;align-items:center}.empty{padding:32px;color:#617187}
.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:28px 0}.stat{background:white;border:1px solid #e2e8f0;border-radius:8px;padding:20px}.stat strong{display:block;font-size:30px;line-height:1.2;color:#1761ca}.stat span{display:block;color:#617187;margin-top:8px}.stat-muted strong{color:#617187}.stat-warn strong{color:#a82727}
@media(max-width:680px){header{height:auto;padding:20px;gap:20px;flex-wrap:wrap}nav{gap:20px}main{margin:28px auto;padding:0 20px}h1{font-size:24px}.logout{margin-left:0}}
'''


def hidden(csrf: str) -> str:
    return f'<input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">'


def page(title: str, body: str, csrf: str | None = None, status=200):
    nav = '' if csrf is None else (
        '<nav><a href="/ops">运营概览</a><a href="/ops/users">客户与试用</a><a href="/ops/trials">生成试用码</a></nav>'
        f'<form class="logout" method="post" action="/ops/logout">{hidden(csrf)}<button class="secondary">退出登录</button></form>'
    )
    return HTMLResponse(
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(title)} · 意客AI</title><link rel="stylesheet" href="/ops/style.css">'
        f'</head><body><header><strong>意客AI · 运营</strong>{nav}</header><main>{body}</main></body></html>',
        status_code=status,
    )


def date(value):
    return value.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M') if value else '—'


def overview_view(summary, csrf):
    """Render the operator landing page from server-derived counts only."""
    labels = (
        ('total', '客户总数', ''),
        ('pending', '待激活试用', ''),
        ('active', '试用中', ''),
        ('expired', '已到期', 'stat-warn'),
        ('revoked', '已停用', 'stat-warn'),
        ('no_trial', '未登记试用', 'stat-muted'),
    )
    cards = ''.join(
        f'<div class="stat {escape(tone)}"><strong>{int(summary.get(key, 0))}</strong>'
        f'<span>{escape(label)}</span></div>'
        for key, label, tone in labels
    )
    body = '<h1>运营概览</h1><p class="muted">数据来自运营数据库当前快照；手机号、试用码和客户业务数据不会出现在概览中。</p>'
    body += f'<div class="stats">{cards}</div>'
    body += '<div class="actions"><a class="button" href="/ops/trials">登记客户并生成试用码</a><a href="/ops/users">查看客户与试用</a></div>'
    return page('运营概览', body, csrf)


def users_view(rows, offset, csrf):
    content=[]
    for row in rows:
        action = f'<a href="/ops/revoke?trial_id={escape(row["trial_id"])}">停用</a>' if row['trial_id'] and row['state'] != '已停用' else '—'
        if row['trial_id'] and not row['activated_at'] and row['state'] != '已停用' and row.get('credential_kind') != 'TEMPORARY_ACCESS':
            action += f' · <a href="/ops/reissue?trial_id={escape(row["trial_id"])}">重发码</a>'
        phone = escape(row['phone']) if row['phone'] else '未留存可还原手机号'
        verified = '已短信验证' if row.get('phone_verified_at') else '未短信验证'
        if row.get('credential_kind') == 'TEMPORARY_ACCESS':
            verified += ' · 历史临时访问（已停用）'
        content.append(f'<tr><td>{escape(row["name"])}<small>{escape(row["user_id"])}</small></td>'
                       f'<td>{phone}<small>{verified}</small></td><td>{escape(row["state"])}</td>'
                       f'<td>{date(row["activated_at"])}</td><td>{date(row["expires_at"])}</td><td>{action}</td></tr>')
    body = '<h1>客户与试用</h1><p class="muted">完整手机号仅管理员可见。试用从首次短信验证并激活后计时；时间为北京时间。</p>'
    body += '<a class="button" href="/ops/trials">登记客户并生成试用码</a>'
    body += '<div class="table-wrap"><table><thead><tr><th>客户</th><th>手机号</th><th>状态</th><th>激活时间</th><th>到期时间</th><th>操作</th></tr></thead><tbody>'
    body += ''.join(content) or '<tr><td colspan="6" class="empty">暂无客户，先登记一位试用客户。</td></tr>'
    body += '</tbody></table></div><div class="actions">'
    if offset:
        body += f'<a href="/ops/users?offset={max(0,offset-50)}">上一页</a>'
    if len(rows) == 50:
        body += f'<a href="/ops/users?offset={offset+50}">下一页</a>'
    return page('客户与试用', body+'</div>', csrf)


def issue_view(csrf, error=None):
    body = '<h1>生成试用码</h1><p class="muted">先登记客户，再通过微信等渠道私下发放 8 位试用码；客户登录时必须同时填写手机号和短信验证码。</p>'
    if error:
        body += f'<p role="alert" class="error">{escape(error)}</p>'
    body += f'<form class="form" method="post" action="/ops/trials">{hidden(csrf)}'
    body += '<label for="name">客户名称</label><input id="name" name="name" maxlength="100" required autocomplete="organization">'
    body += '<label for="phone">客户手机号</label><input id="phone" name="phone" type="tel" pattern="1[0-9]{10}" maxlength="11" required autocomplete="off">'
    body += '<label for="days">激活后试用天数</label><input id="days" name="days" type="number" value="3" min="1" max="30" required>'
    body += '<p class="muted">默认 3 天（72 小时）。未激活的码 30 天后过期；同一手机号不能重复登记。</p><button>生成专属试用码</button></form>'
    return page('生成试用码', body, csrf, 400 if error else 200)

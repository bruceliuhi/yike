"""Separate operator HTTP app. Never mount in the customer runtime."""
from collections import deque
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from html import escape
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse, RedirectResponse

from pilot.ops_store import OpsError, OpsStore
from pilot.ops_views import CSS, hidden, issue_view, page, users_view


def build_ops_app(store: OpsStore, *, password: str, origin: str) -> FastAPI:
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment
            or not isinstance(password,str) or not 16 <= len(password) <= 256):
        raise OpsError('invalid_ops_configuration')
    salt = secrets.token_bytes(16)
    expected = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    hits, lock = deque(), threading.Lock()

    @app.middleware('http')
    async def security(request, call_next):
        content_length = request.headers.get('content-length','0')
        if str(request.base_url).rstrip('/') != origin or request.url.scheme != 'https':
            response = PlainTextResponse('HTTPS 运营入口不匹配', 400)
        elif request.method not in {'GET','HEAD'} and request.headers.get('origin') != origin:
            response = PlainTextResponse('请求来源不匹配', 403)
        elif not re.fullmatch(r'[0-9]{1,9}',content_length):
            response = PlainTextResponse('请求长度无效',400)
        elif request.method == 'POST' and 'content-length' not in request.headers:
            response = PlainTextResponse('请求必须声明长度',411)
        elif int(content_length) > 8192:
            response = PlainTextResponse('请求过大', 413)
        else:
            try:
                response = await call_next(request)
            except Exception:
                # Do not emit DB parameters, form bodies or decrypted phone data.
                response = PlainTextResponse('运营服务暂不可用，请稍后重试。', 503)
        response.headers.update({
            # no-referrer makes browser form POST Origin null, defeating our
            # strict same-origin check. Do not leak referrers to other sites.
            'cache-control':'no-store', 'referrer-policy':'same-origin',
            'x-content-type-options':'nosniff', 'x-frame-options':'DENY',
            'content-security-policy':"default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        })
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return PlainTextResponse('请检查输入格式。', 400)

    def identity(request):
        token = request.cookies.get('yike_ops_session')
        if not store.session_valid(token):
            raise HTTPException(303, headers={'Location':'/ops/login'})
        return token

    def csrf_for(token):
        return hmac.new(token.encode(), b'yike-ops-csrf-v1', hashlib.sha256).hexdigest()

    def authorize(request, csrf):
        token = identity(request)
        if not csrf or not hmac.compare_digest(csrf_for(token),csrf):
            raise HTTPException(403, detail='操作校验失效，请刷新页面。')
        return token

    @app.get('/ops/style.css')
    def css():
        return PlainTextResponse(CSS, media_type='text/css')

    @app.get('/ops')
    def home():
        return RedirectResponse('/ops/users',303)

    @app.get('/ops/login')
    def login_page():
        return page('管理员登录', '<h1>管理员登录</h1><p class="muted">仅限授权运营人员。</p><form class="form" method="post" action="/ops/login"><label for="password">管理员密码</label><input id="password" name="password" type="password" maxlength="256" required autocomplete="current-password"><p><button>登录后台</button></p></form>')

    @app.post('/ops/login')
    def login(password: str = Form(..., max_length=256)):
        with lock:
            now = time.monotonic()
            while hits and hits[0] < now-300:
                hits.popleft()
            if len(hits) >= 10:
                raise HTTPException(429, detail='尝试过于频繁，请五分钟后再试。')
            hits.append(now)
        actual = hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1)
        if not hmac.compare_digest(expected,actual):
            return page('登录失败','<h1>登录失败</h1><p role="alert">管理员密码不正确。</p><a href="/ops/login">重新登录</a>',status=401)
        token = store.new_session()
        response = RedirectResponse('/ops/users',303)
        response.set_cookie('yike_ops_session',token,max_age=7200,httponly=True,secure=True,samesite='strict',path='/ops')
        return response

    @app.post('/ops/logout')
    def logout(request: Request, csrf: str = Form('')):
        store.logout(authorize(request,csrf))
        response = RedirectResponse('/ops/login',303)
        response.delete_cookie('yike_ops_session',path='/ops',secure=True,httponly=True,samesite='strict')
        return response

    @app.get('/ops/users')
    def users(request: Request, offset: int = 0):
        token = identity(request)
        return users_view(store.users(offset=offset),offset,csrf_for(token))

    @app.get('/ops/trials')
    def trials(request: Request):
        return issue_view(csrf_for(identity(request)))

    @app.post('/ops/trials')
    def issue(request: Request, phone: str = Form(...,max_length=11), name: str = Form(...,max_length=100),
              days: int = Form(3), csrf: str = Form('')):
        token = authorize(request,csrf)
        try:
            result = store.issue(phone,name,days)
        except OpsError as error:
            messages = {'phone_already_registered':'此手机号已登记，请在客户列表查看，不能重复签发。',
                        'invalid_phone':'请输入正确的 11 位手机号。','invalid_trial_days':'试用期须为 1–30 天。',
                        'invalid_customer_name':'请输入不超过 100 字的客户名称。'}
            return issue_view(csrf_for(token),messages.get(str(error),'生成结果未确认，请先检查客户列表，勿重复登记。'))
        body = f'<h1>试用码已生成</h1><p>请通过微信等渠道私下发给客户；本页仅展示一次。</p><p class="code">{escape(result["code"])}</p>'
        body += f'<p>客户手机号：{escape(phone)}。首次短信验证并激活后，可试用 {result["days"]} 天。</p>'
        body += '<p class="muted">客户打开登录页，填写手机号和短信验证码，再展开“试用开通”输入此码。后续登录无需再次填码。</p><a class="button" href="/ops/users">查看客户列表</a>'
        return page('试用码已生成',body,csrf_for(token))

    @app.get('/ops/revoke')
    def confirm_revoke(request: Request, trial_id: str):
        token = identity(request)
        return page('确认停用','<h1>确认停用试用？</h1><p>停用后，该客户已有登录会话也将失效；此操作不删除客户数据。</p>'
                    f'<form method="post" action="/ops/revoke">{hidden(csrf_for(token))}<input type="hidden" name="trial_id" value="{escape(trial_id,quote=True)}"><button class="danger">确认停用</button> <a href="/ops/users">取消</a></form>',csrf_for(token))

    @app.get('/ops/access')
    def confirm_access(request: Request, trial_id: str):
        token = identity(request)
        return page('签发临时登录访问码','<h1>签发临时登录访问码？</h1><p>客户只输入此码登录，无需短信。首次登录起固定72小时，后续登录或改发不延期。</p>'
                    '<p>这不是手机号验证。需人工私下分发；原短信试用码或原临时码立即失效，不创建新客户。已激活的短信试用不能转换。</p>'
                    f'<form method="post" action="/ops/access">{hidden(csrf_for(token))}<input type="hidden" name="trial_id" value="{escape(trial_id,quote=True)}"><button>确认签发临时访问码</button> <a href="/ops/users">取消</a></form>',csrf_for(token))

    @app.post('/ops/access')
    def issue_access(request: Request, trial_id: str = Form(...,max_length=36), csrf: str = Form('')):
        token = authorize(request,csrf)
        try:
            result = store.issue_access(trial_id)
        except OpsError:
            return page('无法签发','<h1>无法签发</h1><p>账号已停用、试用已结束或不支持转换，请检查客户状态。</p><a href="/ops/users">返回客户列表</a>',csrf_for(token),400)
        return page('临时登录访问码已生成',f'<h1>临时登录访问码已生成</h1><p>仅本次展示，请私下分发；无需短信，不代表手机号已验证。</p><p class="code">{escape(result["code"])}</p><p>首次登录起72小时，再次登录或改发不延期。</p><a href="/ops/users">返回客户列表</a>',csrf_for(token))

    @app.post('/ops/revoke')
    def revoke(request: Request, trial_id: str = Form(...,max_length=36), csrf: str = Form('')):
        token = authorize(request,csrf)
        try:
            store.revoke(trial_id)
        except OpsError:
            # An expired, already revoked, malformed or missing trial is an
            # operator input/state error. Keep it out of the generic 503
            # handler so the operator does not mistake it for an outage or
            # retry a destructive action blindly.
            return page('无法停用',
                        '<h1>无法停用</h1><p>客户试用不存在、已停用或请求已失效，请刷新客户列表后再试。</p>'
                        '<a href="/ops/users">返回客户列表</a>', csrf_for(token), 400)
        return RedirectResponse('/ops/users',303)

    @app.get('/ops/reissue')
    def confirm_reissue(request: Request, trial_id: str):
        token = identity(request)
        return page('重发未激活试用码','<h1>生成替换码？</h1><p>仅未激活、未停用的试用可重发。原试用码立即作废，不创建新客户。</p>'
                    f'<form method="post" action="/ops/reissue">{hidden(csrf_for(token))}<input type="hidden" name="trial_id" value="{escape(trial_id,quote=True)}"><button>生成替换码</button> <a href="/ops/users">取消</a></form>',csrf_for(token))

    @app.post('/ops/reissue')
    def reissue(request: Request, trial_id: str = Form(...,max_length=36), csrf: str = Form('')):
        token = authorize(request,csrf)
        try:
            result = store.reissue(trial_id)
        except OpsError:
            return page('无法重发','<h1>无法重发</h1><p>试用已激活、停用或记录不存在，请检查客户状态。</p><a href="/ops/users">返回客户列表</a>',csrf_for(token),400)
        return page('替换码已生成',f'<h1>替换码已生成</h1><p>原码已作废，请私下发给原客户；仅展示一次。</p><p class="code">{escape(result["code"])}</p><a href="/ops/users">返回客户列表</a>',csrf_for(token))

    return app


def configured_app():
    """Uvicorn factory, separate process and secret-scoped environment."""
    from pilot.db import PilotDatabase
    if os.environ.get('YIKE_PILOT_ADMIN_DATABASE_URL') or os.environ.get('YIKE_PILOT_DATABASE_URL'):
        raise OpsError('customer_or_admin_database_forbidden_in_ops')
    try:
        database = PilotDatabase(os.environ['YIKE_OPS_DATABASE_URL'])
        key = bytes.fromhex(os.environ['YIKE_OPS_PHONE_ENCRYPTION_KEY'])
        secret = os.environ['YIKE_PILOT_PHONE_AUTH_SECRET'].encode()
        store = OpsStore(database,phone_secret=secret,encryption_key=key)
        return build_ops_app(store,password=os.environ['YIKE_OPS_PASSWORD'],origin=os.environ['YIKE_OPS_ORIGIN'])
    except (KeyError,ValueError):
        raise OpsError('invalid_ops_configuration') from None

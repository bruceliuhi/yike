"""Ordinary Node client / HTTP / restricted PG, synthetic model and source only."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time

import uvicorn
from pilot.auth import issue_token
from pilot.runtime import build_runtime_app
from pilot.short_coach import ShortCoachService
from tests.test_pilot_runtime import _route_service
from tests.test_confirmed_strategy_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_review, real_strategy_env,
)
from tests.test_opportunity_evidence_postgres import include
from tests.test_desktop_opportunity_http_postgres import _node_environment
from tests.test_execution_runtime_postgres import SECRET


def test_runtime_keeps_unconfigured_short_coach_unavailable():
    db=object()
    app=build_runtime_app(db,auth_secret=SECRET,environment={})
    service=_route_service(app,'/api/ui/short-coach/preview',ShortCoachService)
    assert service.database is db and service.model is None


def test_ordinary_client_preview_confirm_generate_replay(real_strategy_env):
    env=real_strategy_env; root=Path(__file__).parents[1]
    with env.admin.connect() as conn:
        conn.execute("SELECT set_config('yike.app_role',%s,true)",(env.db.role,))
        conn.execute((root/'deploy/grant_short_coach.sql').read_text())
    _,_,_,_,_,_,opp=include(env,service=real_review(env))
    class Model:
        available=True; provider='synthetic'; model='coach-v1'; calls=0
        def generate(self,**kwargs):
            self.calls+=1
            assert set(kwargs)=={'sourceText','content','channel','purpose'}
            return {'content':'您好，项目需求还在推进吗？','question':'项目需求还在推进吗？','quote':kwargs['sourceText'][:2]}
    app=build_runtime_app(env.db,auth_secret=SECRET,dev_login=True,environment={})
    service=_route_service(app,'/api/ui/short-coach/preview',ShortCoachService)
    model=Model();service.model=model
    token=issue_token(env.claims.user_id,SECRET)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen(16)
        server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False,lifespan='off'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
            assert server.started
            child_env=_node_environment()
            child_env.update(YIKE_COACH_LIVE_BASE=f'http://127.0.0.1:{listener.getsockname()[1]}',
                YIKE_COACH_LIVE_TOKEN=token,YIKE_COACH_LIVE_OPPORTUNITY=opp)
            child=subprocess.run([os.environ['YIKE_RESEARCH_LIVE_NODE_BINARY'],'node_modules/vitest/vitest.mjs','run',
                'tests/integration/short-coach-live.test.ts','--maxWorkers=1'],cwd=root/'desktop',env=child_env,
                capture_output=True,text=True,timeout=40)
            output=(child.stdout+child.stderr).replace(token,'[redacted]')
            assert child.returncode==0,output
            assert '1 passed' in output and 'skipped' not in output.lower(),output
            assert model.calls==1
        finally:
            server.should_exit=True;thread.join(10);assert not thread.is_alive()
            with env.admin.connect() as conn:
                conn.execute('DELETE FROM pilot_short_coach_requests WHERE tenant_id=ANY(%s)',(env.tenants,))
                conn.execute('DELETE FROM pilot_short_coach_daily_quota WHERE tenant_id=ANY(%s)',(env.tenants,))

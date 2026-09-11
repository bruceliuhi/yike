"""Ordinary client HTTP/restricted PG, synthetic business input only."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import uvicorn
from pilot.auth import issue_token
from pilot.runtime import build_runtime_app
from pilot.store import PilotStore
from tests.test_confirmed_strategy_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_review, real_strategy_env,
)
from tests.test_opportunity_evidence_postgres import include
from tests.test_desktop_opportunity_http_postgres import _node_environment
from tests.test_execution_runtime_postgres import SECRET


def test_client_structured_history_and_recovery(real_strategy_env):
    env=real_strategy_env; root=Path(__file__).parents[1]
    with env.admin.connect() as conn:
        conn.execute("SELECT set_config('yike.app_role',%s,true)",(env.db.role,))
        conn.execute((root/'deploy/grant_structured_followups.sql').read_text())
    _,_,_,_,_,_,opp=include(env,service=real_review(env))
    # Trusted historical fixture only; every new structured write uses restricted HTTP.
    PilotStore(env.admin).record_followup(env.claims.user_id,opp,'CONTACTED','synthetic legacy history')
    app=build_runtime_app(env.db,auth_secret=SECRET,dev_login=True,environment={})
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
            child_env.update(YIKE_FOLLOWUP_LIVE_BASE=f'http://127.0.0.1:{listener.getsockname()[1]}',YIKE_FOLLOWUP_LIVE_TOKEN=token,YIKE_FOLLOWUP_LIVE_OPPORTUNITY=opp)
            child=subprocess.run([os.environ['YIKE_RESEARCH_LIVE_NODE_BINARY'],'node_modules/vitest/vitest.mjs','run','tests/integration/followup-live.test.ts','--maxWorkers=1'],
                cwd=root/'desktop',env=child_env,capture_output=True,text=True,timeout=40)
            output=(child.stdout+child.stderr).replace(token,'[redacted]')
            assert child.returncode==0,output
            assert '1 passed' in output and 'skipped' not in output.lower(),output
        finally:
            server.should_exit=True;thread.join(10);assert not thread.is_alive()
            with env.admin.connect() as conn:
                for table in ('pilot_followup_operations','pilot_followup_reply_reads','pilot_structured_followup_revisions'):
                    conn.execute(f'ALTER TABLE {table} DISABLE TRIGGER USER')
                    conn.execute(f'DELETE FROM {table} WHERE tenant_id=ANY(%s)',(env.tenants,))
                    conn.execute(f'ALTER TABLE {table} ENABLE TRIGGER USER')
                conn.execute('DELETE FROM pilot_followups WHERE tenant_id=ANY(%s)',(env.tenants,))

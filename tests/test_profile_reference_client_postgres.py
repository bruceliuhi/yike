"""Ordinary Node/HTTP/restricted PG; synthetic material, no model network or platform."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import uvicorn
from psycopg import sql
from pilot.auth import issue_token
from pilot.runtime import build_runtime_app
from tests.test_materials_store import database, env, SECRET
from tests.test_material_profile_references import _ready
from tests.test_desktop_opportunity_http_postgres import _node_environment


def test_profile_reference_client_revoke_and_explicit_manual_recovery(env):
    root=Path(__file__).parents[1]
    with env.admin.connect() as conn:
        role=sql.Identifier(env.db.role)
        conn.execute(sql.SQL('GRANT SELECT ON pilot_tenants,business_profiles,pilot_tasks TO {}').format(role))
        conn.execute(sql.SQL('GRANT INSERT ON business_profiles,business_profile_versions,pilot_tasks TO {}').format(role))
        conn.execute(sql.SQL('GRANT UPDATE(name) ON business_profiles TO {}').format(role))
        conn.execute(sql.SQL('GRANT UPDATE(status,approved_at) ON business_profile_versions TO {}').format(role))
        conn.execute("SELECT set_config('yike.app_role',%s,true)",(env.db.role,))
        conn.execute((root/'deploy/grant_search_suggestions.sql').read_text())
    _,source,ready=_ready(env)
    app=build_runtime_app(env.db,auth_secret=SECRET,dev_login=True,environment={
        'YIKE_PILOT_SEARCH_SUGGESTION_BASE_URL':'http://127.0.0.1:9/v1',
        'YIKE_PILOT_SEARCH_SUGGESTION_API_KEY':'synthetic-not-used',
        'YIKE_PILOT_SEARCH_SUGGESTION_MODEL':'synthetic-not-called'})
    token=issue_token(env.users[0],SECRET)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen(16)
        server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False,lifespan='off'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
            assert server.started
            child_env=_node_environment()
            child_env.update(YIKE_PROFILE_REF_BASE=f'http://127.0.0.1:{listener.getsockname()[1]}',
                YIKE_PROFILE_REF_TOKEN=token,YIKE_PROFILE_REF_SOURCE=source,YIKE_PROFILE_REF_MATERIAL=ready['id'],
                YIKE_PROFILE_REF_EXTRACTION=ready['extraction']['id'],YIKE_PROFILE_REF_VERSION=str(ready['version']))
            child=subprocess.run([os.environ['YIKE_RESEARCH_LIVE_NODE_BINARY'],'node_modules/vitest/vitest.mjs','run',
                'tests/integration/profile-references-live.test.ts','--maxWorkers=1'],cwd=root/'desktop',env=child_env,
                capture_output=True,text=True,timeout=40)
            output=(child.stdout+child.stderr).replace(token,'[redacted]')
            assert child.returncode==0,output
            assert '1 passed' in output and 'skipped' not in output.lower(),output
        finally:
            server.should_exit=True;thread.join(10);assert not thread.is_alive()

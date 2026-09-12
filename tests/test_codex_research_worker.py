import copy
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import pytest

pytest.importorskip('mcp', reason='requires optional research dependencies')
pytestmark = pytest.mark.skipif(os.name != 'posix', reason='cloud Worker is POSIX, not Windows client')


def read_event(identifier='item_1'):
    text='示例采购问题，不是真实商机'
    evidence=dict(url='https://new-source.example/project',title='示例',text=text,
                  observed_at=datetime.now(UTC).isoformat(),
                  content_sha256=hashlib.sha256(text.encode()).hexdigest(),read_scope='PUBLIC_PAGE_TEXT')
    return {'type':'item.completed','item':{'id':identifier,'type':'mcp_tool_call',
        'server':'yike_public','tool':'read_public_page','arguments':{'url':evidence['url']},
        'status':'completed','error':None,'result':{'content':[],
        'structured_content':dict(status='READ',evidence=evidence,review_status='UNREVIEWED',replayed=False)}}}


def final_events():
    return [{'type':'item.completed','item':{'id':'item_2','type':'agent_message','text':'模型解释，与原文分开'}},
            {'type':'turn.completed','usage':{'input_tokens':100,'output_tokens':12,'cached_input_tokens':0}}]


@pytest.fixture
def worker(monkeypatch):
    import pilot.codex_research_worker as module
    class FakeBridge:
        base_url='http://127.0.0.1:1/v1'
        token='synthetic-local-token'
        records=[]
        def __init__(self, **kwargs):
            assert kwargs['api_key']=='synthetic-provider-secret'
            assert kwargs['allowed_tools']==(('mcp__yike_public','read_public_page'),)
        def __enter__(self): return self
        def __exit__(self,*exc): pass
    monkeypatch.setattr(module,'ResponsesBridge',FakeBridge)
    return module


def executable(tmp_path, events=(), extra=''):
    path=tmp_path/'codex-fixture'
    payload=''.join(json.dumps(event,ensure_ascii=False)+'\n' for event in events)
    path.write_text(f'#!{sys.executable}\nimport os,sys,time,json,subprocess\n'
                    f'sys.stdout.write({payload!r});sys.stdout.flush()\n'+extra)
    path.chmod(0o700)
    return str(path)


def run(worker,tmp_path,events=(),extra='',**kwargs):
    return worker.run_public_read_mission('阅读提供的公开来源，保留依据。',
        codex_binary=executable(tmp_path,events,extra),python_binary=sys.executable,
        api_key='synthetic-provider-secret',model='test-model',max_seconds=kwargs.pop('max_seconds',5),**kwargs)


def test_actual_jsonl_read_success_and_duplicate_event(worker,tmp_path):
    event=read_event()
    result=run(worker,tmp_path,[event,event,*final_events()])
    assert result['status']=='COMPLETED' and result['code'] is None
    assert result['reads']==[event['item']['result']['structured_content']]
    assert result['summary']=='模型解释，与原文分开'
    assert result['usage']=={'input_tokens':100,'output_tokens':12,'cached_input_tokens':0}


@pytest.mark.parametrize('change', ['hash','url','tool','review','future','conflict'])
def test_invalid_tool_evidence_cannot_become_completed(worker,tmp_path,change):
    event=read_event(); events=[]
    if change=='hash': event['item']['result']['structured_content']['evidence']['content_sha256']='0'*64
    if change=='url': event['item']['arguments']['url']='https://different.example/'
    if change=='tool': event['item']['tool']='send_message'
    if change=='review': event['item']['result']['structured_content']['review_status']='APPROVED'
    if change=='future': event['item']['result']['structured_content']['evidence']['observed_at']='2099-01-01T00:00:00Z'
    if change=='conflict':
        events.append(copy.deepcopy(event)); event['item']['arguments']['url']='https://different.example/'
    result=run(worker,tmp_path,[*events,event,*final_events()])
    assert result['status']=='FAILED' and result['code']=='invalid_runtime_output'


def test_model_only_text_is_not_verified_evidence(worker,tmp_path):
    result=run(worker,tmp_path,final_events())
    assert result['status']=='FAILED' and result['code']=='no_verified_reads' and result['reads']==[]


def test_failed_turn_preserves_actual_reads_but_not_completion(worker,tmp_path):
    result=run(worker,tmp_path,[read_event(),{'type':'turn.failed','error':{'message':'private diagnostic'}}])
    assert result['status']=='FAILED' and len(result['reads'])==1 and result['usage'] is None
    assert 'private diagnostic' not in json.dumps(result)


@pytest.mark.parametrize('usage',[{'input_tokens':True,'output_tokens':1},{'input_tokens':-1,'output_tokens':1}])
def test_invalid_usage_is_not_accepted(worker,tmp_path,usage):
    result=run(worker,tmp_path,[read_event(),{'type':'turn.completed','usage':usage}])
    assert result['status']=='FAILED' and result['usage'] is None


def test_missing_usage_stays_unknown(worker,tmp_path):
    result=run(worker,tmp_path,[read_event(),{'type':'turn.completed'}])
    assert result['status']=='COMPLETED' and result['usage'] is None


def test_failed_tool_fixed_code_separate_from_reads(worker,tmp_path):
    failed=read_event('failed_1'); failed['item']['result']['structured_content']={'status':'FAILED','code':'timeout','replayed':False}
    result=run(worker,tmp_path,[failed,read_event(),*final_events()])
    assert result['status']=='COMPLETED'
    assert result['read_failures']==[{'url':'https://new-source.example/project','code':'timeout'}]


def test_real_process_environment_and_private_workspace_cleanup(worker,tmp_path,monkeypatch):
    capture=tmp_path/'capture.json'
    monkeypatch.setenv('PRIVATE_UNRELATED_ENV','not-for-worker')
    extra=f"open({str(capture)!r},'w').write(json.dumps(dict(argv=sys.argv,env=dict(os.environ),cwd=os.getcwd(),prompt=sys.stdin.read())))\n"
    result=run(worker,tmp_path,[read_event(),*final_events()],extra=extra)
    data=json.loads(capture.read_text())
    assert result['status']=='COMPLETED'
    assert 'synthetic-provider-secret' not in json.dumps(data)
    assert 'PRIVATE_UNRELATED_ENV' not in data['env']
    assert data['env']['YIKE_BRIDGE_TOKEN']=='synthetic-local-token'
    assert data['cwd']!=str(tmp_path) and not Path(data['cwd']).exists()
    assert not Path(data['env']['CODEX_HOME']).exists()
    assert '--ignore-user-config' in data['argv'] and '--ephemeral' in data['argv']
    assert 'mcp_servers.yike_public.required=true' in data['argv']
    assert '-i' in ''.join(data['argv']) and 'shell_environment_policy.inherit="none"' in data['argv']


def test_actual_process_deadline(worker,tmp_path):
    start=time.monotonic()
    result=run(worker,tmp_path,extra='time.sleep(20)\n',max_seconds=1)
    assert result['status']=='FAILED' and result['code']=='timeout'
    assert time.monotonic()-start<3


def test_actual_process_cancel_preserves_read(worker,tmp_path,monkeypatch):
    accepted=[]
    original=worker._ReadEvents.accept
    def record_accept(self,event):
        original(self,event)
        accepted.extend(self.reads)
    monkeypatch.setattr(worker._ReadEvents,'accept',record_accept)
    result=run(worker,tmp_path,[read_event()],extra='time.sleep(20)\n',
               cancelled=lambda:bool(accepted))
    assert result['status']=='CANCELLED' and len(result['reads'])==1


def test_provider_attempts_captured_after_bridge_shutdown(worker,tmp_path,monkeypatch):
    class SettlingBridge(worker.ResponsesBridge):
        def __exit__(self,*exc):
            self.records=[{'ordinal':1,'status':'unknown','code':'interrupted','usage':None}]
    monkeypatch.setattr(worker,'ResponsesBridge',SettlingBridge)
    result=run(worker,tmp_path,extra='time.sleep(20)\n',max_seconds=1)
    assert result['code']=='timeout'
    assert result['provider_calls']==[{'ordinal':1,'status':'unknown','code':'interrupted','usage':None}]


def test_output_limit_aborts_without_echo(worker,tmp_path):
    result=run(worker,tmp_path,extra="sys.stdout.write('SYNTHETIC_SECRET'*200000);sys.stdout.flush();time.sleep(20)\n")
    assert result['status']=='FAILED' and result['code']=='output_limit'
    assert 'SYNTHETIC_SECRET' not in json.dumps(result)


def test_malformed_json_and_nonzero_exit_fail_closed(worker,tmp_path):
    result=run(worker,tmp_path,extra="print('not-json');sys.exit(1)\n")
    assert result['status']=='FAILED' and result['reads']==[]


def test_invalid_host_configuration_never_starts(worker,tmp_path):
    result=worker.run_public_read_mission('公开研究',codex_binary='relative',python_binary=sys.executable,
                                          api_key='synthetic-provider-secret',model='test-model')
    assert result['status']=='FAILED' and result['code']=='invalid_configuration'


def test_owned_descendant_stops_on_parent_exit(worker,tmp_path):
    marker=tmp_path/'should-not-exist'
    child=f"import time,pathlib;time.sleep(0.7);pathlib.Path({str(marker)!r}).write_text('alive')"
    extra=f"subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
    result=run(worker,tmp_path,[read_event(),*final_events()],extra=extra)
    assert result['status']=='COMPLETED'
    time.sleep(0.8)
    assert not marker.exists()

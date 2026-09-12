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


def search_event(identifier='search_1', *, results=None):
    if results is None:
        results=[dict(url='https://new-source.example/project',title='示例搜索结果',
                      snippet='索引摘要，不是原文',date_hint=None,rank=1)]
    value=dict(status='SEARCHED',query='中文 采购 需求',observed_at=datetime.now(UTC).isoformat(),
               read_scope='SEARCH_RESULTS',results=results,omitted_count=0,replayed=False)
    return {'type':'item.completed','item':{'id':identifier,'type':'mcp_tool_call',
        'server':'yike_public','tool':'search_public_web','arguments':{'query':'中文 采购 需求'},
        'status':'completed','error':None,'result':{'content':[],'structured_content':value}}}


def final_events():
    return [{'type':'item.completed','item':{'id':'item_2','type':'agent_message','text':'模型解释，与原文分开'}},
            {'type':'turn.completed','usage':{'input_tokens':100,'output_tokens':12,'cached_input_tokens':0}}]


@pytest.fixture
def worker(monkeypatch):
    import pilot.codex_research_worker as module
    class FakeBridge:
        base_url='http://127.0.0.1:1/v1'
        search_url=None
        token='synthetic-local-token'
        records=[]
        def __init__(self, **kwargs):
            assert kwargs['api_key']=='synthetic-provider-secret'
            expected=(('mcp__yike_public','read_public_page'),)
            if kwargs.get('search_service') is not None:
                expected=(('mcp__yike_public','search_public_web'),*expected)
                self.search_url='http://127.0.0.1:1/v1/public-search'
            assert kwargs['allowed_tools']==expected
        def __enter__(self): return self
        def __exit__(self,*exc): pass
    monkeypatch.setattr(module,'ResponsesBridge',FakeBridge)
    class FakeSearchSession:
        instances=[]
        def __init__(self, *, api_key, max_searches, deadline):
            assert api_key=='synthetic-search-secret'
            self.max_searches=max_searches
            self.deadline=deadline
            self.closed=False
            self.__class__.instances.append(self)
        def close(self): self.closed=True
    monkeypatch.setattr(module,'PublicSearchSession',FakeSearchSession,raising=False)
    module._test_search_sessions=FakeSearchSession.instances
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


def run_research(worker,tmp_path,events=(),extra='',description='研究公开需求。',**kwargs):
    return worker.run_public_research_mission(description,
        codex_binary=executable(tmp_path,events,extra),python_binary=sys.executable,
        api_key='synthetic-provider-secret',search_api_key='synthetic-search-secret',
        model='test-model',max_seconds=kwargs.pop('max_seconds',5),**kwargs)


def test_actual_jsonl_read_success_and_duplicate_event(worker,tmp_path):
    event=read_event()
    result=run(worker,tmp_path,[event,event,*final_events()])
    assert result['status']=='COMPLETED' and result['code'] is None
    assert result['reads']==[event['item']['result']['structured_content']]
    assert result['summary']=='模型解释，与原文分开'
    assert result['usage']=={'input_tokens':100,'output_tokens':12,'cached_input_tokens':0}
    assert set(result)=={'status','code','reads','read_failures','summary','usage','provider_calls'}


def test_actual_jsonl_search_then_read_success(worker,tmp_path):
    searched=search_event()
    result=run_research(worker,tmp_path,[searched,read_event(),*final_events()])
    assert result['status']=='COMPLETED' and result['code'] is None
    assert result['searches']==[searched['item']['result']['structured_content']]
    assert result['search_failures']==[] and len(result['reads'])==1


def test_valid_zero_result_search_is_observed_but_not_a_verified_read(worker,tmp_path):
    searched=search_event(results=[])
    result=run_research(worker,tmp_path,[searched,*final_events()])
    assert result['status']=='FAILED' and result['code']=='no_verified_reads'
    assert result['searches']==[searched['item']['result']['structured_content']]
    assert result['reads']==[]


def test_replayed_search_event_does_not_inflate_observed_search_facts(worker,tmp_path):
    original=search_event()
    replayed=copy.deepcopy(original)
    replayed['item']['id']='search_2'
    replayed['item']['result']['structured_content']['replayed']=True
    result=run_research(worker,tmp_path,[original,replayed,read_event(),*final_events()])
    assert result['status']=='COMPLETED'
    assert result['searches']==[original['item']['result']['structured_content']]


@pytest.mark.parametrize('change',['schema','foreign_read','conflict'])
def test_search_events_fail_closed(worker,tmp_path,change):
    searched=search_event(); events=[]
    if change=='schema': searched['item']['result']['structured_content']['results'][0]['rank']=True
    if change=='foreign_read':
        read=read_event(); read['item']['arguments']['url']='https://foreign.example/item'
        read['item']['result']['structured_content']['evidence']['url']='https://foreign.example/item'
        text=read['item']['result']['structured_content']['evidence']['text']
        read['item']['result']['structured_content']['evidence']['content_sha256']=hashlib.sha256(text.encode()).hexdigest()
        events=[searched,read]
    elif change=='conflict':
        events=[copy.deepcopy(searched)]
        searched['item']['arguments']['query']='另一个查询'
        events.append(searched)
    else: events=[searched]
    result=run_research(worker,tmp_path,[*events,*final_events()])
    assert result['status']=='FAILED' and result['code']=='invalid_runtime_output'


def test_model_text_alone_is_not_a_search(worker,tmp_path):
    result=run_research(worker,tmp_path,final_events())
    assert result['status']=='FAILED' and result['code']=='no_verified_searches'
    assert result['searches']==[] and result['reads']==[]


def test_search_failure_is_separate_actual_event(worker,tmp_path):
    failed=search_event()
    failed['item']['status']='failed'
    failed['item']['result']['structured_content']={'status':'FAILED','code':'rate_limited','replayed':False}
    result=run_research(worker,tmp_path,[failed,*final_events()])
    assert result['status']=='FAILED' and result['code']=='no_verified_searches'
    assert result['search_failures']==[{'query':'中文 采购 需求','code':'rate_limited'}]


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


def test_research_process_gets_only_temporary_search_bridge_credentials(worker,tmp_path,monkeypatch):
    capture=tmp_path/'research-capture.json'
    monkeypatch.setenv('SEARCH_API_KEY','ambient-secret')
    extra=f"open({str(capture)!r},'w').write(json.dumps(dict(argv=sys.argv,env=dict(os.environ),cwd=os.getcwd(),prompt=sys.stdin.read())))\n"
    result=run_research(worker,tmp_path,[search_event(),read_event(),*final_events()],extra=extra)
    data=json.loads(capture.read_text())
    serialized=json.dumps(data,ensure_ascii=False)
    assert result['status']=='COMPLETED'
    assert 'synthetic-provider-secret' not in serialized
    assert 'synthetic-search-secret' not in serialized
    assert 'ambient-secret' not in serialized
    assert data['env']['YIKE_BRIDGE_TOKEN']=='synthetic-local-token'
    assert 'YIKE_PUBLIC_SEARCH_URL' not in data['env']
    assert 'YIKE_PUBLIC_SEARCH_TOKEN' not in data['env']
    assert 'YIKE_PUBLIC_SEARCH_URL=http://127.0.0.1:1/v1/public-search' in serialized
    assert 'YIKE_PUBLIC_SEARCH_TOKEN=synthetic-local-token' in serialized
    assert 'mcp_servers.yike_public.enabled_tools=["search_public_web","read_public_page"]' in data['argv']
    assert 'search_public_web' in serialized and 'read_public_page' in serialized


def test_research_instructions_require_search_then_read(worker,tmp_path):
    capture=tmp_path/'research-config.json'
    extra=("config=next(value for value in sys.argv if value.startswith('model_instructions_file='))\n"
           "instructions=open(json.loads(config.split('=',1)[1])).read()\n"
           f"open({str(capture)!r},'w').write(json.dumps(dict(argv=sys.argv,prompt=sys.stdin.read(),instructions=instructions)))\n")
    result=run_research(worker,tmp_path,[search_event(),read_event(),*final_events()],extra=extra,
                        max_searches=2,max_reads=4,max_requests=5)
    data=json.loads(capture.read_text())
    instruction_arg=next(value for value in data['argv'] if value.startswith('model_instructions_file='))
    # The private temporary file is cleaned; the argv path and mission prompt must never contain secrets.
    assert result['status']=='COMPLETED'
    assert 'synthetic-search-secret' not in json.dumps(data)
    assert '研究公开需求' in data['prompt']
    assert instruction_arg
    assert 'search_public_web first' in data['instructions']
    assert 'then read_public_page' in data['instructions']
    assert 'snippets only discover sources' in data['instructions']
    assert 'at most 2 distinct searches' in data['instructions']
    assert 'at most 4 original-page reads' in data['instructions']
    assert 'host allows at most 5 model requests' in data['instructions']
    assert 'finish the final answer before exhausting that request budget' in data['instructions']
    assert 'first-person buyer' in data['instructions']
    assert 'business or action signals' in data['instructions']
    assert 'community-native sources' in data['instructions']
    assert 'SEO roundups, vendor advertisements, and auto-translated pages' in data['instructions']
    assert 'synthetic-provider-secret' not in data['instructions']
    assert 'synthetic-search-secret' not in data['instructions']


def test_read_only_instructions_remain_exactly_unchanged(worker,tmp_path):
    capture=tmp_path/'read-config.json'
    extra=("config=next(value for value in sys.argv if value.startswith('model_instructions_file='))\n"
           "instructions=open(json.loads(config.split('=',1)[1])).read()\n"
           f"open({str(capture)!r},'w').write(json.dumps(dict(instructions=instructions)))\n")
    result=run(worker,tmp_path,[read_event(),*final_events()],extra=extra,
               max_reads=4,max_requests=5)
    data=json.loads(capture.read_text())
    assert result['status']=='COMPLETED'
    assert data['instructions']==worker._INSTRUCTIONS


@pytest.mark.parametrize('description',['包含 synthetic-provider-secret','包含 synthetic-search-secret'])
def test_research_rejects_secret_substrings_in_public_description(worker,tmp_path,description):
    result=run_research(worker,tmp_path,description=description)
    assert result['status']=='FAILED' and result['code']=='invalid_configuration'
    assert worker._test_search_sessions==[]


def test_research_none_search_key_fails_as_research_without_read_mode_fallback(worker,tmp_path):
    result=worker.run_public_research_mission('公开研究',
        codex_binary=executable(tmp_path),python_binary=sys.executable,
        api_key='synthetic-provider-secret',search_api_key=None,model='test-model')
    assert result['status']=='FAILED' and result['code']=='invalid_configuration'
    assert set(result)=={'status','code','reads','read_failures','summary','usage','provider_calls',
                         'searches','search_failures'}
    assert worker._test_search_sessions==[]


@pytest.mark.parametrize('events,extra,cancel_after_start',[
    ((),"raise RuntimeError('spawn')\n",False),
    ((),"time.sleep(20)\n",True),
])
def test_research_session_closes_on_runtime_error_or_cancel(worker,tmp_path,events,extra,cancel_after_start):
    checks=[]
    def cancelled():
        checks.append(True)
        return cancel_after_start and len(checks) > 1
    result=run_research(worker,tmp_path,events,extra=extra,cancelled=cancelled,max_seconds=1)
    assert result['status'] in {'FAILED','CANCELLED'}
    assert worker._test_search_sessions and worker._test_search_sessions[-1].closed is True


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

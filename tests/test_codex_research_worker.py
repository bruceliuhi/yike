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


def final_events_with(text):
    return [{'type':'item.completed','item':{'id':'item_2','type':'agent_message','text':text}},
            {'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}}]


def citation_final_events(*read_events):
    pages=[]
    for event in read_events:
        evidence=event['item']['result']['structured_content']['evidence']
        pages.append(dict(url=evidence['url'],content_sha256=evidence['content_sha256'],
                          decision='ASSESS',reason='POSSIBLE_DEMAND',quote_ref='q1'))
    return final_events_with(json.dumps(dict(schema_version='research-citation-choice-v1',
        summary='逐页引用选择完成',pages=pages),ensure_ascii=False))


def citation_read_event(event):
    original=copy.deepcopy(event['item']['result']['structured_content'])
    evidence=original['evidence']
    projected=copy.deepcopy(original)
    projected['evidence'].pop('text')
    projected['evidence']['text_fragments']=[
        {'quote_ref':f'q{offset//400+1}','text':evidence['text'][offset:offset+400]}
        for offset in range(0,len(evidence['text']),400)]
    event['item']['result']={'content':[{'type':'text','text':
        'Citation fragments are provided in structuredContent.'}],
        'structured_content':projected,
        '_meta':{'yike_original_read_v1':original}}
    return event


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


@pytest.mark.parametrize('dispatcher',[None,False,{},'not-callable'])
def test_explicit_invalid_effect_dispatcher_fails_before_any_start(worker,tmp_path,dispatcher):
    checks=[]
    result=run_research(worker,tmp_path,effect_dispatcher=dispatcher,
                        cancelled=lambda:checks.append(True))
    assert result['status']=='FAILED' and result['code']=='invalid_configuration'
    assert worker._test_search_sessions==[] and checks==[]
    assert len(result)==9


def test_controlled_worker_passes_shared_gate_and_host_read_credentials(worker,tmp_path,monkeypatch):
    captured={}; services=[]
    class Search:
        def __init__(self, **kwargs): captured['search']=kwargs
        def allows_read(self,url): return url=='https://new-source.example/project'
        def close(self): captured['search_closed']=True
    class Read:
        def __init__(self, **kwargs):
            captured['read']=kwargs; services.append(self); self.closed=False
        def close(self): self.closed=True
    class Bridge:
        base_url='http://127.0.0.1:1/v1'
        search_url=base_url+'/public-search'; read_url=base_url+'/public-read'
        token='synthetic-local-token'; records=[]
        def __init__(self, **kwargs): captured['bridge']=kwargs
        def __enter__(self): return self
        def __exit__(self,*exc): pass
    monkeypatch.setattr(worker,'PublicSearchSession',Search)
    monkeypatch.setattr(worker,'PublicReadSession',Read,raising=False)
    monkeypatch.setattr(worker,'ResponsesBridge',Bridge)
    cancel=[False]; effects=[]
    def dispatcher(kind,payload,deadline,perform):
        effects.append(kind); return perform(deadline)
    capture=tmp_path/'controlled-config.json'
    extra=f"open({str(capture)!r},'w').write(json.dumps(dict(argv=sys.argv,env=dict(os.environ))))\n"
    result=run_research(worker,tmp_path,[search_event(),read_event(),*final_events()],
        extra=extra,effect_dispatcher=dispatcher,cancelled=lambda:cancel[0])
    assert result['status']=='COMPLETED' and len(result)==9
    gate=captured['search']['effect_dispatcher']
    assert gate is captured['read']['effect_dispatcher'] is captured['bridge']['effect_dispatcher']
    assert captured['read']['allowed_url']('https://new-source.example/project')
    assert captured['bridge']['read_service'] is services[0]
    assert services[0].closed and captured['search_closed']
    data=capture.read_text()
    assert 'YIKE_PUBLIC_READ_URL=http://127.0.0.1:1/v1/public-read' in data
    assert 'YIKE_PUBLIC_READ_TOKEN=synthetic-local-token' in data
    assert 'synthetic-provider-secret' not in data and 'synthetic-search-secret' not in data
    # Shared wrapper must stop delayed effects if cancellation changes after admission.
    from pilot.research_effects import EffectDispatchError
    cancel[0]=True
    with pytest.raises(EffectDispatchError): gate('READ',{},time.monotonic()+1,lambda _: {})
    assert effects==[]


def test_controlled_reader_closes_when_bridge_setup_fails(worker,tmp_path,monkeypatch):
    readers=[]
    class Search:
        def __init__(self, **kwargs): pass
        def allows_read(self,url): return False
        def close(self): pass
    class Reader:
        def __init__(self, **kwargs): self.closed=False; readers.append(self)
        def close(self): self.closed=True
    def broken_bridge(**kwargs): raise RuntimeError('private failure')
    monkeypatch.setattr(worker,'PublicSearchSession',Search)
    monkeypatch.setattr(worker,'PublicReadSession',Reader,raising=False)
    monkeypatch.setattr(worker,'ResponsesBridge',broken_bridge)
    result=run_research(worker,tmp_path,effect_dispatcher=lambda *args: {})
    assert result['code']=='runtime_unavailable'
    assert len(readers)==1 and readers[0].closed


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


def test_seeded_event_accepts_exact_read_without_search_and_rejects_ungranted(worker):
    entry='https://www.v2ex.com/go/outsourcing'
    events=worker._ReadEvents(search_enabled=True,entry_urls=[entry])
    accepted=read_event()
    accepted['item']['arguments']['url']=entry
    accepted['item']['result']['structured_content']['evidence']['url']=entry
    events.accept(accepted)
    assert len(events.reads)==1 and events.searches==[]
    nearby=worker._ReadEvents(search_enabled=True,entry_urls=[entry])
    denied=copy.deepcopy(accepted)
    denied['item']['arguments']['url']=entry+'/nearby'
    denied['item']['result']['structured_content']['evidence']['url']=entry+'/nearby'
    with pytest.raises(worker._InvalidOutput):
        nearby.accept(denied)


def test_seeded_controlled_worker_transports_entries_and_completes_without_search(
        worker,tmp_path,monkeypatch):
    entry='https://www.v2ex.com/go/outsourcing'
    context=research_context()
    context['history']=[dict(project_key='known',description='known',state='KNOWN',source_urls=[entry])]
    capture=tmp_path/'seed-config.json'
    class Search:
        def __init__(self, **kwargs): pass
        def allows_read(self,url): return False
        def close(self): pass
    captured={}
    class Read:
        def __init__(self, **kwargs): captured['allowed_url']=kwargs['allowed_url']
        def close(self): pass
    class Bridge:
        base_url='http://127.0.0.1:1/v1'
        search_url=base_url+'/public-search'; read_url=base_url+'/public-read'
        token='synthetic-local-token'; records=[]
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*exc): pass
    monkeypatch.setattr(worker,'PublicSearchSession',Search)
    monkeypatch.setattr(worker,'PublicReadSession',Read)
    monkeypatch.setattr(worker,'ResponsesBridge',Bridge)
    extra=("config=next(value for value in sys.argv if value.startswith('model_instructions_file='))\n"
           "instructions=open(json.loads(config.split('=',1)[1])).read()\n"
           f"open({str(capture)!r},'w').write(json.dumps(dict(argv=sys.argv,env=dict(os.environ),instructions=instructions)))\n")
    event=read_event()
    event['item']['arguments']['url']=entry
    event['item']['result']['structured_content']['evidence']['url']=entry
    event=citation_read_event(event)
    result=run_research(worker,tmp_path,[event,*citation_final_events(event)],extra=extra,
        research_context=context,effect_dispatcher=lambda kind,payload,deadline,perform:perform(deadline))
    data=json.loads(capture.read_text())
    assert result['status']=='COMPLETED' and result['searches']==[] and len(result['reads'])==1
    serialized=json.dumps(data['argv'])
    assert 'YIKE_PUBLIC_ENTRY_URLS=' in serialized and 'https://www.v2ex.com/recent' in serialized
    assert '--citation-mode' in serialized
    expected=['https://www.v2ex.com/recent','https://www.v2ex.com/go/qna',entry]
    assert json.dumps(expected,separators=(',',':')) in data['instructions']
    assert captured['allowed_url'](entry) and not captured['allowed_url'](entry+'/nearby')
    assert 'search_public_web first' not in data['instructions']


def test_negative_catalog_entry_is_only_advisory_and_absent_from_active_guidance(worker):
    blocked='https://www.v2ex.com/go/outsourcing'
    context=research_context()
    context['history']=[dict(project_key='blocked',description='blocked',state='EXCLUDED',
                             source_urls=[blocked])]
    from pilot.research_context import compile_research_context
    compiled=compile_research_context(context)
    assert blocked not in compiled['entry_urls']
    runtime=worker._research_instructions(max_searches=2,max_reads=4,max_requests=5,
                                          entry_urls=compiled['entry_urls'])
    active=runtime.split('The exact trusted entries are: ',1)[1].split('.',1)[0]
    assert blocked not in active
    assert 'neither action is forced' in runtime


def test_uncontrolled_context_keeps_legacy_first_search_instruction(worker):
    runtime=worker._research_instructions(max_searches=2,max_reads=4,max_requests=5)
    assert 'using search_public_web first, then read_public_page' in runtime
    assert 'host-provided trusted entry' not in runtime


def test_read_only_instructions_remain_exactly_unchanged(worker,tmp_path):
    capture=tmp_path/'read-config.json'
    extra=("config=next(value for value in sys.argv if value.startswith('model_instructions_file='))\n"
           "instructions=open(json.loads(config.split('=',1)[1])).read()\n"
           f"open({str(capture)!r},'w').write(json.dumps(dict(argv=sys.argv,instructions=instructions)))\n")
    result=run(worker,tmp_path,[read_event(),*final_events()],extra=extra,
               max_reads=4,max_requests=5)
    data=json.loads(capture.read_text())
    assert result['status']=='COMPLETED'
    assert data['instructions']==worker._INSTRUCTIONS
    serialized=json.dumps(data['argv'])
    assert '--output-schema' not in data['argv'] and '--citation-mode' not in serialized


def research_context():
    return dict(schema_version='research-context-v1',
        profile_version_id='11111111-1111-4111-8111-111111111111',
        strategy_version_id='22222222-2222-4222-8222-222222222222',
        seller_description='食品工厂的不锈钢输送设备设计与安装，服务华东地区。',
        reference_time='2026-09-13T00:00:00+08:00',timezone='Asia/Shanghai',max_age_days=60,
        query_seeds=['产线改造 找设备团队'],intent_signals=['找设备供应商报价'],
        exclusions=['只招聘员工'],history_scope='PARTIAL',history=[dict(
            project_key='known-project',description='已经联系的食品输送项目',state='CONTACTED',
            source_urls=['https://example.com/known'])])


@pytest.mark.parametrize('version',[1,2])
def test_profile_research_loads_original_rules_and_bound_context_in_real_process(worker,tmp_path,version):
    capture=tmp_path/'profile-config.json'
    extra=("config=next(value for value in sys.argv if value.startswith('model_instructions_file='))\n"
           "instructions=open(json.loads(config.split('=',1)[1])).read()\n"
           "schema_index=sys.argv.index('--output-schema')\n"
           "schema=json.load(open(sys.argv[schema_index+1]))\n"
           f"open({str(capture)!r},'w').write(json.dumps(dict(argv=sys.argv,env=dict(os.environ),prompt=sys.stdin.read(),instructions=instructions,schema=schema)))\n")
    context=research_context()
    if version==2:
        from tests.test_research_context import projected_v2
        context=projected_v2()
    event=citation_read_event(read_event())
    result=run_research(worker,tmp_path,[search_event(),event,*citation_final_events(event)],
        extra=extra,research_context=context)
    from pilot.research_context import compile_research_context
    compiled=compile_research_context(context)
    data=json.loads(capture.read_text())
    assert result['status']=='COMPLETED'
    assert result['research_binding']==compiled['binding']
    assert data['instructions'].endswith(compiled['instructions'])
    assert 'v2ex-latest-v1' in data['instructions']
    assert 'https://www.v2ex.com/recent' in data['instructions']
    assert '/api/' not in compiled['instructions']
    assert result['research_binding']['rule_sha256']==hashlib.sha256(
        compiled['instructions'].encode('utf-8')).hexdigest()
    assert data['prompt'].startswith('HOST_RESEARCH_CONTEXT_JSON')
    assert data['prompt'].count(compiled['context_json']) == 1
    assert data['schema'] == worker.citation_choice_schema()
    assert data['argv'].count('--output-schema') == 1
    assert '--citation-mode' in json.dumps(data['argv'])
    from pilot.research_page_selection import parse_page_selection
    assert parse_page_selection(result['summary'], [result['reads'][0]['evidence']])
    assert context['seller_description'] not in json.dumps(data['argv'],ensure_ascii=False)
    assert context['seller_description'] not in json.dumps(data['env'],ensure_ascii=False)
    assert context['seller_description'] not in data['instructions']
    assert 'synthetic-provider-secret' not in json.dumps(data)
    assert 'synthetic-search-secret' not in json.dumps(data)
    assert result['research_binding']['profile_version_id']==context['profile_version_id']


@pytest.mark.parametrize('context',[None,{},research_context()|{'max_age_days':True}])
def test_invalid_explicit_research_context_never_starts_or_downgrades(worker,tmp_path,context):
    result=run_research(worker,tmp_path,research_context=context)
    assert result['status']=='FAILED' and result['code']=='invalid_research_context'
    assert result['research_binding'] is None and result['reads']==[] and result['searches']==[]
    assert worker._test_search_sessions==[]


@pytest.mark.parametrize('secret',['synthetic-provider-secret','synthetic-search-secret'])
def test_research_context_cannot_carry_provider_credentials(worker,tmp_path,secret):
    context=research_context();context['history'][0]['description']='历史 '+secret
    result=run_research(worker,tmp_path,research_context=context)
    assert result['status']=='FAILED' and result['code']=='invalid_configuration'
    assert result['research_binding'] is None
    assert worker._test_search_sessions==[]
    assert secret not in json.dumps(result)


@pytest.mark.parametrize('credential_name,secret',[
    ('api_key','synthetic-provider-"quoted-secret'),
    ('search_api_key',r'synthetic-search-\escaped-secret'),
])
def test_research_context_rejects_json_escaped_actual_credentials_before_start(
        worker,tmp_path,credential_name,secret):
    context=research_context();context['history'][0]['description']='历史 '+secret
    cancellations=[]
    arguments=dict(codex_binary=executable(tmp_path),python_binary=sys.executable,
        api_key='synthetic-provider-secret',search_api_key='synthetic-search-secret',
        model='test-model',research_context=context,cancelled=lambda:cancellations.append(True))
    arguments[credential_name]=secret
    result=worker.run_public_research_mission('研究公开需求。',**arguments)
    assert result['status']=='FAILED' and result['code']=='invalid_configuration'
    assert result['research_binding'] is None
    assert worker._test_search_sessions==[] and cancellations==[]
    assert secret not in json.dumps(result)


def test_research_context_rejects_actual_credential_encoded_by_url_normalization_before_start(
        worker,tmp_path):
    secret='synthetic-provider-"quoted-secret'
    context=research_context()
    context['history'][0]['source_urls']=['https://example.com/history/'+secret]
    cancellations=[]
    result=worker.run_public_research_mission('研究公开需求。',
        codex_binary=executable(tmp_path),python_binary=sys.executable,
        api_key=secret,search_api_key='synthetic-search-secret',model='test-model',
        research_context=context,cancelled=lambda:cancellations.append(True))
    assert result['status']=='FAILED' and result['code']=='invalid_configuration'
    assert result['research_binding'] is None
    assert worker._test_search_sessions==[] and cancellations==[]
    assert secret not in json.dumps(result)


def test_research_context_v1_keeps_original_description_limit(worker,tmp_path):
    result=run_research(worker,tmp_path,description='字'*4001,research_context=research_context())
    assert result['code']=='invalid_configuration' and worker._test_search_sessions==[]


def test_context_v2_delivers_full_8000_character_multiline_profile_to_real_process(
        worker,tmp_path):
    from pilot.research_context import compile_research_context
    from tests.test_research_context import projected_v2
    seller='甲\n'+'乙'*7998
    context=projected_v2(seller_description=seller)
    compiled=compile_research_context(context)
    capture=tmp_path/'long-v2-context.json'
    extra=(f"open({str(capture)!r},'w').write(json.dumps(dict(prompt=sys.stdin.read())))\n")
    event=citation_read_event(read_event())
    result=run_research(worker,tmp_path,[search_event(),event,*citation_final_events(event)],
        description=seller,research_context=context,extra=extra)
    data=json.loads(capture.read_text())
    assert result['status']=='COMPLETED'
    assert result['research_binding']==compiled['binding']
    assert data['prompt'].startswith('HOST_RESEARCH_CONTEXT_JSON')
    assert compiled['context_json'] in data['prompt']
    assert json.loads(data['prompt'].split(':\n', 1)[1])['seller_description'] == seller
    assert len(seller)==8000 and seller.endswith('乙')


def test_contextual_final_message_allows_512_kib_but_legacy_keeps_16000(worker,tmp_path):
    from tests.test_research_context import projected_v2
    large='x'*17000
    event=citation_read_event(read_event())
    contextual=run_research(worker,tmp_path,[search_event(),event,*final_events_with(large)],
                            research_context=projected_v2())
    legacy=run_research(worker,tmp_path,[search_event(),read_event(),*final_events_with(large)])
    assert contextual['status']=='FAILED' and contextual['code']=='research_selection_invalid'
    assert contextual['summary']==''
    assert legacy['status']=='FAILED' and legacy['code']=='invalid_runtime_output'


def test_contextual_invalid_citation_final_fails_closed_without_echo_or_v1_fallback(worker,tmp_path):
    event=citation_read_event(read_event())
    bad=json.dumps(dict(schema_version='research-page-selection-v1',summary='PRIVATE_BAD_FINAL',
        pages=[]),ensure_ascii=False)
    result=run_research(worker,tmp_path,[search_event(),event,*final_events_with(bad)],
                        research_context=research_context())
    assert result['status']=='FAILED' and result['code']=='research_selection_invalid'
    assert result['summary']=='' and 'PRIVATE_BAD_FINAL' not in json.dumps(result)


def test_contextual_unbounded_numeric_quote_ref_returns_fixed_failure(worker,tmp_path):
    event=citation_read_event(read_event())
    evidence=event['item']['result']['structured_content']['evidence']
    marker='9'*5000
    bad=json.dumps(dict(schema_version='research-citation-choice-v1',summary='PRIVATE_LONG_REF',
        pages=[dict(url=evidence['url'],content_sha256=evidence['content_sha256'],
                    decision='ASSESS',reason='POSSIBLE_DEMAND',quote_ref='q'+marker)]),
        ensure_ascii=False)
    result=run_research(worker,tmp_path,[search_event(),event,*final_events_with(bad)],
                        research_context=research_context())
    assert result['status']=='FAILED' and result['code']=='research_selection_invalid'
    assert result['summary']=='' and 'PRIVATE_LONG_REF' not in json.dumps(result)
    assert marker not in json.dumps(result)


@pytest.mark.parametrize('change',['missing_original','changed_projection'])
def test_contextual_read_requires_original_meta_and_exact_projection(worker,tmp_path,change):
    event=citation_read_event(read_event())
    if change=='missing_original':
        event['item']['result'].pop('_meta')
    else:
        event['item']['result']['structured_content']['evidence']['text_fragments'][0]['text']='伪造'
    result=run_research(worker,tmp_path,[search_event(),event,*final_events()],
                        research_context=research_context())
    assert result['status']=='FAILED' and result['code']=='invalid_runtime_output'
    assert result['reads']==[]


def test_context_v2_long_description_requires_exact_verified_seller_profile(worker,tmp_path):
    from tests.test_research_context import projected_v2
    context=projected_v2(seller_description='甲\n'+'乙'*7998)
    result=run_research(worker,tmp_path,description='丙'*8000,research_context=context)
    assert result['code']=='invalid_configuration' and worker._test_search_sessions==[]


def test_context_v2_non_string_description_fails_without_start_or_exception(worker,tmp_path):
    from tests.test_research_context import projected_v2
    result=run_research(worker,tmp_path,description=None,research_context=projected_v2())
    assert result['status']=='FAILED' and result['code']=='invalid_configuration'
    assert result['research_binding'] is None and worker._test_search_sessions==[]


def test_research_rule_failure_never_starts_or_downgrades(worker,tmp_path,monkeypatch):
    import pilot.research_context as module
    def unavailable(_):raise module.ResearchContextError('research_rules_unavailable')
    monkeypatch.setattr(module,'compile_research_context',unavailable)
    result=run_research(worker,tmp_path,research_context=research_context())
    assert result['code']=='research_rules_unavailable' and result['research_binding'] is None
    assert worker._test_search_sessions==[]


def test_research_binding_survives_cancel_without_authorizing_a_lead(worker,tmp_path):
    result=run_research(worker,tmp_path,research_context=research_context(),cancelled=lambda:True)
    assert result['status']=='CANCELLED' and result['reads']==[]
    assert result['research_binding']['strategy_version_id']==research_context()['strategy_version_id']
    assert 'grade' not in result and 'decision' not in result


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

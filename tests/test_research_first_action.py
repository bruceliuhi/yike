"""First action is a model contract, not a retry or extra source allowance."""
import copy
import json
from time import monotonic

import httpx
import pytest

from pilot.responses_bridge import BridgeError, ResponsesBridge
from pilot.research_effect_contract import effect_input, effect_result
from tests.test_research_effect_contract import binding
from tests.test_responses_bridge import KEY, request, real_sse, sse

TOOLS=(("mcp__yike_public","read_public_page"),("mcp__yike_public","search_public_web"))

def payload():
    return {'input':[{'role':'user','content':'Find a real enterprise AI development request.'}],
      'stream':True,'tool_choice':'auto','text':{'format':{'type':'json_schema','name':'choice',
        'schema':{'type':'object','properties':{'pages':{'type':'array','items':{'type':'string'}}}}}},
      'tools':[{'type':'namespace','name':'mcp__yike_public','tools':[
        {'type':'function','name':name,'parameters':{'type':'object'}} for _,name in TOOLS]}]}

def test_first_research_action_required_then_final_answer_allowed_with_same_budget():
    forwarded, admitted=[],[]
    def dispatch(kind, value, deadline, perform):
        clean,_=effect_input(kind,value,binding())
        admitted.append(copy.deepcopy(clean))
        return effect_result(kind,clean,perform(deadline))
    def provider(req):
        value=json.loads(req.content); forwarded.append(value)
        body=real_sse(value['tools'][0]['name']) if len(forwarded)==1 else sse(
          ('response.completed',{'type':'response.completed','response':{'status':'completed','output':[]}}))
        return httpx.Response(200,headers={'content-type':'text/event-stream'},content=body)
    original=payload()
    with ResponsesBridge(api_key=KEY,model='test-model',max_requests=2,deadline=monotonic()+10,
        allowed_tools=TOOLS,require_initial_tool=True,effect_dispatcher=dispatch,
        transport=httpx.MockTransport(provider)) as bridge:
        assert request(bridge,original).status_code==200
        assert request(bridge,original).status_code==200
        assert request(bridge,original).status_code==429
        assert len(bridge.records)==2
    assert [p['tool_choice'] for p in forwarded]==['required','auto']
    assert admitted==forwarded
    assert all(p['text']==original['text'] and p['input']==original['input'] for p in forwarded)
    assert original==payload()

def test_first_action_without_allowed_tools_is_rejected_before_admission():
    calls=[]
    with ResponsesBridge(api_key=KEY,model='test-model',max_requests=1,deadline=monotonic()+10,
        allowed_tools=TOOLS,require_initial_tool=True,
        transport=httpx.MockTransport(lambda req: calls.append(req))) as bridge:
        assert request(bridge,payload()|{'tools':[]}).status_code==400
        assert not calls and not bridge.records

def test_ordinary_bridge_does_not_force_a_tool():
    observed=[]
    def provider(req):
        observed.append(json.loads(req.content))
        return httpx.Response(200,headers={'content-type':'text/event-stream'},content=sse(
          ('response.completed',{'type':'response.completed','response':{'status':'completed','output':[]}})))
    with ResponsesBridge(api_key=KEY,model='test-model',max_requests=1,deadline=monotonic()+10,
        allowed_tools=TOOLS,transport=httpx.MockTransport(provider)) as bridge:
        assert request(bridge,payload()).status_code==200
    assert observed[0]['tool_choice']=='auto'

@pytest.mark.parametrize('invalid',[1,None,'true'])
def test_initial_tool_setting_is_a_host_boolean(invalid):
    with pytest.raises(BridgeError,match='invalid_config'):
        ResponsesBridge(api_key=KEY,model='test-model',max_requests=1,deadline=monotonic()+10,
          allowed_tools=TOOLS,require_initial_tool=invalid)

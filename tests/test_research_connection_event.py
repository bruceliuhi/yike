"""Pure event validation; does not require a POSIX Codex executable or real I/O."""
from pilot.codex_research_worker import _ReadEvents


def test_known_connection_failure_event_is_not_original_evidence():
    entry='https://example.com/buyer'
    events=_ReadEvents(search_enabled=True,entry_urls=[entry])
    event={'type':'item.completed','item':{'id':'read-1','type':'mcp_tool_call',
        'server':'yike_public','tool':'read_public_page','arguments':{'url':entry},
        'status':'completed','result':{'structured_content':{
            'status':'FAILED','code':'connection_unavailable','replayed':False}}}}
    events.accept(event)
    assert events.reads==[]
    assert events.failures==[{'url':entry,'code':'connection_unavailable'}]

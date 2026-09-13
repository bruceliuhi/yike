from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('code',['broker_stop_unknown','broker_stream_unknown'])
@pytest.mark.parametrize('task_status',['CANCELED','RUNNING'])
@pytest.mark.parametrize('dynamic',[False,True])
def test_runtime_projects_broker_uncertainty_before_cancellation(monkeypatch,code,task_status,dynamic):
    from pilot import research_runtime as module
    service=object.__new__(module.ResearchRuntimeService)
    now=datetime.now(timezone.utc)
    cursor=SimpleNamespace(execute=lambda *a: None,fetchone=lambda: (now,))
    service.database=SimpleNamespace(connect=lambda: nullcontext(SimpleNamespace(cursor=lambda: nullcontext(cursor))))
    service._identity=lambda *a: ('tenant',(task_status,'run',task_status))
    service._coordinator=lambda *a: ('run',1,None,None,'STOPPED',code)
    service._usage=lambda *a: ({key:{'pending':0,'unknown':0,'failed':0} for key in ('sourceReads','modelCalls')},0)
    monkeypatch.setattr(module,'source_from_snapshot',lambda _: SimpleNamespace(version=1,scope='test',label='test'))
    state=dict(source_event=None,receipt=None,reviews=[],items=[],skipped=0,strategy_snapshot={})
    if dynamic:
        from pilot import dynamic_research_runtime as dynamic_module
        runtime=object.__new__(dynamic_module.DynamicResearchRuntimeService)
        runtime.fixed=service
        runtime.database=service.database
        runtime.execution=SimpleNamespace(get_task=lambda *a: {})
        runtime._expire_lease=lambda *a: None
        runtime._effect_stop=lambda *a: None
        rows=iter([[({},'PUBLIC_WEB','PUBLIC_ANONYMOUS',None,None)],[],[]])
        cursor.fetchall=lambda: next(rows)
        monkeypatch.setattr(dynamic_module,'dynamic_research_snapshot',lambda _: True)
        result=runtime.status(SimpleNamespace(user_id='user'),'00000000-0000-4000-8000-000000000001')
    else:
        result=service._dto(SimpleNamespace(user_id='user'),'task',state=state)
    assert result['phase']=='STOPPED'
    assert result['stopCode']==code
    assert result['usage']['resourceCloseout']['state']=='UNCERTAIN'
    assert result['newActionsBlocked'] and not result['canAdvance']

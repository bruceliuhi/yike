import importlib
from pathlib import Path
import tempfile
from time import time
import threading
import pytest


def test_client_private_service_roundtrip_and_identity_binding():
    client_module=importlib.import_module('pilot.research_broker_client')
    service_module=importlib.import_module('pilot.research_broker_service')
    broker_module=importlib.import_module('pilot.research_container_broker')
    identity=dict(tenant_id='00000000-0000-4000-8000-000000000001',
        task_id='00000000-0000-4000-8000-000000000002',
        run_id='00000000-0000-4000-8000-000000000003',generation=1)
    key=broker_module.task_key(identity)
    received=threading.Event()
    class Broker:
        def create(self, value, *, expires_at):
            assert value==identity
            return {'key':key,'status':'CREATED'}
        def status(self, value):
            return {'key':key,'status':'RUNNING'}
        def stop(self, value):
            return {'key':key,'status':'STOPPED'}
        def execute(self, value, manifest, *, emit):
            emit(b'')
            emit(b'{"synthetic":true}\n')
            assert received.wait(2), 'client must receive progress before execution completes'
            return {'key':key,'status':'STOPPED','code':None}
    with tempfile.TemporaryDirectory(prefix='yb-',dir='/tmp') as directory:
        path=str(Path(directory)/'control.sock')
        with service_module.BrokerServer(Broker(),path):
            client=client_module.BrokerClient(path)
            assert client.create(identity,expires_at=time()+10)['status']=='CREATED'
            assert client.status(identity)['status']=='RUNNING'
            assert client.stop(identity)['status']=='STOPPED'
            stream=client.events(identity,{})
            assert next(stream)=={'type':'heartbeat'}
            first=next(stream)
            received.set()
            frames=[first,*stream]
            assert frames[0]=={'type':'chunk','data':b'{"synthetic":true}\n'}
            assert frames[1]['value']['key']==key


@pytest.mark.parametrize('change', [{'key':'f'*64}, {'status':'COMPLETED'}, {'extra':True}])
def test_client_rejects_cross_task_or_unexpected_results(change):
    module=importlib.import_module('pilot.research_broker_client')
    identity=dict(tenant_id='00000000-0000-4000-8000-000000000001',
        task_id='00000000-0000-4000-8000-000000000002',
        run_id='00000000-0000-4000-8000-000000000003',generation=1)
    client=object.__new__(module.BrokerClient)
    with pytest.raises(ValueError,match='invalid_broker_result'):
        client._result(identity,{'key':module.task_key(identity),'status':'STOPPED'} | change)


def test_stream_timeout_covers_bounded_terminal_cleanup():
    module=importlib.import_module('pilot.research_broker_client')
    client=object.__new__(module.BrokerClient)
    client.path='/unused.sock'
    with client._client(streaming=True) as transport:
        # CLI wait 2 + inspect/kill/inspect 6 + thread joins .6, with transport margin.
        assert transport.timeout.read >= 11

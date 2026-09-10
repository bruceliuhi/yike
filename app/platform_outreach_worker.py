"""Child half of the private loopback bridge; never reads stdin or logs context."""
from __future__ import annotations
import asyncio, json, os, socket, sys, threading
from pathlib import Path

# The governed runtime is cwd; this bridge remains imported from the product tree.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def _wire(value): return (json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode()
async def _run(conn):
    from app.windows_platform_outreach import _decode, _internal_operation
    conn.setblocking(False)
    loop=asyncio.get_running_loop(); owner=asyncio.current_task()
    context_ready=loop.create_future(); operation_ready=loop.create_future()
    phase={'value':'CONTEXT'}
    cancelled=threading.Event()
    async def read_frames():
        buffer=b''; received=0
        try:
            while True:
                data=await loop.sock_recv(conn,131073-len(buffer))
                if not data: raise ValueError()
                buffer+=data; received+=len(data)
                if len(buffer)>131072 or received>2*131072: raise ValueError()
                while b'\n' in buffer:
                    raw,buffer=buffer.split(b'\n',1); value=_decode(raw)
                    if not isinstance(value,dict): raise ValueError()
                    if phase['value']=='CONTEXT' and set(value)=={'context'} and isinstance(value['context'],dict):
                        phase['value']='SETUP'; context_ready.set_result(value['context'])
                    elif phase['value']=='OPERATION' and set(value)=={'operation'}:
                        operation=_internal_operation(value['operation'])
                        phase['value']='EXECUTING'; operation_ready.set_result(operation)
                    else: raise ValueError()
        except asyncio.CancelledError: raise
        except Exception:
            cancelled.set(); owner.cancel()
    async def send(value, *, read_result=False):
        data=_wire(value)
        if len(data)>(512*1024 if read_result else 131072): raise ValueError()
        await loop.sock_sendall(conn,data)
    reader=asyncio.create_task(read_frames())
    try:
        context=await context_ready
        from app.platform_outreach_runtime import open_xhs_comment_channel
        async with open_xhs_comment_channel(context,cancelled=cancelled.is_set) as channel:
            observation=await channel.check(context)
            phase['value']='OPERATION'
            await send({'state':'READY','observation':observation})
            operation=await operation_ready
            if set(operation)=={'readReplies'}:
                read=operation['readReplies']
                outcome=await channel.read_replies(context,read['rootCommentId'],read['claimedAt'])
                await send({'state':'RESULT','outcome':outcome},read_result=True)
            else:
                outcome=await channel.execute(context,operation)
                await send({'state':'RESULT','outcome':outcome})
    finally:
        cancelled.set(); reader.cancel()
        await asyncio.gather(reader,return_exceptions=True)

def main():
    token=os.environ.pop('YIKE_OUTREACH_TOKEN'); port=int(os.environ.pop('YIKE_OUTREACH_PORT'))
    with socket.create_connection(('127.0.0.1',port),timeout=10) as conn:
        conn.sendall(_wire({'token':token})); asyncio.run(_run(conn))
    return 0
if __name__=='__main__': raise SystemExit(main())

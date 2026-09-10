"""Child half of the private loopback bridge; never reads stdin or logs context."""
from __future__ import annotations
import asyncio, json, os, socket, sys, threading, time
from pathlib import Path

# The governed runtime is cwd; this bridge remains imported from the product tree.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def _wire(value): return (json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode()
def _pairs(items):
    value = {}
    for key, item in items:
        if key in value: raise ValueError()
        value[key] = item
    return value

def _read(conn):
    data=b''
    while b'\n' not in data:
        part=conn.recv(131073-len(data))
        if not part: raise ValueError()
        data+=part
        if len(data)>131072: raise ValueError()
    raw,extra=data.split(b'\n',1)
    if extra: raise ValueError()
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))

async def _run(conn):
    first=_read(conn)
    if not isinstance(first,dict) or set(first)!={'context'} or not isinstance(first['context'],dict): raise ValueError()
    cancelled=threading.Event()
    from app.platform_outreach_runtime import open_xhs_comment_channel
    async with open_xhs_comment_channel(first['context'],cancelled=cancelled.is_set) as channel:
        # The context manager performs the one authoritative check before yield.
        observation={'status':'AVAILABLE'}
        conn.sendall(_wire({'state':'READY','observation':observation}))
        operation=_read(conn)
        if not isinstance(operation,dict) or set(operation)!={'operation'}: raise ValueError()
        # After operation delivery, EOF is a cancellation signal even while a
        # browser await is pending; MSG_PEEK leaves protocol bytes untouched.
        def watch_eof():
            conn.setblocking(False)
            try:
                while not cancelled.is_set():
                    try:
                        if conn.recv(1, socket.MSG_PEEK) == b'': cancelled.set(); return
                    except BlockingIOError: pass
                    except OSError: cancelled.set(); return
                    time.sleep(.01)
            finally: conn.setblocking(True)
        watcher=threading.Thread(target=watch_eof,daemon=True); watcher.start()
        outcome=await channel.execute(first['context'],operation['operation'])
        cancelled.set(); watcher.join(.2)
        conn.sendall(_wire({'state':'RESULT','outcome':outcome}))

def main():
    token=os.environ.pop('YIKE_OUTREACH_TOKEN'); port=int(os.environ.pop('YIKE_OUTREACH_PORT'))
    with socket.create_connection(('127.0.0.1',port),timeout=10) as conn:
        conn.sendall(_wire({'token':token})); asyncio.run(_run(conn))
    return 0
if __name__=='__main__': raise SystemExit(main())

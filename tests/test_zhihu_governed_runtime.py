"""Isolated synthetic checks for a freshly replayed governed Zhihu runtime."""
from pathlib import Path
import os
import subprocess
import textwrap

import pytest


def test_governed_zhihu_runtime_in_isolated_interpreter():
    source_value=os.environ.get("YIKE_ZHIHU_RUNTIME_SOURCE")
    python_value=os.environ.get("YIKE_ZHIHU_RUNTIME_PYTHON")
    if not source_value or not python_value:
        pytest.skip("set replayed runtime source and its Python interpreter")
    source=Path(source_value).resolve(); python=Path(python_value).absolute()
    script=textwrap.dedent(r'''
        import asyncio,importlib,os,sys
        from pathlib import Path
        from types import SimpleNamespace
        source=Path(os.environ['YIKE_ZHIHU_RUNTIME_SOURCE']).resolve()
        sys.path.insert(0,str(source)); os.chdir(source)
        client_module=importlib.import_module('media_platform.zhihu.client')
        core_module=importlib.import_module('media_platform.zhihu.core')
        config=importlib.import_module('config'); runtime=importlib.import_module('tools.yike_runtime')
        class Response:
            def __init__(self,status=200,body=b'{}'): self.status=status; self.raw=body
            async def body(self): return self.raw
            async def dispose(self): pass
        class Request:
            def __init__(self,responses): self.responses=list(responses); self.calls=[]
            async def fetch(self,url,**kwargs): self.calls.append((url,kwargs)); return self.responses.pop(0)
        def make(responses):
            request=Request(responses); value=client_module.ZhiHuClient(headers={},playwright_page=SimpleNamespace(request=request),cookie_dict={})
            async def headers(_url): return {}
            value._pre_headers=headers
            return value,request
        for status,error in ((401,runtime.YikePlatformAuthRequired),(403,runtime.YikePlatformPermissionDenied),
                (429,runtime.YikePlatformRateLimited),(404,runtime.YikePlatformResponseChanged),(500,runtime.YikeNetworkFailed)):
            value,request=make([Response(status)])
            try: asyncio.run(value.get('/api/v4/me')); raise AssertionError(status)
            except error: pass
            assert request.calls[0][0]=='https://www.zhihu.com/api/v4/me'
            assert request.calls[0][1]['max_redirects']==0 and request.calls[0][1]['timeout']==10000
        value,_=make([Response(401),Response(200,b'{"name":"masked"}')])
        assert asyncio.run(value.pong()) is False
        try: asyncio.run(value.pong()); raise AssertionError('unknown self shape')
        except runtime.YikePlatformResponseChanged: pass
        config.ENABLE_GET_SUB_COMMENTS=True
        content=SimpleNamespace(content_id='1',content_type='answer')
        value,_=make([])
        value._extractor=SimpleNamespace(extract_offset=lambda p:p.get('next',''),
            extract_comments=lambda _c,data:[SimpleNamespace(comment_id=str(i['id']),sub_comment_count=i.get('children',0)) for i in data])
        value.get_root_comments=lambda *_a,**_k: asyncio.sleep(0,result={'data':[{'id':1,'children':1}],'paging':{'is_end':True,'next':''}})
        value.get_child_comments=lambda *_a,**_k: asyncio.sleep(0,result={'data':[{'id':2}],'paging':{'is_end':True,'next':''}})
        result=asyncio.run(value.get_note_all_comments(content,max_count=2))
        assert [item.comment_id for item in result]==['1','2']
        value.get_root_comments=lambda *_a,**_k: asyncio.sleep(0,result={'data':[],'paging':{'is_end':False,'next':''}})
        try: asyncio.run(value.get_note_all_comments(content,max_count=1)); raise AssertionError('stalled cursor')
        except runtime.YikePlatformResponseChanged: pass
        class Chromium:
            async def launch_persistent_context(self,**kwargs): self.kwargs=kwargs; return object()
        profile=source.parent/'profile'; profile.mkdir(exist_ok=True); os.environ['YIKE_PROFILE_PATH']=str(profile)
        chromium=Chromium(); asyncio.run(core_module.ZhihuCrawler().launch_browser(chromium,None,None,headless=False))
        assert chromium.kwargs=={'user_data_dir':str(profile),'accept_downloads':False,'headless':False,'viewport':{'width':1920,'height':1080}}
        core=(source/'media_platform/zhihu/core.py').read_text(); store=(source/'store/zhihu/__init__.py').read_text()
        assert 'add_init_script' not in core and 'channel="chrome"' not in core
        assert 'get_creators_and_notes()' not in core and 'get_specified_notes()' not in core
        assert 'zhihu content:' not in store and 'content comment:' not in store
        login=(source/'media_platform/zhihu/login.py').read_text()
        assert 'show_qrcode' not in login and 'add_cookies' not in login
        value,request=make([Response(200,'{"uid":"１２３"}'.encode())])
        try: asyncio.run(value.pong()); raise AssertionError('non ASCII identity')
        except runtime.YikePlatformResponseChanged: pass
        value,request=make([Response()])
        try: asyncio.run(value.request('POST','https://www.zhihu.com/api/v4/me')); raise AssertionError('write request')
        except runtime.YikePlatformResponseChanged: pass
        assert not request.calls
        value,request=make([Response()])
        asyncio.run(value.request('GET','https://www.zhihu.com/api/v4/me',headers={'Cookie':'stale'}))
        assert all(key.lower()!='cookie' for key in request.calls[0][1]['headers'])
        main=importlib.import_module('main'); import tempfile,json
        output=Path(tempfile.mkdtemp()); data=output/'zhihu/jsonl'; data.mkdir(parents=True)
        config.PLATFORM='zhihu'; config.SAVE_DATA_PATH=str(output)
        (data/'search_contents_x.jsonl').write_text(json.dumps({'content_text':'正文'})+'\n')
        assert main._has_candidate_output() is True
        (data/'search_contents_x.jsonl').write_text(json.dumps({'content_text':''})+'\n')
        assert main._has_candidate_output() is False
        (data/'search_comments_x.jsonl').write_text('{}\n'); assert main._has_candidate_output() is True
        class Context:
            async def new_page(self): return SimpleNamespace(goto=lambda *_a,**_k: asyncio.sleep(0))
            async def close(self): raise RuntimeError('synthetic close failure')
        crawler=core_module.ZhihuCrawler()
        async def launch(*_a,**_k): return Context()
        async def create(*_a,**_k): return SimpleNamespace(pong=lambda:asyncio.sleep(0,result=True))
        crawler.launch_browser=launch; crawler.create_zhihu_client=create; crawler.search=lambda:asyncio.sleep(0)
        class Playwright:
            chromium=object()
            async def __aenter__(self): return self
            async def __aexit__(self,*_a): pass
        core_module.async_playwright=lambda:Playwright()
        config.CRAWLER_TYPE='search'; config.ENABLE_IP_PROXY=False; config.ENABLE_CDP_MODE=False
        config.KEYWORDS='词'; config.CRAWLER_MAX_NOTES_COUNT=1; config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES=1
        try: asyncio.run(crawler.start()); raise AssertionError('close failure reported success')
        except RuntimeError as error: assert str(error)=='synthetic close failure'
    ''')
    result=subprocess.run([str(python),"-c",script],cwd=source,env={
        "PATH":os.environ.get("PATH",""),"HOME":os.environ.get("HOME",""),
        "YIKE_ZHIHU_RUNTIME_SOURCE":str(source)},
        capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr

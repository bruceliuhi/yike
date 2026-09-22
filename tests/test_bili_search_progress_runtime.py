"""Controlled source/host tests; not live platform or Windows evidence."""
import asyncio
import ast
from contextlib import nullcontext
from copy import deepcopy
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tests.test_windows_collection_host import request, encoded, run
from tests.test_bili_link_runtime import source


def progress():
    return dict(schema_version='native-search-progress-v1', adapter_version='bili-search-items-v1',
        query='设备', revision=0, base_batch_request_id=None,
        cursor=dict(page=1, consumed_ids=[], refresh_next=False))


def adapter():
    return importlib.import_module('app.bili_search_progress')


def fixture(tmp_path, ids=None, pages=2, fail=None):
    calls = []
    ids = list(range(1,21)) if ids is None else ids
    class Changed(Exception): pass
    class Crawler:
        async def search(self): pytest.fail('legacy search must not run')
        async def get_video_info_task(self, aid, **kwargs):
            calls.append(('detail', aid))
            return None if fail == 'detail' else {'View': {'aid':aid}}
        async def batch_get_video_comments(self, aids):
            calls.append(('comments', aids))
            if fail == 'comments': raise Changed()
        async def get_bilibili_video(self, *args): pass
    async def search(**kwargs):
        calls.append(('search', kwargs))
        return dict(numPages=pages, result=[{'aid': aid} for aid in ids])
    async def store(*args): pass
    module = SimpleNamespace(BilibiliCrawler=Crawler,
        config=SimpleNamespace(KEYWORDS='设备', CRAWLER_MAX_NOTES_COUNT=5, MAX_CONCURRENCY_NUM=1, SAVE_DATA_PATH=str(tmp_path)),
        SearchOrderType=SimpleNamespace(DEFAULT='default'),
        source_keyword_var=SimpleNamespace(set=lambda _: None),
        bilibili_store=SimpleNamespace(update_bilibili_video=store, update_up_info=store))
    crawler = Crawler()
    crawler.bili_client = SimpleNamespace(search_video_by_keyword=search)
    return module, crawler, Changed, calls


def collect(tmp_path, state, **kwargs):
    module, crawler, error, calls = fixture(tmp_path, **kwargs)
    original = module.BilibiliCrawler.search
    with adapter().install_bili_search_progress(module, state, error):
        asyncio.run(crawler.search())
    assert module.BilibiliCrawler.search is original
    delta = json.loads((tmp_path / adapter().MARKER).read_text())
    return delta, calls


def test_page_remaining_items_resume_without_skipping(tmp_path):
    state = progress()
    first, calls = collect(tmp_path, state)
    assert first['processed_ids'] == ['1','2','3','4','5']
    assert first['after'] == dict(page=1, consumed_ids=first['processed_ids'], refresh_next=True)
    assert len([x for x in calls if x[0] == 'search']) == 1
    state['cursor'] = first['after']
    refreshed, _ = collect(tmp_path, state)
    assert refreshed['after'] == first['after'] | {'refresh_next':False}
    state['cursor'] = refreshed['after']
    second, calls = collect(tmp_path, state)
    assert second['processed_ids'] == ['6','7','8','9','10']
    assert calls[0][1]['page'] == 1 and calls[0][1]['page_size'] == 20
    assert second['comments_scope'] == 'BOUNDED_SAMPLE'


@pytest.mark.parametrize('ids,pages,expected', [([],0,1),([1,2],1,1),([1,2],2,2)])
def test_empty_last_and_complete_page(tmp_path, ids, pages, expected):
    delta, _ = collect(tmp_path, progress(), ids=ids, pages=pages)
    assert delta['after'] == dict(page=expected, consumed_ids=[], refresh_next=True)


@pytest.mark.parametrize('kwargs', [dict(ids=[1,1]), dict(ids=[True]), dict(pages=True),
    dict(ids=[],pages=2),dict(pages=0),dict(fail='detail'),dict(fail='comments')])
def test_invalid_or_unfinished_source_has_no_checkpoint(tmp_path, kwargs):
    module, crawler, error, _ = fixture(tmp_path, **kwargs)
    with adapter().install_bili_search_progress(module, progress(), error):
        with pytest.raises((ValueError,error)):
            asyncio.run(crawler.search())
    assert not (tmp_path / adapter().MARKER).exists()


def test_host_negotiated_delta_roundtrip_and_missing_rejected(tmp_path, monkeypatch):
    payload = request(tmp_path) | dict(expected_account_public_id='123', native_progress=progress())
    payload['query'] = '设备'
    delta, _ = collect(tmp_path, progress(), ids=[], pages=0)
    calls = []
    def driver(**kwargs):
        calls.append(kwargs)
        return dict(state='COLLECTED', records=[], query='设备', collector_version='test',native_progress=delta)
    response, _ = run(monkeypatch,encoded(payload),driver)
    assert response['state'] == 'COLLECTED' and response['native_progress'] == delta
    assert calls[0]['native_progress'] == progress()
    response, _ = run(monkeypatch,encoded(payload),lambda **_: dict(state='COLLECTED',records=[],query='设备',collector_version='test'))
    assert response['error_code'] == 'SOURCE_HOST_FAILED'


@pytest.mark.parametrize('change', ['null','platform','account','query','extra'])
def test_invalid_host_input_never_starts_source(tmp_path, monkeypatch, change):
    payload = request(tmp_path) | dict(query='设备',expected_account_public_id='123',native_progress=progress())
    if change == 'null': payload['native_progress'] = None
    if change == 'platform': payload['platform'] = 'DOUYIN'
    if change == 'account': del payload['expected_account_public_id']
    if change == 'query': payload['native_progress']['query'] = 'other'
    if change == 'extra': payload['native_progress']['cursor']['other'] = True
    response, _ = run(monkeypatch,encoded(payload),lambda **_: pytest.fail('must not run'))
    assert response['error_code'] == 'SOURCE_HOST_INPUT_INVALID'


def test_portable_inventory_contains_full_progress_import_closure():
    from app.windows_portable_inventory import HOST_FILES
    assert {'app/bili_search_progress.py','pilot/native_search_cursor.py','pilot/native_search_progress.py'} <= set(HOST_FILES)


def test_portable_host_imports_progress_without_repository_fallback(tmp_path):
    from app.windows_portable_inventory import HOST_FILES
    root=Path(__file__).resolve().parents[1]
    for name in HOST_FILES:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/name,target)
    script='import sys;sys.path.insert(0,sys.argv[1]);import app.windows_collection_host,app.platform_collection_worker,pilot.native_search_progress;assert all(str(m.__file__).startswith(sys.argv[1]) for m in (app.windows_collection_host,app.platform_collection_worker,pilot.native_search_progress))'
    result=subprocess.run([sys.executable,'-I','-B','-c',script,str(tmp_path)],cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('failed', [False,True])
def test_governed_core_detail_and_comment_functions_with_account_guard(source,tmp_path,monkeypatch,failed):
    """Execute actual pinned+patched method bodies through the new adapter."""
    from app import platform_collection_worker as worker
    module,crawler,error,calls=fixture(tmp_path,ids=[1,2],pages=1)
    module.config.ENABLE_GET_COMMENTS=True
    module.config.ENABLE_GET_SUB_COMMENTS=True
    module.config.CRAWLER_MAX_SLEEP_SEC=0
    module.config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES=2
    async def stored(*args): pass
    module.bilibili_store.batch_update_bilibili_video_comments=stored
    tree=ast.parse((source/'media_platform/bilibili/core.py').read_text())
    nodes=next(n.body for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='BilibiliCrawler')
    names={'batch_get_video_comments','get_comments','get_video_info_task'}
    definitions=[n for n in nodes if isinstance(n,ast.AsyncFunctionDef) and n.name in names]
    namespace=dict(vars(module)) | dict(asyncio=asyncio,DataFetchError=error,
        utils=SimpleNamespace(logger=SimpleNamespace(info=lambda *_:None,error=lambda *_:None)))
    # Future annotations are needed for upstream type imports; function bodies unchanged.
    exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*definitions],type_ignores=[])),'<governed-bili-methods>','exec'),namespace)
    for name in names:setattr(module.BilibiliCrawler,name,namespace[name])
    class Client:
        def __init__(self,page):self.playwright_page=page
        async def request(self,kind,aid=None):
            calls.append((kind,aid))
            if kind=='search':return dict(result=[{'aid':1},{'aid':2}],numPages=1)
            if kind=='detail':return {'View':{'aid':aid}}
            if failed:raise error()
        async def search_video_by_keyword(self,**kwargs):return await self.request('search')
        async def get_video_info(self,aid,**kwargs):return await self.request('detail',aid)
        async def get_video_all_comments(self,video_id,**kwargs):
            assert kwargs['max_count']==2 and kwargs['is_fetch_sub_comments'] is True
            return await self.request('comments',video_id)
    crawler.context_page=object();crawler.bili_client=Client(crawler.context_page)
    async def own(_):return '123'
    monkeypatch.setattr(worker,'_bilibili_self_account',own)
    with adapter().install_bili_search_progress(module,progress(),error),worker.install_video_account_guard(module.BilibiliCrawler,Client,error,'123','BILIBILI'):
        if failed:
            with pytest.raises(error):asyncio.run(crawler.search())
        else:asyncio.run(crawler.search())
    assert (tmp_path/adapter().MARKER).exists() is not failed
    assert [item for item in calls if item[0]=='detail']==[('detail',1),('detail',2)]


@pytest.mark.parametrize('outcome',['success','missing','cancel','bad_delta'])
def test_source_driver_progress_uses_private_input_and_only_stopped_success(tmp_path,monkeypatch,outcome):
    from app import windows_source_driver as driver
    monkeypatch.setattr(driver,'sys',SimpleNamespace(platform='win32'))
    monkeypatch.setattr(driver,'_exclusive_paths',lambda _:nullcontext())
    monkeypatch.setattr(driver,'verify_installed_runtime',lambda _:tmp_path/'python.exe')
    monkeypatch.setattr(driver,'verify_private_tree',lambda _:None)
    monkeypatch.setattr(driver,'verify_browser_profile_tree',lambda _:None)
    def create(path):path.mkdir(parents=True);return path
    monkeypatch.setattr(driver,'create_private_directory',create)
    output=tmp_path/'output'
    def supervise(command,**kwargs):
        assert json.loads(kwargs['env']['YIKE_NATIVE_SEARCH_PROGRESS'])==progress()
        assert command[4].endswith('platform_collection_worker.py')
        (output/'.yike-collection-status.json').write_text(json.dumps(dict(schema_version='YIKE_MEDIACRAWLER_STATUS_V1',platform='bili',status='SUCCEEDED_NO_DATA',error_code=None)))
        (output/'.yike-collection-progress.json').write_text(json.dumps(dict(schema_version='YIKE_MEDIACRAWLER_PROGRESS_V1',platform='bili',state='RUNNING',sequence=1)))
        if outcome!='missing':
            delta,_=collect(output,progress(),ids=[],pages=0)
            if outcome=='bad_delta':
                delta['after']['page']=2;(output/adapter().MARKER).write_text(json.dumps(delta))
        return SimpleNamespace(cancelled=outcome=='cancel',timed_out=False,returncode=0)
    monkeypatch.setattr(driver,'run_supervised_process',supervise)
    def run_source():return driver.collect_windows_source(runtime_path=tmp_path/'runtime',profile_path=tmp_path/'profile',output_path=output,
        platform='BILIBILI',query='设备',max_records=10,timeout_seconds=60,expected_account_public_id='123',native_progress=progress())
    if outcome in ('missing','bad_delta'):
        with pytest.raises(driver.WindowsSourceError):run_source()
    else:
        result=run_source()
        if outcome=='cancel':assert result['state']=='CANCELLED' and 'native_progress' not in result
        else:assert result['state']=='COLLECTED' and result['native_progress']['page_ids']==[]

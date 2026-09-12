"""Controlled JSONL and method boundaries, not real platform/Windows proof."""
import asyncio
from copy import deepcopy
import io
import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app import platform_collection_worker as worker
from app import windows_collection_host as host
from app.collection_output import read_collection_output, CollectionOutputError
from tests.test_candidate_mapping import build, BODY
from tests.test_windows_collection_host import request, encoded, run
from pilot.native_collection_links import parse_native_collection_link


URL = 'https://www.bilibili.com/video/BV1xx411c7mD'


def link_request(tmp_path):
    return request(tmp_path) | dict(query=None, expected_account_public_id='123',
        native_link=parse_native_collection_link(URL))


def post():
    return dict(video_id='101', title='销售资料问答', desc=BODY,
        video_url='https://www.bilibili.com/video/av101', creator_hash='not-a-public-mid',
        create_time='2026-09-08T01:02:03Z', collected_at='2026-09-09T02:00:00Z')


def test_native_host_passes_verified_target_and_null_query(tmp_path, monkeypatch):
    calls = []
    def driver(**kwargs):
        calls.append(kwargs)
        return dict(state='COLLECTED', records=[{'content':post()}], query=None,
                    collector_version='controlled-bili-links-v1')
    response, _ = run(monkeypatch, encoded(link_request(tmp_path)), driver)
    assert response['state'] == 'COLLECTED'
    assert calls[0]['native_link'] == parse_native_collection_link(URL)
    assert calls[0]['query'] is None and calls[0]['expected_account_public_id'] == '123'
    assert response['records'][0]['kind'] == 'POST'
    assert response['records'][0]['query'] is None
    assert 'source_context' not in response['records'][0]


@pytest.mark.parametrize('change', ['null', 'extra', 'mismatch', 'platform', 'account', 'query', 'noncanonical', 'bad_bv'])
def test_native_host_rejects_invalid_extension_before_driver(tmp_path, monkeypatch, change):
    data = link_request(tmp_path)
    if change == 'null': data['native_link'] = None
    if change == 'extra': data['native_link']['other'] = 'x'
    if change == 'mismatch': data['native_link']['external_id'] = 'BV1aa411c7mD'
    if change == 'platform': data['platform'] = 'DOUYIN'
    if change == 'account': data.pop('expected_account_public_id')
    if change == 'query': data['query'] = URL
    if change == 'noncanonical': data['native_link']['canonical_url'] += '?tracking=1'
    if change == 'bad_bv': data['native_link'] = parse_native_collection_link(URL.replace('BV1', 'BV0'))
    response, _ = run(monkeypatch, encoded(data), lambda **_: pytest.fail('must not spawn'))
    assert response['error_code'] == 'SOURCE_HOST_INPUT_INVALID'


def test_post_mapping_keeps_source_text_time_and_unknown_author():
    original = post()
    item = build([{'content':original}], 'BILIBILI', query=None).records[0]
    assert item.kind == 'POST' and item.body == BODY
    assert item.author_public_id is None and item.external_comment_id is None and item.parent is None
    assert item.published_at == original['create_time'] and item.observed_at == original['collected_at']
    assert item.public_url == original['video_url'] and item.query is None
    assert item.normalizer_version == 'raw-bili-post-candidate-v1'
    assert original == post()


def write_link_rows(tmp_path, mode, comments=True):
    leaf = tmp_path / 'bili' / 'jsonl'
    leaf.mkdir(parents=True)
    row = post()
    row.pop('collected_at')
    row['last_modify_ts'] = 1788919200000  # 2026-09-09T02:00:00Z
    (leaf / f'{mode}_contents_test.jsonl').write_text(json.dumps(row) + '\n')
    if comments:
        row = dict(video_id='101', comment_id='202', content='需要这类系统',
                   create_time='2026-09-08T01:02:03Z', last_modify_ts=1788919200000)
        (leaf / f'{mode}_comments_test.jsonl').write_text(json.dumps(row) + '\n')
    return leaf


@pytest.mark.parametrize('mode', ['detail', 'creator'])
def test_link_output_posts_and_comments_share_limit(tmp_path, mode):
    write_link_rows(tmp_path, mode)
    rows = read_collection_output(tmp_path, 'BILIBILI', 2, collection_mode=mode)
    assert len(rows) == 2 and set(rows[0]) == {'content'} and 'comment' in rows[1]
    assert [x.kind for x in build(rows, 'BILIBILI', query=None).records] == ['POST', 'COMMENT']
    with pytest.raises(CollectionOutputError):
        read_collection_output(tmp_path, 'BILIBILI', 1, collection_mode=mode)


def test_detail_post_without_comments_is_not_no_data(tmp_path):
    write_link_rows(tmp_path, 'detail', comments=False)
    assert len(read_collection_output(tmp_path, 'BILIBILI', 1, collection_mode='detail')) == 1


@pytest.mark.parametrize('mode', ['search', 'creator'])
def test_foreign_mode_output_is_rejected(tmp_path, mode):
    write_link_rows(tmp_path, mode)
    with pytest.raises(CollectionOutputError):
        read_collection_output(tmp_path, 'BILIBILI', 3, collection_mode='detail')


def argv(tmp_path, mode='detail', comments=0):
    args = ['--platform','bili','--lt','qrcode','--type',mode,
        '--get_comment','yes','--get_sub_comment','yes','--headless','no',
        '--save_data_option','jsonl','--max_concurrency_num','1','--enable_ip_proxy','no',
        '--save_data_path',str(tmp_path),'--crawler_max_notes_count','1',
        '--max_comments_count_singlenotes',str(comments)]
    return args + (['--specified_id='+URL] if mode == 'detail' else ['--creator_id=https://space.bilibili.com/123'])


@pytest.mark.parametrize('mode', ['detail', 'creator'])
def test_fixed_link_cli_accepts_only_bili_and_zero_comment_budget(tmp_path, mode):
    assert worker._fixed_arguments(argv(tmp_path, mode), 'BILIBILI') == mode
    with pytest.raises(ValueError): worker._fixed_arguments(argv(tmp_path, mode), 'DOUYIN')
    with pytest.raises(ValueError): worker._fixed_arguments(argv(tmp_path, mode) + ['--keywords=x'], 'BILIBILI')


def test_link_guard_mismatch_is_sticky_even_if_crawler_swallows(monkeypatch):
    account = ['123']
    calls = []
    class AuthError(Exception): pass
    async def self_account(_): return account[0]
    monkeypatch.setattr(worker, '_bilibili_self_account', self_account)
    class Client:
        def __init__(self, page): self.playwright_page = page
        async def request(self):
            calls.append('request')
            account[0] = '456'
    class Crawler:
        def __init__(self):
            self.context_page = object()
            self.bili_client = Client(self.context_page)
        async def search(self): pytest.fail('not search')
        async def collect_links(self):
            try: await self.bili_client.request()
            except AuthError: pass
            account[0] = '123'
            return 'must not succeed'
    original, request_method = Crawler.collect_links, Client.request
    with worker.install_video_account_guard(Crawler, Client, AuthError, '123', 'BILIBILI', entry_method='collect_links'):
        with pytest.raises(AuthError): asyncio.run(Crawler().collect_links())
    assert calls == ['request']
    assert Crawler.collect_links is original and Client.request is request_method


def test_link_guard_platform_risk_cannot_be_swallowed(monkeypatch):
    class AuthError(Exception): pass
    class RateLimit(Exception): pass
    async def self_account(_): return '123'
    monkeypatch.setattr(worker, '_bilibili_self_account', self_account)
    class Client:
        def __init__(self, page): self.playwright_page = page
        async def request(self): raise RateLimit()
    class Crawler:
        def __init__(self):
            self.context_page = object()
            self.bili_client = Client(self.context_page)
        async def collect_links(self):
            try: await self.bili_client.request()
            except RateLimit: pass
    with worker.install_video_account_guard(Crawler, Client, AuthError, '123', 'BILIBILI',
            error_types={'PLATFORM_RATE_LIMITED':RateLimit}, entry_method='collect_links'):
        with pytest.raises(RateLimit): asyncio.run(Crawler().collect_links())


@pytest.mark.parametrize('mode,budget', [('detail',1),('detail',20),('creator',1),('creator',20)])
def test_source_driver_links_fixed_command_and_real_file_mapping_with_controlled_os(tmp_path, monkeypatch, mode, budget):
    """Real driver+worker argv+reader/mapper, mocked OS supervision (not Windows proof)."""
    from app import windows_source_driver as driver
    monkeypatch.setattr(driver, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(driver, '_exclusive_paths', lambda _: nullcontext())
    monkeypatch.setattr(driver, 'verify_installed_runtime', lambda _: tmp_path/'python.exe')
    monkeypatch.setattr(driver, 'verify_private_tree', lambda _: None)
    def create(path):
        path.mkdir(parents=True)
        return path
    monkeypatch.setattr(driver, 'create_private_directory', create)
    calls = []
    target = parse_native_collection_link(URL if mode == 'detail' else 'https://space.bilibili.com/123')
    output = tmp_path/'output'
    def supervise(command, **kwargs):
        calls.append(command)
        assert command[4].endswith('platform_collection_worker.py')
        assert worker._fixed_arguments(command[5:],'BILIBILI') == mode
        assert not any(arg.startswith('--keywords') for arg in command)
        assert kwargs['env']['YIKE_EXPECTED_ACCOUNT_PUBLIC_ID'] == '123'
        assert kwargs['timeout_seconds'] <= 60
        contents, comments = driver._collection_limits('BILIBILI',budget,mode)
        assert contents * (comments + 1) <= budget
        assert command[command.index('--crawler_max_notes_count')+1] == str(contents)
        write_link_rows(output, mode, comments=False)
        (output/'.yike-collection-status.json').write_text(json.dumps(dict(schema_version='YIKE_MEDIACRAWLER_STATUS_V1',platform='bili',status='SUCCEEDED',error_code=None)))
        (output/'.yike-collection-progress.json').write_text(json.dumps(dict(schema_version='YIKE_MEDIACRAWLER_PROGRESS_V1',platform='bili',state='RUNNING',sequence=1)))
        return SimpleNamespace(cancelled=False,timed_out=False,returncode=0)
    monkeypatch.setattr(driver, 'run_supervised_process', supervise)
    result = driver.collect_windows_source(runtime_path=tmp_path/'runtime',profile_path=tmp_path/'profile',
        output_path=output, platform='BILIBILI', query=None, max_records=budget, timeout_seconds=60,
        expected_account_public_id='123', native_link=target)
    assert len(calls) == 1 and result['state'] == 'COLLECTED' and result['query'] is None
    assert result['collector_version'].endswith('-bili-links-v1')
    assert build(result['records'],'BILIBILI',query=None).records[0].kind == 'POST'

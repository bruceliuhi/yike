"""Controlled XHS output → Windows driver → existing formal candidate mapper."""
from datetime import datetime, timezone
import json
import sys

import pytest

from app.collection_output import CollectionOutputError, read_collection_output
from connectors.candidate_mapping import build_comment_batch
from tests.test_candidate_mapping import execution
from tests.test_windows_source_driver import source


NOTE = '66c01234abcdef0123456789'
COMMENT = '66c11234abcdef0123456789'
BODY = '  原文 é😀\n\t '


def raw():
    return ({'note_id': NOTE, 'title': None, 'desc': '不能用摘要代替标题',
             'time': None, 'last_modify_ts': 1789000000123,
             'note_url': f'https://www.xiaohongshu.com/explore/{NOTE}'},
            {'note_id': NOTE, 'comment_id': COMMENT, 'content': BODY,
             'create_time': '2026-09-10T00:00:00Z', 'parent_comment_id': None,
             'last_modify_ts': 1789000000123, 'creator_hash': 'anonymous', 'nickname': '匿名'})


def write(root, content, comment):
    leaf = root / 'xhs/jsonl'
    leaf.mkdir(parents=True)
    for kind, row in [('contents', content), ('comments', comment)]:
        (leaf / f'search_{kind}_1.jsonl').write_text(json.dumps(row, ensure_ascii=False), encoding='utf-8')


def mapped(records):
    return build_comment_batch(platform='XIAOHONGSHU', raw_records=records, request_id='request-1',
        profile_version_id='profile-1', strategy_version_id='strategy-1', execution=execution(),
        collector_version='controlled-fixture', query='需要设备', now=datetime(2026, 9, 10, 1, tzinfo=timezone.utc))


def test_xhs_exact_raw_evidence_reaches_formal_mapper(tmp_path):
    content, comment = raw()
    write(tmp_path, content, comment)
    rows = read_collection_output(tmp_path, 'XIAOHONGSHU', 2)
    observed_content = content | {'collected_at': '2026-09-10T00:26:40Z'}
    assert rows == [{'content': observed_content},
                    {'content': observed_content, 'comment': comment | {'collected_at': '2026-09-10T00:26:40Z'}}]
    original, item = mapped(rows).records
    assert original.kind == 'POST' and original.body == content['desc'] and original.title is None
    assert original.published_at is None
    assert item.body == BODY and item.title is None and item.parent is None
    assert item.author_public_id is None
    assert item.external_source_id == NOTE and item.external_comment_id == COMMENT


@pytest.mark.parametrize('title', ['', ' \t '])
def test_xhs_blank_title_keeps_post_and_comment_evidence(tmp_path, title):
    content, comment = raw()
    content['title'] = title
    write(tmp_path, content, comment)
    records = mapped(read_collection_output(tmp_path, 'XIAOHONGSHU', 2)).records
    assert [record.title for record in records] == [None, None]
    assert [record.body for record in records] == [content['desc'], BODY]
    assert content['title'] == title


@pytest.mark.parametrize('field', ['comment_id', 'id'])
def test_xhs_comment_alias_and_parent_evidence_preserved(tmp_path, field):
    content, comment = raw()
    comment.pop('comment_id')
    comment.update({field: COMMENT, 'parent_comment_id': '66c21234abcdef0123456789', 'parent_content': BODY})
    write(tmp_path, content, comment)
    item = mapped(read_collection_output(tmp_path, 'XIAOHONGSHU', 2)).records[1]
    assert item.parent.external_comment_id == comment['parent_comment_id']
    assert item.parent.body == BODY and item.parent.published_at is None


@pytest.mark.parametrize('side,field,value', [
    ('content', 'note_id', ' badid'), ('comment', 'note_id', '66c31234abcdef0123456789'),
    ('comment', 'source_id', '66c31234abcdef0123456789'), ('content', 'source_id', '66c31234abcdef0123456789'),
    ('comment', 'id', '66c31234abcdef0123456789'), ('comment', 'comment_id', True),
    ('content', 'note_id', 1.0), ('comment', 'note_id', None)])
def test_xhs_invalid_or_conflicting_identifiers_are_not_repaired(tmp_path, side, field, value):
    content, comment = raw()
    (content if side == 'content' else comment)[field] = value
    write(tmp_path, content, comment)
    with pytest.raises(CollectionOutputError): read_collection_output(tmp_path, 'XIAOHONGSHU', 2)


@pytest.mark.skipif(sys.platform != 'win32', reason='actual Windows Job fixture')
@pytest.mark.parametrize('with_comment,terminal,valid', [
    (True, 'SUCCEEDED', True), (False, 'SUCCEEDED_NO_DATA', True),
    (True, 'SUCCEEDED_NO_DATA', False), (False, 'SUCCEEDED', False),
])
def test_xhs_driver_real_fixture_process_and_formal_mapper(source, monkeypatch, with_comment, terminal, valid):
    from app.collector import run_supervised_process
    content, comment = raw()
    script = '''import json, os, sys
from pathlib import Path
assert sys.argv[sys.argv.index('--platform') + 1] == 'xhs'
assert os.environ['YIKE_PROFILE_PATH']
output = Path(next(x.split('=', 1)[1] for x in sys.argv if x.startswith('--save_data_path=')))
leaf = output / 'xhs/jsonl'
leaf.mkdir(parents=True)
def write(path, data): path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
'''
    script += f"write(leaf / 'search_contents_1.jsonl', {content!r})\n"
    if with_comment:
        script += f"write(leaf / 'search_comments_1.jsonl', {comment!r})\n"
    # The pinned XHS producer's terminal reports comment presence, not posts.
    script += f"write(output / '.yike-collection-status.json', dict(schema_version='YIKE_MEDIACRAWLER_STATUS_V1', platform='xhs', status={terminal!r}, error_code=None))\n"
    script += "write(output / '.yike-collection-progress.json', dict(schema_version='YIKE_MEDIACRAWLER_PROGRESS_V1', platform='xhs', state='RUNNING', sequence=1))\n"
    (source.args['runtime_path'] / 'main.py').write_text(script, encoding='utf-8')
    monkeypatch.setattr(source.api, 'run_supervised_process', run_supervised_process)
    if not valid:
        with pytest.raises(source.api.WindowsSourceError, match='source_collection_failed'):
            source.api.collect_windows_source(**(source.args | {'platform': 'XIAOHONGSHU'}))
        return
    result = source.api.collect_windows_source(**(source.args | {'platform': 'XIAOHONGSHU'}))
    assert result['state'] == 'COLLECTED' and result['task_completed'] is False
    records = mapped(result['records']).records
    original = records[0]
    assert original.kind == 'POST' and original.body == content['desc']
    assert len(records) == 1 + int(with_comment)
    if with_comment:
        assert records[1].kind == 'COMMENT' and records[1].body == BODY

"""Synthetic pinned XHS output; no source-verification or live-platform claims."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from app.collection_output import CollectionOutputError, read_collection_output
from connectors.candidate_mapping import build_comment_batch
from tests.test_candidate_mapping import execution


NOTE = '66c01234abcdef0123456789'
STAMP = 1789000000123
BODY = ' \t需要定制软件 e\u0301\r\n请推荐团队 🧰 '


def post():
    # The pinned store exposes time in UTC and anonymized author metadata.
    return dict(note_id=NOTE, title=' 原标题 ', desc=BODY, time='2026-09-08T01:02:03Z',
                last_modify_ts=STAMP, creator_hash='not-public-id', nickname='匿名',
                note_url=f'https://www.xiaohongshu.com/explore/{NOTE}')


def comment():
    return dict(note_id=NOTE, comment_id='66c11234abcdef0123456789', content=' 可以联系我 ',
                create_time=None, last_modify_ts=STAMP + 1000)


def write(root, posts, comments):
    leaf = root / 'xhs' / 'jsonl'
    leaf.mkdir(parents=True, exist_ok=True)
    for kind, rows in (('contents', posts), ('comments', comments)):
        (leaf / f'search_{kind}_test.jsonl').write_text(
            ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def test_xhs_original_post_and_comment_flow_to_formal_contract(tmp_path):
    write(tmp_path, [post()], [comment()])
    rows = read_collection_output(tmp_path, 'XIAOHONGSHU', 2)
    assert len(rows) == 2
    assert rows[0] == {'content': dict(post(), collected_at='2026-09-10T00:26:40Z')}
    assert rows[1]['comment']['collected_at'] == '2026-09-10T00:26:41Z'
    batch = build_comment_batch(platform='XIAOHONGSHU', raw_records=rows,
        request_id='request-xhs', profile_version_id='profile-xhs', strategy_version_id='strategy-xhs',
        execution=execution(), collector_version='pinned-xhs', query='软件定制',
        now=datetime(2026, 9, 11, tzinfo=timezone.utc))
    assert [item.kind for item in batch.records] == ['POST', 'COMMENT']
    original, reply = batch.records
    assert original.body == BODY and original.title == post()['title']
    assert original.public_url == post()['note_url'] and original.external_source_id == NOTE
    assert original.published_at == post()['time'] and reply.published_at is None
    assert original.observed_at == '2026-09-10T00:26:40Z'
    assert original.author_public_id is None and reply.author_public_id is None
    assert original.external_comment_id is None and original.parent is None
    assert original.normalizer_version == 'raw-xhs-post-candidate-v1'


def test_xhs_post_without_comments_is_not_discarded(tmp_path):
    write(tmp_path, [post()], [])
    assert len(read_collection_output(tmp_path, 'XIAOHONGSHU', 1)) == 1


@pytest.mark.parametrize('problem', ['overbudget', 'missing_observation', 'orphan', 'conflict', 'duplicate_comment'])
def test_xhs_invalid_output_never_becomes_partial_success(tmp_path, problem):
    posts, comments, budget = [post()], [comment()], 3
    if problem == 'overbudget': budget = 1
    if problem == 'missing_observation': posts[0].pop('last_modify_ts')
    if problem == 'orphan': comments[0]['note_id'] = '66c21234abcdef0123456789'
    if problem == 'conflict': posts.append(dict(post(), desc='different'))
    if problem == 'duplicate_comment': comments.append(deepcopy(comments[0]))
    write(tmp_path, posts, comments)
    with pytest.raises(CollectionOutputError, match='INVALID_COLLECTION_OUTPUT'):
        read_collection_output(tmp_path, 'XIAOHONGSHU', budget)

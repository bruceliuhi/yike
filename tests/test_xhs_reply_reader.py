"""Synthetic platform pages/responses; never actual customer replies."""
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.xhs_comment_channel import XhsPostCommentChannel
from tests.test_xhs_comment_channel import Page, context, ACCOUNT, AUTHOR, COMMENT

NOW = datetime(2026, 9, 12, tzinfo=UTC)
CLAIM = (NOW - timedelta(minutes=1)).isoformat()


def harness():
    value, page = context(), Page()
    page.url += '&xsec_token=x'
    page.comments = [{'id': 'comment-' + COMMENT, 'author': ACCOUNT, 'text': value['draft']['savedContent']}]
    row = {'id': 'a' * 24, 'content': '可以先看案例吗', 'create_time': int(NOW.timestamp() * 1000),
           'user_info': {'user_id': AUTHOR}, 'target_comment': {'id': COMMENT}}
    fetch = AsyncMock(return_value={'comments': [row], 'has_more': False, 'cursor': ''})
    return value, page, row, fetch


def test_reader_collects_only_original_buyer_direct_replies_without_actions():
    value, page, row, fetch = harness()
    other = deepcopy(row); other.update(id='b' * 24, user_info={'user_id': ACCOUNT})
    indirect = deepcopy(row); indirect.update(id='c' * 24, target_comment={'id': 'd' * 24})
    fetch.return_value['comments'] += [other, indirect]
    channel = XhsPostCommentChannel(page, now=lambda: NOW, read_sub_comments=fetch)
    result = asyncio.run(channel.read_replies(value, COMMENT, CLAIM))
    assert result == {'status': 'COMPLETE', 'items': [{'externalReplyId': row['id'], 'senderPublicId': AUTHOR,
        'body': row['content'], 'receivedAt': NOW.isoformat(), 'observedAt': NOW.isoformat(), 'readState': 'UNKNOWN'}]}
    assert fetch.call_args.kwargs == {'note_id': value['target']['postId'], 'root_comment_id': COMMENT,
        'xsec_token': 'x', 'num': 10, 'cursor': ''}
    assert page.clicks == page.reloads == 0 and page.draft == ''
    assert 'synthetic-transient-token' not in str(result)


@pytest.mark.parametrize('change', ['account', 'root', 'content', 'token', 'cancel'])
def test_unverified_original_page_never_requests_comments(change):
    value, page, row, fetch = harness()
    if change == 'account': page.account = 'b' * 24
    if change == 'root': page.comments.clear()
    if change == 'content': page.comments[0]['text'] = 'another message'
    if change == 'token': page.url += '&xsec_token=second'
    channel = XhsPostCommentChannel(page, now=lambda: NOW, read_sub_comments=fetch, cancelled=lambda: change == 'cancel')
    with pytest.raises(RuntimeError, match='^REPLY_SOURCE_UNAVAILABLE$'):
        asyncio.run(channel.read_replies(value, COMMENT, CLAIM))
    fetch.assert_not_called()


@pytest.mark.parametrize('change', ['old', 'future', 'bool-time', 'date-text', 'conflict', 'author-conflict', 'cursor', 'account', 'error'])
def test_invalid_or_changed_observation_is_not_empty_success(change):
    value, page, row, fetch = harness()
    if change == 'old': row['create_time'] -= 120000
    if change == 'future': row['create_time'] += 10000
    if change == 'bool-time': row['create_time'] = True
    if change == 'date-text': row['create_time'] = '刚刚'
    if change == 'conflict': fetch.return_value['comments'].append({**row, 'content': 'changed'})
    if change == 'author-conflict': fetch.return_value['comments'].append({**row, 'user_info': {'user_id': ACCOUNT}})
    if change == 'cursor': fetch.return_value.update(has_more=True)
    if change == 'account':
        async def switched(**_):
            page.account = 'b' * 24
            return {'comments': [row], 'has_more': False, 'cursor': ''}
        fetch.side_effect = switched
    if change == 'error': fetch.side_effect = RuntimeError('sensitive platform error')
    channel = XhsPostCommentChannel(page, now=lambda: NOW, read_sub_comments=fetch)
    with pytest.raises(RuntimeError, match='^REPLY_SOURCE_UNAVAILABLE$'):
        asyncio.run(channel.read_replies(value, COMMENT, CLAIM))
    assert fetch.call_count <= 1


def test_reader_bounds_pages_and_deduplicates_same_public_reply():
    value, page, row, fetch = harness()
    fetch.side_effect = [{'comments': [row], 'has_more': True, 'cursor': str(i)} for i in range(3)]
    channel = XhsPostCommentChannel(page, now=lambda: NOW, read_sub_comments=fetch)
    result = asyncio.run(channel.read_replies(value, COMMENT, CLAIM))
    assert result['status'] == 'PARTIAL' and len(result['items']) == 1
    assert fetch.call_count == 3

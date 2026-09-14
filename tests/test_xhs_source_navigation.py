"""Offline browser doubles: no assertions about real XHS availability."""
import asyncio
import importlib

import pytest

NOTE = 'a' * 24
AUTHOR = 'b' * 24
ACCOUNT = 'account1234'
ORIGIN = 'https://www.xiaohongshu.com'
TOKEN = 'private-browser-token'


class Element:
    def __init__(self, page, href=None, visible=True, action=None):
        self.page, self.href, self.visible, self.action = page, href, visible, action

    async def is_visible(self, **kwargs): return self.visible
    async def get_attribute(self, name, **kwargs): return self.href if name == 'href' else None
    def locator(self, selector):
        assert selector.startswith('xpath=ancestor::')
        return Locator([Element(self.page)] if self.page.error_inside_source else [])
    async def fill(self, value, **kwargs): self.page.act('fill', value)
    async def press(self, value, **kwargs): self.page.act('press', value)
    async def click(self, **kwargs):
        self.page.url = self.page.destination or ORIGIN + '/explore/' + NOTE
        self.page.detail = True
        self.page.act('click', None)


class Locator:
    def __init__(self, elements): self.elements = elements
    async def wait_for(self, **kwargs):
        for element in self.elements:
            element.visible = True
    async def count(self): return len(self.elements)
    def nth(self, index): return self.elements[index]
    async def is_visible(self, **kwargs): return len(self.elements) == 1 and self.elements[0].visible
    async def get_attribute(self, name, **kwargs): return await self.elements[0].get_attribute(name)
    async def fill(self, value, **kwargs): await self.elements[0].fill(value)
    async def press(self, value, **kwargs): await self.elements[0].press(value)


class Page:
    def __init__(self):
        self.url, self.account = ORIGIN + '/explore', ACCOUNT
        self.actions, self.hook = [], None
        self.links = [Element(self, '/user/profile/' + AUTHOR + '/' + NOTE + '?xsec_token=' + TOKEN)]
        self.search, self.detail, self.blocked = True, False, False
        self.destination = None
        self.author = AUTHOR
        self.error_text = '安全验证'
        self.error_inside_source = False
        self.pending_self = False
        self.pending_search = False

    def act(self, name, value):
        self.actions.append((name, value))
        if self.hook: self.hook(self, name)

    async def goto(self, url, **kwargs):
        self.url = url
        self.act('goto', url)

    def get_by_role(self, role, **kwargs):
        return Locator([Element(self, '/user/profile/' + self.account, visible=not self.pending_self)] if self.account else [])

    def get_by_text(self, pattern, **kwargs):
        return Locator([Element(self)] if self.blocked and pattern.search(self.error_text) else [])

    def locator(self, selector):
        if selector == 'input#search-input': return Locator([Element(self, visible=not self.pending_search)] if self.search else [])
        if selector == '#noteContainer': return Locator([Element(self)] if self.detail else [])
        if selector == '#noteContainer .author-container a.name':
            return Locator([Element(self, '/user/profile/' + self.author)] if self.detail else [])
        if selector in ('#userPostedFeeds a.cover', 'a[href]'): return Locator(self.links)
        raise AssertionError('unexpected selector')


def run(page, **kwargs):
    try:
        module = importlib.import_module('app.xhs_source_navigation')
    except ModuleNotFoundError:
        pytest.fail('source navigation helper is not implemented')
    return asyncio.run(module.navigate_xhs_source(page, note_id=kwargs.pop('note_id', NOTE),
        expected_account=kwargs.pop('expected_account', ACCOUNT), **kwargs))


def test_author_link_uses_actual_locator_and_never_returns_token(capsys):
    page = Page()
    result = run(page, author_id=AUTHOR)
    assert result == 'SOURCE_OPENED'
    assert page.actions == [('goto', ORIGIN + '/user/profile/' + AUTHOR), ('click', None)]
    assert TOKEN not in str(result) + str(capsys.readouterr())


@pytest.mark.parametrize('kwargs', [dict(note_id='x'), dict(expected_account='short'),
    dict(author_id='x'), dict(original_query=''), dict(original_query=' '),
    dict(original_query='x' * 201), dict(original_query='a\nsecret'), dict()])
def test_invalid_input_has_no_browser_actions(kwargs):
    page = Page()
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_INVALID_INPUT$'): run(page, **kwargs)
    assert page.actions == []


@pytest.mark.parametrize('url', ['http://www.xiaohongshu.com/explore',
    'https://www.xiaohongshu.com.evil.test/', 'https://evil.test/',
    'https://www.xiaohongshu.com:444/', 'https://x@www.xiaohongshu.com/'])
def test_wrong_origin_before_action(url):
    page = Page(); page.url = url
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_ORIGIN_CHANGED$'): run(page, author_id=AUTHOR)
    assert not page.actions


@pytest.mark.parametrize('account', ['', 'different123'])
def test_wrong_or_missing_account_before_action(account):
    page = Page(); page.account = account
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_ACCOUNT_CHANGED$'): run(page, author_id=AUTHOR)
    assert not page.actions


@pytest.mark.parametrize('stage', ['goto', 'fill', 'press', 'click'])
@pytest.mark.parametrize('kind', ['account', 'origin', 'cancel', 'blocked'])
def test_guards_after_every_action(stage, kind):
    page = Page(); cancelled = [False]
    def mutate(p, name):
        if name != stage: return
        if kind == 'account': p.account = 'different123'
        if kind == 'origin': p.url = 'https://evil.test/'; p.destination = p.url
        if kind == 'cancel': cancelled[0] = True
        if kind == 'blocked': p.blocked = True
    page.hook = mutate
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_'):
        run(page, original_query='original query', cancelled=lambda: cancelled[0])
    assert page.actions[-1][0] == stage


def test_pre_cancelled_does_not_navigate():
    page = Page()
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_CANCELLED$'):
        run(page, author_id=AUTHOR, cancelled=lambda: True)
    assert not page.actions


@pytest.mark.parametrize('href', ['/explore/' + 'c' * 24,
    '//evil.test/explore/' + NOTE, 'https://evil.test/explore/' + NOTE,
    '/explore/' + NOTE + '/extra', '/foo?target=/explore/' + NOTE,
    '/explore/' + NOTE + '%2f', 'javascript:alert(1)'])
def test_invalid_or_wrong_note_links_are_not_clicked(href):
    page = Page(); page.links = [Element(page, href)]
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_NOT_FOUND$'): run(page, original_query='query')
    assert all(name != 'click' for name, _ in page.actions)


@pytest.mark.parametrize('mode', ['duplicate', 'hidden'])
def test_no_unique_visible_exact_match(mode):
    page = Page()
    if mode == 'duplicate': page.links.append(Element(page, page.links[0].href))
    else: page.links[0].visible = False
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_NOT_FOUND$'): run(page, author_id=AUTHOR)
    assert all(name != 'click' for name, _ in page.actions)


@pytest.mark.parametrize('path', ['/explore/' + NOTE, '/search_result/' + NOTE,
    '/user/profile/' + AUTHOR + '/' + NOTE])
def test_unknown_author_search_matches_exact_paths(path):
    page = Page(); page.links = [Element(page, path + '?xsec_token=' + TOKEN)]
    page.destination = ORIGIN + path + '?xsec_token=' + TOKEN
    assert run(page, original_query='原始查询') == 'SOURCE_OPENED'
    assert page.actions[1:3] == [('fill', '原始查询'), ('press', 'Enter')]


def test_missing_observed_search_input_stops():
    page = Page(); page.search = False
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_SEARCH_UNAVAILABLE$'): run(page, original_query='query')
    assert len(page.actions) == 1


@pytest.mark.parametrize('destination', [ORIGIN + '/404', ORIGIN + '/explore/' + 'c' * 24])
def test_wrong_destination_is_never_success(destination):
    page = Page(); page.destination = destination
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_DETAIL_UNAVAILABLE$'): run(page, author_id=AUTHOR)


@pytest.mark.parametrize('message', ['404', '页面不存在', '笔记不存在', '扫码登录', '安全验证', '访问受限',
    '当前笔记暂时无法浏览', '请打开小红书App扫码查看'])
def test_visible_error_page_even_with_matching_note_url_is_not_success(message):
    page = Page()
    page.error_text = message
    page.hook = lambda p, name: setattr(p, 'blocked', name == 'click')
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_PLATFORM_BLOCKED$'): run(page, author_id=AUTHOR)


@pytest.mark.parametrize('text', ['404', '安全验证', '这篇文章讨论验证码和网络异常'])
def test_legitimate_source_text_is_not_a_platform_barrier(text):
    page = Page(); page.blocked = True; page.error_text = text; page.error_inside_source = True
    assert run(page, author_id=AUTHOR) == 'SOURCE_OPENED'


@pytest.mark.parametrize('missing', ['detail', 'author'])
def test_matching_url_without_real_detail_is_not_success(missing):
    page = Page()
    def mutate(p, name):
        if name == 'click':
            if missing == 'detail': p.detail = False
            else: p.author = 'invalid'
    page.hook = mutate
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_DETAIL_UNAVAILABLE$'): run(page, author_id=AUTHOR)


def test_known_original_author_must_match_detail_author():
    page = Page(); page.author = 'c' * 24
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_DETAIL_UNAVAILABLE$'): run(page, author_id=AUTHOR)


def test_hidden_duplicate_does_not_compete_with_visible_match():
    page = Page(); page.links.append(Element(page, page.links[0].href, visible=False))
    assert run(page, author_id=AUTHOR) == 'SOURCE_OPENED'


def test_browser_exception_does_not_export_url_or_body(capsys):
    page = Page()
    def fail(*args): raise ValueError(TOKEN + ' secret body query')
    page.hook = fail
    with pytest.raises(RuntimeError, match='^XHS_SOURCE_UNAVAILABLE$') as error: run(page, author_id=AUTHOR)
    assert TOKEN not in str(error.value) + str(capsys.readouterr())


@pytest.mark.parametrize('pending', ['pending_self', 'pending_search'])
def test_spa_controls_wait_for_visibility_before_inspection(pending):
    page = Page(); setattr(page, pending, True)
    assert run(page, original_query='query') == 'SOURCE_OPENED'

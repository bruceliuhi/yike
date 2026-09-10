from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import asyncio

import pytest

from app.xhs_comment_channel import XhsPostCommentChannel


NOTE = "6a9e313a0000000026031b33"
ACCOUNT = "68c000000000000000000001"
AUTHOR = "68c000000000000000000002"
COMMENT = "68c000000000000000000003"


def context():
    ids = [str(uuid4()) for _ in range(9)]
    return {
        "schemaVersion": "outreach-context-v1",
        "binding": {"opportunityId": ids[0], "channel": "comment", "requestId": ids[1], "contentHash": "1" * 64},
        "ownerUserId": ids[2], "accountScope": {"id": ids[3], "version": 1}, "profileVersionId": ids[4],
        "draft": {"opportunityId": ids[0], "channel": "comment", "content": "可以交流这个需求", "savedContent": "可以交流这个需求", "version": 1, "accountId": ACCOUNT, "recipient": AUTHOR},
        "source": {"sourceId": ids[5], "evidenceVersion": ids[6], "evidenceSha256": "2" * 64, "platform": "XIAOHONGSHU", "kind": "POST", "url": f"https://www.xiaohongshu.com/explore/{NOTE}", "excerpt": "公开原帖"},
        "target": {"action": "POST_COMMENT", "authorPublicId": AUTHOR, "postId": NOTE, "commentId": None},
        "connection": {"deviceId": ids[7], "connectionId": ids[8], "connectionVersion": 1, "accountPublicId": ACCOUNT, "platform": "XIAOHONGSHU"},
        "channelCapability": {"status": "UNVERIFIED", "reason": "CHANNEL_CHECK_REQUIRED"},
        "authorization": "NOT_GRANTED", "contextSha256": "3" * 64,
    }


class Locator:
    def __init__(self, page, selector): self.page, self.selector = page, selector
    async def count(self): return len(self.page.nodes(self.selector))
    async def is_visible(self, **_): return bool(self.page.nodes(self.selector))
    async def get_attribute(self, name, **_): return self.page.nodes(self.selector)[0].get(name)
    async def inner_text(self, **_): return self.page.nodes(self.selector)[0].get("text", "")
    def nth(self, index): return ItemLocator(self.page.nodes(self.selector)[index])
    async def fill(self, value, **_): self.page.draft = value
    async def click(self, **_):
        if self.page.pending_click:
            self.page.click_started.set()
            try: await asyncio.wait_for(self.page.click_gate.wait(), .05)
            except TimeoutError: pass
            if self.page.closed: return
        self.page.clicks += 1
        self.page.comments.append({"id": f"comment-{COMMENT}", "author": ACCOUNT, "text": self.page.draft})


class ItemLocator:
    def __init__(self, node): self.node = node
    async def get_attribute(self, name, **_): return self.node.get(name)


class Page:
    def __init__(self, *, account=ACCOUNT, persist=True, pending_click=False):
        self.url = f"https://www.xiaohongshu.com/explore/{NOTE}?xsec_source=pc_feed"
        self.account, self.author, self.persist = account, AUTHOR, persist
        self.draft, self.clicks, self.reloads, self.comments = "", 0, 0, []
        self.pending_click, self.closed = pending_click, False
        self.click_started, self.click_gate = asyncio.Event(), asyncio.Event()
    def locator(self, selector): return Locator(self, selector)
    def nodes(self, selector):
        if selector == "#noteContainer": return [{}]
        if selector == "#noteContainer .author-container a.name": return [{"text": "原帖作者", "href": f"/user/profile/{self.author}?xsec_token=discard"}]
        if selector.startswith("xpath=//a"):
            return [{"href": f"/user/profile/{self.account}"}]
        if selector == "#content-textarea[contenteditable=true]": return [{"text": self.draft}]
        if selector == ".content-edit": return [{"text": self.draft or "说点什么..."}]
        if selector == "button:has-text('发送')": return [{}]
        if selector == "#noteContainer .comment-item:not(.comment-item-sub)":
            return [{"id": c["id"]} for c in self.comments]
        if selector.startswith("#noteContainer .comment-item:not(.comment-item-sub)#comment-"):
            wanted = selector.split("#comment-", 1)[1].split()[0]
            rows = [c for c in self.comments if c["id"] == f"comment-{wanted}" and not c.get("outside") and not c.get("sub")]
            if selector.endswith(" a.name"): return [{"text": "当前用户", "href": f"/user/profile/{c['author']}?xsec_token=discard"} for c in rows]
            if selector.endswith(" .note-text"): return [{"text": c["text"]} for c in rows]
            return rows
        if selector.startswith("#comment-"):
            wanted = selector.split()[0][1:]
            rows = [c for c in self.comments if c["id"] == wanted]
            if selector.endswith(" a.name"): return [{"text": "当前用户", "href": f"/user/profile/{c['author']}?xsec_token=discard"} for c in rows]
            if selector.endswith(" .note-text"): return [{"text": c["text"]} for c in rows]
            return rows
        return []
    async def close(self, **_):
        self.closed = True
        self.click_gate.set()
    async def reload(self, **_):
        self.reloads += 1
        self.draft = ""
        if not self.persist: self.comments.clear()


def operation(now):
    return {"requestId": str(uuid4()), "claimId": str(uuid4()), "dispatchBefore": (now + timedelta(seconds=30)).isoformat()}


def test_check_binds_expected_page_and_requires_blank_main_comment():
    async def run():
        now = datetime(2026, 9, 11, 10, tzinfo=UTC)
        value = context(); page = Page()
        observed = await XhsPostCommentChannel(page, cancelled=lambda: False, now=lambda: now).check(value)
        assert observed == {"status": "AVAILABLE", "contextSha256": value["contextSha256"], "deviceId": value["connection"]["deviceId"], "connectionId": value["connection"]["connectionId"], "connectionVersion": 1, "accountPublicId": ACCOUNT, "recipientId": AUTHOR, "checkedAt": now.isoformat()}
        page.draft = "已有草稿"
        with pytest.raises(RuntimeError, match="CHANNEL_UNAVAILABLE"):
            await XhsPostCommentChannel(page, cancelled=lambda: False, now=lambda: now).check(value)
    asyncio.run(run())


def test_check_normalizes_page_failures():
    class BrokenPage(Page):
        def locator(self, _selector): raise ValueError("browser detail")
    async def run():
        with pytest.raises(RuntimeError, match="^CHANNEL_UNAVAILABLE$"):
            await XhsPostCommentChannel(BrokenPage(), cancelled=lambda: False).check(context())
    asyncio.run(run())


@pytest.mark.parametrize("cancelled,account", [(True, ACCOUNT), (False, "68c000000000000000000009")])
def test_cancelled_or_wrong_account_never_clicks(cancelled, account):
    async def run():
        now = datetime(2026, 9, 11, 10, tzinfo=UTC); value = context(); page = Page(account=account)
        channel = XhsPostCommentChannel(page, cancelled=lambda: cancelled, now=lambda: now)
        try: await channel.check(value)
        except RuntimeError: pass
        assert await channel.execute(value, operation(now)) == {"status": "UNKNOWN"}
        assert page.clicks == 0
    asyncio.run(run())


def test_single_click_and_persistent_reload_receipt_is_sent():
    async def run():
        now = datetime(2026, 9, 11, 10, tzinfo=UTC); value = context(); page = Page()
        channel = XhsPostCommentChannel(page, cancelled=lambda: False, now=lambda: now)
        await channel.check(deepcopy(value))
        result = await channel.execute(deepcopy(value), operation(now))
        assert result["status"] == "SENT" and result["confirmed"] is True
        assert result["proof"]["kind"] == "ACCEPTED" and result["proof"]["externalId"] == COMMENT
        assert len(result["proof"]["sha256"]) == 64
        assert page.clicks == 1 and page.reloads == 1
        assert await channel.execute(value, operation(now)) == {"status": "UNKNOWN"}
        assert page.clicks == 1
    asyncio.run(run())


def test_refresh_disappearance_is_unknown_without_retry():
    async def run():
        now = datetime(2026, 9, 11, 10, tzinfo=UTC); value = context(); page = Page(persist=False)
        channel = XhsPostCommentChannel(page, cancelled=lambda: False, now=lambda: now)
        await channel.check(value)
        assert await channel.execute(value, operation(now)) == {"status": "UNKNOWN"}
        assert page.clicks == 1 and page.reloads == 1
    asyncio.run(run())


def test_cancellation_closes_page_and_aborts_pending_click():
    async def run():
        now = datetime(2026, 9, 11, 10, tzinfo=UTC); value = context(); page = Page(pending_click=True)
        state = {"cancelled": False}
        channel = XhsPostCommentChannel(page, cancelled=lambda: state["cancelled"], now=lambda: now)
        await channel.check(value)
        task = asyncio.create_task(channel.execute(value, operation(now)))
        await page.click_started.wait()
        state["cancelled"] = True
        assert await task == {"status": "UNKNOWN"}
        assert page.closed is True and page.clicks == 0
    asyncio.run(run())


def test_external_task_cancel_closes_pending_click_without_waiting_for_runtime_cleanup():
    async def run():
        now = datetime(2026, 9, 11, 10, tzinfo=UTC); value = context(); page = Page(pending_click=True)
        channel = XhsPostCommentChannel(page, cancelled=lambda: False, now=lambda: now)
        await channel.check(value)
        task = asyncio.create_task(channel.execute(value, operation(now)))
        await page.click_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        # Runtime cleanup has not run: the channel must close the page itself.
        assert page.closed and page.clicks == 0
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    asyncio.run(run())


def test_reload_receipt_outside_top_level_note_scope_is_unknown():
    class OutsideReceiptPage(Page):
        async def reload(self, **kwargs):
            await super().reload(**kwargs)
            self.comments[0]["outside"] = True
        def nodes(self, selector):
            return super().nodes(selector)
    async def run():
        now = datetime(2026, 9, 11, 10, tzinfo=UTC); value = context(); page = OutsideReceiptPage()
        channel = XhsPostCommentChannel(page, cancelled=lambda: False, now=lambda: now)
        await channel.check(value)
        assert await channel.execute(value, operation(now)) == {"status": "UNKNOWN"}
    asyncio.run(run())

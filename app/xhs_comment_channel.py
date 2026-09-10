"""Bounded adapter for one approved XHS top-level comment action.

The caller owns the isolated, already authenticated Playwright page.  This
module exposes no transport or unconfirmed sending entry point.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit
from uuid import UUID


_PUBLIC_ID = re.compile(r"[0-9a-f]{24}")
_SELF = "xpath=//a[contains(@href, '/user/profile/') and .//span[text()='我']]"
_TOP_COMMENTS = "#noteContainer .comment-item:not(.comment-item-sub)"
_UNKNOWN = {"status": "UNKNOWN"}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, UTC)
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(UTC)
    raise ValueError


def _uuid(value):
    try: return isinstance(value, str) and str(UUID(value)) == value
    except ValueError: return False


def _keys(value, names):
    return isinstance(value, dict) and set(value) == set(names)


def _note_url(value, expected):
    if not isinstance(value, str) or "\\" in value or not value.isprintable(): return False
    parsed = urlsplit(value)
    return (parsed.scheme == "https" and parsed.netloc == "www.xiaohongshu.com" and
            parsed.path == f"/explore/{expected}" and
            not parsed.username and not parsed.password and parsed.port is None)


def _profile_id(href):
    if not isinstance(href, str) or "\\" in href: return None
    parsed = urlsplit(href)
    if parsed.scheme and (parsed.scheme != "https" or parsed.netloc != "www.xiaohongshu.com"): return None
    match = re.fullmatch(r"/user/profile/([0-9a-f]{24})", parsed.path)
    return match.group(1) if match else None


def _snapshot(raw):
    value = deepcopy(raw)
    try:
        draft, source, target, connection = value["draft"], value["source"], value["target"], value["connection"]
        note, account, author = target["postId"], connection["accountPublicId"], target["authorPublicId"]
        valid = (
            _keys(value, ("schemaVersion", "binding", "ownerUserId", "accountScope", "profileVersionId", "draft", "source", "target", "connection", "channelCapability", "authorization", "contextSha256")) and
            _keys(value["binding"], ("opportunityId", "channel", "requestId", "contentHash")) and
            _keys(value["accountScope"], ("id", "version")) and
            _keys(draft, ("opportunityId", "channel", "content", "savedContent", "version", "accountId", "recipient")) and
            _keys(source, ("sourceId", "evidenceVersion", "evidenceSha256", "platform", "kind", "url", "excerpt")) and
            _keys(target, ("action", "authorPublicId", "postId", "commentId")) and
            _keys(connection, ("deviceId", "connectionId", "connectionVersion", "accountPublicId", "platform")) and
            _keys(value["channelCapability"], ("status", "reason")) and
            value["schemaVersion"] == "outreach-context-v1" and value["binding"]["channel"] == "comment" and
            all(_uuid(value[key]) for key in ("ownerUserId", "profileVersionId")) and
            all(_uuid(item) for item in (value["binding"]["opportunityId"], value["binding"]["requestId"], value["accountScope"]["id"], source["sourceId"], source["evidenceVersion"], connection["deviceId"], connection["connectionId"])) and
            draft["opportunityId"] == value["binding"]["opportunityId"] and
            all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in (value["accountScope"]["version"], draft["version"], connection["connectionVersion"])) and
            all(isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item) for item in (value["binding"]["contentHash"], source["evidenceSha256"], value["contextSha256"])) and
            source["platform"] == connection["platform"] == "XIAOHONGSHU" and source["kind"] == "POST" and
            target["action"] == "POST_COMMENT" and target["commentId"] is None and
            draft["channel"] == "comment" and draft["content"] == draft["savedContent"] and
            isinstance(draft["savedContent"], str) and 1 <= len(draft["savedContent"]) <= 8000 and
            draft["accountId"] == account and draft["recipient"] == author and
            all(isinstance(item, str) and _PUBLIC_ID.fullmatch(item) for item in (note, account, author)) and
            isinstance(source["excerpt"], str) and len(source["excerpt"]) <= 20_000 and
            _note_url(source["url"], note) and not urlsplit(source["url"]).query and not urlsplit(source["url"]).fragment and
            value["channelCapability"] == {"status": "UNVERIFIED", "reason": "CHANNEL_CHECK_REQUIRED"} and value["authorization"] == "NOT_GRANTED"
        )
        if not valid: raise ValueError
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("CHANNEL_UNAVAILABLE") from None
    return value, _canonical(value)


class XhsPostCommentChannel:
    def __init__(self, page, *, cancelled=lambda: False, now=None):
        self.page = page
        self.cancelled = cancelled
        self.now = now or (lambda: datetime.now(UTC))
        self._checked = None
        self._consumed = False

    async def _identity(self, value, *, require_blank):
        if not _note_url(self.page.url, value["target"]["postId"]): raise RuntimeError("CHANNEL_UNAVAILABLE")
        container = self.page.locator("#noteContainer")
        if await container.count() != 1 or not await container.is_visible(timeout=500): raise RuntimeError("CHANNEL_UNAVAILABLE")
        own = self.page.locator(_SELF)
        if await own.count() != 1 or not await own.is_visible(timeout=500): raise RuntimeError("CHANNEL_UNAVAILABLE")
        href = await own.get_attribute("href", timeout=500)
        if _profile_id(href) != value["connection"]["accountPublicId"]: raise RuntimeError("CHANNEL_UNAVAILABLE")
        author = self.page.locator("#noteContainer .author-container a.name")
        if await author.count() != 1 or not await author.is_visible(timeout=500): raise RuntimeError("CHANNEL_UNAVAILABLE")
        author_id = _profile_id(await author.get_attribute("href", timeout=500))
        if author_id != value["target"]["authorPublicId"]: raise RuntimeError("CHANNEL_UNAVAILABLE")
        editor = self.page.locator("#content-textarea[contenteditable=true]")
        mode = self.page.locator(".content-edit")
        button = self.page.locator("button:has-text('发送')")
        mode_text = (await mode.inner_text(timeout=500)).strip() if await mode.count() == 1 else ""
        if await editor.count() != 1 or not await editor.is_visible(timeout=500) or mode_text != ("说点什么..." if require_blank else value["draft"]["savedContent"]) or await button.count() != 1 or not await button.is_visible(timeout=500):
            raise RuntimeError("CHANNEL_UNAVAILABLE")
        if require_blank and (await editor.inner_text(timeout=500)).strip(): raise RuntimeError("CHANNEL_UNAVAILABLE")
        return editor, button

    async def check(self, context):
        try:
            value, binding = _snapshot(context)
            await self._identity(value, require_blank=True)
            checked = _utc(self.now()).isoformat()
            self._checked = binding
            connection = value["connection"]
            return {"status": "AVAILABLE", "contextSha256": value["contextSha256"], "deviceId": connection["deviceId"],
                    "connectionId": connection["connectionId"], "connectionVersion": connection["connectionVersion"],
                    "accountPublicId": connection["accountPublicId"], "recipientId": value["target"]["authorPublicId"], "checkedAt": checked}
        except Exception:
            raise RuntimeError("CHANNEL_UNAVAILABLE") from None

    async def _comment_ids(self):
        locator = self.page.locator(_TOP_COMMENTS)
        result = set()
        for index in range(await locator.count()):
            raw = await locator.nth(index).get_attribute("id", timeout=500)
            if isinstance(raw, str) and re.fullmatch(r"comment-[0-9a-f]{24}", raw): result.add(raw[8:])
        return result

    async def _matching_new_comment(self, before, value):
        end = asyncio.get_running_loop().time() + 5
        while True:
            candidates = (await self._comment_ids()) - before
            matching = []
            for comment_id in candidates:
                if await self._receipt_matches(comment_id, value): matching.append(comment_id)
            if len(matching) == 1: return matching[0]
            if len(matching) > 1 or asyncio.get_running_loop().time() >= end: return None
            await asyncio.sleep(.1)

    async def _receipt_matches(self, comment_id, value):
        base = f"#noteContainer .comment-item:not(.comment-item-sub)#comment-{comment_id}"
        item = self.page.locator(base)
        if await item.count() != 1 or not await item.is_visible(timeout=500): return False
        author, text = self.page.locator(base + " a.name"), self.page.locator(base + " .note-text")
        if await author.count() != 1 or not await author.is_visible(timeout=500) or await text.count() != 1 or not await text.is_visible(timeout=500): return False
        return (_profile_id(await author.get_attribute("href", timeout=500)) == value["connection"]["accountPublicId"] and
                (await text.inner_text(timeout=500)).strip() == value["draft"]["savedContent"])

    async def _click_or_abort(self, button, deadline, timeout):
        async def stopped():
            while not self.cancelled() and _utc(self.now()) < deadline:
                await asyncio.sleep(.01)
        click_task = asyncio.create_task(button.click(timeout=timeout))
        stop_task = asyncio.create_task(stopped())
        try:
            done, _ = await asyncio.wait((click_task, stop_task), return_when=asyncio.FIRST_COMPLETED)
            if click_task in done:
                await click_task
                return True
            await asyncio.wait_for(self.page.close(run_before_unload=False), timeout=1)
            return False
        except asyncio.CancelledError:
            # Worker EOF cancels the owner task, not only our callback. Closing
            # the actual page must precede cancelling the local click Future.
            try:
                await asyncio.wait_for(self.page.close(run_before_unload=False), timeout=1)
            except Exception:
                pass  # The runtime/Job still owns physical cleanup; no receipt.
            raise
        finally:
            click_task.cancel()
            stop_task.cancel()
            await asyncio.gather(click_task, stop_task, return_exceptions=True)

    async def execute(self, context, operation):
        if self._consumed: return dict(_UNKNOWN)
        self._consumed = True
        try:
            value, binding = _snapshot(context)
            op = deepcopy(operation)
            if not _keys(op, ("requestId", "claimId", "dispatchBefore")) or not isinstance(op["dispatchBefore"], str): return dict(_UNKNOWN)
            deadline = datetime.fromisoformat(op["dispatchBefore"])
            current = _utc(self.now())
            if self._checked != binding or self.cancelled() or not _uuid(op["requestId"]) or not _uuid(op["claimId"]) or deadline.tzinfo is None or deadline <= current or (deadline.astimezone(UTC) - current).total_seconds() > 35:
                return dict(_UNKNOWN)
            editor, button = await self._identity(value, require_blank=True)
            before = await self._comment_ids()
            current = _utc(self.now())
            if self.cancelled() or current >= deadline.astimezone(UTC): return dict(_UNKNOWN)
            await editor.fill(value["draft"]["savedContent"], timeout=500)
            editor, button = await self._identity(value, require_blank=False)
            if (await editor.inner_text(timeout=500)).strip() != value["draft"]["savedContent"] or self.cancelled() or _utc(self.now()) >= deadline.astimezone(UTC): return dict(_UNKNOWN)
            remaining_ms = int((deadline.astimezone(UTC) - _utc(self.now())).total_seconds() * 1_000)
            if remaining_ms <= 0: return dict(_UNKNOWN)
            if not await self._click_or_abort(button, deadline.astimezone(UTC), min(500, remaining_ms)):
                return dict(_UNKNOWN)
            async with asyncio.timeout(5): comment_id = await self._matching_new_comment(before, value)
            if comment_id is None: return dict(_UNKNOWN)
            await self.page.reload(wait_until="domcontentloaded", timeout=5_000)
            await self._identity(value, require_blank=True)
            if not await self._receipt_matches(comment_id, value): return dict(_UNKNOWN)
            facts = {"platform": "XIAOHONGSHU", "noteId": value["target"]["postId"], "accountId": value["connection"]["accountPublicId"], "commentId": comment_id, "content": value["draft"]["savedContent"], "contextSha256": value["contextSha256"]}
            return {"status": "SENT", "confirmed": True, "proof": {"kind": "ACCEPTED", "externalId": comment_id,
                    "sha256": sha256(_canonical(facts).encode()).hexdigest(), "observedAt": _utc(self.now()).isoformat()}}
        except Exception:
            return dict(_UNKNOWN)

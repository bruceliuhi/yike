"""Strict standard-library cursor math for native Bilibili search progress."""
from __future__ import annotations

import re


_AID = re.compile(r"[1-9][0-9]{0,19}", re.ASCII)
_CURSOR_FIELDS = {"page", "consumed_ids", "refresh_next"}


def _checked_ids(value, *, maximum: int) -> list[str]:
    if type(value) is not list or len(value) > maximum:
        raise ValueError("invalid native search identifiers")
    if any(type(item) is not str or _AID.fullmatch(item) is None for item in value):
        raise ValueError("invalid native search identifier")
    if len(set(value)) != len(value):
        raise ValueError("duplicate native search identifier")
    return list(value)


def checked_cursor(value) -> dict:
    """Return a detached plain dict for one exact, valid cursor."""
    if type(value) is not dict or set(value) != _CURSOR_FIELDS:
        raise ValueError("invalid native search cursor")
    page = value["page"]
    refresh_next = value["refresh_next"]
    if type(page) is not int or not 1 <= page <= 1000:
        raise ValueError("invalid native search page")
    if type(refresh_next) is not bool:
        raise ValueError("invalid native search refresh phase")
    return {
        "page": page,
        "consumed_ids": _checked_ids(value["consumed_ids"], maximum=20),
        "refresh_next": refresh_next,
    }


def advance_cursor(before, page_ids, processed_ids, has_more) -> dict:
    """Validate a bounded page claim and deterministically derive its next cursor."""
    cursor = checked_cursor(before)
    page = _checked_ids(page_ids, maximum=20)
    processed = _checked_ids(processed_ids, maximum=5)
    if type(has_more) is not bool or (not page and has_more):
        raise ValueError("invalid native search page boundary")

    if cursor["refresh_next"]:
        available = page[:5]
    else:
        consumed_before = set(cursor["consumed_ids"])
        available = [item for item in page if item not in consumed_before][:5]
    if processed != available[: len(processed)] or (available and not processed):
        raise ValueError("processed identifiers are not an available prefix")

    if cursor["refresh_next"]:
        return {
            "page": cursor["page"],
            "consumed_ids": cursor["consumed_ids"],
            "refresh_next": False,
        }

    consumed_set = set(cursor["consumed_ids"]) | set(processed)
    consumed = [item for item in page if item in consumed_set]
    if len(consumed) == len(page):
        next_page = cursor["page"] + 1 if has_more and cursor["page"] < 1000 else 1
        consumed = []
    else:
        next_page = cursor["page"]
    return {"page": next_page, "consumed_ids": consumed, "refresh_next": True}


__all__ = ["checked_cursor", "advance_cursor"]

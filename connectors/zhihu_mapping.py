"""Pure fixed-shape Zhihu source mapping; grants no source trust."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import re


_ID=re.compile(r"[1-9][0-9]{0,19}")
_UTC=re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_KINDS={"answer","article","zvideo"}


def _error():
    from connectors.candidate_mapping import CandidateMappingError
    return CandidateMappingError()


def _id(value, *, optional=False):
    if optional and (value is None or value=="" or value=="0" or (type(value) is int and value==0)): return None
    if type(value) is int: value=str(value)
    if not isinstance(value,str) or _ID.fullmatch(value) is None: raise _error() from None
    return value


def _time(value, *, optional=False):
    if optional and (value is None or value=="" or (type(value) is int and value==0)): return None
    if type(value) is int:
        try: value=(datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(seconds=value)).isoformat(timespec="seconds").replace("+00:00","Z")
        except (OverflowError,ValueError): raise _error() from None
    if not isinstance(value,str) or _UTC.fullmatch(value) is None: raise _error() from None
    try: datetime.strptime(value,"%Y-%m-%dT%H:%M:%SZ")
    except ValueError: raise _error() from None
    return value


def _content(raw, *, allow_blank_video=False):
    if not isinstance(raw,Mapping): raise _error() from None
    kind=raw.get("content_type")
    if not isinstance(kind,str) or kind not in _KINDS: raise _error() from None
    identifier=_id(raw.get("content_id")); question=raw.get("question_id")
    if kind=="answer":
        question=_id(question)
        expected=f"https://www.zhihu.com/question/{question}/answer/{identifier}"
    elif kind=="article": expected=f"https://zhuanlan.zhihu.com/p/{identifier}"
    else: expected=f"https://www.zhihu.com/zvideo/{identifier}"
    if raw.get("content_url")!=expected: raise _error() from None
    title=raw.get("title")
    if title is not None and not isinstance(title,str): raise _error() from None
    body=raw.get("content_text")
    if not isinstance(body,str) or (not body.strip() and not (kind=="zvideo" and allow_blank_video)):
        raise _error() from None
    return kind,identifier,expected,title,body


def map_zhihu_record(raw, collector_version, query):
    if not isinstance(raw,Mapping) or not isinstance(raw.get("content"),Mapping): raise _error() from None
    content=raw["content"]
    has_comment="comment" in raw
    kind,identifier,url,title,body=_content(content,allow_blank_video=has_comment)
    source_id=f"{kind}:{identifier}"
    common={"external_source_id":source_id,"public_url":url,"title":title,"author_public_id":None,
        "collector_version":collector_version,"normalizer_version":"zhihu-candidate-v1","query":query}
    if not has_comment:
        return {"kind":"POST","external_comment_id":None,"body":body,
            "published_at":_time(content.get("created_time"),optional=True),
            "observed_at":_time(content.get("collected_at")),"parent":None,**common}
    comment=raw.get("comment")
    if not isinstance(comment,Mapping): raise _error() from None
    if comment.get("content_type")!=kind or _id(comment.get("content_id"))!=identifier: raise _error() from None
    comment_body=comment.get("content")
    if not isinstance(comment_body,str) or not comment_body.strip(): raise _error() from None
    comment_id=_id(comment.get("comment_id")); parent_id=_id(comment.get("parent_comment_id"),optional=True)
    parent=None if parent_id is None else {"external_comment_id":parent_id,"body":None,
        "author_public_id":None,"published_at":None,"public_url":None}
    return {"kind":"COMMENT","external_comment_id":comment_id,"body":comment_body,
        "published_at":_time(comment.get("publish_time"),optional=True),
        "observed_at":_time(comment.get("collected_at")),"parent":parent,**common}

"""Bounded, owner-scoped projection of retained source observations."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json

from pydantic import ValidationError

from pilot.candidate_contract import SourceContext


class SourceContentChangeError(ValueError): pass


def _iso(value):
    if isinstance(value,str): value=datetime.fromisoformat(value.replace("Z","+00:00"))
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00","Z")


def _wire_time(value):
    if isinstance(value,str): value=datetime.fromisoformat(value.replace("Z","+00:00"))
    value=value.astimezone(UTC)
    return value.replace(microsecond=(value.microsecond//1000)*1000)


def _stable(prefix,value):
    return prefix+hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(",",":"),default=str).encode()).hexdigest()


def _clip_utf16(value,limit=8000):
    used=0
    for index,char in enumerate(value):
        used+=2 if ord(char)>0xffff else 1
        if used>limit:return value[:index]
    return value


def _quote(body,other):
    index=next((i for i,(a,b) in enumerate(zip(body,other)) if a!=b),min(len(body),len(other)))
    start=max(0,index-1000)
    quote=_clip_utf16(body[start:start+4000])
    if not quote: quote=_clip_utf16(body[:4000])
    if not quote.strip(): raise SourceContentChangeError("blank source body")
    return quote


def _author_quote(body):
    quote=_clip_utf16(body)
    if quote.strip(): return quote
    index=next((index for index,char in enumerate(body) if not char.isspace()),None)
    if index is None: raise SourceContentChangeError("blank author reply")
    quote=_clip_utf16(body[max(0,index-1000):])
    if not quote.strip(): raise SourceContentChangeError("blank author reply")
    return quote


def _author_signature(row, *, author_expected=False):
    """Return a comparable author snapshot, or a reason it is not trustworthy."""
    content=row["content"]; context=content.get("source_context")
    if context is None:
        return None,"missing" if author_expected else "ordinary"
    author=content.get("author_public_id")
    if type(author) is not str or not author.strip():
        return None,"invalid"
    try:
        validated=SourceContext.model_validate(context)
        context=validated.model_dump(mode="json")
    except (ValidationError,ValueError,TypeError):
        return None,"invalid"
    replies=context["author_replies"]
    observed=_wire_time(row["observed_at"])
    published=content.get("published_at")
    try: source_published=None if published is None else _wire_time(published)
    except (TypeError,ValueError,AttributeError): return None,"invalid"
    normalized=[]; ids=set()
    for reply in replies:
        if type(reply) is not dict or set(reply)!={"id","body","published_at"}: return None,"invalid"
        identifier=reply.get("id"); body=reply.get("body")
        if (type(identifier) is not str or not identifier or identifier in ids
                or type(body) is not str or not body.strip()): return None,"invalid"
        try: reply_published=_wire_time(reply.get("published_at"))
        except (TypeError,ValueError,AttributeError): return None,"invalid"
        if reply_published>observed or (source_published is not None and reply_published<source_published):
            return None,"invalid_time"
        ids.add(identifier)
        normalized.append((identifier,body,reply["published_at"]))
    normalized.sort(key=lambda item:item[0])
    return {"author":author,"replies":{item[0]:item[1] for item in normalized},
            "signature":(content["body"],author,tuple(normalized))},None


def _project_author_changes(groups, *, anchor_observation_id, anchor_time, source_url):
    changes=[]; gaps=[]; baseline=None
    author_expected=any(row["content"].get("source_context") is not None for _observed,group in groups for row in group)
    for observed,group in groups:
        if observed<anchor_time: continue
        snapshots=[_author_signature(row,author_expected=author_expected) for row in group]
        comparable=[snapshot for snapshot,_reason in snapshots if snapshot is not None]
        signatures={snapshot["signature"] for snapshot in comparable}
        reasons={reason for _snapshot,reason in snapshots}
        if reasons.intersection({"invalid","invalid_time"}):
            raise SourceContentChangeError("invalid author evidence")
        if len(comparable)!=len(group) or len(signatures)!=1:
            if not (reasons=={"ordinary"} and len(comparable)==0):
                gaps.append("同一观察时间作者内容不一致，无法确定变化方向。"
                            if len(group)>1 else "作者身份或回复读取上下文不可比较，未生成定向变化。")
            baseline=None
            continue
        current=next(row for row in reversed(group)
                     if _author_signature(row,author_expected=author_expected)[0]["signature"]==next(iter(signatures)))
        snapshot=comparable[-1]
        if observed==anchor_time:
            anchor=next((row for row in group if str(row["observation_id"])==anchor_observation_id),None)
            baseline=(anchor,_author_signature(anchor,author_expected=author_expected)[0]) if anchor is not None else None
            continue
        if baseline is None:
            baseline=(current,snapshot); continue
        previous,previous_snapshot=baseline
        if previous_snapshot["author"]!=snapshot["author"]:
            gaps.append("作者身份发生变化，未跨作者推断回复变化。")
            baseline=(current,snapshot); continue
        previous_replies=previous_snapshot["replies"]; current_replies=snapshot["replies"]
        if set(previous_replies)-set(current_replies):
            gaps.append("本次未读到此前回复，不代表已删除。")
        for reply_id in sorted(current_replies):
            before=previous_replies.get(reply_id); after=current_replies[reply_id]
            if before==after: continue
            kind="OBSERVED_NEW" if before is None else "MODIFIED"
            identity=[anchor_observation_id,str(previous["observation_id"]),str(current["observation_id"]),
                      str(previous["version_id"]),str(current["version_id"]),reply_id,kind]
            reference=lambda row,body:{"sourceUrl":source_url,"evidenceVersion":str(row["version_id"]),
                                       "quote":_author_quote(body)}
            changes.append({"id":_stable("oac_",identity),"replyId":reply_id,"kind":kind,
                "label":"首次观察到作者回复" if kind=="OBSERVED_NEW" else "观察到作者回复正文变化",
                "fromObservationId":str(previous["observation_id"]),"toObservationId":str(current["observation_id"]),
                "detectedAt":_iso(max(_wire_time(previous["received_at"]),_wire_time(current["received_at"]))),
                "occurredAt":None,"from":None if before is None else reference(previous,before),
                "to":reference(current,after)})
            if len(changes)>200: raise SourceContentChangeError("author change limit")
        baseline=(current,snapshot)
    return changes,gaps


def project_source_content_changes(rows, *, anchor_observation_id, anchor_version_id,
                                   anchor_observed_at, anchor_received_at, source_url, anchor_body, now=None,
                                   include_author_changes=False):
    if len(rows)>200: raise SourceContentChangeError("observation limit")
    ordered=sorted(rows,key=lambda row:(_wire_time(row["observed_at"]),_wire_time(row["received_at"]),str(row["observation_id"])))
    if now is not None and any(row["observed_at"]>now or row["received_at"]>now for row in ordered):
        raise SourceContentChangeError("future observation")
    anchor=next((row for row in ordered if str(row["observation_id"])==anchor_observation_id),None)
    if (anchor is None or str(anchor["version_id"])!=anchor_version_id or _iso(anchor["observed_at"])!=_iso(anchor_observed_at)
            or _iso(anchor["received_at"])!=_iso(anchor_received_at) or anchor["content"].get("public_url")!=source_url
            or anchor["content"].get("body")!=anchor_body): raise SourceContentChangeError("anchor mismatch")
    unique=[]; seen=set()
    for row in ordered:
        version=str(row["version_id"]); content=row["content"]
        if content.get("public_url")!=source_url or type(content.get("body")) is not str: raise SourceContentChangeError("source mismatch")
        if version not in seen: seen.add(version); unique.append(row)
    if len(unique)>100: raise SourceContentChangeError("version limit")
    versions=[{"id":str(row["version_id"]),"ordinal":index+1,
        "previousVersionId":None if index==0 else str(unique[index-1]["version_id"]),
        "sourceUrl":source_url,"content":row["content"]["body"],"publishedAt":row["content"].get("published_at"),
        "observedAt":_iso(row["observed_at"]),"access":"AVAILABLE"} for index,row in enumerate(unique)]
    if include_author_changes:
        for version,row in zip(versions,unique):
            _snapshot,reason=_author_signature(row,author_expected=row["content"].get("source_context") is not None)
            if reason in {"invalid","invalid_time"}:
                raise SourceContentChangeError("invalid author evidence")
            version["authorPublicId"]=row["content"].get("author_public_id")
            version["sourceContext"]=row["content"].get("source_context")
    observations=[{"id":str(row["observation_id"]),"versionId":str(row["version_id"]),
        "observedAt":_iso(row["observed_at"]),"receivedAt":_iso(row["received_at"])} for row in ordered]
    groups=[]
    for row in ordered:
        observed=_wire_time(row["observed_at"])
        if not groups or groups[-1][0]!=observed: groups.append((observed,[row]))
        else: groups[-1][1].append(row)
    changes=[]; gaps=[]; baseline=None; anchor_time=_wire_time(anchor["observed_at"])
    anchor_context=anchor["content"].get("source_context")
    if not include_author_changes and any(_wire_time(row["observed_at"])>anchor_time
            and row["content"].get("source_context") != anchor_context for row in ordered):
        gaps.append("作者回复或读取范围发生变化，请重新查看原文；本视图尚未生成作者更新的定向变化记录。")
    for observed,group in groups:
        bodies={row["content"]["body"] for row in group}
        if len(bodies)!=1:
            gaps.append("同一观察时间存在不同正文，无法确定变化方向。")
            if observed>=anchor_time: baseline=None
            continue
        current=group[-1]; body=current["content"]["body"]
        if not body.strip():
            gaps.append("观察到空白正文，未生成定向变化。")
            if observed>=anchor_time: baseline=None
            continue
        if observed<anchor_time: continue
        if observed==anchor_time:
            baseline=current if any(str(row["observation_id"])==anchor_observation_id for row in group) else None
            continue
        if baseline is None: baseline=current; continue
        before=baseline["content"]["body"]
        if before!=body:
            detected=max(baseline["received_at"],current["received_at"])
            identity=[anchor_observation_id,str(baseline["observation_id"]),str(current["observation_id"]),
                str(baseline["version_id"]),str(current["version_id"]),_iso(baseline["observed_at"]),
                _iso(current["observed_at"]),_iso(baseline["received_at"]),_iso(current["received_at"])]
            changes.append({"id":_stable("osc_",identity),"kind":"CONTENT","label":"观察到来源正文变化",
                "from":{"sourceUrl":source_url,"evidenceVersion":str(baseline["version_id"]),
                    "quote":_quote(before,body),"field":"source.body"},
                "to":{"sourceUrl":source_url,"evidenceVersion":str(current["version_id"]),
                    "quote":_quote(body,before),"field":"source.body"},
                "fromObservationId":str(baseline["observation_id"]),"toObservationId":str(current["observation_id"]),
                "detectedAt":_iso(detected),"occurredAt":None})
        baseline=current
    result={"anchorObservationId":anchor_observation_id,"versions":versions,
        "observations":observations,"changes":changes,"gaps":list(dict.fromkeys(gaps))}
    if include_author_changes:
        author_changes,author_gaps=_project_author_changes(groups,anchor_observation_id=anchor_observation_id,
            anchor_time=anchor_time,source_url=source_url)
        result={"schemaVersion":3,**result,"authorChanges":author_changes,
                "gaps":list(dict.fromkeys(gaps+author_gaps))}
    return result


def load_source_content_changes(cursor, *, tenant, owner, evidence, now=None, include_author_changes=False):
    observation=evidence["observation"]; source=evidence["source"]
    cursor.execute("""SELECT o.source_id FROM pilot_candidate_observations o
      JOIN pilot_candidate_versions v USING(tenant_id,owner_user_id,source_id,version_id)
      WHERE o.tenant_id=%s AND o.owner_user_id=%s AND o.observation_id=%s
        AND o.version_id=%s AND o.observed_at=%s AND o.received_at=%s
        AND v.content->>'public_url'=%s AND v.content->>'body'=%s""",
      (tenant,owner,observation["id"],source["version_id"],observation["observed_at"],
       observation["received_at"],source["public_url"],source["body"]))
    row=cursor.fetchone()
    if row is None: raise SourceContentChangeError("anchor unavailable")
    cursor.execute("""SELECT o.observation_id,o.version_id,o.observed_at,o.received_at,v.content
      FROM pilot_candidate_observations o JOIN pilot_candidate_versions v
      USING(tenant_id,owner_user_id,source_id,version_id)
      WHERE o.tenant_id=%s AND o.owner_user_id=%s AND o.source_id=%s
      ORDER BY o.observed_at,o.received_at,o.observation_id LIMIT 201""",(tenant,owner,row[0]))
    rows=[dict(zip(("observation_id","version_id","observed_at","received_at","content"),item)) for item in cursor.fetchall()]
    return project_source_content_changes(rows,anchor_observation_id=observation["id"],
        anchor_version_id=source["version_id"],anchor_observed_at=observation["observed_at"],
        anchor_received_at=observation["received_at"],source_url=source["public_url"],anchor_body=source["body"],now=now,
        include_author_changes=include_author_changes)

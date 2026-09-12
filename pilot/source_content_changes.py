"""Bounded, owner-scoped projection of retained source observations."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json


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


def project_source_content_changes(rows, *, anchor_observation_id, anchor_version_id,
                                   anchor_observed_at, anchor_received_at, source_url, anchor_body, now=None):
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
    observations=[{"id":str(row["observation_id"]),"versionId":str(row["version_id"]),
        "observedAt":_iso(row["observed_at"]),"receivedAt":_iso(row["received_at"])} for row in ordered]
    groups=[]
    for row in ordered:
        observed=_wire_time(row["observed_at"])
        if not groups or groups[-1][0]!=observed: groups.append((observed,[row]))
        else: groups[-1][1].append(row)
    changes=[]; gaps=[]; baseline=None; anchor_time=_wire_time(anchor["observed_at"])
    anchor_context=anchor["content"].get("source_context")
    if any(_wire_time(row["observed_at"])>anchor_time
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
    return {"anchorObservationId":anchor_observation_id,"versions":versions,
        "observations":observations,"changes":changes,"gaps":list(dict.fromkeys(gaps))}


def load_source_content_changes(cursor, *, tenant, owner, evidence, now=None):
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
        anchor_received_at=observation["received_at"],source_url=source["public_url"],anchor_body=source["body"],now=now)

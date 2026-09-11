"""Read-only R4 opportunity research projections over retained facts."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

import psycopg

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.opportunity_evidence import OpportunityEvidenceError, evidence_view
from pilot.sessions import PilotSessionRegistry


_PLATFORM = {"XIAOHONGSHU":"xhs","DOUYIN":"douyin","BILIBILI":"bilibili",
             "ZHIHU":"zhihu","PUBLIC_WEB":"web"}
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


class OpportunityResearchError(ValueError):
    def __init__(self, code, status=400):
        allowed = {"invalid_request":422,"invalid_session":401,"opportunity_not_found":404,
            "binding_conflict":409,"snapshot_changed":409,"record_limit_exceeded":409,
            "evidence_unavailable":409,"recognition_required":409,"profile_unavailable":409,
            "strategy_unavailable":409,"platform_unavailable":409,"research_store_unavailable":503}
        self.code = code if allowed.get(code) == status else "research_store_unavailable"
        self.status = status if self.code == code else 503
        super().__init__(self.code)


def _iso(value):
    if hasattr(value,"isoformat"):
        return value.isoformat(timespec="milliseconds")
    if isinstance(value,str) and "T" in value:
        try: return datetime.fromisoformat(value.replace("Z","+00:00")).isoformat(timespec="milliseconds")
        except ValueError: pass
    return value


def _stable(prefix, value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(raw.encode()).hexdigest()


def _claims(claims):
    if (not isinstance(claims, TokenClaims) or type(claims.user_id) is not str
            or not claims.user_id or claims.user_id.strip() != claims.user_id
            or any(unicodedata.category(ch)[0] == "C" for ch in claims.user_id)):
        raise OpportunityResearchError("invalid_session",401)


class OpportunityResearchService:
    def __init__(self, store, *, supported_platforms):
        self.database = getattr(store, "database", store)
        self.sessions = PilotSessionRegistry(self.database)
        self.supported_platforms = supported_platforms

    def _active(self, cursor, claims):
        _claims(claims)
        try:
            return self.sessions.require_active(cursor, claims)
        except (InvalidPilotToken, PermissionError):
            raise OpportunityResearchError("invalid_session",401) from None

    @contextmanager
    def _snapshot(self, claims):
        try:
            with self.database.connect() as auth, auth.cursor() as auth_cursor:
                tenant = self._active(auth_cursor, claims)
                with self.database.connect() as connection, connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    cursor.execute("SELECT set_config('yike.user_id',%s,true),set_config('yike.tenant_id',%s,true)",
                                   (claims.user_id,tenant))
                    cursor.execute("SELECT clock_timestamp()")
                    now = cursor.fetchone()[0]
                    yield cursor,tenant,now
                self._active(auth_cursor, claims)
        except OpportunityResearchError:
            raise
        except psycopg.errors.SerializationFailure:
            raise OpportunityResearchError("snapshot_changed",409) from None
        except psycopg.Error:
            raise OpportunityResearchError("research_store_unavailable",503) from None

    @staticmethod
    def _window(now, identity):
        return {"snapshotId":_stable("ors_",identity),"generatedAt":_iso(now),
                "expiresAt":_iso(now+timedelta(minutes=5))}

    @staticmethod
    def _candidate_opportunity(raw, profile_status):
        content = raw["content"]
        return {"id":str(raw["candidate_id"]),"title":content.get("title") or content["body"][:120],
            "buyer":content.get("author_public_id") or "","summary":"","excerpt":content["body"],
            "matchReason":"","actionSignal":"","value":"","risk":"","contactPath":"",
            "url":content["public_url"],"platform":_PLATFORM.get(raw["platform"],raw["platform"]),
            "sourceStatus":"UNVERIFIED","profileStatus":profile_status,
            "profileVersionId":raw["profile_version_id"],"reviewer":"","reviewedAt":"",
            "publishedAt":content.get("published_at") or "","updatedAt":_iso(raw["latest_observed_at"]),
            "intentStatus":"NEW","comment":"","dm":"","sourceEvidenceVersion":str(raw["version_id"]),
            "sourceObservedAt":_iso(raw["latest_observed_at"]),"sourceEvidence":{"status":"UNAVAILABLE","reason":"NOT_CAPTURED"},
            "sample":False}

    @staticmethod
    def _quotes(assessment, source, version):
        result, seen = [], set()
        for dimension in ("businessMatch","intent","urgency","actionability"):
            for item in (assessment.get(dimension) or {}).get("citations",[]):
                field, quote = item.get("field"), item.get("quote")
                if field == "profile.description" or not isinstance(quote,str) or not quote or quote in seen:
                    continue
                addressed = source.get("body") if field == "body" else source.get("title")
                if field == "parent.body": addressed = (source.get("parent") or {}).get("body")
                if field == "parent.title": addressed = source.get("container_title") or source.get("title")
                if isinstance(addressed,str) and quote in addressed:
                    result.append({"sourceUrl":source["public_url"],"evidenceVersion":version,"quote":quote})
                    seen.add(quote)
        return result[:30]

    def list(self, claims):
        with self._snapshot(claims) as (cursor,tenant,now):
            cursor.execute("""SELECT p.candidate_id,p.profile_version_id,p.strategy_version_id,p.version_id,p.revision,
                p.latest_observed_at,p.ambiguous,s.platform,s.kind,s.external_source_id,s.external_comment_id,
                v.content,pv.status,
                (SELECT r.result FROM pilot_candidate_review_requests r
                 WHERE r.tenant_id=p.tenant_id AND r.owner_user_id=p.owner_user_id
                   AND r.candidate_id=p.candidate_id AND r.status='SUCCEEDED'
                 ORDER BY r.created_at DESC,r.request_id DESC LIMIT 1)
                FROM pilot_candidate_projections p
                JOIN pilot_candidate_sources s USING(tenant_id,owner_user_id,source_id)
                JOIN pilot_candidate_versions v USING(tenant_id,owner_user_id,source_id,version_id)
                JOIN business_profile_versions pv ON pv.tenant_id=p.tenant_id AND pv.profile_version_id=p.profile_version_id
                WHERE p.tenant_id=%s AND p.owner_user_id=%s ORDER BY p.latest_observed_at DESC,p.candidate_id
                LIMIT 1001""",(tenant,claims.user_id))
            candidates = cursor.fetchall()
            cursor.execute("""SELECT o.opportunity_id,o.title,o.buyer,o.summary,o.contact_path,o.public_excerpt,
                o.match_reason,o.action_signal,o.value_judgment,o.risk,o.reviewed_by,o.reviewed_at,
                o.profile_version_id,p.status,o.draft_comment,o.draft_dm,o.source_status,o.intent_status,
                o.updated_at,s.platform,s.public_url,s.published_at,e.included_by_user_id,e.payload,e.payload_sha256
                FROM pilot_opportunities o JOIN pilot_sources s USING(tenant_id,source_id)
                JOIN business_profile_versions p USING(tenant_id,profile_version_id)
                LEFT JOIN pilot_opportunity_evidence e USING(tenant_id,opportunity_id)
                WHERE o.tenant_id=%s ORDER BY o.created_at DESC,o.opportunity_id LIMIT 1001""",(tenant,))
            opportunities = cursor.fetchall()
            records=[]
            imported={str(row[0]) for row in opportunities}
            captured_sources=set()
            for opportunity_row in opportunities:
                profile_id,owner,payload,digest=opportunity_row[12],opportunity_row[22],opportunity_row[23],opportunity_row[24]
                if owner!=claims.user_id or payload is None: continue
                try:
                    view=evidence_view(payload,digest,opportunity_id=opportunity_row[0],profile_version_id=profile_id)
                except OpportunityEvidenceError:
                    raise OpportunityResearchError("research_store_unavailable",503) from None
                source=(view.get("snapshot") or {}).get("source")
                if source:
                    captured_sources.add((profile_id,source["platform"],source["kind"],source["external_source_id"],
                        source["external_comment_id"],source["public_url"]))
            for row in candidates:
                names=("candidate_id","profile_version_id","strategy_version_id","version_id","revision","latest_observed_at",
                    "ambiguous","platform","kind","external_source_id","external_comment_id","content","profile_status","result")
                raw=dict(zip(names,row)); decision=raw.pop("result")
                content=raw["content"]
                if (raw["profile_version_id"],raw["platform"],raw["kind"],raw["external_source_id"],
                        raw["external_comment_id"],content["public_url"]) in captured_sources:
                    continue
                if decision and (decision.get("receipt") or {}).get("opportunityId") in imported:
                    continue
                category, kind, reason, evidence, review = "UNASSESSED","","尚无当前有效分类证据。",[],{"status":"PENDING","reviewer":"","reviewedAt":None}
                candidate=(decision or {}).get("candidate") or {}
                current=(candidate.get("sourceVersionId")==str(raw["version_id"])
                    and candidate.get("profileId")==raw["profile_version_id"]
                    and candidate.get("revision")==raw["revision"])
                assessment=candidate.get("assessment") or (decision or {}).get("assessment") or {}
                source_for_quotes={"body":raw["content"]["body"],"title":raw["content"].get("title"),
                    "parent":raw["content"].get("parent"),"container_title":raw["content"].get("title"),
                    "public_url":raw["content"]["public_url"]}
                evidence=self._quotes(assessment,source_for_quotes,str(raw["version_id"]))
                if decision and decision.get("kind") == "decision" and current:
                    receipt=decision.get("receipt") or {}; candidate=decision.get("candidate") or {}
                    if receipt.get("action")=="EXCLUDE" and candidate.get("sourceVersionId")==str(raw["version_id"]):
                        category,kind,reason="EXCLUDED","EXCLUDE",receipt.get("review",{}).get("reason") or "人工排除"
                        review={"status":"RECOGNIZED","reviewer":receipt.get("reviewedBy") or claims.user_id,
                            "reviewedAt":receipt.get("reviewedAt")}
                        if not evidence:
                            category,kind,reason,review="UNASSESSED","","排除记录缺少可引用原文，待补证据。",{"status":"NEEDS_EVIDENCE","reviewer":"","reviewedAt":None}
                elif decision and decision.get("kind") == "assessment" and current and evidence:
                    choice=assessment.get("effectiveDecision") or assessment.get("decision")
                    if choice=="OBSERVE":
                        category,kind,reason="OBSERVATION",assessment.get("purchaseType") or "CHANGE",assessment.get("summary") or "有待持续观察的业务变化。"
                records.append({"opportunity":self._candidate_opportunity(raw,raw["profile_status"]),
                    "classification":{"category":category,"type":kind,"reason":reason,
                        "ruleVersion":"candidate-review-v1","evidence":evidence,"review":review}})
            for row in opportunities:
                names=("opportunity_id","title","buyer","summary","contact_path","public_excerpt","match_reason",
                    "action_signal","value","risk","reviewed_by","reviewed_at","profile_version_id","profile_status",
                    "draft_comment","draft_dm","source_status","intent_status","updated_at","platform","public_url",
                    "published_at","included_by","payload","payload_sha256")
                item=dict(zip(names,row)); payload=item["payload"]
                valid=None
                if payload is not None:
                    try:
                        valid=evidence_view(payload,item["payload_sha256"],opportunity_id=item["opportunity_id"],
                            profile_version_id=item["profile_version_id"])
                    except OpportunityEvidenceError:
                        raise OpportunityResearchError("research_store_unavailable",503) from None
                snapshot=(valid or {}).get("snapshot") if valid else None
                source=(snapshot or {}).get("source") if snapshot else None
                version=source.get("version_id") if source else None
                opportunity={"id":item["opportunity_id"],"title":item["title"],"buyer":item["buyer"],
                    "summary":item["summary"],"excerpt":source.get("body") if source else (item["public_excerpt"] or ""),
                    "matchReason":item["match_reason"],"actionSignal":item["action_signal"],"value":item["value"],
                    "risk":item["risk"],"contactPath":item["contact_path"],"url":item["public_url"],
                    "platform":_PLATFORM.get(item["platform"],item["platform"]),"sourceStatus":item["source_status"],
                    "profileStatus":item["profile_status"],"profileVersionId":item["profile_version_id"],
                    "reviewer":item["reviewed_by"],"reviewedAt":_iso(item["reviewed_at"]) or "",
                    "publishedAt":_iso(item["published_at"]) or "","updatedAt":_iso(item["updated_at"]),
                    "intentStatus":item["intent_status"],"comment":item["draft_comment"],"dm":item["draft_dm"],"sample":False}
                if version: opportunity["sourceEvidenceVersion"]=version
                opportunity["sourceEvidence"] = valid if valid else {"status":"UNAVAILABLE","reason":"NOT_CAPTURED"}
                if valid:
                    evidence=[{"sourceUrl":source["public_url"],"evidenceVersion":version,"quote":q["quote"]}
                              for q in snapshot["assessment"]["citations"]]
                    classification={"category":"OPPORTUNITY","type":"HUMAN_INCLUDED","reason":item["match_reason"] or "人工认可并导入。",
                        "ruleVersion":snapshot["assessment"]["rule_version"],"evidence":evidence,
                        "review":{"status":"RECOGNIZED","reviewer":item["reviewed_by"],"reviewedAt":_iso(item["reviewed_at"])}}
                else:
                    classification={"category":"UNASSESSED","type":"","reason":"缺少不可变来源版本，待补充证据。",
                        "ruleVersion":"legacy-unassessed-v1","evidence":[],"review":{"status":"NEEDS_EVIDENCE","reviewer":"","reviewedAt":None}}
                records.append({"opportunity":opportunity,"classification":classification})
            if len(records)>1000:
                raise OpportunityResearchError("record_limit_exceeded",409)
            result={"schemaVersion":1,"userId":claims.user_id,"accountScope":{"id":tenant,"version":1},
                    **self._window(now,[tenant,claims.user_id,records]),"records":records}
            return result

    @staticmethod
    def _binding(binding):
        required={"userId","opportunityId","profileVersionId","sourceUrl","evidenceVersion","accountScope"}
        if type(binding) is not dict or set(binding)!=required or type(binding.get("accountScope")) is not dict:
            raise OpportunityResearchError("invalid_request",422)
        scope=binding["accountScope"]
        if (set(scope)!={"id","version"} or type(scope["version"]) is not int or scope["version"]!=1
                or type(scope["id"]) is not str or not 1<=len(scope["id"].strip())<=512):
            raise OpportunityResearchError("invalid_request",422)
        for key in required-{"accountScope"}:
            if type(binding[key]) is not str or not 1<=len(binding[key].strip())<=512:
                raise OpportunityResearchError("invalid_request",422)
        if len(binding["sourceUrl"])>2048:
            raise OpportunityResearchError("invalid_request",422)
        try:
            parsed=urlsplit(binding["sourceUrl"])
            if parsed.scheme not in ("http","https") or not parsed.hostname or parsed.username or parsed.password: raise ValueError
        except ValueError:
            raise OpportunityResearchError("invalid_request",422) from None
        return binding

    def _recognized(self,cursor,tenant,claims,binding):
        cursor.execute("""SELECT o.profile_version_id,s.public_url,e.included_by_user_id,e.payload,e.payload_sha256
            FROM pilot_opportunities o JOIN pilot_sources s USING(tenant_id,source_id)
            JOIN pilot_opportunity_evidence e USING(tenant_id,opportunity_id)
            WHERE o.tenant_id=%s AND o.opportunity_id=%s""",(tenant,binding["opportunityId"]))
        row=cursor.fetchone()
        if not row: raise OpportunityResearchError("evidence_unavailable",409)
        profile,url,owner,payload,digest=row
        if binding["userId"]!=claims.user_id or binding["accountScope"]!={"id":tenant,"version":1}:
            raise OpportunityResearchError("binding_conflict",409)
        try:
            view=evidence_view(payload,digest,opportunity_id=binding["opportunityId"],profile_version_id=profile)
        except OpportunityEvidenceError:
            raise OpportunityResearchError("research_store_unavailable",503) from None
        evidence=view.get("snapshot")
        if evidence is None: raise OpportunityResearchError("evidence_unavailable",409)
        source=evidence["source"]
        if (binding["profileVersionId"]!=profile or binding["sourceUrl"]!=url
                or binding["evidenceVersion"]!=source["version_id"]):
            raise OpportunityResearchError("binding_conflict",409)
        if owner!=claims.user_id: raise OpportunityResearchError("recognition_required",409)
        return evidence

    def timeline(self,claims,binding):
        binding=self._binding(binding)
        with self._snapshot(claims) as (cursor,tenant,now):
            evidence=self._recognized(cursor,tenant,claims,binding); source=evidence["source"]
            cursor.execute("""SELECT v.version_id,v.content,min(o.observed_at),min(o.received_at) FROM pilot_candidate_sources s
                JOIN pilot_candidate_versions v USING(tenant_id,owner_user_id,source_id)
                LEFT JOIN pilot_candidate_observations o USING(tenant_id,owner_user_id,source_id,version_id)
                WHERE s.tenant_id=%s AND s.owner_user_id=%s AND s.platform=%s AND s.kind=%s
                  AND s.external_source_id IS NOT DISTINCT FROM %s AND s.external_comment_id IS NOT DISTINCT FROM %s
                GROUP BY v.version_id,v.content,v.received_at ORDER BY min(o.observed_at) NULLS LAST,v.received_at,v.version_id LIMIT 101""",
                (tenant,claims.user_id,source["platform"],source["kind"],source["external_source_id"],source["external_comment_id"]))
            rows=cursor.fetchall(); anchor=next((i for i,r in enumerate(rows) if str(r[0])==binding["evidenceVersion"]),None)
            if anchor is None: raise OpportunityResearchError("evidence_unavailable",409)
            rows=rows[:anchor+1]
            if len(rows)>100: raise OpportunityResearchError("record_limit_exceeded",409)
            versions=[]
            for i,(vid,content,observed,received) in enumerate(rows):
                versions.append({"id":str(vid),"ordinal":i+1,"previousVersionId":None if i==0 else str(rows[i-1][0]),
                    "sourceUrl":content["public_url"],"content":content["body"],"publishedAt":content.get("published_at"),
                    "observedAt":_iso(observed),"access":"AVAILABLE" if str(vid)==binding["evidenceVersion"] else "UNKNOWN"})
            cursor.execute("SELECT count(*) FROM pilot_followups WHERE tenant_id=%s AND opportunity_id=%s",
                           (tenant,binding["opportunityId"]))
            contact_count=cursor.fetchone()[0]
            gaps=[]
            if len(versions)>1: gaps.append("尚无可验证的结构化变更差异。")
            if contact_count: gaps.append("历史人工跟进缺少可验证登记人，未投影为联系事件。")
            return {"schemaVersion":1,"binding":binding,**self._window(now,[binding,[(v["id"],v["ordinal"]) for v in versions]]),
                "versions":versions,"changes":[],"contacts":[],"gaps":gaps}

    def similar(self,claims,binding,request_id):
        binding=self._binding(binding)
        if type(request_id) is not str or not _UUID.fullmatch(request_id):
            raise OpportunityResearchError("invalid_request",422)
        with self._snapshot(claims) as (cursor,tenant,now):
            evidence=self._recognized(cursor,tenant,claims,binding)
            profile_id=binding["profileVersionId"]
            cursor.execute("SELECT version,status FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s",(tenant,profile_id))
            profile=cursor.fetchone()
            if not profile or profile[1]!="CONFIRMED": raise OpportunityResearchError("profile_unavailable",409)
            strategy_id=evidence["assessment"]["strategy_version_id"]
            cursor.execute("""SELECT v.snapshot FROM pilot_research_strategy_versions v
                JOIN pilot_research_strategy_drafts d USING(tenant_id,owner_user_id,draft_id)
                WHERE v.tenant_id=%s AND v.owner_user_id=%s AND v.profile_version_id=%s
                  AND v.strategy_version_id=%s AND v.state='CONFIRMED'
                  AND d.current_version_id=v.strategy_version_id AND d.current_revision=v.draft_revision
                LIMIT 1""",(tenant,claims.user_id,profile_id,strategy_id))
            strategy=cursor.fetchone()
            if not strategy: raise OpportunityResearchError("strategy_unavailable",409)
            snapshot=strategy[0]; configuration=snapshot["configuration"]
            available=self.supported_platforms(configuration) if callable(self.supported_platforms) else self.supported_platforms
            declared=set(snapshot.get("platforms") or [])
            platforms=[]
            for value in available:
                canonical=value if value in _PLATFORM else next((key for key,item in _PLATFORM.items() if item==value),None)
                if canonical not in declared: continue
                value=_PLATFORM.get(canonical,canonical)
                if value in {"xhs","douyin","bilibili","zhihu","web"} and value not in platforms: platforms.append(value)
            if not platforms: raise OpportunityResearchError("platform_unavailable",409)
            source=evidence["source"]
            haystack="\n".join(filter(None,(source.get("title"),source.get("container_title"),source.get("body"),
                (source.get("parent") or {}).get("body"))))
            keywords=[term for term in (configuration.get("keywords") or []) if term.casefold() in haystack.casefold()][:20]
            if not keywords: raise OpportunityResearchError("strategy_unavailable",409)
            quotes=[{"sourceUrl":source["public_url"],"evidenceVersion":source["version_id"],"quote":q["quote"]}
                    for q in evidence["assessment"]["citations"]][:20]
            if not quotes: raise OpportunityResearchError("evidence_unavailable",409)
            suggestion=_stable("suggestion_",[request_id,binding,keywords,configuration.get("exclusions",[]),platforms])
            return {"schemaVersion":1,"requestId":request_id,"suggestionId":suggestion,"binding":binding,
                "generatedAt":_iso(now),"expiresAt":_iso(now+timedelta(minutes=5)),"eligible":True,
                "ineligibleReason":"","recognition":{"reviewer":claims.user_id,"reviewedAt":_iso(evidence["captured_at"]),
                "evidenceVersion":source["version_id"]},"rationale":"基于已认可来源与当前确认策略缩小同类研究范围。",
                "evidence":quotes,"profileId":profile_id,"profileVersion":profile[0],"keywords":keywords,
                "exclusions":list(configuration.get("exclusions") or [])[:20],"supportedPlatforms":platforms,
                "originalScope":configuration.get("name") or "当前确认策略",
                "additionalScope":f"仅研究同一{source['kind']}来源中命中已确认词项：{'、'.join(keywords)}。",
                "usage":{"status":"UNKNOWN","reason":"当前只读预览未接入可信搜贝计量。"}}

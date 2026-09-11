"""Owner-isolated short-coach admission, grounding and immutable replay."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib, json, re, threading
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, AfterValidator, model_validator

from pilot.auth import TokenClaims
from pilot.outreach_contract import canonical_uuid
from pilot.sessions import PilotSessionRegistry

POLICY_VERSION="short-coach-public-draft-v1"

class ShortCoachError(Exception):
    _status={"invalid_request":422,"invalid_session":401,"capability_unavailable":501,
        "disclosure_mismatch":409,"short_coach_request_conflict":409,"short_coach_processing":409,
        "short_coach_failed":502,"short_coach_quota_exceeded":429,"short_coach_result_expired":409}
    def __init__(self,code,status=None): self.code,self.status=code,status or self._status.get(code,409); super().__init__(code)

def _text(value):
    value.encode("utf-8")
    if "\0" in value: raise ValueError
    return value
Id=Annotated[str,AfterValidator(canonical_uuid)]
Text=Annotated[str,Field(max_length=8000),AfterValidator(_text)]

class _Strict(BaseModel): model_config=ConfigDict(strict=True,extra="forbid",hide_input_in_errors=True)
class AccountScope(_Strict): id:Id; version:Annotated[int,Field(ge=1,le=1)]
class CoachBinding(_Strict):
    accountScope:AccountScope; requestId:Id; opportunityId:Id; profileVersionId:Id
    sourceEvidenceVersion:Id; sourceUrl:str=Field(min_length=1,max_length=2048)
    sourceObservedAt:str=Field(min_length=1,max_length=64); channel:Literal["comment","dm"]
    draftVersion:Annotated[int,Field(ge=1,le=2147483647)]; draftHash:str=Field(pattern=r"^[a-f0-9]{64}$")
    purpose:Literal["requirement","materials","scope"]
class CoachInput(_Strict):
    binding:CoachBinding; content:Text; sourceText:Text=Field(min_length=1)
    @model_validator(mode="after")
    def bound(self):
        if hashlib.sha256(self.content.encode()).hexdigest()!=self.binding.draftHash: raise ValueError("draft hash")
        try:
            u=self.binding.sourceUrl
            if not (u.startswith("https://") or u.startswith("http://")) or "@" in u.split("/",3)[2]: raise ValueError
            d=datetime.fromisoformat(self.binding.sourceObservedAt.replace("Z","+00:00"))
            if d.tzinfo is None: raise ValueError
        except Exception: raise ValueError("source binding") from None
        return self
class Disclosure(_Strict):
    accepted:Literal[True]; inputHash:str=Field(pattern=r"^[a-f0-9]{64}$")
    modelProvider:str; modelName:str; policyVersion:Literal[POLICY_VERSION]
class GenerateInput(CoachInput): disclosure:Disclosure

def _hash(value):
    b=value.binding
    fields=[b.accountScope.id,b.accountScope.version,b.requestId,b.opportunityId,b.profileVersionId,
        b.sourceEvidenceVersion,b.sourceUrl,b.sourceObservedAt,b.channel,b.draftVersion,b.draftHash,b.purpose,
        value.content,value.sourceText]
    return hashlib.sha256(json.dumps(fields,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def _utf16_offset(text,index): return len(text[:index].encode("utf-16-le"))//2

def _same_millisecond(left, right):
    def millis(value):
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
        return int(parsed.timestamp()*1000)
    try: return millis(left)==millis(right)
    except (ValueError,TypeError,OverflowError): return False

def build_suggestion(raw,result):
    value=CoachInput.model_validate(raw); source=value.sourceText
    if type(result) is not dict or set(result)!={"content","question","quote"}: raise ValueError
    content,question,quote=(result[k] for k in ("content","question","quote"))
    if not all(type(v) is str and v and "\0" not in v for v in (content,question,quote)): raise ValueError
    for item in (content,question,quote): item.encode("utf-8")
    if (len(content)>120 or content.count("?")+content.count("？")!=1 or content.count(question)!=1
            or not question.endswith(("?","？")) or question.count("?")+question.count("？")!=1): raise ValueError
    start=source.find(quote)
    if start<0: raise ValueError
    qid=str(uuid4()); now=datetime.now(timezone.utc); b=value.binding
    quotes=[{"id":qid,"text":quote,"start":_utf16_offset(source,start),"end":_utf16_offset(source,start+len(quote)),
        "sourceUrl":b.sourceUrl,"sourceEvidenceVersion":b.sourceEvidenceVersion}]
    return {"suggestionId":str(uuid4()),"binding":b.model_dump(),"content":content,"question":question,
        "context":{"summary":"建议仅依据当前公开原文与人工草稿。","quoteIds":[qid]},"quotes":quotes,
        "checks":[{"kind":"CONTEXT","status":"SUPPORTED","message":"上下文有原文引用。","quoteIds":[qid]},
          {"kind":"ONE_QUESTION","status":"SUPPORTED","message":"短句仅含一个问题。","quoteIds":[]},
          {"kind":"PROMISE","status":"NEEDS_REVIEW","message":"服务承诺须人工复核。","quoteIds":[]},
          {"kind":"LENGTH","status":"SUPPORTED","message":"短句不超过120个字符。","quoteIds":[]}],
        "createdAt":now.isoformat().replace("+00:00","Z"),"expiresAt":(now+timedelta(minutes=5)).isoformat().replace("+00:00","Z")}

class ShortCoachService:
    def __init__(self,database,model=None):
        self.database,self.model=database,model
        self.sessions=PilotSessionRegistry(database) if database else None
        self._call_lock=threading.Lock()
    def _configured(self):
        if self.model is None or not getattr(self.model,"available",False): raise ShortCoachError("capability_unavailable")
        provider,name=getattr(self.model,"provider",None),getattr(self.model,"model",None)
        if (type(provider) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}",provider)
                or type(name) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}",name)):
            raise ShortCoachError("capability_unavailable")
        return provider,name
    def preview_unverified(self,raw):
        value=CoachInput.model_validate(raw); provider,name=self._configured()
        return {"inputHash":_hash(value),"modelProvider":provider,"modelName":name,"policyVersion":POLICY_VERSION}
    def _facts(self,cursor,claims,value):
        tenant=self.sessions.require_active(cursor,claims)
        if value.binding.accountScope.id!=tenant: raise ShortCoachError("invalid_session",403)
        cursor.execute("SELECT o.profile_version_id,o.source_status,o.intent_status,p.status,s.health,e.payload,e.payload_sha256 "
            "FROM pilot_opportunities o JOIN business_profile_versions p ON p.tenant_id=o.tenant_id AND p.profile_version_id=o.profile_version_id "
            "JOIN pilot_sources s ON s.tenant_id=o.tenant_id AND s.source_id=o.source_id LEFT JOIN pilot_opportunity_evidence e "
            "ON e.tenant_id=o.tenant_id AND e.opportunity_id=o.opportunity_id WHERE o.tenant_id=%s AND o.opportunity_id=%s FOR SHARE OF o,p,s",
            (tenant,value.binding.opportunityId))
        row=cursor.fetchone()
        if row is None: raise ShortCoachError("opportunity_not_found",404)
        if (row[0]!=value.binding.profileVersionId or row[1]!="OPEN" or row[2]=="CLOSED"
                or row[3]!="CONFIRMED" or row[4]!="OPEN"): raise ShortCoachError("short_coach_facts_changed")
        from pilot.opportunity_evidence import evidence_view
        proof=evidence_view(row[5],row[6],opportunity_id=value.binding.opportunityId,profile_version_id=value.binding.profileVersionId)
        try:
            snap=proof["snapshot"]; src=snap["source"]; obs=snap["observation"]
            same_time=_same_millisecond(obs["observed_at"],value.binding.sourceObservedAt)
            if proof["status"]!="CAPTURED" or src["body"]!=value.sourceText or src["version_id"]!=value.binding.sourceEvidenceVersion or src["public_url"]!=value.binding.sourceUrl or not same_time: raise ValueError
        except Exception: raise ShortCoachError("short_coach_facts_changed") from None
        return tenant
    def preview(self,claims,raw):
        try: value=CoachInput.model_validate(raw)
        except Exception: raise ShortCoachError("invalid_request") from None
        with self.database.connect() as conn,conn.cursor() as cursor: self._facts(cursor,claims,value)
        return self.preview_unverified(value.model_dump())
    def generate(self,claims,raw):
        try: value=GenerateInput.model_validate(raw)
        except Exception: raise ShortCoachError("invalid_request") from None
        provider,name=self._configured(); expected=self.preview_unverified(value.model_dump(exclude={"disclosure"}))
        if value.disclosure.model_dump()!={"accepted":True,**expected}: raise ShortCoachError("disclosure_mismatch")
        request_hash=expected["inputHash"]; b=value.binding
        with self.database.connect() as conn,conn.cursor() as cursor:
            tenant=self._facts(cursor,claims,value)
            lock=int.from_bytes(hashlib.sha256(f"short-coach-v1\0{tenant}".encode()).digest()[:8],"big",signed=True)
            cursor.execute("SELECT pg_advisory_xact_lock(%s)",(lock,))
            cursor.execute("SELECT request_hash,state,result,error_code,model_provider,model_name,created_at FROM pilot_short_coach_requests WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",(tenant,claims.user_id,b.requestId))
            old=cursor.fetchone()
            if old:
                if old[0]!=request_hash or old[4:6]!=(provider,name): raise ShortCoachError("short_coach_request_conflict")
                if old[1]=="PROCESSING": raise ShortCoachError("short_coach_processing")
                if old[1]=="FAILED": raise ShortCoachError(old[3] or "short_coach_failed",502)
                if old[6] < datetime.now(timezone.utc)-timedelta(minutes=5): raise ShortCoachError("short_coach_result_expired")
                return old[2]
            if not self._call_lock.acquire(blocking=False): raise ShortCoachError("short_coach_processing")
            try:
                cursor.execute("INSERT INTO pilot_short_coach_daily_quota(tenant_id,quota_day,call_count) VALUES(%s,(clock_timestamp() AT TIME ZONE 'UTC')::date,1) "
                    "ON CONFLICT(tenant_id,quota_day) DO UPDATE SET call_count=pilot_short_coach_daily_quota.call_count+1 "
                    "WHERE pilot_short_coach_daily_quota.call_count<50 RETURNING call_count",(tenant,))
                if cursor.fetchone() is None: raise ShortCoachError("short_coach_quota_exceeded")
                cursor.execute("INSERT INTO pilot_short_coach_requests(tenant_id,owner_user_id,request_id,opportunity_id,request_hash,model_provider,model_name,state) VALUES(%s,%s,%s,%s,%s,%s,%s,'PROCESSING')",
                    (tenant,claims.user_id,b.requestId,b.opportunityId,request_hash,provider,name))
            except Exception:
                self._call_lock.release()
                raise
        try:
            try:
                result=build_suggestion(value.model_dump(exclude={"disclosure"}),self.model.generate(sourceText=value.sourceText,content=value.content,channel=b.channel,purpose=b.purpose))
                state,error="SUCCEEDED",None
            except Exception:
                result,state,error=None,"FAILED","short_coach_failed"
            with self.database.connect() as conn,conn.cursor() as cursor:
                self.sessions.require_active(cursor,claims); self._facts(cursor,claims,value)
                cursor.execute("UPDATE pilot_short_coach_requests SET state=%s,result=%s::jsonb,error_code=%s,updated_at=clock_timestamp() WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s AND state='PROCESSING'",
                    (state,None if result is None else json.dumps(result,ensure_ascii=False),error,tenant,claims.user_id,b.requestId))
            if result is None: raise ShortCoachError(error,502)
            return result
        finally:
            self._call_lock.release()

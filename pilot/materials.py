from __future__ import annotations

import hashlib
import json
import secrets
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import ValidationError

from pilot.auth import TokenClaims
from pilot.material_contract import MaterialError, MaterialImpactRequest, MaterialRequest, validate_extraction
from pilot.sessions import PilotSessionRegistry


FAILURE_MESSAGE = "资料解析失败，请重试。"
FAILURE_MESSAGES = {
    "material_version_conflict": "资料版本已变化，请刷新后重试。",
    "material_not_found": "资料不存在或已移除，请刷新。",
    "material_extraction_conflict": "提取结果已变化，请刷新后核对。",
    "material_impact_invalid": "影响确认已失效，请重新查看影响。",
}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _time(value) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class MaterialStore:
    def __init__(self, database, model=None):
        self.database = database
        self.model = model
        self.sessions = PilotSessionRegistry(database)

    def _active(self, cursor, claims):
        if not isinstance(claims, TokenClaims):
            raise MaterialError("invalid_session", 401)
        try:
            return self.sessions.require_active(cursor, claims)
        except PermissionError:
            raise MaterialError("invalid_session", 401) from None

    @staticmethod
    def _lock_id(tenant, owner):
        return int.from_bytes(hashlib.sha256(
            f"materials-v1\0{tenant}\0{owner}".encode()).digest()[:8], "big", signed=True)

    @contextmanager
    def _owner_lock(self, tenant, owner):
        """Serialize owner writes without holding a business/session transaction."""
        with self.database.connect() as connection:
            # RoleDatabase performs SET ROLE first, which opens a transaction.
            # Finish it before switching to autocommit/session-lock mode.
            connection.commit()
            connection.autocommit = True
            lock = self._lock_id(tenant, owner)
            connection.execute("SELECT pg_advisory_lock(%s)", (lock,))
            try:
                yield
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock,))

    @staticmethod
    def _profile(cursor, tenant, profile):
        cursor.execute("SELECT 1 FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s", (tenant, profile))
        if cursor.fetchone() is None:
            raise MaterialError("material_profile_not_found", 404)

    @staticmethod
    def _original(cursor, tenant, owner, request_id, request_sha=None):
        cursor.execute("SELECT request_sha256,receipt FROM pilot_material_operations WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                       (tenant, owner, request_id))
        row = cursor.fetchone()
        if row is None:
            return None
        if request_sha is not None and row[0] != request_sha:
            raise MaterialError("material_request_conflict")
        return row[1]

    def _record_interrupted_parse(self, tenant, owner, request, request_sha):
        """Record only the audited no-change outcome of a pre-authorized parse."""
        receipt = {"requestId": request.requestId, "profileVersionId": request.profileVersionId,
                   "materialId": request.change.materialId, "kind": request.change.kind,
                   "status": "FAILED", "confirmedNoChange": True,
                   "message": "登录状态已变化，资料操作未执行。"}
        with self.database.connect() as conn, conn.cursor() as cursor:
            # Bind this exceptional audit write to the identity snapshot that
            # passed require_active before provider work. It never authorizes a
            # fresh revoked request and never writes a material revision.
            cursor.execute("SELECT set_config('yike.user_id',%s,true),set_config('yike.tenant_id',%s,true)",
                           (owner, tenant))
            cursor.execute("SELECT 1 FROM pilot_users WHERE tenant_id=%s AND user_id=%s", (tenant, owner))
            if cursor.fetchone() is None:
                raise MaterialError("invalid_session", 401)
            self._profile(cursor, tenant, request.profileVersionId)
            original = self._original(cursor, tenant, owner, request.requestId, request_sha)
            if original is None:
                cursor.execute("INSERT INTO pilot_material_operations "
                    "(tenant_id,owner_user_id,profile_version_id,request_id,material_id,kind,request_sha256,receipt) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)", (tenant, owner, request.profileVersionId,
                    request.requestId, request.change.materialId, request.change.kind, request_sha, _json(receipt)))
        return receipt

    @staticmethod
    def _latest(cursor, tenant, owner, profile, material):
        query = ("SELECT material_version,record,removed FROM pilot_material_revisions "
                 "WHERE tenant_id=%s AND owner_user_id=%s AND profile_version_id=%s AND material_id=%s "
                 "ORDER BY material_version DESC LIMIT 1")
        # The owner-scoped advisory lock serializes writers. Revisions stay
        # immutable, so SELECT FOR UPDATE would require an unnecessary UPDATE grant.
        cursor.execute(query, (tenant, owner, profile, material))
        return cursor.fetchone()

    def list(self, claims, profileVersionId):
        try:
            profileVersionId = MaterialImpactRequest.model_validate(dict(profileVersionId=profileVersionId,
                materialId="validation", version=1, action="remove")).profileVersionId
        except ValidationError:
            raise MaterialError("invalid_material_request", 422)
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._active(cursor, claims)
            self._profile(cursor, tenant, profileVersionId)
            cursor.execute("SELECT DISTINCT ON (material_id) material_id,record,removed FROM pilot_material_revisions "
                           "WHERE tenant_id=%s AND owner_user_id=%s AND profile_version_id=%s "
                           "ORDER BY material_id,material_version DESC", (tenant, claims.user_id, profileVersionId))
            rows = [row[1] for row in cursor.fetchall() if not row[2]]
            self._active(cursor, claims)
            return rows

    def operation(self, claims, profileVersionId, requestId):
        try:
            value = MaterialRequest.model_validate({"requestId": requestId, "profileVersionId": profileVersionId,
                "change": {"kind": "parse", "materialId": "validation", "expectedVersion": 1}})
        except ValidationError:
            raise MaterialError("invalid_material_request", 422) from None
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._active(cursor, claims)
            receipt = self._original(cursor, tenant, claims.user_id, value.requestId)
            self._active(cursor, claims)
            if receipt is None or receipt.get("profileVersionId") != profileVersionId:
                raise MaterialError("material_operation_not_found", 404)
            return receipt

    def impact(self, claims, profileVersionId, materialId, version, action):
        try:
            request = MaterialImpactRequest.model_validate(dict(profileVersionId=profileVersionId,
                materialId=materialId, version=version, action=action))
        except ValidationError:
            raise MaterialError("invalid_material_request", 422) from None
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._active(cursor, claims)
        with self._owner_lock(tenant, claims.user_id):
            with self.database.connect() as conn, conn.cursor() as cursor:
                tenant = self._active(cursor, claims)
                self._profile(cursor, tenant, request.profileVersionId)
                latest = self._latest(cursor, tenant, claims.user_id, request.profileVersionId, request.materialId)
                if latest is None or latest[2]:
                    raise MaterialError("material_not_found", 404)
                if latest[0] != request.version:
                    raise MaterialError("material_version_conflict")
                from pilot.material_references import material_impacts, material_reference_snapshot_sha
                from pilot.contact_material_references import draft_impacts, draft_snapshot_sha
                try:
                    references = material_impacts(cursor, tenant=tenant, owner=claims.user_id,
                        source_profile_version_id=request.profileVersionId, material_id=request.materialId,
                        material_version=request.version)
                    drafts = draft_impacts(cursor, tenant=tenant, owner=claims.user_id,
                        source_profile_version_id=request.profileVersionId, material_id=request.materialId,
                        material_version=request.version)
                    if len(references) + len(drafts) > 100:
                        raise ValueError("material impact exceeds display limit")
                except ValueError:
                    raise MaterialError("material_impact_too_large") from None
                snapshot_sha = material_reference_snapshot_sha(cursor, tenant=tenant, owner=claims.user_id,
                    source_profile_version_id=request.profileVersionId, material_id=request.materialId,
                    material_version=request.version)
                snapshot_sha = hashlib.sha256((snapshot_sha + draft_snapshot_sha(cursor, tenant=tenant,
                    owner=claims.user_id, source_profile_version_id=request.profileVersionId,
                    material_id=request.materialId, material_version=request.version)).encode()).hexdigest()
                token = secrets.token_urlsafe(32)
                expiry = datetime.now(UTC) + timedelta(minutes=5)
                cursor.execute("INSERT INTO pilot_material_impact_tokens "
                    "(tenant_id,owner_user_id,profile_version_id,material_id,material_version,action,token_sha256,expires_at,reference_snapshot_sha256) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (tenant, claims.user_id, request.profileVersionId,
                    request.materialId, request.version, request.action, hashlib.sha256(token.encode()).hexdigest(), expiry,
                    snapshot_sha))
                self._active(cursor, claims)
                return {"profileVersionId": request.profileVersionId, "materialId": request.materialId,
                        "version": request.version, "action": request.action, "token": token,
                        "expiresAt": _time(expiry), "references": references + [
                            {"kind":"draft","label":"联系草稿"} for _ in drafts]}

    def mutate(self, claims, raw):
        try:
            request = MaterialRequest.model_validate(raw)
        except ValidationError:
            raise MaterialError("invalid_material_request", 422) from None
        raw_request = request.model_dump(exclude_none=False)
        request_sha = _digest(raw_request)
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._active(cursor, claims)
        with self._owner_lock(tenant, claims.user_id):
            with self.database.connect() as conn, conn.cursor() as cursor:
                tenant = self._active(cursor, claims)
                self._profile(cursor, tenant, request.profileVersionId)
                original = self._original(cursor, tenant, claims.user_id, request.requestId, request_sha)
                if original is not None:
                    return original
                latest = self._latest(cursor, tenant, claims.user_id, request.profileVersionId, request.change.materialId)
            extraction = None
            model_started = False
            if request.change.kind == "parse" and latest is not None and not latest[2] and latest[0] == request.change.expectedVersion:
                try:
                    if self.model is None:
                        raise RuntimeError("model unavailable")
                    model_started = True
                    extraction = validate_extraction(self.model.extract(latest[1]["text"]), latest[1]["text"])
                except Exception:
                    extraction = None
            try:
                with self.database.connect() as conn, conn.cursor() as cursor:
                    tenant = self._active(cursor, claims)
                    self._profile(cursor, tenant, request.profileVersionId)
                    original = self._original(cursor, tenant, claims.user_id, request.requestId, request_sha)
                    if original is not None:
                        return original
                    latest = self._latest(cursor, tenant, claims.user_id, request.profileVersionId, request.change.materialId)
                    try:
                        receipt = self._apply(cursor, tenant, claims.user_id, request, latest, extraction)
                    except MaterialError as error:
                        receipt = {"requestId": request.requestId, "profileVersionId": request.profileVersionId,
                                   "materialId": request.change.materialId, "kind": request.change.kind,
                                   "status": "FAILED", "confirmedNoChange": True,
                                   "message": FAILURE_MESSAGES.get(error.code, "资料操作未执行，请刷新后重试。")}
                    cursor.execute("INSERT INTO pilot_material_operations "
                        "(tenant_id,owner_user_id,profile_version_id,request_id,material_id,kind,request_sha256,receipt) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)", (tenant, claims.user_id, request.profileVersionId,
                        request.requestId, request.change.materialId, request.change.kind, request_sha, _json(receipt)))
                    self._active(cursor, claims)
                    return receipt
            except MaterialError as error:
                if error.code == "invalid_session" and model_started:
                    self._record_interrupted_parse(tenant, claims.user_id, request, request_sha)
                raise

    def _apply(self, cursor, tenant, owner, request, latest, extraction):
        change = request.change
        old_version = 0 if latest is None else latest[0]
        if change.kind == "save":
            if (change.expectedVersion is None) != (latest is None):
                raise MaterialError("material_version_conflict")
            if latest is not None and (latest[2] or change.expectedVersion != old_version):
                raise MaterialError("material_version_conflict")
            version, status = old_version + 1, "DRAFT"
            record = {"id": change.materialId, "profileVersionId": request.profileVersionId,
                      "version": version, "updatedAt": _time(datetime.now(UTC)), "status": status,
                      **change.input.model_dump(exclude_none=True)}
            removed = False
        else:
            if latest is None or latest[2]:
                raise MaterialError("material_not_found", 404)
            if change.expectedVersion != old_version:
                raise MaterialError("material_version_conflict")
            version = old_version + 1
            record, removed = dict(latest[1]), False
            record["version"], record["updatedAt"] = version, _time(datetime.now(UTC))
            if change.kind == "parse":
                if extraction is None:
                    record["status"], record["failure"] = "FAILED", FAILURE_MESSAGE
                    record.pop("extraction", None)
                else:
                    record["status"] = "REVIEW_REQUIRED"
                    record.pop("failure", None)
                    record["extraction"] = {"id": str(uuid4()), "materialVersion": version, **extraction}
            elif change.kind == "confirm":
                current = record.get("extraction")
                if record.get("status") != "REVIEW_REQUIRED" or not current or current.get("id") != change.extractionId:
                    raise MaterialError("material_extraction_conflict")
                suggested = current.get("fields", {})
                if any(field not in suggested for field in change.fields):
                    raise MaterialError("material_extraction_conflict")
                evidence = [item for item in current["evidence"] if item["field"] in change.fields]
                record["status"] = "READY"
                record["extraction"] = {"id": current["id"], "materialVersion": version,
                                        "fields": change.fields, "evidence": evidence}
            else:
                self._consume_impact(cursor, tenant, owner, request.profileVersionId, change)
                if change.kind == "revoke":
                    record["status"] = "REVOKED"
                else:
                    removed = True
        if record.get("extraction"):
            record["extraction"]["materialVersion"] = version
        cursor.execute("INSERT INTO pilot_material_revisions "
            "(tenant_id,owner_user_id,profile_version_id,material_id,material_version,record,removed) "
            "VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s)", (tenant, owner, request.profileVersionId,
            change.materialId, version, _json(record), removed))
        if latest is not None and latest[1].get("status") == "READY" and change.kind in ("save", "revoke", "remove"):
            from pilot.material_references import invalidate_material_references
            invalidate_material_references(cursor, tenant=tenant, owner=owner,
                source_profile_version_id=request.profileVersionId, material_id=change.materialId,
                material_version=old_version, reason="material_" + change.kind)
        receipt = {"requestId": request.requestId, "profileVersionId": request.profileVersionId,
                   "materialId": change.materialId, "kind": change.kind, "status": "SUCCEEDED"}
        if change.kind != "remove":
            receipt["record"] = record
        return receipt

    @staticmethod
    def _consume_impact(cursor, tenant, owner, profile, change):
        digest = hashlib.sha256(change.impactToken.encode()).hexdigest()
        from pilot.material_references import material_reference_snapshot_sha
        from pilot.contact_material_references import draft_snapshot_sha
        snapshot_sha = material_reference_snapshot_sha(cursor, tenant=tenant, owner=owner,
            source_profile_version_id=profile, material_id=change.materialId,
            material_version=change.expectedVersion)
        snapshot_sha = hashlib.sha256((snapshot_sha + draft_snapshot_sha(cursor, tenant=tenant, owner=owner,
            source_profile_version_id=profile, material_id=change.materialId,
            material_version=change.expectedVersion)).encode()).hexdigest()
        cursor.execute("UPDATE pilot_material_impact_tokens SET consumed_at=clock_timestamp() "
            "WHERE tenant_id=%s AND owner_user_id=%s AND profile_version_id=%s AND material_id=%s "
            "AND material_version=%s AND action=%s AND token_sha256=%s AND consumed_at IS NULL "
            "AND expires_at>clock_timestamp() AND reference_snapshot_sha256=%s RETURNING 1", (tenant, owner, profile, change.materialId,
            change.expectedVersion, change.kind, digest, snapshot_sha))
        if cursor.fetchone() is None:
            raise MaterialError("material_impact_invalid")

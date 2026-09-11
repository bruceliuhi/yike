"""Minimal, tenant-safe provenance for profile fields derived from private material."""
from __future__ import annotations

import hashlib
import json
from uuid import uuid4


FIELD_LABELS = {
    "service": "服务内容",
    "customer": "目标客户",
    "regions": "服务地区",
    "preference": "项目偏好",
    "exclusions": "排除项",
}
FIELD_LIMITS = {"service": 500, "customer": 500, "regions": 500,
                "preference": 200, "exclusions": 500}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_profile_description(description: str) -> dict[str, str]:
    if type(description) is not str or not description.strip() or len(description) > 8000 or "\0" in description:
        raise ValueError("invalid canonical profile description")
    result: dict[str, str] = {}
    labels = {label: field for field, label in FIELD_LABELS.items()}
    lines = description.split("\n")
    if len(lines) != len(FIELD_LABELS):
        raise ValueError("profile description must contain the canonical five fields")
    for line in lines:
        if "：" not in line:
            raise ValueError("invalid canonical profile field")
        label, encoded = line.split("：", 1)
        field = labels.get(label)
        if field is None or field in result:
            raise ValueError("invalid canonical profile field")
        try:
            value = json.loads(encoded)
        except (TypeError, ValueError):
            raise ValueError("invalid canonical profile value") from None
        if type(value) is not str or "\0" in value or len(value) > FIELD_LIMITS[field]:
            raise ValueError("invalid canonical profile value")
        result[field] = value
    if set(result) != set(FIELD_LABELS):
        raise ValueError("missing canonical profile field")
    return result


def profile_content_digest(payload: dict, references: list[dict], *, managed: bool = True) -> str:
    if not references and not managed:
        return _sha(_json(payload))
    identities = [{key: value for key, value in reference.items() if key != "reference_id"}
                  for reference in references]
    return _sha(_json({"payload": payload, "material_references": identities}))


def minimal_references(rows) -> list[dict]:
    return [{"field": row["field_name"], "referenceId": str(row["reference_id"]),
             "valid": bool(row["valid"])} for row in rows]


def read_references(cursor, tenant: str, profile_version_id: str) -> list[dict]:
    cursor.execute("SELECT field_name,reference_id,valid FROM pilot_material_profile_references "
                   "WHERE tenant_id=%s AND target_profile_version_id=%s ORDER BY field_name",
                   (tenant, profile_version_id))
    columns = [item.name for item in cursor.description]
    return minimal_references([dict(zip(columns, row)) for row in cursor.fetchall()])


def assert_references_valid(cursor, tenant: str, profile_version_id: str) -> None:
    cursor.execute("SELECT count(*),COALESCE(bool_and(valid),true) FROM pilot_material_profile_references "
                   "WHERE tenant_id=%s AND target_profile_version_id=%s", (tenant, profile_version_id))
    count, valid = cursor.fetchone()
    if count and not valid:
        raise ValueError("profile material reference unavailable")


def reference_snapshot_sha(cursor, tenant: str, profile_version_id: str) -> str:
    cursor.execute("SELECT reference_id,field_name,adopted_value_sha256,valid FROM pilot_material_profile_references "
                   "WHERE tenant_id=%s AND target_profile_version_id=%s ORDER BY field_name,reference_id",
                   (tenant, profile_version_id))
    return _sha(_json([[str(a), b, c, d] for a, b, c, d in cursor.fetchall()]))


def resolve_references(cursor, *, tenant: str, owner: str, description: str,
                       base_profile_version_id: str | None, requested: list[dict]) -> list[dict]:
    fields = parse_profile_description(description)
    if len(requested) > 5 or len({item.get("field") for item in requested}) != len(requested):
        raise ValueError("invalid material references")
    resolved = []
    for item in requested:
        if type(item) is not dict or item.get("field") not in FIELD_LABELS:
            raise ValueError("invalid material reference")
        field = item["field"]
        adopted = _sha(fields[field])
        if set(item) == {"field", "referenceId"}:
            if not base_profile_version_id:
                raise ValueError("base profile version required")
            cursor.execute("SELECT source_owner_user_id,source_profile_version_id,material_id,material_version,"
                           "extraction_id,adopted_value_sha256 FROM pilot_material_profile_references "
                           "WHERE tenant_id=%s AND target_profile_version_id=%s AND reference_id=%s "
                           "AND field_name=%s AND valid",
                           (tenant, base_profile_version_id, item["referenceId"], field))
            row = cursor.fetchone()
            if row is None or row[5] != adopted:
                raise ValueError("material reference unavailable")
            source_owner, source_profile, material_id, version, extraction_id, value_sha = row
        elif set(item) == {"field", "sourceProfileVersionId", "materialId", "materialVersion", "extractionId"}:
            source_profile, material_id, version, extraction_id = (item["sourceProfileVersionId"], item["materialId"],
                                                                   item["materialVersion"], item["extractionId"])
            if type(version) is not int or isinstance(version, bool) or not 1 <= version <= 2147483647:
                raise ValueError("invalid material version")
            cursor.execute("SELECT owner_user_id,record FROM pilot_material_revisions WHERE tenant_id=%s "
                           "AND owner_user_id=%s AND profile_version_id=%s AND material_id=%s "
                           "AND material_version=%s AND NOT removed",
                           (tenant, owner, source_profile, material_id, version))
            source = cursor.fetchone()
            if source is None:
                raise ValueError("material source unavailable")
            source_owner, record = source
            extraction = record.get("extraction") or {}
            evidence = extraction.get("evidence") or []
            if (record.get("status") != "READY" or extraction.get("id") != extraction_id
                    or extraction.get("fields", {}).get(field) is None
                    or not any(e.get("field") == field and e.get("quote") for e in evidence)):
                raise ValueError("material source unavailable")
            value_sha = adopted
        else:
            raise ValueError("invalid material reference")
        resolved.append({"reference_id": str(uuid4()), "field_name": field,
                         "source_owner_user_id": source_owner, "source_profile_version_id": source_profile,
                         "material_id": material_id, "material_version": version, "extraction_id": extraction_id,
                         "adopted_value_sha256": value_sha})
    return sorted(resolved, key=lambda row: row["field_name"])


def reference_source_owners(cursor, *, tenant: str, requester: str, requested: list[dict]) -> set[str]:
    """Discover lock identities only; callers must revalidate every row after locking."""
    owners = {requester}
    for item in requested:
        if type(item) is dict and set(item) == {"field", "referenceId"}:
            cursor.execute("SELECT source_owner_user_id FROM pilot_material_profile_references "
                           "WHERE tenant_id=%s AND reference_id=%s", (tenant, item["referenceId"]))
            row = cursor.fetchone()
            if row is not None:
                owners.add(row[0])
    return owners


def insert_references(cursor, *, tenant: str, target_profile_version_id: str, references: list[dict]) -> None:
    for ref in references:
        cursor.execute("INSERT INTO pilot_material_profile_references(tenant_id,reference_id,target_profile_version_id,"
                       "field_name,source_owner_user_id,source_profile_version_id,material_id,material_version,extraction_id,"
                       "adopted_value_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                       (tenant, ref["reference_id"], target_profile_version_id, ref["field_name"],
                        ref["source_owner_user_id"], ref["source_profile_version_id"], ref["material_id"],
                        ref["material_version"], ref["extraction_id"], ref["adopted_value_sha256"]))


def material_impacts(cursor, *, tenant: str, owner: str, source_profile_version_id: str,
                     material_id: str, material_version: int) -> list[dict]:
    cursor.execute("SELECT target_profile_version_id,field_name FROM pilot_material_profile_references "
                   "WHERE tenant_id=%s AND source_owner_user_id=%s AND source_profile_version_id=%s "
                   "AND material_id=%s AND material_version=%s AND valid "
                   "ORDER BY target_profile_version_id,field_name LIMIT 101",
                   (tenant, owner, source_profile_version_id, material_id, material_version))
    rows = cursor.fetchall()
    if len(rows) > 100:
        raise ValueError("material impact exceeds display limit")
    return [{"kind": "profile", "label": f"业务画像 / {FIELD_LABELS[field]}"} for _profile, field in rows]


def material_reference_snapshot_sha(cursor, *, tenant: str, owner: str, source_profile_version_id: str,
                                    material_id: str, material_version: int) -> str:
    cursor.execute("SELECT reference_id,target_profile_version_id,field_name,adopted_value_sha256,valid "
                   "FROM pilot_material_profile_references WHERE tenant_id=%s AND source_owner_user_id=%s "
                   "AND source_profile_version_id=%s AND material_id=%s AND material_version=%s "
                   "ORDER BY target_profile_version_id,field_name,reference_id",
                   (tenant, owner, source_profile_version_id, material_id, material_version))
    return _sha(_json([[str(a), b, c, d, e] for a, b, c, d, e in cursor.fetchall()]))


def invalidate_material_references(cursor, *, tenant: str, owner: str, source_profile_version_id: str,
                                   material_id: str, material_version: int, reason: str) -> None:
    cursor.execute("UPDATE pilot_material_profile_references SET valid=FALSE,invalidated_at=clock_timestamp(),"
                   "invalidation_reason=%s WHERE tenant_id=%s AND source_owner_user_id=%s "
                   "AND source_profile_version_id=%s AND material_id=%s AND material_version=%s AND valid",
                   (reason, tenant, owner, source_profile_version_id, material_id, material_version))

"""Owner-private qualification for material quotations adopted by contact drafts."""
import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, AfterValidator, field_validator
from typing import Annotated

from pilot.outreach_contract import canonical_uuid


def _text(value):
    value.encode("utf-8")
    if not value.strip() or "\0" in value:
        raise ValueError("invalid material reference text")
    return value


class ContactMaterialReference(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", revalidate_instances="always")
    sourceProfileVersionId: Annotated[str, AfterValidator(canonical_uuid)]
    materialId: Annotated[str, Field(min_length=1, max_length=200), AfterValidator(_text)]
    materialVersion: Annotated[int, Field(ge=1, le=2_147_483_647)]
    extractionId: Annotated[str, Field(min_length=1, max_length=200), AfterValidator(_text)]
    quote: Annotated[str, Field(min_length=1, max_length=2000), AfterValidator(_text)]


def qualify(cursor, *, tenant, owner, references):
    values = [ContactMaterialReference.model_validate(item).model_dump() for item in references]
    identities = [json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in values]
    if len(values) > 3 or len(set(identities)) != len(values):
        raise ValueError("invalid contact material references")
    for ref in values:
        cursor.execute("SELECT material_version,record,removed FROM pilot_material_revisions "
            "WHERE tenant_id=%s AND owner_user_id=%s AND profile_version_id=%s AND material_id=%s "
            "ORDER BY material_version DESC LIMIT 1", (tenant, owner, ref["sourceProfileVersionId"], ref["materialId"]))
        row = cursor.fetchone()
        record = row[1] if row else {}
        extraction = record.get("extraction") or {}
        original = record.get("text")
        if (row is None or row[0] != ref["materialVersion"] or row[2] or record.get("status") != "READY"
                or record.get("visibility") != "external"
                or extraction.get("id") != ref["extractionId"] or type(original) is not str
                or ref["quote"] not in original):
            raise ValueError("contact material reference unavailable")
    return values


def draft_impacts(cursor, *, tenant, owner, source_profile_version_id, material_id, material_version):
    cursor.execute("SELECT request_id,opportunity_id,channel,draft_version,payload FROM ("
        "SELECT DISTINCT ON (opportunity_id,channel) request_id,opportunity_id,channel,draft_version,payload "
        "FROM pilot_contact_drafts WHERE tenant_id=%s AND owner_user_id=%s "
        "ORDER BY opportunity_id,channel,draft_version DESC) heads "
        "WHERE payload #> '{snapshot,draft,materialReferences}' @> %s::jsonb LIMIT 101",
        (tenant, owner, json.dumps([{"sourceProfileVersionId": source_profile_version_id,
            "materialId": material_id, "materialVersion": material_version}], separators=(",", ":"))))
    matches = []
    for request_id, opportunity_id, channel, version, payload in cursor.fetchall():
        refs = ((payload.get("snapshot") or {}).get("draft") or {}).get("materialReferences", [])
        for ref in refs:
            if (ref.get("sourceProfileVersionId") == source_profile_version_id
                    and ref.get("materialId") == material_id and ref.get("materialVersion") == material_version):
                matches.append((request_id, opportunity_id, channel, version, ref))
    if len(matches) > 100:
        raise ValueError("material impact exceeds display limit")
    return matches


def draft_snapshot_sha(cursor, **scope):
    rows = draft_impacts(cursor, **scope)
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()

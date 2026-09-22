"""Import an authorized evaluation manifest into the local calibration loop."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    from .business_api import API_VERSION, BusinessApiError
    from .evaluation_contract import validate_evaluation_manifest
    from .storage import Store
except ImportError:
    from business_api import API_VERSION, BusinessApiError
    from evaluation_contract import validate_evaluation_manifest
    from storage import Store


SOURCE_KIND_BY_PERMISSION = {
    "authorized_search_api": "authorized_search_api",
    "search_index_proof": "search_index_snippet",
    "licensed_index": "search_index_snippet",
    "public_url_user_supplied": "public_url_capture",
    "public_feed_user_supplied": "public_feed_capture",
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _required_text(value: Any, field: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise BusinessApiError(f"{field}_required", f"{field} 必填。")
    if len(text) > maximum:
        raise BusinessApiError(f"{field}_too_long", f"{field} 超出长度限制。")
    return text


def import_evaluation_manifest(
    store: Store,
    workspace_id: str,
    task_id: Any,
    manifest: Any,
    name: Any = "授权评测样本校准",
) -> dict[str, Any]:
    """Import reviewed, rights-backed samples without sending external actions.

    The manifest validator remains the source of truth for fields and evidence.
    Import is allowed for a partial batch so teams can accumulate 30 samples, but
    rights approval and zero external actions are hard requirements.
    """
    task_id = _required_text(task_id, "task_id", 120)
    task = store.get_task(task_id)
    if not task or task.get("workspace_id") != workspace_id:
        raise BusinessApiError("task_not_found", "任务不存在。", 404)
    report = validate_evaluation_manifest(manifest)
    if not report.get("schema_valid"):
        raise BusinessApiError("evaluation_manifest_invalid", "评测 manifest 未通过字段校验。", 400)
    dataset = manifest["dataset"]
    if dataset.get("rights_approval_verified") is not True:
        raise BusinessApiError("evaluation_rights_not_verified", "评测样本的权利证明尚未由责任人核验。", 409)
    if dataset.get("external_actions_sent") != 0:
        raise BusinessApiError("evaluation_external_actions_forbidden", "评测样本存在外部动作记录，不能进入本地校准。", 409)
    samples = manifest["samples"]
    if not samples:
        raise BusinessApiError("evaluation_samples_required", "评测 manifest 至少需要一条样本。", 400)
    batch_name = str(name or "授权评测样本校准").strip() or "授权评测样本校准"
    if len(batch_name) > 120:
        raise BusinessApiError("calibration_name_too_long", "name 超出长度限制。", 400)

    opportunity_ids: list[str] = []
    predicted_labels: dict[str, str] = {}
    created_count = 0
    deduplicated_count = 0
    reopen_verified_count = 0
    sample_to_opportunity: list[tuple[dict[str, Any], str]] = []
    dataset_id = dataset["dataset_id"]
    dataset_version = dataset["dataset_version"]
    for sample in samples:
        permission = sample["source_permission"]
        source_kind = SOURCE_KIND_BY_PERMISSION.get(permission, "manual_public_evidence")
        sample_id = sample["sample_id"]
        imported_at = _timestamp()
        item = {
            "title": str(sample.get("title") or f"评测样本 {sample_id}").strip(),
            "published_at": sample.get("published_at"),
            "industry_location": sample.get("industry"),
            "source_kind": source_kind,
            "source_url": sample["source_url"],
            "snippet": sample["snippet"],
            "evidence_level": "CAPTURED" if source_kind in {"public_url_capture", "public_feed_capture"} else "INDEXED_SNIPPET",
            "source_permission": permission,
            "evidence_type": "evaluation_manifest_sample",
            "evidence_metadata": {
                "capture_method": "authorized_evaluation_manifest_import",
                "dataset_id": dataset_id,
                "dataset_version": dataset_version,
                "sample_id": sample_id,
                "industry": sample["industry"],
                "source_family": sample["source_family"],
                "source_proof_ref": sample["source_proof_ref"],
                "license_or_rights_ref": dataset["license_or_rights_ref"],
                "evidence_fingerprint": sample["evidence_fingerprint"],
                "reopen_required": sample["reopen_required"],
                "reopen_verified": sample["reopen_verified"],
                "imported_at": imported_at,
            },
        }
        opportunity, was_duplicate = store.add_opportunity(task_id, item, "REVIEW")
        opportunity_id = opportunity["id"]
        opportunity_ids.append(opportunity_id)
        predicted_labels[opportunity_id] = sample["system_predicted_label"]
        sample_to_opportunity.append((sample, opportunity_id))
        created_count += int(not was_duplicate)
        deduplicated_count += int(was_duplicate)
        if sample["reopen_required"] and sample["reopen_verified"]:
            current = store.get_opportunity(opportunity_id) or {}
            already_imported = any(
                evidence.get("evidence_type") == "reopen_check"
                and (evidence.get("metadata") or {}).get("sample_id") == sample_id
                for evidence in current.get("evidence", [])
            )
            if not already_imported:
                store.append_evidence(
                    opportunity_id,
                    "reopen_check",
                    sample["snippet"],
                    sample["source_url"],
                    {
                        "matches_previous_snapshot": True,
                        "verification_source": "authorized_evaluation_manifest",
                        "dataset_id": dataset_id,
                        "dataset_version": dataset_version,
                        "sample_id": sample_id,
                        "evidence_fingerprint": sample["evidence_fingerprint"],
                        "reopen_verified": True,
                    },
                    captured_at=imported_at,
                )
            reopen_verified_count += 1

    batch = store.create_calibration_batch(
        workspace_id,
        batch_name,
        max(30, len(opportunity_ids)),
        opportunity_ids,
        predicted_labels=predicted_labels,
    )
    if not batch:
        raise BusinessApiError("workspace_not_found", "工作区不存在。", 404)
    for sample, opportunity_id in sample_to_opportunity:
        item = next(item for item in batch["items"] if item["opportunity_id"] == opportunity_id)
        reviewed = store.review_calibration_item(
            batch["id"],
            item["id"],
            sample["gold_label"],
            sample["reviewer"],
            sample["review_note"],
            apply_feedback=False,
        )
        if reviewed is None:
            raise BusinessApiError("calibration_item_not_found", "导入后的校准样本不存在。", 500)
    return {
        "api_version": API_VERSION,
        "batch": store.get_calibration_batch(batch["id"], workspace_id),
        "import": {
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "sample_count": len(samples),
            "created_count": created_count,
            "deduplicated_count": deduplicated_count,
            "reopen_verified_count": reopen_verified_count,
            "external_actions_sent": 0,
            "human_action_boundary": "calibration_only_no_external_actions",
        },
        "validation": report,
    }

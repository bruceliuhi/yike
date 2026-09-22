"""Read-only calibration evaluation reports for quality and production gates."""
from __future__ import annotations

from typing import Any

try:
    from .business_api import API_VERSION, BusinessApiError, _required_text
    from .storage import Store
except ImportError:
    from business_api import API_VERSION, BusinessApiError, _required_text
    from storage import Store


def get_calibration_evaluation(store: Store, workspace_id: str, batch_id: Any) -> dict[str, Any]:
    normalized = _required_text(batch_id, "batch_id", 120)
    report = store.calibration_evaluation(normalized, workspace_id)
    if not report:
        raise BusinessApiError("calibration_batch_not_found", "校准批次不存在。", 404)
    return {
        "api_version": API_VERSION,
        "batch_id": normalized,
        "evaluation": report,
    }

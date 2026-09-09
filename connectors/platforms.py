"""Platform names only; this is not an adapter or connection capability registry."""

_CANONICAL_PLATFORM_IDS = {
    "dy": "douyin",
    "bili": "bilibili",
    "xhs": "xhs",
    "douyin": "douyin",
    "bilibili": "bilibili",
    "zhihu": "zhihu",
    "web": "web",
}


def canonical_platform_id(value: object) -> str:
    """Resolve an exact known name without implying collection support."""
    if not isinstance(value, str) or value not in _CANONICAL_PLATFORM_IDS:
        raise ValueError("unknown platform ID")
    return _CANONICAL_PLATFORM_IDS[value]

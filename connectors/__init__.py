"""Pure platform parsers; importing this package does not start collection."""

from connectors.bilibili import normalize_bilibili
from connectors.douyin import normalize_douyin
from connectors.models import NormalizedSignal
from connectors.normalizer import PlatformResponseChanged
from connectors.platforms import canonical_platform_id

__all__ = [
    "NormalizedSignal",
    "PlatformResponseChanged",
    "canonical_platform_id",
    "normalize_bilibili",
    "normalize_douyin",
]

"""Compatibility exports for the standalone Douyin parser."""

from connectors.douyin import (
    Any,
    Mapping,
    NormalizedSignal,
    PlatformResponseChanged,
    first_present,
    normalize_douyin,
    normalize_time,
    optional_text,
    parse_qsl,
    raw_sha256,
    re,
    require_text,
    sha256_text,
    urlsplit,
)

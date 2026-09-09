"""Compatibility exports for the standalone Bilibili parser."""

from connectors.bilibili import (
    Any,
    Mapping,
    NormalizedSignal,
    PlatformResponseChanged,
    first_present,
    normalize_bilibili,
    normalize_time,
    optional_text,
    raw_sha256,
    re,
    require_text,
    sha256_text,
    urlsplit,
)

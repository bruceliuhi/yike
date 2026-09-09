"""Pure parser contracts using synthetic format fixtures, not platform evidence."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _connector_module(name: str):
    assert importlib.util.find_spec("connectors") is not None, (
        "The standalone connectors package must exist before parser integration"
    )
    assert importlib.util.find_spec(name) is not None, (
        f"The standalone parser module {name} must exist"
    )
    return importlib.import_module(name)


def test_connector_imports_do_not_load_application_or_database_modules():
    _connector_module("connectors")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import connectors, connectors.douyin, connectors.bilibili, "
            "connectors.models, connectors.normalizer, connectors.platforms; "
            "print(sorted(name for name in sys.modules "
            "if name.split('.')[0] in {'app', 'pilot', 'sqlite3', 'psycopg'}))",
            str(PROJECT_ROOT),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout


@pytest.mark.parametrize(
    "platform,module_name,source_id,comment_id,source_url,comment_url,source_author,author",
    [
        (
            "dy", "douyin", "7123456789", "8234567890",
            "https://www.douyin.com/video/7123456789",
            "https://www.douyin.com/video/7123456789?comment_id=8234567890",
            "creator-dy", "lead-dy",
        ),
        (
            "bili", "bilibili", "987654", "123456",
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "https://www.bilibili.com/video/BV1xx411c7mD#reply123456",
            "up-bili", "lead-bili",
        ),
    ],
)
def test_connector_synthetic_fixtures_preserve_fields_and_stable_results(
    platform, module_name, source_id, comment_id, source_url, comment_url,
    source_author, author,
):
    parser = getattr(_connector_module(f"connectors.{module_name}"), f"normalize_{module_name}")
    payload = json.loads(
        (PROJECT_ROOT / "tests" / "fixtures" / platform / "comments.json").read_text(
            encoding="utf-8"
        )
    )
    record = {"content": payload["contents"][0], "comment": payload["comments"][0]}
    original = deepcopy(record)

    item = parser(record)

    assert isinstance(item, _connector_module("connectors.models").NormalizedSignal)
    assert item.platform == platform
    assert item.external_source_id == source_id
    assert item.external_comment_id == comment_id
    assert item.source_title == original["content"]["title"]
    assert item.source_url == source_url
    assert item.comment_url == comment_url
    assert item.source_author_public_id == source_author
    assert item.author_public_id == author
    assert item.parent_comment_id == original["comment"]["parent_comment_id"]
    assert item.parent_body == original["comment"]["parent_content"]
    assert item.body == "想找能自动筛出高意向客户的工具"
    assert item.source_published_at is None
    assert item.published_at == "2026-08-11T16:00:00Z"
    assert item.collected_at == "2026-08-12T01:00:00Z"
    assert item.body_sha256 == hashlib.sha256(item.body.encode("utf-8")).hexdigest()
    raw = json.dumps(original["comment"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert item.raw_sha256 == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert item.normalizer_version == f"{platform}-v1"
    assert item.verifiable is False
    assert parser(record) == item
    assert record == original


@pytest.mark.parametrize(
    "old_module,new_module,names",
    [
        (
            "app.collectors.douyin", "connectors.douyin",
            ("normalize_douyin", "NormalizedSignal", "PlatformResponseChanged"),
        ),
        (
            "app.collectors.bilibili", "connectors.bilibili",
            ("normalize_bilibili", "NormalizedSignal", "PlatformResponseChanged"),
        ),
        (
            "app.normalizer", "connectors.normalizer",
            ("PlatformResponseChanged", "first_present", "normalize_time", "optional_text",
             "raw_sha256", "require_text", "sha256_text"),
        ),
    ],
)
def test_connector_legacy_entry_points_are_the_same_objects(old_module, new_module, names):
    new = _connector_module(new_module)
    old = importlib.import_module(old_module)
    for name in names:
        assert getattr(old, name) is getattr(new, name)


def test_connector_signal_preserves_repository_type_defaults_and_immutability():
    model = _connector_module("connectors.models").NormalizedSignal
    assert importlib.import_module("app.repository").NormalizedSignal is model
    item = model(platform="dy", body="example")
    optional_fields = (
        "external_source_id", "source_title", "source_url", "source_author_public_id",
        "external_comment_id", "parent_comment_id", "parent_body", "comment_url",
        "normalized_comment_url", "author_public_id", "source_published_at",
        "published_at", "collected_at", "raw_sha256", "body_sha256", "envelope_sha256",
        "query_cluster", "query_text", "collection_run_id", "normalizer_version",
    )
    assert asdict(item) == {
        "platform": "dy", "body": "example", "verifiable": False,
        **dict.fromkeys(optional_fields),
    }
    with pytest.raises(FrozenInstanceError):
        item.verifiable = True


def test_connector_package_is_in_wheel_configuration():
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "connectors" in config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("dy", "douyin"),
        ("bili", "bilibili"),
        ("xhs", "xhs"),
        ("douyin", "douyin"),
        ("bilibili", "bilibili"),
        ("zhihu", "zhihu"),
        ("web", "web"),
    ],
)
def test_connector_platform_names_map_only_explicit_aliases(value, expected):
    canonical_platform_id = _connector_module("connectors.platforms").canonical_platform_id
    assert canonical_platform_id(value) == expected
    assert _connector_module("connectors").canonical_platform_id is canonical_platform_id


@pytest.mark.parametrize(
    "value",
    [None, True, 1, [], {}, b"dy", "", "unknown", "weibo"]
    + [
        variant
        for platform in ("dy", "bili", "xhs", "douyin", "bilibili", "zhihu", "web")
        for variant in (platform.upper(), f" {platform}", f"{platform}\n")
    ],
)
def test_connector_platform_names_reject_unknown_and_noncanonical_values(value):
    canonical_platform_id = _connector_module("connectors.platforms").canonical_platform_id
    with pytest.raises(ValueError, match="platform"):
        canonical_platform_id(value)

import json

import pytest


def test_validates_only_distinct_canonical_public_urls():
    from pilot.research_entry_urls import validate_entry_urls

    assert validate_entry_urls(["https://www.v2ex.com/go/outsourcing"]) == (
        "https://www.v2ex.com/go/outsourcing",
    )
    assert validate_entry_urls(()) == ()
    for value in (
        "https://www.v2ex.com/go/outsourcing",
        ["https://www.v2ex.com/go/outsourcing"] * 2,
        ["https://www.v2ex.com:443/go/outsourcing"],
        ["http://www.v2ex.com/go/outsourcing"],
        ["https://www.v2ex.com/go/outsourcing"] * 21,
    ):
        with pytest.raises(ValueError, match="^invalid_entry_urls$") as raised:
            validate_entry_urls(value)
        assert repr(value) not in str(raised.value)


def test_transport_is_list_only_bounded_and_detached():
    from pilot.research_entry_urls import decode_entry_urls_json

    source = ["https://www.v2ex.com/recent"]
    assert decode_entry_urls_json(json.dumps(source)) == tuple(source)
    source.append("https://www.v2ex.com/go/qna")
    assert decode_entry_urls_json("[]") == ()
    for raw in ('null', '{}', '"[]"', '[', ' ' * (45 * 1024 + 1)):
        with pytest.raises(ValueError, match="^invalid_entry_urls$"):
            decode_entry_urls_json(raw)


def test_catalog_entries_share_the_hint_projection():
    from pilot.research_source_catalog import research_entry_hints, research_public_entry_urls

    assert research_public_entry_urls() == (
        "https://www.v2ex.com/recent",
        "https://www.v2ex.com/go/qna",
        "https://www.v2ex.com/go/outsourcing",
    )
    hints = research_entry_hints()
    assert all(url in hints for url in research_public_entry_urls())

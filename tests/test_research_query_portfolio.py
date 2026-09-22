import pytest

from pilot.research_query_portfolio import build_query_portfolio


def test_portfolio_combines_business_seed_with_buyer_action_language_and_deduplicates():
    queries = build_query_portfolio(
        query_seeds=["企业知识库", "RAG客服"],
        intent_signals=["询价", "找供应商"],
        exclusions=["招聘", "培训课程"],
        region="北京",
        max_queries=12,
    )

    assert len(queries) == 12
    assert len(queries) == len(set(queries))
    assert queries[0] == "北京 企业知识库 询价"
    assert "北京 企业知识库 找供应商" in queries
    assert any("-招聘" in query and "-培训课程" in query for query in queries)
    assert all(len(query) <= 160 for query in queries)


def test_portfolio_does_not_emit_empty_or_secret_like_input():
    with pytest.raises(ValueError, match="invalid query portfolio input"):
        build_query_portfolio(query_seeds=[""], intent_signals=["询价"])

    with pytest.raises(ValueError, match="invalid query portfolio input"):
        build_query_portfolio(query_seeds=["api_key=secret"], intent_signals=["询价"])


def test_portfolio_respects_max_queries_and_stable_order():
    kwargs = dict(
        query_seeds=["AI质检"], intent_signals=["预算", "招募团队"],
        exclusions=[], region="", max_queries=4,
    )
    first = build_query_portfolio(**kwargs)
    second = build_query_portfolio(**kwargs)
    assert first == second
    assert len(first) == 4

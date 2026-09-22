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
    assert all(len(query) <= 512 for query in queries)


def test_portfolio_falls_back_for_empty_seed_and_rejects_secret_like_input():
    assert build_query_portfolio(query_seeds=[], intent_signals=["询价"])[0] == "公开需求 询价"

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


def test_portfolio_accepts_context_field_limits():
    queries = build_query_portfolio(
        query_seeds=["x" * 160], intent_signals=["y" * 160],
        exclusions=["z" * 160], max_queries=4,
    )
    assert len(queries) == 4


def test_portfolio_covers_each_explicit_seed_before_expanding_actions():
    seeds = [f"业务{s}" for s in range(20)]
    queries = build_query_portfolio(
        query_seeds=seeds,
        intent_signals=[f"动作{a}" for a in range(5)],
        exclusions=["招聘"],
        max_queries=24,
    )

    assert all(any(seed in query for query in queries) for seed in seeds)

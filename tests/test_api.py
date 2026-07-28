from typing import get_type_hints

from app.api.main import health, search_examples


def test_health_reports_running_application() -> None:
    response = health()

    assert response["status"] == "ok"
    assert response["app"]


def test_search_returns_ranked_corpus_results() -> None:
    payload = search_examples(query_mdc="htp", k=3)

    assert payload["query"] == "htp"
    assert len(payload["results"]) == 3
    assert all("final_score" in row for row in payload["results"])


def test_search_route_declares_query_validation_contract() -> None:
    hints = get_type_hints(search_examples, include_extras=True)
    query_constraints = hints["query_mdc"].__metadata__[0]
    count_constraints = hints["k"].__metadata__[0]

    assert any(
        getattr(rule, "min_length", None) == 1
        for rule in query_constraints.metadata
    )
    assert any(getattr(rule, "ge", None) == 1 for rule in count_constraints.metadata)
    assert any(
        getattr(rule, "le", None) == 100 for rule in count_constraints.metadata
    )

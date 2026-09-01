"""The FastAPI search endpoint, called as plain functions.

`httpx` is not a dependency, so Starlette's TestClient cannot be used; the route
functions are ordinary callables and are exercised directly. That covers the part
that matters — the endpoint shares `retrieve_top_k` with the UI, so every notation the
workspace accepts must come back with the same parallels here.
"""

from typing import get_type_hints

import pytest
from fastapi import HTTPException

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


@pytest.mark.parametrize(
    ("query", "expected_prefix"),
    [
        # Manuel de Codage, as a phone user typed it: X is ẖ, D is ḏ.
        ("aHa.n stX qnd r Dw", "ꜥḥꜥ.n stẖ"),
        # Unicode, TLA conventions — the notation that used to be deleted outright.
        ("ꜥḥꜥ.n stẖ qnd", "ꜥḥꜥ.n stẖ"),
        # Plain ASCII, no special keys.
        ("htp di nsw", "ḥtp"),
    ],
)
def test_every_notation_reaches_the_same_parallels(query: str, expected_prefix: str) -> None:
    """The API has no corpus vocabulary to hand `parse_query`, so MdC detection falls
    back to the capital-letter heuristic there; it must still land on the reading."""
    payload = search_examples(query_mdc=query, k=2)

    assert payload["query"] == query
    assert payload["results"], f"no results for {query!r}"
    top = str(payload["results"][0]["transliteration_gold"])
    assert top.startswith(expected_prefix), f"{query!r} -> {top!r}"


def test_k_bounds_the_number_of_results() -> None:
    assert len(search_examples(query_mdc="htp", k=1)["results"]) == 1
    assert len(search_examples(query_mdc="htp", k=5)["results"]) == 5


def test_no_evidence_is_a_404_not_an_empty_list() -> None:
    """Tokens that occur nowhere in the corpus share no evidence with any row, and the
    endpoint says so with a status code rather than a 200 carrying nothing."""
    with pytest.raises(HTTPException) as excinfo:
        search_examples(query_mdc="zzzyx qqqqw pppfl", k=3)
    assert excinfo.value.status_code == 404


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

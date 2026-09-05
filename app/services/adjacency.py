"""Query bigrams: how much of the query's *word order* a candidate reading keeps.

Written for Experiment 2 (see docs/experiment-2-adjacency-2026-09-05.md and the
ROADMAP's pre-registration). At step 0 this module is measurement only — nothing in
the ranking path imports it — so the pre-check that decides whether the experiment
continues cannot itself have changed a single suggestion.

The definition, frozen before any run:

* Tokenisation is the ranker's own: ``tokenize_query(loose_reading_form(text))`` —
  the same pair of functions ``suggest_top_readings`` uses for the loose branch of
  its ``translit_overlap`` term and ``_evidence_summary`` uses for its shared-token
  list. The loose ASCII fold is the branch that can match an ASCII query against a
  Unicode corpus reading at all, which is what every benchmark query is.
* A ``_`` placeholder is **not** a token. It is a spanner: in ``a _ b`` the pair
  ``(a, b)`` is an eligible bigram which matches when the candidate contains
  ``a X b`` for exactly one intervening token ``X``. Any pair whose two members
  include a ``_`` earns nothing, so ``a _ _ b`` and ``_ _`` contribute nothing.
* Bigrams are taken on the **query side only**: the count is over distinct query
  bigrams, so a longer candidate is never penalised for its surplus words.
* Repeated occurrences count once (a set, not a multiset).
"""

from __future__ import annotations

from app.retrieval.tokens import tokenize_query

PLACEHOLDER = "_"

# (first token, second token, how many tokens stand between them: 0 or 1)
Bigram = tuple[str, str, int]


def adjacency_tokens(text: object) -> list[str]:
    """The ranker's own token sequence for a query or a candidate reading.

    One function, called by both step 0's pre-check and step 2's bonus, so the two
    provably tokenise the same way. `loose_reading_form` is imported inside the
    call because `app.services.suggestions` will import this module in step 2.
    """
    from app.services.suggestions import loose_reading_form

    return tokenize_query(loose_reading_form(text))


def query_bigrams(tokens: list[str]) -> list[Bigram]:
    """The distinct eligible bigrams of a query token sequence, in first-seen order."""
    found: list[Bigram] = []
    seen: set[Bigram] = set()

    def add(bigram: Bigram) -> None:
        if bigram not in seen:
            seen.add(bigram)
            found.append(bigram)

    for index in range(len(tokens) - 1):
        left, right = tokens[index], tokens[index + 1]
        if left != PLACEHOLDER and right != PLACEHOLDER:
            add((left, right, 0))
    for index in range(len(tokens) - 2):
        left, middle, right = tokens[index], tokens[index + 1], tokens[index + 2]
        if left != PLACEHOLDER and middle == PLACEHOLDER and right != PLACEHOLDER:
            add((left, right, 1))
    return found


def bigram_matches(bigram: Bigram, candidate_tokens: list[str]) -> bool:
    """Does this query bigram occur consecutively in the candidate token sequence?"""
    left, right, gap = bigram
    span = gap + 1
    for index in range(len(candidate_tokens) - span):
        if candidate_tokens[index] == left and candidate_tokens[index + span] == right:
            return True
    return False


def adjacency_score(query_bigram_list: list[Bigram], candidate_tokens: list[str]) -> float:
    """matched distinct query bigrams / total eligible query bigrams (0.0 if none)."""
    if not query_bigram_list:
        return 0.0
    matched = sum(
        1 for bigram in query_bigram_list if bigram_matches(bigram, candidate_tokens)
    )
    return matched / len(query_bigram_list)


def count_matches(query_bigram_list: list[Bigram], candidate_tokens: list[str]) -> int:
    """How many distinct query bigrams the candidate keeps consecutively."""
    return sum(
        1 for bigram in query_bigram_list if bigram_matches(bigram, candidate_tokens)
    )

"""Similar-text search across the annotation tiers (ROADMAP item E).

Nederhof's rescoped item E: search the corpus for *parallels* — the same or a similar
sentence somewhere else — in whichever tier the reader happens to hold. Three tiers:

* **transliteration** — the `mdc_norm` char 2-4-gram cosine the workspace already uses;
* **signs** — the same `NgramIndex` class over `hieroglyphs_norm`, with the sign analyzer
  below (1-3-grams of hieroglyph code points, group boundaries discarded);
* **translation** — the same class again over the `translation` column.

And his research question, "can one improve on edit distance?", which this module answers
by giving both orderings the same shape: `cosine_ranking` and `edit_reranked` return the
same kind of array, so the evaluation (`scripts/run_similar_text_eval.py`) and the UI page
can be pointed at either one without any other change. Which one each tier uses in the app
is decided by `docs/similar-text-eval-2026-09-05.md`, not here.

Nothing in this module writes anything: no uploads, no stored queries, no database.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from rapidfuzz.distance import Levenshtein

from app.data.normalizer import contains_hieroglyphs, normalize_hieroglyphs, search_fold
from app.data.query import ASCII_DIGRAPHS, MDC_MARKED_LETTERS
from app.retrieval.tfidf import NgramIndex
from app.retrieval.tokens import TOKEN_SPLIT_RE

TIER_TRANSLITERATION = "transliteration"
TIER_SIGNS = "signs"
TIER_TRANSLATION = "translation"
TIERS = (TIER_TRANSLITERATION, TIER_SIGNS, TIER_TRANSLATION)

#: How deep the edit-distance re-rank reaches. Pre-registered as 50 in
#: docs/similar-text-eval-2026-09-05.md §6 and used by both the evaluation and the UI, so
#: the page is ordered by exactly the method that was measured.
RERANK_DEPTH = 50

#: The letters that only ever appear in Egyptological transliteration. Used by
#: `detect_tier` to rule *out* a translation: no German or English sentence contains one.
EGYPTOLOGICAL_LETTERS = frozenset("ꜣꜥḥḥḫẖšṯḏꞽıṱḳ")


# --------------------------------------------------------------------------- signs


def sign_code_points(value: object) -> str:
    """The sign sequence of a normalised hieroglyph string, without group boundaries.

    `hieroglyphs_norm` separates sign *groups* (quadrats) with spaces, and those spaces
    are meaningful for the workspace, which matches group against group. They are dropped
    here on purpose: two editions of the same sentence routinely cut the same signs into
    different quadrats, and punishing that difference would measure the editors' layout
    conventions rather than the text. `<g>ID</g>` placeholders survive normalisation as
    one code point each, so a sign with no Unicode encoding still counts as one sign.
    """
    return "".join(char for char in str(value) if not char.isspace())


def sign_ngram_list(value: object, min_n: int = 1, max_n: int = 3) -> list[str]:
    """1-3-grams of hieroglyph code points — the `NgramIndex` analyzer for the sign tier.

    Deliberately shaped like `app.retrieval.tfidf._char_ngram_list` (a flat list, so it
    doubles as the `CountVectorizer` analyzer) but with two differences that follow from
    what a sign is: the unit is a code point rather than a character of a Latin string, so
    unigrams are already meaningful and `min_n` is 1; and there is no space padding,
    because the group boundaries have just been removed and there is nothing to pad.
    """
    signs = sign_code_points(value)
    return [
        signs[index : index + n]
        for n in range(min_n, max_n + 1)
        for index in range(0, max(len(signs) - n + 1, 0))
    ]


def query_sign_sequence(text: object) -> str:
    """A pasted hieroglyph string reduced to the same sign sequence the index holds."""
    return sign_code_points(normalize_hieroglyphs(text))


# ----------------------------------------------------------------- tier detection


def has_egyptological_letters(text: str) -> bool:
    return any(char in EGYPTOLOGICAL_LETTERS for char in str(text))


def has_mdc_signature(text: str) -> bool:
    """True when the text carries an MdC-only capital (`aHa`, `stX`) or one of the app's
    documented ASCII digraphs (`kh sh tj dj`)."""
    raw = str(text)
    if any(char in MDC_MARKED_LETTERS for char in raw):
        return True
    lowered = raw.lower()
    return any(digraph in lowered for digraph in (d for d, _ in ASCII_DIGRAPHS))


def _known_token_share(text: str, vocabulary: frozenset[str] | set[str]) -> tuple[int, int]:
    """(tokens of `text` the corpus is indexed under, tokens in total)."""
    tokens = [token for token in TOKEN_SPLIT_RE.split(search_fold(text)) if token]
    if not tokens:
        return 0, 0
    return sum(1 for token in tokens if token in vocabulary), len(tokens)


def detect_tier(text: object, vocabulary: set[str] | frozenset[str] | None = None) -> tuple[str, str]:
    """Which tier a pasted string belongs to, and the reason, for the page's caption.

    The rule, in order:

    1. **Unicode hieroglyphs present -> signs.** Unambiguous; nothing else contains them.
    2. **Most words are in the corpus's transliteration vocabulary -> transliteration.**
       This step is not in the original sketch of the rule, which went straight from "has
       glyphs" to "Latin words with spaces and no Egyptological letter and no MdC digraph
       -> translation". Applied as written that sends `htp dj nswt` — plain ASCII, spaced,
       no Egyptological letter, and `dj` only counts as a digraph by luck — to the
       translation tier, which is the single most likely thing a reader of this app types.
       So the vocabulary decides first where it can: the corpus itself knows whether
       `htp`, `nswt` and `zj` are Egyptian words, and it is a fact about the data rather
       than a guess about the characters. `vocabulary` is `SearchIndex.vocabulary`; when
       it is not supplied this step is skipped and the original rule stands.
    3. **Otherwise, Latin prose -> translation:** at least two whitespace-separated words,
       no Egyptological letter, no MdC signature.
    4. **Otherwise -> transliteration**, the tier this app is about.

    Returns `(tier, reason)` where `reason` is one plain sentence for the UI caption.
    """
    raw = str(text or "").strip()
    if not raw:
        return TIER_TRANSLITERATION, "Nothing typed yet."
    if contains_hieroglyphs(raw):
        return TIER_SIGNS, "The text contains Unicode hieroglyphs, so it is read as signs."
    if vocabulary:
        known, total = _known_token_share(raw, vocabulary)
        if total and known * 2 >= total:
            return (
                TIER_TRANSLITERATION,
                f"{known} of {total} words are in the corpus's transliteration "
                "vocabulary, so it is read as a transliteration.",
            )
    words = raw.split()
    if len(words) >= 2 and not has_egyptological_letters(raw) and not has_mdc_signature(raw):
        return (
            TIER_TRANSLATION,
            "Several plain-Latin words with no Egyptological letter and no Manuel de "
            "Codage spelling, so it is read as a translation.",
        )
    if has_egyptological_letters(raw):
        return TIER_TRANSLITERATION, "Egyptological letters, so it is read as a transliteration."
    if has_mdc_signature(raw):
        return (
            TIER_TRANSLITERATION,
            "Manuel de Codage or ASCII-digraph spelling, so it is read as a transliteration.",
        )
    return TIER_TRANSLITERATION, "Read as a transliteration (the default)."


# ------------------------------------------------------------------- tier indexes


def build_sign_ngram_index(df: pd.DataFrame) -> NgramIndex:
    """The sign tier's index: 1-3-grams of hieroglyph code points over `hieroglyphs_norm`."""
    return NgramIndex.build(df["hieroglyphs_norm"], analyzer=sign_ngram_list)


def build_translation_ngram_index(df: pd.DataFrame) -> NgramIndex:
    """The translation tier's index: the default char 2-4-gram analyzer over `translation`.

    Char n-grams rather than words on purpose — they carry German compounding and
    inflection ("Opfergabe" / "Opfergaben") without a stemmer for either language, and the
    tier is only ever compared within one language anyway (see the evaluation).
    """
    return NgramIndex.build(df["translation"].astype(str))


@dataclass(frozen=True)
class TierIndexes:
    """The three tier indexes, any of which may be absent for a frame that lacks the field."""

    transliteration: NgramIndex
    signs: NgramIndex | None = None
    translation: NgramIndex | None = None

    def for_tier(self, tier: str) -> NgramIndex | None:
        return {
            TIER_TRANSLITERATION: self.transliteration,
            TIER_SIGNS: self.signs,
            TIER_TRANSLATION: self.translation,
        }.get(tier)


# ----------------------------------------------------------------------- ranking


def cosine_ranking(scores: np.ndarray, exclude: int | None = None) -> np.ndarray:
    """Corpus positions ordered best-first.

    Stable, so ties fall back to corpus row order — the same order the app shows and the
    evaluation measures, rather than whatever an unstable sort happened to produce.
    `exclude` drops one row (the query's own row) by scoring it below everything else.
    """
    working = scores
    if exclude is not None:
        working = scores.copy()
        working[exclude] = -np.inf
    return np.argsort(-working, kind="stable")


def edit_similarity(left: object, right: object) -> float:
    """Normalised Levenshtein similarity in [0, 1] — the "edit distance" of item E.

    `rapidfuzz.distance.Levenshtein.normalized_similarity`, i.e. `1 - distance / max(len)`.
    Named here so the evaluation and the UI cannot end up using two different notions of
    edit distance.
    """
    return float(Levenshtein.normalized_similarity(str(left), str(right)))


def edit_reranked(
    order: np.ndarray,
    query_text: str,
    texts: np.ndarray | list[str],
    depth: int = RERANK_DEPTH,
) -> tuple[np.ndarray, dict[int, float]]:
    """Re-order the first `depth` of `order` by edit similarity to `query_text`.

    Only the head is touched; everything below `depth` keeps the cosine order. That is
    what makes this a *re-rank* of a retrieval rather than a second retrieval — an edit
    distance against all 130,472 rows per query is neither what was asked for nor
    affordable in a page render.

    Returns the new ordering and the edit similarity of every re-ranked position, which
    the UI shows on the card and the evaluation ignores.
    """
    head = order[:depth]
    similarities = {int(position): edit_similarity(query_text, texts[int(position)]) for position in head}
    reordered = sorted(range(len(head)), key=lambda i: -similarities[int(head[i])])
    # `sorted` is stable, so equal edit similarities keep the cosine order between them.
    new_head = head[np.asarray(reordered, dtype=np.int64)] if len(head) else head
    return np.concatenate([new_head, order[depth:]]), similarities


def ranks_from_order(order: np.ndarray, n_rows: int) -> np.ndarray:
    """1-based rank per corpus position, from an ordering — what rank fusion needs."""
    ranks = np.empty(n_rows, dtype=np.float64)
    ranks[order] = np.arange(1, n_rows + 1, dtype=np.float64)
    return ranks


def reciprocal_rank_fusion(orders: list[np.ndarray], n_rows: int, k: int = 60) -> np.ndarray:
    """RRF over several tier orderings: `sum(1 / (k + rank))`, higher is better."""
    fused = np.zeros(n_rows, dtype=np.float64)
    for order in orders:
        fused += 1.0 / (k + ranks_from_order(order, n_rows))
    return fused


def min_max(scores: np.ndarray) -> np.ndarray:
    low, high = float(np.min(scores)), float(np.max(scores))
    if high <= low:
        return np.zeros_like(scores)
    return (scores - low) / (high - low)


def score_mean(score_arrays: list[np.ndarray]) -> np.ndarray:
    """Mean of the min-max normalised tier scores — the second combination rule."""
    if not score_arrays:
        raise ValueError("score_mean needs at least one tier")
    return np.mean([min_max(scores) for scores in score_arrays], axis=0)

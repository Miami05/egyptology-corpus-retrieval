from __future__ import annotations

import re
from dataclasses import dataclass, replace
from math import log

import pandas as pd

from app.data.normalizer import pipe_list_to_set

TOKEN_SPLIT_RE = re.compile(r"[\s:\-]+")


@dataclass(frozen=True)
class ScoreWeights:
    """Relative weight of each ranking signal.

    Absolute values do not matter: `combine_scores` renormalises over the signals
    that actually carry information for a given query, so the final score always
    spans a comparable range. That matters because several metadata signals below
    are empty for large parts of the corpus, and previously their weight was
    silently lost, capping a perfect text match at roughly 0.60.
    """

    # Live-signal weights chosen by scripts/tune_ranking_weights.py: swept on a
    # 40-query tune split, then scored once on a disjoint 40-query holdout, where
    # they beat the previous values (top-3 useful-family 0.675 -> 0.725, MRR
    # 0.592 -> 0.617). IDF overlap carries the most weight because rare shared
    # tokens identify a parallel far better than ubiquitous particles do.
    fuzzy: float = 0.35
    tfidf: float = 0.18
    overlap: float = 0.10
    idf_overlap: float = 0.40
    exact: float = 0.10
    reading_order: float = 0.10
    # Sign-based signals. They are zero for a transliteration query and the
    # transliteration signals are zero for a sign query, and combine_scores drops
    # whichever set is inactive, so one weight set serves both input modes.
    glyph_overlap: float = 0.30
    glyph_idf_overlap: float = 0.50
    glyph_exact: float = 0.20
    deity: float = 0.10
    formula_type: float = 0.06
    formula_slot: float = 0.04
    offering: float = 0.04
    recipient: float = 0.03
    aesthetic: float = 0.03

    def replace(self, **changes: float) -> ScoreWeights:
        return replace(self, **changes)


# Maps each weight field to the scored column it applies to.
WEIGHT_COLUMNS: dict[str, str] = {
    "fuzzy": "fuzzy_score",
    "tfidf": "tfidf_score",
    "overlap": "overlap_score",
    "idf_overlap": "idf_overlap_score",
    "exact": "exact_bonus",
    "reading_order": "reading_order_overlap",
    "deity": "deity_bonus",
    "formula_type": "formula_type_bonus",
    "formula_slot": "formula_slot_bonus",
    "offering": "offering_overlap",
    "recipient": "recipient_bonus",
    "aesthetic": "aesthetic_bonus",
    "glyph_overlap": "glyph_overlap_score",
    "glyph_idf_overlap": "glyph_idf_overlap_score",
    "glyph_exact": "glyph_exact_bonus",
}

DEFAULT_WEIGHTS = ScoreWeights()

KNOWN_DEITIES = {
    "wsir": "wsir",
    "inpw": "inpw",
    "ra": "ra",
    "pth": "pth",
    "hwt-hr": "hwt-hr",
    "anpu": "inpw",
}

KNOWN_OFFERING_ITEMS = {
    "t": "bread",
    "hnqt": "beer",
    "k3w": "oxen",
    "3pdw": "fowl",
    "irp": "wine",
    "sšmn": "oil",
}


def tokenize_query(text: str) -> list[str]:
    raw = str(text).strip().lower()
    return [tok for tok in TOKEN_SPLIT_RE.split(raw) if tok]


def token_overlap_score(query: str, candidate: str) -> float:
    q_tokens = set(tokenize_query(query))
    c_tokens = set(tokenize_query(candidate))
    if not q_tokens or not c_tokens:
        return 0.0
    return len(q_tokens & c_tokens) / len(q_tokens | c_tokens)


def document_frequencies(values: pd.Series) -> dict[str, int]:
    """How many corpus rows each token appears in."""
    frequencies: dict[str, int] = {}
    for value in values:
        for token in set(tokenize_query(value)):
            frequencies[token] = frequencies.get(token, 0) + 1
    return frequencies


def idf_overlap_score(
    query: str,
    candidate: str,
    frequencies: dict[str, int],
    corpus_size: int,
) -> float:
    """Token overlap weighted by how rare each shared token is.

    Plain Jaccard gives `n`, `k`, `f`, `m` the same say as `ḫnt.ꞽ` or `sḫnti̯`, so a
    query's distinctive tokens get drowned out by grammatical particles that appear
    in most rows. Weighting each token by inverse document frequency makes the rare,
    identifying tokens decide the ranking.
    """
    q_tokens = set(tokenize_query(query))
    c_tokens = set(tokenize_query(candidate))
    if not q_tokens or not c_tokens:
        return 0.0

    def weight(token: str) -> float:
        # +1 smoothing keeps an unseen query token finite; a token in every row
        # contributes almost nothing.
        return log((corpus_size + 1) / (frequencies.get(token, 0) + 1)) + 1.0

    shared = q_tokens & c_tokens
    union = q_tokens | c_tokens
    union_weight = sum(weight(token) for token in union)
    if union_weight <= 0:
        return 0.0
    return sum(weight(token) for token in shared) / union_weight


def exact_label_bonus(query_value: str, candidate_value: str) -> float:
    if not query_value or not candidate_value:
        return 0.0
    return 1.0 if str(query_value).strip() == str(candidate_value).strip() else 0.0


def pipe_overlap_score(query_value: str, candidate_value: str) -> float:
    q_set = pipe_list_to_set(str(query_value))
    c_set = pipe_list_to_set(str(candidate_value))
    if not q_set or not c_set:
        return 0.0
    return len(q_set & c_set) / len(q_set | c_set)


def extract_query_features(
    query_mdc_norm: str,
    query_reading_order_norm: str = "",
) -> dict:
    """
    Rule-based Phase 3 feature extraction.

    This is still a baseline, but it is safer than substring matching
    and better aligned with real offering-formula patterns.
    """
    source_text = query_reading_order_norm or query_mdc_norm
    tokens = tokenize_query(source_text)
    token_set = set(tokens)
    detected_deity = ""
    for token in tokens:
        if token in KNOWN_DEITIES:
            detected_deity += KNOWN_DEITIES[token]
            break
    formula_type = ""
    formula_slot = ""
    opening_pattern = {"htp", "di", "nsw"}
    invocation_pattern = {"prt", "hrw"}
    if opening_pattern.issubset(token_set):
        formula_type = "offering_formula"
        formula_slot = "opening"
    elif invocation_pattern.issubset(token_set):
        formula_type = "invocation_formula"
        formula_slot = "invocation"
    detected_items: list[str] = []
    for token in tokens:
        item = KNOWN_OFFERING_ITEMS.get(token)
        if item and item not in detected_items:
            detected_items.append(item)
    offering_items = "|".join(detected_items)
    recipient = ""
    if "k3" in token_set and "im3hw" in token_set:
        recipient = "revered_one"
    elif detected_deity == "wsir":
        recipient = "osiris"
    elif detected_deity == "inpw":
        recipient = "anubis"
    return {
        "query_deity_norm": detected_deity,
        "query_formula_type_norm": formula_type,
        "query_formula_slot_norm": formula_slot,
        "query_offering_items_norm": offering_items,
        "query_recipient_norm": recipient,
    }


def combine_scores(
    df: pd.DataFrame,
    query_mdc_norm: str,
    query_reading_order_norm: str = "",
    weights: ScoreWeights = DEFAULT_WEIGHTS,
    query_hieroglyphs_norm: str = "",
) -> pd.DataFrame:
    out = df.copy()
    if "fuzzy_score" not in out.columns:
        out["fuzzy_score"] = 0.0
    if "tfidf_score" not in out.columns:
        out["tfidf_score"] = 0.0
    if "exact_bonus" not in out.columns:
        out["exact_bonus"] = 0.0
    out["overlap_score"] = out["mdc_norm"].map(
        lambda value: token_overlap_score(query_mdc_norm, value)
    )
    frequencies = document_frequencies(out["mdc_norm"])
    corpus_size = len(out)
    out["idf_overlap_score"] = out["mdc_norm"].map(
        lambda value: idf_overlap_score(
            query_mdc_norm, value, frequencies, corpus_size
        )
    )

    # Sign-sequence matching, used when the query is written in hieroglyphs.
    if query_hieroglyphs_norm and "hieroglyphs_norm" in out.columns:
        glyph_frequencies = document_frequencies(out["hieroglyphs_norm"])
        out["glyph_overlap_score"] = out["hieroglyphs_norm"].map(
            lambda value: token_overlap_score(query_hieroglyphs_norm, value)
        )
        out["glyph_idf_overlap_score"] = out["hieroglyphs_norm"].map(
            lambda value: idf_overlap_score(
                query_hieroglyphs_norm, value, glyph_frequencies, corpus_size
            )
        )
        out["glyph_exact_bonus"] = out["hieroglyphs_norm"].map(
            lambda value: 1.0 if str(value).strip() == query_hieroglyphs_norm else 0.0
        )
    else:
        out["glyph_overlap_score"] = 0.0
        out["glyph_idf_overlap_score"] = 0.0
        out["glyph_exact_bonus"] = 0.0
    out["reading_order_overlap"] = out["normalized_reading_order_norm"].map(
        lambda value: (
            token_overlap_score(query_reading_order_norm, value)
            if query_reading_order_norm
            else 0.0
        )
    )
    query_features = extract_query_features(
        query_mdc_norm=query_mdc_norm,
        query_reading_order_norm=query_reading_order_norm,
    )
    out["deity_bonus"] = out["deity_norm"].map(
        lambda value: exact_label_bonus(query_features["query_deity_norm"], value)
    )
    out["formula_type_bonus"] = out["formula_type_norm"].map(
        lambda value: exact_label_bonus(
            query_features["query_formula_type_norm"], value
        )
    )
    out["formula_slot_bonus"] = out["formula_slot_norm"].map(
        lambda value: exact_label_bonus(
            query_features["query_formula_slot_norm"], value
        )
    )
    out["offering_overlap"] = out["offering_items_norm"].map(
        lambda value: pipe_overlap_score(
            query_features["query_offering_items_norm"], value
        )
    )
    out["recipient_bonus"] = out["recipient_norm"].map(
        lambda value: exact_label_bonus(query_features["query_recipient_norm"], value)
    )
    out["aesthetic_bonus"] = out["aesthetic_arrangement_flag_bool"].map(
        lambda value: 0.03 if value and query_reading_order_norm else 0.0
    )
    # Renormalise over the signals that actually discriminate for this query. A
    # signal that is zero for every candidate — an empty metadata column, or the
    # reading-order overlap when the user supplied no reading order — tells us
    # nothing, so letting it keep its share of the weight would just compress every
    # score toward zero and make confidences incomparable between queries.
    active: dict[str, float] = {}
    for field, column in WEIGHT_COLUMNS.items():
        weight = getattr(weights, field)
        if weight <= 0 or column not in out.columns:
            continue
        if float(out[column].abs().max() or 0.0) <= 0.0:
            continue
        active[column] = weight

    total_weight = sum(active.values())
    if total_weight <= 0:
        out["final_score"] = 0.0
    else:
        score = pd.Series(0.0, index=out.index)
        for column, weight in active.items():
            score = score + (weight / total_weight) * out[column]
        out["final_score"] = score
    return out.sort_values("final_score", ascending=False)

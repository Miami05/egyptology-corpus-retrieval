"""Run the competitive ambiguity benchmark (item A: --stage none/auto/declared).

`data/benchmarks/competitive_ambiguity_eval_queries_v4.csv` carries a `language_stage`
column, one stage per row, derived by `derive_v4_declared_stage` (see its docstring
and `app.services.stage.derive_stage_from_period` for the exact rule) and computed
once, not at eval time. To regenerate it after the benchmark or the corpus changes:

    python -c "
    import pandas as pd
    from scripts.run_competitive_ambiguity_eval import derive_v4_declared_stage
    from app.data.loader import load_examples_csv
    bench = pd.read_csv('data/benchmarks/competitive_ambiguity_eval_queries_v4.csv')
    corpus = load_examples_csv('data/processed/examples.csv')
    keyed = corpus.set_index(['source_text_id', 'source_sentence_id'])['period']
    def stage_for(row):
        period = keyed.get((row.expected_source_text_id, row.expected_source_sentence_id), '')
        return derive_v4_declared_stage(row.expected_source_text_id, period) or ''
    bench['language_stage'] = bench.apply(stage_for, axis=1)
    bench.to_csv('data/benchmarks/competitive_ambiguity_eval_queries_v4.csv', index=False)
    "

Older benchmark files (v1/v2/v3, and the plain-named v1 file) have no such column;
`--stage declared` against one of them declares no stage for any row.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.data.query import parse_query
from app.services.retrieval import retrieve_top_k
from app.services.stage import (
    build_stage_resources,
    derive_stage_from_period,
    infer_stage,
    normalize_stage,
    stage_base_rates,
)
from app.services.suggestions import (
    DEFAULT_SUGGESTION_WEIGHTS,
    SUGGESTION_PRESET_ENV,
    SuggestionWeights,
    canonical_reading,
    loose_reading_form,
    name_normalised_reading_key,
    notation_folded_reading_key,
    suggest_top_readings,
)
from scripts.build_competitive_ambiguity_benchmark import STOP_TOKENS
from scripts.eval_guards import TwinGuard

EXAMPLES_PATH = "data/processed/examples.csv"
# Default for `_load_benchmark` callers that pass nothing. The CLI no longer has a
# default benchmark (--benchmark is required, audit A26): this file is v1, where 17 of
# 20 targets have an edition twin in the corpus, so a bare run measured memorisation.
BENCHMARK_PATH = "data/benchmarks/competitive_ambiguity_eval_queries.csv"


def derive_v4_declared_stage(expected_source_text_id: object, period: object) -> str | None:
    """The documented rule behind the v4 benchmark's `language_stage` column.

    A thin, benchmark-specific name for `app.services.stage.derive_stage_from_period`
    — the exact same rule (TLA source-id prefix, else `period` keywords, ambiguous
    or absent -> None), applied here to a benchmark row's *expected target* columns
    rather than a corpus row's own. Kept as a separate name because the
    regeneration command in this module's docstring calls it explicitly; the rule
    itself now lives in one place (`app/services/stage.py`) so this CSV-generation
    path and `compatible_frame`'s load-time derivation can never drift apart.
    """
    return derive_stage_from_period(expected_source_text_id, period)


REQUIRED_COLUMNS = [
    "benchmark_id",
    "query_input",
    "query_type",
    "expected_transliteration",
    "expected_source_text_id",
    "expected_source_sentence_id",
    "expected_key_tokens",
    "expected_lemma_ids",
    "acceptable_token_overlap_threshold",
    "notes",
]


def _row_key(row: pd.Series) -> tuple[str, str]:
    return str(row["source_text_id"]), str(row["source_sentence_id"])


def _exclude_expected(
    examples_df: pd.DataFrame,
    bench_row: pd.Series,
    extra_positions: "list[int] | set[int] | None" = None,
) -> pd.DataFrame:
    """The corpus without this query's target row (and, optionally, other rows).

    `extra_positions` are *positional* row numbers of `examples_df` to drop as well
    (the target's edition twins, see scripts/eval_guards.py). Left out, the result is
    exactly what the row-wise version returned before (audit A4); callers that pass
    two arguments are unaffected.
    """
    expected_text_id = str(bench_row["expected_source_text_id"])
    expected_sentence_id = str(bench_row["expected_source_sentence_id"])
    keep = ~(
        (examples_df["source_text_id"].astype(str) == expected_text_id).to_numpy()
        & (examples_df["source_sentence_id"].astype(str) == expected_sentence_id).to_numpy()
    )
    if extra_positions:
        keep[list(extra_positions)] = False
    return examples_df.loc[keep, :].copy()


def _tokens(value: object) -> set[str]:
    return {token for token in str(value).split() if token.strip()}


def _lemma_ids(value: object) -> set[str]:
    ids: set[str] = set()
    for part in str(value).split():
        lemma_id = part.split("|", 1)[0].strip()
        if lemma_id:
            ids.add(lemma_id)
    return ids


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _candidate_lemmas(
    examples_df: pd.DataFrame,
    candidate_transliteration: str,
) -> set[str]:
    candidate_key = canonical_reading(candidate_transliteration)
    matches = examples_df[
        examples_df["transliteration_gold"].map(canonical_reading) == candidate_key
    ]
    ids: set[str] = set()
    for value in matches["lemma_sequence"].tolist():
        ids |= _lemma_ids(value)
    return ids


USEFUL_RULES = ("v4", "v5")


def useful_decision(
    is_exact: bool,
    candidate_tokens: set[str],
    candidate_lemmas: set[str],
    expected_key_tokens: set[str],
    expected_lemma_ids: set[str],
    token_threshold: float,
    rule: str = "v4",
) -> tuple[bool, str, float, float]:
    """The useful-family test, given already-computed candidate evidence.

    Split out of `_useful_reason` so `scripts/compute_v4_answerability.py` can apply
    exactly this decision to all 130k corpus rows with the token sets and lemma sets
    precomputed once (the naive path re-scans the corpus per candidate). The `v4`
    branch is the original code, unchanged and in the original order.

    `rule="v5"` is the pre-registered lemma-first rule of 2026-09-05 (see
    docs/v4-answerability-and-v5-rule.md): when both sides carry lemma ids, only the
    lemma branches may declare a candidate useful — the token branch is not applied.
    When either side lacks lemma ids, v5 falls back to the v4 test verbatim. No new
    constant is introduced; the thresholds are v4's own.
    """
    if is_exact:
        return True, "exact expected transliteration", 1.0, 1.0

    token_score = _overlap(expected_key_tokens, candidate_tokens)
    lemma_intersection = expected_lemma_ids & candidate_lemmas
    lemma_score = (
        len(lemma_intersection) / min(len(expected_lemma_ids), len(candidate_lemmas))
        if expected_lemma_ids and candidate_lemmas
        else 0.0
    )

    if rule == "v5" and expected_lemma_ids and candidate_lemmas:
        if len(lemma_intersection) >= 2 and lemma_score >= 0.4:
            shared = ", ".join(sorted(lemma_intersection)[:8])
            return True, f"useful lemma-family match: {shared}", token_score, lemma_score
        if len(expected_lemma_ids) <= 2 and len(lemma_intersection) >= 1:
            shared = ", ".join(sorted(lemma_intersection)[:8])
            return True, f"useful short lemma-family match: {shared}", token_score, lemma_score
        return False, "no useful-family match (v5 lemma-first)", token_score, lemma_score

    if token_score >= token_threshold:
        shared = ", ".join(sorted(expected_key_tokens & candidate_tokens)[:8])
        return True, f"useful token-family match: {shared}", token_score, lemma_score

    if len(lemma_intersection) >= 2 and lemma_score >= 0.4:
        shared = ", ".join(sorted(lemma_intersection)[:8])
        return True, f"useful lemma-family match: {shared}", token_score, lemma_score

    if len(expected_lemma_ids) <= 2 and len(lemma_intersection) >= 1:
        shared = ", ".join(sorted(lemma_intersection)[:8])
        return True, f"useful short lemma-family match: {shared}", token_score, lemma_score

    return False, "no useful-family match", token_score, lemma_score


def _useful_reason(
    candidate: str,
    candidate_pool: pd.DataFrame,
    expected: str,
    expected_key_tokens: set[str],
    expected_lemma_ids: set[str],
    token_threshold: float,
    rule: str = "v4",
) -> tuple[bool, str, float, float]:
    is_exact = canonical_reading(candidate) == canonical_reading(expected)
    if is_exact:
        return True, "exact expected transliteration", 1.0, 1.0

    candidate_tokens = _tokens(loose_reading_form(candidate))
    candidate_lemmas = _candidate_lemmas(candidate_pool, candidate)
    return useful_decision(
        is_exact=False,
        candidate_tokens=candidate_tokens,
        candidate_lemmas=candidate_lemmas,
        expected_key_tokens=expected_key_tokens,
        expected_lemma_ids=expected_lemma_ids,
        token_threshold=token_threshold,
        rule=rule,
    )


# ---------------------------------------------------------------------------
# Fixed baselines and stricter reporting rows (audit A23).
#
# The headline "useful" rule is loose enough that a plain word-overlap ranker nearly
# matches the app on v4, so every run also scores two fixed rankers on the SAME
# candidate pool (target, and twins when excluded, removed) with the SAME useful rule,
# and reports the app's margin over them. Nothing here feeds the gate: the v4 rule is
# frozen and these are extra rows only.
# ---------------------------------------------------------------------------

BM25_K1 = 1.5
BM25_B = 0.75
# Strict-useful (reported only): token Jaccard after dropping one-letter particles.
STRICT_TOKEN_THRESHOLD = 0.5
NEAR_EXACT_THRESHOLD = 0.8


class BaselineStats:
    """Per-corpus tables for the baselines, built once per run from a TwinGuard."""

    def __init__(self, examples_df: pd.DataFrame, guard: TwinGuard) -> None:
        self.token_sets = guard.token_sets
        self.token_index = guard.token_index
        # The notation-folded key equals the strict (canonical) key since the fold
        # shipped (tests/test_notation_fold.py pins that), so the guard's keys are
        # reused instead of calling canonical_reading on 130k rows a second time.
        self.canonical = guard.keys
        self.by_canonical = guard.folded_groups
        self.lemma_sequences = [str(value or "") for value in examples_df["lemma_sequence"]]
        self.size = len(self.token_sets)
        self.lengths = [len(tokens) for tokens in self.token_sets]
        self.average_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0


def build_baseline_stats(examples_df: pd.DataFrame, guard: TwinGuard) -> BaselineStats:
    return BaselineStats(examples_df, guard)


def _top_distinct(ranked: list[int], stats: BaselineStats, top_n: int) -> list[int]:
    """First `top_n` positions of `ranked` (best first) with distinct canonical readings."""
    chosen: list[int] = []
    seen: set[str] = set()
    for position in ranked:
        key = stats.canonical[position]
        if key in seen:
            continue
        seen.add(key)
        chosen.append(position)
        if len(chosen) >= top_n:
            break
    return chosen


def overlap_ranking(
    query_tokens: set[str],
    stats: BaselineStats,
    excluded: "set[int] | frozenset[int]" = frozenset(),
    top_n: int = 3,
) -> list[int]:
    """Row positions of the best word-overlap (Jaccard) matches, best first.

    The plain baseline: no weighting, no stage, no lemma, no suggestion layer. Ties go
    to the earlier row, so the result is deterministic; at most one row per canonical
    reading is returned (the app also groups identical readings); excluded positions
    never appear.
    """
    if not query_tokens:
        return []
    candidates: set[int] = set()
    for token in query_tokens:
        candidates.update(stats.token_index.get(token, ()))
    candidates.difference_update(excluded)
    scored: list[tuple[float, int]] = []
    for position in candidates:
        row_tokens = stats.token_sets[position]
        shared = len(query_tokens & row_tokens)
        if shared:
            scored.append((-shared / len(query_tokens | row_tokens), position))
    scored.sort()
    return _top_distinct([position for _, position in scored], stats, top_n)


def bm25_ranking(
    query_tokens: set[str],
    stats: BaselineStats,
    excluded: "set[int] | frozenset[int]" = frozenset(),
    top_n: int = 3,
) -> list[int]:
    """Row positions of the best BM25 matches (k1=1.5, b=0.75), best first.

    Binary term frequency (a token is in a row or it is not), idf from the whole
    corpus document frequency, row length = number of distinct tokens. Only the
    postings of the query's own tokens are touched. Same tie-break and de-duplication
    as `overlap_ranking`.
    """
    if not query_tokens or not stats.size:
        return []
    scores: dict[int, float] = defaultdict(float)
    for token in query_tokens:
        postings = stats.token_index.get(token, ())
        if not postings:
            continue
        df_t = len(postings)
        idf = math.log(1.0 + (stats.size - df_t + 0.5) / (df_t + 0.5))
        for position in postings:
            if position in excluded:
                continue
            norm = 1.0 - BM25_B + BM25_B * stats.lengths[position] / (stats.average_length or 1.0)
            scores[position] += idf * (BM25_K1 + 1.0) / (1.0 + BM25_K1 * norm)
    ranked = sorted(scores, key=lambda position: (-scores[position], position))
    return _top_distinct(ranked, stats, top_n)


def candidate_lemmas_fast(
    stats: BaselineStats,
    reading: str,
    excluded: "set[int] | frozenset[int]" = frozenset(),
) -> set[str]:
    """`_candidate_lemmas` over a pool given as 'whole corpus minus `excluded`'.

    Same answer as scanning the pool for rows with the reading's canonical key, but
    through the by-key table instead of a 130k-row `map(canonical_reading)` per call.
    """
    ids: set[str] = set()
    for position in stats.by_canonical.get(canonical_reading(reading), ()):
        if position not in excluded:
            ids |= _lemma_ids(stats.lemma_sequences[position])
    return ids


def strict_useful(
    is_exact: bool,
    candidate_tokens: set[str],
    candidate_lemmas: set[str],
    expected_key_tokens: set[str],
    expected_lemma_ids: set[str],
) -> bool:
    """A stricter 'useful', REPORTED ONLY (it does not replace the frozen v4 rule).

    Exact; or token Jaccard >= 0.5 once the one-letter particles in STOP_TOKENS
    (m n r s f k t w pw hr) are dropped from both sides; or the lemma-family branches
    that v4 and v5 share. Under v4's 0.26 threshold two sentences that share only
    `n` and `m` can count as a lead (audit A23); here they cannot.
    """
    if is_exact:
        return True
    if _overlap(expected_key_tokens - STOP_TOKENS, candidate_tokens - STOP_TOKENS) >= (
        STRICT_TOKEN_THRESHOLD
    ):
        return True
    shared = expected_lemma_ids & candidate_lemmas
    if expected_lemma_ids and candidate_lemmas:
        lemma_score = len(shared) / min(len(expected_lemma_ids), len(candidate_lemmas))
        if len(shared) >= 2 and lemma_score >= 0.4:
            return True
    return len(expected_lemma_ids) <= 2 and len(shared) >= 1


def rank_metrics(ranks: "list[int | None]") -> tuple[float, float]:
    """(top-3 hit share, MRR) over per-query useful ranks (None = no hit in top 3)."""
    total = len(ranks)
    if not total:
        return 0.0, 0.0
    hits = sum(1 for rank in ranks if rank is not None and rank <= 3)
    mrr = sum(1.0 / rank for rank in ranks if rank is not None) / total
    return hits / total, mrr


def margin_summary(
    app_ranks: "list[int | None]", baseline_ranks: "list[int | None]", prefix: str
) -> dict[str, float]:
    """A baseline's numbers and the app's margin over them, as rounded summary values."""
    app_top3, app_mrr = rank_metrics(app_ranks)
    base_top3, base_mrr = rank_metrics(baseline_ranks)
    return {
        f"{prefix}_top3_useful": round(base_top3, 4),
        f"{prefix}_mrr_value": round(base_mrr, 4),
        f"margin_over_{prefix}_top3": round(app_top3 - base_top3, 4),
        f"margin_over_{prefix}_mrr_value": round(app_mrr - base_mrr, 4),
    }


def _row_label(row: pd.Series) -> str:
    """The `source/text_id/sentence_id` label `suggestions._source_label` prints.

    Kept identical to it on purpose (including the `unknown` / `no_text_id` /
    `no_sentence_id` fallbacks): the name-duplicate metric below identifies the row
    a suggestion was built from by matching that printed label, so any drift here
    would silently turn every suggestion into an unannotated one.
    """
    def text(value: object) -> str:
        if value is None:
            return ""
        stripped = str(value).strip()
        return "" if stripped.lower() == "nan" else stripped

    source = text(row.get("source")) or "unknown"
    text_id = text(row.get("source_text_id")) or "no_text_id"
    sentence_id = text(row.get("source_sentence_id")) or "no_sentence_id"
    return f"{source}/{text_id}/{sentence_id}"


def build_annotation_lookup(examples_df: pd.DataFrame) -> dict[tuple[str, str], tuple[str, str]]:
    """(row label, canonical reading) -> (lemma_sequence, upos), over the whole corpus.

    Item D's symptom metric needs the *token annotation of the row a suggestion was
    built from*, and a `ReadingSuggestion` carries only its reading and its source
    labels. `suggest_top_readings` puts the best-scoring row first in both, so the
    first supporting source plus the reading pins that row down. The reading is part
    of the key because a label alone is not guaranteed unique across the corpus.
    """
    upos_column = (
        examples_df["upos"]
        if "upos" in examples_df.columns
        else pd.Series([""] * len(examples_df), index=examples_df.index)
    )
    lookup: dict[tuple[str, str], tuple[str, str]] = {}
    for (_, row), upos in zip(examples_df.iterrows(), upos_column):
        key = (_row_label(row), canonical_reading(row.get("transliteration_gold")))
        lookup.setdefault(key, (str(row.get("lemma_sequence") or ""), str(upos or "")))
    return lookup


def name_duplicate_slots(
    suggestions: list, annotations: dict[tuple[str, str], tuple[str, str]]
) -> int:
    """How many of a query's top-3 slots repeat an earlier slot's *name-normalised* key.

    Item D's symptom metric, pre-registered 2026-09-06: the name-normalised key of a
    suggestion is `strict_reading_key` with every aligned PROPN token replaced by its
    lemma id (rows without a full token/lemma/upos alignment keep the plain strict
    key), and a slot counts as a duplicate when its key equals that of a slot above
    it. Two slots that are the same sentence with one name spelled two ways score 1;
    three such slots score 2.
    """
    keys: list[str] = []
    duplicates = 0
    for suggestion in suggestions:
        reading = suggestion.candidate_transliteration
        label = suggestion.supporting_sources[0] if suggestion.supporting_sources else ""
        lemma_sequence, upos = annotations.get((label, canonical_reading(reading)), ("", ""))
        key = name_normalised_reading_key(reading, lemma_sequence, upos)
        if key in keys:
            duplicates += 1
        keys.append(key)
    return duplicates


def notation_duplicate_slots(suggestions: list) -> int:
    """How many of a query's top-3 slots repeat an earlier slot's *notation-folded* key.

    Item D′'s symptom metric, pre-registered 2026-09-06: the key of a suggestion is
    `notation_folded_reading_key` (the strict key with `i̯`→`ꞽ` and `u̯`→`w`), and a
    slot counts as a duplicate when its key equals that of a slot above it. Two slots
    that are one sentence in two editions' weak-consonant notation score 1.

    Unlike item D's name metric this needs no corpus lookup: the fold is a property of
    the reading string alone, so the suggestion's own `candidate_transliteration` is
    all it reads. Before the fold ships this counts the pairs that *would* merge;
    after, it counts the pairs the shipped key failed to merge, and should be 0.
    """
    keys: list[str] = []
    duplicates = 0
    for suggestion in suggestions:
        key = notation_folded_reading_key(suggestion.candidate_transliteration)
        if key in keys:
            duplicates += 1
        keys.append(key)
    return duplicates


def _load_benchmark(benchmark_path: str = BENCHMARK_PATH) -> pd.DataFrame:
    path = Path(benchmark_path)
    if not path.exists():
        raise FileNotFoundError(
            f"{benchmark_path} not found. Run scripts.build_competitive_ambiguity_benchmark first."
        )
    df = pd.read_csv(path).fillna("")
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing competitive benchmark columns: {missing}")
    return df


def _parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the competitive ambiguity benchmark. Paths are configurable so the "
            "same frozen benchmark can be replayed against different corpus sizes."
        )
    )
    parser.add_argument("--examples", default=EXAMPLES_PATH, help="Corpus CSV to search.")
    parser.add_argument(
        "--benchmark",
        required=True,
        help=(
            "Benchmark queries CSV. Required: the old default was v1, whose targets "
            "mostly have an edition twin in the corpus (audit A26). The release gate "
            "is data/benchmarks/competitive_ambiguity_eval_queries_v4.csv."
        ),
    )
    parser.add_argument(
        "--results",
        default=None,
        help=(
            "Where to write per-query results. Default: a fresh temporary directory "
            "(printed), never a committed file."
        ),
    )
    parser.add_argument(
        "--failures",
        default=None,
        help="Where to write failing rows. Default: the same temporary directory.",
    )
    parser.add_argument(
        "--exclude-twins",
        type=float,
        default=0.0,
        metavar="OVERLAP",
        help=(
            "Audit A4. Besides the target row, also remove from every query's pool each "
            "row whose word overlap (Jaccard on loose-form tokens) with the target is "
            "at least OVERLAP, and each row with the same notation-folded reading "
            "(another edition of the same sentence). 0 (default) keeps today's pool, "
            "so the gate number is unchanged; 0.7 is the audit's recommendation. "
            "Both numbers should be quoted: the default one includes free edition-copy "
            "hits."
        ),
    )
    parser.add_argument(
        "--label",
        default="",
        help="Optional run label printed with the summary (e.g. 'corpus=300').",
    )
    parser.add_argument(
        "--query-path",
        choices=["app", "legacy"],
        default="app",
        help=(
            "How the query reaches retrieval and the suggestion layer. 'app' (default) "
            "mirrors app/ui/whyptology_app.py: retrieval always gets a SearchIndex, so "
            "parse_query can use the corpus vocabulary to choose a notation, and "
            "suggest_top_readings is handed the *interpreted reading* "
            "(`searched.reading or query`) rather than the raw string. 'legacy' is what "
            "this harness did before 2026-09-05 — index=None whenever no stage "
            "resolves, and the raw query string into the suggestion layer — and is kept "
            "so the published v4 numbers (0.90 / MRR 0.79) can be reproduced exactly."
        ),
    )
    parser.add_argument(
        "--useful-rule",
        choices=list(USEFUL_RULES),
        default="v4",
        help=(
            "Which useful-family definition to score with. 'v4' (default) is the "
            "frozen v4 rule and is byte-identical to every earlier run. 'v5' is the "
            "pre-registered lemma-first rule of 2026-09-05 (see "
            "docs/v4-answerability-and-v5-rule.md): where both the expected row and "
            "the candidate carry lemma ids, only the lemma branches can declare a "
            "match useful. v5 never replaces a v4 number; both are reported."
        ),
    )
    parser.add_argument(
        "--stage",
        choices=["none", "auto", "declared"],
        default="auto",
        help=(
            "Language-stage handling (item A). 'auto' (default) infers the stage per "
            "query, see below. 'none' reproduces the pre-item-A pooled retrieval "
            "exactly -- no StageResources is ever built. 'declared' "
            "reads the benchmark's own `language_stage` column (see "
            "derive_v4_declared_stage for how that column was populated; a "
            "benchmark file with no such column declares no stage for any row) and "
            "retrieves through app.services.stage.build_stage_resources, exactly as "
            "the app does: the candidate pool stays pooled, only the token "
            "weighting is stage-restricted (stage is a preference, not a filter, "
            "for retrieval). 'auto' infers the stage per query from a first "
            "retrieval pass over the pooled pool, then retrieves the same way."
        ),
    )
    return parser.parse_args(argv)


def _resolve_output_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    """--results / --failures, or files in a fresh temp directory when not given.

    The old defaults were the committed result files, so a bare run overwrote
    them (audit A26).
    """
    if args.results is not None and args.failures is not None:
        return Path(args.results), Path(args.failures)
    temp_dir = Path(tempfile.mkdtemp(prefix="competitive-eval-"))
    print(f"No --results/--failures given; writing to {temp_dir}")
    return (
        Path(args.results) if args.results is not None else temp_dir / "results.csv",
        Path(args.failures) if args.failures is not None else temp_dir / "failures.csv",
    )


def render_extra_summary(
    total: int,
    twin_threshold: float,
    queries_with_twins: int,
    twin_rows_removed: int,
    app_ranks: "list[int | None]",
    overlap_ranks: "list[int | None]",
    bm25_ranks: "list[int | None]",
    near_exact_hits: int,
    strict_top3_hits: int,
) -> str:
    """The summary lines added by audit A4 and A23, as printable text.

    Key names deliberately avoid the substrings verify_release greps for
    (`top3_useful_family_accuracy:`, `mrr:`, `failures:`).
    """
    lines = [
        f"twin_exclusion: {twin_threshold if twin_threshold > 0 else 'off'}",
    ]
    if twin_threshold > 0:
        lines.append(f"queries_with_twins: {queries_with_twins}")
        lines.append(f"twin_rows_removed: {twin_rows_removed}")
    extra: dict[str, object] = {}
    extra.update(margin_summary(app_ranks, overlap_ranks, "overlap_baseline"))
    extra.update(margin_summary(app_ranks, bm25_ranks, "bm25_baseline"))
    extra["top3_near_exact"] = round(near_exact_hits / total, 4) if total else 0.0
    extra["top3_strict_useful"] = round(strict_top3_hits / total, 4) if total else 0.0
    lines.extend(f"{key}: {value}" for key, value in extra.items())
    return "\n".join(lines)


def main(argv: "list[str] | None" = None) -> None:
    args = _parse_args(argv)
    results_path, failures_path = _resolve_output_paths(args)
    examples_df = load_examples_csv(args.examples)
    benchmark_df = _load_benchmark(args.benchmark)

    # Twin guard (audit A4) and baseline tables (audit A23): corpus-wide token sets,
    # token index and folded-reading groups, built once (about 5 s) and reused for
    # every query. Built even when --exclude-twins is off, because the baselines run
    # on the same pool.
    guard = TwinGuard(examples_df)
    baseline_stats = build_baseline_stats(examples_df, guard)
    twin_threshold = args.exclude_twins
    queries_with_twins = 0
    twin_rows_removed = 0
    app_useful_ranks: list[int | None] = []
    overlap_ranks: list[int | None] = []
    bm25_ranks: list[int | None] = []
    strict_ranks: list[int | None] = []
    near_exact_hits = 0
    strict_top3_hits = 0

    # Item D's symptom metric needs the token annotation behind each suggestion; one
    # pass over the corpus, reused for every query.
    annotations = build_annotation_lookup(examples_df)
    name_duplicate_total = 0
    notation_duplicate_total = 0
    expected_absent_from_pool = 0

    rows: list[dict[str, object]] = []
    top1_exact_hits = 0
    top3_exact_hits = 0
    top1_useful_hits = 0
    top3_useful_hits = 0
    reciprocal_rank_sum = 0.0

    # Base rates for infer_stage's lift check (item A, 'auto'): computed once on the
    # full corpus rather than per query — excluding one target row shifts a stage's
    # share by a fraction of a percent, not enough to matter, and recomputing per
    # query would cost one more full-column pass per query for no measurable gain.
    pooled_base_rates = stage_base_rates(examples_df)

    stages_used: list[str] = []
    for _, bench_row in benchmark_df.iterrows():
        twin_positions: list[int] = []
        if twin_threshold > 0:
            twin_positions = [
                position for position, _, _ in guard.twins(bench_row, twin_threshold)
            ]
            if twin_positions:
                queries_with_twins += 1
                twin_rows_removed += len(twin_positions)
        candidate_pool = _exclude_expected(examples_df, bench_row, twin_positions)
        query_input = str(bench_row["query_input"])
        query_reading_order = (
            query_input
            if bench_row["query_type"] == "normalized_reading_order"
            else ""
        )

        # Item A: which rows may stand as evidence for this query. 'none' leaves
        # candidate_pool untouched and never builds a StageResources, so that mode
        # reproduces today's numbers exactly (unchanged by the fix below).
        # Built at most once per query, and only when something actually needs it:
        # the stage build below, or --query-path 'app' (the app never retrieves
        # without a SearchIndex, so parse_query always has the corpus vocabulary).
        pooled_cache: list[object] = []

        def pooled() -> object:
            if not pooled_cache:
                pooled_cache.append(build_stage_resources(candidate_pool, None))
            return pooled_cache[0]

        stage: str | None = None
        if args.stage == "declared":
            # Read the benchmark's own precomputed column (see
            # derive_v4_declared_stage) rather than recomputing it here — a
            # benchmark file without the column (v1/v2/v3) simply declares no
            # stage for any row, via bench_row.get's default.
            stage = normalize_stage(bench_row.get("language_stage", ""))
        elif args.stage == "auto":
            first_pass = retrieve_top_k(
                candidate_pool,
                query_mdc=query_input,
                query_reading_order=query_reading_order,
                k=10,
                # 'app' resolves the stage from a retrieval that already has the
                # index, exactly as resolve_ui_stage does in whyptology_app.py.
                index=pooled().index if args.query_path == "app" else None,
            )
            stage = infer_stage(first_pass, base_rates=pooled_base_rates)
        stages_used.append(stage or "")

        # Retrieve through the same StageResources the app builds, not a bespoke
        # compatible_frame filter: a formulaic parallel in a different (known)
        # stage must stay a reachable candidate (stage is a preference for
        # retrieval, not a filter — app/services/stage.py). `candidate_pool` above
        # already excludes this row's own target sentence, so "pooled" here means
        # "every other row", exactly as intended; `candidate_pool` itself is never
        # narrowed any further. 'none' and an unresolved stage both retrieve on
        # `candidate_pool` directly with no cached index, unchanged from before.
        #
        # --query-path 'app' departs from that last sentence on purpose: the app has
        # no such branch, it always retrieves through resources that carry an index,
        # so an unresolved stage there still means "pooled resources", not "no index".
        if stage is None and args.query_path == "legacy":
            retrieval_frame = candidate_pool
            retrieval_index = None
        elif stage is None:
            retrieval_frame = pooled().frame
            retrieval_index = pooled().index
        else:
            pooled_resources = pooled()
            stage_resources = build_stage_resources(
                candidate_pool,
                stage,
                pooled_reading_model=pooled_resources.reading_model,
                pooled_index=pooled_resources.index,
            )
            retrieval_frame = stage_resources.frame
            retrieval_index = stage_resources.index

        retrieval_results = retrieve_top_k(
            retrieval_frame,
            query_mdc=query_input,
            query_reading_order=query_reading_order,
            k=min(50, len(retrieval_frame)),
            index=retrieval_index,
        )
        # The suggestion layer compares *readings* as strings of sounds, so the app
        # hands it the transliteration the query was understood as, not the raw MdC
        # or plain-ASCII text (whyptology_app.py: `query_mdc=searched.reading or
        # query`). 'legacy' passes the raw string, as this harness always did.
        suggestion_query = query_input
        if args.query_path == "app":
            searched = parse_query(
                query_input,
                vocabulary=retrieval_index.vocabulary if retrieval_index is not None else None,
            )
            suggestion_query = searched.reading or query_input
        suggestions = suggest_top_readings(
            retrieval_results,
            query_mdc=suggestion_query,
            query_reading_order=query_reading_order,
            top_n=3,
        )
        candidates = [suggestion.candidate_transliteration for suggestion in suggestions]
        expected = str(bench_row["expected_transliteration"])
        expected_key_tokens = _tokens(bench_row["expected_key_tokens"])
        expected_lemma_ids = _tokens(bench_row["expected_lemma_ids"])
        token_threshold = float(bench_row["acceptable_token_overlap_threshold"])

        exact_rank = None
        useful_rank = None
        useful_reasons: list[str] = []
        token_scores: list[str] = []
        lemma_scores: list[str] = []
        for rank, candidate in enumerate(candidates, start=1):
            if exact_rank is None and canonical_reading(candidate) == canonical_reading(expected):
                exact_rank = rank
            useful, reason, token_score, lemma_score = _useful_reason(
                candidate,
                candidate_pool=candidate_pool,
                expected=expected,
                expected_key_tokens=expected_key_tokens,
                expected_lemma_ids=expected_lemma_ids,
                token_threshold=token_threshold,
                rule=args.useful_rule,
            )
            useful_reasons.append(reason)
            token_scores.append(f"{token_score:.3f}")
            lemma_scores.append(f"{lemma_score:.3f}")
            if useful and useful_rank is None:
                useful_rank = rank

        # Fixed baselines on the SAME pool (audit A23): the target and, with
        # --exclude-twins, its twins are out of reach for them too. Their query is the
        # interpreted reading the app hands the suggestion layer, so a query-parsing
        # quirk affects app and baselines alike and only the ranking differs.
        excluded_positions = set(guard.target_positions(bench_row)) | set(twin_positions)
        baseline_query_tokens = {
            token for token in loose_reading_form(suggestion_query).split() if token
        }
        expected_canonical = canonical_reading(expected)

        def baseline_rank(positions: list[int]) -> int | None:
            for baseline_rank_value, position in enumerate(positions, start=1):
                is_exact_here = baseline_stats.canonical[position] == expected_canonical
                useful_here, _, _, _ = useful_decision(
                    is_exact=is_exact_here,
                    candidate_tokens=baseline_stats.token_sets[position],
                    candidate_lemmas=candidate_lemmas_fast(
                        baseline_stats,
                        str(examples_df["transliteration_gold"].iat[position]),
                        excluded_positions,
                    ),
                    expected_key_tokens=expected_key_tokens,
                    expected_lemma_ids=expected_lemma_ids,
                    token_threshold=token_threshold,
                    rule=args.useful_rule,
                )
                if useful_here:
                    return baseline_rank_value
            return None

        overlap_positions = overlap_ranking(
            baseline_query_tokens, baseline_stats, excluded_positions
        )
        bm25_positions = bm25_ranking(baseline_query_tokens, baseline_stats, excluded_positions)
        overlap_rank = baseline_rank(overlap_positions)
        bm25_rank = baseline_rank(bm25_positions)
        overlap_ranks.append(overlap_rank)
        bm25_ranks.append(bm25_rank)
        app_useful_ranks.append(useful_rank)

        # Stricter rows for the app's own suggestions, reported only (see
        # strict_useful): the first top-3 slot that is strict-useful, and whether any
        # slot is a near-exact copy (token overlap >= 0.8 with the expected row).
        strict_rank = None
        for rank, candidate in enumerate(candidates, start=1):
            if strict_useful(
                is_exact=canonical_reading(candidate) == expected_canonical,
                candidate_tokens=_tokens(loose_reading_form(candidate)),
                candidate_lemmas=candidate_lemmas_fast(
                    baseline_stats, candidate, excluded_positions
                ),
                expected_key_tokens=expected_key_tokens,
                expected_lemma_ids=expected_lemma_ids,
            ):
                strict_rank = rank
                break
        strict_ranks.append(strict_rank)
        if strict_rank is not None:
            strict_top3_hits += 1
        near_exact = any(float(score) >= NEAR_EXACT_THRESHOLD for score in token_scores)
        if near_exact:
            near_exact_hits += 1

        if exact_rank == 1:
            top1_exact_hits += 1
        if exact_rank is not None and exact_rank <= 3:
            top3_exact_hits += 1
        if useful_rank == 1:
            top1_useful_hits += 1
        if useful_rank is not None and useful_rank <= 3:
            top3_useful_hits += 1
        if useful_rank is not None:
            reciprocal_rank_sum += 1.0 / useful_rank

        # Item D, pre-registered 2026-09-06: how many of this query's top-3 slots are
        # the same reading with a proper noun spelled another way. An additional
        # column; nothing above it reads this value, so no existing number moves.
        query_name_duplicates = name_duplicate_slots(suggestions, annotations)
        name_duplicate_total += query_name_duplicates

        # Item D′, pre-registered 2026-09-06: how many of this query's top-3 slots are
        # the same reading in another edition's weak-consonant notation. Another
        # appended column; nothing above it reads this value either.
        query_notation_duplicates = notation_duplicate_slots(suggestions)
        notation_duplicate_total += query_notation_duplicates

        # Item D2's trigger, reported only in the summary. The benchmark excludes the
        # target row by construction, so "is the target in the pool?" cannot be asked
        # literally; what is asked instead is whether the top-50 pool the re-ranker
        # chooses from contains ANY row that would count as a useful-family answer.
        # If it does not, no re-ranking rule could have succeeded and the miss is a
        # retrieval (recall) problem — which is what D2 would address.
        pool_reachable = False
        for _, pool_row in retrieval_results.iterrows():
            pool_reading = str(pool_row.get("transliteration_gold") or "")
            reachable, _, _, _ = useful_decision(
                is_exact=canonical_reading(pool_reading) == canonical_reading(expected),
                candidate_tokens=_tokens(loose_reading_form(pool_reading)),
                candidate_lemmas=_lemma_ids(pool_row.get("lemma_sequence")),
                expected_key_tokens=expected_key_tokens,
                expected_lemma_ids=expected_lemma_ids,
                token_threshold=token_threshold,
                rule=args.useful_rule,
            )
            if reachable:
                pool_reachable = True
                break
        if not pool_reachable:
            expected_absent_from_pool += 1

        rows.append(
            {
                "benchmark_id": bench_row["benchmark_id"],
                "query_input": query_input,
                "query_type": bench_row["query_type"],
                "expected_transliteration": expected,
                "expected_source_text_id": bench_row["expected_source_text_id"],
                "expected_source_sentence_id": bench_row["expected_source_sentence_id"],
                "expected_key_tokens": bench_row["expected_key_tokens"],
                "expected_lemma_ids": bench_row["expected_lemma_ids"],
                "acceptable_token_overlap_threshold": token_threshold,
                "stage_mode": args.stage,
                "stage_used": stage or "",
                "exact_rank": exact_rank if exact_rank is not None else "",
                "useful_family_rank": useful_rank if useful_rank is not None else "",
                "top1_exact_hit": exact_rank == 1,
                "top3_exact_hit": exact_rank is not None and exact_rank <= 3,
                "top1_useful_family_hit": useful_rank == 1,
                "top3_useful_family_hit": useful_rank is not None and useful_rank <= 3,
                "suggestions": " || ".join(candidates),
                "confidence_scores": " || ".join(
                    f"{suggestion.confidence_score:.3f}" for suggestion in suggestions
                ),
                "evidence_summaries": " || ".join(
                    suggestion.evidence_summary for suggestion in suggestions
                ),
                "useful_family_reasons": " || ".join(useful_reasons),
                "expected_token_overlap_scores": " || ".join(token_scores),
                "expected_lemma_overlap_scores": " || ".join(lemma_scores),
                "supporting_sources": " || ".join(
                    "; ".join(suggestion.supporting_sources)
                    for suggestion in suggestions
                ),
                "notes": bench_row["notes"],
                # Last columns on purpose: appended after every column this file has
                # ever had, so a run against a frozen benchmark diffs clean against
                # its committed results apart from these additions.
                "name_duplicate_slots": query_name_duplicates,
                "notation_duplicate_slots": query_notation_duplicates,
                # Appended after those two (audit A4, A23): see the module notes on
                # twins and baselines. Every column above is unchanged by them.
                "twin_exclusion": twin_threshold,
                "twins_removed": len(twin_positions),
                "overlap_baseline_useful_rank": overlap_rank if overlap_rank is not None else "",
                "bm25_baseline_useful_rank": bm25_rank if bm25_rank is not None else "",
                "strict_useful_rank": strict_rank if strict_rank is not None else "",
                "top3_near_exact": near_exact,
                "overlap_baseline_suggestions": " || ".join(
                    str(examples_df["transliteration_gold"].iat[position])
                    for position in overlap_positions
                ),
            }
        )

    results_df = pd.DataFrame(rows)
    total = len(results_df)
    failures = (
        int((~results_df["top3_useful_family_hit"]).sum())
        if not results_df.empty
        else 0
    )
    summary = {
        "corpus_rows": len(examples_df),
        "total_queries": total,
        "stage_mode": args.stage,
        "top1_exact_accuracy": round(top1_exact_hits / total, 4) if total else 0.0,
        "top3_exact_accuracy": round(top3_exact_hits / total, 4) if total else 0.0,
        "top1_useful_family_accuracy": round(top1_useful_hits / total, 4) if total else 0.0,
        "top3_useful_family_accuracy": round(top3_useful_hits / total, 4) if total else 0.0,
        "mrr": round(reciprocal_rank_sum / total, 4) if total else 0.0,
        "failures": failures,
        # Item D (2026-09-06). Total over the run of top-3 slots that repeat an
        # earlier slot's name-normalised reading — Nederhof's "the alternatives are
        # one name in different forms", counted. Expected 0 on v4, held-out 1 and
        # LE-v1, which is why item D needed its own NAME-v1 set.
        "name_duplicate_slots": name_duplicate_total,
        # Item D′ (2026-09-06). Total over the run of top-3 slots that repeat an
        # earlier slot's notation-folded reading — the same complaint counted for
        # ordinary vocabulary written `ḏi̯` in one edition and `ḏꞽ` in another.
        "notation_duplicate_slots": notation_duplicate_total,
        # Item D2's trigger: queries whose top-50 retrieval pool holds no
        # useful-family row at all, so no re-ranking rule could have answered them.
        "expected_absent_from_pool": expected_absent_from_pool,
    }
    if args.stage != "none":
        summary["stages_used"] = dict(pd.Series(stages_used).value_counts())
    # Printed only for a non-default rule, so a `--useful-rule v4` run (the default)
    # emits exactly the CSV columns it always did. The summary itself gained one
    # line on 2026-09-05 -- `query_path` is always printed, because since then the
    # default path is the app's and a reader must be able to tell which one a
    # quoted number came from.
    if args.useful_rule != "v4":
        summary["useful_rule"] = args.useful_rule
    summary["query_path"] = args.query_path
    # Experiment 1 (2026-09-05): which re-rank configuration this run used, printed
    # only when it is not the shipped default, so a default run's summary is
    # unchanged. The preset is chosen with the WHYPTOLOGY_SUGGESTION_PRESET
    # environment variable and read once at import of app.services.suggestions.
    if DEFAULT_SUGGESTION_WEIGHTS != SuggestionWeights():
        summary["suggestion_preset"] = os.environ.get(SUGGESTION_PRESET_ENV, "")

    heading = "Competitive ambiguity evaluation summary"
    if args.label:
        heading = f"{heading} [{args.label}]"
    print(f"{heading}:")
    for key, value in summary.items():
        print(f"{key}: {value}")

    # Printed AFTER every key above: scripts/verify_release.py greps this output with
    # an unanchored first-match re.search, so nothing new may precede or collide with
    # top3_useful_family_accuracy / mrr / failures / corpus_rows / total_queries.
    print(render_extra_summary(
        total=total,
        twin_threshold=twin_threshold,
        queries_with_twins=queries_with_twins,
        twin_rows_removed=twin_rows_removed,
        app_ranks=app_useful_ranks,
        overlap_ranks=overlap_ranks,
        bm25_ranks=bm25_ranks,
        near_exact_hits=near_exact_hits,
        strict_top3_hits=strict_top3_hits,
    ))

    results_path.parent.mkdir(parents=True, exist_ok=True)
    failures_path.parent.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(results_path, index=False)
    failures_df = (
        results_df[results_df["top3_useful_family_hit"] == False].copy()  # noqa: E712
        if not results_df.empty
        else pd.DataFrame()
    )
    failures_df.to_csv(failures_path, index=False)
    print(f"Saved competitive ambiguity results to {results_path}")
    print(f"Saved competitive ambiguity failures to {failures_path}")


if __name__ == "__main__":
    main()

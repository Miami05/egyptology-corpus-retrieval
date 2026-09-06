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
import os
import sys
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
    suggest_top_readings,
)

EXAMPLES_PATH = "data/processed/examples.csv"
BENCHMARK_PATH = "data/benchmarks/competitive_ambiguity_eval_queries.csv"
RESULTS_PATH = "data/benchmarks/competitive_ambiguity_eval_results.csv"
FAILURES_PATH = "data/benchmarks/competitive_ambiguity_eval_failures.csv"


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


def _exclude_expected(examples_df: pd.DataFrame, bench_row: pd.Series) -> pd.DataFrame:
    expected_key = (
        str(bench_row["expected_source_text_id"]),
        str(bench_row["expected_source_sentence_id"]),
    )
    mask = examples_df.apply(lambda row: _row_key(row) != expected_key, axis=1)
    return examples_df.loc[mask, :].copy()


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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the competitive ambiguity benchmark. Paths are configurable so the "
            "same frozen benchmark can be replayed against different corpus sizes."
        )
    )
    parser.add_argument("--examples", default=EXAMPLES_PATH, help="Corpus CSV to search.")
    parser.add_argument("--benchmark", default=BENCHMARK_PATH, help="Benchmark queries CSV.")
    parser.add_argument("--results", default=RESULTS_PATH, help="Where to write per-query results.")
    parser.add_argument("--failures", default=FAILURES_PATH, help="Where to write failing rows.")
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
            "Language-stage handling (item A). 'none' (default) reproduces today's "
            "pooled retrieval exactly -- no StageResources is ever built. 'declared' "
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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    examples_df = load_examples_csv(args.examples)
    benchmark_df = _load_benchmark(args.benchmark)

    # Item D's symptom metric needs the token annotation behind each suggestion; one
    # pass over the corpus, reused for every query.
    annotations = build_annotation_lookup(examples_df)
    name_duplicate_total = 0
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
        candidate_pool = _exclude_expected(examples_df, bench_row)
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
                # Last column on purpose: appended after every column this file has
                # ever had, so a run against a frozen benchmark diffs clean against
                # its committed results apart from this one addition.
                "name_duplicate_slots": query_name_duplicates,
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

    results_path = Path(args.results)
    failures_path = Path(args.failures)
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

"""Audit batch "eval" (2026-10-11 audit, findings A4, A23, A24, A25, A26, A55, A56).

What these tests pin:

* the twin guard finds every edition twin of a benchmark target (A4) and the set of
  known twins per benchmark cannot change unnoticed (A55);
* the fixed baselines and the strict-useful rule behave as documented, and the extra
  summary lines cannot disturb the numbers `scripts/verify_release.py` greps (A23);
* the eval scripts no longer default to contaminated inputs or committed outputs (A26);
* duplicate exclusion and the lexicon-leak exclusion do what their flags say (A24, A56).

Tests on the real corpus skip when `data/processed/examples.csv` is not checked out
(git LFS); everything else runs on tiny synthetic corpora.
"""

from __future__ import annotations

import hashlib
import itertools
import random
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = PROJECT_ROOT / "data" / "benchmarks"
CORPUS_PATH = PROJECT_ROOT / "data" / "processed" / "examples.csv"

from app.data.loader import REQUIRED_COLUMNS, load_examples_csv  # noqa: E402
from app.services.lexicon import Lexicon  # noqa: E402
from app.services.suggestions import loose_reading_form  # noqa: E402
from scripts import (  # noqa: E402
    compare_twin_scores,
    list_benchmark_twins,
    run_competitive_ambiguity_eval as ce,
    run_reading_model_eval as rm,
    run_sign_reading_eval as se,
    tune_ranking_weights as tune,
)
from scripts.build_competitive_ambiguity_benchmark import (  # noqa: E402
    _token_set,
    build_token_index,
)
from scripts.eval_guards import (  # noqa: E402
    TwinGuard,
    assert_text_groups_disjoint,
    jaccard,
    ramses_official_split,
    text_group_keys,
    twin_rows,
)


def _corpus_available() -> bool:
    try:
        with open(CORPUS_PATH, "r", encoding="utf-8") as handle:
            return handle.readline().startswith("source,")
    except OSError:
        return False


needs_corpus = pytest.mark.skipif(
    not _corpus_available(),
    reason="data/processed/examples.csv is missing or a git-LFS pointer",
)

# Distinct plain-ASCII words that `loose_reading_form` leaves untouched.
WORDS = [
    "htp", "nsw", "wsr", "nfr", "anx", "mdw", "rdi", "sdm", "iri", "mry",
    "xpr", "pwt", "snb", "mnt", "mnx", "sxm", "bik", "ddi", "kmt", "tpi",
]


def _frame(readings: list[str], lemmas: "list[str] | None" = None) -> pd.DataFrame:
    """A minimal corpus frame: ids T<i>/S<i>, a reading and (optionally) lemma ids."""
    return pd.DataFrame(
        {
            "source": ["TLA"] * len(readings),
            "source_text_id": [f"T{i}" for i in range(len(readings))],
            "source_sentence_id": [f"S{i}" for i in range(len(readings))],
            "transliteration_gold": readings,
            "lemma_sequence": lemmas if lemmas is not None else [""] * len(readings),
        }
    )


def _bench_row(position: int, df: pd.DataFrame, **extra: object) -> pd.Series:
    row = {
        "benchmark_id": f"B{position}",
        "expected_source_text_id": df["source_text_id"].iat[position],
        "expected_source_sentence_id": df["source_sentence_id"].iat[position],
        "expected_transliteration": df["transliteration_gold"].iat[position],
        "expected_key_tokens": " ".join(sorted(_token_set(loose_reading_form(df["transliteration_gold"].iat[position])))),
    }
    row.update(extra)
    return pd.Series(row)


# ---------------------------------------------------------------------------
# Step 0: eval_guards
# ---------------------------------------------------------------------------


def test_the_test_words_survive_loose_reading_form():
    assert loose_reading_form(" ".join(WORDS)).split() == WORDS


def test_twin_rows_agrees_with_a_full_scan_on_random_corpora():
    rng = random.Random(20261011)
    for trial in range(25):
        token_sets = [
            set(rng.sample(WORDS[:12], rng.randint(1, 6))) for _ in range(rng.randint(5, 40))
        ]
        index = build_token_index(token_sets)
        for threshold in (0.5, 0.7, 0.8, 0.9):
            for row, target in enumerate(token_sets):
                brute = [
                    (other, len(target & tokens) / len(target | tokens))
                    for other, tokens in enumerate(token_sets)
                    if target & tokens and len(target & tokens) / len(target | tokens) >= threshold
                ]
                found = twin_rows(target, token_sets, index, threshold)
                assert [p for p, _ in found] == [p for p, _ in brute], (trial, threshold, row)
                for (_, got), (_, want) in zip(found, brute):
                    assert got == pytest.approx(want)


def test_a_row_at_exactly_0_7_is_a_twin_and_one_at_0_6667_is_not():
    """Guards the float-boundary bug the builder already had once (7/10 vs 6/9)."""
    base = set(WORDS[:7])
    at_boundary = base | set(WORDS[7:10])  # 7 shared of 10 -> exactly 0.7
    just_below = set(WORDS[:6]) | set(WORDS[10:12])  # 6 shared of 9 -> 0.6667 (7 + 2 in the union)
    token_sets = [base, at_boundary, just_below]
    index = build_token_index(token_sets)
    found = {position for position, _ in twin_rows(base, token_sets, index, 0.7)}
    assert found == {0, 1}
    assert jaccard(base, at_boundary) == 0.7


def test_the_target_is_never_its_own_twin():
    df = _frame(["htp nsw wsr nfr", "htp nsw wsr nfr anx", "mdw rdi sdm"])
    guard = TwinGuard(df)
    positions = [p for p, _, _ in guard.twins(_bench_row(0, df), 0.7)]
    assert positions == [1]


def test_a_row_with_the_same_folded_reading_is_a_twin_even_below_the_overlap_line():
    """Brackets and dots differ, so the loose tokens differ (the corpus does this:
    `zmy.t` against `z(my).t`), but the notation-folded reading is identical."""
    df = _frame(
        [
            "z(my).t ꞽmn.t(ꞽ).t ḥtp",
            "zmy.t ꞽmn.tꞽ.t ḥtp",
            "mdw rdi sdm",
        ]
    )
    guard = TwinGuard(df)
    # Above the overlap the loose tokens reach, so only the folded rule can return it.
    twins = guard.twins(_bench_row(0, df), 0.99)
    assert [(p, folded) for p, _, folded in twins] == [(1, True)]
    assert twins[0][1] < 0.99


def test_target_tokens_fall_back_to_expected_key_tokens_when_the_row_is_absent():
    df = _frame(["htp nsw wsr nfr anx", "mdw rdi sdm"])
    guard = TwinGuard(df)
    absent = pd.Series(
        {
            "benchmark_id": "X",
            "expected_source_text_id": "nope",
            "expected_source_sentence_id": "nope",
            "expected_key_tokens": "htp nsw wsr nfr",
            "expected_transliteration": "htp nsw wsr nfr",
        }
    )
    assert [p for p, _, _ in guard.twins(absent, 0.7)] == [0]


@needs_corpus
@pytest.mark.parametrize(
    "benchmark_file",
    [
        "competitive_ambiguity_eval_queries_v4_driftcorrected.csv",
        "competitive_ambiguity_eval_queries_holdout_2026-09-05.csv",
        "competitive_ambiguity_eval_queries_le_v1.csv",
        "competitive_ambiguity_eval_queries_name_v1.csv",
    ],
)
def test_benchmark_key_tokens_drift_from_the_corpus_only_as_reviewed(real_corpus, benchmark_file):
    """The twin guard takes target tokens from the corpus row, not from the benchmark's
    expected_key_tokens (only a fallback). The frozen column and today's normaliser
    may drift apart only as recorded in KNOWN_KEY_TOKEN_DRIFT; any other difference
    (a new normaliser change, a regenerated benchmark) fails here and must be reviewed.
    The benchmark files themselves are never rewritten (historical results stay
    reproducible); the eval reports the drift per query instead."""
    _, guard = real_corpus
    bench = pd.read_csv(BENCHMARKS / benchmark_file).fillna("")
    drift: dict[str, str] = {}
    for _, row in bench.iterrows():
        assert guard.target_positions(row), f"{row['benchmark_id']} is not in the corpus"
        text = ce.format_token_drift(*ce.key_token_drift(row, guard))
        if text:
            drift[str(row["benchmark_id"])] = text
    assert drift == KNOWN_KEY_TOKEN_DRIFT.get(benchmark_file, {})


# Reviewed 2026-10-25 on the merged audit-fixes tree (retrieval-core A17 deletes `{…}`
# superfluous text from the search and loose keys). Each entry: the frozen
# expected_key_tokens against today's loose tokens of the target row, `-` only in the
# frozen column, `+` only today. All three are the intended A17 semantics.
KNOWN_KEY_TOKEN_DRIFT = {
    "competitive_ambiguity_eval_queries_holdout_2026-09-05.csv": {
        "HOLD_001": "+nn",  # n{t}n.t: the superfluous t goes, nn.t remains
        "HOLD_008": "-i",  # {=ꞽ}: the superfluous pronoun is no longer a token
        "HOLD_026": "-kh",  # wḫꜣ{ḫ}: the superfluous ḫ is no longer a token
    },
}


@needs_corpus
def test_v4_key_tokens_differ_from_the_corpus_only_by_the_stale_pl_token(real_corpus):
    """Why v4_driftcorrected exists: v4 recorded `pl` (from `.pl` markers) that today's
    loose form no longer yields. The difference is that one token, nothing else, which
    is also why twin detection must not read the benchmark's token column."""
    _, guard = real_corpus
    bench = pd.read_csv(BENCHMARKS / "competitive_ambiguity_eval_queries_v4.csv").fillna("")
    drifted = 0
    for _, row in bench.iterrows():
        current = guard.token_sets[guard.target_positions(row)[0]]
        recorded = set(str(row["expected_key_tokens"]).split())
        assert recorded - current <= {"pl"} and not current - recorded
        drifted += int(recorded != current)
    assert drifted == 12


@pytest.fixture(scope="module")
def real_corpus():
    df = load_examples_csv(str(CORPUS_PATH))
    return df, TwinGuard(df)


# ---------------------------------------------------------------------------
# A55: the twin allow-list, parametrised over every gated or quoted benchmark
# ---------------------------------------------------------------------------

KNOWN_TWINS = BENCHMARKS / "known_twins_2026-10-12.csv"
GATED_OR_QUOTED = [
    "competitive_ambiguity_eval_queries_v4.csv",
    "competitive_ambiguity_eval_queries_holdout_2026-09-05.csv",
    "competitive_ambiguity_eval_queries_le_v1.csv",
    "competitive_ambiguity_eval_queries_name_v1.csv",
    "competitive_ambiguity_eval_queries_v4_driftcorrected.csv",
]
# (targets with a twin at >= 0.7 or folded-identical, targets with a twin at >= 0.9),
# as measured on 2026-10-12 on the 130,472-row corpus and re-measured 2026-10-25 after
# audit A17 (`{…}` superfluous text leaves the loose key): only the retired sets moved,
# v1 0.9 10 -> 11 (COMP_001's BBAW edition B083910 at 1.0) and v2 0.9 0 -> 1 (COMP_003,
# the same BBAW row). A regenerated twin list that changes these shows up here and in
# review, not only in a CSV diff.
EXPECTED_COUNTS = {
    "competitive_ambiguity_eval_queries_v4.csv": (7, 2),
    "competitive_ambiguity_eval_queries_holdout_2026-09-05.csv": (4, 0),
    "competitive_ambiguity_eval_queries_le_v1.csv": (5, 0),
    "competitive_ambiguity_eval_queries_name_v1.csv": (5, 0),
    "competitive_ambiguity_eval_queries_v4_driftcorrected.csv": (7, 2),
    "competitive_ambiguity_eval_queries.csv": (17, 11),
    "competitive_ambiguity_eval_queries_v2.csv": (18, 1),
    "competitive_ambiguity_eval_queries_v3.csv": (20, 3),
}


def _twin_identity(frame: pd.DataFrame) -> set[tuple[str, str, str, str]]:
    return {
        (str(r.benchmark_id), str(r.twin_source), str(r.twin_text_id), str(r.twin_sentence_id))
        for r in frame.itertuples()
    }


def _known_for(benchmark_file: str) -> pd.DataFrame:
    known = pd.read_csv(KNOWN_TWINS, dtype=str).fillna("")
    return known[known["benchmark_file"] == benchmark_file]


def _differences(computed: pd.DataFrame, known: pd.DataFrame) -> tuple[set, set]:
    """(twins that are new, twins that vanished) relative to the allow-list."""
    got, want = _twin_identity(computed), _twin_identity(known)
    return got - want, want - got


@needs_corpus
@pytest.mark.parametrize("benchmark_file", GATED_OR_QUOTED)
def test_benchmark_twins_match_the_recorded_allow_list(real_corpus, benchmark_file):
    """A new twin (benchmark regenerated, corpus source added) fails, and so does a
    vanished one, so the list stays honest in both directions."""
    df, guard = real_corpus
    bench = pd.read_csv(BENCHMARKS / benchmark_file).fillna("")
    computed = pd.DataFrame(
        list_benchmark_twins.twin_records(df, guard, bench, benchmark_file),
        columns=list_benchmark_twins.COLUMNS,
    )
    known = _known_for(benchmark_file)
    new, vanished = _differences(computed, known)
    assert not new, f"new twins in {benchmark_file}: {sorted(new)[:5]}"
    assert not vanished, f"twins in the allow-list that no longer exist: {sorted(vanished)[:5]}"
    # The list is not stale: every id it names is in the benchmark, every target in the corpus.
    assert set(known["benchmark_id"]) <= set(bench["benchmark_id"])
    for _, row in bench.iterrows():
        assert guard.target_positions(row), f"{row['benchmark_id']} is not in the corpus"


@needs_corpus
def test_a_duplicate_row_injected_into_the_corpus_fails_the_allow_list(real_corpus):
    """Negative control: the comparison above must actually be able to fail."""
    df, _ = real_corpus
    benchmark_file = "competitive_ambiguity_eval_queries_v4.csv"
    bench = pd.read_csv(BENCHMARKS / benchmark_file).fillna("")
    with_twin = set(_known_for(benchmark_file)["benchmark_id"])
    target = next(row for _, row in bench.iterrows() if row["benchmark_id"] not in with_twin)
    key = (str(target["expected_source_text_id"]), str(target["expected_source_sentence_id"]))
    source_row = df[
        (df["source_text_id"].astype(str) == key[0]) & (df["source_sentence_id"].astype(str) == key[1])
    ].iloc[[0]].copy()
    source_row["source_text_id"] = "INJECTED_DUPLICATE"
    source_row["source_sentence_id"] = "S_INJECTED"
    polluted = pd.concat([df, source_row], ignore_index=True)
    computed = pd.DataFrame(
        list_benchmark_twins.twin_records(polluted, TwinGuard(polluted), bench, benchmark_file),
        columns=list_benchmark_twins.COLUMNS,
    )
    new, vanished = _differences(computed, _known_for(benchmark_file))
    assert any(identity[0] == target["benchmark_id"] and identity[2] == "INJECTED_DUPLICATE" for identity in new)
    assert not vanished


def test_known_twin_counts_per_benchmark_are_the_measured_ones():
    known = pd.read_csv(KNOWN_TWINS)
    for benchmark_file, (at_07, at_09) in EXPECTED_COUNTS.items():
        rows = known[known["benchmark_file"] == benchmark_file]
        assert rows["benchmark_id"].nunique() == at_07, benchmark_file
        assert rows.loc[rows["overlap"] >= 0.9, "benchmark_id"].nunique() == at_09, benchmark_file


def test_allow_list_differences_are_reported_in_both_directions():
    known = pd.DataFrame(
        [
            {"benchmark_id": "B1", "twin_source": "TLA", "twin_text_id": "t1", "twin_sentence_id": "s1"},
            {"benchmark_id": "B1", "twin_source": "TLA", "twin_text_id": "t2", "twin_sentence_id": "s2"},
        ]
    )
    computed = pd.DataFrame(
        [
            {"benchmark_id": "B1", "twin_source": "TLA", "twin_text_id": "t1", "twin_sentence_id": "s1"},
            {"benchmark_id": "B2", "twin_source": "AES", "twin_text_id": "t9", "twin_sentence_id": "s9"},
        ]
    )
    new, vanished = _differences(computed, known)
    assert new == {("B2", "AES", "t9", "s9")}
    assert vanished == {("B1", "TLA", "t2", "s2")}


# ---------------------------------------------------------------------------
# A4: twin exclusion in the competitive eval
# ---------------------------------------------------------------------------


def _old_exclude_expected(examples_df: pd.DataFrame, bench_row: pd.Series) -> pd.DataFrame:
    """The row-wise implementation this replaced, kept to prove the same result."""
    expected_key = (
        str(bench_row["expected_source_text_id"]),
        str(bench_row["expected_source_sentence_id"]),
    )
    mask = examples_df.apply(
        lambda row: (str(row["source_text_id"]), str(row["source_sentence_id"])) != expected_key,
        axis=1,
    )
    return examples_df.loc[mask, :].copy()


def test_exclude_expected_two_argument_call_is_unchanged():
    df = _frame(["htp nsw", "htp nsw wsr", "mdw rdi", "nfr anx"])
    df.loc[3, ["source_text_id", "source_sentence_id"]] = ["T1", "S1"]  # a repeated key
    row = _bench_row(1, df)
    new = ce._exclude_expected(df, row)
    old = _old_exclude_expected(df, row)
    pd.testing.assert_frame_equal(new, old)
    assert list(new.index) == [0, 2]


def test_exclude_expected_three_argument_call_drops_the_given_positions_only():
    df = _frame(["htp nsw", "htp nsw wsr", "mdw rdi", "nfr anx"])
    pool = ce._exclude_expected(df, _bench_row(1, df), [3])
    assert list(pool.index) == [0, 2]
    pool = ce._exclude_expected(df, _bench_row(1, df), None)
    assert list(pool.index) == [0, 2, 3]
    pool = ce._exclude_expected(df, _bench_row(1, df), set())
    assert list(pool.index) == [0, 2, 3]


def _write_corpus(tmp_path: Path, rows: list[tuple[str, str]]) -> Path:
    """rows: (reading, lemma_sequence); writes a loader-shaped CSV, ids T<i>/S<i>."""
    records = []
    for i, (reading, lemmas) in enumerate(rows):
        record = {column: "" for column in REQUIRED_COLUMNS}
        record.update(
            source="TLA",
            source_text_id=f"T{i}",
            source_sentence_id=f"S{i}",
            transliteration_gold=reading,
            lemma_sequence=lemmas,
            language_stage="Earlier Egyptian",
            review_status="draft",
        )
        records.append(record)
    path = tmp_path / "corpus.csv"
    pd.DataFrame(records).to_csv(path, index=False)
    return path


TWIN_CORPUS = [
    ("ḥtp ḏi̯ nsw wsꞽr nb ꜥnḫ", ""),  # 0: the target
    ("ḥtp ḏꞽ nsw wsꞽr nb ꜥnḫ ḥr", ""),  # 1: its edition twin (Jaccard 6/7)
    ("ḥtp nsw ꜥnḫ ḥꜣt", ""),  # 2: a genuine rival
    ("ꜥnḫ nb m ḥꜣt ḥtp", ""),  # 3: a genuine rival
    ("nfr nb m ꜥnḫ", ""),  # 4: a genuine rival
] + [(f"x{i} y{i} nb", "") for i in range(20)]


def _write_benchmark(tmp_path: Path) -> Path:
    bench = pd.DataFrame(
        [
            {
                "benchmark_id": "B1",
                "query_input": "htp di nsw wsir nb",
                "query_type": "simplified_transliteration",
                "expected_transliteration": "ḥtp ḏi̯ nsw wsꞽr nb ꜥnḫ",
                "expected_source_text_id": "T0",
                "expected_source_sentence_id": "S0",
                "expected_key_tokens": "htp di nsw wsir nb anx",
                "expected_lemma_ids": "",
                "acceptable_token_overlap_threshold": "0.26",
                "notes": "",
            }
        ]
    )
    path = tmp_path / "bench.csv"
    bench.to_csv(path, index=False)
    return path


def _run_eval(
    tmp_path: Path, capsys, *extra: str, tag: str = "run", rows: "list[tuple[str, str]] | None" = None
) -> tuple[pd.DataFrame, str]:
    corpus = _write_corpus(tmp_path, rows if rows is not None else TWIN_CORPUS)
    bench = _write_benchmark(tmp_path)
    capsys.readouterr()
    ce.main(
        [
            "--examples", str(corpus),
            "--benchmark", str(bench),
            "--results", str(tmp_path / f"{tag}_results.csv"),
            "--failures", str(tmp_path / f"{tag}_failures.csv"),
            "--stage", "none",
            *extra,
        ]
    )
    out = capsys.readouterr().out
    return pd.read_csv(tmp_path / f"{tag}_results.csv").fillna(""), out


def test_exclude_twins_removes_the_twin_from_the_pool_and_keeps_the_rival(tmp_path, capsys):
    twin = "ḥtp ḏꞽ nsw wsꞽr nb ꜥnḫ ḥr"
    rival = "ḥtp nsw ꜥnḫ ḥꜣt"
    off, _ = _run_eval(tmp_path, capsys, tag="off")
    on, out = _run_eval(tmp_path, capsys, "--exclude-twins", "0.7", tag="on")
    assert twin in off.loc[0, "suggestions"].split(" || ")
    shown = on.loc[0, "suggestions"].split(" || ")
    assert twin not in shown and rival in shown
    assert int(on.loc[0, "twins_removed"]) == 1 and int(off.loc[0, "twins_removed"]) == 0
    assert "twin_exclusion: 0.7" in out and "queries_with_twins: 1" in out
    assert "twin_rows_removed: 1" in out


LEGACY_COLUMNS = [
    "benchmark_id", "query_input", "query_type", "expected_transliteration",
    "expected_source_text_id", "expected_source_sentence_id", "expected_key_tokens",
    "expected_lemma_ids", "acceptable_token_overlap_threshold", "stage_mode", "stage_used",
    "exact_rank", "useful_family_rank", "top1_exact_hit", "top3_exact_hit",
    "top1_useful_family_hit", "top3_useful_family_hit", "suggestions", "confidence_scores",
    "evidence_summaries", "useful_family_reasons", "expected_token_overlap_scores",
    "expected_lemma_overlap_scores", "supporting_sources", "notes", "name_duplicate_slots",
    "notation_duplicate_slots",
]


def test_default_run_keeps_every_legacy_column_first_and_unchanged(tmp_path, capsys):
    """Twin exclusion off is the default; on a corpus with no twin, on = off column for column."""
    rows = list(TWIN_CORPUS)
    rows[1] = ("qqq www eee", "")  # no twin of the target any more
    off, _ = _run_eval(tmp_path, capsys, tag="off", rows=rows)
    on, _ = _run_eval(tmp_path, capsys, "--exclude-twins", "0.7", tag="on", rows=rows)
    assert list(off.columns[: len(LEGACY_COLUMNS)]) == LEGACY_COLUMNS
    pd.testing.assert_frame_equal(off[LEGACY_COLUMNS], on[LEGACY_COLUMNS])
    assert int(on.loc[0, "twins_removed"]) == 0


# verify_release.py reads the eval's summary with these unanchored, first-match
# patterns (scripts/verify_release.py, the `grab(...)` calls after the competitive
# eval). Copied here so a new summary line that collides with them fails this test.
VERIFY_RELEASE_PATTERNS = {
    "corpus_rows": r"corpus_rows:\s*(\d+)",
    "total_queries": r"total_queries:\s*(\d+)",
    "top1_useful_family_accuracy": r"top1_useful_family_accuracy:\s*([\d.]+)",
    "top3_useful_family_accuracy": r"top3_useful_family_accuracy:\s*([\d.]+)",
    "mrr": r"mrr:\s*([\d.]+)",
    "failures": r"failures:\s*(\d+)",
}


def test_new_summary_lines_do_not_disturb_what_verify_release_greps(tmp_path, capsys):
    _, out = _run_eval(tmp_path, capsys, "--exclude-twins", "0.7")
    # The baseline block is really there...
    assert "overlap_baseline_top3_useful:" in out and "margin_over_bm25_baseline_top3:" in out
    for key, pattern in VERIFY_RELEASE_PATTERNS.items():
        first = re.search(pattern, out)
        own_line = re.search(rf"^{key}: ([\d.]+)$", out, flags=re.MULTILINE)
        assert first and own_line, key
        # ...and the first unanchored match is still the legacy line itself.
        assert first.group(1) == own_line.group(1), key
    # The extra block comes after every legacy key.
    assert out.index("twin_exclusion:") > out.index("expected_absent_from_pool:")


def test_bare_results_default_to_a_temp_dir_not_a_committed_file():
    args = ce._parse_args(["--benchmark", "x.csv"])
    assert args.results is None and args.failures is None
    results, failures = ce._resolve_output_paths(args)
    data_dir = (PROJECT_ROOT / "data").resolve()
    assert not results.resolve().is_relative_to(data_dir)
    assert not failures.resolve().is_relative_to(data_dir)
    assert results.parent == failures.parent


# ---------------------------------------------------------------------------
# A23: baselines, margins, strict useful
# ---------------------------------------------------------------------------


def _stats(readings: list[str], lemmas: "list[str] | None" = None):
    df = _frame(readings, lemmas)
    return ce.build_baseline_stats(df, TwinGuard(df)), df


def test_overlap_ranking_orders_by_jaccard_then_position_and_respects_exclusions():
    stats, _ = _stats(
        [
            "htp nsw wsr",  # 0: 1.0
            "htp nsw wsr nfr",  # 1: 0.75
            "htp nsw nfr anx",  # 2: 0.4
            "htp nsw nfr anx",  # 3: same reading as 2 -> never shown twice
            "mdw",  # 4: no overlap
            "htp mdw",  # 5: 0.25
            "htp nsw",  # 6: 0.667
            "nsw wsr",  # 7: 0.667, ties with 6 and loses on position
        ]
    )
    query = {"htp", "nsw", "wsr"}
    assert ce.overlap_ranking(query, stats, top_n=3) == [0, 1, 6]
    assert ce.overlap_ranking(query, stats, excluded={0}, top_n=3) == [1, 6, 7]
    everything = ce.overlap_ranking(query, stats, excluded={1}, top_n=10)
    assert everything == [0, 6, 7, 2, 5]
    assert 4 not in everything and 3 not in everything and 1 not in everything


def test_overlap_ranking_equals_a_brute_force_scan_on_random_corpora():
    rng = random.Random(7)
    for trial in range(15):
        readings = [" ".join(rng.sample(WORDS[:10], rng.randint(1, 5))) for _ in range(rng.randint(8, 40))]
        stats, df = _stats(readings)
        sets = [set(r.split()) for r in readings]
        excluded = set(rng.sample(range(len(readings)), 2))
        query = set(rng.sample(WORDS[:10], rng.randint(1, 4)))
        scored = sorted(
            (-len(query & s) / len(query | s), p)
            for p, s in enumerate(sets)
            if p not in excluded and query & s
        )
        want, seen = [], set()
        for _, p in scored:
            if stats.canonical[p] in seen:
                continue
            seen.add(stats.canonical[p])
            want.append(p)
            if len(want) == 3:
                break
        assert ce.overlap_ranking(query, stats, excluded) == want, trial


def test_bm25_prefers_a_rare_shared_token_where_jaccard_prefers_the_ubiquitous_one():
    fillers = [f"nb q{a}{b}" for a, b in itertools.product("abcdef", "abcde")]
    readings = ["nb", "wsr nfr anx mdw"] + fillers
    stats, _ = _stats(readings)
    query = {"nb", "wsr"}
    assert ce.overlap_ranking(query, stats, top_n=1) == [0]
    assert ce.bm25_ranking(query, stats, top_n=1) == [1]
    assert 0 not in ce.bm25_ranking(query, stats, excluded={0}, top_n=3)


def test_bm25_ignores_excluded_rows_and_is_deterministic():
    stats, _ = _stats(["htp nsw", "htp nsw", "htp nsw wsr", "mdw"])
    first = ce.bm25_ranking({"htp", "nsw"}, stats, excluded={0})
    assert first == ce.bm25_ranking({"htp", "nsw"}, stats, excluded={0})
    assert 0 not in first


def test_margin_arithmetic():
    app = [1, None, 2]  # top-3 2/3, MRR (1 + 0.5) / 3
    baseline = [None, None, 1]  # top-3 1/3, MRR 1/3
    margin = ce.margin_summary(app, baseline, "overlap_baseline")
    assert margin["overlap_baseline_top3_useful"] == round(1 / 3, 4)
    assert margin["margin_over_overlap_baseline_top3"] == round(2 / 3 - 1 / 3, 4)
    assert margin["overlap_baseline_mrr_value"] == round(1 / 3, 4)
    assert margin["margin_over_overlap_baseline_mrr_value"] == round(0.5 - 1 / 3, 4)
    assert ce.rank_metrics([]) == (0.0, 0.0)


def test_extra_summary_keys_cannot_collide_with_the_greps():
    text = ce.render_extra_summary(
        total=3,
        twin_threshold=0.7,
        queries_with_twins=1,
        twin_rows_removed=2,
        app_ranks=[1, None, 2],
        overlap_ranks=[None, None, 1],
        bm25_ranks=[1, 1, 1],
        near_exact_hits=1,
        strict_top3_hits=2,
    )
    for pattern in VERIFY_RELEASE_PATTERNS.values():
        assert re.search(pattern, text) is None


def test_strict_useful_rejects_a_match_on_particles_that_v4_accepts():
    """The audit scenario: the only shared tokens are `n` and `m`."""
    expected = {"n", "m", "aa", "bb"}
    candidate = {"n", "m"}
    v4_useful, *_ = ce.useful_decision(
        is_exact=False,
        candidate_tokens=candidate,
        candidate_lemmas=set(),
        expected_key_tokens=expected,
        expected_lemma_ids={"1", "2", "3"},
        token_threshold=0.34,
    )
    assert v4_useful is True
    assert not ce.strict_useful(False, candidate, set(), expected, {"1", "2", "3"})
    # Shared content words are enough, a shared lemma family is enough, exact always is.
    assert ce.strict_useful(False, {"aa", "bb", "n"}, set(), expected, {"1", "2", "3"})
    assert ce.strict_useful(False, {"zz"}, {"1", "2"}, {"aa", "bb"}, {"1", "2", "3"})
    assert ce.strict_useful(True, set(), set(), expected, set())


def test_candidate_lemmas_fast_matches_the_pool_scan():
    df = _frame(
        ["htp nsw", "htp nsw", "mdw rdi", "htp nsw"],
        ["1|a 2|b", "3|c", "9|z", "4|d"],
    )
    stats = ce.build_baseline_stats(df, TwinGuard(df))
    for excluded in (set(), {1}, {0, 3}):
        pool = df.drop(index=sorted(excluded))
        assert ce.candidate_lemmas_fast(stats, "htp nsw", excluded) == ce._candidate_lemmas(
            pool, "htp nsw"
        )


def test_compare_twin_scores_reports_the_rank_change(tmp_path):
    def result(ranks, shown):
        return pd.DataFrame(
            {
                "benchmark_id": ["B1", "B2"],
                "useful_family_rank": ranks,
                "exact_rank": ["", ""],
                "suggestions": shown,
                "twins_removed": [0, 1],
            }
        )

    twins_in = result([1, 2], ["a || b", "c || d"])
    twins_out = result(["", 2], ["x || b", "c || d"])
    metrics = compare_twin_scores.metrics_from_results(twins_out)
    assert metrics["top3_useful"] == 0.5 and metrics["failures"] == 1.0
    changes = compare_twin_scores.query_changes(twins_in, twins_out)
    assert list(changes["benchmark_id"]) == ["B1"]
    assert changes.loc[0, "useful_rank_twins_in"] == 1


# ---------------------------------------------------------------------------
# A26: no contaminated default benchmark, no committed default output
# ---------------------------------------------------------------------------

COMMITTED_OUTPUTS = [
    "competitive_ambiguity_eval_results.csv",
    "competitive_ambiguity_eval_failures.csv",
    "ranking_weight_tuning.csv",
    "reading_model_eval.csv",
    "reading_model_eval_clean.csv",
    "reading_model_errors.csv",
    "sign_reading_eval_results.csv",
    "sign_reading_eval_clean.csv",
    "sign_reading_eval_failures.csv",
]


def _fingerprint(name: str) -> tuple[str, int]:
    path = BENCHMARKS / name
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


@pytest.mark.parametrize("module", [ce, tune])
def test_benchmark_is_required(module, capsys):
    with pytest.raises(SystemExit) as raised:
        module._parse_args([])
    assert raised.value.code == 2
    assert "--benchmark" in capsys.readouterr().err


def test_tuner_output_defaults_to_a_temp_dir():
    args = tune._parse_args(["--benchmark", "x.csv"])
    assert args.output is None and args.min_queries == 40 and args.twin_threshold == 0.7
    path = tune._resolve_output(args)
    assert not path.resolve().is_relative_to((PROJECT_ROOT / "data").resolve())


def test_tuner_refuses_a_small_benchmark_unless_allowed(tmp_path):
    small = tmp_path / "small.csv"
    pd.DataFrame({"benchmark_id": list("abcd")}).to_csv(small, index=False)
    with pytest.raises(SystemExit) as raised:
        tune.main(["--benchmark", str(small), "--examples", str(tmp_path / "missing.csv")])
    assert raised.value.code not in (0, None)
    assert "--allow-small" in str(raised.value.code)


def test_resolving_default_paths_leaves_committed_outputs_untouched():
    """Path resolution only: no evaluator runs here. The run-level guarantee is
    test_a_default_competitive_run_writes_nothing_under_data below."""
    before = {name: _fingerprint(name) for name in COMMITTED_OUTPUTS if (BENCHMARKS / name).exists()}
    assert before, "the committed result files should exist"
    ce._resolve_output_paths(ce._parse_args(["--benchmark", "x.csv"]))
    tune._resolve_output(tune._parse_args(["--benchmark", "x.csv"]))
    se._parse_args([])
    rm._parse_args([])
    assert {name: _fingerprint(name) for name in before} == before


def test_the_dead_80_query_benchmark_stays_dead():
    assert not (BENCHMARKS / "tuning_benchmark_80.csv").exists()


def test_tuner_cache_pool_drops_the_targets_twins_only_when_asked(tmp_path):
    corpus = load_examples_csv(str(_write_corpus(tmp_path, TWIN_CORPUS)))
    bench = pd.read_csv(_write_benchmark(tmp_path)).fillna("")
    twin = "ḥtp ḏꞽ nsw wsꞽr nb ꜥnḫ ḥr"

    def pool_readings(guard, threshold) -> set[str]:
        cache = tune.build_query_cache(corpus, bench, guard, threshold)
        return set(cache[0]["scored"]["transliteration_gold"])

    guard = TwinGuard(corpus)
    assert twin in pool_readings(None, 0.0)  # library default: only the target leaves
    assert twin in pool_readings(guard, 0.0)
    without = pool_readings(guard, 0.7)
    assert twin not in without
    assert "ḥtp ḏi̯ nsw wsꞽr nb ꜥnḫ" not in without  # the target itself is always out
    assert "ḥtp nsw ꜥnḫ ḥꜣt" in without  # a genuine rival stays


# ---------------------------------------------------------------------------
# A56: sign-reading eval duplicate handling
# ---------------------------------------------------------------------------

def _glyph(index: int) -> str:
    return chr(0x13000 + index)


G = [_glyph(i) for i in range(0, 12)]


def _sign_frame(rows: list[tuple[list[str], str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": ["TLA"] * len(rows),
            "source_text_id": [f"T{i}" for i in range(len(rows))],
            "source_sentence_id": [f"S{i}" for i in range(len(rows))],
            "hieroglyphs_norm": [" ".join(signs) for signs, _ in rows],
            "transliteration_gold": [reading for _, reading in rows],
        }
    )


def test_sign_pool_removes_copies_by_signs_and_by_reading_and_keeps_the_rest():
    df = _sign_frame(
        [
            (G[0:5], "htp nsw wsr nfr anx"),  # 0 the target
            (G[0:5], "mdw rdi sdm iri mry"),  # 1 identical sign groups
            (G[0:4], "xpr pwt snb wdj"),  # 2 4 of 5 shared -> Jaccard 0.8
            (G[0:3], "mnx sxm bik"),  # 3 3 of 5 shared -> 0.6, kept
            (G[6:11], "htp nsw wsr nfr anx"),  # 4 other signs, same reading
            (G[6:9], "kmt tpi ddi"),  # 5 unrelated
        ]
    )
    guard = se.SignDuplicateGuard(df, 0.8)
    assert guard.removals(0) == {1, 2, 4}
    keep = se.pool_keep_mask(df, df.iloc[0], guard.removals(0))
    assert list(np.flatnonzero(keep)) == [3, 5]  # the target itself is always out
    # Rule off: only the target leaves, exactly the legacy pool.
    legacy = se.SignDuplicateGuard(df, 0.0)
    assert legacy.removals(0) == set()
    assert list(np.flatnonzero(se.pool_keep_mask(df, df.iloc[0], legacy.removals(0)))) == [1, 2, 3, 4, 5]


def test_sign_eval_defaults_and_the_legacy_switches():
    defaults = se._parse_args([])
    assert defaults.exclude_duplicates is True and defaults.near_duplicate_overlap == 0.8
    assert defaults.results.endswith("sign_reading_eval_results_v2.csv")
    assert defaults.failures.endswith("sign_reading_eval_failures_v2.csv")
    legacy = se._parse_args(["--no-exclude-duplicates"])
    assert legacy.exclude_duplicates is False
    exact_only = se._parse_args(["--exclude-duplicates", "--near-duplicate-overlap", "0"])
    assert exact_only.exclude_duplicates is True and exact_only.near_duplicate_overlap == 0
    # The pre-A56 flag spelling still parses.
    assert se._parse_args(["--exclude-duplicates"]).exclude_duplicates is True
    assert not defaults.results.endswith("sign_reading_eval_results.csv")


def test_sign_source_table_reports_each_source():
    results = pd.DataFrame(
        {
            "source": ["TLA", "TLA", "Ramses"],
            "top1_exact": [True, False, False],
            "top3_exact": [True, False, False],
            "top3_useful": [True, True, False],
            "pool_rows_removed": [2, 0, 4],
        }
    )
    table = se.source_table(results)
    assert table.loc["TLA", "queries"] == 2 and table.loc["TLA", "top3_useful"] == 1.0
    assert table.loc["Ramses", "top3_useful"] == 0.0 and table.loc["Ramses", "mean_pool_rows_removed"] == 4


# ---------------------------------------------------------------------------
# A24 / A56: reading-model eval
# ---------------------------------------------------------------------------


def _split_frame() -> pd.DataFrame:
    """20 sentences with disjoint signs; every 5th (0, 5, 10, 15) is the test split.

    Row 1 repeats test row 0's signs (an exact copy in training), row 6 is 4 of test
    row 5's 5 groups (Jaccard 0.8, a near copy) and row 11 is 3 of test row 10's 5
    groups (0.6, kept).
    """
    signs = [[_glyph(10 * i + k) for k in range(5)] for i in range(20)]
    signs[1] = list(signs[0])
    signs[6] = signs[5][:4]
    signs[11] = signs[10][:3]
    sources = {0: "Ramses", 5: "AES", 10: "TLA", 15: "BBAW", 1: "Ramses", 2: "AES"}
    return pd.DataFrame(
        {
            "source": [sources.get(i, "TLA") for i in range(20)],
            "hieroglyphs_norm": [" ".join(group) for group in signs],
            "transliteration_gold": [" ".join(f"r{k}" for k in group) for group in signs],
        }
    )


def test_select_test_rows_drops_exact_and_near_copies_and_reports_both():
    frame = _split_frame()
    split = rm.select_test_rows(frame, 0.2, True, 0.8, lexicon_on=False, lexicon_exclude_sources=set())
    assert split.exact_duplicates == 1  # row 0
    assert split.near_duplicates == 1  # row 5 (row 6 is its 0.8 copy)
    assert list(split.test.index) == [10, 15]  # row 10's 0.6 neighbour is kept
    assert len(split.train) == 16 and set(split.train.index).isdisjoint({0, 5, 10, 15})


def test_select_test_rows_legacy_settings_keep_everything():
    frame = _split_frame()
    split = rm.select_test_rows(frame, 0.2, False, 0.0, lexicon_on=False, lexicon_exclude_sources=set())
    assert list(split.test.index) == [0, 5, 10, 15]
    assert split.exact_duplicates == 1 and split.near_duplicates == 0
    exact_only = rm.select_test_rows(frame, 0.2, True, 0.0, False, set())
    assert list(exact_only.test.index) == [5, 10, 15] and exact_only.near_duplicates == 0


def test_lexicon_on_removes_ramses_and_aes_from_test_but_not_from_training():
    frame = _split_frame()
    split = rm.select_test_rows(
        frame, 0.2, False, 0.0, lexicon_on=True, lexicon_exclude_sources={"Ramses", "AES"}
    )
    assert set(split.test["source"]) <= {"TLA", "BBAW"}
    assert split.excluded_for_lexicon == 2  # row 0 (Ramses) and row 5 (AES)
    assert "Ramses" in set(split.train["source"]) and "AES" in set(split.train["source"])
    # Without the lexicon nothing is excluded.
    kept = rm.select_test_rows(frame, 0.2, False, 0.0, lexicon_on=False, lexicon_exclude_sources={"Ramses", "AES"})
    assert kept.excluded_for_lexicon == 0 and list(kept.test.index) == [0, 5, 10, 15]


def test_reading_eval_defaults():
    args = rm._parse_args([])
    assert args.exclude_duplicates is True and args.near_duplicate_overlap == 0.8
    assert args.lexicon_exclude_test_sources == "Ramses,AES"
    assert args.results.endswith("reading_model_eval_v2.csv")
    assert args.errors.endswith("reading_model_errors_v2.csv")
    assert args.by_source_results.endswith("reading_model_eval_by_source_v2.csv")
    legacy = rm._parse_args(
        ["--no-exclude-duplicates", "--near-duplicate-overlap", "0", "--lexicon-exclude-test-sources", ""]
    )
    assert legacy.exclude_duplicates is False and legacy.near_duplicate_overlap == 0
    assert rm.parse_source_list(legacy.lexicon_exclude_test_sources) == set()
    assert rm.parse_source_list(" Ramses, AES ,") == {"Ramses", "AES"}
    # The documented sign-function command still parses.
    assert rm._parse_args(["--exclude-duplicates", "--sizes", "0"]).sizes == "0"


def _end_to_end_corpus(tmp_path: Path) -> Path:
    """60 aligned sentences over 8 signs with two readings each; sources cycle."""
    rng = random.Random(3)
    base = {g: f"b{i}" for i, g in enumerate(G[:8])}
    alt = {g: f"a{i}" for i, g in enumerate(G[:8])}
    sources = ["TLA", "AES", "Ramses", "BBAW"]
    records = []
    for i in range(60):
        signs = [rng.choice(G[:6]) for _ in range(4)]
        if i % 5 == 0:
            # Test sentences carry two signs the training split never sees: one the
            # lexicon knows (G[6]) and one it does not (G[7], fallback).
            signs[0], signs[1] = G[6], G[7]
        readings = [base[g] if rng.random() < 0.7 else alt[g] for g in signs]
        record = {column: "" for column in REQUIRED_COLUMNS}
        record.update(
            source=sources[i % 4],
            source_text_id=f"T{i}",
            source_sentence_id=f"S{i}",
            hieroglyphs=" ".join(signs),
            transliteration_gold=" ".join(readings),
            review_status="draft",
        )
        records.append(record)
    path = tmp_path / "reading_corpus.csv"
    pd.DataFrame(records).to_csv(path, index=False)
    return path


def test_by_source_counters_sum_to_the_pooled_counters(tmp_path, monkeypatch):
    lexicon = Lexicon()
    lexicon.readings[G[6]] = Counter({"b6": 9, "a6": 1})
    lexicon.sources = {G[6]: "Ramses"}
    monkeypatch.setattr(rm, "load_lexicon", lambda: lexicon)
    corpus = _end_to_end_corpus(tmp_path)
    results, errors, by_source = (tmp_path / n for n in ("r.csv", "e.csv", "s.csv"))
    rm.main(
        [
            "--examples", str(corpus), "--sizes", "0",
            "--no-exclude-duplicates", "--lexicon-exclude-test-sources", "",
            "--results", str(results), "--errors", str(errors), "--by-source-results", str(by_source),
        ]
    )
    pooled = pd.read_csv(results).iloc[0]
    per_source = pd.read_csv(by_source)
    assert set(per_source["source"]) == {"TLA", "AES", "Ramses", "BBAW"}, "a row per source"
    assert per_source["test_sentences"].sum() == pooled["test_sentences"]
    assert per_source["unseen_signs"].sum() == pooled["unseen_signs"] > 0
    assert per_source["lexicon_predictions"].sum() == pooled["lexicon_predictions"] > 0
    assert per_source["fallback_predictions"].sum() == pooled["fallback_predictions"]
    assert per_source["ambiguous_instances"].sum() == pooled["ambiguous_instances"] > 0
    pooled_correct = round(pooled["acc_lexicon"] * pooled["lexicon_predictions"])
    assert per_source["lexicon_correct"].sum() == pooled_correct
    # New summary columns are appended after the old ones.
    columns = list(pd.read_csv(results).columns)
    assert columns.index("right_context_gain") < columns.index("test_sentences_excluded_for_lexicon")


def test_reading_eval_excludes_lexicon_leaking_sources_by_default(tmp_path, monkeypatch):
    lexicon = Lexicon()
    lexicon.readings[G[6]] = Counter({"b6": 9})
    lexicon.sources = {G[6]: "Ramses"}
    monkeypatch.setattr(rm, "load_lexicon", lambda: lexicon)
    corpus = _end_to_end_corpus(tmp_path)

    def run(*extra: str) -> tuple[pd.Series, pd.DataFrame]:
        tag = "_".join(extra).replace("-", "") or "default"
        results, by_source = tmp_path / f"{tag}_r.csv", tmp_path / f"{tag}_s.csv"
        rm.main(
            ["--examples", str(corpus), "--sizes", "0", "--no-exclude-duplicates",
             "--results", str(results), "--errors", str(tmp_path / f"{tag}_e.csv"),
             "--by-source-results", str(by_source), *extra]
        )
        return pd.read_csv(results).iloc[0], pd.read_csv(by_source)

    default_row, default_sources = run()
    assert set(default_sources["source"]) == {"TLA", "BBAW"}
    assert default_row["lexicon_test_sources_excluded"] == "AES,Ramses"
    assert default_row["test_sentences_excluded_for_lexicon"] > 0
    nolex_row, nolex_sources = run("--no-lexicon")
    assert set(nolex_sources["source"]) == {"TLA", "AES", "Ramses", "BBAW"}
    assert nolex_row["test_sentences_excluded_for_lexicon"] == 0


# ---------------------------------------------------------------------------
# A25: the proposal exists
# ---------------------------------------------------------------------------


def test_test_set_proposal_is_present_and_covers_its_sections():
    text = (PROJECT_ROOT / "docs" / "test-set-proposal-2026-10-11.md").read_text(encoding="utf-8")
    for heading in ("Size", "Sampling", "Twin guard", "Custody"):
        assert re.search(rf"^#+ .*{heading}", text, flags=re.MULTILINE), heading
    assert "proposal" in text.lower()


def test_scorer_records_that_the_shipped_weights_cannot_be_reproduced():
    """A26: the tuning benchmark behind the weights is gone, and the code says so."""
    text = (PROJECT_ROOT / "app" / "retrieval" / "scorer.py").read_text(encoding="utf-8")
    assert "cannot be re-run" in text and "audit A26" in text


def test_proposal_quotes_no_unregistered_margin():
    """No new measurement goes into a doc before it is pre-registered."""
    text = (PROJECT_ROOT / "docs" / "test-set-proposal-2026-10-11.md").read_text(encoding="utf-8")
    assert "margin over plain word overlap is" not in text
    assert "pre-registered" in text


# ---------------------------------------------------------------------------
# Fix round 1 (2026-10-25): review findings on the eval branch
# ---------------------------------------------------------------------------


def test_a_default_competitive_run_writes_nothing_under_data(tmp_path, capsys, monkeypatch):
    """A26 (review nit): a real, tiny evaluator run with no --results/--failures. Every
    file it writes is recorded, so a hardcoded committed path would fail here, not
    only a wrong default in argparse."""
    corpus = _write_corpus(tmp_path, TWIN_CORPUS)
    bench = _write_benchmark(tmp_path)
    before = {name: _fingerprint(name) for name in COMMITTED_OUTPUTS if (BENCHMARKS / name).exists()}
    written: list[Path] = []
    original = pd.DataFrame.to_csv

    def recording_to_csv(self, path_or_buf=None, *args, **kwargs):
        if path_or_buf is not None and not hasattr(path_or_buf, "write"):
            written.append(Path(path_or_buf).resolve())
        return original(self, path_or_buf, *args, **kwargs)

    data_dir = (PROJECT_ROOT / "data").resolve()
    tree_before = _data_tree_state(data_dir)
    monkeypatch.setattr(pd.DataFrame, "to_csv", recording_to_csv)
    ce.main(["--examples", str(corpus), "--benchmark", str(bench), "--stage", "none"])
    assert len(written) == 2, written  # results and failures, nothing else
    assert all(not path.is_relative_to(data_dir) for path in written), written
    assert {name: _fingerprint(name) for name in before} == before
    # Writes that bypass DataFrame.to_csv (open(), Path.write_text) would not be
    # recorded above; every file under data/ keeping its size and mtime catches them.
    assert _data_tree_state(data_dir) == tree_before


def _data_tree_state(root: Path) -> dict[str, tuple[int, int]]:
    """relative path -> (size, mtime_ns) for every file under `root`."""
    state = {}
    for path in root.rglob("*"):
        if path.is_file():
            info = path.stat()
            state[str(path.relative_to(root))] = (info.st_size, info.st_mtime_ns)
    return state


@pytest.mark.parametrize("bad", ["70", "-0.1", "1.5", "nan", "x"])
def test_exclude_twins_refuses_a_threshold_outside_0_to_1(bad, capsys):
    with pytest.raises(SystemExit) as raised:
        ce._parse_args(["--benchmark", "x.csv", "--exclude-twins", bad])
    assert raised.value.code == 2
    assert "--exclude-twins" in capsys.readouterr().err


@pytest.mark.parametrize("good, value", [("0", 0.0), ("0.7", 0.7), ("1", 1.0)])
def test_exclude_twins_accepts_off_and_thresholds(good, value):
    assert ce._parse_args(["--benchmark", "x.csv", "--exclude-twins", good]).exclude_twins == value


def test_summary_labels_the_pool_as_legacy_or_twin_controlled(tmp_path, capsys):
    """A4/A23 (review blocker, eval side): a run says which kind of number it is."""
    _, off = _run_eval(tmp_path, capsys, tag="off")
    _, on = _run_eval(tmp_path, capsys, "--exclude-twins", "0.7", tag="on")
    assert "pool: legacy" in off and "pool: twin-controlled" not in off
    assert "pool: twin-controlled" in on and "pool: legacy" not in on
    for out in (off, on):
        for pattern in VERIFY_RELEASE_PATTERNS.values():
            first = re.search(pattern, out)
            assert first is not None
            assert first.start() < out.index("pool:")


def test_key_token_drift_is_reported_per_query_and_in_the_summary(tmp_path, capsys):
    """A55/A17: the frozen expected_key_tokens disagree with today's tokens of the
    target row; the run says so instead of silently scoring against stale tokens."""
    corpus = _write_corpus(tmp_path, TWIN_CORPUS)
    bench_path = _write_benchmark(tmp_path)
    bench = pd.read_csv(bench_path)
    bench.loc[0, "expected_key_tokens"] = "htp di nsw wsir nb anx pl"  # a stale `pl`
    bench.to_csv(bench_path, index=False)
    capsys.readouterr()
    ce.main(
        [
            "--examples", str(corpus), "--benchmark", str(bench_path),
            "--results", str(tmp_path / "r.csv"), "--failures", str(tmp_path / "f.csv"),
            "--stage", "none",
        ]
    )
    out = capsys.readouterr().out
    results = pd.read_csv(tmp_path / "r.csv").fillna("")
    guard = TwinGuard(load_examples_csv(str(corpus)))
    current = guard.token_sets[guard.target_positions(bench.iloc[0])[0]]
    recorded = set(bench.loc[0, "expected_key_tokens"].split())
    want = ce.format_token_drift(recorded - current, current - recorded)
    assert "-pl" in want.split()
    assert results.loc[0, "key_token_drift"] == want
    assert "key_token_drift_queries: 1" in out
    # Appended after every earlier column; only fix round 2's three follow it.
    assert list(results.columns)[-4] == "key_token_drift"


def test_key_token_drift_is_empty_for_an_absent_target():
    df = _frame(["htp nsw"])
    row = pd.Series(
        {"expected_source_text_id": "nope", "expected_source_sentence_id": "nope", "expected_key_tokens": "zz"}
    )
    assert ce.key_token_drift(row, TwinGuard(df)) == (set(), set())
    assert ce.format_token_drift({"b", "a"}, {"c"}) == "-a -b +c"


def _reference_bm25(query: set[str], readings: list[str], excluded: set[int]) -> dict[int, float]:
    """Textbook Okapi BM25 written out independently (k1 1.5, b 0.75)."""
    docs = [r.split() for r in readings]
    n = len(docs)
    average = sum(len(d) for d in docs) / n
    out: dict[int, float] = {}
    for position, doc in enumerate(docs):
        if position in excluded:
            continue
        score = 0.0
        for token in query:
            tf = doc.count(token)
            if not tf:
                continue
            df_t = sum(1 for d in docs if token in d)
            idf = np.log(1 + (n - df_t + 0.5) / (df_t + 0.5))
            score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * len(doc) / average))
        if score:
            out[position] = score
    return out


def test_bm25_counts_repeated_tokens_like_conventional_bm25():
    """A23 (review): binary BM25 scored `htp nsw` and `htp htp nsw nsw` identically
    (same distinct tokens), so the earlier row won the tie. Conventional BM25 gives
    the repeated row tf 2 at length 4, which wins at this average length."""
    readings = ["htp nsw", "htp htp nsw nsw"]
    stats, _ = _stats(readings)
    assert stats.lengths == [2, 4]
    assert ce.bm25_ranking({"htp"}, stats, top_n=2) == [1, 0]


def test_bm25_scores_equal_a_textbook_implementation_on_random_corpora():
    rng = random.Random(11)
    for trial in range(15):
        readings = [
            " ".join(rng.choice(WORDS[:8]) for _ in range(rng.randint(1, 6)))
            for _ in range(rng.randint(5, 30))
        ]
        stats, _ = _stats(readings)
        query = set(rng.sample(WORDS[:8], rng.randint(1, 3)))
        excluded = set(rng.sample(range(len(readings)), 1))
        got = ce.bm25_scores(query, stats, excluded)
        want = _reference_bm25(query, readings, excluded)
        assert set(got) == set(want), trial
        for position, score in want.items():
            assert got[position] == pytest.approx(score), (trial, position)


def _compare_frame(ids, threshold, **overrides) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "benchmark_id": ids,
            "query_input": [f"q{i}" for i in ids],
            "query_type": ["simplified_transliteration"] * len(ids),
            "expected_transliteration": [f"e{i}" for i in ids],
            "expected_source_text_id": [f"T{i}" for i in ids],
            "expected_source_sentence_id": [f"S{i}" for i in ids],
            "expected_key_tokens": [f"k{i} x" for i in ids],
            "expected_lemma_ids": [f"L{i}" for i in ids],
            "acceptable_token_overlap_threshold": [0.26] * len(ids),
            "stage_mode": ["auto"] * len(ids),
            "query_path": ["app"] * len(ids),
            "useful_rule": ["v4"] * len(ids),
            "expected_tokens": ["current"] * len(ids),
            "twin_exclusion": [threshold] * len(ids),
            "useful_family_rank": [1] * len(ids),
            "exact_rank": [""] * len(ids),
            "suggestions": ["a"] * len(ids),
        }
    )
    for column, value in overrides.items():
        frame[column] = value
    return frame


def test_compare_accepts_a_matching_pair():
    compare_twin_scores.validate_pair(_compare_frame(["B1", "B2"], 0.0), _compare_frame(["B2", "B1"], 0.7))


@pytest.mark.parametrize(
    "twins_in, twins_out, message",
    [
        # The reviewer's scenario: a failing query missing from one run.
        (_compare_frame(["B1", "B2"], 0.0), _compare_frame(["B1"], 0.7), "different queries"),
        (_compare_frame(["B1", "B1"], 0.0), _compare_frame(["B1"], 0.7), "repeats"),
        (
            _compare_frame(["B1"], 0.0),
            _compare_frame(["B1"], 0.7, query_input=["other"]),
            "query_input differs",
        ),
        (
            _compare_frame(["B1"], 0.0),
            _compare_frame(["B1"], 0.7, expected_source_sentence_id=["S9"]),
            "expected_source_sentence_id differs",
        ),
        (_compare_frame(["B1"], 0.0), _compare_frame(["B1"], 0.7, stage_mode=["none"]), "stage_mode"),
        (_compare_frame(["B1"], 0.7), _compare_frame(["B1"], 0.7), "not off"),
        (_compare_frame(["B1"], 0.0), _compare_frame(["B1"], 0.0), "not in (0, 1]"),
        (
            _compare_frame(["B1", "B2"], 0.0),
            _compare_frame(["B1", "B2"], 0.7, twin_exclusion=[0.7, 0.8]),
            "not constant",
        ),
    ],
)
def test_compare_refuses_mismatched_pairs(twins_in, twins_out, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        compare_twin_scores.validate_pair(twins_in, twins_out, "v4")


def test_compare_main_refuses_a_pair_with_a_dropped_query(tmp_path):
    twins_in, twins_out = tmp_path / "in.csv", tmp_path / "out.csv"
    _compare_frame(["B1", "B2"], 0.0).to_csv(twins_in, index=False)
    _compare_frame(["B1"], 0.7).to_csv(twins_out, index=False)
    metrics, changes = tmp_path / "m.csv", tmp_path / "c.csv"
    with pytest.raises(ValueError, match="different queries"):
        compare_twin_scores.main(
            ["--pair", "v4", str(twins_in), str(twins_out),
             "--metrics-output", str(metrics), "--changes-output", str(changes)]
        )
    assert not metrics.exists() and not changes.exists()


# A56 (review): text-level split

AES_REF = "AES/sawlit#text={text}&sentence={sentence}"


def _text_frame() -> pd.DataFrame:
    """Rows with real text identities: two AES texts of three sentences, Ramses rows
    naming their official split, and TLA/BBAW rows with none."""
    rows = [
        ("AES", "AES_1", "s1", AES_REF.format(text="TXTA", sentence="1")),
        ("TLA", "TLA_EARLIER_001", "S001", "x#row=1"),
        ("AES", "AES_2", "s2", AES_REF.format(text="TXTA", sentence="2")),
        ("AES", "AES_3", "s3", AES_REF.format(text="TXTB", sentence="3")),
        ("Ramses", "RAMSES_A", "S_test_1", "ramses-trl 2019-09-01 test line 1"),
        ("Ramses", "RAMSES_B", "S_train_2", "ramses-trl 2019-09-01 train line 2"),
        ("Ramses", "RAMSES_C", "S_val_3", "ramses-trl 2019-09-01 val line 3"),
        ("BBAW", "bbaw_egyptian_2018", "B1", "phiwi/bbaw_egyptian"),
        ("BBAW", "bbaw_egyptian_2018", "B2", "phiwi/bbaw_egyptian"),
        ("AES", "AES_4", "s4", AES_REF.format(text="TXTA", sentence="4")),
        ("AES", "AES_5", "s5", AES_REF.format(text="TXTB", sentence="5")),
        ("TLA", "TLA_EARLIER_002", "S002", "x#row=2"),
    ]
    frame = pd.DataFrame(rows, columns=["source", "source_text_id", "source_sentence_id", "source_ref"])
    signs = [[_glyph(10 * i + k) for k in range(3)] for i in range(len(frame))]
    frame["hieroglyphs_norm"] = [" ".join(group) for group in signs]
    frame["transliteration_gold"] = [" ".join(f"r{i}{k}" for k in range(3)) for i in range(len(frame))]
    return frame


def test_text_group_keys_use_the_aes_text_id_and_fall_back_to_the_sentence():
    keys = text_group_keys(_text_frame())
    assert keys[0] == keys[2] == keys[9] == "AES:text:TXTA"
    assert keys[3] == keys[10] == "AES:text:TXTB"
    # BBAW shares one source_text_id but has no text identity: each row is its own group.
    assert keys[7] != keys[8]
    assert len(set(keys)) == len(keys) - 3


def test_ramses_official_split_is_read_from_source_ref():
    assert ramses_official_split("Ramses", "ramses-trl 2019-09-01 test line 7") == "test"
    assert ramses_official_split("Ramses", "ramses-trl 2019-09-01 val line 7") == "val"
    assert ramses_official_split("Ramses", "something else") is None
    assert ramses_official_split("TLA", "ramses-trl 2019-09-01 test line 7") is None


def test_text_split_keeps_every_text_on_one_side_and_uses_the_ramses_split():
    frame = _text_frame()
    split = rm.select_test_rows(frame, 0.5, False, 0.0, False, set(), split_by="text")
    test_ids = set(split.test["source_sentence_id"])
    # Group ordinals (first appearance, Ramses rows aside): TXTA 0, TLA_001 1, TXTB 2,
    # B1 3, B2 4, TLA_002 5 -> every 2nd group: TXTA, TXTB, B2.
    assert test_ids == {"s1", "s2", "s4", "s3", "s5", "B2", "S_test_1"}
    assert "S_train_2" in set(split.train["source_sentence_id"])
    assert "S_val_3" in set(split.train["source_sentence_id"])
    train_keys = set(text_group_keys(split.train))
    assert train_keys.isdisjoint(text_group_keys(split.test))


def test_sentence_split_leaks_a_text_across_the_split_and_the_check_catches_it():
    """Why the text split exists: the old every-k-th split puts TXTA on both sides."""
    frame = _text_frame()
    old = rm.select_test_rows(frame, 0.5, False, 0.0, False, set(), split_by="sentence")
    with pytest.raises(ValueError, match="both train and test"):
        assert_text_groups_disjoint(old.train, old.test)


def test_text_split_equals_the_old_split_when_no_row_has_a_text_identity():
    frame = _split_frame()  # no source_ref: every sentence is its own group
    for exclude in (False, True):
        old = rm.select_test_rows(frame, 0.2, exclude, 0.8, False, set(), split_by="sentence")
        new = rm.select_test_rows(frame, 0.2, exclude, 0.8, False, set(), split_by="text")
        assert list(new.test.index) == list(old.test.index)
        assert list(new.train.index) == list(old.train.index)


def test_reading_eval_defaults_to_the_text_split():
    assert rm._parse_args([]).split == "text"
    assert rm._parse_args(["--split", "sentence"]).split == "sentence"
    with pytest.raises(ValueError):
        rm.select_test_rows(_split_frame(), 0.2, False, 0.0, False, set(), split_by="nope")


def test_sign_pool_drops_the_targets_own_text_only_when_asked():
    frame = _text_frame()
    same_text = se.SignDuplicateGuard(frame, 0.0, same_text=True)
    assert same_text.removals(0) == {2, 9}  # the other TXTA sentences
    assert same_text.removals(7) == set()  # BBAW: no text identity
    legacy = se.SignDuplicateGuard(frame, 0.0)
    assert legacy.removals(0) == set()
    args = se._parse_args([])
    assert args.exclude_same_text is True
    assert se._parse_args(["--no-exclude-same-text"]).exclude_same_text is False


# A25 (review): the proposal records the decisions and does not claim the fix


def test_test_set_proposal_records_the_decisions_and_keeps_a25_open():
    text = (PROJECT_ROOT / "docs" / "test-set-proposal-2026-10-11.md").read_text(encoding="utf-8")
    assert re.search(r"^## Decisions", text, flags=re.MULTILINE)
    assert "A25 stays OPEN" in text
    assert "n = 200" in text and "stratified and seeded" in text
    assert "data/private/" in text and "gitignored" in text
    # load_private_examples globs data/private/*.csv, so the doc must forbid a top-level file.
    assert "never as a top-level CSV" in text
    assert "until after the first report" in text


# ---------------------------------------------------------------------------
# Fix round 2 (2026-10-25): Opus + Astra reviews of fix round 1
# ---------------------------------------------------------------------------


def test_scoring_tokens_come_from_the_same_normaliser_as_the_candidates():
    """A55/A17 (Astra blocker): the default scoring runs the expected reading through
    the exact token rule `_useful_reason` applies to a candidate, so a normaliser
    change moves both sides together. 'frozen' is the recorded column, unchanged."""
    for reading in ["n{t}n.t =f", "wḫꜣ{ḫ} ḥr", "ḥtp ḏi̯ nsw.t", "pr.pl ꜥꜣ"]:
        row = pd.Series({"expected_transliteration": reading, "expected_key_tokens": "stale pl"})
        assert ce.scoring_key_tokens(row) == ce._tokens(loose_reading_form(reading))
        assert ce.scoring_key_tokens(row, "frozen") == {"stale", "pl"}
    with pytest.raises(ValueError):
        ce.scoring_key_tokens(row, "nope")


def test_a_stale_frozen_token_column_no_longer_decides_the_default_score(tmp_path, capsys):
    """Astra's counterexample in miniature: the frozen tokens disagree with today's
    normaliser. The default run scores with today's tokens on both sides (the twin is
    a useful lead); --expected-tokens frozen reproduces the old mixed scoring (it is
    not), and each run says which scoring it used, per row and in the summary."""
    corpus = _write_corpus(tmp_path, TWIN_CORPUS)
    bench_path = _write_benchmark(tmp_path)
    bench = pd.read_csv(bench_path)
    bench.loc[0, "expected_key_tokens"] = "qq1 qq2 qq3 qq4"
    bench.to_csv(bench_path, index=False)

    def run(*extra: str) -> tuple[pd.DataFrame, str]:
        tag = extra[-1] if extra else "default"
        capsys.readouterr()
        ce.main(
            ["--examples", str(corpus), "--benchmark", str(bench_path),
             "--results", str(tmp_path / f"{tag}_r.csv"), "--failures", str(tmp_path / f"{tag}_f.csv"),
             "--stage", "none", *extra]
        )
        return pd.read_csv(tmp_path / f"{tag}_r.csv").fillna(""), capsys.readouterr().out

    current, current_out = run()
    frozen, frozen_out = run("--expected-tokens", "frozen")
    assert current.loc[0, "suggestions"] == frozen.loc[0, "suggestions"]
    assert current.loc[0, "useful_family_rank"] != "" and frozen.loc[0, "useful_family_rank"] == ""
    assert current.loc[0, "expected_tokens"] == "current" and frozen.loc[0, "expected_tokens"] == "frozen"
    assert "expected_tokens: current" in current_out
    assert "expected_tokens: frozen" in frozen_out
    for out in (current_out, frozen_out):
        for key, pattern in VERIFY_RELEASE_PATTERNS.items():
            own = re.search(rf"^{key}: ([\d.]+)$", out, flags=re.MULTILINE)
            assert re.search(pattern, out).group(1) == own.group(1), key


def test_expected_tokens_defaults_to_current():
    assert ce._parse_args(["--benchmark", "x.csv"]).expected_tokens == "current"
    assert ce._parse_args(["--benchmark", "x.csv", "--expected-tokens", "frozen"]).expected_tokens == "frozen"


def test_the_typed_query_reaches_the_suggestion_layer_when_it_takes_query_raw(tmp_path, capsys, monkeypatch):
    """The services fix (A54) adds `query_raw=` to suggest_top_readings; the harness
    passes the query as typed, exactly as the app does, and omits it on a layer that
    does not take it yet."""
    import inspect

    assert ce.SUGGEST_TAKES_QUERY_RAW == (
        "query_raw" in inspect.signature(ce.suggest_top_readings).parameters
    )
    original = ce.suggest_top_readings
    seen: list[dict] = []

    def recording(*args, **kwargs):
        seen.append(dict(kwargs))
        kwargs.pop("query_raw", None)
        return original(*args, **kwargs)

    monkeypatch.setattr(ce, "suggest_top_readings", recording)
    monkeypatch.setattr(ce, "SUGGEST_TAKES_QUERY_RAW", True)
    _run_eval(tmp_path, capsys, tag="raw")
    assert seen and seen[-1]["query_raw"] == "htp di nsw wsir nb"
    monkeypatch.setattr(ce, "SUGGEST_TAKES_QUERY_RAW", False)
    _run_eval(tmp_path, capsys, tag="noraw")
    assert "query_raw" not in seen[-1]


@pytest.mark.parametrize(
    "column, other",
    [
        ("expected_key_tokens", ["k1 y"]),
        ("expected_lemma_ids", ["L9"]),
        ("acceptable_token_overlap_threshold", [0.34]),
    ],
)
def test_compare_refuses_a_pair_whose_scoring_definition_differs(column, other):
    """Astra (should_fix): v4 and v4_driftcorrected have the same queries and targets
    but different expected tokens on 12 rows; such a pair used to be accepted."""
    with pytest.raises(ValueError, match=re.escape(f"{column} differs")):
        compare_twin_scores.validate_pair(
            _compare_frame(["1"], 0.0), _compare_frame(["1"], 0.7, **{column: other})
        )


@pytest.mark.parametrize("column", ["stage_mode", "query_path", "useful_rule", "expected_tokens"])
def test_compare_refuses_a_run_that_does_not_record_its_configuration(column):
    with pytest.raises(ValueError, match=re.escape(f"does not record {column}")):
        compare_twin_scores.validate_pair(
            _compare_frame(["B1"], 0.0), _compare_frame(["B1"], 0.7).drop(columns=[column])
        )
    with pytest.raises(ValueError, match=re.escape(f"does not record {column}")):
        compare_twin_scores.validate_pair(
            _compare_frame(["B1"], 0.0).drop(columns=[column]),
            _compare_frame(["B1"], 0.7).drop(columns=[column]),
        )


@pytest.mark.parametrize(
    "column, value",
    [("query_path", "legacy"), ("useful_rule", "v5"), ("expected_tokens", "frozen")],
)
def test_compare_refuses_a_pair_run_under_different_settings(column, value):
    with pytest.raises(ValueError, match=re.escape(f"{column} differs")):
        compare_twin_scores.validate_pair(
            _compare_frame(["B1"], 0.0), _compare_frame(["B1"], 0.7, **{column: [value]})
        )


def test_two_real_runs_make_a_valid_pair(tmp_path, capsys):
    """The eval records every column validate_pair requires."""
    off, _ = _run_eval(tmp_path, capsys, tag="off")
    on, _ = _run_eval(tmp_path, capsys, "--exclude-twins", "0.7", tag="on")
    off = pd.read_csv(tmp_path / "off_results.csv").fillna("")
    on = pd.read_csv(tmp_path / "on_results.csv").fillna("")
    compare_twin_scores.validate_pair(off, on, "synthetic")
    assert list(on.columns)[-3:] == ["query_path", "useful_rule", "expected_tokens"]


@pytest.mark.parametrize("split", ["text", "sentence"])
def test_reading_eval_reports_the_test_mix_per_source(tmp_path, capsys, split):
    """A56 (Opus should_fix): the pooled number is a source mix that depends on
    --split, so every run prints and records the mix and says the pooled numbers are
    not comparable across split modes."""
    corpus = _end_to_end_corpus(tmp_path)
    results, by_source = tmp_path / "r.csv", tmp_path / "s.csv"
    capsys.readouterr()
    rm.main(
        ["--examples", str(corpus), "--sizes", "0", "--no-exclude-duplicates", "--no-lexicon",
         "--split", split, "--results", str(results), "--errors", str(tmp_path / "e.csv"),
         "--by-source-results", str(by_source)]
    )
    out = capsys.readouterr().out
    assert "NOT comparable across --split" in out
    per_source = pd.read_csv(by_source)
    want = ", ".join(
        f"{row.source} {row.test_sentences}" for row in per_source.sort_values("source").itertuples()
    )
    assert f"test sentences by source ({split} split): {want}" in out
    summary = pd.read_csv(results)
    assert summary.loc[0, "test_sentences_by_source"] == want
    assert list(summary.columns)[-1] == "test_sentences_by_source"


def test_sign_eval_documents_how_to_get_the_old_exact_only_rule(capsys):
    """A56 nit: same-text exclusion is on by default, so the old rule needs its switch."""
    assert "--near-duplicate-overlap 0 --no-exclude-same-text" in " ".join(se.__doc__.split())
    with pytest.raises(SystemExit):
        se._parse_args(["--help"])
    help_text = " ".join(capsys.readouterr().out.split())
    assert "the old exact-only rule also needs --no-exclude-same-text" in help_text


def test_readme_states_the_measured_twin_inventory_not_a_guarantee():
    """README (Opus should_fix, Astra nit): v4 has twins at 0.7; the README says so."""
    text = " ".join((PROJECT_ROOT / "README.md").read_text(encoding="utf-8").split())
    assert "guaranteed to have no near-identical twin" not in text
    at_07, at_09 = EXPECTED_COUNTS["competitive_ambiguity_eval_queries_v4.csv"]
    assert f"{at_07} of v4's 20 targets" in text and f"{at_09} of them at ≥ 0.9" in text
    assert "--exclude-twins 0.7" in text

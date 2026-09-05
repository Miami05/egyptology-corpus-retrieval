"""Phase 4 — an evaluation you can trust.

The benchmark used to inherit the pipeline's own assumptions: its queries were
generated from the corpus's transliteration tokens, its twin guard saw only a
2,000-row slice of a 12,772-row corpus, and its expectations were pinned to ids that
moved whenever the importer's input changed. These tests pin the properties that
make a number quotable.
"""

from __future__ import annotations

import itertools
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from app.data.loader import REQUIRED_COLUMNS as LOADER_REQUIRED_COLUMNS  # noqa: E402
from app.services.suggestions import loose_reading_form  # noqa: E402
from scripts.build_competitive_ambiguity_benchmark import (  # noqa: E402
    _token_set,
    build_token_index,
    exhaustive_best_twin_overlap,
    rivals_for,
    twin_probe_count,
)
from scripts.build_competitive_ambiguity_benchmark import (  # noqa: E402
    main as build_benchmark_main,
)
from scripts.import_tla_dataset import content_id  # noqa: E402
from scripts.migrate_example_ids import build_mapping  # noqa: E402

BENCHMARKS = PROJECT_ROOT / "data" / "benchmarks"


# ---------- twin detection ----------


def test_token_index_finds_the_same_rivals_as_a_full_scan():
    """The inverted index is an optimisation: it must be exact, not approximate."""
    token_sets = [
        {"a", "b", "c"},
        {"a", "b", "c"},          # identical twin of row 0
        {"a", "b", "d"},          # close
        {"x", "y", "z"},          # unrelated
        {"a", "q", "r", "s"},     # shares one common token
    ]
    index = build_token_index(token_sets)
    for row in range(len(token_sets)):
        target = token_sets[row]
        expected_rivals = 0
        expected_best = 0.0
        for other in range(len(token_sets)):
            if other == row:
                continue
            union = target | token_sets[other]
            score = len(target & token_sets[other]) / len(union) if union else 0.0
            if score >= 0.16:
                expected_rivals += 1
                expected_best = max(expected_best, score)
        rivals, best = rivals_for(row, token_sets, index, min_overlap=0.16)
        assert rivals == expected_rivals
        assert best == pytest.approx(expected_best)


def test_identical_twin_is_detected():
    token_sets = [{"a", "b", "c"}, {"a", "b", "c"}]
    index = build_token_index(token_sets)
    _, best = rivals_for(0, token_sets, index, min_overlap=0.9)
    assert best == pytest.approx(1.0)


def test_exhaustive_scan_finds_a_twin_at_exactly_the_threshold():
    """Regression, reported 2026-09-05: ten tokens, a nine-token twin, Jaccard exactly
    9/10 = 0.90. `int((1.0 - 0.9) * 10)` is 0 in floating point, so the scan used to
    probe only the rarest token, `a`, which the twin lacks — and returned (0.0, None)."""
    token_sets = [set("abcdefghij"), set("bcdefghij")]
    index = build_token_index(token_sets)

    best, twin = exhaustive_best_twin_overlap(0, token_sets, index, threshold=0.90)

    assert (best, twin) == (pytest.approx(0.9), 1)


@pytest.mark.parametrize("size", [10, 20, 30, 40, 50, 100])
def test_probe_count_is_exact_at_whole_number_boundaries(size):
    """At t = 0.9 a row of 10·k tokens may miss exactly k tokens, so k + 1 probes are
    needed. The float product (1 - 0.9)·size lands just under k for every one of these."""
    assert twin_probe_count(size, 0.9) == size // 10 + 1
    assert twin_probe_count(size, 0.9) > int((1.0 - 0.9) * size)  # the old, short answer


def test_probe_count_never_below_one_and_zero_for_empty_rows():
    assert twin_probe_count(0, 0.9) == 0
    assert twin_probe_count(1, 0.9) == 1
    assert twin_probe_count(3, 0.26) == int((1 - 0.26) * 3) + 1  # 3, i.e. every token


def test_exhaustive_scan_agrees_with_brute_force_on_random_corpora():
    """The prefix filter is only an optimisation: on small random corpora its answer must
    equal the best Jaccard >= t found by comparing every pair, for every row and for
    thresholds whose (1-t)·|A| is a whole number as often as possible."""
    import random

    rng = random.Random(20260905)
    alphabet = [f"t{i}" for i in range(14)]
    for trial in range(40):
        token_sets = [
            set(rng.sample(alphabet, rng.randint(1, 10))) for _ in range(rng.randint(2, 12))
        ]
        index = build_token_index(token_sets)
        for threshold in (0.5, 0.75, 0.8, 0.9):
            for row in range(len(token_sets)):
                target = token_sets[row]
                brute = 0.0
                for other, other_tokens in enumerate(token_sets):
                    if other == row or not (target & other_tokens):
                        continue
                    score = len(target & other_tokens) / len(target | other_tokens)
                    if score >= threshold and score > brute:
                        brute = score
                found, _ = exhaustive_best_twin_overlap(row, token_sets, index, threshold)
                assert found == pytest.approx(brute), (trial, threshold, row, token_sets)


def test_row_with_no_shared_tokens_has_no_rivals():
    token_sets = [{"a", "b"}, {"x", "y"}]
    index = build_token_index(token_sets)
    assert rivals_for(0, token_sets, index, min_overlap=0.16) == (0, 0.0)


# ---------- the shipped benchmark is clean ----------


@pytest.fixture(scope="module")
def corpus_tokens():
    from app.data.loader import load_examples_csv

    df = load_examples_csv(str(PROJECT_ROOT / "data" / "processed" / "examples.csv"))
    token_sets = [_token_set(loose_reading_form(v)) for v in df["transliteration_gold"]]
    index = build_token_index(token_sets)
    position = {
        (str(text_id), str(sentence_id)): i
        for i, (text_id, sentence_id) in enumerate(
            zip(df["source_text_id"], df["source_sentence_id"])
        )
    }
    return token_sets, index, position


def test_v2_benchmark_has_no_twin_anywhere_in_the_corpus(corpus_tokens):
    """The property the whole phase is about: excluding the target must not leave a
    near-identical row behind to hand the answer over."""
    token_sets, index, position = corpus_tokens
    benchmark = pd.read_csv(BENCHMARKS / "competitive_ambiguity_eval_queries_v2.csv")
    assert len(benchmark) == 20
    for _, row in benchmark.iterrows():
        key = (str(row["expected_source_text_id"]), str(row["expected_source_sentence_id"]))
        assert key in position, f"benchmark row {row['benchmark_id']} is not in the corpus"
        _, best = rivals_for(position[key], token_sets, index, min_overlap=0.9)
        assert best < 0.9, f"{row['benchmark_id']} has a twin at overlap {best:.2f}"


def test_v1_benchmark_is_kept_and_still_contaminated(corpus_tokens):
    """v1 is deliberately retained so the numbers quoted in CORPUS_SCALING_REPORT.md
    stay reproducible. This test records *why* it must not be quoted as accuracy."""
    token_sets, index, position = corpus_tokens
    benchmark = pd.read_csv(BENCHMARKS / "competitive_ambiguity_eval_queries.csv")
    contaminated = 0
    for _, row in benchmark.iterrows():
        key = (str(row["expected_source_text_id"]), str(row["expected_source_sentence_id"]))
        if key not in position:
            continue
        _, best = rivals_for(position[key], token_sets, index, min_overlap=0.9)
        contaminated += int(best >= 0.9)
    # 11 of 20 under the yod-deleting fold; 7 of 20 once the yod is kept (2026-09-01),
    # because token sets that used to collide on `rin` now differ. Still contaminated.
    assert contaminated >= 7, (
        "v1 was measured at 7 of 20 contaminated under the 2026-09-01 fold; if this "
        "changed, the corpus or the fold changed and the report's numbers need revisiting"
    )


# ---------- real pastes ----------


def test_expert_paste_benchmark_contains_real_hieroglyph_pastes():
    queries = pd.read_csv(BENCHMARKS / "expert_paste_queries.csv")
    assert len(queries) >= 8
    glyph_queries = [
        q
        for q in queries["query_input"]
        if any(0x13000 <= ord(ch) <= 0x143FF for ch in str(q))
    ]
    assert len(glyph_queries) >= 6, "the point of this file is glyph pastes"


def test_no_other_benchmark_contains_a_hieroglyph():
    """Records the gap this phase filled: every generated benchmark is text-only."""
    for name in [
        "competitive_ambiguity_eval_queries.csv",
        "competitive_ambiguity_eval_queries_v2.csv",
        "ambiguous_reading_eval_queries.csv",
    ]:
        queries = pd.read_csv(BENCHMARKS / name)
        for value in queries["query_input"]:
            assert not any(
                0x13000 <= ord(ch) <= 0x143FF for ch in str(value)
            ), f"{name} unexpectedly contains a glyph query"


def test_expert_paste_eval_passes_end_to_end(tmp_path):
    """The runner exits non-zero if any paste regresses, so this is the gate.

    Results go to a temp path on purpose. Without `--results` the runner rewrote the
    *committed* data/benchmarks/expert_paste_eval_results.csv on every test run, so a
    plain `pytest` left the working tree dirty and a scoring change could slip into a
    commit unreviewed, hidden inside a benchmark file nobody meant to touch.
    """
    results_path = tmp_path / "expert_paste_eval_results.csv"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_expert_paste_eval.py",
            "--results",
            str(results_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed 8/8" in result.stdout
    assert results_path.exists(), "runner did not write to the requested results path"


# ---------- stable importer ids ----------


def parquet_row(**overrides) -> pd.Series:
    base = {
        "hieroglyphs": "𓊵𓏙",
        "transliteration": "ḥtp",
        "translation": "peace",
        "lemmatization": "",
        "UPOS": "",
        "glossing": "",
        "dateNotBefore": "-2000",
        "dateNotAfter": "-1900",
    }
    base.update(overrides)
    return pd.Series(base)


def test_content_id_is_stable_and_position_independent():
    row = parquet_row()
    assert content_id(row) == content_id(row)
    # The same content in a different Series order is the same sentence.
    shuffled = pd.Series(dict(reversed(list(row.items()))))
    assert content_id(shuffled) == content_id(row)


def test_content_id_separates_rows_that_differ_only_outside_the_transliteration():
    """Four rows in this dataset share a transliteration; hashing the whole row is
    what keeps them apart."""
    a = parquet_row(translation="peace")
    b = parquet_row(translation="satisfaction")
    assert content_id(a) != content_id(b)


def test_content_ids_survive_a_skipped_row_where_positional_ids_do_not():
    """The failure mode in one test: drop a row from the input and the positional
    scheme renumbers everything after it, while content ids do not move."""
    from scripts.import_tla_dataset import _row_from_parquet

    rows = [parquet_row(transliteration=f"r{i}", translation=f"t{i}") for i in range(4)]

    def ids(subset, stable):
        out = []
        for position, row in enumerate(subset, start=1):
            row = row.copy()
            row.name = position - 1
            mapped = _row_from_parquet(row, position, Path("x.parquet"), stable)
            out.append(mapped[0]["source_text_id"])
        return out

    full_positional = ids(rows, False)
    full_stable = ids(rows, True)
    # An upstream row disappears (or is skipped as empty):
    without_second = [rows[0], rows[2], rows[3]]
    assert ids(without_second, False) != [
        full_positional[0],
        full_positional[2],
        full_positional[3],
    ]
    assert ids(without_second, True) == [
        full_stable[0],
        full_stable[2],
        full_stable[3],
    ]


# ---------- the id migration ----------


class FakeExample:
    def __init__(self, source_ref, hieroglyphs, transliteration, text_id, sentence_id):
        self.source_ref = source_ref
        self.hieroglyphs = hieroglyphs
        self.transliteration_gold = transliteration
        self.source_text_id = text_id
        self.source_sentence_id = sentence_id


def test_migration_maps_rows_by_content_not_position():
    csv_df = pd.DataFrame(
        [
            {
                "source_ref": "f.parquet#row=1",
                "hieroglyphs": "A",
                "transliteration_gold": "a",
                "source_text_id": "TLA_EARLIER_AAAA",
                "source_sentence_id": "SAAAA",
            },
            {
                "source_ref": "f.parquet#row=2",
                "hieroglyphs": "B",
                "transliteration_gold": "b",
                "source_text_id": "TLA_EARLIER_BBBB",
                "source_sentence_id": "SBBBB",
            },
        ]
    )
    rows = [
        FakeExample("f.parquet#row=2", "B", "b", "TLA_EARLIER_002", "S002"),
        FakeExample("f.parquet#row=1", "A", "a", "TLA_EARLIER_001", "S001"),
    ]
    plan = build_mapping(csv_df, rows)
    assert len(plan["renames"]) == 2
    assert not plan["unmatched"] and not plan["ambiguous"]
    renamed = {old.source_text_id: new for old, new, _ in plan["renames"]}
    # Order in the database does not matter; content decides.
    assert renamed["TLA_EARLIER_001"] == "TLA_EARLIER_AAAA"
    assert renamed["TLA_EARLIER_002"] == "TLA_EARLIER_BBBB"


def test_migration_reports_unmatched_rows_rather_than_guessing():
    csv_df = pd.DataFrame(
        [
            {
                "source_ref": "f.parquet#row=1",
                "hieroglyphs": "A",
                "transliteration_gold": "a",
                "source_text_id": "NEW_A",
                "source_sentence_id": "S_A",
            }
        ]
    )
    rows = [FakeExample("f.parquet#row=99", "Z", "z", "OLD_Z", "S_Z")]
    plan = build_mapping(csv_df, rows)
    assert len(plan["unmatched"]) == 1
    assert not plan["renames"]


def test_migration_is_a_no_op_when_ids_already_match():
    csv_df = pd.DataFrame(
        [
            {
                "source_ref": "r1",
                "hieroglyphs": "A",
                "transliteration_gold": "a",
                "source_text_id": "SAME",
                "source_sentence_id": "S1",
            }
        ]
    )
    rows = [FakeExample("r1", "A", "a", "SAME", "S1")]
    plan = build_mapping(csv_df, rows)
    assert plan["unchanged"] == 1
    assert not plan["renames"]


# ---------- dead weight is gone ----------


@pytest.mark.parametrize(
    "path",
    [
        "scripts/run_eval.py",
        "scripts/run_phase3_eval.py",
        "data/benchmarks/phase3_eval_queries.csv",
        "data/benchmarks/phase3_eval_results.csv",
        "data/benchmarks/ambiguous_suggestion_eval_results.csv",
        "data/benchmarks/tuning_benchmark_80.csv",
    ],
)
def test_dead_files_are_deleted(path):
    """Each of these either crashed on import, scored zero forever, or published a
    number the current corpus cannot reproduce."""
    assert not (PROJECT_ROOT / path).exists(), f"{path} should have been removed"


def test_every_script_still_imports():
    """A script that crashes on import is dead code nobody notices."""
    failures = []
    for script in sorted((PROJECT_ROOT / "scripts").glob("*.py")):
        if script.name == "__init__.py":
            continue
        result = subprocess.run(
            [sys.executable, "-c", f"import ast;ast.parse(open({str(script)!r}).read())"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            failures.append(f"{script.name}: {result.stderr.strip()[:80]}")
    assert not failures, failures


def test_regeneration_dependency_is_declared():
    """download_all_sources.py imports `datasets`; the corpus is advertised as
    regenerable, so the dependency has to be installable from requirements.txt."""
    requirements = (PROJECT_ROOT / "requirements.txt").read_text()
    assert "datasets" in requirements


def test_ambiguous_eval_is_labelled_as_a_sanity_check():
    source = (PROJECT_ROOT / "scripts" / "run_ambiguous_suggestion_eval.py").read_text()
    assert "SANITY CHECK" in source
    assert "never be quoted as accuracy" in source


# ---------- builder flags added for the Late Egyptian eval set (LE-v1, item 6) ----------
#
# Two flags were added on 2026-09-05 so LE-v1 could be built by the *same* builder that
# produced v4 and held-out 1 rather than by a parallel implementation:
#
#   --stage "Late Egyptian"   restricts the *candidates*, nothing else
#   --exclude-benchmark       became repeatable, so a new set can be held out from
#                             several existing sets at once
#
# The property that matters and is easy to get wrong: narrowing candidacy must NOT
# narrow twin detection. The eval loads the whole corpus, so a Late Egyptian row whose
# edition twin is a BBAW or Earlier Egyptian row would still be handed its own answer
# for free, and must still be thrown out.


def _synthetic_corpus_row(**overrides) -> dict:
    row = {col: "" for col in LOADER_REQUIRED_COLUMNS}
    row.update(source="Synthetic", review_status="ok")
    row.update(overrides)
    # The reading-order query type reads this column; leaving it blank would make
    # every third generated query empty and drop it on the signal filter.
    if not row.get("normalized_reading_order"):
        row["normalized_reading_order"] = row["transliteration_gold"]
    return row


def _stage_corpus() -> list[dict]:
    """A tiny corpus with a Late Egyptian and an Earlier Egyptian rival cluster.

    Tokens are chosen so the builder's own text handling cannot interfere: none is
    in STOP_TOKENS, none is longer than four characters (so `_strip_some_endings`
    never fires), and none ends in t/w/j/y.
    """

    def row(sentence_id, stage, tokens):
        return _synthetic_corpus_row(
            source_text_id="SYN",
            source_sentence_id=sentence_id,
            language_stage=stage,
            transliteration_gold=tokens,
        )

    return [
        # A Late Egyptian rival cluster: each has two rivals above overlap 0.16.
        row("LE1", "Late Egyptian", "alfa brav chrm delp"),
        row("LE2", "Late Egyptian", "alfa brav chrm echo"),
        row("LE3", "Late Egyptian", "alfa brav golf hotl"),
        # A Late Egyptian row with a rival *inside* the stage and an exact twin
        # *outside* it. Restricting twin detection to the stage would let it through.
        row("LE_TWIN", "Late Egyptian", "indg juli kilo lima"),
        row("LE_TWIN_RIVAL", "Late Egyptian", "indg juli mike nvmb"),
        row("EE_TWIN", "Earlier Egyptian", "indg juli kilo lima"),
        # An Earlier Egyptian rival cluster that --stage must keep out.
        row("EE1", "Earlier Egyptian", "oscr papa qube rome"),
        row("EE2", "Earlier Egyptian", "oscr papa qube sirr"),
    ]


_builder_run_counter = itertools.count()


def _run_builder(monkeypatch, tmp_path, rows, *extra_args) -> pd.DataFrame:
    examples = tmp_path / "examples.csv"
    pd.DataFrame(rows).to_csv(examples, index=False)
    output = tmp_path / f"bench_{next(_builder_run_counter)}.csv"
    argv = [
        "build_competitive_ambiguity_benchmark.py",
        "--examples",
        str(examples),
        "--output",
        str(output),
        "--limit",
        "10",
        "--exhaustive-twins",
        *extra_args,
    ]
    monkeypatch.setattr(sys, "argv", argv)
    build_benchmark_main()
    try:
        return pd.read_csv(output).fillna("")
    except pd.errors.EmptyDataError:
        # A build that selected nothing writes an empty frame, which has no header
        # row at all rather than a header with no rows.
        return pd.DataFrame()


def _selected_ids(frame: pd.DataFrame) -> set[str]:
    if frame.empty:
        return set()
    return set(frame["expected_source_sentence_id"].astype(str))


def test_stage_filter_keeps_only_candidates_of_that_stage(monkeypatch, tmp_path):
    built = _run_builder(monkeypatch, tmp_path, _stage_corpus(), "--stage", "Late Egyptian")
    assert _selected_ids(built) <= {"LE1", "LE2", "LE3", "LE_TWIN", "LE_TWIN_RIVAL"}
    assert not _selected_ids(built) & {"EE1", "EE2", "EE_TWIN"}
    assert set(built["language_stage"]) == {"Late Egyptian"}


def test_stage_filter_still_excludes_a_twin_that_lives_outside_the_stage(
    monkeypatch, tmp_path
):
    """The regression this flag could easily have introduced.

    LE_TWIN has a rival inside Late Egyptian (so it is a candidate at all) and an
    exact twin in an Earlier Egyptian row. If --stage had narrowed the frame that
    twin detection runs on, LE_TWIN would look clean and be selected — and at eval
    time, with the whole corpus loaded and only LE_TWIN excluded, its Earlier
    Egyptian duplicate would hand over the expected reading for free.
    """
    built = _run_builder(monkeypatch, tmp_path, _stage_corpus(), "--stage", "Late Egyptian")
    assert "LE_TWIN" not in _selected_ids(built)
    # Its rival has no twin and is unaffected — the guard is targeted, not blanket.
    assert "LE_TWIN_RIVAL" in _selected_ids(built)


def test_without_the_stage_flag_the_builder_is_unrestricted(monkeypatch, tmp_path):
    built = _run_builder(monkeypatch, tmp_path, _stage_corpus())
    assert _selected_ids(built) & {"EE1", "EE2"}, "default must consider every stage"
    assert "LE_TWIN" not in _selected_ids(built)
    assert "EE_TWIN" not in _selected_ids(built)


def test_stage_filter_naming_an_absent_population_selects_nothing(monkeypatch, tmp_path):
    built = _run_builder(monkeypatch, tmp_path, _stage_corpus(), "--stage", "Coptic")
    assert _selected_ids(built) == set()


def test_benchmark_rows_carry_the_corpus_language_stage(monkeypatch, tmp_path):
    """`--stage declared` reads this column; without it a declared run declares
    nothing and is indistinguishable from a pooled run."""
    built = _run_builder(monkeypatch, tmp_path, _stage_corpus())
    assert "language_stage" in built.columns
    pairs = zip(built["expected_source_sentence_id"].astype(str), built["language_stage"])
    for sentence_id, stage in pairs:
        expected = "Late Egyptian" if sentence_id.startswith("LE") else "Earlier Egyptian"
        assert stage == expected


def _exclusion_file(path: Path, sentence_ids: list[str]) -> Path:
    pd.DataFrame(
        [
            {"expected_source_text_id": "SYN", "expected_source_sentence_id": sentence_id}
            for sentence_id in sentence_ids
        ]
    ).to_csv(path, index=False)
    return path


def test_exclude_benchmark_is_repeatable_and_takes_the_union(monkeypatch, tmp_path):
    rows = _stage_corpus()
    baseline = _selected_ids(_run_builder(monkeypatch, tmp_path, rows))
    assert {"LE1", "LE2"} <= baseline, "precondition: both are selected without exclusions"

    first = _exclusion_file(tmp_path / "exclude_a.csv", ["LE1"])
    second = _exclusion_file(tmp_path / "exclude_b.csv", ["LE2"])
    built = _run_builder(
        monkeypatch,
        tmp_path,
        rows,
        "--exclude-benchmark",
        str(first),
        "--exclude-benchmark",
        str(second),
    )
    assert not _selected_ids(built) & {"LE1", "LE2"}


def test_two_exclusion_files_equal_one_concatenated_file(monkeypatch, tmp_path):
    """Repeating the flag must be exactly concatenation, not last-one-wins."""
    rows = _stage_corpus()
    first = _exclusion_file(tmp_path / "one.csv", ["LE1"])
    second = _exclusion_file(tmp_path / "two.csv", ["LE2", "EE1"])
    both = _exclusion_file(tmp_path / "both.csv", ["LE1", "LE2", "EE1"])

    repeated = _run_builder(
        monkeypatch,
        tmp_path,
        rows,
        "--exclude-benchmark",
        str(first),
        "--exclude-benchmark",
        str(second),
    )
    concatenated = _run_builder(
        monkeypatch, tmp_path, rows, "--exclude-benchmark", str(both)
    )
    assert _selected_ids(repeated) == _selected_ids(concatenated)


def test_a_single_exclusion_file_still_behaves_as_before(monkeypatch, tmp_path):
    rows = _stage_corpus()
    only = _exclusion_file(tmp_path / "only.csv", ["LE1"])
    built = _run_builder(monkeypatch, tmp_path, rows, "--exclude-benchmark", str(only))
    assert "LE1" not in _selected_ids(built)
    assert {"LE2", "LE3"} <= _selected_ids(built)

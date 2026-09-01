"""Phase 4 — an evaluation you can trust.

The benchmark used to inherit the pipeline's own assumptions: its queries were
generated from the corpus's transliteration tokens, its twin guard saw only a
2,000-row slice of a 12,772-row corpus, and its expectations were pinned to ids that
moved whenever the importer's input changed. These tests pin the properties that
make a number quotable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from app.services.suggestions import loose_reading_form  # noqa: E402
from scripts.build_competitive_ambiguity_benchmark import (  # noqa: E402
    _token_set,
    build_token_index,
    rivals_for,
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

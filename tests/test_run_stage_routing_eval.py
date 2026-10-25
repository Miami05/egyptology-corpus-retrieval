"""scripts/run_stage_routing_eval.py, rule A2.3 of the 2026-10-25 pre-registration.

Synthetic input only: no test reads data/processed/examples.csv, and the script is
never run on the corpus here (that is step 9 of the re-measure, on a pinned commit).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import REQUIRED_COLUMNS, load_examples_csv  # noqa: E402
from scripts import run_stage_routing_eval as routing  # noqa: E402

E, L, D = routing.EARLIER, routing.LATE, routing.DEMOTIC
GLYPHS = [chr(0x13000 + i) for i in range(60)]


def _row(source, text_id, sentence_id, stage, glyphs, translit):
    row = {column: "" for column in REQUIRED_COLUMNS}
    row.update(
        source=source,
        source_text_id=text_id,
        source_sentence_id=sentence_id,
        language_stage=stage,
        hieroglyphs=glyphs,
        transliteration_gold=translit,
    )
    return row


def _corpus(tmp_path) -> Path:
    """Earlier (TLA) and Late (Ramses, TLA) rows with signs, a Demotic text-only row,
    an unlabelled BBAW row, a sign-string duplicate and a labelled row from a source
    A2.3 does not admit."""
    rows = []
    for i in range(6):
        g = GLYPHS[2 * i : 2 * i + 2]
        rows.append(_row("TLA", f"TLA_EARLIER_T{i}", "1", E, " ".join(g), f"e{i}a e{i}b"))
        rows.append(_row("TLA", f"TLA_EARLIER_T{i}", "2", E, g[0], f"e{i}a"))
    for i in range(6):
        g = GLYPHS[20 + 2 * i : 22 + 2 * i]
        source = "Ramses" if i % 2 else "TLA"
        rows.append(_row(source, f"L{i}", "1", L, " ".join(g), f"l{i}a l{i}b"))
    rows.append(_row("TLA", "TLA_DEMOTIC_X", "1", D, "", "dm"))
    rows.append(_row("BBAW", "B1", "1", "Unspecified (BBAW)", GLYPHS[0], "e0a"))
    rows.append(_row("TLA", "TLA_EARLIER_DUP", "1", E, f"{GLYPHS[0]} {GLYPHS[1]}", "e0a e0b"))
    rows.append(_row("AES", "A1", "1", E, GLYPHS[50], "x"))
    path = tmp_path / "examples.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_eligible_rows_follow_a2_3(tmp_path):
    df = load_examples_csv(str(_corpus(tmp_path)))
    eligible = routing.eligible_rows(df)
    assert set(eligible["source"]) == {"TLA", "Ramses"}  # AES and BBAW are out
    assert not eligible["hieroglyphs_norm"].duplicated().any()
    # The duplicate sign string keeps the first row in (source, text, sentence) order.
    first = eligible[eligible["hieroglyphs_norm"] == df.loc[0, "hieroglyphs_norm"]]
    assert first["source_text_id"].tolist() == ["TLA_EARLIER_DUP"]
    keys = eligible[routing.SORT_KEYS].astype(str).values.tolist()
    assert keys == sorted(keys)


def test_draw_sample_is_earlier_then_late_from_one_generator(tmp_path):
    df = load_examples_csv(str(_corpus(tmp_path)))
    eligible = routing.eligible_rows(df)
    sample = routing.draw_sample(eligible, 20261025, 3)
    rng = np.random.default_rng(20261025)
    earlier = eligible[eligible["true_stage"] == E]
    late = eligible[eligible["true_stage"] == L]
    expected = list(earlier.index[rng.choice(len(earlier), 3, replace=False)])
    expected += list(late.index[rng.choice(len(late), 3, replace=False)])
    assert list(sample.index) == expected
    with pytest.raises(ValueError, match="fewer than --per-stage"):
        routing.draw_sample(eligible, 1, 100)


def test_held_out_pool_drops_twins_and_whole_texts(tmp_path):
    df = load_examples_csv(str(_corpus(tmp_path)))
    sample = df.loc[[0]].assign(true_stage=E)  # TLA_EARLIER_T0 sentence 1
    pool = routing.held_out_pool(df, sample)
    assert "TLA_EARLIER_T0" not in set(pool["source_text_id"])  # sentence 2 too
    assert "TLA_EARLIER_DUP" not in set(pool["source_text_id"])  # same sign string
    assert len(pool) == len(df) - 3


@pytest.mark.parametrize(
    "coverage, scores, expected",
    [
        ({}, {}, None),
        ({E: 0}, {E: -1.0}, None),
        ({E: 2}, {E: -9.0}, E),
        ({E: 2, L: 1}, {E: -9.0, L: -1.0}, E),  # coverage first, no margin
        ({E: 2, L: 2}, {E: -1.0, L: -2.0}, E),
        ({E: 2, L: 2}, {E: -1.0, L: -1.0}, None),  # equality abstains
        ({E: 2, L: 2}, {E: -1.0, L: -1.0 - 1e-10}, None),  # within the margin
    ],
)
def test_reference_decision_is_rule_a2_4(coverage, scores, expected):
    assert routing.reference_decision(coverage, scores) == expected


def _results(pairs):
    return pd.DataFrame(
        [
            {"true_stage": t, "chosen_stage": c, "matches_reference": True,
             "aligned_tokens": 2, "chosen_model_right": 1, "true_model_right": 2}
            for t, c in pairs
        ]
    )


def test_any_demotic_routing_fails_the_pass_rule():
    report, passed = routing.summarize(_results([(E, E), (L, "None"), (L, L)]))
    assert passed and "abstentions (None): 1/3" in report
    report, passed = routing.summarize(_results([(E, E), (L, D)]))
    assert not passed
    assert "Late Egyptian -> Demotic: 1/1" in report and "FAIL" in report


def test_end_to_end_on_synthetic_input(tmp_path, capsys):
    results = tmp_path / "out" / "routing.csv"
    code = routing.main([
        "--examples", str(_corpus(tmp_path)), "--seed", "7", "--per-stage", "2",
        "--results", str(results), "--lexicon", str(tmp_path / "no-lexicon.csv"),
    ])
    out = capsys.readouterr().out
    assert code in (0, 1)
    assert "pass rule (A2.3" in out
    assert "each stage's own eligible pool" in out
    written = pd.read_csv(results)
    assert len(written) == 4
    assert sorted(written["true_stage"]) == [E, E, L, L]
    assert {"coverage_Demotic", "score_Earlier Egyptian", "reference_stage"} <= set(written.columns)
    # Demotic has no aligned rows of its own here, so the guard keeps it from winning.
    assert D not in set(written["chosen_stage"])
    assert code == 0


def test_too_few_eligible_rows_stops(tmp_path, capsys):
    code = routing.main([
        "--examples", str(_corpus(tmp_path)), "--per-stage", "50",
        "--results", str(tmp_path / "r.csv"), "--lexicon", str(tmp_path / "none.csv"),
    ])
    assert code == 2
    assert "STOP" in capsys.readouterr().out

"""scripts/check_standrews_urkiv_gate.py finds the private rows it is meant to gate.

Pre-registration 2026-10-25, A5 change 1: the script used the script-relative
`data/private`, which is empty in a worktree, and so ran the "St Andrews" gate with no
St Andrews rows. It now takes `--private-dir` (default `PRIVATE_DATA_DIR`, else the old
path), prints what it loaded, and refuses to run on zero private rows. No test here
reads real private data or the public corpus.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import REQUIRED_COLUMNS  # noqa: E402
from scripts import check_standrews_urkiv_gate as gate  # noqa: E402


def _write_private(directory: Path, rows: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({column: [""] * rows for column in REQUIRED_COLUMNS})
    frame["source"] = "StAndrews"
    frame["source_text_id"] = "synthetic"
    frame["source_sentence_id"] = [str(i) for i in range(rows)]
    frame["hieroglyphs"] = "𓀀"
    frame["transliteration_gold"] = "ꞽ"
    frame.to_csv(directory / "standrews.csv", index=False)


def _public_stub(monkeypatch) -> None:
    public = pd.DataFrame({column: ["x"] for column in REQUIRED_COLUMNS})
    monkeypatch.setattr(gate, "load_examples_csv", lambda path: public)


def test_private_dir_defaults_to_the_app_environment_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("PRIVATE_DATA_DIR", str(tmp_path))
    assert gate.parse_args([]).private_dir == str(tmp_path)
    monkeypatch.delenv("PRIVATE_DATA_DIR")
    assert gate.parse_args([]).private_dir == str(gate.PRIVATE_DIR)
    assert gate.parse_args(["--private-dir", "/elsewhere"]).private_dir == "/elsewhere"


def test_load_corpus_reads_the_given_directory_and_counts_its_rows(monkeypatch, tmp_path):
    _public_stub(monkeypatch)
    _write_private(tmp_path / "priv", 3)
    df, private_rows = gate.load_corpus(tmp_path / "priv")
    assert private_rows == 3
    assert len(df) == 4


def test_no_private_rows_is_not_run_and_exits_non_zero(monkeypatch, tmp_path, capsys):
    """An empty directory must stop before any evaluation, never report a gate."""
    _public_stub(monkeypatch)

    def boom(*_args, **_kwargs):
        raise AssertionError("evaluation must not start without private rows")

    monkeypatch.setattr(gate, "load_lexicon", boom)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert gate.main(["--private-dir", str(empty)]) == 1
    out = capsys.readouterr().out
    assert f"private dir {empty.resolve()}: 0 private rows" in out
    assert "NOT RUN" in out


# --- final eval 2026-10-25: the gate is one pinned row, and its exit code is the verdict ---
# --- A7, 2026-10-26: the pinned row's RANK is reported, not gated. No St Andrews row
#     has a `hieroglyphs` value, and `retrieve_top_k` drops rows with no shared sign
#     evidence, so "rank 1 among St Andrews rows" was unreachable by construction. ---

def _urk_private(directory: Path, *, with_target: bool = True) -> None:
    """Two sentences of Urk. IV 1 under the text marker: a different line, and (unless
    `with_target` is False) the pinned row for Camilla's line. Synthetic readings."""
    directory.mkdir(parents=True, exist_ok=True)
    rows = [("S_urkIV-001_urkIV-001Tr_0039", "line 39", "xyz")]
    if with_target:
        rows.append((gate.GATE_SENTENCE_ID, "line 2", gate.GATE_READING))
    frame = pd.DataFrame({column: [""] * len(rows) for column in REQUIRED_COLUMNS})
    frame["source"] = "StAndrews"
    frame["source_text_id"] = "synthetic"
    frame["source_sentence_id"] = [sid for sid, _, _ in rows]
    frame["source_ref"] = [f"urkIV-001 (urkIV-001Tr) {ref}" for _, ref, _ in rows]
    frame["transliteration_gold"] = [reading for _, _, reading in rows]
    frame["hieroglyphs"] = "𓀀"
    frame.to_csv(directory / "standrews.csv", index=False)


def _run_gate(monkeypatch, tmp_path, *, pastes_pass: bool, target_first: bool,
              with_target: bool = True, target_in_pool: bool = True) -> int:
    """`main()` with every heavy step stubbed: the pool is the private rows in a fixed
    order, and every paste check passes or fails as asked.

    `target_in_pool=False` is the real shape of the run: the pinned row is in the corpus
    but never reaches the retrieval pool.
    """
    from types import SimpleNamespace

    _public_stub(monkeypatch)
    private = tmp_path / "priv"
    _urk_private(private, with_target=with_target)
    monkeypatch.setattr(gate, "load_lexicon", lambda *a, **k: None)
    monkeypatch.setattr(
        gate, "build_stage_resources",
        lambda *a, **k: SimpleNamespace(frame=None, index=None, segmenter=None,
                                        reading_model=None),
    )
    monkeypatch.setattr(gate, "resolve_stage", lambda mode, row, get: (None, False, {}))
    monkeypatch.setattr(
        gate, "evaluate_row",
        lambda row, *a, **k: {"benchmark_id": row["benchmark_id"], "passed": pastes_pass,
                              "actual_reading": "", "expected_reading": ""},
    )
    monkeypatch.setattr(gate, "contains_hieroglyphs", lambda query: False)
    monkeypatch.setattr(gate, "suggest_top_readings", lambda *a, **k: [])

    def pool(*_args, **_kwargs):
        frame = gate.load_private_examples(private)
        if not target_in_pool:
            frame = frame.loc[~gate.is_gate_row(frame)]
        return frame.iloc[::-1] if target_first else frame

    monkeypatch.setattr(gate, "retrieve_top_k", pool)
    return gate.main(["--private-dir", str(private)])


def test_gate_passes_on_all_pastes_with_the_pinned_row_present(monkeypatch, tmp_path, capsys):
    assert _run_gate(monkeypatch, tmp_path, pastes_pass=True, target_first=True) == 0
    out = capsys.readouterr().out
    assert "rank among St Andrews rows only: 1" in out
    assert "rank among St Andrews rows: 1 (reported, not gated" in out
    assert "GATE: PASS" in out


def test_failed_paste_checks_exit_non_zero(monkeypatch, tmp_path, capsys):
    assert _run_gate(monkeypatch, tmp_path, pastes_pass=False, target_first=True) == 1
    assert "GATE: FAIL (paste checks 0/" in capsys.readouterr().out


def test_the_rank_is_reported_and_does_not_gate(monkeypatch, tmp_path, capsys):
    """A7: line 39 of Urk. IV 1 ahead of Camilla's line puts the pinned row at rank 2.
    That is printed and does not fail the gate (it used to)."""
    assert _run_gate(monkeypatch, tmp_path, pastes_pass=True, target_first=False) == 0
    out = capsys.readouterr().out
    assert "rank among St Andrews rows: 2 (reported, not gated" in out
    assert "GATE: PASS" in out
    assert "not 1" not in out


def test_a_pinned_row_that_never_reaches_the_pool_is_reported_not_gated(
    monkeypatch, tmp_path, capsys
):
    """The real shape of the run: the row is in the corpus, never in the pool."""
    assert _run_gate(
        monkeypatch, tmp_path, pastes_pass=True, target_first=True, target_in_pool=False
    ) == 0
    out = capsys.readouterr().out
    assert "rank among St Andrews rows: not retrieved (reported, not gated" in out
    assert "GATE: PASS" in out


def test_gate_verdict_judges_only_the_paste_checks():
    assert gate.gate_verdict(8, 8) == []
    assert gate.gate_verdict(7, 8) == ["paste checks 7/8"]
    assert gate.gate_verdict(0, 0) == ["paste checks 0/0"]


def test_missing_pinned_row_fails_before_evaluation(monkeypatch, tmp_path, capsys):
    """Presence of the pinned row is still gated, even though its rank is not."""
    assert _run_gate(
        monkeypatch, tmp_path, pastes_pass=True, target_first=True, with_target=False
    ) == 1
    assert "GATE: FAIL (0 rows with source_sentence_id" in capsys.readouterr().out


def test_a_changed_pinned_reading_still_fails(monkeypatch, tmp_path):
    """A re-import that renumbers the sentences must fail loudly, not be reported."""
    import pandas as pd

    frame = pd.DataFrame({column: [""] for column in REQUIRED_COLUMNS})
    frame["source"] = "StAndrews"
    frame["source_sentence_id"] = gate.GATE_SENTENCE_ID
    frame["transliteration_gold"] = "a different line"
    assert gate.check_gate_row(frame) == (
        f"{gate.GATE_SENTENCE_ID} no longer carries the expected reading"
    )

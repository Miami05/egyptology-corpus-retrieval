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

"""Unit tests for the §4d declaration file.

Synthetic fixtures only: invented line ids, a fake commit and a fake corpus sha.
Nothing here reads KRI material, the custody directory or the real corpus.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import kri_declaration as decl
from scripts.kri_declaration import (
    CONFIRMATION,
    DECLARATION_COLUMNS,
    EXPLORATORY,
    FREEZE_DATE,
    POWER_FLOOR,
    Declaration,
    DeclarationError,
    DeclaredRun,
    read_declaration,
    validate,
    validate_run,
    write_declaration,
)

COMMIT = "a" * 40
CORPUS = "b" * 64
A1 = "\U00013000"


def run(**changes) -> DeclaredRun:
    base = dict(
        declaration_id="KRI_01_G",
        line_id="KRI_01",
        input_modality="glyphs",
        endpoint="G",
        stage="auto",
        cohort=EXPLORATORY,
        material_received="2026-10-26",
        declared_on="2026-10-26",
        commit=COMMIT,
        corpus_sha256=CORPUS,
        notes="",
    )
    base.update(changes)
    return DeclaredRun(**base)


def retrieval(**changes) -> DeclaredRun:
    base = {"declaration_id": "KRI_01_R", "input_modality": "transliteration", "endpoint": "R"}
    base.update(changes)
    return run(**base)


# --------------------------------------------------------------------- the pairings


def test_the_two_pairings_validate():
    assert validate_run(run()) == []
    assert validate_run(retrieval()) == []


def test_a_crossed_pairing_is_refused():
    """§4d pairs glyph input with the reading endpoint and text input with retrieval."""
    problems = validate_run(run(endpoint="R"))
    assert any("§4d pairs glyphs input with endpoint G" in problem for problem in problems)


def test_one_line_may_be_declared_for_both_endpoints():
    """§4d: "A line with both kinds of input gets two declared runs"."""
    assert validate(Declaration(runs=[run(), retrieval()])) == []


def test_the_same_line_twice_on_one_endpoint_is_refused():
    problems = validate(Declaration(runs=[run(), run(declaration_id="KRI_01_G_again")]))
    assert any("declared twice for endpoint G" in problem for problem in problems)


def test_a_duplicate_declaration_id_is_refused():
    problems = validate(Declaration(runs=[run(), run(line_id="KRI_02")]))
    assert any("duplicate declaration_id" in problem for problem in problems)


# --------------------------------------------------------------------- the pins


def test_the_stage_must_be_auto():
    assert any("stage must be 'auto'" in p for p in validate_run(run(stage="declared")))


def test_two_commits_in_one_declaration_are_refused():
    """§4e: one evaluation on a pinned commit and a pinned corpus sha."""
    problems = validate(Declaration(runs=[run(), retrieval(commit="c" * 40)]))
    assert any("different commits" in problem for problem in problems)


def test_two_corpus_shas_in_one_declaration_are_refused():
    problems = validate(Declaration(runs=[run(), retrieval(corpus_sha256="c" * 64)]))
    assert any("different corpus sha256s" in problem for problem in problems)


def test_a_short_commit_or_a_non_sha_corpus_is_refused():
    assert any("40-character sha" in p for p in validate_run(run(commit="abc123")))
    assert any("is not a sha256" in p for p in validate_run(run(corpus_sha256="abc")))


# --------------------------------------------------------------------- eligibility


def test_endpoint_g_on_pre_freeze_material_cannot_be_a_confirmation():
    """The freeze record: these PDFs are exploratory for G, whatever a row claims."""
    problems = validate_run(run(cohort=CONFIRMATION, material_received=FREEZE_DATE))
    assert any("not eligible for a confirmation" in problem for problem in problems)
    assert any(FREEZE_DATE in problem for problem in problems)


def test_endpoint_g_on_later_material_may_be_a_confirmation():
    assert validate_run(run(cohort=CONFIRMATION, material_received="2026-11-02")) == []
    assert run(cohort=CONFIRMATION, material_received="2026-11-02").eligible_for_confirmation


def test_endpoint_r_is_unaffected_by_the_b_freq_freeze():
    """§4e: "endpoint R is unaffected" — R's baseline is protocol (B), not B-freq."""
    assert validate_run(retrieval(cohort=CONFIRMATION, material_received=FREEZE_DATE)) == []
    assert retrieval(cohort=CONFIRMATION, material_received=FREEZE_DATE).eligible_for_confirmation


def test_an_exploratory_g_row_is_never_eligible_however_late_the_material():
    assert not run(cohort=EXPLORATORY, material_received="2026-12-01").eligible_for_confirmation


# --------------------------------------------------------------------- no text


def test_a_note_or_line_id_carrying_egyptian_is_refused():
    assert any("never the line itself" in p for p in validate_run(run(notes="ꞽri̯.n=f")))
    assert any("never the line itself" in p for p in validate_run(run(line_id=f"KRI {A1}")))


# --------------------------------------------------------------------- counts


def test_the_counts_and_the_power_floor_are_per_endpoint():
    runs = [run(declaration_id=f"G{i}", line_id=f"L{i}") for i in range(POWER_FLOOR + 1)]
    runs += [retrieval(declaration_id=f"R{i}", line_id=f"L{i}") for i in range(3)]
    declaration = Declaration(runs=runs)
    assert declaration.counts() == {"G": POWER_FLOOR + 1, "R": 3}
    assert declaration.underpowered() == {"G": False, "R": True}


def test_an_empty_declaration_is_invalid():
    assert validate(Declaration()) == ["the declaration is empty: there is nothing declared to run"]


# --------------------------------------------------------------------- file i/o


def test_a_round_trip_preserves_every_field(tmp_path):
    path = tmp_path / "declaration.csv"
    declaration = Declaration(runs=[run(), retrieval()])
    write_declaration(declaration, path)
    assert read_declaration(path).runs == declaration.runs


def test_a_foreign_header_is_refused(tmp_path):
    path = tmp_path / "declaration.csv"
    path.write_text("line_id,endpoint\nKRI_01,G\n", encoding="utf-8")
    with pytest.raises(DeclarationError):
        read_declaration(path)


def test_the_file_is_written_deterministically(tmp_path):
    declaration = Declaration(runs=[run()])
    first = write_declaration(declaration, tmp_path / "a.csv")
    second = write_declaration(declaration, tmp_path / "b.csv")
    assert first == second


# --------------------------------------------------------------------- CLI


def test_the_template_is_empty_and_has_only_headers(tmp_path):
    path = tmp_path / "declaration.csv"
    assert decl.main(["template", "--output", str(path)]) == 0
    assert path.read_text(encoding="utf-8") == ",".join(DECLARATION_COLUMNS) + "\n"
    assert list(csv.DictReader(path.open(encoding="utf-8"))) == []


def test_the_template_does_not_overwrite_without_force(tmp_path):
    path = tmp_path / "declaration.csv"
    decl.main(["template", "--output", str(path)])
    path.write_text("do not lose me\n", encoding="utf-8")
    assert decl.main(["template", "--output", str(path)]) == 2
    assert path.read_text(encoding="utf-8") == "do not lose me\n"
    assert decl.main(["template", "--output", str(path), "--force"]) == 0


def test_validate_prints_the_sha256_and_the_power_note(tmp_path, capsys):
    path = tmp_path / "declaration.csv"
    write_declaration(Declaration(runs=[run(), retrieval()]), path)
    assert decl.main(["validate", "--declaration", str(path)]) == 0
    out = capsys.readouterr().out
    assert "declaration sha256" in out
    assert "uninformative" in out  # 1 line per endpoint is far below the floor
    assert "exploratory" in out


def test_validate_fails_on_a_crossed_pairing(tmp_path, capsys):
    path = tmp_path / "declaration.csv"
    write_declaration(Declaration(runs=[run(endpoint="R")]), path)
    assert decl.main(["validate", "--declaration", str(path)]) == 1

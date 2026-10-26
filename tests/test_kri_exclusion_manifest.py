"""Unit tests for the (B) exclusion manifest (plan 2026-10-26 §4d, §4e).

Synthetic fixtures only. The "KRI lines" here are invented ASCII transliterations;
nothing in this file reads KRI material, the custody directory or the real corpus.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import kri_exclusion_manifest as manifest_mod
from scripts.kri_exclusion_manifest import (
    MANIFEST_COLUMNS,
    PENDING_HASH,
    Manifest,
    ManifestEntry,
    ManifestError,
    content_hash,
    read_manifest,
    validate,
    validate_entry,
    write_manifest,
)

A1 = "\U00013000"


def entry(**changes) -> ManifestEntry:
    base = dict(
        entry_id="EX001",
        added="2026-10-26",
        scope="passage",
        reference="KRI II 569 (lines 3-16), Karnak Great Hypostyle Hall",
        hash_basis="pending",
        sha256=PENDING_HASH,
        source="KRI PDFs received 2026-10-26",
        note="exploratory self-test 2026-10-26",
    )
    base.update(changes)
    return ManifestEntry(**base)


# --------------------------------------------------------------------------- hashing


def test_the_hash_is_of_a_canonical_form_so_two_editions_of_one_line_agree():
    """Spacing and editorial apparatus must not turn one passage into two exclusions."""
    left = content_hash("ꞽri̯.n=f m mn.w=f", basis="canonical_transliteration")
    right = content_hash("ꞽri̯.n=f  m  [mn].w=f", basis="canonical_transliteration")
    assert left == right


def test_two_different_readings_get_different_hashes():
    assert content_hash("ꜣḫ.t", basis="canonical_transliteration") != content_hash(
        "ꜥḫ.t", basis="canonical_transliteration"
    )


def test_the_basis_is_part_of_the_hash():
    """The same canonical string under two bases is two different fingerprints."""
    text = "ꞽri̯"
    glyphs = A1
    assert content_hash(text, basis="canonical_transliteration") != content_hash(
        glyphs, basis="canonical_glyphs"
    )


def test_a_pending_basis_cannot_hash_anything():
    with pytest.raises(ManifestError):
        content_hash("ꞽri̯", basis="pending")


def test_text_with_no_canonical_form_is_refused_rather_than_hashed_as_empty():
    with pytest.raises(ManifestError):
        content_hash("[...]", basis="canonical_transliteration")


# --------------------------------------------------------------------------- validation


def test_a_well_formed_pending_entry_validates():
    assert validate_entry(entry()) == []


def test_strict_mode_refuses_a_pending_hash():
    problems = validate_entry(entry(), strict=True)
    assert any(PENDING_HASH in problem for problem in problems)


def test_a_reference_carrying_hieroglyphs_is_refused():
    problems = validate_entry(entry(reference=f"KRI II 569 {A1}"))
    assert any("never text" in problem for problem in problems)


def test_a_note_carrying_a_transliteration_is_refused():
    """This is the leak the manifest exists to prevent: text in a 'helpful' field."""
    problems = validate_entry(entry(note="the line reads ꞽri̯.n=f"))
    assert any("never text" in problem for problem in problems)


def test_a_hash_that_is_not_a_sha256_is_refused():
    problems = validate_entry(entry(hash_basis="canonical_transliteration", sha256="deadbeef"))
    assert any("64 lower-case hex" in problem for problem in problems)


def test_a_real_hash_with_a_pending_basis_is_refused():
    digest = content_hash("ꞽri̯.n=f", basis="canonical_transliteration")
    problems = validate_entry(entry(hash_basis="pending", sha256=digest))
    assert any("name the basis used" in problem for problem in problems)


def test_an_empty_reference_is_refused():
    assert any("excludes nothing" in p for p in validate_entry(entry(reference="  ")))


def test_a_bad_scope_and_a_bad_date_are_both_reported():
    problems = validate_entry(entry(scope="chapter", added="26/10/2026"))
    assert len(problems) == 2


def test_duplicate_entry_ids_are_reported():
    problems = validate(Manifest(entries=[entry(), entry()]))
    assert any("duplicate entry_id" in problem for problem in problems)


# --------------------------------------------------------------------------- lookup


def test_an_excluded_line_is_found_by_its_text_without_the_manifest_holding_it():
    line = "ꞽri̯.n=f m mn.w=f"
    digest = content_hash(line, basis="canonical_transliteration")
    book = Manifest(entries=[entry(hash_basis="canonical_transliteration", sha256=digest)])
    assert [hit.entry_id for hit in book.excludes_text(line)] == ["EX001"]
    assert [hit.entry_id for hit in book.excludes_text("ky ḏd")] == []
    # And the text itself appears nowhere in the file it would be written to.
    assert all(line not in value for value in book.entries[0].as_row().values())


def test_a_pending_entry_never_matches_a_line():
    book = Manifest(entries=[entry()])
    assert book.excludes_text("ꞽri̯.n=f") == []
    assert book.hashes == set()


# --------------------------------------------------------------------------- file i/o


def test_a_round_trip_through_the_file_preserves_every_entry(tmp_path):
    path = tmp_path / "exclusion-manifest.csv"
    book = Manifest(entries=[entry(), entry(entry_id="EX002", scope="line")])
    write_manifest(book, path)
    assert read_manifest(path).entries == book.entries


def test_the_file_is_written_deterministically(tmp_path):
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    book = Manifest(entries=[entry()])
    assert write_manifest(book, first) == write_manifest(book, second)
    assert first.read_bytes() == second.read_bytes()
    assert b"\r\n" not in first.read_bytes()


def test_a_foreign_header_is_refused(tmp_path):
    path = tmp_path / "wrong.csv"
    path.write_text("reference,sha256\nKRI II 569,deadbeef\n", encoding="utf-8")
    with pytest.raises(ManifestError):
        read_manifest(path)


def test_next_entry_id_continues_the_sequence():
    assert Manifest().next_entry_id() == "EX001"
    assert Manifest(entries=[entry(entry_id="EX007")]).next_entry_id() == "EX008"


# --------------------------------------------------------------------------- CLI


def test_init_writes_headers_only(tmp_path):
    path = tmp_path / "m.csv"
    assert manifest_mod.main(["init", "--manifest", str(path)]) == 0
    assert path.read_text(encoding="utf-8") == ",".join(MANIFEST_COLUMNS) + "\n"


def test_add_pending_records_the_reference_and_no_text(tmp_path):
    path = tmp_path / "m.csv"
    manifest_mod.main(["init", "--manifest", str(path)])
    code = manifest_mod.main(
        [
            "add",
            "--manifest", str(path),
            "--scope", "passage",
            "--reference", "KRI II 569 (lines 3-16), Karnak Great Hypostyle Hall",
            "--note", "exploratory self-test 2026-10-26",
            "--added", "2026-10-26",
            "--pending",
        ]
    )
    assert code == 0
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["sha256"] == PENDING_HASH
    assert rows[0]["hash_basis"] == "pending"
    assert rows[0]["entry_id"] == "EX001"


def test_add_hashes_a_text_file_without_copying_its_text(tmp_path):
    """The private file is read here and hashed here; the manifest gets the digest."""
    path = tmp_path / "m.csv"
    secret = tmp_path / "line.txt"
    secret.write_text("ꞽri̯.n=f m mn.w=f", encoding="utf-8")
    manifest_mod.main(["init", "--manifest", str(path)])
    manifest_mod.main(
        [
            "add", "--manifest", str(path), "--scope", "line",
            "--reference", "KRI II 569, line 3", "--added", "2026-10-26",
            "--text-file", str(secret), "--hash-basis", "canonical_transliteration",
        ]
    )
    written = path.read_text(encoding="utf-8")
    assert "ꞽri̯" not in written and "iri" not in written
    assert content_hash(secret.read_text(encoding="utf-8"), basis="canonical_transliteration") in written


def test_add_refuses_an_entry_whose_reference_carries_text(tmp_path):
    path = tmp_path / "m.csv"
    manifest_mod.main(["init", "--manifest", str(path)])
    code = manifest_mod.main(
        ["add", "--manifest", str(path), "--scope", "line", "--reference", f"KRI {A1}", "--pending"]
    )
    assert code == 1
    assert list(csv.DictReader(path.open(encoding="utf-8"))) == []


def test_validate_passes_a_pending_manifest_and_fails_it_under_strict(tmp_path, capsys):
    path = tmp_path / "m.csv"
    manifest_mod.main(["init", "--manifest", str(path)])
    manifest_mod.main(
        ["add", "--manifest", str(path), "--scope", "passage",
         "--reference", "KRI II 569 (lines 3-16)", "--added", "2026-10-26", "--pending"]
    )
    assert manifest_mod.main(["validate", "--manifest", str(path)]) == 0
    assert manifest_mod.main(["validate", "--manifest", str(path), "--strict"]) == 1
    assert "manifest sha256" in capsys.readouterr().out

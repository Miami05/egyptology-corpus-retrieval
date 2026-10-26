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


def test_manifest_problems_never_echo_a_fields_content(tmp_path, capsys):
    secret = f"{A1} ꞽri̯.n=f"
    bad = entry(entry_id=secret, added=secret, scope=secret, hash_basis=secret, sha256=secret, reference=secret)
    problems = manifest_mod.validate(Manifest(entries=[bad]))
    assert problems and all(A1 not in problem and "ꞽri̯" not in problem for problem in problems)
    path = tmp_path / "m.csv"
    write_manifest(Manifest(entries=[entry(reference=f"KRI II 569 {A1}", sha256=PENDING_HASH, hash_basis="pending")]), path)
    assert manifest_mod.main(["validate", "--manifest", str(path)]) == 1
    captured = capsys.readouterr()
    assert A1 not in captured.out + captured.err


def test_kri_spans_parse_and_overlap_toward_exclusion():
    from scripts.kri_exclusion_manifest import parse_kri_span, spans_overlap

    passage = parse_kri_span("KRI II 569 (lines 3–16), Karnak")
    assert (passage.volume, passage.page_start, passage.line_start, passage.line_end) == ("II", 569, 3, 16)
    assert spans_overlap(parse_kri_span("KRI II 569 (line 5)"), passage)
    assert not spans_overlap(parse_kri_span("KRI II 569 (line 17)"), passage)
    assert not spans_overlap(parse_kri_span("KRI III 569 (line 5)"), passage)
    assert spans_overlap(parse_kri_span("KRI II 569"), passage)  # no line given: whole page
    assert spans_overlap(parse_kri_span("KRI II 569, line 9"), parse_kri_span("KRI II 568-570 (lines 1-2)"))
    assert parse_kri_span("Urk. IV 1") is None


def test_strict_validation_needs_a_kri_citation_for_line_and_passage_entries():
    loose = entry(scope="passage", reference="Karnak hypostyle, somewhere")
    assert any("KRI citation" in p for p in validate_entry(loose, strict=True))
    assert not any("KRI citation" in p for p in validate_entry(loose))


# --------------------------------------------------------------------------- review round 2


def test_every_kri_span_in_a_reference_is_parsed_not_only_the_leading_one():
    from scripts.kri_exclusion_manifest import parse_kri_spans

    spans = parse_kri_spans("KRI II 569 (lines 3-16) = KRI VII 45-46, second edition")
    assert [(s.volume, s.page_start, s.page_end) for s in spans] == [("II", 569, 569), ("VII", 45, 46)]
    assert parse_kri_spans("Urk. IV 1") == []
    # A line whose reference cites the excluded span second is still excluded.
    book = Manifest(entries=[entry(reference="KRI II 569 (lines 3-16), test")])
    assert [e.entry_id for e in book.excludes_reference("KRI VII 45 = KRI II 569 (line 4)")] == ["EX001"]


def test_a_linked_second_edition_of_an_excluded_passage_is_excluded():
    """Synthetic: EX001 excludes a passage; EX002 links it to its second edition."""
    passage = entry(entry_id="EX001", scope="passage", reference="KRI II 569 (lines 3-16), test")
    by_span = entry(entry_id="EX002", scope="edition",
                    reference="KRI II 569 (lines 3-16) = KRI VII 45-46, second edition")
    book = Manifest(entries=[passage, by_span])
    assert [e.entry_id for e in book.excludes_reference("KRI VII 45 (line 2)")] == ["EX001", "EX002"]
    assert book.excludes_reference("KRI VII 47 (line 2)") == []
    # A link by entry id, with only the second edition's span in the reference.
    by_id = entry(entry_id="EX002", scope="edition", reference="KRI VII 45-46, second edition of EX001")
    book = Manifest(entries=[passage, by_id])
    assert [e.entry_id for e in book.excludes_reference("KRI VII 46")] == ["EX001", "EX002"]
    assert not validate(book, strict=False)


def test_an_edition_entry_must_relate_references():
    lonely = entry(entry_id="EX001", scope="edition", reference="KRI VII 45-46, an edition of something")
    assert any("relates no references" in p for p in validate(Manifest(entries=[lonely]), strict=True))
    dangling = entry(entry_id="EX001", scope="edition", reference="KRI VII 45, second edition of EX009")
    assert any("does not have" in p for p in validate(Manifest(entries=[dangling])))


def test_validation_never_prints_a_rejected_entrys_raw_fields(tmp_path, capsys):
    """An entry_id carrying Egyptian text is named by its position, never echoed."""
    secret_id = f"EX001 ḥtp-dj-nsw {A1}"
    path = tmp_path / "m.csv"
    write_manifest(
        Manifest(entries=[
            entry(entry_id=secret_id, reference="KRI II 569 (lines 3-16), test",
                  sha256=PENDING_HASH, hash_basis="pending"),
            entry(entry_id="EX002", reference="KRI II 570, test", added="not-a-date",
                  sha256=PENDING_HASH, hash_basis="pending"),
        ]),
        path,
    )
    assert manifest_mod.main(["validate", "--manifest", str(path)]) == 1
    captured = capsys.readouterr()
    shown = captured.out + captured.err
    assert "ḥtp" not in shown and A1 not in shown and secret_id not in shown
    assert "EX002" not in shown and "KRI II 570" not in shown  # rejected: fields withheld
    assert "entry 1" in shown and "entry 2" in shown
    problems = validate(read_manifest(path))
    assert problems and all("ḥtp" not in p and A1 not in p for p in problems)

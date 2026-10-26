"""Unit tests for the §4a overlap checker (plan 2026-10-26).

Synthetic fixtures only. The "corpus" is six invented rows in
`tests/fixtures/overlap_dev_corpus.csv`; nothing here reads
`data/processed/examples.csv`, the private corpus or any KRI path.

These are the **threshold-edge** tests §4a's fixture table asks for ("unit tests with
hand-built token sets at exact rational J = 0.49/0.50/0.69/0.70, 2- vs 3-word runs,
trigram share 0.49/0.50, containment of q in r vs r in q, 2- vs 3-word q for C4"),
plus the dev fixture end to end.
"""

from __future__ import annotations

import csv
import sys
from fractions import Fraction
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import search_fold
from scripts import check_overlap
from scripts.kri_overlap import (
    CONTAINED,
    NEW,
    PARTIAL,
    PREDICATES,
    check_lines,
    exact_jaccard,
    extra_fold,
    label_for,
    pinned_jaccard,
    predicates_for,
    prepare,
    prepare_lines,
    signs,
)

DEV_CORPUS = PROJECT_ROOT / "tests/fixtures/overlap_dev_corpus.csv"
DEV_FIXTURE = PROJECT_ROOT / "tests/fixtures/overlap_dev_v1.csv"

Z2 = "\U000133E5"  # plural strokes, the corpus's form
Z15B = "\U000133FC"  # three vertical strokes, the TLA form the app folds to Z2
A1 = "\U00013000"
B1 = "\U00013001"
C1_ = "\U00013002"
D1_ = "\U00013003"


def words(count: int, prefix: str) -> list[str]:
    """`count` distinct ASCII tokens that survive the fold unchanged."""
    out = [f"{prefix}{'a' * (i + 1)}" for i in range(count)]
    assert len({search_fold(w) for w in out}) == count
    return out


def line(tokens: list[str], hieroglyphs: str = "", key: str = "q") -> object:
    return prepare(key=key, transliteration=" ".join(tokens), hieroglyphs=hieroglyphs)


def token_sets_with_jaccard(target: Fraction, shared: int | None = None) -> tuple[list[str], list[str]]:
    """Two token lists whose exact Jaccard is `target`, with no shared 3-word run.

    |A n B| = shared, |A u B| = shared / target. The private tokens are interleaved
    so that no three consecutive words are the same on both sides, which keeps these
    tests about J alone.
    """
    if shared is None:
        # `shared` chosen so the union is exactly 100 tokens, whatever `target`
        # reduces to: J = shared / 100.
        shared = target.numerator * (100 // target.denominator)
    union = shared / target
    assert union.denominator == 1, f"{target} needs a different `shared`"
    private = int(union) - shared
    left_only, right_only = private // 2, private - private // 2
    common = words(shared, "s")
    left = words(left_only, "l")
    right = words(right_only, "r")
    a, b = [], []
    for index, token in enumerate(common):
        a.append(token)
        b.append(token)
        if index < len(left):
            a.append(left[index])
        if index < len(right):
            b.append(right[index])
    a.extend(left[len(common):])
    b.extend(right[len(common):])
    return a, b


# --------------------------------------------------------------------- pinned pieces


def test_the_exact_jaccard_agrees_with_the_pinned_float_one():
    """§4a pins `scripts.eval_guards.jaccard`; the rational form must be that number."""
    for left, right in [({"a", "b"}, {"b", "c"}), ({"a"}, {"a"}), (set(), {"a"}), ({"a", "b", "c"}, {"a", "b"})]:
        assert float(exact_jaccard(left, right)) == pytest.approx(pinned_jaccard(left, right))


def test_search_fold_already_folds_the_yod_and_the_space_before_the_suffix():
    """§4a adds "the yod ꞽ/j/i and spacing-before-`=` folds the tool uses".

    Both are inside `search_fold` already. This test is the tripwire: if either ever
    leaves it, the checker would silently lose a fold, and §4a's extra-fold evidence
    type is explicitly *not* allowed to make up for that.
    """
    assert search_fold("ꞽri̯.n=f") == search_fold("jrj.n=f") == search_fold("iri.n=f")
    assert search_fold("ꞽri̯.n =f") == search_fold("ꞽri̯.n=f")


def test_the_extra_fold_is_reported_and_never_changes_a_label():
    """An extra-fold-only match is evidence, not containment."""
    row = prepare("r", "nfr  htp", "", source="TLA")
    query = prepare("q", "nfr htp", "")
    assert extra_fold("nfr  htp") == extra_fold("nfr htp")
    [result] = check_lines([query], [row])
    # Whatever the predicates said, EXTRA_FOLD is not one of them.
    assert "EXTRA_FOLD" not in result.fired
    assert set(result.fired) <= set(PREDICATES)


def test_the_app_sign_normalisation_is_applied_and_reported():
    """SIGNS_RULE: a variant codepoint must not make a seen line look new."""
    row = prepare("r", "nfr", A1 + Z2 + B1, source="TLA")
    query = prepare("q", "ky ḏd", A1 + Z15B + B1)
    assert signs(A1 + Z15B + B1) == signs(A1 + Z2 + B1)
    hits = predicates_for(query, row)
    assert "C2" in hits and hits["C2"] == "normalised-only"


# --------------------------------------------------------------------- C1


def test_c1_fires_on_the_strict_key_and_on_the_fold_and_needs_both_non_empty():
    row = prepare("r", "ꞽri̯.n=f", "", source="TLA")
    assert "C1" in predicates_for(prepare("q", "jrj.n=f", ""), row)
    empty_row = prepare("r", "[...]", "", source="TLA")
    assert "C1" not in predicates_for(prepare("q", "...", ""), empty_row)


# --------------------------------------------------------------------- C2


def test_c2_needs_two_signs_on_the_line():
    row = prepare("r", "nfr", A1 + B1, source="TLA")
    assert "C2" in predicates_for(prepare("q", "ky", A1 + B1), row)
    one_sign_row = prepare("r", "nfr", A1, source="TLA")
    assert "C2" not in predicates_for(prepare("q", "ky", A1), one_sign_row)


# --------------------------------------------------------------------- C3 / P1 edges


@pytest.mark.parametrize(
    "value, predicate",
    [
        (Fraction(70, 100), "C3"),
        (Fraction(69, 100), "P1"),
        (Fraction(50, 100), "P1"),
        (Fraction(49, 100), None),
    ],
)
def test_the_jaccard_thresholds_are_inclusive_at_0_70_and_0_50(value, predicate):
    """0.70 and 0.50 are inclusive bounds; 0.69 and 0.49 are on the other side."""
    left, right = token_sets_with_jaccard(value)
    query, row = line(left), prepare("r", " ".join(right), "", source="TLA")
    assert exact_jaccard(set(query.tokens), set(row.tokens)) == value
    hits = predicates_for(query, row)
    assert ("C3" in hits) == (predicate == "C3")
    assert ("P1" in hits) == (predicate == "P1")


def test_c3_and_p1_are_mutually_exclusive_by_construction():
    left, right = token_sets_with_jaccard(Fraction(70, 100))
    hits = predicates_for(line(left), prepare("r", " ".join(right), "", source="TLA"))
    assert "C3" in hits and "P1" not in hits


# --------------------------------------------------------------------- C4 / P2


def test_c4_needs_three_folded_words_and_word_boundaries():
    row = prepare("r", "nfr ḥtp nswt nṯr pr", "", source="TLA")
    assert "C4" in predicates_for(line(["ḥtp", "nswt", "nṯr"]), row)
    assert "C4" not in predicates_for(line(["ḥtp", "nswt"]), row)  # two words
    # Word-bounded, not substring: a prefix of a word does not count.
    assert "C4" not in predicates_for(line(["ḥt", "nswt", "nṯr"]), row)


def test_the_other_direction_is_p2_not_c4():
    """§4a: a corpus row of >= 3 words inside the line is `partial`, not containment."""
    row = prepare("r", "ḥtp nswt nṯr", "", source="TLA")
    query = line(["bꜣk", "ꞽm", "ḥtp", "nswt", "nṯr", "bnr", "ḥw", "sḫt", "ḏw", "ꞽwn", "wr", "mn"])
    hits = predicates_for(query, row)
    assert "P2" in hits and "C4" not in hits
    assert label_for(hits) == PARTIAL


def test_p2_needs_a_run_of_three_not_two():
    row = prepare("r", "nfr ḥtp nswt nṯr pr", "", source="TLA")
    assert "P2" in predicates_for(line(["ḥtp", "nswt", "nṯr", "bꜣk", "bnr", "ḥw", "sḫt", "ḏw"]), row)
    two_word_run = line(["ḥtp", "nswt", "bꜣk", "bnr", "ḥw", "sḫt", "ḏw", "ꞽwn"])
    assert "P2" not in predicates_for(two_word_run, row)


# --------------------------------------------------------------------- P3 edges


def test_the_trigram_share_threshold_is_inclusive_at_one_half():
    """T(q) of 100 trigrams; the row carries exactly 50, then exactly 49."""
    glyphs = [chr(0x13000 + i) for i in range(102)]
    query = prepare("q", "ky ḏd", "".join(glyphs))  # 100 trigrams
    half = prepare("r", "nfr", "".join(glyphs[:52]), source="TLA")  # trigrams 0..49
    assert predicates_for(query, half).get("P3", "").startswith("share 50/100")
    just_under = prepare("r", "nfr", "".join(glyphs[:51]), source="TLA")  # 49
    assert "P3" not in predicates_for(query, just_under)


def test_p3_needs_three_signs_on_both_sides():
    query = prepare("q", "ky", A1 + B1)
    row = prepare("r", "nfr", A1 + B1 + C1_, source="TLA")
    assert "P3" not in predicates_for(query, row)


# --------------------------------------------------------------------- labels


def test_the_precedence_is_fixed_any_c_beats_any_p():
    assert label_for(["P1", "P2", "C4"]) == CONTAINED
    assert label_for(["P3"]) == PARTIAL
    assert label_for([]) == NEW


def test_every_predicate_that_fired_is_reported_not_just_the_label():
    """§4a: "The report prints every predicate that fired, with the r key and the J
    value, so `partial` via P2/P3 is never presented as containment"."""
    row = prepare("r", "nfr ḥtp nswt nṯr pr sn mn wꜣḥ", "", source="TLA")
    [result] = check_lines([line(["ḥtp", "nswt", "nṯr"], key="L1")], [row])
    assert result.label == CONTAINED
    assert set(result.fired) == {"C4", "P2"}
    assert all(result.evidence[p].witness == "r" for p in result.fired)
    assert "C4 (q contained in r)" in result.summary()


def test_the_witness_kept_is_the_highest_jaccard_row():
    near = prepare("near", "nfr ḥtp nswt nṯr", "", source="TLA")
    far = prepare("far", "nfr ḥtp nswt bꜣk bnr ḥw sḫt ḏw ꞽwn wr", "", source="AES")
    [result] = check_lines([line(["nfr", "ḥtp", "nswt"], key="L1")], [far, near])
    assert result.evidence["C4"].witness == "near"


def test_the_ramses_nearest_neighbour_is_reported_for_every_line():
    """§4d requires it whatever the label — Ramses is Ramesside, like KRI."""
    rows = [
        prepare("ram", "nfr ḥtp nswt", "", source="Ramses"),
        prepare("tla", "bꜣk ꞽm bnr", "", source="TLA"),
    ]
    [result] = check_lines([line(["bꜣk", "ꞽm", "bnr"], key="L1")], rows)
    assert result.nearest_ramses_witness == "ram"
    assert result.nearest_ramses == Fraction(0)


def test_a_duplicate_line_id_is_refused():
    with pytest.raises(ValueError):
        prepare_lines([{"line_id": "L1", "transliteration": "a"}, {"line_id": "L1", "transliteration": "b"}])


# --------------------------------------------------------------------- the dev fixture


def test_the_dev_fixture_passes_its_own_gate():
    assert check_overlap.main(["--fixture", str(DEV_FIXTURE), "--examples", str(DEV_CORPUS)]) == 0


def test_the_fixture_runner_refuses_a_corpus_the_fixture_was_not_frozen_on(tmp_path):
    """§4a retires a fixture whose corpus changed; it must not quietly re-score it."""
    other = tmp_path / "corpus.csv"
    other.write_text(
        DEV_CORPUS.read_text(encoding="utf-8") + "bꜣk ꞽm bnr,,TLA,TLA_7\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit) as error:
        check_overlap.main(["--fixture", str(DEV_FIXTURE), "--examples", str(other)])
    assert "retires a fixture whose corpus changed" in str(error.value)


def test_a_gate_failure_is_reported_row_by_row(tmp_path, capsys):
    broken = tmp_path / "broken.csv"
    rows = list(csv.DictReader(DEV_FIXTURE.open(encoding="utf-8")))
    rows[-1]["expected_label"] = "new"  # the 0.70 edge is `contained`
    with broken.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    assert check_overlap.main(["--fixture", str(broken), "--examples", str(DEV_CORPUS)]) == 1
    assert "label contained != expected new" in capsys.readouterr().out


# --------------------------------------------------------------------- the CLI


def write_lines(path: Path, records: list[dict]) -> None:
    """Write the SHARED lines file (the driver reads the same one).

    Records may use the short names `transliteration` / `hieroglyphs`, which become
    the gold reading and the glyph input.
    """
    from scripts.kri_overlap import LINES_FILE_COLUMNS

    rows = []
    for record in records:
        row = {column: "" for column in LINES_FILE_COLUMNS}
        row.update({k: v for k, v in record.items() if k in LINES_FILE_COLUMNS})
        if "transliteration" in record:
            row["gold_reading"] = record["transliteration"]
        if "hieroglyphs" in record:
            row["glyph_input"] = record["hieroglyphs"]
        rows.append(row)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(LINES_FILE_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_the_report_carries_no_line_text(tmp_path):
    """The report is committed-safe by construction: ids, labels, witnesses, numbers."""
    lines = tmp_path / "lines.csv"
    secret = "bꜣk ꞽm bnr sḫt ḏw"
    write_lines(lines, [{"line_id": "KRI_01", "transliteration": secret, "hieroglyphs": A1 + B1}])
    out = tmp_path / "report.csv"
    assert check_overlap.main(
        ["--lines", str(lines), "--examples", str(DEV_CORPUS), "--output", str(out)]
    ) == 0
    written = out.read_text(encoding="utf-8")
    assert "KRI_01" in written and "new" in written
    for token in secret.split() + [A1, B1]:
        assert token not in written
    sidecar = out.with_suffix(".csv.json")
    assert "examples_sha256" in sidecar.read_text(encoding="utf-8")


def test_a_partial_line_never_leaks_its_shared_words(tmp_path, capsys):
    """P2's evidence is counts and offsets, never the shared run (review 2026-10-26).

    The line shares `ḏd mdw ꞽn` with TLA_5, so P2 fires; neither the report, nor
    stdout, nor the sidecar may carry those words — raw or folded.
    """
    lines = tmp_path / "lines.csv"
    secret = "bꜣk ḏd mdw ꞽn sḫt ḥw ꞽwn wr bnr ḏw"
    write_lines(lines, [{"line_id": "L1", "transliteration": secret}])
    out = tmp_path / "report.csv"
    assert check_overlap.main(
        ["--lines", str(lines), "--examples", str(DEV_CORPUS), "--output", str(out)]
    ) == 0
    row = list(csv.DictReader(out.open(encoding="utf-8")))[0]
    assert "P2" in row["predicates_fired"]
    assert "offset(s) 1" in row["evidence"]
    written = out.read_text(encoding="utf-8") + capsys.readouterr().out
    written += out.with_suffix(".csv.json").read_text(encoding="utf-8")
    for token in set(secret.split()) | set(search_fold(secret).split()):
        assert f" {token} " not in f" {written} ".replace("[", " ").replace("]", " "), token


def test_p2_detail_is_counts_and_offsets_only():
    row = prepare("r", "nfr ḥtp nswt nṯr pr", "", source="TLA")
    detail = predicates_for(line(["bꜣk", "ḥtp", "nswt", "nṯr", "bnr"]), row)["P2"]
    assert detail == "1 shared 3-word run(s) at line word offset(s) 1"


def test_the_query_transliteration_is_checked_too(tmp_path):
    """Endpoint R's input is part of the line: a contained query makes it `contained`."""
    lines = tmp_path / "lines.csv"
    write_lines(
        lines,
        [{"line_id": "L1", "transliteration": "bꜣk ꞽm bnr", "query_transliteration": "ḏd mdw ꞽn wsꞽr"}],
    )
    out = tmp_path / "report.csv"
    check_overlap.main(["--lines", str(lines), "--examples", str(DEV_CORPUS), "--output", str(out)])
    row = list(csv.DictReader(out.open(encoding="utf-8")))[0]
    assert row["label"] == CONTAINED and "C1" in row["predicates_fired"]


def test_the_lines_file_is_the_drivers_schema(tmp_path):
    """One shared schema: the old checker-only columns are refused, not guessed."""
    lines = tmp_path / "lines.csv"
    lines.write_text("line_id,transliteration,hieroglyphs\nL1,bꜣk,\n", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        check_overlap.main(["--lines", str(lines), "--examples", str(DEV_CORPUS), "--output", str(tmp_path / "r.csv")])
    assert "run_kri_endpoints.py" in str(error.value)
    from scripts import run_kri_endpoints

    assert run_kri_endpoints.LINE_COLUMNS == check_overlap.LINES_FILE_COLUMNS


def test_the_sidecar_binds_the_report_to_its_inputs(tmp_path):
    lines = tmp_path / "lines.csv"
    write_lines(lines, [{"line_id": "L1", "transliteration": "bꜣk ꞽm bnr"}])
    out = tmp_path / "report.csv"
    check_overlap.main(["--lines", str(lines), "--examples", str(DEV_CORPUS), "--output", str(out)])
    import json

    from scripts.kri_exclusion_manifest import sha256_file

    sidecar = json.loads(out.with_suffix(".csv.json").read_text(encoding="utf-8"))
    assert sidecar["lines_sha256"] == sha256_file(lines)
    assert sidecar["report_sha256"] == sha256_file(out)
    assert sidecar["checker_sha256"] == check_overlap.checker_sha256()
    assert sidecar["examples_sha256"] == sha256_file(DEV_CORPUS)
    assert sidecar["manifest_complete"] is False


def _manifest_with(tmp_path, *entries) -> Path:
    from scripts import kri_exclusion_manifest as manifest_mod

    path = tmp_path / "manifest.csv"
    manifest_mod.main(["init", "--manifest", str(path)])
    for scope, reference, extra in entries:
        manifest_mod.main(
            ["add", "--manifest", str(path), "--scope", scope, "--reference", reference,
             "--added", "2026-10-26"] + extra
        )
    return path


def _excluded_texts(tmp_path, rows) -> Path:
    path = tmp_path / "excluded.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["entry_id", "transliteration", "hieroglyphs"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


PASSAGE = "bꜣk ꞽm bnr sḫt ḏw ḥw ꞽwn wr ḫpr mꜣꜥ"


def _passage_manifest(tmp_path):
    from scripts.kri_exclusion_manifest import content_hash

    digest = content_hash(PASSAGE, basis="canonical_transliteration")
    manifest = _manifest_with(
        tmp_path,
        ("passage", "KRI II 569 (lines 3-16), test passage",
         ["--sha256", digest, "--hash-basis", "canonical_transliteration"]),
    )
    texts = _excluded_texts(tmp_path, [{"entry_id": "EX001", "transliteration": PASSAGE, "hieroglyphs": ""}])
    return manifest, texts


def _run_with_manifest(tmp_path, records, manifest, texts=None):
    lines = tmp_path / "lines.csv"
    write_lines(lines, records)
    out = tmp_path / "report.csv"
    argv = ["--lines", str(lines), "--examples", str(DEV_CORPUS), "--output", str(out),
            "--manifest", str(manifest)]
    if texts is not None:
        argv += ["--excluded-texts", str(texts)]
    assert check_overlap.main(argv) == 0
    return {row["line_id"]: row for row in csv.DictReader(out.open(encoding="utf-8"))}, out


def test_a_subsection_and_a_near_twin_of_an_excluded_passage_are_excluded(tmp_path):
    """Exact hashes alone let both escape (review 2026-10-26); the predicates catch them."""
    manifest, texts = _passage_manifest(tmp_path)
    rows, _out = _run_with_manifest(
        tmp_path,
        [
            {"line_id": "SUB", "transliteration": "sḫt ḏw ḥw ꞽwn"},  # a subsection
            {"line_id": "TWIN", "transliteration": "bꜣk ꞽm bnr sḫt ḏw ḥw ꞽwn wr ḫpr nfr"},  # near-twin
            {"line_id": "OTHER", "transliteration": "nb pt tꜣ dwꜣt"},
        ],
        manifest,
        texts,
    )
    assert rows["SUB"]["excluded_by"] == "EX001" and "C4" in rows["SUB"]["exclusion_evidence"]
    assert rows["TWIN"]["excluded_by"] == "EX001" and "C3" in rows["TWIN"]["exclusion_evidence"]
    assert rows["OTHER"]["excluded_by"] == ""
    for row in rows.values():  # an excluded line may still be run exploratorily
        assert row["runnable"] == ("yes" if row["label"] == NEW else "no")
    assert rows["SUB"]["confirmation_eligible"] == "no"
    assert rows["OTHER"]["confirmation_eligible"] == "yes"


def test_a_line_inside_an_excluded_kri_span_is_excluded_by_reference(tmp_path):
    manifest = _manifest_with(tmp_path, ("passage", "KRI II 569 (lines 3-16), test", ["--pending"]))
    rows, _out = _run_with_manifest(
        tmp_path,
        [
            {"line_id": "IN", "transliteration": "nb pt", "kri_reference": "KRI II 569 (line 5)"},
            {"line_id": "OUT", "transliteration": "nb pt tꜣ", "kri_reference": "KRI II 569 (line 17)"},
            {"line_id": "NOREF", "transliteration": "nb tꜣ"},
        ],
        manifest,
    )
    assert rows["IN"]["exclusion_evidence"] == "EX001:reference"
    assert rows["OUT"]["excluded_by"] == "" and rows["OUT"]["kri_reference_checked"] == "yes"
    assert rows["NOREF"]["kri_reference_checked"] == "no"


def test_an_excluded_text_that_does_not_hash_to_its_entry_is_refused(tmp_path):
    manifest, _texts = _passage_manifest(tmp_path)
    wrong = _excluded_texts(tmp_path, [{"entry_id": "EX001", "transliteration": "nb pt", "hieroglyphs": ""}])
    lines = tmp_path / "lines.csv"
    write_lines(lines, [{"line_id": "L1", "transliteration": "nb tꜣ"}])
    with pytest.raises(SystemExit) as error:
        check_overlap.main(
            ["--lines", str(lines), "--examples", str(DEV_CORPUS), "--output", str(tmp_path / "r.csv"),
             "--manifest", str(manifest), "--excluded-texts", str(wrong)]
        )
    assert "does not hash" in str(error.value) and "nb pt" not in str(error.value)


def test_the_manifest_is_complete_only_with_every_hash_and_every_text(tmp_path):
    import json

    manifest, texts = _passage_manifest(tmp_path)
    _rows, out = _run_with_manifest(tmp_path, [{"line_id": "L1", "transliteration": "nb tꜣ"}], manifest, texts)
    assert json.loads(out.with_suffix(".csv.json").read_text(encoding="utf-8"))["manifest_complete"] is True
    _rows, out = _run_with_manifest(tmp_path, [{"line_id": "L1", "transliteration": "nb tꜣ"}], manifest)
    assert json.loads(out.with_suffix(".csv.json").read_text(encoding="utf-8"))["manifest_complete"] is False
    pending = _manifest_with(tmp_path, ("passage", "KRI II 569 (lines 3-16), test", ["--pending"]))
    _rows, out = _run_with_manifest(tmp_path, [{"line_id": "L1", "transliteration": "nb tꜣ"}], pending)
    sidecar = json.loads(out.with_suffix(".csv.json").read_text(encoding="utf-8"))
    assert sidecar["manifest_complete"] is False
    assert any("pending" in reason or "fill it in" in reason for reason in sidecar["manifest_incomplete_reasons"])


def test_a_fixture_without_a_corpus_sha_is_refused(tmp_path):
    broken = tmp_path / "nosha.csv"
    rows = list(csv.DictReader(DEV_FIXTURE.open(encoding="utf-8")))
    for row in rows:
        row["corpus_sha"] = ""
    with broken.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(SystemExit) as error:
        check_overlap.main(["--fixture", str(broken), "--examples", str(DEV_CORPUS)])
    assert "corpus_sha is empty" in str(error.value)


def test_the_cli_marks_an_excluded_line_as_not_confirmation_eligible(tmp_path):
    """A line in the (B) manifest never counts toward §4e, label notwithstanding;
    it may still be run exploratorily (§4d runs every line it then excludes)."""
    from scripts import kri_exclusion_manifest as manifest_mod

    secret = "bꜣk ꞽm bnr sḫt ḏw"
    manifest = tmp_path / "manifest.csv"
    manifest_mod.main(["init", "--manifest", str(manifest)])
    digest = manifest_mod.content_hash(secret, basis="canonical_transliteration")
    manifest_mod.main(
        ["add", "--manifest", str(manifest), "--scope", "line", "--reference", "KRI II 569, line 3",
         "--added", "2026-10-26", "--sha256", digest, "--hash-basis", "canonical_transliteration"]
    )
    lines = tmp_path / "lines.csv"
    write_lines(lines, [{"line_id": "KRI_01", "transliteration": secret, "hieroglyphs": ""}])
    out = tmp_path / "report.csv"
    check_overlap.main(
        ["--lines", str(lines), "--examples", str(DEV_CORPUS), "--output", str(out),
         "--manifest", str(manifest)]
    )
    row = list(csv.DictReader(out.open(encoding="utf-8")))[0]
    assert row["label"] == NEW and row["excluded_by"] == "EX001"
    assert row["runnable"] == "yes" and row["confirmation_eligible"] == "no"
    assert "EX001:" in row["exclusion_evidence"] and "hash" in row["exclusion_evidence"]


def test_the_corpus_argument_may_not_point_at_kri_custody(tmp_path):
    from scripts.bfreq_baseline import ForbiddenPathError

    lines = tmp_path / "lines.csv"
    write_lines(lines, [{"line_id": "KRI_01", "transliteration": "bꜣk", "hieroglyphs": ""}])
    with pytest.raises(ForbiddenPathError):
        check_overlap.main(
            ["--lines", str(lines), "--examples", "~/egyptology-private-kri/examples.csv",
             "--output", str(tmp_path / "r.csv")]
        )


def test_a_private_dir_without_standrews_is_refused(tmp_path):
    lines = tmp_path / "lines.csv"
    write_lines(lines, [{"line_id": "KRI_01", "transliteration": "bꜣk", "hieroglyphs": ""}])
    with pytest.raises(SystemExit) as error:
        check_overlap.main(
            ["--lines", str(lines), "--examples", str(DEV_CORPUS), "--private-dir", str(tmp_path),
             "--output", str(tmp_path / "r.csv")]
        )
    assert "standrews.csv" in str(error.value)


def test_private_rows_join_the_gate_corpus_and_are_labelled_as_witnesses(tmp_path):
    """§4a: "With `--private-dir`, G also includes `standrews.csv` at a recorded sha256"."""
    private = tmp_path / "private"
    private.mkdir()
    (private / "standrews.csv").write_text(
        "transliteration_gold,hieroglyphs,source,source_ref\nbꜣk ꞽm bnr sḫt ḏw,,StAndrews,SA_1\n",
        encoding="utf-8",
    )
    lines = tmp_path / "lines.csv"
    write_lines(lines, [{"line_id": "KRI_01", "transliteration": "bꜣk ꞽm bnr sḫt ḏw", "hieroglyphs": ""}])
    out = tmp_path / "report.csv"
    check_overlap.main(
        ["--lines", str(lines), "--examples", str(DEV_CORPUS), "--private-dir", str(private),
         "--output", str(out)]
    )
    row = list(csv.DictReader(out.open(encoding="utf-8")))[0]
    assert row["label"] == CONTAINED
    assert row["max_jaccard_witness"].startswith("private/")

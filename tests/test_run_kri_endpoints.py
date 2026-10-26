"""End-to-end tests for the KRI endpoint driver, on a synthetic declaration.

Synthetic fixtures only: a six-row invented corpus written into `tmp_path`, two
invented "KRI" lines made of real codepoints, a declaration pinned to this commit
and that corpus's sha256, and a hand-written judgement file standing in for
Camilla's blind judging. Nothing here reads the real corpus or any KRI path, and the
lexicon is switched off so the run depends on nothing outside the test.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import check_overlap, run_kri_endpoints as driver
from scripts.bfreq_baseline import BFreqEntry
from scripts.kri_declaration import DECLARATION_COLUMNS

# Nine signs: three attested three-sign sentences, built so that the test lines
# reuse the *groups* without reproducing any *sentence* (otherwise §4a would label
# them `contained` and the driver would — rightly — refuse to run them).
S = [chr(0x13000 + index) for index in range(9)]
CORPUS_ROWS = [
    (f"{S[0]} {S[1]} {S[2]}", "nfr ḥtp bnr"),
    (f"{S[3]} {S[4]} {S[5]}", "nswt bꜣk ḏw"),
    (f"{S[6]} {S[7]} {S[8]}", "sḫt ḥw ꞽwn"),
]


def write_csv(path: Path, columns, rows) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def corpus(tmp_path) -> Path:
    rows = []
    for repeat in range(4):  # a few attestations per group, so the model is confident
        for index, (glyphs, reading) in enumerate(CORPUS_ROWS):
            rows.append(
                {
                    "source": "TLA",
                    "source_ref": f"TLA_{index}_{repeat}",
                    "hieroglyphs": glyphs,
                    "transliteration_gold": reading,
                    "language_stage": "Late Egyptian",
                }
            )
    return write_csv(
        tmp_path / "examples.csv",
        ("source", "source_ref", "hieroglyphs", "transliteration_gold", "language_stage"),
        rows,
    )


@pytest.fixture
def lines(tmp_path) -> Path:
    return write_csv(
        tmp_path / "lines.csv",
        driver.LINE_COLUMNS,
        [
            {
                "line_id": "KRI_01",
                "kri_reference": "KRI II 570 (line 1)",
                "glyph_input": S[0] + S[3] + S[6],
                "gold_groups": f"{S[0]} {S[3]} {S[6]}",
                "gold_reading": "nfr nswt sḫt",
                "query_transliteration": "",
            },
            {
                "line_id": "KRI_02",
                "kri_reference": "KRI II 570 (line 2)",
                "glyph_input": "",
                "gold_groups": "",
                "gold_reading": "",
                "query_transliteration": "ḏw ꞽwn bnr",
            },
        ],
    )


def make_overlap_report(tmp_path, corpus, lines, extra=()) -> Path:
    out = tmp_path / "overlap-report.csv"
    assert check_overlap.main(
        ["--lines", str(lines), "--examples", str(corpus), "--output", str(out), *extra]
    ) == 0
    return out


@pytest.fixture
def overlap_report(tmp_path, corpus, lines) -> Path:
    """The real §4a checker, run on the SAME lines file and synthetic corpus."""
    out = make_overlap_report(tmp_path, corpus, lines)
    labels = {row["line_id"]: row["label"] for row in csv.DictReader(out.open(encoding="utf-8"))}
    assert labels == {"KRI_01": "new", "KRI_02": "new"}, labels
    return out


def declaration_rows(commit: str, corpus_sha: str, cohort: str = "exploratory") -> list[dict]:
    common = {
        "stage": "auto",
        "cohort": cohort,
        "material_received": "2026-10-26",
        "declared_on": "2026-10-26",
        "commit": commit,
        "corpus_sha256": corpus_sha,
        "notes": "",
    }
    return [
        {"declaration_id": "KRI_01_G", "line_id": "KRI_01", "input_modality": "glyphs", "endpoint": "G", **common},
        {"declaration_id": "KRI_02_R", "line_id": "KRI_02", "input_modality": "transliteration", "endpoint": "R", **common},
    ]


@pytest.fixture
def declaration(tmp_path, corpus) -> Path:
    from scripts.kri_exclusion_manifest import sha256_file

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    return write_csv(
        tmp_path / "declaration.csv",
        DECLARATION_COLUMNS,
        declaration_rows(commit, sha256_file(corpus)),
    )


@pytest.fixture
def judgements(tmp_path) -> Path:
    return write_csv(
        tmp_path / "judgements.csv",
        driver.JUDGEMENT_COLUMNS,
        [{"line_id": "KRI_02", "app_success": "1", "baseline_success": "0"}],
    )


def run(tmp_path, declaration, lines, overlap_report, corpus, judgements=None, extra=()):
    out = tmp_path / "out"
    argv = [
        "--declaration", str(declaration),
        "--lines", str(lines),
        "--overlap-report", str(overlap_report),
        "--examples", str(corpus),
        "--build-bfreq",
        "--out", str(out),
        "--no-lexicon",
    ]
    if judgements is not None:
        argv += ["--judgements", str(judgements)]
    code = driver.main(argv + list(extra))
    return code, out


# --------------------------------------------------------------------- the whole run


def test_the_driver_runs_both_endpoints_end_to_end(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    code, out = run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert code == 0
    results = json.loads((out / "summary.json").read_text(encoding="utf-8"))

    g_rows = list(csv.DictReader((out / "endpoint_g_lines.csv").open(encoding="utf-8")))
    assert len(g_rows) == 1
    row = g_rows[0]
    assert row["error"] == ""
    assert int(row["gold_groups"]) == 3
    # The app segments the paste itself; on this corpus each sign is its own group.
    assert int(row["exact"]) == 3
    assert row["app_success"] == "yes" and int(row["app_hits"]) == 3
    # B-freq is handed the gold division, so it answers all three too.
    assert row["baseline_success"] == "yes" and int(row["baseline_hits"]) == 3

    r_rows = list(csv.DictReader((out / "endpoint_r_lines.csv").open(encoding="utf-8")))
    assert r_rows[0]["judged"] == "yes"
    assert r_rows[0]["app_success"] == "yes" and r_rows[0]["baseline_success"] == "no"

    # Both lines are exploratory: descriptive counts, never a confirmatory statistic.
    assert results["endpoints"]["G"]["exploratory"]["n"] == 1
    assert results["endpoints"]["R"]["exploratory"]["wins"] == 1
    assert results["endpoints"]["G"]["confirmation"]["n"] == 0
    assert results["endpoints"]["G"]["underpowered"] and results["endpoints"]["R"]["underpowered"]
    # The test's hermetic flags make this an experimental run: no verdict at all.
    assert results["verdict_allowed"] is False and results["configuration"].startswith("experimental")
    for block in results["endpoints"].values():
        for key in ("p_value", "interval", "holm_reject", "beats_baseline", "margin"):
            assert key not in block
    assert results["secondary"]["G_late_egyptian_bfreq"]["n"] == 1


def test_the_summary_says_what_section_4d_requires_it_to_say(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    _code, out = run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "never pooled" in summary
    assert "uninformative" in summary
    assert "exploratory" in summary
    assert "B-freq is given the gold word division" in summary
    assert "no percentages" in summary  # n < 30


def test_the_outputs_carry_no_egyptian(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    """Counts and ids only: these files are derived from KRI material."""
    _code, out = run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    for name in ("endpoint_g_lines.csv", "endpoint_r_lines.csv", "summary.md"):
        text = (out / name).read_text(encoding="utf-8")
        for sign in S:
            assert sign not in text
        for reading in ("nfr", "nswt", "sḫt", "ḏw", "ꞽwn"):
            assert reading not in text


def test_an_unjudged_retrieval_line_is_recorded_as_unjudged_not_as_a_loss(
    tmp_path, declaration, lines, overlap_report, corpus
):
    code, out = run(tmp_path, declaration, lines, overlap_report, corpus, judgements=None)
    assert code == 1  # a line that could not be scored fails the run, loudly
    r_rows = list(csv.DictReader((out / "endpoint_r_lines.csv").open(encoding="utf-8")))
    assert r_rows[0]["judged"] == "no" and "no blind judgement" in r_rows[0]["error"]
    results = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert results["endpoints"]["R"]["exploratory"]["n"] == 0
    assert results["endpoints"]["R"]["failed"] == 1
    assert results["run_complete"] is False and results["verdict_allowed"] is False
    assert any("incomplete" in reason for reason in results["no_verdict_because"])


# --------------------------------------------------------------------- the refusals


def test_a_corpus_that_is_not_the_declared_one_stops_the_run(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    corpus.write_text(corpus.read_text(encoding="utf-8") + "TLA,X,,nfr,Late Egyptian\n", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert "pins corpus sha256" in str(error.value)


def test_a_declaration_pinned_to_another_commit_stops_the_run(
    tmp_path, corpus, lines, overlap_report, judgements
):
    from scripts.kri_exclusion_manifest import sha256_file

    path = write_csv(
        tmp_path / "declaration.csv",
        DECLARATION_COLUMNS,
        declaration_rows("f" * 40, sha256_file(corpus)),
    )
    with pytest.raises(SystemExit) as error:
        run(tmp_path, path, lines, overlap_report, corpus, judgements)
    assert "pins commit" in str(error.value)


def test_an_invalid_declaration_stops_the_run(tmp_path, corpus, lines, overlap_report, judgements):
    from scripts.kri_exclusion_manifest import sha256_file

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    rows = declaration_rows(commit, sha256_file(corpus))
    rows[0]["endpoint"] = "R"  # a crossed pairing
    path = write_csv(tmp_path / "declaration.csv", DECLARATION_COLUMNS, rows)
    with pytest.raises(SystemExit) as error:
        run(tmp_path, path, lines, overlap_report, corpus, judgements)
    assert "not valid" in str(error.value)


def rewrite_report_and_rebind(overlap_report: Path, rows: list[dict]) -> None:
    """Edit a report AND forge its sidecar's report sha, to test the row checks."""
    from scripts.kri_exclusion_manifest import sha256_file

    write_csv(overlap_report, check_overlap.REPORT_COLUMNS, rows)
    sidecar_path = overlap_report.with_suffix(".csv.json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["report_sha256"] = sha256_file(overlap_report)
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")


def test_a_line_that_is_not_new_is_never_run(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    rows = list(csv.DictReader(overlap_report.open(encoding="utf-8")))
    rows[0]["label"], rows[0]["runnable"] = "contained", "no"
    rewrite_report_and_rebind(overlap_report, rows)
    with pytest.raises(SystemExit) as error:
        run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert "runs only on `new` lines" in str(error.value)


def test_the_label_is_checked_not_only_the_runnable_flag(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    """A `contained` row that says runnable=yes is still refused (review 2026-10-26)."""
    rows = list(csv.DictReader(overlap_report.open(encoding="utf-8")))
    rows[0]["label"], rows[0]["runnable"] = "contained", "yes"
    rewrite_report_and_rebind(overlap_report, rows)
    with pytest.raises(SystemExit) as error:
        run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert "runs only on `new` lines" in str(error.value)


def test_an_edited_report_is_refused(tmp_path, declaration, lines, overlap_report, corpus, judgements):
    rows = list(csv.DictReader(overlap_report.open(encoding="utf-8")))
    write_csv(overlap_report, check_overlap.REPORT_COLUMNS, rows[:1] + rows[1:])
    overlap_report.write_text(overlap_report.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert "changed after the checker wrote it" in str(error.value)


def test_a_report_on_other_lines_or_another_corpus_is_refused(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    """The report is bound to the lines file and the corpus it was made from."""
    lines.write_text(lines.read_text(encoding="utf-8").replace("KRI II 570 (line 2)", "KRI II 571"), encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert "different lines file" in str(error.value)


def test_a_report_without_its_sidecar_is_refused(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    overlap_report.with_suffix(".csv.json").unlink()
    with pytest.raises(SystemExit) as error:
        run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert "sidecar" in str(error.value)


def test_a_line_missing_from_the_overlap_report_is_never_run(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    rows = [row for row in csv.DictReader(overlap_report.open(encoding="utf-8"))][1:]
    rewrite_report_and_rebind(overlap_report, rows)
    with pytest.raises(SystemExit) as error:
        run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert "overlap-checks every line first" in str(error.value)


def _rewrite_lines_and_report(tmp_path, corpus, lines, rows):
    write_csv(lines, driver.LINE_COLUMNS, rows)
    return make_overlap_report(tmp_path, corpus, lines)


def test_a_declared_line_missing_from_the_lines_file_is_refused_before_anything_runs(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    rows = [row for row in csv.DictReader(lines.open(encoding="utf-8")) if row["line_id"] != "KRI_01"]
    write_csv(lines, driver.LINE_COLUMNS, rows)
    report = make_overlap_report(tmp_path, corpus, lines)
    # The report no longer lists KRI_01, so the overlap gate already refuses.
    with pytest.raises(SystemExit):
        run(tmp_path, declaration, lines, report, corpus, judgements)
    assert not (tmp_path / "out").exists()


def test_a_mismatched_gold_division_is_refused_before_the_app_runs(
    tmp_path, declaration, lines, corpus, judgements, capsys
):
    """A gold division that is not its glyph input is a data-entry error (review 2026-10-26)."""
    rows = list(csv.DictReader(lines.open(encoding="utf-8")))
    rows[0]["gold_groups"] = f"{S[0]} {S[3]} {S[7]}"  # a sign the paste does not carry
    report = _rewrite_lines_and_report(tmp_path, corpus, lines, rows)
    with pytest.raises(SystemExit) as error:
        run(tmp_path, declaration, lines, report, corpus, judgements)
    assert "nothing was run" in str(error.value)
    assert "not the glyph input it divides" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_an_empty_glyph_input_with_a_gold_division_is_refused(tmp_path, declaration, lines, corpus, judgements, capsys):
    rows = list(csv.DictReader(lines.open(encoding="utf-8")))
    rows[0]["glyph_input"] = ""
    rows[0]["gold_reading"] = "nfr nswt sḫt"
    report = _rewrite_lines_and_report(tmp_path, corpus, lines, rows)
    with pytest.raises(SystemExit):
        run(tmp_path, declaration, lines, report, corpus, judgements)
    assert "needs a glyph_input" in capsys.readouterr().err


def test_a_gold_reading_count_that_does_not_match_the_groups_is_refused(
    tmp_path, declaration, lines, corpus, judgements, capsys
):
    rows = list(csv.DictReader(lines.open(encoding="utf-8")))
    rows[0]["gold_reading"] = "nfr nswt"
    report = _rewrite_lines_and_report(tmp_path, corpus, lines, rows)
    with pytest.raises(SystemExit):
        run(tmp_path, declaration, lines, report, corpus, judgements)
    assert "one reading per group" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["", "maybe", "2"])
def test_a_malformed_judgement_is_refused_not_read_as_a_failure(
    tmp_path, declaration, lines, overlap_report, corpus, value, capsys
):
    path = write_csv(
        tmp_path / "judgements.csv",
        driver.JUDGEMENT_COLUMNS,
        [{"line_id": "KRI_02", "app_success": value, "baseline_success": "0"}],
    )
    with pytest.raises(SystemExit):
        run(tmp_path, declaration, lines, overlap_report, corpus, path)
    assert "app_success is not one of" in capsys.readouterr().err


def test_duplicate_judgements_are_refused(tmp_path, declaration, lines, overlap_report, corpus):
    path = write_csv(
        tmp_path / "judgements.csv",
        driver.JUDGEMENT_COLUMNS,
        [
            {"line_id": "KRI_02", "app_success": "1", "baseline_success": "0"},
            {"line_id": "KRI_02", "app_success": "0", "baseline_success": "1"},
        ],
    )
    with pytest.raises(SystemExit) as error:
        run(tmp_path, declaration, lines, overlap_report, corpus, path)
    assert "repeats line KRI_02" in str(error.value)


def test_duplicate_lines_are_refused(tmp_path, declaration, lines, overlap_report, corpus, judgements):
    rows = list(csv.DictReader(lines.open(encoding="utf-8")))
    with pytest.raises(SystemExit) as error:
        driver.unique_by_line(rows + rows[:1], "lines file")
    assert "repeats line KRI_01" in str(error.value)


def test_an_app_output_that_loses_signs_is_scored_as_misses_not_failed(tmp_path):
    """§4e: groups the app does not produce are misses; the line is flagged, not failed."""
    from scripts.bfreq_baseline import BFreqTable

    class FakeModel:
        def predict_sequence(self, groups):
            from app.services.reading_model import ReadingPrediction

            return [
                ReadingPrediction(sign=g, predicted="nfr", candidates=[], attested_count=1,
                                  is_ambiguous=False, was_seen=True)
                for g in groups
            ]

    record = {"line_id": "L", "glyph_input": S[0] + S[3], "gold_groups": f"{S[0]} {S[3]}", "gold_reading": "nfr nswt"}
    original = driver.run_app_on_line
    driver.run_app_on_line = lambda resources, glyph_input, top_k: (None, False, [S[0]], [["nfr"]])
    try:
        row = driver.score_g_line(None, BFreqTable(), record, 3)
    finally:
        driver.run_app_on_line = original
    assert row["app_sign_mismatch"] == "yes" and row["error"] == ""
    assert row["app_hits"] == 0 and row["app_success"] == "no"


# --------------------------------------------------------------------- eligibility and verdicts


def _rows(confirmation: str, app_only: int = 0, both: int = 0, neither: int = 0, base_only: int = 0):
    def row(app, base):
        return {"app_success": "yes" if app else "no", "baseline_success": "yes" if base else "no",
                "error": "", "confirmation": confirmation}
    return ([row(True, False)] * app_only + [row(True, True)] * both
            + [row(False, False)] * neither + [row(False, True)] * base_only)


def test_exploratory_lines_never_enter_the_confirmatory_statistic():
    """Astra's probe: 150 exploratory wins must not produce "beats its baseline"."""
    blocks = driver.analyse(
        {"G": _rows("no", app_only=150), "R": []}, verdict_allowed=True, why_not=[]
    )
    g = blocks["G"]
    assert g["confirmation"]["n"] == 0 and g["exploratory"]["wins"] == 150
    assert "beats_baseline" not in g and "p_value" not in g
    assert "no confirmation lines" in g["verdict_line"]


def test_a_confirmation_family_gets_its_verdict_and_holm():
    blocks = driver.analyse(
        {"G": _rows("yes", app_only=40, both=60, neither=60) + _rows("no", base_only=500), "R": []},
        verdict_allowed=True,
        why_not=[],
    )
    g = blocks["G"]
    assert g["confirmation"]["n"] == 160 and g["holm_threshold_exact"] == "1/40"
    assert g["holm_reject"] is True and g["beats_baseline"] is True
    assert g["exploratory"]["losses"] == 500  # reported, never tested


def test_an_underpowered_endpoint_never_claims_to_beat_its_baseline():
    blocks = driver.analyse({"G": _rows("yes", app_only=40), "R": []}, verdict_allowed=True, why_not=[])
    assert blocks["G"]["underpowered"] and blocks["G"]["beats_baseline"] is False


def test_small_n_writes_counts_only():
    blocks = driver.analyse({"G": _rows("yes", app_only=4), "R": []}, verdict_allowed=True, why_not=[])
    g = blocks["G"]
    for key in ("interval", "p_value", "margin", "beats_baseline", "holm_reject"):
        assert key not in g
    assert "%" not in g["verdict_line"] and "[" not in g["verdict_line"]


def test_an_incomplete_run_writes_no_verdict():
    blocks = driver.analyse(
        {"G": _rows("yes", app_only=40, both=60, neither=60), "R": []},
        verdict_allowed=False,
        why_not=["1 declared line(s) could not be scored"],
    )
    assert "beats_baseline" not in blocks["G"] and "no verdict" in blocks["G"]["verdict_line"]


# --------------------------------------------------------------------- configuration


def test_experimental_flags_are_refused_for_confirmation_lines(
    tmp_path, corpus, lines, overlap_report, judgements
):
    from scripts.kri_exclusion_manifest import sha256_file

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    rows = declaration_rows(commit, sha256_file(corpus), cohort="confirmation")
    rows[0]["material_received"] = rows[1]["material_received"] = "2026-11-01"
    path = write_csv(tmp_path / "declaration.csv", DECLARATION_COLUMNS, rows)
    with pytest.raises(SystemExit) as error:
        run(tmp_path, path, lines, overlap_report, corpus, judgements)
    assert "experimental override" in str(error.value)


def test_a_confirmation_needs_a_complete_manifest_and_unexcluded_lines(
    tmp_path, corpus, lines, judgements
):
    """Driven through verify_overlap_report, the gate a confirmation passes first."""
    from scripts.kri_declaration import Declaration, DeclaredRun

    report = make_overlap_report(tmp_path, corpus, lines)
    run_ = DeclaredRun(
        declaration_id="KRI_02_R", line_id="KRI_02", input_modality="transliteration", endpoint="R",
        stage="auto", cohort="confirmation", material_received="2026-11-01", declared_on="2026-11-01",
        commit="0" * 40, corpus_sha256="0" * 64,
    )
    from scripts.kri_exclusion_manifest import sha256_file

    with pytest.raises(SystemExit) as error:
        driver.verify_overlap_report(report, lines, sha256_file(corpus), Declaration(runs=[run_]), driver.DEFAULT_MANIFEST)
    assert "complete exclusion manifest" in str(error.value)

    # A line inside an excluded KRI span is refused for confirmation outright.
    from scripts import kri_exclusion_manifest as manifest_mod

    manifest = tmp_path / "m.csv"
    passage = "nb pt tꜣ dwꜣt"
    manifest_mod.main(["init", "--manifest", str(manifest)])
    manifest_mod.main(["add", "--manifest", str(manifest), "--scope", "passage", "--reference",
                       "KRI II 570 (lines 1-3), test", "--added", "2026-10-26",
                       "--sha256", manifest_mod.content_hash(passage, basis="canonical_transliteration"),
                       "--hash-basis", "canonical_transliteration"])
    texts = write_csv(tmp_path / "excluded.csv", ("entry_id", "transliteration", "hieroglyphs"),
                      [{"entry_id": "EX001", "transliteration": passage, "hieroglyphs": ""}])
    report = make_overlap_report(
        tmp_path, corpus, lines, ["--manifest", str(manifest), "--excluded-texts", str(texts)]
    )
    assert json.loads(report.with_suffix(".csv.json").read_text(encoding="utf-8"))["manifest_complete"]
    with pytest.raises(SystemExit) as error:
        driver.verify_overlap_report(report, lines, sha256_file(corpus), Declaration(runs=[run_]), manifest)
    assert "covered by the (B) exclusion manifest" in str(error.value)


def test_a_bfreq_table_is_tied_to_its_header_corpus_and_code(tmp_path):
    from scripts.kri_exclusion_manifest import sha256_file

    table = tmp_path / "bfreq_table_all.csv"
    write_csv(table, ("sign_key", "rank", "reading_key", "count", "surface_reading"),
              [{"sign_key": S[0], "rank": 1, "reading_key": "nfr", "count": 9, "surface_reading": "nfr"}])
    with pytest.raises(SystemExit) as error:
        driver.verify_bfreq_table(table, "c" * 64, confirmation=False)
    assert "bfreq_header.json" in str(error.value)

    header = {
        "corpus_sha256": "c" * 64,
        "top_k": 3,
        "module_sha256": {name: sha256_file(PROJECT_ROOT / name) for name in driver.BFREQ_CODE},
        "tables": {"bfreq_table_all.csv": {"sha256": sha256_file(table)}},
    }
    (tmp_path / "bfreq_header.json").write_text(json.dumps(header), encoding="utf-8")
    assert driver.verify_bfreq_table(table, "c" * 64, confirmation=False)["top_k"] == 3
    with pytest.raises(SystemExit) as error:
        driver.verify_bfreq_table(table, "d" * 64, confirmation=False)
    assert "not the declared corpus" in str(error.value)
    # Not the frozen table recorded in the freeze document: no confirmation.
    with pytest.raises(SystemExit) as error:
        driver.verify_bfreq_table(table, "c" * 64, confirmation=True)
    assert "recorded (or last amended)" in str(error.value)


def test_the_recorded_table_sha_is_read_from_the_freeze_record():
    assert driver.recorded_table_sha("bfreq_table_all.csv") == (
        "2b342dc4d3a4b9f0c0913fc71ac053719c037a7ab0bbd371e0e3fefa556360e1"
    )


# --------------------------------------------------------------------- the pieces


def test_the_app_top_three_is_the_chosen_reading_then_its_alternatives():
    from app.services.reading_model import ReadingPrediction

    prediction = ReadingPrediction(
        sign="x",
        predicted="ḥtp",
        candidates=[("nfr", 0.6), ("ḥtp", 0.3), ("bnr", 0.1)],
        attested_count=10,
        is_ambiguous=True,
        was_seen=True,
    )
    assert driver.app_top_readings(prediction, 3) == ["ḥtp", "nfr", "bnr"]
    assert driver.app_top_readings(prediction, 2) == ["ḥtp", "nfr"]


def test_an_unreadable_group_offers_whatever_candidates_it_has():
    from app.services.reading_model import ReadingPrediction

    prediction = ReadingPrediction(
        sign="x", predicted="", candidates=[], attested_count=0, is_ambiguous=False, was_seen=False
    )
    assert driver.app_top_readings(prediction, 3) == []


def test_the_frozen_table_is_read_back_exactly_as_it_was_written(tmp_path):
    path = tmp_path / "bfreq_table_all.csv"
    write_csv(
        path,
        ("sign_key", "rank", "reading_key", "count", "surface_reading"),
        [
            {"sign_key": S[0], "rank": 1, "reading_key": "nfr", "count": 9, "surface_reading": "nfr"},
            {"sign_key": S[0], "rank": 2, "reading_key": "ḥtp", "count": 2, "surface_reading": "ḥtp.w"},
        ],
    )
    table = driver.load_bfreq_table(path)
    assert table.entries[S[0]] == (
        BFreqEntry(rank=1, reading_key="nfr", count=9, surface_reading="nfr"),
        BFreqEntry(rank=2, reading_key="ḥtp", count=2, surface_reading="ḥtp.w"),
    )
    assert table.top(S[0]) == ["nfr", "ḥtp.w"]

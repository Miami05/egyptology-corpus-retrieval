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
                "glyph_input": S[0] + S[3] + S[6],
                "gold_groups": f"{S[0]} {S[3]} {S[6]}",
                "gold_reading": "nfr nswt sḫt",
                "query_transliteration": "",
            },
            {
                "line_id": "KRI_02",
                "glyph_input": "",
                "gold_groups": "",
                "gold_reading": "",
                "query_transliteration": "ḏw ꞽwn bnr",
            },
        ],
    )


@pytest.fixture
def overlap_report(tmp_path, corpus, lines) -> Path:
    """The real §4a checker, run on the same synthetic corpus."""
    check_lines = write_csv(
        tmp_path / "overlap_lines.csv",
        ("line_id", "transliteration", "hieroglyphs"),
        [
            {"line_id": "KRI_01", "transliteration": "nfr nswt sḫt", "hieroglyphs": S[0] + S[3] + S[6]},
            {"line_id": "KRI_02", "transliteration": "ḏw ꞽwn bnr", "hieroglyphs": ""},
        ],
    )
    out = tmp_path / "overlap-report.csv"
    assert check_overlap.main(
        ["--lines", str(check_lines), "--examples", str(corpus), "--output", str(out)]
    ) == 0
    labels = {row["line_id"]: row["label"] for row in csv.DictReader(out.open(encoding="utf-8"))}
    assert labels == {"KRI_01": "new", "KRI_02": "new"}, labels
    return out


def declaration_rows(commit: str, corpus_sha: str) -> list[dict]:
    common = {
        "stage": "auto",
        "cohort": "exploratory",
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

    assert results["endpoints"]["G"]["scored"] == 1
    assert results["endpoints"]["R"]["wins"] == 1
    # One line each is far below the floor, and both still sit in the Holm family.
    assert results["endpoints"]["G"]["underpowered"] and results["endpoints"]["R"]["underpowered"]
    assert results["endpoints"]["G"]["holm_threshold"] in (0.025, 0.05)


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
    assert results["endpoints"]["R"]["scored"] == 0 and results["endpoints"]["R"]["failed"] == 1


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


def test_a_line_that_is_not_new_is_never_run(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    rows = list(csv.DictReader(overlap_report.open(encoding="utf-8")))
    rows[0]["label"], rows[0]["runnable"] = "contained", "no"
    write_csv(overlap_report, check_overlap.REPORT_COLUMNS, rows)
    with pytest.raises(SystemExit) as error:
        run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert "runs only on `new` lines" in str(error.value)


def test_a_line_missing_from_the_overlap_report_is_never_run(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    rows = [row for row in csv.DictReader(overlap_report.open(encoding="utf-8"))][1:]
    write_csv(overlap_report, check_overlap.REPORT_COLUMNS, rows)
    with pytest.raises(SystemExit) as error:
        run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert "overlap-checks every line first" in str(error.value)


def test_a_declared_line_missing_from_the_lines_file_is_reported_not_skipped(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    rows = [row for row in csv.DictReader(lines.open(encoding="utf-8")) if row["line_id"] != "KRI_01"]
    write_csv(lines, driver.LINE_COLUMNS, rows)
    code, out = run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert code == 1
    g_rows = list(csv.DictReader((out / "endpoint_g_lines.csv").open(encoding="utf-8")))
    assert "missing from the lines file" in g_rows[0]["error"]


def test_a_mismatched_gold_division_is_reported_as_a_failure_not_scored(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    """Gold groups that are not the glyph input mean a mis-assembled run."""
    rows = list(csv.DictReader(lines.open(encoding="utf-8")))
    rows[0]["gold_groups"] = f"{S[0]} {S[3]} {S[7]}"  # a sign the paste does not carry
    write_csv(lines, driver.LINE_COLUMNS, rows)
    code, out = run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert code == 1
    g_rows = list(csv.DictReader((out / "endpoint_g_lines.csv").open(encoding="utf-8")))
    assert "not the same sign string" in g_rows[0]["error"]
    assert g_rows[0]["app_success"] == ""


def test_a_gold_reading_count_that_does_not_match_the_groups_is_refused(
    tmp_path, declaration, lines, overlap_report, corpus, judgements
):
    rows = list(csv.DictReader(lines.open(encoding="utf-8")))
    rows[0]["gold_reading"] = "nfr nswt"
    write_csv(lines, driver.LINE_COLUMNS, rows)
    code, out = run(tmp_path, declaration, lines, overlap_report, corpus, judgements)
    assert code == 1
    g_rows = list(csv.DictReader((out / "endpoint_g_lines.csv").open(encoding="utf-8")))
    assert "one reading per group" in g_rows[0]["error"]


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

"""Unit tests for the frozen B-freq baseline (plan 2026-10-26 §4e, endpoint G).

Synthetic fixtures only. Nothing here reads the real corpus, and nothing here may
read KRI material — the baseline's evidentiary value is that it was frozen before any
KRI line was opened, so one test watches every file the builder touches.

The hieroglyphs below are real codepoints but the "corpus" they sit in is invented:
these tests check the counting and scoring rules, not Egyptian.
"""

from __future__ import annotations

import builtins
import csv
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import bfreq_baseline as bf
from scripts import build_bfreq_table as build_script

# Three distinct signs, plus the one variant pair the normaliser folds.
A = "\U00013000"  # A1
B = "\U00013001"
C = "\U00013002"
Z2 = "\U000133E5"  # plural strokes, the canonical form
Z15B = "\U000133FC"  # three vertical strokes, folded to Z2 by normalize_hieroglyphs


def frame(rows: list[dict]) -> pd.DataFrame:
    """A corpus frame with the three columns B-freq reads."""
    return pd.DataFrame(
        [
            {
                "hieroglyphs": row.get("hieroglyphs", ""),
                "transliteration_gold": row.get("transliteration_gold", ""),
                "language_stage": row.get("language_stage", "Earlier Egyptian"),
            }
            for row in rows
        ]
    )


# ---------------------------------------------------------------------------
# the rule: most frequent attested reading
# ---------------------------------------------------------------------------


def test_most_frequent_reading_wins_and_the_ranking_is_by_count():
    df = frame(
        [
            {"hieroglyphs": A, "transliteration_gold": "pr"},
            {"hieroglyphs": A, "transliteration_gold": "pr"},
            {"hieroglyphs": A, "transliteration_gold": "pr"},
            {"hieroglyphs": A, "transliteration_gold": "zꜣ"},
            {"hieroglyphs": A, "transliteration_gold": "zꜣ"},
            {"hieroglyphs": A, "transliteration_gold": "nb"},
        ]
    )
    table = bf.build_table(df)
    assert table.top(A) == ["pr", "zꜣ", "nb"]
    assert table.top(A, top_k=1) == ["pr"]
    entries = table.entries[bf.sign_key(A)]
    assert [(e.rank, e.reading_key, e.count) for e in entries] == [
        (1, "pr", 3),
        (2, "zꜣ", 2),
        (3, "nb", 1),
    ]


def test_counts_are_per_word_not_per_row():
    """A multi-word row contributes one pair per aligned word, like ReadingModel."""
    df = frame([{"hieroglyphs": f"{A} {B} {A}", "transliteration_gold": "pr nb pr"}])
    table = bf.build_table(df)
    assert table.entries[bf.sign_key(A)][0].count == 2
    assert table.entries[bf.sign_key(B)][0].count == 1
    assert table.pairs == 3


def test_a_misaligned_row_contributes_nothing_and_is_counted():
    df = frame(
        [
            {"hieroglyphs": f"{A} {B}", "transliteration_gold": "pr"},  # 2 signs, 1 word
            {"hieroglyphs": "", "transliteration_gold": "pr nb"},  # text-only
            {"hieroglyphs": A, "transliteration_gold": "pr"},
        ]
    )
    table = bf.build_table(df)
    assert table.rows_misaligned == 1
    assert table.rows_text_only == 1
    assert table.rows_used == 1
    assert table.pairs == 1
    assert table.top(B) == []


# ---------------------------------------------------------------------------
# tie-break determinism
# ---------------------------------------------------------------------------


def test_ties_break_by_code_point_not_by_insertion_order():
    """`zꜣ` is seen first but `nb` sorts first, so order of appearance must not decide."""
    df = frame(
        [
            {"hieroglyphs": A, "transliteration_gold": "zꜣ"},
            {"hieroglyphs": A, "transliteration_gold": "nb"},
        ]
    )
    assert bf.build_table(df).top(A) == ["nb", "zꜣ"]

    reversed_df = frame(
        [
            {"hieroglyphs": A, "transliteration_gold": "nb"},
            {"hieroglyphs": A, "transliteration_gold": "zꜣ"},
        ]
    )
    assert bf.build_table(reversed_df).top(A) == ["nb", "zꜣ"]


def test_the_whole_table_is_independent_of_row_order():
    rows = [
        {"hieroglyphs": A, "transliteration_gold": "pr"},
        {"hieroglyphs": A, "transliteration_gold": "nb"},
        {"hieroglyphs": B, "transliteration_gold": "zꜣ"},
        {"hieroglyphs": B, "transliteration_gold": "zꜣ"},
        {"hieroglyphs": C, "transliteration_gold": "ḥm"},
    ]
    forward = bf.table_rows(bf.build_table(frame(rows)))
    backward = bf.table_rows(bf.build_table(frame(list(reversed(rows)))))
    assert forward == backward


# ---------------------------------------------------------------------------
# fold equivalence: the same normalisation the app uses, on both sides
# ---------------------------------------------------------------------------


def test_sign_group_key_applies_the_app_variant_fold():
    """Z15B and Z2 are one group for the app, so they must be one group for B-freq.

    `glyph_key` alone does not fold them — that is exactly why `sign_key` runs the
    app's `normalize_hieroglyphs` first. Without it a gold group pasted with Z15B
    would miss a group the corpus attests, and B-freq would lose for a typographic
    reason.
    """
    from scripts.import_ud_egyptian_pc import glyph_key

    assert glyph_key(Z15B) != glyph_key(Z2)
    assert bf.sign_key(Z15B) == bf.sign_key(Z2) == Z2

    df = frame([{"hieroglyphs": Z2, "transliteration_gold": "w"}] * 2)
    table = bf.build_table(df)
    assert table.top(Z15B) == ["w"]


def test_sign_group_key_ignores_layout_controls_and_placeholders():
    """Format controls, spacing and `<g>` markup never change the key (§4a `signs`)."""
    assert bf.sign_key(f"{A}︀") == A
    assert bf.sign_key(f" {A} ") == A
    assert bf.sign_key(f"{A}<g>US9No2</g>") == A
    assert bf.sign_key("<g>US9No2</g>") == ""
    assert bf.sign_key("") == ""


def test_reading_identity_is_the_app_suggestion_key_so_notation_variants_merge():
    """TLA's `i̯` and the corpus's `ꞽ` are one reading (item D′), so one table entry."""
    df = frame(
        [
            {"hieroglyphs": A, "transliteration_gold": "ḏi̯"},
            {"hieroglyphs": A, "transliteration_gold": "ḏꞽ"},
            {"hieroglyphs": A, "transliteration_gold": "nb"},
        ]
    )
    table = bf.build_table(df)
    # One identity, count 2 — the two notations do not compete as separate readings.
    assert table.top_keys(A) == ["ḏꞽ", "nb"]
    assert table.entries[bf.sign_key(A)][0].count == 2
    # What is *offered* is an attested spelling of that identity (SURFACE_RULE):
    # both spellings occur once, so the code-point tie-break picks `ḏi̯` (i < ꞽ).
    assert table.top(A) == ["ḏi̯", "nb"]
    assert bf.reading_key(table.top(A)[0]) == table.top_keys(A)[0]


def test_the_strict_key_still_keeps_different_consonants_apart():
    """The fold must not go as far as the ASCII search fold: ꜣ ≠ ꜥ (Nederhof, round 2)."""
    df = frame(
        [
            {"hieroglyphs": A, "transliteration_gold": "ꜣb"},
            {"hieroglyphs": A, "transliteration_gold": "ꜥb"},
        ]
    )
    assert len(bf.build_table(df).top(A)) == 2
    assert bf.folded_reading_key("ꜣb") == bf.folded_reading_key("ꜥb")  # the fold would merge


def test_the_word_alignment_is_the_reading_models_own():
    """Pinned against `ReadingModel.fit`, so the app cannot drift away from B-freq."""
    from collections import Counter

    from app.services.reading_model import ReadingModel

    df = pd.DataFrame(
        [
            {"hieroglyphs_norm": f"{A} {B}", "transliteration_gold": "pr nb"},
            {"hieroglyphs_norm": f"{A} {B} {C}", "transliteration_gold": "pr nb"},  # skipped
            {"hieroglyphs_norm": "", "transliteration_gold": "pr"},  # text-only
            {"hieroglyphs_norm": A, "transliteration_gold": "zꜣ"},
            {"hieroglyphs_norm": f"{C} {C}", "transliteration_gold": "ḥm ḥm"},
        ]
    )
    model = ReadingModel().fit(df)
    model_pairs = Counter(
        {
            (sign, reading): count
            for sign, counter in model.sign_reading.items()
            for reading, count in counter.items()
        }
    )
    ours = Counter((group, word) for group, word, _ in bf.iter_word_pairs(df))
    assert ours == model_pairs

    df = df.assign(language_stage="Earlier Egyptian")
    table = bf.build_table(df)
    assert table.rows_misaligned == model.sentences_skipped == 1
    assert table.rows_text_only == model.sentences_text_only == 1
    assert table.rows_used == model.sentences_seen == 3


# ---------------------------------------------------------------------------
# unseen groups
# ---------------------------------------------------------------------------


def test_an_unattested_group_gives_an_explicit_no_reading():
    df = frame([{"hieroglyphs": A, "transliteration_gold": "pr"}])
    table = bf.build_table(df)
    assert table.top(C) == []
    assert table.predict_line([A, C]) == [["pr"], []]


def test_an_unattested_group_is_a_miss_and_never_borrows_from_the_app():
    """B-freq has no fallback: no similarity borrowing, no lexicon, no composition.

    A nearly identical attested group must not leak a reading into the unattested
    one, which the app's `nearest_known_group` fallback would happily do.
    """
    df = frame([{"hieroglyphs": f"{A}{B}", "transliteration_gold": "pr"}] * 5)
    table = bf.build_table(df)
    assert table.top(f"{A}{C}") == []
    score = bf.score_line(["pr"], table.predict_line([f"{A}{C}"]))
    assert score.hits == 0 and score.score == 0.0 and score.success is False


def test_a_group_with_no_signs_at_all_is_a_miss_not_a_crash():
    df = frame([{"hieroglyphs": A, "transliteration_gold": "pr"}])
    table = bf.build_table(df)
    assert table.top("") == []
    assert table.top("<g>US9No2</g>") == []


# ---------------------------------------------------------------------------
# the Late-Egyptian-restricted secondary
# ---------------------------------------------------------------------------


def test_the_late_egyptian_table_sees_only_late_egyptian_rows():
    df = frame(
        [
            {"hieroglyphs": A, "transliteration_gold": "pr", "language_stage": "Earlier Egyptian"},
            {"hieroglyphs": A, "transliteration_gold": "pr", "language_stage": "Earlier Egyptian"},
            {"hieroglyphs": A, "transliteration_gold": "nb", "language_stage": bf.LATE_EGYPTIAN},
            {"hieroglyphs": B, "transliteration_gold": "zꜣ", "language_stage": "Demotic"},
        ]
    )
    primary = bf.build_table(df)
    late = bf.build_table(df, stage=bf.LATE_EGYPTIAN)

    assert primary.top(A) == ["pr", "nb"]
    assert late.top(A) == ["nb"]  # the Earlier majority is invisible to the restriction
    assert late.top(B) == []  # a Demotic row is not Late Egyptian
    assert late.rows_used == 1
    assert late.pairs == 1


def test_the_restriction_counts_skipped_rows_only_within_the_stage():
    df = frame(
        [
            {"hieroglyphs": "", "transliteration_gold": "pr", "language_stage": "Demotic"},
            {"hieroglyphs": "", "transliteration_gold": "nb", "language_stage": bf.LATE_EGYPTIAN},
        ]
    )
    assert bf.build_table(df).rows_text_only == 2
    assert bf.build_table(df, stage=bf.LATE_EGYPTIAN).rows_text_only == 1


# ---------------------------------------------------------------------------
# the scorer (§4e), shared by app and baseline
# ---------------------------------------------------------------------------


def test_the_line_score_is_hits_over_groups_with_success_at_one_half():
    gold = ["pr", "nb", "zꜣ", "ḥm"]
    candidates = [["pr"], ["x", "y", "nb"], ["x"], None]
    score = bf.score_line(gold, candidates)
    assert score.groups == 4
    assert score.hits == 2
    assert score.score == 0.5
    assert score.success is True  # the threshold is inclusive: s >= 0.5
    assert score.group_hits == (True, True, False, False)

    worse = bf.score_line(gold, [["pr"], ["x"], ["x"], None])
    assert worse.score == 0.25 and worse.success is False


def test_only_the_top_three_count():
    gold = ["nb"]
    assert bf.score_line(gold, [["a", "b", "nb"]]).hits == 1
    assert bf.score_line(gold, [["a", "b", "c", "nb"]]).hits == 0
    assert bf.score_line(gold, [["a", "b", "nb"]], top_k=2).hits == 0


def test_a_group_the_app_did_not_produce_is_a_miss():
    """§4e: a group the segmentation merges, splits or misses counts against the app."""
    assert bf.score_line(["pr", "nb"], [["pr"], None]).score == 0.5
    assert bf.score_line(["pr", "nb"], [["pr"], []]).score == 0.5


def test_the_scorer_compares_by_the_suggestion_identity_key_not_by_string():
    assert bf.score_line(["ḏi̯=f"], [["ḏꞽ=f"]]).hits == 1
    assert bf.score_line(["ꜣb"], [["ꜥb"]]).hits == 0
    assert bf.score_line(["ꜣb"], [["ꜥb"]], key=bf.folded_reading_key).hits == 1


def test_an_unreadable_gold_group_is_a_miss_for_both_sides():
    assert bf.score_line(["", "nb"], [["anything"], ["nb"]]).group_hits == (False, True)


def test_the_scorer_refuses_a_malformed_line():
    with pytest.raises(ValueError):
        bf.score_line(["pr", "nb"], [["pr"]])
    with pytest.raises(ValueError):
        bf.score_line([], [])
    with pytest.raises(ValueError):
        bf.score_line(["pr"], [["pr"]], top_k=0)


def test_app_and_baseline_are_scored_by_the_same_function():
    """Symmetry is the test: swap the two sides and the two results swap, nothing else.

    `score_pair` is the only way an analysis gets both numbers, so a second scoring
    path cannot appear without this test noticing.
    """
    gold = ["pr", "nb", "zꜣ", "ḥm"]
    app = [["pr"], ["nb"], ["x"], ["ḥm"]]
    baseline = [["pr"], ["x"], ["x"], None]

    app_score, baseline_score = bf.score_pair(gold, app, baseline)
    swapped_baseline, swapped_app = bf.score_pair(gold, baseline, app)
    assert app_score == swapped_app
    assert baseline_score == swapped_baseline
    assert app_score == bf.score_line(gold, app)
    assert baseline_score == bf.score_line(gold, baseline)
    assert app_score.score == 0.75 and baseline_score.score == 0.25

    identical = bf.score_pair(gold, app, list(app))
    assert identical[0] == identical[1]


def test_the_baseline_is_scored_from_the_table_through_the_same_scorer():
    df = frame(
        [
            {"hieroglyphs": f"{A} {B}", "transliteration_gold": "pr nb"},
            {"hieroglyphs": f"{A} {B}", "transliteration_gold": "pr zꜣ"},
        ]
    )
    table = bf.build_table(df)
    gold_groups = [A, B, C]
    gold_readings = ["pr", "nb", "ḥm"]
    app = [["pr"], ["nb"], ["ḥm"]]
    app_score, baseline_score = bf.score_pair(
        gold_readings, app, table.predict_line(gold_groups)
    )
    assert app_score.score == 1.0 and app_score.success is True
    # B-freq has `pr` and `nb` in its top 3 but never attests C.
    assert baseline_score.group_hits == (True, True, False)
    assert baseline_score.score == pytest.approx(2 / 3)


def test_the_folded_scorer_does_not_punish_the_baseline_for_offering_a_key():
    """Regression, review of 2026-10-26: the secondary folded scorer was asymmetric.

    Corpus, app and gold all read the same word `n(.ꞽ).t`. B-freq used to offer its
    *identity key* `nꞽt`, from which the editorial apparatus has already been
    removed, while the app offers the spelling. The ASCII search fold treats the two
    differently — `search_fold("nꞽt") == "nit"` but `search_fold("n(.ꞽ).t") == "nt"`
    — so under the folded key the app scored 1 and B-freq 0 on identical material.
    That is an artefact of representation, not of reading Egyptian.

    B-freq now offers an attested spelling (`SURFACE_RULE`), so both sides fold the
    same kind of string.
    """
    from app.data.normalizer import search_fold
    from app.services.suggestions import strict_reading_key

    spelling = "n(.ꞽ).t"
    # The asymmetry in the underlying functions is real and is not what changed.
    assert search_fold(strict_reading_key(spelling)) != search_fold(spelling)

    df = frame([{"hieroglyphs": A, "transliteration_gold": spelling}] * 3)
    table = bf.build_table(df)
    assert table.top_keys(A) == [strict_reading_key(spelling)]
    assert table.top(A) == [spelling]

    gold = [spelling]
    app_candidates = [[spelling]]
    baseline_candidates = table.predict_line([A])

    for key in (bf.reading_key, bf.folded_reading_key):
        app_score, baseline_score = bf.score_pair(
            gold, app_candidates, baseline_candidates, key=key
        )
        assert app_score.hits == 1, key
        assert baseline_score.hits == 1, key  # used to be 0 under the folded key
        assert app_score == baseline_score, key


def test_the_strict_scorer_is_unchanged_by_offering_spellings():
    """The fix must not move the primary number: the spelling carries the identity."""
    df = frame(
        [
            {"hieroglyphs": A, "transliteration_gold": "n(.ꞽ).t"},
            {"hieroglyphs": A, "transliteration_gold": "n(.ꞽ).t"},
            {"hieroglyphs": B, "transliteration_gold": "[pr]"},
        ]
    )
    table = bf.build_table(df)
    for group in (A, B):
        offered, keys = table.top(group), table.top_keys(group)
        assert [bf.reading_key(item) for item in offered] == keys
    assert bf.score_line(["nꞽt", "pr"], table.predict_line([A, B])).hits == 2


# ---------------------------------------------------------------------------
# gold groups are counted and declared before anything is scored
# ---------------------------------------------------------------------------


def test_gold_groups_are_classified_before_scoring():
    report = bf.inspect_gold_groups([A, "<g>US9No2</g>", "", f"{B}{C}"])
    assert report.groups == 4
    assert report.scorable == 2
    assert report.placeholder_only == 1
    assert report.no_signs == 1
    assert report.unkeyable == 2
    assert report.placeholder_indices == (1,)
    assert report.no_signs_indices == (2,)
    assert report.kinds == (
        bf.GROUP_SCORABLE,
        bf.GROUP_PLACEHOLDER_ONLY,
        bf.GROUP_NO_SIGNS,
        bf.GROUP_SCORABLE,
    )
    assert "placeholder-only" in report.summary()


def test_an_unkeyable_gold_group_stays_in_the_denominator_as_a_baseline_miss():
    """The declared treatment: counted up front, never dropped after the fact."""
    assert "STAY in the denominator" in bf.PLACEHOLDER_GOLD_TREATMENT

    df = frame([{"hieroglyphs": f"{A} {B}", "transliteration_gold": "pr nb"}])
    table = bf.build_table(df)
    gold_groups = [A, "<g>US9No2</g>", B]
    gold_readings = ["pr", "ḥm", "nb"]
    app = [["pr"], ["ḥm"], ["nb"]]  # the app can read a placeholder group

    report, app_score, baseline_score = bf.score_endpoint_g(
        table, gold_groups, gold_readings, app
    )
    assert report.placeholder_only == 1 and report.placeholder_indices == (1,)
    assert app_score.groups == baseline_score.groups == 3  # denominator unchanged
    assert app_score.score == 1.0
    assert baseline_score.group_hits == (True, False, True)
    assert baseline_score.score == pytest.approx(2 / 3)


def test_score_endpoint_g_reports_before_it_scores_and_refuses_a_mismatch():
    df = frame([{"hieroglyphs": A, "transliteration_gold": "pr"}])
    table = bf.build_table(df)
    with pytest.raises(ValueError):
        bf.score_endpoint_g(table, [A, B], ["pr"], [["pr"], ["nb"]])

    report, app_score, baseline_score = bf.score_endpoint_g(
        table, [A], ["pr"], [None]
    )
    assert report.scorable == 1
    assert app_score.hits == 0  # the app did not produce the group
    assert baseline_score.hits == 1  # B-freq always gets the gold segmentation


# ---------------------------------------------------------------------------
# custody: the baseline never reads anything from a KRI path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "~/egyptology-private-kri/lines.csv",
        "/Users/someone/egyptology-private-kri/declaration.csv",
        "/Users/someone/kri/pages/KRI_II_120.csv",
        "/Users/someone/projects/Egyptology-APP/data/private/standrews.csv",
    ],
)
def test_a_kri_or_private_path_is_refused(path):
    with pytest.raises(bf.ForbiddenPathError):
        bf.assert_public_path(path)
    with pytest.raises(bf.ForbiddenPathError):
        bf.load_corpus(path)


def test_the_guard_does_not_trip_on_this_branch_or_the_public_corpus():
    """`kri-baseline-2026-10-26` and `docs/kri-bfreq-...md` must stay usable."""
    bf.assert_public_path(PROJECT_ROOT / "data" / "processed" / "examples.csv")
    bf.assert_public_path("/tmp/worktrees/kri-baseline-2026-10-26/data/processed/examples.csv")
    bf.assert_public_path("/tmp/docs/kri-bfreq-baseline-2026-10-26.md")


def test_the_guard_never_touches_the_custody_directory(monkeypatch):
    """Checking a KRI path must not stat, list or open it — purely lexical."""
    import os as os_module

    def forbidden(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("the guard touched the filesystem")

    monkeypatch.setattr(os_module.path, "realpath", forbidden)
    monkeypatch.setattr(os_module, "stat", forbidden)
    monkeypatch.setattr(os_module, "listdir", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    with pytest.raises(bf.ForbiddenPathError):
        bf.assert_public_path("~/egyptology-private-kri/lines.csv")


def test_the_builder_opens_only_the_files_it_was_given(tmp_path, monkeypatch):
    """Every path the build script reads or writes is recorded and inspected.

    This is the test that backs the sentence in
    `docs/kri-bfreq-baseline-2026-10-26.md`: building the frozen table reads the
    public corpus and the two source files, and nothing else.
    """
    corpus = tmp_path / "examples.csv"
    with open(corpus, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["hieroglyphs", "transliteration_gold", "language_stage"])
        writer.writerow([f"{A} {B}", "pr nb", "Earlier Egyptian"])
        writer.writerow([f"{A} {B}", "pr zꜣ", bf.LATE_EGYPTIAN])
        writer.writerow(["", "ḥm", bf.LATE_EGYPTIAN])

    opened: list[str] = []
    real_open = builtins.open
    real_read_csv = pd.read_csv

    def recording_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def recording_read_csv(path, *args, **kwargs):
        opened.append(str(path))
        return real_read_csv(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", recording_open)
    monkeypatch.setattr(pd, "read_csv", recording_read_csv)

    out_dir = tmp_path / "out"
    assert (
        build_script.main(
            ["--examples", str(corpus), "--out-dir", str(out_dir)]
        )
        == 0
    )

    monkeypatch.undo()
    assert opened, "nothing was recorded, so the test proves nothing"

    # Every recorded path passes the module's own guard …
    for path in opened:
        bf.assert_public_path(path)

    # … and the only files outside the checkout are the corpus it was given and the
    # output directory it was told to write.
    outside = {
        Path(path).resolve()
        for path in opened
        if PROJECT_ROOT not in Path(path).resolve().parents
    }
    allowed = {corpus.resolve()} | {p.resolve() for p in out_dir.iterdir()}
    assert outside <= allowed, outside - allowed
    assert corpus.resolve() in outside


# ---------------------------------------------------------------------------
# the build script
# ---------------------------------------------------------------------------


def test_the_build_script_writes_both_tables_and_a_header(tmp_path):
    corpus = tmp_path / "examples.csv"
    with open(corpus, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["hieroglyphs", "transliteration_gold", "language_stage"])
        writer.writerow([f"{A} {B}", "pr nb", "Earlier Egyptian"])
        writer.writerow([f"{A} {B}", "pr zꜣ", bf.LATE_EGYPTIAN])

    out_dir = tmp_path / "out"
    assert build_script.main(["--examples", str(corpus), "--out-dir", str(out_dir)]) == 0

    header = json.loads((out_dir / "bfreq_header.json").read_text(encoding="utf-8"))
    assert header["corpus_rows"] == 2
    assert header["tie_break_rule"] == bf.TIE_BREAK_RULE
    assert header["top_k"] == 3
    assert set(header["tables"]) == {"bfreq_table_all.csv", "bfreq_table_late_egyptian.csv"}
    assert (out_dir / "bfreq_header.txt").read_text(encoding="utf-8").strip()

    rows = list(csv.DictReader((out_dir / "bfreq_table_all.csv").read_text(encoding="utf-8").splitlines()))
    assert [r["sign_key"] for r in rows] == sorted(r["sign_key"] for r in rows)
    pr = [r for r in rows if r["sign_key"] == A]
    assert pr == [
        {"sign_key": A, "rank": "1", "reading_key": "pr", "count": "2", "surface_reading": "pr"}
    ]

    late = list(csv.DictReader((out_dir / "bfreq_table_late_egyptian.csv").read_text(encoding="utf-8").splitlines()))
    assert {r["reading_key"] for r in late} == {"pr", "zꜣ"}


def test_the_build_script_is_byte_reproducible(tmp_path):
    corpus = tmp_path / "examples.csv"
    with open(corpus, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["hieroglyphs", "transliteration_gold", "language_stage"])
        for reading in ("pr", "nb", "pr", "zꜣ"):
            writer.writerow([A, reading, bf.LATE_EGYPTIAN])

    first, second = tmp_path / "a", tmp_path / "b"
    build_script.main(["--examples", str(corpus), "--out-dir", str(first)])
    build_script.main(["--examples", str(corpus), "--out-dir", str(second)])
    for name in ("bfreq_table_all.csv", "bfreq_table_late_egyptian.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert build_script.sha256_file(first / name) == build_script.sha256_file(second / name)


def test_the_build_script_refuses_to_write_into_data_processed(tmp_path):
    corpus = tmp_path / "examples.csv"
    corpus.write_text("hieroglyphs,transliteration_gold,language_stage\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        build_script.main(
            ["--examples", str(corpus), "--out-dir", str(build_script.PROCESSED_DIR)]
        )


def test_the_build_script_refuses_a_kri_output_directory(tmp_path):
    corpus = tmp_path / "examples.csv"
    corpus.write_text("hieroglyphs,transliteration_gold,language_stage\n", encoding="utf-8")
    with pytest.raises(bf.ForbiddenPathError):
        build_script.main(
            ["--examples", str(corpus), "--out-dir", "~/egyptology-private-kri/out"]
        )

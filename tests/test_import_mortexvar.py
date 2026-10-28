"""The MORTEXVAR donor-file importer.

The data has no licence, so every string below is INVENTED in the database's format;
nothing here is copied from MORTEXVAR.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import REQUIRED_COLUMNS  # noqa: E402
from scripts import import_mortexvar as mv  # noqa: E402

DOCS = [
    {"witness": "B1X", "document": "B1X", "necropolis": "Siteone", "dating": "Sésostris I"},
    {"witness": "T2Y", "document": "T2Y", "necropolis": "Sitetwo", "dating": "Fin I P.I."},
    {"witness": "G3Z", "document": "G3Z", "necropolis": "Sitethree", "dating": "?"},
]
SPELLS = [{"spell_order": 1, "spell": "CT1", "head": "", "foot": "", "top": "", "back": "", "front": "", "bottom": "", "others": ""}]


def line(translit: str, witness: str = "B1X", translation: str = '"un texte"', spell: str = "CT9") -> dict:
    return {
        "spell": spell,
        "code_text": "I 001 a",
        "witness": witness,
        "transliteration": translit,
        "translation": translation,
        "analysis": "",
        "comments": "",
    }


def convert_lines(*records: dict):
    return mv.convert(list(records), DOCS, sha="ab" * 32)


def to_js_literal(array: list) -> str:
    """Encode JSON the way a bundler writes it: a JS single-quoted string."""
    text = json.dumps(array, ensure_ascii=False)
    return "JSON.parse('" + text.replace("\\", "\\\\").replace("'", "\\'") + "')"


# --- JS string literals -----------------------------------------------------


def test_js_literal_decodes_escaped_quote_and_backslash():
    assert mv.decode_js_string_literal(r"it\'s a \\ b") == "it's a \\ b"


def test_js_literal_decodes_unicode_hex_and_surrogate_pairs():
    assert mv.decode_js_string_literal(r"é\x41\u{1F600}") == "éA😀"
    assert mv.decode_js_string_literal(r"😀") == "😀"
    assert mv.decode_js_string_literal("a\\\nb") == "ab"  # line continuation


def test_bundle_roundtrip_with_quote_and_backslash_in_values():
    # A French apostrophe and a quoted translation survive JS-literal -> JSON decoding,
    # including the inner `\"` (a JSON-escaped quote) that the bundle really contains.
    lines = [line("n.k", translation='"d\'un homme \\ ici"')]
    bundle = (
        "x=1;" + to_js_literal(DOCS) + ";y=" + to_js_literal(SPELLS) + ";z=" + to_js_literal(lines) + ";"
    )
    tables = mv.split_tables(mv.extract_json_literals(bundle))
    assert len(tables.lines) == 1 and len(tables.spells) == 1 and len(tables.documents) == 3
    assert tables.lines[0]["translation"] == '"d\'un homme \\ ici"'


def test_split_tables_requires_all_three_arrays():
    with pytest.raises(SystemExit):
        mv.split_tables([DOCS, SPELLS])


# --- MdC conversion -----------------------------------------------------------


def test_the_six_laryngeal_and_fricative_letters_stay_distinct():
    out = mv.convert_transliteration("A a x X H h")
    assert out.split() == ["ꜣ", "ꜥ", "ḫ", "ẖ", "ḥ", "h"]
    assert len(set(out.split())) == 6


def test_other_letters_follow_the_ramses_mapping():
    assert mv.convert_transliteration("iw S T D z s y") == "ꞽw š ṯ ḏ z s y"


def test_o_is_this_databases_ascii_for_q():
    assert mv.convert_transliteration("sbo-oq") == "sbq-qq"


def test_name_placeholder_sign_name_and_digits_are_kept():
    assert mv.convert_transliteration("N nb zp 2 Z1") == "N nb zp 2 Z1"


# --- brackets -------------------------------------------------------------------


def test_restored_supplied_omitted_and_superfluous_markup_kept_verbatim():
    frame, report = convert_lines(line("[Dd-mdw in N] Sm.(w) <m> {pn}"))
    assert report.kept == 1
    assert frame.loc[0, "transliteration_gold"] == "[ḏd-mdw ꞽn N] šm.(w) <m> {pn}"


def test_attached_question_mark_is_kept_but_bare_question_mark_is_not():
    assert mv.classify_transliteration("wn(?) m r") == ""
    assert mv.classify_transliteration("wn ? m r") == "unread_token"


# --- exclusion rule ---------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, reason",
    [
        ("", "empty_transliteration"),
        ("   ", "empty_transliteration"),
        ("(...)", "lacuna_only"),
        ("? (...) ?", "lacuna_only"),
        ("[...] ?", "lacuna_only"),
        ("[]", "lacuna_only"),
        ("a// b", "lacuna_a35"),  # `//` inside a word, audit A35
        ("wn [] m", "lacuna_a35"),  # empty brackets
        ("wn [...] m", "lacuna_a35"),
        ("wn _ m", "lacuna_a35"),
        ("wn (...) m", "lacuna_paren"),
        ("wn.f(...) .w", "lacuna_paren"),
        ("wn ? m", "unread_token"),
        ("Axy (= Hxy) m", "editorial_gloss"),
        ("wn [m r] m", ""),
        ("imn.t [/ iAb.t]", ""),  # a lone slash is not a lacuna
    ],
)
def test_classify_transliteration(raw, reason):
    assert mv.classify_transliteration(raw) == reason


def test_summary_counts_every_exclusion_reason():
    frame, report = convert_lines(
        line("Dd-mdw in X"),
        line(""),
        line("(...)"),
        line("wn (...) m"),
        line("wn ? m"),
        line("a// b"),
        line("Axy (= Hxy)"),
        line("{m}"),  # only superfluous text: nothing left to search
        line("n.k"),
    )
    assert report.total == 9
    assert report.excluded["empty_transliteration"] == 1
    assert report.excluded["lacuna_only"] == 1
    assert report.excluded["lacuna_paren"] == 1
    assert report.excluded["unread_token"] == 1
    assert report.excluded["lacuna_a35"] == 1
    assert report.excluded["editorial_gloss"] == 1
    assert report.excluded["unsearchable"] == 1
    assert report.kept == len(frame) == 2
    tables = mv.Tables([line("x")], SPELLS, DOCS)
    summary = mv.build_summary(report, frame, tables, "ab" * 32, {})
    assert summary["rows_in"] == 9 and summary["rows_out"] == 2
    assert summary["excluded_total"] == 7
    assert sum(summary["excluded_by_reason"].values()) == 7
    assert set(summary["excluded_by_reason"]) == set(mv.EXCLUSION_REASONS)


# --- schema, period, witness ----------------------------------------------------------


def test_row_schema_and_fixed_columns():
    frame, _ = convert_lines(line("Dd-mdw in X", translation='"Parole de X"'))
    assert list(frame.columns) == REQUIRED_COLUMNS
    row = frame.iloc[0]
    assert row["source"] == "MORTEXVAR"
    assert row["language_stage"] == "Earlier Egyptian"
    assert row["hieroglyphs"] == "" and row["mdc"] == ""
    assert row["translation"] == "Parole de X"
    assert row["display_sequence"] == row["transliteration_gold"] == row["sign_sequence"]
    assert row["review_status"] == "seed"
    assert row["grammar_notes"].startswith("CT spell: CT9; de Buck: I 001 a; witness: B1X")
    assert "translation language: fr" in row["grammar_notes"]
    assert row["source_text_id"].startswith("MORTEXVAR_")


def test_period_comes_from_the_joined_document_else_unknown():
    frame, report = convert_lines(
        line("a", witness="B1X"), line("b", witness="T2Y"), line("c", witness="G3Z"), line("d", witness="Q9")
    )
    assert list(frame["period"]) == ["Middle Kingdom", "First Intermediate Period", "unknown", "unknown"]
    assert report.kept_without_document == 1
    assert report.kept_by_prefix["B"] == 1 and report.kept_by_prefix["Q"] == 1


@pytest.mark.parametrize(
    "dating, period",
    [
        ("Sésostris I", "Middle Kingdom"),
        ("Sésostris II ?", "Middle Kingdom"),
        ("Sésostris III", "Middle Kingdom"),
        ("Fin XI d. / Amenemhat I", "Middle Kingdom"),
        ("XI / XII dd.", "Middle Kingdom"),
        ("Moyen Empire", "Middle Kingdom"),
        ("Fin I P.I.", "First Intermediate Period"),
        ("XIII d.", "unknown"),
        ("Amenemhat II ou plus tard", "unknown"),
        ("Fin Ancien Empire ou I P.I.", "unknown"),
        ("?", "unknown"),
        ("", "unknown"),
        ("Inconnue", "unknown"),
    ],
)
def test_period_for_dating(dating, period):
    assert mv.period_for_dating(dating) == period


def test_conflicting_document_rows_make_the_witness_unknown():
    index = mv.build_witness_index(
        [
            {"witness": "W1", "necropolis": "A", "dating": "Sésostris I"},
            {"witness": "W1", "necropolis": "B", "dating": "Sésostris I"},
        ]
    )
    assert index["W1"].period == "unknown" and index["W1"].necropolis == ""


def test_witness_prefix():
    assert [mv.witness_prefix(w) for w in ["B3Bo", "Sq3Ca", "Pap.Gard.II", "", "T1L"]] == [
        "B", "Sq", "Pap", "(none)", "T",
    ]


def test_strip_translation_removes_only_the_surrounding_quotes():
    assert mv.strip_translation('"un "mot" ici"') == 'un "mot" ici'
    assert mv.strip_translation("") == ""


def test_ids_are_stable_and_sensitive_to_content():
    a = mv.content_id(1, "CT1", "I 001 a", "B1X", "ꞽw")
    assert a == mv.content_id(1, "CT1", "I 001 a", "B1X", "ꞽw")
    assert a != mv.content_id(2, "CT1", "I 001 a", "B1X", "ꞽw")
    assert a != mv.content_id(1, "CT1", "I 001 a", "B1X", "ꞽy")


def test_overlap_counts_new_and_known_tokens():
    import pandas as pd

    donor = pd.DataFrame({"transliteration_gold": ["ꞽw nb", "ꞽw zz"]})
    existing = pd.DataFrame({"transliteration_gold": ["ꞽw ḥr"], "language_stage": ["Earlier Egyptian"]})
    result = mv.overlap_report(donor, existing)["whole_corpus"]["word_level (search_fold tokens)"]
    assert result["donor_types"] == 3 and result["donor_types_new"] == 2
    assert result["donor_tokens"] == 4 and result["donor_tokens_new"] == 2


# --- refusals ----------------------------------------------------------------------------


def test_sha_mismatch_is_refused_and_match_accepted(tmp_path):
    bundle = tmp_path / "bundle.js"
    bundle.write_text("JSON.parse('[]')", encoding="utf-8")
    with pytest.raises(SystemExit, match="sha256"):
        mv.verify_sha256(bundle, mv.PINNED_SHA256)
    digest = mv.sha256_of(bundle)
    assert mv.verify_sha256(bundle, digest) == digest


def test_cli_refuses_a_wrong_bundle_before_reading_it(tmp_path):
    bundle = tmp_path / "bundle.js"
    bundle.write_text("not the bundle", encoding="utf-8")
    with pytest.raises(SystemExit, match="sha256"):
        mv.main(
            [str(bundle), "--output", str(tmp_path / "o.csv"), "--summary", str(tmp_path / "s.json"), "--existing", ""]
        )
    assert not (tmp_path / "o.csv").exists()


def test_cli_end_to_end_with_expect_sha_override(tmp_path):
    lines = [line("Dd-mdw in X"), line("(...)"), line("ra-oq")]
    bundle = tmp_path / "bundle.js"
    bundle.write_text(
        to_js_literal(DOCS) + ";" + to_js_literal(SPELLS) + ";" + to_js_literal(lines) + ";", encoding="utf-8"
    )
    out, summary = tmp_path / "donor.csv", tmp_path / "summary.json"
    mv.main(
        [str(bundle), "--output", str(out), "--summary", str(summary),
         "--expect-sha256", mv.sha256_of(bundle), "--existing", ""]
    )
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["rows_in"] == 3 and data["rows_out"] == 2
    assert data["excluded_by_reason"]["lacuna_only"] == 1
    assert out.exists()


def test_outputs_under_data_or_the_corpus_are_refused():
    with pytest.raises(SystemExit):
        mv.refuse_output_under_data(mv.DATA_DIR / "processed" / "x.csv")
    with pytest.raises(SystemExit):
        mv.refuse_unsafe_output(mv.EXAMPLES)
    mv.refuse_output_under_data(Path.home() / "egyptology-runs" / "x.csv")

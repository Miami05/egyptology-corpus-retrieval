"""UD_Egyptian-PC importer: Tübingen -> TLA mapping, surface tokens, row building.

The sample sentence is copied verbatim from `egy_pc-ud-train.conllu` (PT 1 §1b, Teti),
so the test pins the importer against real treebank content.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_ud_egyptian_pc import (  # noqa: E402
    build_row,
    classify_overlap,
    hiero_signs,
    hiero_unknown,
    parse_conllu,
    tuebingen_to_tla,
)

PT_1_1B = """# sent_id = PT_Sethe_1_1b_Teti
# title = PT
# edition = Sethe
# spell = 1
# section = 1b
# king = Teti
# TLA = IBUBd11TMVFFmkdXkKT53VyNhLQ
# text = mr.y (⸗ꞽ) pw ḥtp.n (⸗ꞽ) ḥr ⸗f
1\tmr.y\tmri̯\tVERB\t_\t_\t0\troot\t_\tHiero=𓌸𓇋𓇋|ID=400005
2\t(⸗ꞽ)\tꞽ\tPRON\t_\t_\t1\tnmod\t_\tHiero=No|ID=10030_Add
3\tpw\tpw\tDET\t_\t_\t1\tnsubj\t_\tHiero=𓊪𓅱|ID=59741
4\tḥtp.n\tḥtp\tVERB\t_\t_\t1\tacl:relcl\t_\tHiero=(𓊵:𓏏𓊪)𓈖|ID=111230
5\t(⸗ꞽ)\tꞽ\tPRON\t_\t_\t4\tnsubj\t_\tHiero=No|ID=10030_Add
6\tḥr\tḥr\tADP\t_\t_\t7\tcase\t_\tHiero=(𓁷:𓂋)|ID=400092
7\t⸗f\tf\tPRON\t_\t_\t4\tobl\t_\tHiero=𓆑|ID=10050

"""

MWT = """# sent_id = X_1
# spell = 9
# section = 1a
# king = Pepi
# edition = Sethe
# TLA = A; B
1\tḏ\tḏ\tVERB\t_\t_\t0\troot\t_\tHiero=𓆓|ID=1
2-3\tNfr-kꜣ\t_\t_\t_\t_\t_\t_\t_\tHiero=𓄤𓂓|ID=400330
2\tNfr\tnfr\tPROPN\t_\t_\t1\tobj\t_\tHiero=𓄤|ID=2
3\tkꜣ\tkꜣ\tPROPN\t_\t_\t2\tflat\t_\tHiero=𓂓|ID=3
4\t|\t|\tPUNCT\t_\t_\t1\tpunct\t_\tID=.|LINE=Punct
5\t[...]\t_\tX\t_\t_\t1\tdep\t_\tHiero=Lost

"""


def test_tuebingen_letters_map_to_tla_and_s_stays_distinct_from_sh() -> None:
    # s (𓊃) -> z, ś (𓋴) -> s: two signs, two letters, never merged.
    assert tuebingen_to_tla("s ś") == "z s"
    assert tuebingen_to_tla("č ṭ č̣ ḳ") == "ṯ d ḏ q"
    assert tuebingen_to_tla("śč̣m.n⸗f") == "sḏm.n=f"
    assert tuebingen_to_tla("ŚČ Č̣") == "SṮ Ḏ"


def test_unchanged_letters_pass_through() -> None:
    assert tuebingen_to_tla("ꜣꞽyꜥwbpfmnrhḥḫẖškgt") == "ꜣꞽyꜥwbpfmnrhḥḫẖškgt"


def test_notation_marks() -> None:
    assert tuebingen_to_tla("˹m˺") == "⸢m⸣"
    assert tuebingen_to_tla("H̠nm.w") == "H̱nm.w"


def test_hiero_signs_drops_grouping() -> None:
    assert hiero_signs("(𓊵:𓏏𓊪)𓈖") == "𓊵𓏏𓊪𓈖"
    assert hiero_signs("UC_No") == ""


def test_unwritten_suffix_is_glued_and_row_is_aligned() -> None:
    (sentence,) = parse_conllu(PT_1_1B)
    row = build_row(sentence, "train")
    assert row["transliteration_gold"] == "mr.y(=ꞽ) pw ḥtp.n(=ꞽ) ḥr =f"
    assert row["hieroglyphs"] == "𓌸𓇋𓇋 𓊪𓅱 𓊵𓏏𓊪𓈖 𓁷𓂋 𓆑"
    assert len(row["hieroglyphs"].split()) == len(row["transliteration_gold"].split())
    assert row["lemma_sequence"].split()[1] == "10030|(=ꞽ)"
    assert row["citation"] == "PT 1 §1b (Teti; Sethe ed.)"
    assert row["tla_sentence_ids"] == "IBUBd11TMVFFmkdXkKT53VyNhLQ"
    assert row["aligned"] == "True"


def test_multiword_range_punct_and_lacuna() -> None:
    (sentence,) = parse_conllu(MWT)
    row = build_row(sentence, "dev")
    # range line is the surface word; `|` dropped; `[...]` flags a lacuna
    assert row["transliteration_gold"] == "ḏ Nfr-kꜣ [...]"
    assert row["has_lacuna"] == "True"
    assert row["aligned"] == "False" and row["hieroglyphs"] == ""
    assert row["tla_sentence_ids"] == "A;B"


def test_overlap_classes() -> None:
    (sentence,) = parse_conllu(PT_1_1B)
    rows = [build_row(sentence, "train") for _ in range(3)]
    rows[1]["transliteration_gold"] = "zzz yyy"
    rows[2]["transliteration_gold"] = "ḥtp.n(=ꞽ) ḥr"
    corpus = pd.DataFrame(
        {
            "source": ["TLA", "AES"],
            "source_ref": ["x", "AES/x#text=T&sentence=OTHER"],
            "transliteration_gold": ["mr.y(=ꞽ) pw ḥtp.n(=ꞽ) ḥr =f", "ꞽw ḥtp.n ḥr =f m ḥtp"],
        }
    )
    classify_overlap(rows, corpus)
    assert [r["overlap_status"] for r in rows] == [
        "duplicate_strict", "unmatched_by_current_rules", "overlap_partial",
    ]
    assert "net_new" not in {r["overlap_status"] for r in rows}
    assert [r["repeated_in_candidates"] for r in rows] == ["False", "False", "False"]



# PT 262 §334b (Teti), verbatim from egy_pc-ud-train.conllu: `<m>` is a whole word the
# editor supplies (Hiero=No, ID=…_Emend), not a suffix.
PT_262_334B = """# sent_id = PT_Sethe_262_334b_Teti_(1)
# edition = Sethe
# spell = 262
# section = 334b
# king = Teti
# TLA = No
1\tč̣ꜣ.n\tč̣ꜣi̯\tVERB\t_\t_\t0\troot\t_\tHiero=𓍒𓄿(𔀟:𓈖)|Hierocl=𔀟|ID=181780
2\tTtꞽ\tTtꞽ\tPROPN\t_\t_\t1\tnsubj\t_\tHiero=𓍹(𓏏:𓏏)𓇋𓍺|ID=450656
3\t<m>\tm\tADP\t_\t_\t4\tcase\t_\tHiero=No|ID=400007_Emend
4\tmẖn.t\tmẖn.t\tNOUN\t_\t_\t1\tobl\t_\tHiero=𓅓(𓄡:𓈖:𓏏)|ID=74610
5\twr.t\twr\tADJ\t_\t_\t4\tamod\t_\tHiero=(𓅨:𓂋:𓏏)|ID=47271

"""

# Restored whole word `[mṭw]` and restored / omitted suffixes `[⸗k]`, `<⸗f>` (shapes
# as in the treebank; Hiero=No on all three).
RESTORED = """# sent_id = R_1
# edition = Sethe
# spell = 1
# section = 1a
# king = Unas
# TLA = No
1\tč̣ṭ\tč̣ṭ\tVERB\t_\t_\t0\troot\t_\tHiero=𓆓𓂧|ID=185810
2\t[⸗k]\tk\tPRON\t_\t_\t1\tnsubj\t_\tHiero=No|ID=10110_Rest
3\t[mṭw]\tmṭw\tNOUN\t_\t_\t1\tobj\t_\tHiero=No|ID=78140_Rest
4\t<⸗f>\tf\tPRON\t_\t_\t3\tnmod\t_\tHiero=No|ID=10050_Add

"""

# PT 437 §808a (Pepi), the first four tokens verbatim: `wč̣b` has an unknown sign.
PT_437_808A = """# sent_id = PT_Sethe_437_808a-b_Pepi
# edition = Sethe
# spell = 437
# section = 808a-b
# king = Pepi
# TLA = IBUBd1TXFb49Ukgwv3c79WGBqx4
1\tšmś\tšmś\tVERB\t_\t_\t0\troot\t_\tHiero=𓈙𓌞𓋴|ID=155000
2\tčw\tčw\tPRON\t_\t_\t1\tobj\t_\tHiero=𓍿𓅱|ID=174900
3\tꞽꜣm\tꞽꜣm\tNOUN\t_\t_\t1\tnsubj\t_\tHiero=𓇋𓄿𓌳𓅓𓆭|Hierocl=𓆭|ID=24810
4\twč̣b\twč̣b\tVERB\t_\t_\t1\tconj\t_\tHiero=𓎗𓃀UC_No𓃀|Hierocl=UC_No|ID=52620

"""


def test_supplied_whole_word_is_not_glued_and_row_is_not_aligned() -> None:
    (sentence,) = parse_conllu(PT_262_334B)
    row = build_row(sentence, "train")
    assert row["transliteration_gold"] == "ḏꜣ.n Ttꞽ <m> mẖn.t wr.t"  # not "Ttꞽ<m>"
    assert row["aligned"] == "False" and row["hieroglyphs"] == ""
    assert row["alignment_issue"] == "unwritten_word;no_signs"
    assert row["glyphs_incomplete"] == "False"


def test_restored_word_separate_and_supplied_suffixes_glued() -> None:
    (sentence,) = parse_conllu(RESTORED)
    row = build_row(sentence, "train")
    assert row["transliteration_gold"] == "ḏd[=k] [mdw]<=f>"
    assert row["aligned"] == "False" and "unwritten_word" in row["alignment_issue"]


def test_supplied_suffixes_alone_keep_the_row_aligned() -> None:
    (sentence,) = parse_conllu(PT_1_1B)
    row = build_row(sentence, "train")
    assert row["alignment_issue"] == "" and row["aligned"] == "True"


def test_unknown_sign_marker_is_detected_before_stripping() -> None:
    assert hiero_unknown("𓎗𓃀UC_No𓃀") == "UC_No"
    assert hiero_unknown("(𓂋:139CA)") == "139CA"
    assert hiero_unknown("[...](𓂝:𓂋)") == "..."
    assert hiero_unknown("Lost") == "Lost"
    # notation and a run-on next key are not unknown signs
    assert hiero_unknown("˹𓇋(𓈙:𓏏)˺{𓈖}<𓎡>𓂘_FE02 $𓋳$") == ""
    assert hiero_unknown("𓆑ID=10050") == ""
    assert hiero_signs("[(𓂋:𓏤)]Hierocl=𓏤") == "𓂋𓏤"


def test_unknown_sign_row_is_flagged_and_not_aligned() -> None:
    (sentence,) = parse_conllu(PT_437_808A)
    row = build_row(sentence, "train")
    assert row["glyphs_incomplete"] == "True"
    assert row["alignment_issue"] == "unknown_sign"
    assert row["aligned"] == "False" and row["hieroglyphs"] == ""


def test_glyph_lemma_and_repeat_flags() -> None:
    (sentence,) = parse_conllu(PT_1_1B)
    rows = [build_row(sentence, "train") for _ in range(2)]
    rows[1]["transliteration_gold"] = "zzz yyy"
    corpus = pd.DataFrame(
        {
            "source": ["TLA"],
            "source_ref": ["x"],
            "transliteration_gold": ["something else entirely"],
            # same signs, different spacing and a layout control
            "hieroglyphs": ["𓌸𓇋 𓇋𓊪𓅱 𓊵\U00013430𓏏𓊪𓈖 𓁷𓂋𓆑"],
            "lemma_sequence": ["400005|mr 10030|=ꞽ 59741|pw 111230|ḥtp 10030|=ꞽ 400092|ḥr 10050|=f"],
        }
    )
    classify_overlap(rows, corpus)
    assert [r["overlap_status"] for r in rows] == ["unmatched_by_current_rules"] * 2
    assert [r["glyph_overlap"] for r in rows] == ["True", "True"]
    assert [r["lemma_overlap"] for r in rows] == ["True", "True"]
    assert [r["repeated_in_candidates"] for r in rows] == ["False", "False"]
    rows[1]["transliteration_gold"] = rows[0]["transliteration_gold"]
    classify_overlap(rows, corpus)
    assert [r["repeated_in_candidates"] for r in rows] == ["True", "True"]

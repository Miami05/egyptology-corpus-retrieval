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
    assert [r["overlap_status"] for r in rows] == ["duplicate_strict", "net_new", "overlap_partial"]

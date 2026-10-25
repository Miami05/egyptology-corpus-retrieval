"""ORAEC metadata linker: record parsing, AES text-id link, unique BBAW sentence link.

The record below is cut down from `oraec1.json` (Piye stela) with its real field shapes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_oraec_metadata import build, parse_text  # noqa: E402

AED = "66ATQAWY55BNBFZYHSRGQK5RG4"


def record(aed: str, words: list[list[str]]) -> dict:
    return {
        "title": "Textfeld / Siegesstele des Piye",
        "date": [{"date": "Pije", "id": "X"}],
        "origplace": [{"origplace": "Gebel Barkal", "id": "Y"}],
        "location": [{"location": "Egyptian Museum", "id": "Z"}],
        "idno": ["JE 48862", "JE 48862"],
        "bibliography": "- Urk. III, 1-56 [H]",
        "sentences": [{"token": [{"written_form": w} for w in s]} for s in words],
        "credits": {
            "license": "cc-by-sa-4.0",
            "author": "Silke Grallert",
            "source": ["https://github.com/simondschweitzer/aes",
                       f"https://github.com/simondschweitzer/aed-tei/blob/master/files/{aed}.xml"],
        },
    }


def test_parse_text_fields() -> None:
    t = parse_text("oraec1", record(AED, []))
    assert t["aed_text_id"] == AED
    assert t["idno"] == "JE 48862"  # duplicates collapsed
    assert t["origplace"] == "Gebel Barkal"
    assert t["text_licence"] == "CC BY-SA 4.0"
    assert "oraec1.json" in t["text_provenance"]


def test_build_links_aes_by_text_id_and_bbaw_only_when_unique(tmp_path: Path) -> None:
    other = "A" * 26
    (tmp_path / "oraec1.json").write_text(json.dumps({"oraec1": record(AED, [["ḏd", "mdw"], ["nb≡f", "jr,t"]])}))
    (tmp_path / "oraec2.json").write_text(json.dumps({"oraec2": record(other, [["ḏd", "mdw"]])}))
    (tmp_path / "mapping_oraec_trismegistos.csv").write_text("ORAEC,Trismegistos Text\noraec1,123\n")
    (tmp_path / "oraec_hierarchical_path.tsv").write_text("oraec1\tA→B\t<a>A</a>\n")
    corpus = pd.DataFrame(
        {
            "source": ["AES", "AES", "BBAW", "BBAW"],
            "source_sentence_id": ["s1", "s2", "B1", "B2"],
            "source_ref": [f"AES/x#text={AED}&sentence=I1", f"AES/x#text={AED}&sentence=I2", "bbaw", "bbaw"],
            "transliteration_gold": ["x", "y", "nb=f ꞽr.t", "ḏd mdw"],
        }
    )
    meta, links, stats = build(tmp_path, corpus)
    assert stats["aes_rows_linked"] == 2
    # "nb=f ꞽr.t" belongs to oraec1 only; "ḏd mdw" is in both texts -> ambiguous
    assert links["source_sentence_id"].tolist() == ["B1"]
    assert links["oraec_id"].tolist() == ["oraec1"]
    assert stats["bbaw_rows_ambiguous"] == 1
    row = meta.set_index("oraec_id").loc["oraec1"]
    assert row["trismegistos_id"] == "123" and row["trismegistos_licence"] == "CC0 1.0"
    assert row["hierarchical_path"] == "A→B"
    assert int(row["aes_rows_linked"]) == 2 and int(row["bbaw_rows_linked"]) == 1
    assert "oraec2" not in set(meta["oraec_id"])

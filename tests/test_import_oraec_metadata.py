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


def record(aed: str, words: list[list[str]], translations: list[str] | None = None) -> dict:
    translations = translations or [""] * len(words)
    return {
        "title": "Textfeld / Siegesstele des Piye",
        "date": [{"date": "Pije", "id": "X"}],
        "origplace": [{"origplace": "Gebel Barkal", "id": "Y"}],
        "location": [{"location": "Egyptian Museum", "id": "Z"}],
        "idno": ["JE 48862", "JE 48862"],
        "bibliography": "- Urk. III, 1-56 [H]",
        "sentences": [{"token": [{"written_form": w} for w in s], "translation": t}
                      for s, t in zip(words, translations)],
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


def write_raw(tmp_path: Path, texts: dict[str, dict]) -> None:
    for oid, rec in texts.items():
        (tmp_path / f"{oid}.json").write_text(json.dumps({oid: rec}))
    (tmp_path / "mapping_oraec_trismegistos.csv").write_text("ORAEC,Trismegistos Text\noraec1,123\n")
    (tmp_path / "oraec_hierarchical_path.tsv").write_text("oraec1\tA→B\t<a>A</a>\n")


def test_build_links_aes_by_text_id_and_bbaw_only_when_unique(tmp_path: Path) -> None:
    other = "A" * 26
    write_raw(tmp_path, {
        "oraec1": record(AED, [["ḏd", "mdw"], ["nb≡f", "jr,t", "nfr"]], ["Recitation.", "His  lord made good."]),
        "oraec2": record(other, [["ḏd", "mdw"]], ["Recitation."]),
    })
    corpus = pd.DataFrame(
        {
            "source": ["AES", "AES", "BBAW", "BBAW"],
            "source_sentence_id": ["s1", "s2", "B1", "B2"],
            "source_ref": [f"AES/x#text={AED}&sentence=I1", f"AES/x#text={AED}&sentence=I2", "bbaw", "bbaw"],
            "transliteration_gold": ["x", "y", "nb=f ꞽr.t nfr", "ḏd mdw"],
            "translation": ["", "", "His lord made  good. ", "Recitation."],
        }
    )
    meta, links, candidates, stats = build(tmp_path, corpus)
    assert stats["aes_rows_linked"] == 2
    # "nb=f ꞽr.t nfr" belongs to oraec1 only, 3 words, translation equal up to whitespace
    assert links["source_sentence_id"].tolist() == ["B1"]
    assert links["oraec_id"].tolist() == ["oraec1"]
    assert links["link_status"].tolist() == ["accepted"]
    # "ḏd mdw" is in both texts -> ambiguous, neither a link nor a candidate
    assert stats["bbaw_rows_ambiguous"] == 1 and candidates.empty
    row = meta.set_index("oraec_id").loc["oraec1"]
    assert row["trismegistos_id"] == "123" and row["trismegistos_licence"] == "CC0 1.0"
    assert row["hierarchical_path"] == "A→B"
    assert int(row["aes_rows_linked"]) == 2 and int(row["bbaw_rows_linked"]) == 1
    assert "oraec2" not in set(meta["oraec_id"])


def test_short_unique_key_is_a_review_candidate_not_a_link(tmp_path: Path) -> None:
    # B027251 "zꜣ.t =f" / "His daughter Neferut.": the BBAW row lost the name, so its
    # two-word key is unique to the wrong text (oraec7120); the sentence is in oraec316.
    write_raw(tmp_path, {
        "oraec316": record("B" * 26, [["zꜣ,t≡f", "nfr,wt"]], ["His daughter Neferut."]),
        "oraec7120": record("C" * 26, [["zꜣ,t≡f"]], ["his daughter"]),
    })
    corpus = pd.DataFrame({
        "source": ["BBAW"], "source_sentence_id": ["B027251"], "source_ref": ["bbaw"],
        "transliteration_gold": ["zꜣ.t =f"], "translation": ["His daughter Neferut."],
    })
    meta, links, candidates, stats = build(tmp_path, corpus)
    assert links.empty and meta.empty
    assert candidates[["source_sentence_id", "oraec_id", "link_status", "translation_match"]].values.tolist() == [
        ["B027251", "oraec7120", "review_short_key", "False"]
    ]
    assert stats["bbaw_rows_linked_accepted"] == 0 and stats["bbaw_rows_review_short_key"] == 1


def test_translation_disagreement_is_quarantined(tmp_path: Path) -> None:
    write_raw(tmp_path, {"oraec1": record(AED, [["nb≡f", "jr,t", "nfr"]], ["His lord made good."])})
    corpus = pd.DataFrame({
        "source": ["BBAW", "BBAW"], "source_sentence_id": ["B1", "B2"], "source_ref": ["bbaw", "bbaw"],
        "transliteration_gold": ["nb=f ꞽr.t nfr", "nb=f ꞽr.t nfr"],
        "translation": ["Something else entirely.", ""],
    })
    meta, links, candidates, stats = build(tmp_path, corpus)
    assert links.empty
    assert candidates["link_status"].tolist() == ["quarantine_translation_mismatch", "review_no_translation"]
    assert stats["bbaw_rows_quarantine_translation_mismatch"] == 1


def test_limited_run_proposes_no_links(tmp_path: Path) -> None:
    """--limit drops files before uniqueness is judged, so a sentence shared with a
    skipped file would look unique. A partial run must not propose links."""
    write_raw(tmp_path, {
        "oraec1": record(AED, [["nb≡f", "jr,t", "nfr"]], ["His lord made good."]),
        "oraec2": record("A" * 26, [["nb≡f", "jr,t", "nfr"]], ["His lord made good."]),
    })
    corpus = pd.DataFrame({
        "source": ["BBAW"], "source_sentence_id": ["B1"], "source_ref": ["bbaw"],
        "transliteration_gold": ["nb=f ꞽr.t nfr"], "translation": ["His lord made good."],
    })
    _, full_links, _, full_stats = build(tmp_path, corpus)
    assert full_links.empty and full_stats["bbaw_rows_ambiguous"] == 1
    _, links, candidates, _ = build(tmp_path, corpus, limit=1)
    assert links.empty and candidates.empty


def test_main_refuses_output_collisions(tmp_path: Path, monkeypatch) -> None:
    import pytest

    from scripts import import_oraec_metadata as mod

    examples = tmp_path / "examples.csv"
    examples.write_text("source\n", encoding="utf-8")
    monkeypatch.setattr(mod, "build", lambda *a, **k: (_ for _ in ()).throw(AssertionError("built")))
    cases = [
        ["--output", str(examples)],
        ["--output", str(tmp_path / "m.csv"), "--bbaw-links", str(tmp_path / "m.csv")],
        ["--output", str(tmp_path / "m.csv"), "--bbaw-link-candidates", str(examples)],
    ]
    for extra in cases:
        monkeypatch.setattr(sys, "argv", ["x", "--raw-dir", str(tmp_path), "--examples", str(examples), *extra])
        with pytest.raises(SystemExit) as info:
            mod.main()
        assert "refusing" in str(info.value) or "different files" in str(info.value)
    assert examples.read_text(encoding="utf-8") == "source\n"

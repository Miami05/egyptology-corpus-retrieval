"""Wikidata lemma glosses: offline build from saved SPARQL bindings (no network)."""

from __future__ import annotations

import collections
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.fetch_wikidata_lemma_glosses import build  # noqa: E402

WD = "http://www.wikidata.org/entity/"


def binding(lex: str, tla: str, lemma: str, sense: str | None = None, gloss: str | None = None) -> dict:
    b = {"lexeme": {"value": WD + lex}, "tla": {"value": tla}, "lemma": {"value": lemma}}
    if sense:
        b["sense"] = {"value": WD + sense}
        b["gloss"] = {"value": gloss}
    return b


def test_build_groups_senses_and_skips_unglossed() -> None:
    bindings = [
        binding("L1381981", "5", "ꜣ.t", "L1381981-S1", "moment"),
        binding("L1381981", "5", "ꜣ.t", "L1381981-S2", "instant"),
        binding("L9", "77", "x"),  # lexeme without an English gloss
    ]
    df = build(bindings, collections.Counter({"5": 52}), "2026-10-25")
    assert df["tla_lemma_id"].tolist() == ["5"]
    row = df.iloc[0]
    assert row["gloss_en"] == "moment | instant"
    assert row["sense_ids"] == "L1381981-S1 | L1381981-S2"
    assert row["in_corpus"] == "True" and row["corpus_rows"] == 52
    assert row["licence"] == "CC0 1.0" and "L1381981" in row["source"]

"""Wikidata lemma glosses: offline build from saved SPARQL bindings (no network)."""

from __future__ import annotations

import collections
import io
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.fetch_wikidata_lemma_glosses as wd  # noqa: E402
from scripts.fetch_wikidata_lemma_glosses import build, fetch, load_bindings  # noqa: E402

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


def fake_endpoint(monkeypatch: pytest.MonkeyPatch, page_sizes: list[int]) -> None:
    """Serve `page_sizes[i]` bindings for page i; no network, no sleeping."""
    monkeypatch.setattr(wd, "PAGE", 2)
    monkeypatch.setattr(wd.time, "sleep", lambda _s: None)
    calls = iter(page_sizes)

    def urlopen(_req, timeout=0):  # noqa: ARG001
        n = next(calls)
        body = {"results": {"bindings": [binding(f"L{i}", str(i), "x") for i in range(n)]}}
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(wd.urllib.request, "urlopen", urlopen)


def test_refetch_with_fewer_pages_ignores_stale_pages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_endpoint(monkeypatch, [2, 2, 1])  # first fetch: three pages
    fetch(tmp_path)
    assert len(load_bindings(tmp_path)[0]) == 5
    fake_endpoint(monkeypatch, [1])  # later fetch: the result shrank to one page
    fetch(tmp_path)
    bindings, retrieved = load_bindings(tmp_path)
    assert len(bindings) == 1 and retrieved
    assert sorted(p.name for p in tmp_path.glob("page_*.json")) == ["page_00.json"]


def test_stale_page_beside_a_manifest_is_not_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_endpoint(monkeypatch, [1])
    fetch(tmp_path)
    stale = {"results": {"bindings": [binding("L9", "9", "x")] * 3}}
    (tmp_path / "page_05.json").write_text(json.dumps(stale))
    assert len(load_bindings(tmp_path)[0]) == 1


def test_build_refuses_without_a_completed_fetch(tmp_path: Path) -> None:
    (tmp_path / "page_00.json").write_text(json.dumps({"results": {"bindings": []}}))
    with pytest.raises(SystemExit):
        load_bindings(tmp_path)

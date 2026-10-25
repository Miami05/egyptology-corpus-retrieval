"""Audit batch "pipeline" (findings A6 A7 A8 A10 A32 A33 A34 A35 A36 A37 A38).

The importers used to destroy data with their default arguments (A6, A7, A8), label
rows with facts the sources do not state (A10, A34), keep broken readings (A35), drop
the date range and editors (A33), and download unpinned data (A37). Every test here
runs on small tmp fixtures; none touches data/processed, data/private or data/raw.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
import types
import zipfile
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import REQUIRED_COLUMNS  # noqa: E402
from scripts import (  # noqa: E402
    build_examples_from_real,
    import_aes_relannis,
    import_bbaw_egyptian,
    import_helsinki_lexicon,
    import_ramses,
    import_tla_dataset,
)
from scripts.import_bbaw_egyptian import (  # noqa: E402
    TRANSLIT_LACUNA_RE,
    refuse_unsafe_output,
)

PRIVATE_DIR = PROJECT_ROOT / "data" / "private"
EXAMPLES = PROJECT_ROOT / "data" / "processed" / "examples.csv"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def listing(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) if root.exists() else []


# --- shared guard (supports A6, A7, A8) ---------------------------------------------


def test_refuse_unsafe_output_rejects_the_corpus_the_private_dir_and_existing(tmp_path):
    for bad in (EXAMPLES, PRIVATE_DIR / "x.csv", PRIVATE_DIR / "sub" / "x.csv"):
        with pytest.raises(SystemExit):
            refuse_unsafe_output(bad, tmp_path / "other.csv")
    same = tmp_path / "corpus.csv"
    with pytest.raises(SystemExit):
        refuse_unsafe_output(same, same)
    assert not (PRIVATE_DIR / "x.csv").exists()


def test_refuse_unsafe_output_accepts_a_scratch_file(tmp_path):
    refuse_unsafe_output(tmp_path / "scratch.csv", tmp_path / "corpus.csv")
    refuse_unsafe_output(tmp_path / "scratch.csv")


def test_allow_corpus_still_refuses_the_private_dir():
    refuse_unsafe_output(EXAMPLES, allow_corpus=True)
    with pytest.raises(SystemExit):
        refuse_unsafe_output(PRIVATE_DIR / "x.csv", allow_corpus=True)


# --- A7: TLA importer must not truncate its own worklist ----------------------------


def _write_worklist(path: Path, rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {column: [""] * rows for column in import_tla_dataset.FINAL_COLUMNS}
    )
    frame["source"] = "TLA"
    frame["source_text_id"] = [f"TLA_EARLIER_{i:03d}" for i in range(rows)]
    frame.to_csv(path, index=False)


def _tla_parquet(path: Path, rows: int = 5, **extra) -> Path:
    data = {
        "hieroglyphs": ["𓊵𓏙"] * rows,
        "transliteration": [f"ḥtp{i}" for i in range(rows)],
        "translation": ["peace"] * rows,
        "lemmatization": [""] * rows,
        "UPOS": [""] * rows,
        "glossing": [""] * rows,
        "dateNotBefore": ["-2000"] * rows,
        "dateNotAfter": ["-1900"] * rows,
    }
    data.update({key: [value] * rows for key, value in extra.items()})
    pd.DataFrame(data).to_parquet(path, index=False)
    return path


def test_tla_importer_with_no_arguments_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    worklist = tmp_path / "data" / "raw" / "real_examples_worklist.csv"
    _write_worklist(worklist, 300)
    before = sha(worklist)
    monkeypatch.setattr(sys, "argv", ["import_tla_dataset.py"])
    with pytest.raises(SystemExit):
        import_tla_dataset.main()
    assert sha(worklist) == before


def test_tla_importer_will_not_shrink_an_existing_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    worklist = tmp_path / "data" / "raw" / "real_examples_worklist.csv"
    _write_worklist(worklist, 300)
    before = sha(worklist)
    source = _tla_parquet(tmp_path / "tiny.parquet")
    argv = ["x", "--input", str(source), "--output", str(worklist), "--limit", "5"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        import_tla_dataset.main()
    assert sha(worklist) == before

    monkeypatch.setattr(sys, "argv", argv + ["--force"])
    import_tla_dataset.main()
    assert len(pd.read_csv(worklist)) == 5


def test_tla_importer_refuses_the_corpus_as_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = _tla_parquet(tmp_path / "tiny.parquet")
    monkeypatch.setattr(
        sys, "argv", ["x", "--input", str(source), "--output", str(EXAMPLES), "--force"]
    )
    with pytest.raises(SystemExit):
        import_tla_dataset.main()


def test_tla_missing_dataset_path_fails_loudly_instead_of_falling_back(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    worklist = tmp_path / "data" / "raw" / "real_examples_worklist.csv"
    _write_worklist(worklist, 30)
    before = sha(worklist)
    monkeypatch.setattr(
        sys, "argv", ["x", "--dataset-path", "no/such/folder", "--output", str(worklist)]
    )
    with pytest.raises(FileNotFoundError):
        import_tla_dataset.main()
    assert sha(worklist) == before
    assert not hasattr(import_tla_dataset, "_load_fallback_worklist")


# --- A8: build_examples_from_real must not replace a multi-source corpus ------------


def _worklist_rows(n: int, genre: str = "g", period: str = "p") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": ["TLA"] * n,
            "source_text_id": [f"T{i}" for i in range(n)],
            "source_sentence_id": [f"S{i}" for i in range(n)],
            "genre": [genre] * n,
            "period": [period] * n,
            "mdc": ["m"] * n,
            "sign_sequence": ["s"] * n,
            "transliteration_gold": [f"ḥtp{i}" for i in range(n)],
        }
    )


def test_build_defaults_no_longer_invent_a_genre_or_period():
    frame = _worklist_rows(1, genre="", period="")
    out = build_examples_from_real._normalize_defaults(frame)
    assert out.loc[0, "genre"] == "unknown"
    assert out.loc[0, "period"] == "unknown"
    assert out.loc[0, "review_status"] == "seed"


def test_build_keeps_a_row_that_only_lacked_a_genre(tmp_path):
    worklist = tmp_path / "w.csv"
    _worklist_rows(2, genre="").to_csv(worklist, index=False)
    out = tmp_path / "out.csv"
    build_examples_from_real.main(["--input", str(worklist), "--output", str(out)])
    written = pd.read_csv(out, dtype=str, keep_default_na=False)
    assert len(written) == 2
    assert set(written["genre"]) == {"unknown"}


def test_build_refuses_to_overwrite_a_multi_source_corpus(tmp_path):
    worklist = tmp_path / "w.csv"
    _worklist_rows(3).to_csv(worklist, index=False)
    corpus = tmp_path / "examples.csv"
    existing = pd.concat([_worklist_rows(3), _worklist_rows(2).assign(source="BBAW")])
    existing.to_csv(corpus, index=False)
    before = sha(corpus)
    with pytest.raises(SystemExit):
        build_examples_from_real.main(["--input", str(worklist), "--output", str(corpus)])
    assert sha(corpus) == before
    build_examples_from_real.main(
        ["--input", str(worklist), "--output", str(corpus), "--force"]
    )
    assert len(pd.read_csv(corpus)) == 3


def test_build_requires_an_output_and_writes_to_a_fresh_path(tmp_path):
    worklist = tmp_path / "w.csv"
    _worklist_rows(3).to_csv(worklist, index=False)
    with pytest.raises(SystemExit):
        build_examples_from_real.main(["--input", str(worklist)])
    fresh = tmp_path / "new" / "examples.csv"
    build_examples_from_real.main(["--input", str(worklist), "--output", str(fresh)])
    assert len(pd.read_csv(fresh)) == 3


def test_build_refuses_the_private_dir():
    with pytest.raises(SystemExit):
        build_examples_from_real.main(["--output", str(PRIVATE_DIR / "x.csv")])
    assert not (PRIVATE_DIR / "x.csv").exists()


# --- A6 / A10 / A35: Ramses ---------------------------------------------------------


def _ramses_raw(directory: Path, lines: list[tuple[list[str], str]]) -> Path:
    """One `train` split: (words of the transliteration, src-sep line) per sentence."""
    directory.mkdir(parents=True, exist_ok=True)
    tgt = [" ".join("_".join(words) + "_") for words, _ in lines]
    sep = [line for _, line in lines]
    (directory / "tgt-train.txt").write_text("\n".join(tgt) + "\n", encoding="utf-8")
    (directory / "src-sep-train.txt").write_text("\n".join(sep) + "\n", encoding="utf-8")
    (directory / "src-train.txt").write_text("\n".join(sep) + "\n", encoding="utf-8")
    return directory


RAMSES_LINES = [
    (["iw", "iw"], "M17 Z7 _ M17 Z7 _"),
    (["imn-m-//"], "M17 _"),
    (["iw", "hr-[...]"], "M17 _ D2 _"),
    (["iw", "[]-nxt"], "M17 _ D2 _"),
    (["r", "1/2"], "D21 _ Z1 _"),
]


def test_ramses_without_output_writes_nothing(tmp_path, monkeypatch):
    raw = _ramses_raw(tmp_path / "raw", RAMSES_LINES)
    monkeypatch.chdir(tmp_path)
    before_tmp = listing(tmp_path)
    before_private = listing(PRIVATE_DIR)
    monkeypatch.setattr(
        sys, "argv", ["x", "--raw-dir", str(raw), "--splits", "train", "--existing", ""]
    )
    import_ramses.main()
    assert listing(tmp_path) == before_tmp
    assert listing(PRIVATE_DIR) == before_private
    assert not hasattr(import_ramses, "DEFAULT_OUTPUT")


def test_ramses_refuses_the_private_dir_and_writes_a_scratch_file(tmp_path, monkeypatch):
    raw = _ramses_raw(tmp_path / "raw", RAMSES_LINES)
    base = ["x", "--raw-dir", str(raw), "--splits", "train", "--existing", ""]
    monkeypatch.setattr(sys, "argv", base + ["--output", str(PRIVATE_DIR / "r.csv")])
    with pytest.raises(SystemExit):
        import_ramses.main()
    assert not (PRIVATE_DIR / "r.csv").exists()

    scratch = tmp_path / "tmp" / "out.csv"
    monkeypatch.setattr(sys, "argv", base + ["--output", str(scratch)])
    import_ramses.main()
    assert len(pd.read_csv(scratch)) == 2  # the clean line and the 1/2 fraction


def test_ramses_rows_do_not_claim_a_period():
    row = import_ramses.to_schema("train", 1, "ꞽw", "𓅱", "𓅱")
    assert row["period"] == "unknown"
    assert row["language_stage"] == "Late Egyptian"
    # The id does not include the period, so annotations stay attached.
    assert row["source_text_id"] == "RAMSES_4C2862257FB4"


@pytest.mark.parametrize("text", ["ꞽmn-m-//", "bw-///-k-///", "ḥr-[...]", "x-[]", "[..]-ꞽr", "a [ ] b"])
def test_translit_lacuna_regex_matches_partial_gaps(text):
    assert TRANSLIT_LACUNA_RE.search(text)


@pytest.mark.parametrize("text", ["1/2", "nb.[t]", "[sšr]", "ꞽmn-m", "ꜥnḫ =f"])
def test_translit_lacuna_regex_leaves_real_readings_alone(text):
    assert not TRANSLIT_LACUNA_RE.search(text)


def test_ramses_drops_partial_lacunae_and_keeps_clean_lines(tmp_path):
    raw = _ramses_raw(tmp_path / "raw", RAMSES_LINES)
    frame, report = import_ramses.convert(raw, ["train"])
    assert report.dropped_partial_lacuna == 3
    assert report.dropped_translit_lacuna == 3
    assert list(frame["transliteration_gold"]) == ["ꞽw ꞽw", "r 1/2"]
    assert set(frame["period"]) == {"unknown"}


def test_bbaw_text_only_rows_drop_a_lacuna_and_display_their_reading():
    raw = pd.DataFrame(
        {
            "transcription": ["jw fnḏ =k m ḫnm.w [...]", "ḏd =f", "jw nb.[t] r"],
            "translation": ["a", "b", "c"],
            "hieroglyphs": ["", "", ""],
        }
    )
    frame, report = import_bbaw_egyptian.convert(raw, include_text_only=True)
    assert report.dropped_translit_lacuna == 1
    assert list(frame["transliteration_gold"]) == ["ḏd =f", "ꞽw nb.[t] r"]
    assert list(frame["display_sequence"]) == list(frame["transliteration_gold"])
    # the existing glyph-side lacuna counter is separate
    assert report.dropped_lacuna == 0


def test_bbaw_refuses_the_corpus_as_output(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["x", "--output", str(EXAMPLES)])
    with pytest.raises(SystemExit):
        import_bbaw_egyptian.main()


# --- A34 / A33: TLA period and notes ------------------------------------------------


def _row(**overrides) -> pd.Series:
    base = {
        "hieroglyphs": "",
        "transliteration": "ḥtp",
        "translation": "peace",
        "lemmatization": "",
        "UPOS": "",
        "glossing": "",
        "dateNotBefore": "201",
        "dateNotAfter": "250",
    }
    base.update(overrides)
    return pd.Series(base, name=0)


def _map(row: pd.Series, **kwargs) -> dict:
    mapped = import_tla_dataset._row_from_parquet(
        row, 1, Path("x.parquet"), True, "Demotic", "TLA_DEMOTIC", "Demotic", **kwargs
    )
    assert mapped is not None
    return mapped[0]


def test_undated_demotic_row_is_unknown_not_the_language_stage():
    out = _map(_row(dateNotBefore="", dateNotAfter=""))
    assert out["period"] == "unknown"
    assert out["language_stage"] == "Demotic"


def test_roman_period_now_reaches_the_arab_conquest():
    assert import_tla_dataset._derive_period("426", "450") == "Roman Period"
    assert import_tla_dataset._derive_period("451", "475") == "Roman Period"
    assert import_tla_dataset._derive_period("700", "720").startswith("Undated range")
    assert import_tla_dataset._derive_period("-664", "-626") == "Late Period"
    assert import_tla_dataset._derive_period("201", "250") == "Roman Period"


def test_tla_row_keeps_the_date_range_and_editors_in_grammar_notes():
    row = _row(authors="Günter Vittmann;AV Altägyptisches Wörterbuch")
    note = _map(row)["grammar_notes"]
    assert "TLA date: 201 to 250" in note
    assert "Günter Vittmann" in note and ";" not in note.split("editors:")[1]
    assert _map(_row())["grammar_notes"] == "TLA date: 201 to 250 (negative = BCE)"
    assert _map(_row(dateNotBefore="", dateNotAfter=""))["grammar_notes"] == ""


def test_stable_id_does_not_depend_on_the_new_authors_alias():
    """The id hashes the source Series, which this change does not touch."""
    a = _map(_row())["source_text_id"]
    assert a == import_tla_dataset.content_id(_row(), "TLA_DEMOTIC")


def test_grammar_notes_survive_the_append_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = _tla_parquet(tmp_path / "d.parquet", authors="A B;C D")
    existing = tmp_path / "existing.csv"
    pd.DataFrame([{c: "x" for c in REQUIRED_COLUMNS}]).to_csv(existing, index=False)
    out = tmp_path / "scratch.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        ["x", "--input", str(source), "--output", str(out), "--existing", str(existing),
         "--append", "--stable-ids", "--limit", "5"],
    )
    import_tla_dataset.main()
    combined = pd.read_csv(existing, dtype=str, keep_default_na=False)
    tla = combined[combined["source"] == "TLA"]
    assert len(tla) > 0
    assert all("TLA date: -2000 to -1900" in n and "editors: A B, C D" in n for n in tla["grammar_notes"])


# --- A38: Helsinki weak radical -----------------------------------------------------


def test_aes_weak_radical_and_yod_fold_to_one_letter():
    convert = import_helsinki_lexicon.reading_to_corpus_convention
    assert convert("Spsi", "AES") == "špsꞽ"
    assert convert("Spsy", "AES") == "špsꞽ"
    folded = convert("yAwi̯", "AES")
    assert folded == "ꞽꜣwꞽ" and "̯" not in folded
    assert convert("i", "Ramses") == "ꞽ"
    assert convert("y", "Ramses") == "y"


def test_one_reading_in_two_aes_spellings_merges_in_the_built_lexicon(tmp_path, monkeypatch):
    aes = tmp_path / "AES.json"
    aes.write_text(
        json.dumps(
            {"words": [{"encoding": "S29 N31 A1", "interpretations": [
                {"transliteration": "Spsi", "freq": 2},
                {"transliteration": "Spsy", "freq": 1},
            ]}]}
        )
    )
    ramses = tmp_path / "R.json"
    ramses.write_text(
        json.dumps({"words": [{"encoding": "M17", "interpretations": [
            {"transliteration": "i", "freq": 5}]}]})
    )
    files = {"AESModel.json": aes, "RamsesTrainingSetModel.json": ramses}
    monkeypatch.setattr(import_helsinki_lexicon, "download", lambda name, force=False: files[name])
    frame, _ = import_helsinki_lexicon.build()
    spsi = frame[frame["reading"] == "špsꞽ"]
    assert len(spsi) == 1 and int(spsi.iloc[0]["freq"]) == 3
    assert not frame["reading"].str.contains("špsi").any()


# --- A32 / A36: AES -----------------------------------------------------------------


AES_ROW = {
    "corpus": "sawlit",
    "text_id": "T1",
    "sentence_id": "S1",
    "hieroglyphs": "𓅱 𓂋",
    "transliteration": "ꞽw r",
    "date": "NK",
    "text_name": "sawlit:Traumgeschichte",
}


def test_aes_ids_are_unchanged_and_the_text_name_is_in_the_notes():
    out = import_aes_relannis.to_schema(AES_ROW)
    # Annotations and 41 benchmark/test/doc files hold AES ids: they must not move.
    assert out["source_text_id"] == "AES_CF273D209508" == import_aes_relannis.content_id(AES_ROW)
    assert out["source_sentence_id"] == "SCF273D209508"
    assert out["source_ref"] == "AES/sawlit#text=T1&sentence=S1"
    assert out["grammar_notes"].startswith("AES date: NK")
    assert "AES text: sawlit:Traumgeschichte" in out["grammar_notes"]
    assert "upstream text id: T1" in out["grammar_notes"]


def test_duplicate_report_counts_without_filtering():
    frame = pd.DataFrame(
        {
            "transliteration_gold": ["ꞽw r", "jw r", "nfr"],
            "hieroglyphs": ["𓅱𓂋", "𓅱𓂋", "𓄤"],
        }
    )
    existing = pd.DataFrame(
        {"transliteration_gold": ["ḥtp"], "hieroglyphs": ["𓄤"]}
    )
    summary = import_aes_relannis.duplicate_report(frame, existing)
    assert summary["kept"] == 3 and len(frame) == 3
    assert summary["repeated_readings"] == 1  # `ꞽw r` and `jw r` are one reading
    assert summary["glyph_twins_other_reading"] == 1  # 𓄤 reads `nfr` here, `ḥtp` there


def _relannis_archive(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    nodes, annotations, meta = [], [], []
    node = 0
    for doc, sentence in (("d1", "S1"), ("d2", "S2")):
        for order, (glyph, form) in enumerate((("𓅱", "jw"), ("𓂋", "r"))):
            node += 1
            nodes.append(f"{node}\t0\t{doc}\tx\tn\t0\t0\tNULL\t{order}\t{order}")
            annotations.append(f"{node}\tns\twritten_form\t{form}")
            annotations.append(f"{node}\tns\thiero_unicode\t{glyph}")
        meta += [
            f"{doc}\tns\ttext_name\tsawlit:Traumgeschichte",
            f"{doc}\tns\ttext\tT1",
            f"{doc}\tns\tsentence_id\t{sentence}",
            f"{doc}\tns\tdate\tNK",
        ]
    archive = directory / "sawlit.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("node.annis", "\n".join(nodes) + "\n")
        zf.writestr("node_annotation.annis", "\n".join(annotations) + "\n")
        zf.writestr("corpus_annotation.annis", "\n".join(meta) + "\n")
    return directory


def test_aes_main_reports_repeats_but_keeps_every_row(tmp_path, monkeypatch, capsys):
    relannis = _relannis_archive(tmp_path / "relannis")
    out = tmp_path / "aes.csv"
    monkeypatch.setattr(
        sys, "argv", ["x", "--relannis", str(relannis), "--output", str(out), "--existing", ""]
    )
    import_aes_relannis.main()
    written = pd.read_csv(out, dtype=str, keep_default_na=False)
    assert len(written) == 2
    assert all("AES text: sawlit:Traumgeschichte" in n for n in written["grammar_notes"])
    printed = capsys.readouterr().out
    assert "repeat an earlier reading in this import: 1" in printed


def test_aes_refuses_the_private_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["x", "--relannis", str(tmp_path), "--output", str(PRIVATE_DIR / "a.csv")]
    )
    with pytest.raises(SystemExit):
        import_aes_relannis.main()
    assert not (PRIVATE_DIR / "a.csv").exists()


# --- A37: pinned downloads ----------------------------------------------------------


def _download_module(monkeypatch, calls: list):
    class FakeDataset:
        def to_pandas(self):
            return pd.DataFrame({"a": [1, 2]})

    def load_dataset(name, split=None, revision=None):
        calls.append((name, split, revision))
        return FakeDataset()

    monkeypatch.setitem(sys.modules, "datasets", types.SimpleNamespace(load_dataset=load_dataset))
    monkeypatch.delitem(sys.modules, "scripts.download_all_sources", raising=False)
    return importlib.import_module("scripts.download_all_sources")


def test_every_dataset_is_pinned_to_a_commit(monkeypatch):
    module = _download_module(monkeypatch, [])
    assert module.DATASETS
    for item in module.DATASETS:
        assert re.fullmatch(r"[0-9a-f]{40}", item["revision"])


def test_download_passes_the_revision_and_keeps_existing_files(tmp_path, monkeypatch):
    calls: list = []
    module = _download_module(monkeypatch, calls)
    out = tmp_path / "x" / "a.parquet"
    module.save_dataset("org/name", str(out), "a" * 40)
    assert calls == [("org/name", "train", "a" * 40)]
    first = sha(out)
    out.write_bytes(b"changed")
    module.save_dataset("org/name", str(out), "a" * 40)  # exists: not downloaded again
    assert len(calls) == 1 and out.read_bytes() == b"changed"
    module.save_dataset("org/name", str(out), "a" * 40, force=True)
    assert len(calls) == 2 and sha(out) == first


def test_download_main_force_flag(tmp_path, monkeypatch):
    calls: list = []
    module = _download_module(monkeypatch, calls)
    out = tmp_path / "a.parquet"
    monkeypatch.setattr(
        module, "DATASETS", [{"name": "org/n", "revision": "b" * 40, "out": str(out)}]
    )
    monkeypatch.setattr(sys, "argv", ["x"])
    module.main()
    module.main()
    assert len(calls) == 1
    monkeypatch.setattr(sys, "argv", ["x", "--force"])
    module.main()
    assert len(calls) == 2


def test_bbaw_and_helsinki_urls_are_pinned_to_a_commit():
    for url in (import_bbaw_egyptian.PARQUET_URL, import_helsinki_lexicon.BASE_URL):
        assert re.search(r"[0-9a-f]{40}", url)
        assert "/main" not in url

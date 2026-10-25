"""Sign reference: Unikemet parsing, JSesh join by code, MdC -> TLA values, attribution."""

from __future__ import annotations

import collections
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_sign_reference import build, parse_jsesh, parse_unikemet  # noqa: E402

# Unikemet.txt 18.0.0, U+13002, verbatim.
UNIKEMET = """# comment
U+13002\tkEH_Cat\tA-01-005
U+13002\tkEH_Core\tC
U+13002\tkEH_Desc\tMan, seated on heel, right knee raised, right arm raised, left arm in front of body.
U+13002\tkEH_Func\tClassifier sitting
U+13002\tkEH_FVal\tḥmsꞽ
U+13002\tkEH_UniK\tA003
U+13002\tkEH_JSesh\tA3
U+13002\tkEH_HG\tA3
"""

JSESH = b"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE signs PUBLIC "-//ORG/QENHERKHOPESHEF//DTD SIGNDESCRIPTION 1.0" "sign_description.dtd">
<signs>
  <sign sign="A3">
    <hasTag sign="A3" tag="seated"/>
    <hasTransliteration sign="A3" transliteration="Hmsi" type="ideogram" use="keyboard"/>
    <variantOf baseSign="A1" isSimilar="y" linguistic="partial" sign="A3"/>
  </sign>
</signs>
"""


def test_unikemet_and_jsesh_join() -> None:
    uk = parse_unikemet(UNIKEMET)
    js = parse_jsesh(JSESH)
    df = build(uk, js, collections.Counter({"𓀂": 5}), set())
    row = df.iloc[0]
    assert row["sign"] == "𓀂" and row["codepoint"] == "U+13002"
    assert row["gardiner"] == "A3" and row["unikemet_value"] == "ḥmsꞽ"
    assert row["jsesh_values"] == "ḥmsꞽ"  # MdC Hmsi converted to TLA letters
    assert row["jsesh_values_mdc"] == "Hmsi"
    assert row["jsesh_variant_of"] == "A1" and row["jsesh_tags"] == "seated"
    assert row["in_corpus"] == "True" and row["corpus_occurrences"] == 5
    assert "Unicode License V3" in row["source"] and "CC BY 4.0" in row["source"]


def test_committed_table_carries_attribution() -> None:
    path = PROJECT_ROOT / "data" / "processed" / "sign_reference.csv"
    if not path.exists():
        return
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert df["source"].str.contains("Unicode License V3").all()
    assert len(df) == df["codepoint"].nunique()


def test_unikemet_qoph_kept_upstream_and_normalised_to_tla_q() -> None:
    uk = parse_unikemet("U+1320E\tkEH_FVal\tḳꜣb\nU+1320E\tkEH_JSesh\tN29\n")
    row = build(uk, {}, collections.Counter(), set()).iloc[0]
    assert row["unikemet_value"] == "ḳꜣb"  # verbatim upstream
    assert row["unikemet_value_tla"] == "qꜣb"


def test_main_refuses_to_overwrite_its_examples_input(tmp_path: Path, monkeypatch) -> None:
    """The guard used to cover only the repository examples.csv, not --examples."""
    import pytest

    from scripts import build_sign_reference as mod
    from scripts import fetch_wikidata_lemma_glosses as wd
    from scripts import import_ud_egyptian_pc as ud

    custom = tmp_path / "corpus.csv"
    custom.write_text("hieroglyphs\n", encoding="utf-8")
    argvs = [
        (mod, ["--unikemet", "u", "--jsesh", "j"]),
        (wd, ["--raw-dir", str(tmp_path)]),
        (ud, ["--raw-dir", str(tmp_path)]),
    ]
    for module, extra in argvs:
        monkeypatch.setattr(sys, "argv", ["x", *extra, "--examples", str(custom), "--output", str(custom)])
        with pytest.raises(SystemExit) as info:
            module.main()
        assert "--examples" in str(info.value), module.__name__
    assert custom.read_text(encoding="utf-8") == "hieroglyphs\n"

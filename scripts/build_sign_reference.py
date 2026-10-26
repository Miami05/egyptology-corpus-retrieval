"""Build `data/processed/sign_reference.csv` from Unicode Unikemet 18.0 and JSesh.

Sources and licences.
  * Unikemet.txt, Unicode Character Database 18.0.0
    (https://www.unicode.org/Public/18.0.0/ucd/Unikemet.txt) — Unicode License V3,
    © 1991-2026 Unicode, Inc. The licence requires its copyright and permission
    notice to appear with copies or in associated documentation; it is reproduced in
    full in DATA-LICENSE.md.
  * JSesh `signs_description.xml` (https://github.com/rosmord/jsesh,
    jsesh/src/main/resources/jsesh/glyphs/resources/signs_description.xml) — CC BY 4.0
    per the JSesh README, credited to Serge Rosmorduc and JSesh contributors. Only
    this XML is used; JSesh fonts are under separate terms and nothing from them is
    read or redistributed.

One row per Unikemet code point. Columns:
    sign, codepoint                        the character and U+XXXXX
    unikemet_catalog, unikemet_unik        kEH_Cat (Unikemet catalogue), kEH_UniK
    gardiner                               kEH_JSesh (the JSesh / extended Gardiner code)
    unikemet_core                          kEH_Core: C core, L legacy, N otherwise
    unikemet_description                   kEH_Desc
    unikemet_function, unikemet_value      kEH_Func, kEH_FVal, verbatim upstream values.
                                           FVal is in Schenkel-style letters (ꞽ ḥ ẖ ...)
                                           that match TLA except `ḳ` (170 rows in 18.0),
                                           which TLA writes `q`
    unikemet_value_tla                     unikemet_value with `ḳ`/`Ḳ` -> `q`/`Q`, the only
                                           letter that differs from the corpus convention
    jsesh_values                           hasTransliteration values, converted from
                                           JSesh's Manuel-de-Codage ASCII (`i`=yod,
                                           `A`=ꜣ, `a`=ꜥ, `H x X S T D`) to the corpus's
                                           TLA letters by the Ramses importer's table
    jsesh_values_mdc, jsesh_value_types    the same values as written, and their type
                                           (phonogram / ideogram / abbreviation / typical)
    jsesh_variant_of, jsesh_tags           variantOf baseSign; hasTag labels
    in_corpus, corpus_occurrences          whether the sign occurs in examples.csv
    in_nederhof                            whether data/processed/sign_functions.csv has it
    source                                 which of the two sources contributed columns

    python -I scripts/build_sign_reference.py --unikemet data/raw/unikemet/Unikemet.txt \
        --jsesh data/raw/jsesh/signs_description.xml --output data/processed/sign_reference.csv
"""

from __future__ import annotations

import argparse
import collections
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_ramses import convert_word as mdc_to_tla  # noqa: E402

EXAMPLES = PROJECT_ROOT / "data" / "processed" / "examples.csv"
NEDERHOF = PROJECT_ROOT / "data" / "processed" / "sign_functions.csv"

UNIKEMET_SOURCE = "Unicode Unikemet 18.0.0 (Unicode License V3, © 1991-2026 Unicode, Inc.)"
JSESH_SOURCE = "JSesh signs_description.xml (Serge Rosmorduc et al., CC BY 4.0)"

COLUMNS = [
    "sign", "codepoint", "unikemet_catalog", "unikemet_unik", "gardiner", "unikemet_core",
    "unikemet_description", "unikemet_function", "unikemet_value", "unikemet_value_tla",
    "jsesh_values", "jsesh_values_mdc", "jsesh_value_types", "jsesh_variant_of", "jsesh_tags",
    "in_corpus", "corpus_occurrences", "in_nederhof", "source",
]

TAGS = {
    "kEH_Cat": "unikemet_catalog",
    "kEH_UniK": "unikemet_unik",
    "kEH_JSesh": "gardiner",
    "kEH_Core": "unikemet_core",
    "kEH_Desc": "unikemet_description",
    "kEH_Func": "unikemet_function",
    "kEH_FVal": "unikemet_value",
}


# Unikemet's kEH_FVal letters that the corpus's TLA convention writes differently.
FVAL_TO_TLA = str.maketrans({"ḳ": "q", "Ḳ": "Q"})


def fval_to_tla(value: str) -> str:
    """A kEH_FVal value in the corpus's letters (`ḳ` -> `q`); everything else unchanged."""
    return value.translate(FVAL_TO_TLA)


def is_hieroglyph(ch: str) -> bool:
    cp = ord(ch)
    return 0x13000 <= cp <= 0x1342F or 0x13460 <= cp <= 0x143FF


def parse_unikemet(text: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] not in TAGS:
            continue
        cp, tag, value = parts
        col = TAGS[tag]
        prev = out[cp].get(col)
        out[cp][col] = f"{prev} | {value}" if prev else value
    return dict(out)


def parse_jsesh(xml_bytes: bytes) -> dict[str, dict[str, str]]:
    """JSesh code -> value / variant / tag columns. External DTD is never fetched."""
    root = ET.fromstring(xml_bytes)
    acc: dict[str, dict[str, list[str]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for el in root.iter():
        code = el.get("sign")
        if not code:
            continue
        if el.tag == "hasTransliteration":
            value = el.get("transliteration", "")
            if value and value not in acc[code]["mdc"]:
                acc[code]["mdc"].append(value)
                acc[code]["types"].append(el.get("type", ""))
        elif el.tag == "variantOf" and el.get("baseSign"):
            acc[code]["variant"].append(el.get("baseSign", ""))
        elif el.tag == "hasTag" and el.get("tag"):
            acc[code]["tags"].append(el.get("tag", ""))
    out: dict[str, dict[str, str]] = {}
    for code, d in acc.items():
        out[code] = {
            "jsesh_values": " | ".join(mdc_to_tla(v) for v in d["mdc"]),
            "jsesh_values_mdc": " | ".join(d["mdc"]),
            "jsesh_value_types": " | ".join(d["types"]),
            "jsesh_variant_of": " | ".join(dict.fromkeys(d["variant"])),
            "jsesh_tags": " | ".join(dict.fromkeys(d["tags"])),
        }
    return out


def build(unikemet: dict, jsesh: dict, corpus_counts: collections.Counter, nederhof: set[str]) -> pd.DataFrame:
    rows = []
    for cp, fields in unikemet.items():
        sign = chr(int(cp[2:], 16))
        row = {c: "" for c in COLUMNS}
        row.update(fields)
        row["sign"], row["codepoint"] = sign, cp
        row["unikemet_value_tla"] = fval_to_tla(row["unikemet_value"])
        sources = [UNIKEMET_SOURCE]
        js = jsesh.get(fields.get("gardiner", ""))
        if js and any(js.values()):
            row.update(js)
            sources.append(JSESH_SOURCE)
        row["in_corpus"] = str(sign in corpus_counts)
        row["corpus_occurrences"] = corpus_counts.get(sign, 0)
        row["in_nederhof"] = str(sign in nederhof)
        row["source"] = "; ".join(sources)
        rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--unikemet", required=True)
    parser.add_argument("--jsesh", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--examples", default=str(EXAMPLES))
    parser.add_argument("--nederhof", default=str(NEDERHOF))
    args = parser.parse_args()
    out = Path(args.output).resolve()
    if out == EXAMPLES.resolve():
        sys.exit("refusing to overwrite examples.csv")
    if out == Path(args.examples).resolve():
        sys.exit("refusing to overwrite the --examples input")

    unikemet = parse_unikemet(Path(args.unikemet).read_text(encoding="utf-8"))
    jsesh = parse_jsesh(Path(args.jsesh).read_bytes())
    glyphs = pd.read_csv(args.examples, dtype=str, keep_default_na=False, usecols=["hieroglyphs"])["hieroglyphs"]
    counts: collections.Counter = collections.Counter()
    for value in glyphs:
        counts.update(ch for ch in value if is_hieroglyph(ch))
    nederhof = set(pd.read_csv(args.nederhof, dtype=str, keep_default_na=False)["sign"])

    df = build(unikemet, jsesh, counts, nederhof)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    total_occ = sum(counts.values())
    ref = df.set_index("sign")
    has_value = ref[(ref["unikemet_function"] != "") | (ref["unikemet_value"] != "") | (ref["jsesh_values"] != "")]
    has_any_fn = set(has_value.index)
    corpus_signs = set(counts)
    print(f"unikemet code points: {len(df)}; with JSesh values joined: {(df['jsesh_values'] != '').sum()}")
    print(f"corpus distinct signs: {len(corpus_signs)}; occurrences: {total_occ}")
    print(f"  in Unikemet at all: {len(corpus_signs & set(ref.index))}")
    print(f"  with a function or value (Unikemet or JSesh): {len(corpus_signs & has_any_fn)} "
          f"({sum(counts[s] for s in corpus_signs & has_any_fn) / total_occ:.4f} of occurrences)")
    print(f"  Nederhof covers: {len(corpus_signs & nederhof)}")
    union = corpus_signs & (has_any_fn | nederhof)
    print(f"  union with Nederhof: {len(union)} ({sum(counts[s] for s in union) / total_occ:.4f} of occurrences)")
    print(f"  newly covered (not in Nederhof): {len(corpus_signs & has_any_fn - nederhof)}")
    print(f"  still uncovered: {len(corpus_signs - union)}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

"""Convert Mark-Jan Nederhof's sign-function XML into `data/processed/sign_functions.csv`.

What this is. The a-priori knowledge item C needs: for each Unicode 5.2 hieroglyph,
what the sign *does* in a writing — logogram, determinative (classifier), phonogram,
phonetic determinative — with the transliteration and gloss where the class carries
one. It is the file behind Nederhof & Rahman (2015) and the tables at
<https://mjn.host.cs.st-andrews.ac.uk/egyptian/unicode/>.

Licence. On 2026-09-04 Nederhof wrote, of this file: "You can use the XML file with
functions under whatever license you prefer" (archived in
`docs/permission-requests.md`, "Reply … received 2026-09-04"). We publish our
converted table as **CC BY 4.0, credited to Mark-Jan Nederhof**, which is compatible
with the CC BY-SA corpus beside it. The original XML is his and is not redistributed;
`data/raw/standrews/unicode/` is gitignored. This is *not* the CC BY-NC-SA St Andrews
text corpus — a different file under a different grant, and unlike the texts this one
may be committed.

Inputs (fetched from his Unicode page into `data/raw/standrews/unicode/`):

    signuse.xml      <sign id="A1"><det><al>s</al><tr>man</tr>…  — the functions
    signunicode.xml  <sign id="A1" code="0x13000"/>              — the codepoints

Function elements and how they map to the `function` column, using his own
definitions from the prose at the head of `signuse.xml`:

    <log>          logogram                 stands for a word by itself
    <det>          determinative            narrows the meaning, follows phonograms
    <logdet>       logogram or determinative
    <phon>         phonogram                a sequence of consonants
    <phondet>      phonetic determinative   cannot stand alone; repeats consonants
    <phonphondet>  phonogram or phonetic determinative
    <typ>          typographic              everything else

Children read from each: `<al>` the transliteration (converted from his Manuel de
Codage-style ASCII to the corpus's TLA convention by the same table
`import_standrews.py` uses — he writes the yod `j`), `<tr>` the translation or, for a
determinative with no single word, the range of meanings from `<describe>`, and
`<group>` the RES sign combination when the reading belongs to a combination rather
than to the sign alone. `<example>` children are attestations and are not carried:
they are RES quadrats, not sign functions, and item C wants the function inventory.

Attributes kept in `qualifier`: `period`, `texttype`, `plural`, `dual`, `numeral`,
`certain` (Nederhof's own hedge on an uncertain reading), and `root` on `<al>` (the
consonantal root behind an inflected reading).

    python scripts/import_sign_functions.py
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

from scripts.import_standrews import convert_word  # noqa: E402

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "standrews" / "unicode"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "sign_functions.csv"

SOURCE_NOTE = (
    "Mark-Jan Nederhof, sign-function list (Unicode 5.2 set), "
    "https://mjn.host.cs.st-andrews.ac.uk/egyptian/unicode/ — used under his written "
    "grant of 2026-09-04; published here CC BY 4.0"
)

FUNCTIONS = {
    "log": "logogram",
    "det": "determinative",
    "logdet": "logogram or determinative",
    "phon": "phonogram",
    "phondet": "phonetic determinative",
    "phonphondet": "phonogram or phonetic determinative",
    "typ": "typographic",
}

QUALIFIER_ATTRIBUTES = ("period", "texttype", "plural", "dual", "numeral", "certain")

COLUMNS = [
    "sign",
    "gardiner",
    "codepoint",
    "function",
    "value",
    "meaning",
    "group",
    "qualifier",
    "source_note",
]


def read_codepoints(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    codepoints: dict[str, int] = {}
    for sign in root.findall("sign"):
        code = sign.get("code")
        name = sign.get("id")
        if code and name:
            codepoints[name] = int(code, 16)
    return codepoints


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _qualifier(element: ET.Element, value_element: ET.Element | None) -> str:
    parts = [
        f"{name}={element.get(name)}"
        for name in QUALIFIER_ATTRIBUTES
        if element.get(name)
    ]
    if value_element is not None and value_element.get("root"):
        parts.append(f"root={convert_word(value_element.get('root', ''))}")
    if value_element is not None and value_element.get("certain"):
        parts.append(f"certain={value_element.get('certain')}")
    return "; ".join(parts)


def convert(raw_dir: Path) -> tuple[pd.DataFrame, collections.Counter[str]]:
    codepoints = read_codepoints(raw_dir / "signunicode.xml")
    root = ET.parse(raw_dir / "signuse.xml").getroot()
    stats: collections.Counter[str] = collections.Counter()
    rows: list[dict] = []
    for sign in root.findall("sign"):
        gardiner = sign.get("id", "")
        if not gardiner:
            continue
        stats["signs"] += 1
        codepoint = codepoints.get(gardiner)
        if codepoint is None:
            stats["signs without a Unicode codepoint"] += 1
        character = chr(codepoint) if codepoint else ""
        for element in sign:
            function = FUNCTIONS.get(element.tag)
            if function is None:
                # `<p>` — Nederhof's prose cross-references ("Cf. A30"). Not a
                # function; the reference lives in the HTML tables, not here.
                continue
            stats[function] += 1
            value_element = element.find("al")
            meaning = _text(element.find("tr")) or _text(element.find("describe"))
            rows.append(
                {
                    "sign": character,
                    "gardiner": gardiner,
                    "codepoint": f"U+{codepoint:04X}" if codepoint else "",
                    "function": function,
                    "value": convert_word(_text(value_element)),
                    "meaning": meaning,
                    "group": _text(element.find("group")),
                    "qualifier": _qualifier(element, value_element),
                    "source_note": SOURCE_NOTE,
                }
            )
    return pd.DataFrame(rows, columns=COLUMNS), stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    frame, stats = convert(Path(args.raw_dir))
    print(f"signs in signuse.xml           {stats['signs']:>8,}")
    print(f"  no Unicode codepoint         {stats['signs without a Unicode codepoint']:>8,}")
    print(f"function entries               {len(frame):>8,}")
    for function in FUNCTIONS.values():
        print(f"  {function:<34} {stats[function]:>8,}")
    print(f"entries with a transliteration {int((frame['value'] != '').sum()):>8,}")
    print(f"entries with a meaning         {int((frame['meaning'] != '').sum()):>8,}")
    print(f"entries scoped to a group      {int((frame['group'] != '').sum()):>8,}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    print(f"\nwrote {len(frame)} rows to {output}")
    print("CC BY 4.0, credited to Mark-Jan Nederhof — safe to commit (see DATA-LICENSE.md).")


if __name__ == "__main__":
    main()

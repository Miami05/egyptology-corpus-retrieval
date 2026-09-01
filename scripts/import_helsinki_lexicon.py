"""Build the sign-reading lexicon from the Helsinki "Transliteration Model" files.

What this is. Heidi and Tommi Jauhiainen (University of Helsinki) published three JSON
files they call "transliteration models" (Zenodo 10.5281/zenodo.7991241, CC BY 4.0;
github.com/MaReTEgyptologists/TranslitModels). They are not neural weights: each is a
list of hieroglyphic *words* — a sign sequence in Manuel de Codage codes — with every
transliteration that word carries in a corpus, and how often. That is exactly the
statistic `app.services.reading_model.ReadingModel` computes from our own corpus, so
the two can be laid side by side: our counts first, theirs where ours are silent.

Why it matters. Our corpus knows 39,487 distinct sign groups. The two lexicons hold
84,558 spellings, 53,457 of them (63%) never seen by our model — and 41,508 of those
come from the Ramses corpus of Late Egyptian, the period where our corpus is thinnest
and where both expert testers' queries landed. A group attested in the corpus reads
correctly about 89% of the time; an unattested one about 25%. This file moves tens of
thousands of groups from the second bucket towards the first.

What it is not. It has no sentences. A lexicon reading can never be shown as a corpus
parallel, and the UI labels it as its own kind of evidence ("lexicon N×, no sentence
in this corpus"). Nothing here is generated: every row is an attested count.

Provenance the app must carry. The AES half derives from Schweitzer's AES corpus (CC
BY-SA 4.0). The Ramses half derives from the Ramses Transliteration Corpus
(Rosmorduc / Université de Liège), whose own README is CC BY-NC-SA; Helsinki released
the derived statistics as CC BY 4.0 and we rely on that in good faith, citing both.
See DATA-LICENSE.md.

Conventions in the source files (verified 2026-09-01):
  encoding          "D21 Z1", "2 R8", "A1" — Gardiner codes separated by spaces; bare
                    digits are numerals; Ramses-specific codes (Ff100) have no Unicode.
  transliteration   Manuel de Codage ASCII: A=ꜣ a=ꜥ i/j=ꞽ H=ḥ x=ḫ X=ẖ S=š T=ṯ D=ḏ,
                    `.` and `-` as in TLA, `=` before suffix pronouns. Proper names
                    are capitalised (Nfr, Ꜥ, J…); the corpus writes everything in
                    lower case, so the MdC letters are converted FIRST and the rest
                    lower-cased AFTER — lower-casing `H` before conversion would turn
                    ḥ into h.

Usage:
    python scripts/import_helsinki_lexicon.py            # writes data/processed/helsinki_lexicon.csv
    python scripts/import_helsinki_lexicon.py --limit 500  # smoke run
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import nfc, normalize_hieroglyphs  # noqa: E402
from scripts.import_bbaw_egyptian import sign_for_code  # noqa: E402

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "helsinki_lexicon"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "helsinki_lexicon.csv"
BASE_URL = "https://raw.githubusercontent.com/MaReTEgyptologists/TranslitModels/main/Models/"
# The combined file is deliberately not used: it loses which corpus a count came
# from, and the two halves have different provenance (see module docstring).
SOURCES = {
    "AES": "AESModel.json",
    "Ramses": "RamsesTrainingSetModel.json",
}

# The two halves do NOT write the yod the same way — verified on the raw files:
#   AES     M17 → "=y", D21 → "yr" (ꞽr), G43 → "wy" (wꞽ); j never occurs, y 16,451×.
#           So `y` IS the yod, and `i` is the weak radical i̯ (as in "ywi" = ꞽwi̯).
#   Ramses  M17 → "i", M17 M17 → "y"; `i`/`j` are the yod and `y` is the double reed.
# One shared table would have merged 𓀀 "=y" (AES) and "=i" (Ramses) as two readings.
MDC_LETTERS = {"A": "ꜣ", "a": "ꜥ", "H": "ḥ", "x": "ḫ", "X": "ẖ", "S": "š", "T": "ṯ", "D": "ḏ", "Q": "q"}
YOD_BY_SOURCE = {
    "AES": {"y": "ꞽ", "Y": "ꞽ", "J": "ꞽ"},
    "Ramses": {"i": "ꞽ", "j": "ꞽ", "I": "ꞽ", "J": "ꞽ"},
}


def download(name: str, force: bool = False) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / name
    if target.exists() and not force:
        return target
    with urllib.request.urlopen(BASE_URL + name, timeout=120) as response:
        target.write_bytes(response.read())
    return target


def encoding_to_group(encoding: str) -> str:
    """Gardiner codes ("D21 Z1") → one normalised Unicode sign group ("𓂋𓏤")."""
    codes = [code for code in encoding.split() if code]
    if not codes:
        return ""
    return normalize_hieroglyphs("".join(sign_for_code(code) for code in codes))


def reading_to_corpus_convention(mdc: str, source: str) -> str:
    """MdC ASCII transliteration → the corpus's Unicode, lower-case convention.

    `source` selects the yod rule (see YOD_BY_SOURCE). Order matters: yod first, then
    the shared MdC letters, and only then lower-casing — lower-casing `H` before
    conversion would turn ḥ into h.
    """
    table = {**MDC_LETTERS, **YOD_BY_SOURCE[source]}
    text = "".join(table.get(char, char) for char in nfc(mdc).strip())
    return text.lower()


def build(limit: int = 0, force: bool = False) -> tuple[pd.DataFrame, dict]:
    counts: dict[tuple[str, str], Counter] = defaultdict(Counter)  # (group, reading) -> source -> freq
    report = {"spellings": 0, "unmapped_groups": 0, "empty_readings": 0}
    for source, name in SOURCES.items():
        words = json.loads(download(name, force=force).read_text())["words"]
        if limit:
            words = words[:limit]
        for word in words:
            report["spellings"] += 1
            group = encoding_to_group(word["encoding"])
            if not group:
                report["unmapped_groups"] += 1
                continue
            for interpretation in word["interpretations"]:
                reading = reading_to_corpus_convention(interpretation["transliteration"], source)
                if not reading:
                    report["empty_readings"] += 1
                    continue
                counts[(group, reading)][source] += int(interpretation["freq"])
    rows = [
        {
            "group": group,
            "reading": reading,
            "freq": sum(per_source.values()),
            "source": "+".join(sorted(per_source)),
        }
        for (group, reading), per_source in counts.items()
    ]
    frame = pd.DataFrame(rows).sort_values(["group", "freq"], ascending=[True, False])
    report["rows"] = len(frame)
    report["groups"] = frame["group"].nunique()
    report["multivalent_groups"] = int((frame.groupby("group").size() > 1).sum())
    return frame.reset_index(drop=True), report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--limit", type=int, default=0, help="Spellings per source (0 = all).")
    parser.add_argument("--force-download", action="store_true")
    args = parser.parse_args()
    frame, report = build(limit=args.limit, force=args.force_download)
    frame.to_csv(args.output, index=False)
    for key, value in report.items():
        print(f"{key:20} {value:>10,}")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()

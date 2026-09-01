"""Import the BBAW 2018 corpus snapshot published as `phiwi/bbaw_egyptian`.

What it is. A January-2018 excerpt of the internal database of the BBAW project
"Strukturen und Transformationen des Wortschatzes der ägyptischen Sprache" — the same
institution and database behind the TLA and AES rows already in the corpus. 100,736
sentence rows with `transcription` and a German `translation`; 35,503 of them also
carry `hieroglyphs`. Licence CC BY-SA 4.0, the corpus's own licence, so no permission
is needed; the attribution block lives in DATA-LICENSE.md. Primary source: AED-TEI
(github.com/simondschweitzer/aed-tei).

Why it is worth importing. The reading tool needs sign groups aligned one-to-one with
transliteration tokens, and this export has them: in `D54 *Z7 -M17 *N35 D21 I9 …` for
`jwi̯.jn r =f …` a whitespace token that *starts with* a layout operator (`-`, `:`,
`*`) continues the current word's quadrat and a token that does not starts the next
word. Read that way the row yields exactly as many sign groups as the transcription
has tokens, which is the property the loader's alignment report demands.

What is different from the corpus, and what is done about it:

  hieroglyphs   Manuel de Codage Gardiner codes, not Unicode. Converted through the
                names of the Unicode Egyptian Hieroglyphs block ("EGYPTIAN HIEROGLYPH
                D021" -> D21). Codes with no codepoint (Ff1, US9No2VARA, numerals)
                become `<g>CODE</g>` markup, which `normalize_hieroglyphs` already
                turns into a stable placeholder sign.
  transcription Older BBAW convention: comma as morpheme separator (`sḫ,tj`), `{,pl}`
                for plural, `≡` beside `=` as the suffix marker, and `j` for the yod
                where TLA writes `ꞽ`. Commas become dots, braces around plural/dual
                markers are dropped, `≡` becomes `=`, and `j` becomes `ꞽ` so that
                `strict_reading_key` agrees across sources (as for AES).

Strictness, as in the AES importer: a sentence is kept only when every word has a
sign group and the counts match. Rows with a lacuna (`//`), an unreadable sign
(`"?"`, `"⸮"`), an empty group or a count mismatch are counted and dropped, never
patched, because a shifted pairing silently corrupts the sign-level model.

    python scripts/import_bbaw_egyptian.py                 # measure only
    python scripts/import_bbaw_egyptian.py --append        # append aligned rows
    python scripts/import_bbaw_egyptian.py --include-text-only --output out.csv
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import REQUIRED_COLUMNS  # noqa: E402
from app.data.normalizer import normalize_hieroglyphs, search_fold  # noqa: E402

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "bbaw_egyptian"
RAW_PARQUET = RAW_DIR / "train.parquet"
PARQUET_URL = (
    "https://huggingface.co/datasets/phiwi/bbaw_egyptian/resolve/main/"
    "data/train-00000-of-00001.parquet"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "bbaw_rows.csv"
EXAMPLES = PROJECT_ROOT / "data" / "processed" / "examples.csv"

SOURCE = "BBAW"
TEXT_ID = "bbaw_egyptian_2018"
SOURCE_REF = "phiwi/bbaw_egyptian (AED-TEI, BBAW, Jan 2018 snapshot)"

# ---------------------------------------------------------------------------
# Gardiner code -> Unicode sign
# ---------------------------------------------------------------------------

_UNICODE_NAME_RE = re.compile(r"^EGYPTIAN HIEROGLYPH ([A-Z]+?)(\d{3})([A-Z]*)$")
_CODE_RE = re.compile(r"^([A-Za-z]+?)(\d+)([A-Za-z]*)$")


def _canonical(letters: str, digits: str, suffix: str) -> str:
    """One spelling for a code so `Aa1`, `AA001` and `aa1` all meet."""
    letters = letters.upper()
    return f"{letters}{int(digits)}{suffix.upper()}"


def build_gardiner_table() -> dict[str, str]:
    """Gardiner code -> Unicode sign, from the block's own character names."""
    table: dict[str, str] = {}
    for start, end in ((0x13000, 0x1342F), (0x13460, 0x143FF)):
        for codepoint in range(start, end + 1):
            try:
                name = unicodedata.name(chr(codepoint))
            except ValueError:
                continue
            match = _UNICODE_NAME_RE.match(name)
            if match:
                table[_canonical(*match.groups())] = chr(codepoint)
    return table


GARDINER_TO_UNICODE = build_gardiner_table()


def sign_for_code(code: str) -> str:
    """The Unicode sign for a Gardiner code, or `<g>CODE</g>` when there is none."""
    match = _CODE_RE.match(code)
    if match:
        sign = GARDINER_TO_UNICODE.get(_canonical(*match.groups()))
        if sign:
            return sign
    return f"<g>{code}</g>"


# ---------------------------------------------------------------------------
# Manuel de Codage token grammar, as far as this export uses it
# ---------------------------------------------------------------------------

OPERATOR_PREFIX_RE = re.compile(r"^[-:*]+")
# Editorial and layout markers that carry no sign. Openers precede a word's first sign
# (`[? *N35 *?]`, `<1 -G39 -N5 2>` cartouche); closers end one.
# `[? … ?]` uncertain, `[[ … ]]` erased/restored, `[( … )]`, `<1 … 2>` cartouche.
OPENER_RE = re.compile(r"^(\[+\(?\??|\(|<[a-z]?\d*)$")
CLOSER_RE = re.compile(r"^(\??\)?\]+|\)|\d*>)$")
LACUNA_RE = re.compile(r"^/{2,}$")
SHADING_RE = re.compile(r"^[hv]?/$")  # partial-sign shading, no sign of its own
UNREADABLE_RE = re.compile(r'^"?(\?|⸮)"?$')
# Quoted lower-case words are editorial annotations, not signs: "lb" marks a line
# break inside the text (2,080 times), "var" a variant writing of the sign before it.
ANNOTATION_RE = re.compile(r'^"[a-z]+"$')
DECORATION_RE = re.compile(r"""["'()\[\]{}#!,.+$〈〉_]""")
MODIFIER_RE = re.compile(r"\\\S*")  # \R90 rotation, \t mirroring, trailing \
NUMERAL_RE = re.compile(r"^\d+$")
CODE_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


@dataclass
class ParsedGlyphs:
    groups: list[str] = field(default_factory=list)
    lacuna: bool = False
    unreadable: bool = False
    unknown_codes: collections.Counter = field(default_factory=collections.Counter)
    stray_tokens: list[str] = field(default_factory=list)


def parse_glyph_field(text: str) -> ParsedGlyphs:
    """Turn one MdC field into space-separated Unicode sign groups, one per word."""
    parsed = ParsedGlyphs()
    groups: list[list[str]] = []

    def current() -> list[str]:
        if not groups:
            groups.append([])
        return groups[-1]

    for raw in str(text).split():
        prefix = OPERATOR_PREFIX_RE.match(raw)
        continues = bool(prefix)
        core = raw[prefix.end():] if prefix else raw
        core = MODIFIER_RE.sub("", core)
        if not core:
            continue
        if LACUNA_RE.match(core):
            parsed.lacuna = True
            continue
        if SHADING_RE.match(core):
            continue
        if CLOSER_RE.match(core):
            continue
        if OPENER_RE.match(core):
            # A bare opener begins the next word; the signs that follow carry `*`.
            if not continues and current():
                groups.append([])
            continue
        if UNREADABLE_RE.match(core):
            parsed.unreadable = True
            continue
        if ANNOTATION_RE.match(core):
            continue
        core = DECORATION_RE.sub("", core)
        if not core:
            continue
        if not continues and current():
            groups.append([])
        target = current()
        for piece in core.split("&"):  # `F39&Aa1` is a ligature of two signs
            if not piece:
                continue
            if NUMERAL_RE.match(piece):
                target.append(f"<g>NUM{piece}</g>")
            elif CODE_TOKEN_RE.match(piece):
                sign = sign_for_code(piece)
                if sign.startswith("<g>"):
                    parsed.unknown_codes[piece] += 1
                target.append(sign)
            else:
                parsed.stray_tokens.append(raw)
    parsed.groups = ["".join(group) for group in groups if group]
    return parsed


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

PLURAL_BRACES_RE = re.compile(r"\{[,.](pl|du)\}")


def to_corpus_convention(transcription: str) -> str:
    """The corpus's conventions for the yod, the dot and the suffix marker.

    The yod is rewritten `j` → `ꞽ` (and `J` → `Ꞽ` in capitalised names), exactly as
    the AES importer does. The search fold would treat `j` and `ꞽ` as one letter, but
    `strict_reading_key` — the identity the suggestion grouping and the sign-reading
    statistics rest on — would not, so left as `j` the same word would count as two
    readings depending on which corpus it came from. The AES conversion was validated
    on 1,342 sentences present in both corpora with no letter disagreement. Only the
    letter is touched: `i̯` (i + U+032F) and `y` are different letters and stay.
    Brackets wrap transliteration here too, so a restored `[tp,j]` converts as well.
    Everything else — brackets, restorations, capitalisation — is verbatim.
    """
    text = str(transcription).replace("≡", "=").replace("⸗", "=")
    text = PLURAL_BRACES_RE.sub(lambda m: f".{m.group(1)}", text)
    text = text.replace(",", ".")
    text = text.replace("j", "ꞽ").replace("J", "Ꞽ")
    return re.sub(r"\s+", " ", text).strip()


def dedup_key(transliteration: str) -> str:
    """Search fold made yod-insensitive, so `jwi̯` and `ꞽwi̯` count as one sentence.

    Lower-cased first: a capitalised name's `J`/`Ꞽ` must reach the fold as the same
    letter as `j`/`ꞽ`, or the key would depend on the yod spelling after all.
    """
    text = str(transliteration).lower().replace("ꞽ", "i").replace("j", "i")
    return search_fold(text)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def to_schema(index: int, transcription: str, translation: str, glyphs: str) -> dict:
    out = {column: "" for column in REQUIRED_COLUMNS}
    out.update(
        {
            "source": SOURCE,
            "source_text_id": TEXT_ID,
            # The parquet row index: the export has no ids of its own, and the row
            # order is the only stable handle it offers.
            "source_sentence_id": f"B{index:06d}",
            "language_stage": "Unspecified (BBAW)",
            "script_type": "hieroglyphic/hieratic",
            "genre": "unknown",
            "period": "unknown",
            "hieroglyphs": glyphs,
            "mdc": "",
            "sign_sequence": transcription,
            "transliteration_gold": transcription,
            "translation": str(translation or "").replace("\n", " ").strip(),
            "source_ref": SOURCE_REF,
            "review_status": "seed",
            "display_sequence": glyphs,
            "aesthetic_arrangement_flag": False,
        }
    )
    return out


@dataclass
class ImportReport:
    total: int = 0
    with_glyphs: int = 0
    aligned: int = 0
    dropped_lacuna: int = 0
    dropped_unreadable: int = 0
    dropped_empty_group: int = 0
    dropped_mismatch: int = 0
    dropped_empty_transcription: int = 0
    dropped_unsearchable: int = 0
    text_only: int = 0
    unknown_codes: collections.Counter = field(default_factory=collections.Counter)
    mismatch_samples: list[tuple[str, str, int, int]] = field(default_factory=list)


def convert(frame: pd.DataFrame, include_text_only: bool) -> tuple[pd.DataFrame, ImportReport]:
    report = ImportReport(total=len(frame))
    rows: list[dict] = []
    for index, record in enumerate(frame.itertuples(index=False)):
        transcription = to_corpus_convention(record.transcription or "")
        if not transcription:
            report.dropped_empty_transcription += 1
            continue
        if not search_fold(transcription):
            # A reading that folds to nothing (the bare interjection `ꞽ`) can never be
            # reached by a transliteration query, and the loader's reachability test
            # rightly refuses such a row. Six sentences in this export, one of them
            # net-new; the others duplicate rows already dropped for the same reason.
            report.dropped_unsearchable += 1
            continue
        glyph_field = str(record.hieroglyphs or "").strip()
        if not glyph_field:
            report.text_only += 1
            if include_text_only:
                rows.append(to_schema(index, transcription, record.translation, ""))
            continue
        report.with_glyphs += 1
        parsed = parse_glyph_field(glyph_field)
        report.unknown_codes.update(parsed.unknown_codes)
        if parsed.lacuna:
            report.dropped_lacuna += 1
            continue
        if parsed.unreadable:
            report.dropped_unreadable += 1
            continue
        if not parsed.groups:
            report.dropped_empty_group += 1
            continue
        tokens = transcription.split()
        if len(parsed.groups) != len(tokens):
            report.dropped_mismatch += 1
            if len(report.mismatch_samples) < 12:
                report.mismatch_samples.append(
                    (glyph_field[:160], transcription[:120], len(parsed.groups), len(tokens))
                )
            continue
        report.aligned += 1
        rows.append(to_schema(index, transcription, record.translation, " ".join(parsed.groups)))
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS), report


def deduplicate(frame: pd.DataFrame, existing: pd.DataFrame | None) -> tuple[pd.DataFrame, int, int]:
    """Drop rows already present — by yod-insensitive reading or by identical signs."""
    keys = frame["transliteration_gold"].map(dedup_key)
    glyphs = frame["hieroglyphs"].map(lambda v: normalize_hieroglyphs(v) if v else "")
    before = len(frame)
    internal = ~(keys.duplicated() | (glyphs.ne("") & glyphs.duplicated()))
    frame, keys, glyphs = frame[internal], keys[internal], glyphs[internal]
    internal_dropped = before - len(frame)
    if existing is None or existing.empty:
        return frame, internal_dropped, 0
    seen_keys = set(existing["transliteration_gold"].map(dedup_key))
    seen_glyphs = {
        g for g in existing["hieroglyphs"].map(lambda v: normalize_hieroglyphs(v) if v else "")
        if g
    }
    keep = ~(keys.isin(seen_keys) | (glyphs.ne("") & glyphs.isin(seen_glyphs)))
    return frame[keep], internal_dropped, int((~keep).sum())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--parquet", default=str(RAW_PARQUET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--existing", default=str(EXAMPLES), help="Corpus to deduplicate against; '' to skip.")
    parser.add_argument("--append", action="store_true", help="Append the new rows to --existing.")
    parser.add_argument("--include-text-only", action="store_true", help="Also import rows without hieroglyphs.")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    parquet = Path(args.parquet)
    if not parquet.exists():
        parquet.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {PARQUET_URL} -> {parquet}")
        import urllib.request

        urllib.request.urlretrieve(PARQUET_URL, parquet)

    started = time.time()
    raw = pd.read_parquet(parquet)
    if args.limit:
        raw = raw.head(args.limit)
    frame, report = convert(raw, include_text_only=args.include_text_only)

    existing = None
    if args.existing:
        path = Path(args.existing)
        if path.exists():
            existing = pd.read_csv(path, dtype=str).fillna("")
    frame, internal_dupes, existing_dupes = deduplicate(frame, existing)

    print(f"rows in export                 {report.total:>8,}")
    print(f"  with hieroglyphs             {report.with_glyphs:>8,}")
    print(f"    aligned one-to-one         {report.aligned:>8,}")
    print(f"    dropped: lacuna //         {report.dropped_lacuna:>8,}")
    print(f"    dropped: unreadable sign   {report.dropped_unreadable:>8,}")
    print(f"    dropped: empty group       {report.dropped_empty_group:>8,}")
    print(f"    dropped: count mismatch    {report.dropped_mismatch:>8,}")
    print(f"  text only (no hieroglyphs)   {report.text_only:>8,}  {'included' if args.include_text_only else 'skipped (--include-text-only)'}")
    print(f"  empty transcription          {report.dropped_empty_transcription:>8,}")
    print(f"  unsearchable reading         {report.dropped_unsearchable:>8,}")
    print(f"duplicates within the export   {internal_dupes:>8,}")
    print(f"already in {Path(args.existing).name if args.existing else '-':<19} {existing_dupes:>8,}")
    print(f"NET NEW                        {len(frame):>8,}")
    if report.unknown_codes:
        print("codes without a Unicode sign (placeholders):", report.unknown_codes.most_common(15))
    if report.mismatch_samples:
        print("\nmismatch samples (groups vs tokens):")
        for glyphs, text, g, t in report.mismatch_samples:
            print(f"  {g}≠{t}  {glyphs}\n        {text}")
    print(f"\nconverted in {time.time() - started:.1f}s")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    print(f"wrote {len(frame)} rows to {output}")

    if args.append and existing is not None:
        combined = pd.concat([existing, frame.astype(str)], ignore_index=True)[REQUIRED_COLUMNS]
        combined.to_csv(args.existing, index=False)
        print(f"appended to {args.existing}: {len(existing):,} -> {len(combined):,} rows")


if __name__ == "__main__":
    main()

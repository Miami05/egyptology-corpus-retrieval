"""Import the Ramses Transliteration Corpus (Rosmorduc, Universite de Liege/Projet
Ramses, V. 2019-09-01).

What it is. A parallel corpus of Late Egyptian sentences built mechanically from the
Ramses project's own annotation database, released to train the accompanying
transliteration network: `src-*.txt` (one line per sentence, whitespace-separated
Gardiner codes), `src-sep-*.txt` (the same, with `_` marking word boundaries in the
glyph stream) and `tgt-*.txt` (the transliteration, tokenised one *character* per
space-separated token, `_` marking word boundaries). 73,992 sentences across five
splits (train/val/test/ctest/htest).

Licence: CC BY-NC-SA 4.0 (the archive's own README, not Zenodo's metadata field,
which mislabels it). Output goes to `data/private/ramses.csv`, which must never be
committed.

Why word alignment is NOT trusted globally. The README says outright: "transliterations
are standardised according to what is grammatically expected" — a word can be present
in the transliteration with no corresponding sign at all (an unwritten genitival `n`,
a supplied `m`), and `src-sep`'s glyph-side `_` count disagrees with the transliteration's
word count in 28,629 of 73,992 lines (38.7%) for exactly that reason. Where the counts
*do* agree (61.3%), spot checks confirm the pairing is correct and not a coincidence —
e.g. `M17 G17` (i + m) aligned to the word `m`, a documented Late Egyptian habit of
writing the preposition `m` with a redundant phonetic complement. So alignment is
built per row, gated on an objective count check exactly like the BBAW/AES importers,
never guessed: rows where the count agrees AND no glyph-side lacuna marker is present
become aligned rows; every other row with clean transliteration becomes text-only
(glyphs kept as raw Gardiner-code text in `hieroglyphs`, which normalises to "" so the
loader counts it as text-only, never misaligned); rows whose *transliteration* itself
contains a lacuna are dropped outright, because "LACUNA" as literal text is not a
reading.

Transliteration-side lacuna markers, all three drop the row:
  - a whole word equal to `LACUNA` (or `MISSING`, not observed but checked defensively)
  - the bracket convention `[_]` (an indeterminate-length lacuna; ambiguous with the
    word-boundary `_` at the character level, so it is detected on the *raw* token
    stream before any word-splitting is attempted)
  - a word made only of `/` characters (`//`, `///`, ...; a fraction like `1/2` is not
    a lacuna and is kept)

Glyph-side lacuna markers (`LACUNA`, `MISSING`, `SHADED1/2/3`) do not drop a row — they
only disqualify it from word alignment, falling back to text-only, per the rules.

Character inventory. Verified over all five splits' `tgt-*.txt` (masking out the
`LACUNA` token spelled `L A C U N A`): every character is in the expected MdC set
(`A a i H x X S T D q k g t d b p f m n r h z s w y . - = ( ) [ ] < > / 0-9 ?`) with a
handful of rare exceptions, all traced to specific, harmless causes (see the module
docstring continuation in the importer's report and the final task report): 19 `j`
(an alternate spelling of the yod inside the editorial `n(j)` genitive marker — folded
to the same sign as `i`), 5 `I` (capitalised yod in a proper name, mirrors the BBAW
importer's `J` -> `Ꞽ`), 131 `l` and 52 `+` (Ramses's own `+name+l` wrapper around a
handful of foreign/hypocoristic personal names — meaning unclear, kept verbatim), 2 `e`
and 2 `u` and the single instance of `F` outside `[_]` (all inside the Hittite name
`tili-tesub` in the Ramses-Hittite treaty text; kept verbatim as a literal proper noun
spelling), 1 `o` (kept verbatim). None of these are dropped or special-cased beyond
"leave the character as written" — see `RAMSES_CHAR_MAP`.

    python scripts/import_ramses.py                       # measure only
    python scripts/import_ramses.py --append               # append to --existing
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import REQUIRED_COLUMNS, alignment_report  # noqa: E402
from app.data.normalizer import normalize_hieroglyphs, search_fold  # noqa: E402
from scripts.import_bbaw_egyptian import (  # noqa: E402
    dedup_key,
    deduplicate,
    sign_for_code,
)

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ramses" / "ramses-trl" / "data"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "private" / "ramses.csv"
EXAMPLES = PROJECT_ROOT / "data" / "processed" / "examples.csv"

SOURCE = "Ramses"
VERSION = "2019-09-01"
ALL_SPLITS = ["train", "val", "test", "ctest", "htest"]
GRAMMAR_NOTE = (
    "Ramses transliteration is normalised to the expected grammatical form, not the "
    "attested spelling."
)

# ---------------------------------------------------------------------------
# MdC ASCII (Ramses tgt convention) -> TLA transliteration
# ---------------------------------------------------------------------------

# The yod is already written `i` in this corpus (not `j`, as BBAW/AES write it), so it
# maps straight to `ꞽ`. The rare `j` (19 occurrences, always inside the editorial
# `n(j)` genitive marker) is folded to the same sign — it is the same letter, just an
# alternate spelling of the same editorial convention `normalize_transliteration`
# already strips via `PARENTHESISED_YOD_RE`. `I`, capitalised, mirrors BBAW's `J` ->
# `Ꞽ` for a proper name. Everything else in `q k g t d b p f m n r h z s w y` and the
# rare foreign-name letters `l + e u o F` is left exactly as written: `q k g t d b p f
# m n r h z s w y` are already the corpus's own ASCII spelling for those letters, and
# `l + e u o F` have no defined TLA equivalent (see module docstring) so are kept
# verbatim rather than guessed at.
RAMSES_CHAR_MAP: dict[str, str] = {
    "A": "ꜣ",
    "a": "ꜥ",
    "i": "ꞽ",
    "j": "ꞽ",
    "H": "ḥ",
    "x": "ḫ",
    "X": "ẖ",
    "S": "š",
    "T": "ṯ",
    "D": "ḏ",
    "I": "Ꞽ",
}
_RAMSES_TABLE = str.maketrans(RAMSES_CHAR_MAP)


def convert_word(word: str) -> str:
    """One MdC-ASCII transliteration word -> the corpus's TLA convention."""
    return word.translate(_RAMSES_TABLE)


# ---------------------------------------------------------------------------
# tgt parsing: character-per-token stream, `_` = word boundary
# ---------------------------------------------------------------------------


def has_bracket_lacuna(tokens: list[str]) -> bool:
    """True when the raw token stream contains the literal 3-token run `[ _ ]`.

    This is the MdC convention for an indeterminate-length lacuna. It must be
    detected on the *raw* tokens, before any word-splitting: the `_` inside it is a
    literal character, not a word-boundary marker, and the two are indistinguishable
    once the stream has been rejoined and split on `_`.
    """
    for i in range(len(tokens) - 2):
        if tokens[i] == "[" and tokens[i + 1] == "_" and tokens[i + 2] == "]":
            return True
    return False


def rejoin_words(tokens: list[str]) -> list[str]:
    """Rejoin the per-character tgt tokens and split on `_`, the word boundary.

    Only safe once `has_bracket_lacuna` has ruled out the one pattern where a literal
    `_` character (inside `[_]`) would be mistaken for a boundary.
    """
    text = "".join(tokens)
    return [w for w in text.split("_") if w]


def is_translit_lacuna_word(word: str) -> bool:
    """A whole transliteration word that is itself a lacuna marker."""
    if word in ("LACUNA", "MISSING"):
        return True
    return bool(word) and set(word) == {"/"}


# ---------------------------------------------------------------------------
# src-sep parsing: whole Gardiner codes, `_` its own token marking a word boundary
# ---------------------------------------------------------------------------

GLYPH_LACUNA_CODES = {"LACUNA", "MISSING"}


def is_glyph_lacuna_code(code: str) -> bool:
    return code in GLYPH_LACUNA_CODES or code.startswith("SHADED")


def group_src_sep(tokens: list[str]) -> list[list[str]]:
    """Gardiner codes from a src-sep line, grouped into one list per word."""
    groups: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token == "_":
            if current:
                groups.append(current)
                current = []
        else:
            current.append(token)
    if current:
        groups.append(current)
    return groups


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def content_id(split: str, lineno: int, transliteration: str, hieroglyphs: str) -> str:
    """A stable id derived from the row's own content, prefixed `RAMSES_`.

    Depends on the split, the line number *within that split* (the corpus's own
    stable handle — line order in the release archive does not change) and the two
    text fields, so a re-run always assigns the same id to the same sentence.
    """
    parts = [
        f"split={split}",
        f"line={lineno}",
        f"transliteration_gold={transliteration}",
        f"hieroglyphs={hieroglyphs}",
    ]
    digest = hashlib.blake2b("\x1f".join(parts).encode("utf-8"), digest_size=6)
    return f"RAMSES_{digest.hexdigest().upper()}"


def to_schema(
    split: str, lineno: int, transliteration: str, hieroglyphs: str
) -> dict:
    text_id = content_id(split, lineno, transliteration, hieroglyphs)
    out = {column: "" for column in REQUIRED_COLUMNS}
    out.update(
        {
            "source": SOURCE,
            "source_text_id": text_id,
            "source_sentence_id": f"S_{split}_{lineno:06d}",
            "language_stage": "Late Egyptian",
            "script_type": "hieroglyphic/hieratic",
            "genre": "unknown",
            "period": "New Kingdom",
            "hieroglyphs": hieroglyphs,
            "mdc": "",
            "sign_sequence": transliteration,
            "transliteration_gold": transliteration,
            "translation": "",
            "grammar_notes": GRAMMAR_NOTE,
            "source_ref": f"ramses-trl {VERSION} {split} line {lineno}",
            "review_status": "seed",
            "display_sequence": hieroglyphs,
            "aesthetic_arrangement_flag": False,
        }
    )
    return out


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


@dataclass
class ImportReport:
    total: int = 0
    dropped_bracket_lacuna: int = 0
    dropped_word_lacuna: int = 0
    dropped_slash_lacuna: int = 0
    dropped_empty_transliteration: int = 0
    dropped_unsearchable: int = 0
    aligned: int = 0
    text_only_count_mismatch: int = 0
    text_only_glyph_lacuna: int = 0
    unknown_codes: collections.Counter = field(default_factory=collections.Counter)

    @property
    def text_only(self) -> int:
        return self.text_only_count_mismatch + self.text_only_glyph_lacuna

    @property
    def dropped_translit_lacuna(self) -> int:
        return (
            self.dropped_bracket_lacuna
            + self.dropped_word_lacuna
            + self.dropped_slash_lacuna
        )


def _iter_split_lines(raw_dir: Path, split: str):
    src_path = raw_dir / f"src-{split}.txt"
    srcsep_path = raw_dir / f"src-sep-{split}.txt"
    tgt_path = raw_dir / f"tgt-{split}.txt"
    with src_path.open(encoding="utf-8") as fsrc, srcsep_path.open(
        encoding="utf-8"
    ) as fsep, tgt_path.open(encoding="utf-8") as ftgt:
        for lineno, (sline, ssline, tline) in enumerate(
            zip(fsrc, fsep, ftgt), start=1
        ):
            yield lineno, sline.strip().split(), ssline.strip().split(), tline.strip().split()


def convert(raw_dir: Path, splits: list[str], limit: int = 0) -> tuple[pd.DataFrame, ImportReport]:
    report = ImportReport()
    rows: list[dict] = []
    for split in splits:
        for lineno, stoks, sstoks, ttoks in _iter_split_lines(raw_dir, split):
            report.total += 1

            if has_bracket_lacuna(ttoks):
                report.dropped_bracket_lacuna += 1
                continue

            words_raw = rejoin_words(ttoks)
            if not words_raw:
                report.dropped_empty_transliteration += 1
                continue

            if any(w in ("LACUNA", "MISSING") for w in words_raw):
                report.dropped_word_lacuna += 1
                continue
            if any(w and set(w) == {"/"} for w in words_raw):
                report.dropped_slash_lacuna += 1
                continue

            transliteration = " ".join(convert_word(w) for w in words_raw)
            if not search_fold(transliteration):
                report.dropped_unsearchable += 1
                continue

            groups = group_src_sep(sstoks)
            count_matches = len(groups) == len(words_raw)
            glyph_lacuna = any(
                is_glyph_lacuna_code(code) for group in groups for code in group
            )

            if count_matches and not glyph_lacuna:
                sign_groups = []
                for group in groups:
                    signs = []
                    for code in group:
                        sign = sign_for_code(code)
                        if sign.startswith("<g>"):
                            report.unknown_codes[code] += 1
                        signs.append(sign)
                    sign_groups.append("".join(signs))
                hieroglyphs_field = " ".join(sign_groups)
                report.aligned += 1
            else:
                # Text-only: the raw (unsegmented) Gardiner-code line, kept verbatim
                # for a specialist to read, comma-joined rather than space-joined.
                # Space-joining would backfire: `normalize_hieroglyphs`'s
                # `BARE_GARDINER_TOKEN_RE` treats a whitespace-bounded Gardiner-shaped
                # ASCII token (`N35`, `F20`, ...) exactly like `<g>N35</g>` markup and
                # turns each one into its own placeholder sign, one group per
                # *individual sign* instead of per word — the opposite of empty, and
                # guaranteed to misalign against the much shorter transliteration. A
                # comma is not whitespace, so the same regex's `(?<!\S)`/`(?!\S)`
                # boundaries never match for any *interior* token. The first and last
                # token are still bounded by the string's edges, which the same
                # lookarounds treat as whitespace — a lone code, or a list of exactly
                # one, still matched and came back non-empty (2 rows, caught by the
                # alignment check below). Wrapping the whole field in a non-whitespace
                # sentinel removes that edge case too: every token, including the
                # first and last, now has a non-whitespace neighbour, so nothing in
                # the field falls inside `BARE_GARDINER_TOKEN_RE`'s boundaries. Every
                # character then falls through `NON_GROUP_CHAR_RE` and becomes a
                # space, and the field reduces to "" — a text-only row, never a
                # misaligned one.
                hieroglyphs_field = "|" + ",".join(stoks) + "|"
                if not count_matches:
                    report.text_only_count_mismatch += 1
                else:
                    report.text_only_glyph_lacuna += 1

            rows.append(to_schema(split, lineno, transliteration, hieroglyphs_field))
            if limit and len(rows) >= limit:
                return pd.DataFrame(rows, columns=REQUIRED_COLUMNS), report

    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS), report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--existing", default=str(EXAMPLES), help="Corpus to deduplicate against; '' to skip."
    )
    parser.add_argument(
        "--splits",
        default=",".join(ALL_SPLITS),
        help=f"Comma-separated splits to import (default: all of {ALL_SPLITS}).",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--append", action="store_true", help="Append the new rows to --existing.")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    splits = [s.strip() for s in args.splits.split(",") if s.strip()]

    started = time.time()
    frame, report = convert(raw_dir, splits, limit=args.limit)

    existing = None
    if args.existing:
        path = Path(args.existing)
        if path.exists():
            existing = pd.read_csv(path, dtype=str).fillna("")
    frame, internal_dupes, existing_dupes = deduplicate(frame, existing)

    print(f"splits imported                {','.join(splits)}")
    print(f"rows read                      {report.total:>8,}")
    print(f"  dropped: translit lacuna     {report.dropped_translit_lacuna:>8,}")
    print(f"    [_] bracket lacuna         {report.dropped_bracket_lacuna:>8,}")
    print(f"    LACUNA/MISSING word        {report.dropped_word_lacuna:>8,}")
    print(f"    // slash-run word          {report.dropped_slash_lacuna:>8,}")
    print(f"  dropped: empty transliteration {report.dropped_empty_transliteration:>6,}")
    print(f"  dropped: unsearchable reading {report.dropped_unsearchable:>7,}")
    print(f"  kept                         {report.aligned + report.text_only:>8,}")
    print(f"    aligned (sign groups)      {report.aligned:>8,}")
    print(f"    text-only, total           {report.text_only:>8,}")
    print(f"      count mismatch           {report.text_only_count_mismatch:>8,}")
    print(f"      glyph-side lacuna        {report.text_only_glyph_lacuna:>8,}")
    print(f"duplicates within the import    {internal_dupes:>8,}")
    print(f"already in {Path(args.existing).name if args.existing else '-':<19} {existing_dupes:>8,}")
    print(f"NET NEW                         {len(frame):>8,}")
    if report.unknown_codes:
        print("codes without a Unicode sign (placeholders), top 20:", report.unknown_codes.most_common(20))
        print("distinct unresolved codes:", len(report.unknown_codes))
    print(f"\nconverted in {time.time() - started:.1f}s")

    align = alignment_report(
        frame.assign(hieroglyphs_norm=frame["hieroglyphs"].map(lambda v: normalize_hieroglyphs(v) if v else ""))
    )
    print(
        f"\nalignment check on the produced frame: total={align.total_rows} "
        f"misaligned={align.misaligned_rows} text_only={align.text_only_rows} "
        f"usable={align.usable_rows}"
    )
    if align.misaligned_rows:
        print("MISALIGNED ROWS FOUND (should be 0):", align.misaligned_indices[:20])

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    print(f"\nwrote {len(frame)} rows to {output}")

    if args.append and existing is not None:
        combined = pd.concat([existing, frame.astype(str)], ignore_index=True)[REQUIRED_COLUMNS]
        combined.to_csv(args.existing, index=False)
        print(f"appended to {args.existing}: {len(existing):,} -> {len(combined):,} rows")


if __name__ == "__main__":
    main()

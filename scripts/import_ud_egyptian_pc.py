"""Build candidate corpus rows from the UD_Egyptian-PC treebank (Pyramid Texts).

What it is. Universal Dependencies' Egyptian-PC treebank (University of Jaén; Roberto
Antonio Díaz Hernández with Bruno Guillaume and Daniel Zeman), v2.18: 3,089 sentences
/ 34,234 tokens of the Pyramid Texts, manually annotated. Each sentence carries
`# spell`, `# section` (Sethe's §), `# king` (the witness pyramid), `# edition`
(Sethe or Allen) and `# TLA` (one or more TLA sentence ids); each token carries
`Hiero=` (the Unicode signs, with RES-like `:`/`()` grouping), `ID=` (the TLA lemma
id, sometimes suffixed `_Add` for an unwritten token or `_Rest` for a restored one).

Licence: CC BY-SA 4.0 (README "License: CC BY-SA 4.0" and LICENSE.txt) — the same
licence as examples.csv, so the rows may join the public corpus with attribution.

Transcription. The treebank writes the Tübingen system (Schenkel), not the TLA/Berlin
convention the corpus uses. The mapping is explicit and one-to-one on the signs, from
the README's own table:

    Tübingen  sign  TLA        note
    s         𓊃     z          the door bolt: TLA keeps it as `z` in Old Egyptian
    ś         𓋴     s          the folded cloth: TLA `s`
    č         𓍿     ṯ
    ṭ         𓂧     d
    č̣         𓆓     ḏ          č + combining dot below (U+0323)
    ḳ         𓈎     q
    ⸗         —     =          suffix-pronoun marker

`s` and `ś` are two different signs and stay two different TLA letters (`z`, `s`);
nothing here merges them. Every other letter (ꜣ ꞽ y ꜥ w b p f m n r h ḥ ḫ ẖ š k g t)
is the same in both systems and passes through. Three notation marks are mapped too:
the half brackets `˹ ˺` (partly damaged sign) become TLA's `⸢ ⸣`, and the combining
minus sign below (U+0320) under a capital `H` becomes the macron below (U+0331) that
the corpus writes for capital `H̱`. The `|` line-divider tokens (`LINE=Punct`) are
dropped.

Tokens. A UD multiword-token range line (`5-7  Nfr-kꜣ-Rꜥw`) is the surface word and
carries its own Hiero and lemma id; its component words are skipped, which matches
TLA's tokenisation of compounds and names.

`Hiero=No` marks a token with no signs on the monument. Only a *supplied suffix
pronoun* — a form that is `⸗x` once its editorial brackets `( ) < > [ ]` are set
aside, e.g. `(⸗ꞽ)`, `<⸗k>`, `[⸗f]` — is glued onto the previous word without a space,
exactly as TLA writes `kꜣ(=ꞽ)`. Every other `Hiero=No` token is a whole word the editor
supplies or restores (`<m>`, `[mṭw]`, `Nb.t-ḥw.t`, `[4]`): it stays a separate word,
and since it has no signs the row's glyph alignment is unavailable.

A row is *aligned* (hieroglyphs filled) only when every surface word has at least one
sign in the Unicode hieroglyph ranges **and** no token's `Hiero=` value carries a
marker for an unknown or missing sign (`UC_No`, `Lost`, `...`, an unencoded code point
written as `139CA` / `UC142E4`, or any other residue once the signs, the grouping and
editorial notation `: ( ) [ ] { } < > ˹ ˺ * $ §` and the variation-selector notes
`_FE00`..`_FE0F` are removed). Such rows keep `glyphs_incomplete = True`; the signs are
never silently stripped into an apparently complete sequence. `alignment_issue` names
every reason a row is text-only (`unwritten_word`, `unknown_sign`, `no_signs`,
`lacuna`). `[...]` (an unrestored lacuna) is flagged, not dropped.

Overlap with examples.csv, in order:
    duplicate_tla_id   one of the sentence's TLA ids is an AES row's sentence id
    duplicate_strict   same reading under the corpus's strict identity key
    duplicate_fold     same reading under the ASCII search fold
    overlap_partial    the UD reading is inside a corpus row, or a corpus row of
                       >= 3 words is inside the UD reading (search fold, word-bounded)
    unmatched_by_current_rules   none of the above (not "new": see the flags below)

Independent flags, set on every row whatever its status:
    glyph_overlap      the row's signs, all spacing and grouping removed, equal some
                       corpus row's signs (spacing-insensitive)
    lemma_overlap      the row's TLA lemma-id sequence equals some corpus row's
    repeated_in_candidates   the strict reading occurs more than once in this file
A row is unmatched on every axis only when its status is unmatched_by_current_rules
and both overlap flags are False; the script prints that count separately.

Output is a candidate CSV with the examples.csv schema plus `citation` (PT spell/§,
witness, edition), `ud_sent_id`, `tla_sentence_ids`, `overlap_status`, `glyph_overlap`,
`lemma_overlap`, `repeated_in_candidates`, `has_lacuna`, `glyphs_incomplete`,
`alignment_issue` and `aligned`. It never writes examples.csv; the lead decides what joins.

    python -I scripts/import_ud_egyptian_pc.py --raw-dir data/raw/ud_egyptian_pc/repo \
        --output data/processed/ud_egyptian_pc_candidates.csv
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
import unicodedata
from bisect import bisect_right
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import REQUIRED_COLUMNS  # noqa: E402
from app.data.normalizer import search_fold  # noqa: E402
from app.services.suggestions import strict_reading_key  # noqa: E402

EXAMPLES = PROJECT_ROOT / "data" / "processed" / "examples.csv"
SOURCE = "UD_Egyptian-PC"
VERSION = "2.18"
SPLITS = ["train", "dev", "test"]

EXTRA_COLUMNS = [
    "citation", "ud_sent_id", "tla_sentence_ids", "overlap_status", "glyph_overlap", "lemma_overlap",
    "repeated_in_candidates", "has_lacuna", "glyphs_incomplete", "alignment_issue", "aligned",
]
UNMATCHED = "unmatched_by_current_rules"
STATUSES = ["duplicate_tla_id", "duplicate_strict", "duplicate_fold", "overlap_partial", UNMATCHED]

# NFC Tübingen -> TLA. `č` followed by U+0323 is handled in `tuebingen_to_tla`.
TUEBINGEN_TO_TLA: dict[str, str] = {
    "s": "z",
    "S": "Z",
    "ś": "s",
    "Ś": "S",
    "č": "ṯ",
    "Č": "Ṯ",
    "ṭ": "d",
    "Ṭ": "D",
    "ḳ": "q",
    "Ḳ": "Q",
    "⸗": "=",
    # Not letters but notation: the treebank's half brackets for a partly damaged
    # sign and its "minus sign below" under a capital H are TLA's ⸢ ⸣ and the macron
    # below (`H̱`, capital ẖ, which has no precomposed form).
    "˹": "⸢",
    "˺": "⸣",
    "\u0320": "\u0331",
}
DOTTED_C = {"č": "ḏ", "Č": "Ḏ"}  # č̣ / Č̣ = c-caron + U+0323
COMBINING_DOT_BELOW = "̣"


def tuebingen_to_tla(text: str) -> str:
    """Tübingen transcription -> the corpus's TLA convention (see module docstring)."""
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch in DOTTED_C and nxt == COMBINING_DOT_BELOW:
            out.append(DOTTED_C[ch])
            i += 2
            continue
        out.append(TUEBINGEN_TO_TLA.get(ch, ch))
        i += 1
    return unicodedata.normalize("NFC", "".join(out))


def is_hieroglyph(ch: str) -> bool:
    cp = ord(ch)
    return 0x13000 <= cp <= 0x1342F or 0x13460 <= cp <= 0x143FF


# A MISC field that lost its `|` separator runs straight into the next key
# (`Hiero=𓆑ID=10050`, `Hiero=𓏤Hierocl=𓏤`); the value ends where that key starts.
_RUN_ON_KEY_RE = re.compile(r"(?:Hierocl|ID|MWE|LINE)=")
# Notation that is not a sign and not a gap: RES-like grouping, editorial brackets
# (restored `[]`, superfluous `{}`, omitted `<>`, damaged `˹˺`), `*`, `$`/`§` notes,
# and variation-selector notes (`_FE00`, ` FE01`).
_GLYPH_NOTATION_RE = re.compile(r"[ _]?FE0[0-9A-F]|[:()\[\]{}<>˹˺*$§\s]")


def hiero_value(value: str) -> str:
    """The `Hiero=` value proper: a doubled `Hiero=` prefix and a run-on next key removed."""
    if value.startswith("Hiero="):
        value = value[len("Hiero="):]
    return _RUN_ON_KEY_RE.split(value, maxsplit=1)[0]


def hiero_signs(value: str) -> str:
    """Keep only hieroglyph code points from a `Hiero=` value (drops `:`, `()`, `[]`).

    Unknown-sign markers such as `UC_No` are dropped here too, so callers must check
    `hiero_unknown` first: an empty or shortened result is not a complete reading.
    """
    return "".join(ch for ch in hiero_value(value) if is_hieroglyph(ch))


def hiero_unknown(value: str) -> str:
    """What a `Hiero=` value holds besides signs and notation: `UC_No`, `Lost`, `...`,
    an unencoded code point (`139CA`), stray text. Empty means every sign is encoded."""
    rest = "".join(ch for ch in hiero_value(value) if not is_hieroglyph(ch))
    return _GLYPH_NOTATION_RE.sub("", rest)


def is_supplied_suffix(form: str) -> bool:
    """`(⸗ꞽ)`, `<⸗k>`, `[(⸗ꞽ)]`: a suffix pronoun once editorial brackets are set aside."""
    return form.strip("()<>[]").startswith("⸗")


def parse_misc(misc: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if misc in ("", "_"):
        return out
    for part in misc.split("|"):
        key, _, val = part.partition("=")
        out[key] = val
    return out


def parse_conllu(text: str) -> list[dict]:
    """Sentences as dicts: comments plus a list of *surface* tokens."""
    sentences: list[dict] = []
    meta: dict[str, str] = {}
    lines: list[list[str]] = []

    def flush() -> None:
        if meta or lines:
            sentences.append({"meta": dict(meta), "surface": surface_tokens(lines)})
        meta.clear()
        lines.clear()

    for raw in text.splitlines():
        if not raw.strip():
            flush()
            continue
        if raw.startswith("#"):
            key, sep, val = raw[1:].partition("=")
            if sep:
                meta[key.strip()] = val.strip()
            continue
        cols = raw.split("\t")
        if len(cols) == 10:
            lines.append(cols)
    flush()
    return sentences


def surface_tokens(lines: list[list[str]]) -> list[dict]:
    """Collapse multiword ranges to one surface token; drop empty nodes (`3.1`)."""
    covered: set[str] = set()
    out: list[dict] = []
    for cols in lines:
        tid = cols[0]
        if "." in tid:
            continue
        if "-" in tid:
            start, end = (int(x) for x in tid.split("-"))
            covered.update(str(n) for n in range(start, end + 1))
            parts = [c for c in lines if c[0].isdigit() and start <= int(c[0]) <= end]
            upos = "+".join(dict.fromkeys(c[3] for c in parts if c[3] != "_")) or "X"
            out.append({"form": cols[1], "upos": upos, "misc": parse_misc(cols[9])})
            continue
        if tid in covered:
            continue
        out.append({"form": cols[1], "upos": cols[3], "misc": parse_misc(cols[9])})
    return out


def lemma_id(misc: dict[str, str]) -> str:
    """`ID=10030_Add` -> `10030`; keeps a non-numeric id as written."""
    raw = misc.get("ID", "")
    return raw.split("_", 1)[0]


def build_row(sentence: dict, split: str) -> dict:
    meta = sentence["meta"]
    words: list[str] = []
    glyphs: list[str] = []
    lemmas: list[str] = []
    upos: list[str] = []
    lemma_ids: list[str] = []
    issues: list[str] = []
    for tok in sentence["surface"]:
        if tok["upos"] == "PUNCT" and tok["misc"].get("LINE") == "Punct":
            continue  # `|`, the treebank's line divider in offering lists: not a word
        raw_form = tok["form"]
        form = tuebingen_to_tla(raw_form)
        hiero = tok["misc"].get("Hiero", "")
        if hiero == "No" and words and is_supplied_suffix(raw_form):
            words[-1] += form  # TLA glues an editorial suffix: kꜣ(=ꞽ)
        else:
            words.append(form)
            if hiero == "No":
                issues.append("unwritten_word")  # a supplied/restored whole word: no signs
            elif hiero_unknown(hiero):
                issues.append("unknown_sign")
            signs = hiero_signs(hiero) if hiero != "No" else ""
            if not signs:
                issues.append("no_signs")
            glyphs.append(signs)
        lid = lemma_id(tok["misc"])
        lemmas.append(f"{lid}|{form}" if lid else form)
        lemma_ids.append(lid if lid.isdigit() else "?")
        upos.append(tok["upos"])
    translit = " ".join(words)
    has_lacuna = "[...]" in translit or "..." in translit
    if has_lacuna:
        issues.append("lacuna")
    issues = list(dict.fromkeys(issues))
    aligned = not issues
    hieroglyphs = " ".join(glyphs) if aligned else ""
    spell, section, king = meta.get("spell", ""), meta.get("section", ""), meta.get("king", "")
    edition = meta.get("edition", "")
    citation = f"PT {spell} §{section} ({king}; {edition} ed.)" if edition == "Sethe" else (
        f"PT {spell} {section} ({king}; {edition} ed.)"
    )
    sid = meta.get("sent_id", "")
    row = {col: "" for col in REQUIRED_COLUMNS}
    row.update(
        {
            "source": SOURCE,
            "source_text_id": f"UDPC_PT{spell}_{king}",
            "source_sentence_id": sid,
            "language_stage": "Earlier Egyptian",
            "script_type": "hieroglyphic/hieratic",
            "genre": "funerary literature",
            "period": "Old Kingdom",
            "hieroglyphs": hieroglyphs,
            "sign_sequence": translit,
            "transliteration_gold": translit,
            "lemma_sequence": " ".join(lemmas),
            "upos": " ".join(upos),
            "source_ref": f"UD_Egyptian-PC v{VERSION} egy_pc-ud-{split}.conllu#sent_id={sid}",
            "review_status": "seed",
            "display_sequence": hieroglyphs or translit,
            "aesthetic_arrangement_flag": "False",
            "citation": citation,
            "ud_sent_id": sid,
            "tla_sentence_ids": ";".join(x.strip() for x in meta.get("TLA", "").split(";") if x.strip()),
            "has_lacuna": str(has_lacuna),
            "glyphs_incomplete": str("unknown_sign" in issues),
            "alignment_issue": ";".join(issues),
            "aligned": str(aligned),
            # Overlap keys, not written out (the DataFrame keeps only the named columns).
            "_glyph_key": "".join(glyphs),
            "_lemma_key": " ".join(lemma_ids),
        }
    )
    return row


# ---------------------------------------------------------------------------
# overlap
# ---------------------------------------------------------------------------

AES_SENTENCE_RE = re.compile(r"sentence=([A-Za-z0-9_-]+)")


def glyph_key(value: str) -> str:
    """Signs only: spacing, layout controls and placeholders removed."""
    return "".join(ch for ch in value if is_hieroglyph(ch))


def lemma_key(value: str) -> str:
    """The lemma-id sequence of a `lemma_sequence` value (ids before `|`)."""
    return " ".join(tok.split("|", 1)[0] for tok in value.split())


def classify_overlap(rows: list[dict], corpus: pd.DataFrame) -> None:
    """Fill `overlap_status` and the independent overlap flags on each row in place.

    `corpus` needs `source`, `source_ref` and `transliteration_gold`; the glyph and
    lemma flags are computed when it also has `hieroglyphs` / `lemma_sequence`.
    """
    aes_ids = set(
        corpus.loc[corpus["source"] == "AES", "source_ref"].str.extract(AES_SENTENCE_RE)[0].dropna()
    )
    strict = set(corpus["transliteration_gold"].map(strict_reading_key))
    folds = [f for f in corpus["transliteration_gold"].map(search_fold) if f]
    fold_set = set(folds)
    big = "\n" + "\n".join(f" {f} " for f in folds) + "\n"

    ud_folds = [search_fold(r["transliteration_gold"]) for r in rows]
    # Corpus row (>= 3 words) inside a UD reading.
    joined_parts: list[str] = []
    starts: list[int] = []
    pos = 0
    for f in ud_folds:
        starts.append(pos)
        piece = f" {f} \n"
        joined_parts.append(piece)
        pos += len(piece)
    joined = "".join(joined_parts)
    contains_corpus_row: set[int] = set()
    for f in fold_set:
        if f.count(" ") < 2:
            continue
        needle = f" {f} "
        at = joined.find(needle)
        while at != -1:
            contains_corpus_row.add(bisect_right(starts, at) - 1)
            at = joined.find(needle, at + 1)

    corpus_glyphs = (
        {k for k in corpus["hieroglyphs"].map(glyph_key) if k} if "hieroglyphs" in corpus else set()
    )
    corpus_lemmas = (
        {k for k in corpus["lemma_sequence"].map(lemma_key) if k} if "lemma_sequence" in corpus else set()
    )
    strict_counts = collections.Counter(strict_reading_key(r["transliteration_gold"]) for r in rows)

    for i, row in enumerate(rows):
        g = row.get("_glyph_key", "")
        lk = row.get("_lemma_key", "")
        row["glyph_overlap"] = str(bool(g) and g in corpus_glyphs)
        row["lemma_overlap"] = str(bool(lk) and "?" not in lk.split() and lk in corpus_lemmas)
        row["repeated_in_candidates"] = str(strict_counts[strict_reading_key(row["transliteration_gold"])] > 1)
        tla_ids = [x for x in row["tla_sentence_ids"].split(";") if x]
        f = ud_folds[i]
        if any(t in aes_ids for t in tla_ids):
            status = "duplicate_tla_id"
        elif strict_reading_key(row["transliteration_gold"]) in strict:
            status = "duplicate_strict"
        elif f in fold_set:
            status = "duplicate_fold"
        elif (f and f" {f} " in big) or i in contains_corpus_row:
            status = "overlap_partial"
        else:
            status = UNMATCHED
        row["overlap_status"] = status


def convert(raw_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for split in SPLITS:
        path = raw_dir / f"egy_pc-ud-{split}.conllu"
        for sentence in parse_conllu(path.read_text(encoding="utf-8")):
            rows.append(build_row(sentence, split))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", required=True, help="Clone of UniversalDependencies/UD_Egyptian-PC")
    parser.add_argument("--output", required=True)
    parser.add_argument("--examples", default=str(EXAMPLES))
    args = parser.parse_args()
    out = Path(args.output).resolve()
    if out == EXAMPLES.resolve():
        sys.exit("refusing to overwrite examples.csv")
    if out == Path(args.examples).resolve():
        sys.exit("refusing to overwrite the --examples input")

    rows = convert(Path(args.raw_dir))
    corpus = pd.read_csv(
        args.examples, dtype=str, keep_default_na=False,
        usecols=["source", "source_ref", "transliteration_gold", "hieroglyphs", "lemma_sequence"],
    )
    classify_overlap(rows, corpus)
    df = pd.DataFrame(rows, columns=REQUIRED_COLUMNS + EXTRA_COLUMNS)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    status = collections.Counter(df["overlap_status"])
    print(f"sentences: {len(df)}")
    print(f"aligned: {(df['aligned'] == 'True').sum()}  text-only: {(df['aligned'] != 'True').sum()}  "
          f"with lacuna: {(df['has_lacuna'] == 'True').sum()}  "
          f"glyphs incomplete: {(df['glyphs_incomplete'] == 'True').sum()}")
    issues = collections.Counter(i for v in df["alignment_issue"] for i in v.split(";") if i)
    print(f"alignment issues (rows): {dict(issues)}")
    for k in STATUSES:
        print(f"{k}: {status.get(k, 0)}")
    nn = df[df["overlap_status"] == UNMATCHED]
    nl = nn[nn["has_lacuna"] != "True"]
    print(f"{UNMATCHED} without lacuna: {len(nl)}; aligned: {(nn['aligned'] == 'True').sum()}")
    print(f"  of those without lacuna: glyph_overlap {(nl['glyph_overlap'] == 'True').sum()}, "
          f"lemma_overlap {(nl['lemma_overlap'] == 'True').sum()}, "
          f"repeated_in_candidates {(nl['repeated_in_candidates'] == 'True').sum()}")
    every = nn[(nn["glyph_overlap"] != "True") & (nn["lemma_overlap"] != "True")]
    every_nl = every[every["has_lacuna"] != "True"]
    print(f"unmatched on all of strict, fold, glyph and lemma-id: {len(every)}; without lacuna: {len(every_nl)}; "
          f"distinct strict readings among those: {every_nl['transliteration_gold'].map(strict_reading_key).nunique()}; "
          f"aligned: {(every_nl['aligned'] == 'True').sum()}")
    chars = collections.Counter("".join(df["transliteration_gold"]))
    corpus_chars = set("".join(corpus["transliteration_gold"]))
    unseen = {c: n for c, n in chars.items() if c not in corpus_chars}
    print(f"characters not in the corpus transliteration inventory: {unseen}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

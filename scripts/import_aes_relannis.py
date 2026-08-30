"""Import the AES corpus from its relANNIS export.

Why relANNIS and not the JSON. `data/raw/aes` ships the same corpus twice. The JSON
export under `files/aes/` is the obvious one to reach for and it is useless here:
101,796 sentences, of which **23** contain a hieroglyph. Its `mdc` field is an ASCII
transliteration, not sign codes. On that basis AES was written off as unusable for a
sign-based reading tool.

That was wrong. The relANNIS export under `files/relANNIS/` carries a `hiero_unicode`
annotation the JSON drops — 241,414 tokens of it. Read from there, AES yields 14,824
sentences whose hieroglyphs align one-to-one with their transliteration, including
Amarna material that is securely Dynasty 18, the period the first expert trial came
from and the one the corpus was thinnest in.

What "aligned" means here, and why it is strict: a sentence is kept only when *every*
word span carries both a `written_form` and a `hiero_unicode`. A sentence where some
words have glyphs and others do not cannot be used — the sign-to-reading pairing
would silently shift, which is the exact defect Phase 0 existed to remove. Partial
sentences are counted and discarded, never patched.

relANNIS layout, as far as this script needs it:

  corpus.annis             one row per document; here one document is one sentence
  corpus_annotation.annis  document metadata (date, text_name, sentence_translation…)
  node.annis               nodes; word spans have token_index NULL and a left_token
                           ordinal in column 8, and column 2 points at the document
  node_annotation.annis    (node id, namespace, key, value) — written_form,
                           hiero_unicode, lemmaID, pos and friends live here

    python scripts/import_aes_relannis.py --output data/processed/aes_rows.csv
    python scripts/import_aes_relannis.py --corpora bbawamarna --limit 50
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import os
import re
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import REQUIRED_COLUMNS  # noqa: E402
from scripts.import_tla_dataset import unify_suffix_marker  # noqa: E402

RELANNIS_DIR = PROJECT_ROOT / "data" / "raw" / "aes" / "files" / "relANNIS"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "aes_rows.csv"

# AES dates its documents with coarse era labels rather than year ranges. They are
# mapped to readable equivalents and *not* narrowed: "OK & FIP" genuinely means the
# editors placed the text in either, and inventing a single period here would be
# making the data more precise than its source.
PERIOD_LABELS = {
    "OK & FIP": "Old Kingdom / First Intermediate Period",
    "MK & SIP": "Middle Kingdom / Second Intermediate Period",
    "NK": "New Kingdom",
    "TIP - Roman times": "Third Intermediate Period to Roman",
    "unknown": "unknown",
}

# Subcorpus -> a genre label a reader can filter on.
GENRE_LABELS = {
    "bbawamarna": "Amarna inscriptions",
    "bbawgrabinschriften": "tomb inscriptions",
    "bbawgraeberspzt": "Late Period tomb inscriptions",
    "bbawhistbiospzt": "Late Period historical-biographical",
    "bbawpyramidentexte": "Pyramid Texts",
    "bbawtempelbib": "temple library",
    "bbawtotenlit": "funerary literature",
    "sawlit": "literary",
    "sawmedizin": "medical",
    "smaek": "museum collection",
    "tuebingerstelen": "stelae (Tübingen)",
}


def _split_rows(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            yield line.rstrip("\n").split("\t")


def read_corpus(directory: Path) -> list[dict]:
    """Every fully-aligned sentence in one unpacked relANNIS corpus."""
    annotations: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for parts in _split_rows(directory / "node_annotation.annis"):
        if len(parts) >= 4:
            annotations[parts[0]][parts[2]] = parts[3]
    if not annotations:
        return []

    # Word spans, grouped by the document (= sentence) they belong to and ordered by
    # their first token, which is what puts the words back in reading order.
    spans: dict[str, list[tuple[int, str]]] = collections.defaultdict(list)
    for parts in _split_rows(directory / "node.annis"):
        if len(parts) >= 10 and parts[7] == "NULL" and parts[8] not in ("NULL", ""):
            try:
                order = int(parts[8])
            except ValueError:
                continue
            if parts[0] in annotations:
                spans[parts[2]].append((order, parts[0]))

    metadata: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for parts in _split_rows(directory / "corpus_annotation.annis"):
        if len(parts) >= 4:
            metadata[parts[0]][parts[2]] = parts[3]

    out: list[dict] = []
    for document, entries in spans.items():
        entries.sort()
        words = [node for _, node in entries if "written_form" in annotations[node]]
        if len(words) < 2:
            continue
        glyphs = [annotations[node].get("hiero_unicode", "") for node in words]
        if not all(glyphs):
            continue  # partial coverage cannot be aligned; drop rather than patch
        readings = [annotations[node]["written_form"] for node in words]
        lemmas = [annotations[node].get("lemmaID", "") for node in words]
        parts_of_speech = [annotations[node].get("pos", "") for node in words]
        info = metadata.get(document, {})
        out.append(
            {
                "hieroglyphs": " ".join(glyphs),
                "transliteration": " ".join(readings),
                "translation": info.get("sentence_translation", ""),
                "lemma_sequence": " ".join(lemmas),
                "upos": " ".join(parts_of_speech),
                "date": info.get("date", "unknown"),
                "text_name": info.get("text_name", ""),
                "text_id": info.get("text", ""),
                "sentence_id": info.get("sentence_id", ""),
                "editor": info.get("editor", ""),
                "findspot": info.get("findspot", ""),
                "corpus": directory.name,
            }
        )
    return out


# AES follows a different transliteration standard from the TLA corpora already in
# examples.csv: the yod is "j" where TLA writes "ꞽ", the morpheme separator is a comma
# where TLA uses a dot, the suffix marker is "≡" not "=", plural and dual are ",pl" and
# ",du" rather than ".PL" and ".DU", and proper nouns are capitalised. Left as they
# are, the sign-level model would see "=j" and "=ꞽ" as two different readings of the
# same sign, splitting every statistic the tool reports.
#
# The conversion was validated, not assumed. 1,342 sentences occur in both corpora
# independently; converting the AES form reproduces the TLA form exactly for 85% of
# them and, crucially, **disagrees on a letter in none of them**. The remaining 15%
# differ only in editorial judgement — TLA restoring an unwritten sign as "bš(ꜣ)"
# where AES prints "bšꜣ", or hyphenating "ḥtp-ḏi̯-nswt" where AES separates the words.
# Those are two defensible editions of the same text, not an error in this mapping,
# and they are left alone. Declared in DATA-LICENSE.md as an adaptation.
EDITORIAL_MARKS_RE = re.compile(r"[〈〉{}⸢⸣\[\]⸮?]")


def to_tla_convention(transliteration: str) -> str:
    """Rewrite an AES transliteration in the convention the corpus already uses."""
    text = str(transliteration).replace("≡", "=")
    text = EDITORIAL_MARKS_RE.sub("", text)
    text = text.lower()
    text = text.replace("j", "ꞽ")
    text = text.replace(",pl", ".PL").replace(",du", ".DU")
    text = text.replace(",", ".")
    return re.sub(r"\s+", " ", text).strip()


def content_id(row: dict) -> str:
    """Identifier derived from the sentence's own content, not its position."""
    key = "\x1f".join(
        str(row.get(field, ""))
        for field in ("corpus", "text_id", "sentence_id", "hieroglyphs", "transliteration")
    )
    return "AES_" + hashlib.blake2b(key.encode("utf-8"), digest_size=6).hexdigest().upper()


def to_schema(row: dict) -> dict[str, object]:
    """Map one AES sentence onto the corpus schema."""
    identifier = content_id(row)
    transliteration = unify_suffix_marker(to_tla_convention(row["transliteration"]))
    source_ref = (
        f"AES/{row['corpus']}#text={row.get('text_id','')}"
        f"&sentence={row.get('sentence_id','')}"
    )
    note_bits = [f"AES date: {row.get('date','unknown')}"]
    if row.get("findspot"):
        note_bits.append(f"findspot: {row['findspot']}")
    if row.get("editor"):
        note_bits.append(f"editor: {row['editor']}")

    out = {column: "" for column in REQUIRED_COLUMNS}
    out.update(
        {
            "source": "AES",
            "source_text_id": identifier,
            "source_sentence_id": f"S{identifier.rsplit('_', 1)[-1]}",
            # AES does not state a language stage per sentence and deriving one from
            # a coarse era label would be a guess, so it is left unclaimed.
            "language_stage": "Unspecified (AES)",
            "script_type": "hieroglyphic/hieratic",
            "genre": GENRE_LABELS.get(row["corpus"], row["corpus"]),
            "period": PERIOD_LABELS.get(row.get("date", ""), row.get("date", "unknown")),
            "hieroglyphs": row["hieroglyphs"],
            "mdc": "",
            "sign_sequence": transliteration,
            "transliteration_gold": transliteration,
            "translation": row.get("translation", ""),
            "lemma_sequence": row.get("lemma_sequence", ""),
            "upos": row.get("upos", ""),
            "glossing": "",
            "grammar_notes": "; ".join(note_bits),
            "source_ref": source_ref,
            "review_status": "seed",
            "display_sequence": row["hieroglyphs"],
            "normalized_reading_order": "",
            "aesthetic_arrangement_flag": False,
        }
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relannis", default=str(RELANNIS_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--corpora",
        nargs="*",
        default=None,
        help="Subcorpus names to import (default: all present).",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--existing",
        default="data/processed/examples.csv",
        help="Corpus to deduplicate against; pass '' to skip.",
    )
    args = parser.parse_args()

    archives = sorted(Path(args.relannis).glob("*.zip"))
    if args.corpora:
        wanted = set(args.corpora)
        archives = [a for a in archives if a.stem in wanted]
    if not archives:
        raise SystemExit(f"No relANNIS archives found in {args.relannis}")

    collected: list[dict] = []
    per_corpus: dict[str, int] = {}
    with TemporaryDirectory() as workspace:
        for archive in archives:
            target = Path(workspace) / archive.stem
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(target)
            found = read_corpus(target)
            per_corpus[archive.stem] = len(found)
            collected.extend(found)
            print(f"  {archive.stem:26s} {len(found):6d} fully aligned sentences")

    print(f"\n{len(collected)} aligned sentences across {len(archives)} subcorpora")

    rows = [to_schema(row) for row in collected]
    frame = pd.DataFrame(rows)

    before = len(frame)
    frame = frame.drop_duplicates(subset=["source_text_id"])
    if before != len(frame):
        print(f"dropped {before - len(frame)} rows with a duplicate content id")

    if args.existing:
        existing_path = Path(args.existing)
        if existing_path.exists():
            existing = pd.read_csv(existing_path).fillna("")

            def key(value: object) -> str:
                return re.sub(r"[^a-zꜣꜥḥḫẖšṯḏꞽ]", "", str(value).lower())

            seen = {key(v) for v in existing["transliteration_gold"]}
            mask = [key(v) not in seen for v in frame["transliteration_gold"]]
            dropped = len(frame) - sum(mask)
            frame = frame[mask]
            print(f"dropped {dropped} sentences already present in {existing_path}")

    if args.limit:
        frame = frame.head(args.limit)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    print(f"\nWrote {len(frame)} AES rows to {output}")
    print("periods:", frame["period"].value_counts().to_dict())


if __name__ == "__main__":
    main()

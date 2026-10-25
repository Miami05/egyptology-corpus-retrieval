"""Link corpus rows to ORAEC text metadata: title, bibliography, object, Trismegistos.

What it is. `oraec/corpus_raw_data` (Open Richly Annotated Egyptian Corpus) republishes
the AED/AES texts — the same BBAW database excerpt behind our AES and BBAW rows — as
one JSON per text (`oraec1.json` .. `oraec13026.json`) with title, date, find place,
object type, present location, inventory numbers (`idno`), bibliography and credits.
`credits.source` names the AED-TEI file the text came from; its file name is the same
26-character text id our AES rows carry in `source_ref` (`#text=<id>&sentence=…`).

Licences (per file, from the upstream README's table):
    oraec*.json, oraec_hierarchical_path.tsv   CC BY-SA 4.0 (authors listed per file)
    mapping_oraec_trismegistos.csv              CC0, ORAEC
    mapping_oraec_wikidata.tsv                  CC0, ORAEC (contributor -> Wikidata Q id)
Files not in the README's licence table (`mapping_oraec_karnak.tsv`,
`mapping_oraec_lemmata_karnak.tsv`) are not read. `mapping_oraec_lemmata_vega.tsv`
(CC BY-SA) is not needed here. Every output row records which file and licence each
group of columns came from.

Linking.
    AES   by text id: the AED-TEI id in `credits.source` == `text=` in our source_ref.
    BBAW  our BBAW rows carry no text id (one dataset-level id), so they are linked by
          sentence: each ORAEC sentence's `written_form` tokens are joined, converted
          with the BBAW importer's own `to_corpus_convention`, and reduced to the
          BBAW importer's `dedup_key`. Keys shared by several texts (formulae, short
          phrases) are counted as ambiguous and never linked. A key owned by exactly
          one text is only a *proposed* link; it is **accepted** only when all hold:
              key_words >= 3          (a one- or two-word key is too weak: `zꜣ.t =f`
                                       "his daughter" is unique to the wrong text
                                       because the BBAW row lost the name)
              unique text ownership
              translation match       the BBAW row's translation is nonempty and
                                       equals, after whitespace normalisation, the
                                       translation of an ORAEC sentence with that key
                                       in that text
          Proposed links that fail are kept as candidates, never as links:
              review_short_key                 key_words < 3
              quarantine_translation_mismatch  >= 3 words, both translations
                                               nonempty, and they differ
              review_no_translation            >= 3 words, a translation is empty

Outputs (`--output` is required; the two link files are optional):
    source_metadata_oraec.csv   one row per ORAEC text with >= 1 AES row or accepted
                                BBAW link (`bbaw_rows_linked` counts accepted links only)
    <bbaw-links>                accepted BBAW source_sentence_id -> oraec_id links
    <bbaw-link-candidates>      proposed links that were not accepted, with
                                `link_status`; for review, not for provenance

    python -I scripts/import_oraec_metadata.py --raw-dir data/raw/oraec/repo \
        --output data/processed/source_metadata_oraec.csv \
        --bbaw-links data/processed/source_metadata_oraec_bbaw_links.csv \
        --bbaw-link-candidates data/processed/source_metadata_oraec_bbaw_link_candidates.csv
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_bbaw_egyptian import dedup_key, to_corpus_convention  # noqa: E402

EXAMPLES = PROJECT_ROOT / "data" / "processed" / "examples.csv"
UPSTREAM = "https://github.com/oraec/corpus_raw_data"
TEXT_LICENCE = "CC BY-SA 4.0"
CC0 = "CC0 1.0"

AED_ID_RE = re.compile(r"aed-tei/blob/[^/]+/files/([A-Z0-9]{26})\.xml")
AES_TEXT_RE = re.compile(r"text=([A-Z0-9]{26})")

COLUMNS = [
    "oraec_id",
    "aed_text_id",
    "title",
    "hierarchical_path",
    "date",
    "origplace",
    "objecttype",
    "location",
    "idno",
    "bibliography",
    "text_authors",
    "text_licence",
    "text_provenance",
    "trismegistos_id",
    "trismegistos_url",
    "trismegistos_licence",
    "trismegistos_provenance",
    "aes_rows_linked",
    "bbaw_rows_linked",
    "retrieved",
]


def _labels(items: object, key: str) -> str:
    if not isinstance(items, list):
        return ""
    return " | ".join(str(i.get(key, "")).strip() for i in items if isinstance(i, dict) and i.get(key))


def parse_text(oraec_id: str, record: dict) -> dict:
    """Metadata columns from one `oraecN.json` record."""
    credits = record.get("credits") or {}
    sources = credits.get("source") or []
    if isinstance(sources, str):
        sources = [sources]
    aed = ""
    for s in sources:
        m = AED_ID_RE.search(str(s))
        if m:
            aed = m.group(1)
            break
    idno = record.get("idno") or []
    if isinstance(idno, str):
        idno = [idno]
    authors = credits.get("author") or ""
    if isinstance(authors, list):
        authors = "; ".join(authors)
    return {
        "oraec_id": oraec_id,
        "aed_text_id": aed,
        "title": str(record.get("title") or "").strip(),
        "date": _labels(record.get("date"), "date"),
        "origplace": _labels(record.get("origplace"), "origplace"),
        "objecttype": _labels(record.get("objecttype"), "objecttype"),
        "location": _labels(record.get("location"), "location"),
        "idno": " | ".join(dict.fromkeys(str(x).strip() for x in idno if str(x).strip())),
        "bibliography": str(record.get("bibliography") or "").strip(),
        "text_authors": authors,
        "text_licence": TEXT_LICENCE if str(credits.get("license", "")).lower() == "cc-by-sa-4.0"
        else str(credits.get("license", "")),
        "text_provenance": f"{UPSTREAM} {oraec_id}.json; upstream: " + " ".join(str(s) for s in sources),
    }


MIN_KEY_WORDS = 3
LINK_COLUMNS = ["source", "source_sentence_id", "oraec_id", "match_method", "key_words",
                "translation_match", "link_status"]


def norm_translation(text: object) -> str:
    """Whitespace-normalised translation; nothing else is folded."""
    return " ".join(str(text or "").split())


def sentence_keys(record: dict) -> dict[str, set[str]]:
    """dedup_key -> the normalised translations of the sentences that have that key."""
    keys: dict[str, set[str]] = {}
    for sent in record.get("sentences") or []:
        words = [str(t.get("written_form", "")) for t in sent.get("token") or [] if t.get("written_form")]
        if words:
            key = dedup_key(to_corpus_convention(" ".join(words)))
            if key:
                translations = keys.setdefault(key, set())
                tr = norm_translation(sent.get("translation"))
                if tr:
                    translations.add(tr)
    return keys


def link_status(key_words: int, corpus_translation: str, oraec_translations: set[str]) -> tuple[bool, str]:
    """(translation_match, link_status) for a key owned by exactly one text."""
    match = bool(corpus_translation) and corpus_translation in oraec_translations
    if key_words < MIN_KEY_WORDS:
        return match, "review_short_key"
    if match:
        return match, "accepted"
    if corpus_translation and oraec_translations:
        return match, "quarantine_translation_mismatch"
    return match, "review_no_translation"


def read_tm(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)
        return {row[0]: row[1] for row in reader if len(row) >= 2 and row[1].strip()}


def read_paths(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2:
                out[parts[0]] = parts[1]
    return out


def build(
    raw_dir: Path, corpus: pd.DataFrame, limit: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    aes = corpus[corpus["source"] == "AES"]
    aes_text = aes["source_ref"].str.extract(AES_TEXT_RE)[0]
    aes_counts = collections.Counter(aes_text.dropna())

    bbaw = corpus[corpus["source"] == "BBAW"]
    bbaw_keys = bbaw["transliteration_gold"].map(dedup_key)
    bbaw_tr = (bbaw["translation"] if "translation" in bbaw else pd.Series("", index=bbaw.index)).map(
        norm_translation)

    tm = read_tm(raw_dir / "mapping_oraec_trismegistos.csv")
    paths = read_paths(raw_dir / "oraec_hierarchical_path.tsv")

    files = sorted(raw_dir.glob("oraec*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    if limit:
        files = files[:limit]
    texts: dict[str, dict] = {}
    key_owner: dict[str, set[str]] = collections.defaultdict(set)
    key_translations: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    wanted_keys = set(bbaw_keys)
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        for oraec_id, record in data.items():
            texts[oraec_id] = parse_text(oraec_id, record)
            for k, trs in sentence_keys(record).items():
                if k in wanted_keys:
                    key_owner[k].add(oraec_id)
                    key_translations[(k, oraec_id)].update(trs)

    by_aed = {t["aed_text_id"]: oid for oid, t in texts.items() if t["aed_text_id"]}

    proposed = []
    ambiguous = 0
    for sid, key, tr in zip(bbaw["source_sentence_id"], bbaw_keys, bbaw_tr):
        owners = key_owner.get(key, set())
        if len(owners) == 1:
            oid = next(iter(owners))
            n_words = len(key.split())
            match, status = link_status(n_words, tr, key_translations.get((key, oid), set()))
            proposed.append({"source": "BBAW", "source_sentence_id": sid, "oraec_id": oid,
                             "match_method": "unique sentence dedup_key + translation", "key_words": n_words,
                             "translation_match": str(match), "link_status": status})
        elif len(owners) > 1:
            ambiguous += 1
    proposed_df = pd.DataFrame(proposed, columns=LINK_COLUMNS)
    accepted = proposed_df["link_status"] == "accepted"
    link_df = proposed_df[accepted].reset_index(drop=True)
    candidate_df = proposed_df[~accepted].reset_index(drop=True)
    bbaw_per_text = collections.Counter(link_df["oraec_id"])

    today = dt.date.today().isoformat()
    rows = []
    for oid, t in texts.items():
        n_aes = aes_counts.get(t["aed_text_id"], 0) if t["aed_text_id"] else 0
        n_bbaw = bbaw_per_text.get(oid, 0)
        if not (n_aes or n_bbaw):
            continue
        tm_id = tm.get(oid, "")
        rows.append({
            **t,
            "hierarchical_path": paths.get(oid, ""),
            "trismegistos_id": tm_id,
            "trismegistos_url": f"https://www.trismegistos.org/text/{tm_id}" if tm_id else "",
            "trismegistos_licence": CC0 if tm_id else "",
            "trismegistos_provenance": f"{UPSTREAM} mapping_oraec_trismegistos.csv" if tm_id else "",
            "aes_rows_linked": n_aes,
            "bbaw_rows_linked": n_bbaw,
            "retrieved": today,
        })
    meta = pd.DataFrame(rows, columns=COLUMNS)

    linked_aes_rows = sum(n for aed, n in aes_counts.items() if aed in by_aed)
    stats = {
        "oraec_texts": len(texts),
        "oraec_texts_with_aed_id": len(by_aed),
        "aes_rows": len(aes),
        "aes_text_ids": len(aes_counts),
        "aes_text_ids_linked": sum(1 for aed in aes_counts if aed in by_aed),
        "aes_rows_linked": linked_aes_rows,
        "bbaw_rows": len(bbaw),
        "bbaw_rows_proposed_unique": len(proposed_df),
        "bbaw_rows_linked_accepted": len(link_df),
        "bbaw_rows_review_short_key": int((candidate_df["link_status"] == "review_short_key").sum()),
        "bbaw_rows_review_short_key_translation_match": int(
            ((candidate_df["link_status"] == "review_short_key") & (candidate_df["translation_match"] == "True")).sum()),
        "bbaw_rows_quarantine_translation_mismatch": int(
            (candidate_df["link_status"] == "quarantine_translation_mismatch").sum()),
        "bbaw_rows_review_no_translation": int((candidate_df["link_status"] == "review_no_translation").sum()),
        "bbaw_rows_ambiguous": ambiguous,
        "metadata_rows": len(meta),
        "metadata_rows_with_tm": int((meta["trismegistos_id"] != "").sum()),
        "aes_rows_with_tm": int(meta.loc[meta["trismegistos_id"] != "", "aes_rows_linked"].sum()),
        "aes_rows_with_bibliography": int(meta.loc[meta["bibliography"] != "", "aes_rows_linked"].sum()),
        "aes_rows_with_idno": int(meta.loc[meta["idno"] != "", "aes_rows_linked"].sum()),
    }
    return meta, link_df, candidate_df, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", required=True, help="Clone of oraec/corpus_raw_data")
    parser.add_argument("--output", required=True)
    parser.add_argument("--bbaw-links", default="")
    parser.add_argument("--bbaw-link-candidates", default="")
    parser.add_argument("--examples", default=str(EXAMPLES))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    for target in (args.output, args.bbaw_links, args.bbaw_link_candidates):
        if target and Path(target).resolve() == EXAMPLES.resolve():
            sys.exit("refusing to overwrite examples.csv")
    corpus = pd.read_csv(
        args.examples, dtype=str, keep_default_na=False,
        usecols=["source", "source_sentence_id", "source_ref", "transliteration_gold", "translation"],
    )
    meta, links, candidates, stats = build(Path(args.raw_dir), corpus, args.limit)
    out.parent.mkdir(parents=True, exist_ok=True)
    meta.to_csv(out, index=False)
    if args.bbaw_links:
        links.to_csv(args.bbaw_links, index=False)
    if args.bbaw_link_candidates:
        candidates.to_csv(args.bbaw_link_candidates, index=False)
    for k, v in stats.items():
        print(f"{k}: {v}")
    print(f"AES link rate: {stats['aes_rows_linked'] / max(stats['aes_rows'], 1):.4f}")
    print(f"BBAW accepted link rate: {stats['bbaw_rows_linked_accepted'] / max(stats['bbaw_rows'], 1):.4f}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

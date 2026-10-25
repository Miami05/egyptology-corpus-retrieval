"""English glosses for TLA lemma ids from Wikidata's Egyptian lexemes (CC0).

What it is. Wikidata holds ~14,800 Egyptian lexemes (language Q50868) carrying the
property P12188 "Thesaurus Linguae Aegyptiae lemma ID". Their senses have glosses
(`skos:definition`) in several languages. This script pulls, for every lexeme with a
P12188 value, its lemma and its English sense glosses, and writes one row per TLA
lemma id that has at least one English gloss.

Licence: Wikidata's structured data, the Lexeme namespace included, is CC0
(https://www.wikidata.org/wiki/Wikidata:Licensing: "All data in Wikidata has a CC0
license."). No attribution is legally required; the output keeps lexeme and sense ids
as provenance and the site credits "Wikidata contributors" as a courtesy.

Politeness. Two steps, so the network is touched once:
    --fetch      pages through query.wikidata.org/sparql (LIMIT 10000, a few requests,
                 one second apart, descriptive User-Agent) and saves each page's JSON
                 under --raw-dir
    (always)     builds --output from the saved pages, offline

    python -I scripts/fetch_wikidata_lemma_glosses.py --fetch --raw-dir data/raw/wikidata \
        --output data/processed/lemma_glosses_en.csv
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = PROJECT_ROOT / "data" / "processed" / "examples.csv"
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = (
    "Whyptology-open-data/1.0 (Egyptian reading-suggestion research project; "
    "contact l.durmishaj@apelos.de) python-urllib"
)
PAGE = 10000
MAX_PAGES = 10

QUERY = """SELECT ?lexeme ?tla ?lemma ?sense ?gloss WHERE {{
  ?lexeme wdt:P12188 ?tla ; wikibase:lemma ?lemma .
  OPTIONAL {{ ?lexeme ontolex:sense ?sense . ?sense skos:definition ?gloss . FILTER(LANG(?gloss) = "en") }}
}} ORDER BY ?lexeme ?sense LIMIT {limit} OFFSET {offset}"""

COLUMNS = [
    "tla_lemma_id", "gloss_en", "lexeme_ids", "lemmas", "sense_ids", "in_corpus",
    "corpus_rows", "source", "licence", "retrieved",
]


def fetch(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for page in range(MAX_PAGES):
        query = QUERY.format(limit=PAGE, offset=page * PAGE)
        url = ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/sparql-results+json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read()
        data = json.loads(body)
        n = len(data["results"]["bindings"])
        (raw_dir / f"page_{page:02d}.json").write_bytes(body)
        (raw_dir / f"page_{page:02d}.sparql").write_text(query, encoding="utf-8")
        print(f"page {page}: {n} bindings")
        if n < PAGE:
            break
        time.sleep(1.0)
    (raw_dir / "retrieved.txt").write_text(dt.date.today().isoformat(), encoding="utf-8")


def _tail(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def build(bindings: list[dict], corpus_counts: collections.Counter, retrieved: str) -> pd.DataFrame:
    by_id: dict[str, dict] = collections.defaultdict(
        lambda: {"gloss": [], "lexeme": [], "lemma": [], "sense": []})
    for b in bindings:
        if "gloss" not in b:
            continue
        tla = b["tla"]["value"].strip()
        d = by_id[tla]
        for key, val in (("gloss", b["gloss"]["value"].strip()), ("lexeme", _tail(b["lexeme"]["value"])),
                         ("lemma", b["lemma"]["value"]), ("sense", _tail(b["sense"]["value"]))):
            if val and val not in d[key]:
                d[key].append(val)
    rows = []
    for tla in sorted(by_id, key=lambda x: (len(x), x)):
        d = by_id[tla]
        rows.append({
            "tla_lemma_id": tla,
            "gloss_en": " | ".join(d["gloss"]),
            "lexeme_ids": " | ".join(d["lexeme"]),
            "lemmas": " | ".join(d["lemma"]),
            "sense_ids": " | ".join(d["sense"]),
            "in_corpus": str(tla in corpus_counts),
            "corpus_rows": corpus_counts.get(tla, 0),
            "source": "Wikidata lexemes (P12188 TLA lemma ID), https://www.wikidata.org/wiki/" + d["lexeme"][0],
            "licence": "CC0 1.0",
            "retrieved": retrieved,
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def corpus_lemma_counts(path: Path) -> collections.Counter:
    """Rows per lemma id, ids taken exactly like the 2026-10-25 preflight (before `|`)."""
    counts: collections.Counter = collections.Counter()
    seq = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=["lemma_sequence"])["lemma_sequence"]
    for value in seq:
        ids = {tok.split("|", 1)[0] for tok in value.split() if tok.split("|", 1)[0]}
        counts.update(ids)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--examples", default=str(EXAMPLES))
    args = parser.parse_args()
    out = Path(args.output).resolve()
    if out == EXAMPLES.resolve():
        sys.exit("refusing to overwrite examples.csv")
    raw_dir = Path(args.raw_dir)
    if args.fetch:
        fetch(raw_dir)
    bindings: list[dict] = []
    for page in sorted(raw_dir.glob("page_*.json")):
        bindings.extend(json.loads(page.read_text(encoding="utf-8"))["results"]["bindings"])
    retrieved_file = raw_dir / "retrieved.txt"
    retrieved = retrieved_file.read_text().strip() if retrieved_file.exists() else ""

    counts = corpus_lemma_counts(Path(args.examples))
    df = build(bindings, counts, retrieved)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    lexemes = {b["lexeme"]["value"] for b in bindings}
    wd_ids = {b["tla"]["value"].strip() for b in bindings}
    glossed = set(df["tla_lemma_id"])
    corpus_ids = set(counts)
    total_tokens_rows = sum(counts.values())
    print(f"bindings: {len(bindings)}; lexemes: {len(lexemes)}; TLA ids on Wikidata: {len(wd_ids)}")
    print(f"TLA ids with an English gloss: {len(glossed)}")
    print(f"corpus lemma ids: {len(corpus_ids)}")
    print(f"  on Wikidata at all: {len(corpus_ids & wd_ids)}")
    print(f"  with an English gloss: {len(corpus_ids & glossed)} ({len(corpus_ids & glossed) / len(corpus_ids):.4f})")
    covered = sum(counts[i] for i in corpus_ids & glossed)
    print(f"  (row-weighted: {covered} of {total_tokens_rows} lemma-row pairs, {covered / total_tokens_rows:.4f})")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

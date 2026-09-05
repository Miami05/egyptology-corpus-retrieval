"""Build the drift-corrected companion to the frozen v4 benchmark.

The v4 file was frozen before `fold_plural_marker` entered the normaliser, so its
`expected_key_tokens` cells still carry a `pl` token that today's fold can never
produce from a corpus row (`.pl`/`.PL` now folds to `.w`, and the index holds `pl` in
exactly one row out of 130,472). Twelve of the twenty v4 rows are affected. Comparing
today's pipeline against those cells measures the drift as much as the pipeline.

This script writes a NEW file. **The frozen v4 file is never touched**, and the
drift-corrected numbers are always reported beside the v4 numbers, never in place of
them.

What is recomputed, and with whose code:

  * `expected_key_tokens` — `sorted(_token_set(loose_reading_form(gold)))`, taken from
    `scripts/build_competitive_ambiguity_benchmark.py` itself (imported, not copied), run
    over the *current* corpus row named by the frozen expected ids.
  * `acceptable_token_overlap_threshold` — the builder's own rule,
    `0.34 if len(key_tokens) <= 4 else 0.26`. It is a function of the key tokens, so it
    has to follow them. It can only move up (a shorter token set is judged more
    strictly); a row that would move *down* is left at its frozen value and reported,
    because the threshold must never be loosened.

Everything else — `query_input`, `query_type`, `expected_transliteration`, the expected
ids, `expected_lemma_ids`, `notes`, `language_stage` — is copied verbatim from v4.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv
from app.services.suggestions import loose_reading_form
from scripts.build_competitive_ambiguity_benchmark import _lemma_ids, _token_set

V4_PATH = "data/benchmarks/competitive_ambiguity_eval_queries_v4.csv"
OUT_PATH = "data/benchmarks/competitive_ambiguity_eval_queries_v4_driftcorrected.csv"
EXAMPLES_PATH = "data/processed/examples.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--v4", default=V4_PATH)
    parser.add_argument("--out", default=OUT_PATH)
    args = parser.parse_args()

    corpus = load_examples_csv(args.examples)
    keyed = corpus.set_index(
        [corpus["source_text_id"].astype(str), corpus["source_sentence_id"].astype(str)]
    )
    bench = pd.read_csv(args.v4).fillna("")
    # Written back as a formatted string, so the column must not stay float64.
    bench["acceptable_token_overlap_threshold"] = bench[
        "acceptable_token_overlap_threshold"
    ].map(lambda value: f"{float(value):.2f}")

    changed_tokens = 0
    changed_threshold = 0
    threshold_would_drop: list[str] = []
    missing: list[str] = []
    lemma_drift: list[str] = []

    for position, row in bench.iterrows():
        key = (str(row["expected_source_text_id"]), str(row["expected_source_sentence_id"]))
        if key not in keyed.index:
            missing.append(str(row["benchmark_id"]))
            continue
        corpus_row = keyed.loc[key]
        if isinstance(corpus_row, pd.DataFrame):
            corpus_row = corpus_row.iloc[0]
        gold = str(corpus_row["transliteration_gold"])
        key_tokens = sorted(_token_set(loose_reading_form(gold)))
        old_tokens = str(row["expected_key_tokens"]).split()
        if key_tokens != old_tokens:
            changed_tokens += 1
        new_threshold = 0.34 if len(key_tokens) <= 4 else 0.26
        old_threshold = float(row["acceptable_token_overlap_threshold"])
        if new_threshold < old_threshold:
            # Never loosen a frozen threshold; keep the stricter of the two.
            threshold_would_drop.append(str(row["benchmark_id"]))
            new_threshold = old_threshold
        if new_threshold != old_threshold:
            changed_threshold += 1
        current_lemmas = _lemma_ids(corpus_row["lemma_sequence"])
        if sorted(current_lemmas) != sorted(str(row["expected_lemma_ids"]).split()):
            lemma_drift.append(str(row["benchmark_id"]))

        bench.at[position, "expected_key_tokens"] = " ".join(key_tokens)
        bench.at[position, "acceptable_token_overlap_threshold"] = f"{new_threshold:.2f}"

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bench.to_csv(out_path, index=False)
    print(f"rows: {len(bench)}")
    print(f"expected_key_tokens changed: {changed_tokens}")
    print(f"threshold changed (only upward): {changed_threshold}")
    if threshold_would_drop:
        print(f"threshold would have DROPPED, kept frozen value: {threshold_would_drop}")
    if lemma_drift:
        print(f"expected_lemma_ids differ from the current corpus row (left frozen): {lemma_drift}")
    if missing:
        print(f"expected row no longer in corpus (left untouched): {missing}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

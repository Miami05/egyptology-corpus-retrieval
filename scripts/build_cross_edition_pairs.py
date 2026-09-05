"""Build the frozen cross-edition pair set for the similar-text evaluation (item E).

A *pair* is two corpus rows from different sources that are the same sentence in two
editions. The rule is pre-registered in `docs/similar-text-eval-2026-09-05.md` §1-§3 and
implemented here exactly as written there; read that document first, not this docstring.

The short version:

* both rows have >= 5 loose tokens (`loose_reading_form(transliteration_gold).split()`),
* their loose-token Jaccard is in `[0.5, 0.9)` — `>= 0.9` are near-copies (13,659 corpus
  rows have such a twin) and would make every method look perfect,
* the two rows come from different `source` values,
* at most one pair per corpus row, greedy and deterministic, round-robin over the
  unordered source pairs, capped at 300.

Candidate generation is the prefix filter, not a scan. `twin_probe_count` is *imported*
from `scripts.build_competitive_ambiguity_benchmark` rather than copied, so the two places
that rely on the theorem cannot drift apart. It is applied prefix-to-prefix here (index
only each row's rarest `twin_probe_count(|A|, t)` tokens, probe only those) which is
exact — see the proof in the pre-registration — and, unlike probing full postings lists,
affordable at t = 0.5: under a document-frequency-ascending global order a very frequent
token is last, so it sits in almost no row's prefix. There is no postings cap.

Usage:
    python scripts/build_cross_edition_pairs.py [--out data/benchmarks/cross_edition_pairs_v1.csv]
"""

from __future__ import annotations

import argparse
import resource
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv  # noqa: E402

from app.services.suggestions import loose_reading_form  # noqa: E402
from scripts.build_competitive_ambiguity_benchmark import twin_probe_count  # noqa: E402

DATA_PATH = PROJECT_ROOT / "data/processed/examples.csv"
DEFAULT_OUT = PROJECT_ROOT / "data/benchmarks/cross_edition_pairs_v1.csv"

# Pre-registered constants (docs/similar-text-eval-2026-09-05.md §1, §3).
MIN_JACCARD = 0.5
MAX_JACCARD = 0.9  # exclusive: >= this is a near-copy twin, deliberately excluded
MIN_TOKENS = 5
MAX_PAIRS = 300

# Which language each source's `translation` column is in. Ramses has none.
TRANSLATION_LANGUAGE = {"TLA": "de", "AES": "de", "BBAW": "en", "Ramses": ""}


def peak_rss_gb() -> float:
    """Peak resident set size of this process, in GB (macOS reports bytes)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024**3) if sys.platform == "darwin" else peak / (1024**2)


def assert_yod_folds_together() -> None:
    """The pre-registration promises this is checked, not assumed.

    The brief asks for a Ramses `i` -> `ꞽ` mapping "where the fold does not already" do
    it. `normalize_transliteration` folds `ꞽ`, `j`, dotless `ı` and ASCII `i` all to `i`,
    and `normalize_mdc` (the second half of `loose_reading_form`) then drops the editorial
    apparatus including the combining breve of `i̯`, so both editions' yod already meets in
    one token and no extra mapping is needed. The check is on `loose_reading_form`, the
    function the pair rule actually uses, not on `normalize_transliteration` alone — that
    half still keeps the breve, so `ꞽri̯.n=f` and `iri.n=f` differ until the fold finishes.
    If this ever stops being true the pair set would silently lose every Ramses<->TLA
    pair, so it stops the build instead.
    """
    tla = "ꞽri̯.n=f"       # TLA writes the yod as U+A7BD
    ramses = "iri.n=f"      # Ramses writes it as ASCII i
    gardiner = "jrj.n=f"    # bbaw_egyptian / Gardiner-school j
    folds = {loose_reading_form(v) for v in (tla, ramses, gardiner)}
    if len(folds) != 1:
        raise SystemExit(
            "yod does not fold to one form across the editions: "
            f"{sorted(folds)} — the pair rule cannot be applied as pre-registered"
        )


def loose_token_sets(df: pd.DataFrame) -> list[set[str]]:
    return [
        set(loose_reading_form(value).split())
        for value in df["transliteration_gold"].astype(str)
    ]


def find_candidate_pairs(
    token_sets: list[set[str]],
    sources: list[str],
    eligible: list[int],
    threshold: float = MIN_JACCARD,
    upper: float = MAX_JACCARD,
) -> tuple[list[tuple[int, int, float]], int]:
    """Every cross-source pair with Jaccard in `[threshold, upper)`, by prefix filtering.

    Exact: if J(A,B) >= t then |A n B| >= t*max(|A|,|B|), so the globally-earliest shared
    token has fewer than `twin_probe_count(|A|, t)` tokens of A before it and therefore
    lies in A's prefix — and symmetrically in B's. Indexing prefixes only is what makes
    t = 0.5 affordable.

    That the shared token is in *both* prefixes is also what lets each unordered pair be
    emitted exactly once, from the lower-positioned row (`other > position`), with no set
    of already-seen pairs to keep. The first version of this function did keep one, and
    on the real corpus it was most of the 3.9 GB it had reached when it was killed:
    Jaccard 0.5 over 130k rows with BBAW re-editing TLA is a lot of pairs. The near-copies
    at `>= upper` are counted and dropped here for the same reason rather than collected
    and filtered by the caller.

    Returns `(pairs, near_copies_excluded)` where each pair is
    `(position_a, position_b, jaccard)` with `position_a < position_b`.
    """
    document_frequency: Counter[str] = Counter()
    for position in eligible:
        document_frequency.update(token_sets[position])
    # One global order over tokens: rarest first, ties by the token itself so the order is
    # a function of the corpus alone and not of dict insertion.
    order = {
        token: rank
        for rank, (token, _) in enumerate(
            sorted(document_frequency.items(), key=lambda item: (item[1], item[0]))
        )
    }

    prefixes: dict[int, list[str]] = {}
    postings: dict[str, list[int]] = defaultdict(list)
    for position in eligible:
        tokens = sorted(token_sets[position], key=lambda token: order[token])
        prefix = tokens[: twin_probe_count(len(tokens), threshold)]
        prefixes[position] = prefix
        for token in prefix:
            postings[token].append(position)

    pairs: list[tuple[int, int, float]] = []
    near_copies = 0
    started = time.perf_counter()
    for done, position in enumerate(eligible, start=1):
        target = token_sets[position]
        size = len(target)
        # Size bound: a partner at Jaccard >= t satisfies t*|A| <= |B| <= |A|/t.
        low, high = threshold * size, size / threshold
        source = sources[position]
        for token in prefixes[position]:
            for other in postings[token]:
                # Each unordered pair is emitted once, from its lower position.
                if other <= position:
                    continue
                if sources[other] == source:
                    continue
                other_tokens = token_sets[other]
                other_size = len(other_tokens)
                if not low <= other_size <= high:
                    continue
                shared = len(target & other_tokens)
                if not shared:
                    continue
                score = shared / (size + other_size - shared)
                if score < threshold:
                    continue
                if score >= upper:
                    near_copies += 1
                    continue
                pairs.append((position, other, score))
        if done % 20_000 == 0:
            print(
                f"  probed {done:,}/{len(eligible):,} rows, {len(pairs):,} pairs in band, "
                f"{time.perf_counter() - started:.0f}s",
                flush=True,
            )
    return pairs, near_copies


def source_pair_label(left: str, right: str) -> str:
    return "<->".join(sorted((left, right)))


def select_pairs(
    candidates: list[tuple[int, int, float]],
    df: pd.DataFrame,
    cap: int = MAX_PAIRS,
) -> pd.DataFrame:
    """The pre-registered greedy, deterministic, round-robin selection (§3)."""
    sources = df["source"].astype(str).tolist()
    text_ids = df["source_text_id"].astype(str).tolist()
    sentence_ids = df["source_sentence_id"].astype(str).tolist()

    grouped: dict[str, list[tuple[int, int, float]]] = defaultdict(list)
    for a, b, score in candidates:
        grouped[source_pair_label(sources[a], sources[b])].append((a, b, score))

    def sort_key(item: tuple[int, int, float]):
        a, b, score = item
        # Highest overlap first (most confidently the same sentence), then a key made
        # only of the data, so the order does not depend on how the candidates were found.
        return (
            -score,
            sources[a],
            text_ids[a],
            sentence_ids[a],
            sources[b],
            text_ids[b],
            sentence_ids[b],
        )

    queues = {label: sorted(items, key=sort_key) for label, items in grouped.items()}
    cursors = {label: 0 for label in queues}
    used: set[int] = set()
    selected: list[tuple[str, int, int, float]] = []

    labels = sorted(queues)
    while len(selected) < cap:
        progressed = False
        for label in labels:
            if len(selected) >= cap:
                break
            queue, cursor = queues[label], cursors[label]
            while cursor < len(queue):
                a, b, score = queue[cursor]
                cursor += 1
                if a in used or b in used:
                    continue
                used.add(a)
                used.add(b)
                selected.append((label, a, b, score))
                progressed = True
                break
            cursors[label] = cursor
        if not progressed:
            break

    rows = []
    for rank, (label, a, b, score) in enumerate(selected, start=1):
        left, right = df.iloc[a], df.iloc[b]
        rows.append(
            {
                "pair_id": f"XED_{rank:03d}",
                "source_pair": label,
                "jaccard": round(score, 6),
                "a_position": a,
                "a_source": left["source"],
                "a_text_id": left["source_text_id"],
                "a_sentence_id": left["source_sentence_id"],
                "a_language_stage": left["language_stage"],
                "a_transliteration": left["transliteration_gold"],
                "a_has_hieroglyphs": bool(str(left["hieroglyphs_norm"]).strip()),
                "a_has_translation": bool(str(left["translation"]).strip()),
                "b_position": b,
                "b_source": right["source"],
                "b_text_id": right["source_text_id"],
                "b_sentence_id": right["source_sentence_id"],
                "b_language_stage": right["language_stage"],
                "b_transliteration": right["transliteration_gold"],
                "b_has_hieroglyphs": bool(str(right["hieroglyphs_norm"]).strip()),
                "b_has_translation": bool(str(right["translation"]).strip()),
                "translation_language": (
                    TRANSLATION_LANGUAGE.get(str(left["source"]), "")
                    if TRANSLATION_LANGUAGE.get(str(left["source"]), "")
                    == TRANSLATION_LANGUAGE.get(str(right["source"]), "")
                    else ""
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--data", default=str(DATA_PATH))
    parser.add_argument("--cap", type=int, default=MAX_PAIRS)
    parser.add_argument("--hand-check", type=int, default=10)
    args = parser.parse_args()

    assert_yod_folds_together()
    print("yod check: ꞽri̯.n=f / iri.n=f / jrj.n=f all fold to one form — no extra mapping needed")

    started = time.perf_counter()
    df = load_examples_csv(args.data)
    print(f"corpus: {len(df):,} rows loaded in {time.perf_counter() - started:.1f}s")

    token_sets = loose_token_sets(df)
    sources = df["source"].astype(str).tolist()
    eligible = [i for i, tokens in enumerate(token_sets) if len(tokens) >= MIN_TOKENS]
    print(f"eligible rows (>= {MIN_TOKENS} loose tokens): {len(eligible):,}")

    started = time.perf_counter()
    in_band, excluded = find_candidate_pairs(token_sets, sources, eligible)
    print(
        f"cross-source candidate pairs in band [{MIN_JACCARD}, {MAX_JACCARD}): "
        f"{len(in_band):,} in {time.perf_counter() - started:.1f}s "
        f"({excluded:,} near-copy pairs at >= {MAX_JACCARD} found and excluded)"
    )
    band_counts = Counter(
        source_pair_label(sources[a], sources[b]) for a, b, _ in in_band
    )
    print("candidates in band, per source pair:")
    for label, count in sorted(band_counts.items()):
        print(f"  {label:22s} {count:,}")

    pairs = select_pairs(in_band, df, cap=args.cap)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pairs.to_csv(out_path, index=False)
    print(f"\nselected {len(pairs)} pairs -> {out_path}")
    print("selected pairs, per source pair:")
    for label, count in sorted(Counter(pairs["source_pair"]).items()):
        print(f"  {label:22s} {count}")
    print(
        "both rows have hieroglyphs: "
        f"{int((pairs['a_has_hieroglyphs'] & pairs['b_has_hieroglyphs']).sum())}"
    )
    print(
        "both rows have a same-language translation: "
        f"{int(((pairs['translation_language'] != '') & pairs['a_has_translation'] & pairs['b_has_translation']).sum())}"
    )

    if args.hand_check:
        # Spread across the source pairs and across each one's Jaccard range. Taking
        # every Nth row of the selected list would not do it: the selection is
        # round-robin over six source pairs, so every 30th row is the same source pair.
        labels = sorted(pairs["source_pair"].unique())
        per_group = -(-args.hand_check // len(labels))
        columns: list[list[int]] = []
        for label in labels:
            group = pairs.index[pairs["source_pair"] == label].tolist()
            step = max(len(group) // per_group, 1)
            columns.append(group[::step][:per_group])
        interleaved = [
            position
            for depth in range(per_group)
            for column in columns
            if depth < len(column)
            for position in [column[depth]]
        ][: args.hand_check]
        print(f"\n--- {args.hand_check} pairs for hand-checking ---")
        for _, row in pairs.loc[interleaved].iterrows():
            print(f"\n{row['pair_id']}  {row['source_pair']}  Jaccard {row['jaccard']:.3f}")
            print(f"  A {row['a_source']}/{row['a_text_id']}/{row['a_sentence_id']}: {row['a_transliteration']}")
            print(f"  B {row['b_source']}/{row['b_text_id']}/{row['b_sentence_id']}: {row['b_transliteration']}")
            for side in ("a", "b"):
                translation = str(df.iloc[int(row[f"{side}_position"])]["translation"]).strip()
                if translation:
                    print(f"  {side.upper()} translation: {translation}")

    print(f"\npeak RSS {peak_rss_gb():.2f} GB")


if __name__ == "__main__":
    main()

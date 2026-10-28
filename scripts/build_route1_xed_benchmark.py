"""Route 1: build the SEALED cross-edition query benchmark (no evaluation, no index).

The rules are fixed in `docs/route1-xed-benchmark-preregistration-2026-10-28.md` (a
DRAFT until approved); read that first. In short: every usable pair of
`data/benchmarks/cross_edition_pairs_v1.csv` (the same sentence in two editions, item E)
becomes ONE query. One side of the pair is typed verbatim as the query (its own
notation, nothing folded), the other side is the expected answer and STAYS in the
search pool. The query's own row and its near-twins are recorded per query in
`hidden_row_keys` for the harness to remove (leave-one-out; the harness does not read
that column yet, see the pre-registration, section 6).

Which side is the query is decided once, before any exclusion, by a seeded shuffle
inside each source pair, half and half, so no pair is used in both directions (two
directions of one pair are one sentence counted twice) and the exclusions below cannot
move another pair's direction.

A pair is dropped, under the first rule that applies, when:

1. a row's (source_text_id, source_sentence_id) is not in the corpus, or is not unique;
2. a row's transliteration differs from the one frozen in the pair file;
3. a row is in the data-cleanup removal manifest with decision `removed`;
4. a row is the target of any committed benchmark (every `data/benchmarks/*.csv` that has
   expected_source_text_id and expected_source_sentence_id columns, held-out 2/3 included);
5. a row is a near-twin (loose-token Jaccard >= 0.9) of such a target;
6. a row shares a TLA/AES/Ramses source_text_id with such a target;
7. a row is a BBAW row within +-20 sentence numbers of such a target
   (rules 4 to 7 are the Experiment 3 held-out rules, reused through the builder's own
   `same_text_exclusions`);
8. the query side has fewer than 5 loose tokens on the current corpus.

The build is read-only on the corpus, deterministic (no clock, no unseeded randomness),
refuses to overwrite an existing sealed file, and prints COUNTS ONLY: no query text.

    python scripts/build_route1_xed_benchmark.py            # build once, write file + log
    python scripts/build_route1_xed_benchmark.py --verify   # rebuild in memory, compare
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv  # noqa: E402
from app.services.stage import normalize_stage  # noqa: E402
from app.services.suggestions import loose_reading_form  # noqa: E402
from scripts.build_competitive_ambiguity_benchmark import (  # noqa: E402
    _lemma_ids,
    _token_set,
    same_text_exclusions,
)
from scripts.eval_guards import TwinGuard, twin_rows, twins_of_target  # noqa: E402

B_DIR = "data/benchmarks"
PAIRS_PATH = f"{B_DIR}/cross_edition_pairs_v1.csv"
OUT_PATH = f"{B_DIR}/competitive_ambiguity_eval_queries_xed_route1_2026-10-28_SEALED.csv"
LOG_PATH = f"{B_DIR}/route1_xed_build_log_2026-10-28.txt"
EXAMPLES_PATH = "data/processed/examples.csv"
MANIFEST_PATH = (
    "/Users/lediodurmishaj/egyptology-runs/data-cleanup-2026-10-26/build_N/removal_manifest.csv"
)

SEED = 20261028
ID_PREFIX = "XED1"
QUERY_TYPE = "cross_edition_transliteration"
MIN_TOKENS = 5  # the pair file's own floor
TWIN_NEAR_COPY = 0.9  # Experiment 3's builder line for "near-twin of a target"
HIDE_TWIN_THRESHOLD = 0.7  # the audit's twin line (eval_guards.DEFAULT_TWIN_THRESHOLD)
BBAW_WINDOW = 20
KEY_SEPARATOR = "|"

OUTPUT_COLUMNS = [
    "benchmark_id",
    "query_input",
    "query_type",
    "expected_transliteration",
    "expected_source_text_id",
    "expected_source_sentence_id",
    "expected_key_tokens",
    "expected_lemma_ids",
    "acceptable_token_overlap_threshold",
    "notes",
    "language_stage",
    # Read by the harness once the Route 1 change exists (pre-registration section 6):
    "hidden_row_keys",
    "expected_in_pool",
    # Informational; the harness never reads them.
    "pair_id",
    "source_pair",
    "direction",
    "query_source",
    "expected_source",
    "pair_jaccard",
]

REASONS = (
    "row_missing_from_corpus",
    "row_key_not_unique",
    "transliteration_changed_since_freeze",
    "removed_by_cleanup_part_1",
    "benchmark_target_row",
    "near_twin_of_benchmark_target",
    "same_text_as_benchmark_target",
    "bbaw_window_of_benchmark_target",
    "query_side_too_short",
)


def sha256_file(path: "str | Path") -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def row_key(text_id: object, sentence_id: object) -> tuple[str, str]:
    return str(text_id), str(sentence_id)


def hidden_item(text_id: str, sentence_id: str) -> str:
    """One `text_id|sentence_id` item of `hidden_row_keys` (space-separated list)."""
    for part in (text_id, sentence_id):
        if not part or any(ch.isspace() for ch in part) or KEY_SEPARATOR in part:
            raise ValueError(f"row id {part!r} cannot be written into hidden_row_keys")
    return f"{text_id}{KEY_SEPARATOR}{sentence_id}"


def load_removed_keys(path: "str | Path") -> set[tuple[str, str]]:
    """(text_id, sentence_id) of every manifest line whose decision is exactly `removed`.

    The manifest key is `source|source_text_id|source_sentence_id`; kept lines (`kept:
    annotated`, `kept: exception ...`) stay in the corpus and are not removed here.
    """
    manifest = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=["key", "decision"])
    removed: set[tuple[str, str]] = set()
    for key, decision in zip(manifest["key"], manifest["decision"]):
        if decision.strip() != "removed":
            continue
        parts = key.split(KEY_SEPARATOR)
        if len(parts) != 3:
            raise ValueError(f"manifest key {key!r} is not source|text_id|sentence_id")
        removed.add((parts[1], parts[2]))
    return removed


def collect_target_keys(
    directory: "str | Path", skip_substrings: tuple[str, ...] = ("xed_route1",)
) -> tuple[set[tuple[str, str]], dict[str, int]]:
    """Every row any committed benchmark file names as an expected target.

    A file counts when it has both `expected_source_text_id` and
    `expected_source_sentence_id`: query sets, their results and failures files, held-out
    2 and the sealed held-out 3 alike (only these two id columns are read, never a query).
    Files of this benchmark itself are skipped so a rebuild cannot exclude its own rows.
    Returns the keys and, per file, how many it contributed.
    """
    keys: set[tuple[str, str]] = set()
    per_file: dict[str, int] = {}
    wanted = ["expected_source_text_id", "expected_source_sentence_id"]
    for path in sorted(Path(directory).glob("*.csv")):
        if any(part in path.name for part in skip_substrings):
            continue
        header = pd.read_csv(path, nrows=0).columns
        if not all(column in header for column in wanted):
            continue
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=wanted)
        found = {
            row_key(text_id, sentence_id)
            for text_id, sentence_id in zip(*(frame[column] for column in wanted))
            if text_id or sentence_id
        }
        per_file[path.name] = len(found)
        keys |= found
    return keys, per_file


def assign_directions(
    pair_ids_by_source_pair: dict[str, list[str]], seed: int
) -> dict[str, str]:
    """pair_id -> `A2B` (query is side a) or `B2A`, half and half per source pair.

    Inside each source pair the pair ids are sorted, shuffled with a generator seeded
    from (seed, source pair), and the first half (rounded down) is `A2B`. Odd groups
    give the extra pair to `B2A`. Depends on nothing but the ids and the seed.
    """
    directions: dict[str, str] = {}
    for source_pair in sorted(pair_ids_by_source_pair):
        ids = sorted(pair_ids_by_source_pair[source_pair])
        random.Random(f"{seed}|{source_pair}").shuffle(ids)
        half = len(ids) // 2
        for position, pair_id in enumerate(ids):
            directions[pair_id] = "A2B" if position < half else "B2A"
    return directions


def _frame_columns(corpus: pd.DataFrame) -> dict[str, list[str]]:
    def column(name: str) -> list[str]:
        if name not in corpus.columns:
            return [""] * len(corpus)
        return ["" if pd.isna(value) else str(value) for value in corpus[name]]

    return {
        name: column(name)
        for name in (
            "source",
            "source_text_id",
            "source_sentence_id",
            "transliteration_gold",
            "lemma_sequence",
            "language_stage",
        )
    }


def build_xed_queries(
    pairs: pd.DataFrame,
    corpus: pd.DataFrame,
    removed_keys: "set[tuple[str, str]]",
    target_keys: "set[tuple[str, str]]",
    seed: int = SEED,
) -> tuple[pd.DataFrame, dict]:
    """The sealed query frame and a counts-only report. Pure: no file is read or written.

    `corpus` needs source, source_text_id, source_sentence_id, transliteration_gold and
    (optionally) lemma_sequence and language_stage. `pairs` is the frozen pair file as a
    string frame.
    """
    cols = _frame_columns(corpus)
    guard = TwinGuard(corpus)
    sources = [value.strip() for value in cols["source"]]
    text_ids = cols["source_text_id"]
    sentence_ids = cols["source_sentence_id"]

    # Rules 4 to 7 depend only on the corpus and the target list: compute their row sets once.
    target_positions = sorted(
        {p for key in target_keys for p in guard.positions.get(key, ())}
    )
    near_twin_positions: set[int] = set()
    for position in target_positions:
        tokens = guard.token_sets[position]
        for other, _ in twin_rows(tokens, guard.token_sets, guard.token_index, TWIN_NEAR_COPY):
            near_twin_positions.add(other)
    same_text, in_window = same_text_exclusions(
        sources, text_ids, sentence_ids, target_positions, BBAW_WINDOW
    )
    target_position_set = set(target_positions)

    by_source_pair: dict[str, list[str]] = defaultdict(list)
    for pair_id, source_pair in zip(pairs["pair_id"], pairs["source_pair"]):
        by_source_pair[source_pair].append(pair_id)
    directions = assign_directions(by_source_pair, seed)

    rows: list[dict[str, str]] = []
    dropped: Counter = Counter()  # (reason, source_pair)
    pair_count: Counter = Counter()
    hidden_sizes: list[int] = []
    pairs_with_extra_b_twins = 0
    for pair in pairs.sort_values("pair_id").to_dict("records"):
        source_pair = pair["source_pair"]
        pair_count[source_pair] += 1
        direction = directions[pair["pair_id"]]
        query_side, expected_side = ("a", "b") if direction == "A2B" else ("b", "a")

        def side(prefix: str) -> dict[str, str]:
            return {
                "text_id": pair[f"{prefix}_text_id"],
                "sentence_id": pair[f"{prefix}_sentence_id"],
                "source": pair[f"{prefix}_source"],
                "transliteration": pair[f"{prefix}_transliteration"],
            }

        both = {"a": side("a"), "b": side("b")}
        positions: dict[str, int] = {}
        reason = ""
        for name in ("a", "b"):
            found = guard.positions.get(row_key(both[name]["text_id"], both[name]["sentence_id"]), [])
            if not found:
                reason = reason or "row_missing_from_corpus"
            elif len(found) > 1:
                reason = reason or "row_key_not_unique"
            else:
                positions[name] = found[0]
        if not reason:
            for name in ("a", "b"):
                if cols["transliteration_gold"][positions[name]].strip() != both[name][
                    "transliteration"
                ].strip():
                    reason = "transliteration_changed_since_freeze"
        if not reason:
            for name in ("a", "b"):
                key = row_key(both[name]["text_id"], both[name]["sentence_id"])
                if key in removed_keys:
                    reason = "removed_by_cleanup_part_1"
        if not reason:
            if any(positions[name] in target_position_set for name in ("a", "b")):
                reason = "benchmark_target_row"
            elif any(positions[name] in near_twin_positions for name in ("a", "b")):
                reason = "near_twin_of_benchmark_target"
            elif any(positions[name] in same_text for name in ("a", "b")):
                reason = "same_text_as_benchmark_target"
            elif any(positions[name] in in_window for name in ("a", "b")):
                reason = "bbaw_window_of_benchmark_target"
        if not reason and len(guard.token_sets[positions[query_side]]) < MIN_TOKENS:
            reason = "query_side_too_short"
        if reason:
            dropped[(reason, source_pair)] += 1
            continue

        query = both[query_side]
        expected = both[expected_side]
        query_position = positions[query_side]
        expected_position = positions[expected_side]

        # Leave-one-out set: the query's own row and its near-twins (loose-token
        # Jaccard >= 0.7 or the same notation-folded reading), never the answer row.
        query_row = pd.Series(
            {
                "expected_source_text_id": query["text_id"],
                "expected_source_sentence_id": query["sentence_id"],
            }
        )
        twin_positions = {
            p for p, _, _ in twins_of_target(guard, query_row, HIDE_TWIN_THRESHOLD)
        }
        hidden = {query_position} | twin_positions
        hidden.discard(expected_position)
        hidden_items = sorted(
            hidden_item(text_ids[p], sentence_ids[p]) for p in hidden
        )
        hidden_sizes.append(len(hidden_items))

        # Informational: does the answer row have other near-copies of its own?
        expected_row = pd.Series(
            {
                "expected_source_text_id": expected["text_id"],
                "expected_source_sentence_id": expected["sentence_id"],
            }
        )
        extra = {
            p for p, _, _ in twins_of_target(guard, expected_row, HIDE_TWIN_THRESHOLD)
        } - hidden - {query_position}
        if extra:
            pairs_with_extra_b_twins += 1

        key_tokens = sorted(guard.token_sets[expected_position])
        threshold = 0.34 if len(key_tokens) <= 4 else 0.26
        pair_number = pair["pair_id"].rsplit("_", 1)[-1]
        rows.append(
            {
                "benchmark_id": f"{ID_PREFIX}_{pair_number}",
                "query_input": query["transliteration"],
                "query_type": QUERY_TYPE,
                "expected_transliteration": expected["transliteration"],
                "expected_source_text_id": expected["text_id"],
                "expected_source_sentence_id": expected["sentence_id"],
                "expected_key_tokens": " ".join(key_tokens),
                "expected_lemma_ids": " ".join(_lemma_ids(cols["lemma_sequence"][expected_position])),
                "acceptable_token_overlap_threshold": f"{threshold:.2f}",
                "notes": (
                    f"Cross-edition ({pair['pair_id']}, {direction}): the query is the "
                    f"{query['source']} edition typed verbatim, the expected answer is the "
                    f"{expected['source']} edition and stays in the pool; the query's own "
                    "row and its near-twins are listed in hidden_row_keys."
                ),
                "language_stage": normalize_stage(cols["language_stage"][expected_position]) or "",
                "hidden_row_keys": " ".join(hidden_items),
                "expected_in_pool": "1",
                "pair_id": pair["pair_id"],
                "source_pair": source_pair,
                "direction": direction,
                "query_source": query["source"],
                "expected_source": expected["source"],
                "pair_jaccard": pair["jaccard"],
            }
        )

    queries = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    report = {
        "pairs_in": len(pairs),
        "queries_out": len(queries),
        "pairs_per_source_pair": dict(sorted(pair_count.items())),
        "queries_per_source_pair": dict(sorted(Counter(queries["source_pair"]).items())),
        "queries_per_direction": dict(sorted(Counter(queries["direction"]).items())),
        "queries_per_direction_and_source_pair": dict(
            sorted(Counter(zip(queries["source_pair"], queries["direction"])).items())
        ),
        "queries_per_query_source": dict(sorted(Counter(queries["query_source"]).items())),
        "queries_per_expected_source": dict(sorted(Counter(queries["expected_source"]).items())),
        "excluded_by_reason": {
            reason: sum(n for (r, _), n in dropped.items() if r == reason) for reason in REASONS
        },
        "excluded_by_reason_and_source_pair": {
            f"{reason} / {source_pair}": n for (reason, source_pair), n in sorted(dropped.items())
        },
        "hidden_row_keys_per_query": (
            {
                "min": min(hidden_sizes),
                "median": sorted(hidden_sizes)[len(hidden_sizes) // 2],
                "max": max(hidden_sizes),
                "queries_with_a_twin_hidden": sum(1 for n in hidden_sizes if n > 1),
            }
            if hidden_sizes
            else {}
        ),
        "queries_whose_answer_row_has_other_near_copies_in_pool_c": pairs_with_extra_b_twins,
        "target_rows_found_in_corpus": len(target_position_set),
        "target_keys_total": len(target_keys),
        "near_twin_rows_of_targets": len(near_twin_positions - target_position_set),
        "same_text_rows_of_targets": len(same_text - target_position_set),
        "bbaw_window_rows_of_targets": len(in_window - target_position_set),
    }
    return queries, report


def frame_to_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8")


def render_log(report: dict, context: dict[str, str], out_sha: str) -> str:
    """The build log: counts, input hashes, the output hash. Never a query."""
    lines = [
        "Route 1 cross-edition benchmark: build log (counts only; no query text appears here)",
        f"seed {context['seed']}",
        f"script {context['script']}",
        f"pairs file {PAIRS_PATH} sha256 {context['pairs_sha']}",
        f"corpus {EXAMPLES_PATH} sha256 {context['corpus_sha']}",
        f"cleanup removal manifest {context['manifest_name']} sha256 {context['manifest_sha']}",
        f"  ({context['removed_total']} lines with decision == removed)",
        f"benchmark files read for target rows ({context['target_files']}):",
    ]
    for name, count in context["per_file"].items():
        lines.append(f"  {name}: {count} keys")
    lines += [
        f"distinct target keys {report['target_keys_total']}, found in the corpus "
        f"{report['target_rows_found_in_corpus']}",
        f"rows removed by rule at the corpus level: {report['near_twin_rows_of_targets']} "
        f"near-twins (>= {TWIN_NEAR_COPY}), {report['same_text_rows_of_targets']} sharing a "
        f"TLA/AES/Ramses source_text_id, {report['bbaw_window_rows_of_targets']} BBAW rows "
        f"within +-{BBAW_WINDOW}",
        "",
        f"pairs in {report['pairs_in']}; queries out {report['queries_out']}",
        "pairs / queries per source pair:",
    ]
    for source_pair, n in report["pairs_per_source_pair"].items():
        lines.append(f"  {source_pair}: {n} pairs -> {report['queries_per_source_pair'].get(source_pair, 0)} queries")
    lines.append(f"queries per direction: {report['queries_per_direction']}")
    lines.append("queries per direction and source pair:")
    for (source_pair, direction), n in report["queries_per_direction_and_source_pair"].items():
        lines.append(f"  {source_pair} {direction}: {n}")
    lines.append(f"queries per query source: {report['queries_per_query_source']}")
    lines.append(f"queries per expected source: {report['queries_per_expected_source']}")
    lines.append("pairs excluded, each under the first rule that applies:")
    for reason, n in report["excluded_by_reason"].items():
        lines.append(f"  {reason}: {n}")
    lines.append("excluded by reason and source pair:")
    for label, n in report["excluded_by_reason_and_source_pair"].items():
        lines.append(f"  {label}: {n}")
    lines.append(f"hidden_row_keys per query: {report['hidden_row_keys_per_query']}")
    lines.append(
        "queries whose answer row has other near-copies (>= 0.7) left in pool C: "
        f"{report['queries_whose_answer_row_has_other_near_copies_in_pool_c']}"
    )
    lines += ["", f"sealed file {OUT_PATH}", f"sha256 {out_sha}"]
    return "\n".join(lines) + "\n"


def _run(args: argparse.Namespace) -> tuple[bytes, str]:
    pairs = pd.read_csv(args.pairs, dtype=str, keep_default_na=False)
    corpus = load_examples_csv(args.examples)
    removed = load_removed_keys(args.removal_manifest)
    targets, per_file = collect_target_keys(Path(args.pairs).parent)
    queries, report = build_xed_queries(pairs, corpus, removed, targets, seed=args.seed)
    if len(queries) < args.minimum:
        raise SystemExit(
            f"only {len(queries)} usable queries (< {args.minimum}); nothing written."
        )
    payload = frame_to_bytes(queries)
    out_sha = hashlib.sha256(payload).hexdigest()
    context = {
        "seed": str(args.seed),
        "script": "scripts/build_route1_xed_benchmark.py",
        "pairs_sha": sha256_file(args.pairs),
        "corpus_sha": sha256_file(args.examples),
        "manifest_name": f"{Path(args.removal_manifest).parent.name}/{Path(args.removal_manifest).name}",
        "manifest_sha": sha256_file(args.removal_manifest),
        "removed_total": str(len(removed)),
        "target_files": str(len(per_file)),
        "per_file": per_file,
    }
    return payload, render_log(report, context, out_sha)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pairs", default=PAIRS_PATH)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--removal-manifest", default=MANIFEST_PATH)
    parser.add_argument("--out", default=OUT_PATH)
    parser.add_argument("--log", default=LOG_PATH)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--minimum", type=int, default=100, help="Refuse to write fewer queries.")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Rebuild in memory and compare with the existing sealed file; write nothing.",
    )
    args = parser.parse_args(argv)
    payload, log_text = _run(args)
    out = Path(args.out)
    if args.verify:
        same = out.exists() and out.read_bytes() == payload
        print(f"verify: {'identical' if same else 'DIFFERENT'} ({hashlib.sha256(payload).hexdigest()})")
        return 0 if same else 1
    if out.exists():
        print(f"{out} already exists: the sealed file is built once. Use --verify.", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(payload)
    Path(args.log).write_text(log_text, encoding="utf-8")
    print(log_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

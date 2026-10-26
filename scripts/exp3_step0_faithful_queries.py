"""Experiment 3, step 0 — faithful query variants and the kill switch. No ranker code.

Pre-registered in ROADMAP.md ("Experiment 3 — the notation-faithful search key",
2026-09-07; re-scoped by the addendum of 2026-10-26). For every query of v4,
held-out 1, LE-v1 and NAME-v1 this derives a query written in Unicode
transliteration (ꜣ ꜥ ḥ ḫ ẖ … kept) from `expected_transliteration`, checks that it
folds back to the stored query, and counts the queries that *can* move under a
notation-faithful key: those with at least one token whose folded key merges two
spellings that differ in ꜣ/ꜥ, ḫ/ẖ or ḥ/h somewhere in the public corpus.

Two derivations, both reported:

* **recipe** — the builder's recipe minus the fold (scripts/
  build_competitive_ambiguity_benchmark.py `_competitive_query`), per query type:
  the faithful token list (`unfolded_reading_form`, with the editor-supplied yods the
  search key drops removed first) is paired one-to-one with its loose fold, and every
  decision the builder takes (strip a light ending, drop a stop token, truncate) is
  taken on the *folded* token and applied to the faithful one. NAME-v1's respelled
  name (recorded in `notes`) is substituted first, as the builder did.
* **aligned** (the repair) — each stored query token is replaced by a faithful
  spelling from the expected transliteration that folds to exactly that token;
  a token with no such spelling stays as stored (ASCII). So the fold-back holds by
  construction wherever the stored query is a fixed point of `search_fold`, and the
  ASCII tokens left are the recorded residue.

The movers are counted on the aligned variant. A token counts under the
pre-registered rule when its `search_fold` key is a merging key; the stricter count
also requires the token itself to carry a letter of that pair (a token typed as
plain `nb` cannot be told apart by any key).

Merging keys follow the method recorded with the 2026-09-07 measurement (expert-round-2
write-up): every whitespace token of `transliteration_gold` is folded with
`search_fold`; a key merges pair (x, y) when tokens with and without the second letter
y fold to it. The script prints its counts next to the recorded 681 / 242 / 638 so
the reuse can be checked.

Light: string work on 100 queries plus one pass over one corpus column.

    python scripts/exp3_step0_faithful_queries.py \
        --out-csv data/benchmarks/exp3_step0_faithful_queries.csv \
        --baseline-dir ~/egyptology-runs/remeasure-2026-10-25
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import (  # noqa: E402
    PARENTHESISED_YOD_RE,
    fold_strict_aliases,
    normalize_mdc,
    normalize_notation,
    search_fold,
)
from app.data.query import parse_query, vocabulary_from  # noqa: E402
from app.services.suggestions import (  # noqa: E402
    loose_reading_form,
    strict_reading_key,
    QueryForms,
    unfolded_reading_form,
)
from scripts.build_competitive_ambiguity_benchmark import STOP_TOKENS  # noqa: E402

EXAMPLES_PATH = "data/processed/examples.csv"
BENCHMARKS = {
    "v4": "data/benchmarks/competitive_ambiguity_eval_queries_v4.csv",
    "held-out 1": "data/benchmarks/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv",
    "LE-v1": "data/benchmarks/competitive_ambiguity_eval_queries_le_v1.csv",
    "NAME-v1": "data/benchmarks/competitive_ambiguity_eval_queries_name_v1.csv",
}
# (name, first letter, second letter): the merges Nederhof rejected (sixth mail).
PAIRS = (("aleph/ayin", "ꜣ", "ꜥ"), ("kh/khh", "ḫ", "ẖ"), ("h-dot/h", "ḥ", "h"))
RECORDED_MERGING_KEYS = {"aleph/ayin": 681, "kh/khh": 242, "h-dot/h": 638}
# Attempt-2 run files (outside the repo) per set, for the baseline printout.
BASELINE_FILES = {
    "v4": ("v4_L_auto.csv", "v4_T_auto.csv"),
    "held-out 1": ("holdout_L_auto.csv", "holdout_T_auto.csv"),
    "LE-v1": ("le_v1_L_auto.csv", "le_v1_T_auto.csv"),
}
NAME_COMMITTED = "data/benchmarks/ceval_name_v1_app_auto_results.csv"
RESPELLED_RE = re.compile(r"respelled (\S+) -> (\S+?)\.?$")
# ASCII angle brackets (Ramses' editorial `=<ꞽ>`) survive the unfolded form but not
# the search key; nobody types them, so they are removed from a faithful spelling.
ASCII_EDITORIAL_RE = re.compile(r"[<>]")


# --------------------------------------------------------------------------- pieces


def faithful_pairs(transliteration: str) -> list[tuple[str, str]]:
    """(faithful token, its loose fold) for every token the builder's loose form has.

    The editor-supplied yod in round brackets is removed first because the search
    key (and so the loose form) drops it; a piece whose loose fold is empty (`ʾ`,
    `?`) is dropped for the same reason. A piece that folds to several tokens keeps
    its fold as one string — it never occurs in the four sets, and the fold-back
    check would show it.
    """
    text = PARENTHESISED_YOD_RE.sub("", normalize_notation(str(transliteration)))
    pairs: list[tuple[str, str]] = []
    for piece in unfolded_reading_form(text).split():
        piece = ASCII_EDITORIAL_RE.sub("", piece)
        folded = loose_reading_form(piece)
        if piece and folded:
            pairs.append((piece, folded))
    return pairs


def _strip_ending(pair: tuple[str, str]) -> tuple[str, str]:
    """The builder's `_strip_some_endings`, decided on the folded token."""
    faithful, folded = pair
    if len(folded) > 4 and folded.endswith(("t", "w", "j", "y")):
        return faithful[:-1], folded[:-1]
    return pair


def recipe_query(transliteration: str, query_type: str) -> str:
    """The builder's recipe minus the fold (see the module docstring)."""
    if query_type == "normalized_reading_order":
        # The builder took the corpus row's `normalized_reading_order` column (the
        # import-time fold of the whole reading, hyphens kept); its faithful
        # counterpart is each whitespace word with brackets and dots removed.
        text = PARENTHESISED_YOD_RE.sub("", normalize_notation(str(transliteration)))
        words = [fold_strict_aliases(strict_reading_key(word)) for word in text.split()]
        tokens = [word for word in words if search_fold(word)]
        if len(tokens) > 5:
            tokens = tokens[: max(4, round(len(tokens) * 0.75))]
        return " ".join(tokens)
    pairs = [_strip_ending(pair) for pair in faithful_pairs(transliteration)]
    content = [pair for pair in pairs if pair[1] not in STOP_TOKENS] or pairs
    if query_type == "partial_transliteration":
        keep = max(2, min(len(content), round(len(content) * 0.6)))
        chosen = content[:keep]
    else:
        chosen = content[:8]
    return " ".join(faithful for faithful, _ in chosen)


def _candidate_spellings(transliteration: str) -> tuple[list[str], list[str]]:
    """The faithful spellings the expected reading offers, in reading order: first
    the tokens and their light-ending-stripped forms, then (second tier, tried only
    when no token fits) whole whitespace words, for hyphenated reading-order tokens."""
    tokens: list[str] = []
    for faithful, folded in faithful_pairs(transliteration):
        tokens.append(faithful)
        stripped, _ = _strip_ending((faithful, folded))
        if stripped != faithful:
            tokens.append(stripped)
    text = PARENTHESISED_YOD_RE.sub("", normalize_notation(str(transliteration)))
    words: list[str] = []
    for word in text.split():
        whole = ASCII_EDITORIAL_RE.sub("", fold_strict_aliases(strict_reading_key(word)))
        if whole and whole not in tokens and whole not in words:
            words.append(whole)
    return tokens, words


def aligned_query(query_input: str, transliteration: str) -> tuple[str, list[str]]:
    """Each stored token rewritten as a faithful spelling that folds to it exactly;
    returns (query, stored tokens left as typed). The first unused match at or after
    the previous match wins, then any unused match, so repeated words keep order."""
    tokens, words = _candidate_spellings(transliteration)
    spellings = tokens + words
    folds = [search_fold(spelling) for spelling in spellings]
    used: set[int] = set()
    cursor = 0
    out: list[str] = []
    residue: list[str] = []
    for token in str(query_input).split():
        order = (
            list(range(cursor, len(tokens)))
            + list(range(0, min(cursor, len(tokens))))
            + list(range(len(tokens), len(spellings)))
        )
        match = next((i for i in order if i not in used and folds[i] == token), None)
        if match is None:
            out.append(token)
            residue.append(token)
            continue
        used.add(match)
        if match < len(tokens):
            cursor = match + 1
        out.append(spellings[match])
    return " ".join(out), residue


def apply_respelling(transliteration: str, notes: str) -> str:
    """NAME-v1: substitute the respelled name recorded in `notes`, as the builder did
    (first whitespace token equal to the original spelling)."""
    match = RESPELLED_RE.search(str(notes or ""))
    if not match:
        return transliteration
    original, substitute = match.group(1), match.group(2)
    tokens = str(transliteration).split()
    for index, token in enumerate(tokens):
        if token == original:
            tokens[index] = substitute
            break
    return " ".join(tokens)


# --------------------------------------------------------------------- merging keys


def merging_keys(
    tokens: set[str], conservative: bool = False
) -> tuple[dict[str, set[str]], int]:
    """Per pair, the folded keys that tokens with and without its second letter both
    fold to; and the number of distinct folded keys.

    `conservative` (a sensitivity check, not the recorded method) also requires the
    token without the second letter to carry the first one, so a key merges only when
    an actual x-spelling and an actual y-spelling meet in it."""
    by_key: dict[str, set[str]] = defaultdict(set)
    for token in tokens:
        key = search_fold(token)
        if key:
            by_key[key].add(token)
    merging: dict[str, set[str]] = {name: set() for name, _, _ in PAIRS}
    for key, spellings in by_key.items():
        if len(spellings) < 2:
            continue
        for name, first, second in PAIRS:
            with_second = any(second in spelling for spelling in spellings)
            without_second = any(
                second not in spelling and (first in spelling or not conservative)
                for spelling in spellings
            )
            if with_second and without_second:
                merging[name].add(key)
    return merging, len(by_key)


def corpus_tokens(path: str) -> tuple[set[str], set[str], int, str]:
    """(lower-cased NFC whitespace tokens of `transliteration_gold`, the search
    vocabulary, row count, sha256). The vocabulary is what `parse_query` is handed by
    the app (`SearchIndex.stats.mdc_frequencies`): the tokens of `mdc_norm`, which
    the loader folds from the transliteration and falls back to the stored `mdc`
    column only where there is no transliteration (app/data/loader.py)."""
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    frame = pd.read_csv(
        path, usecols=["transliteration_gold", "mdc"], dtype=str, keep_default_na=False
    )
    tokens: set[str] = set()
    for value in frame["transliteration_gold"]:
        tokens.update(nfc_lower(value).split())
    has_reading = frame["transliteration_gold"].str.strip() != ""
    keys = frame["transliteration_gold"].map(search_fold).where(
        has_reading, frame["mdc"].map(normalize_mdc)
    )
    vocabulary = vocabulary_from(keys)
    return tokens, vocabulary, len(frame), sha


def nfc_lower(value: str) -> str:
    return unicodedata.normalize("NFC", str(value)).lower()


def mover_tokens(query: str, merging: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    """(pre-registered: key merges; strict: key merges and the token carries a letter
    of that pair) as `token[pair]` strings."""
    loose_hits: list[str] = []
    strict_hits: list[str] = []
    for token in query.split():
        key = search_fold(token)
        for name, first, second in PAIRS:
            if key in merging[name]:
                loose_hits.append(f"{token}[{name}]")
                lowered = token.lower()
                if first in lowered or second in lowered:
                    strict_hits.append(f"{token}[{name}]")
    return loose_hits, strict_hits


# ------------------------------------------------------------------------ baselines


def _metrics(path: Path) -> tuple[float, float, int]:
    frame = pd.read_csv(path)
    ranks = pd.to_numeric(frame["useful_family_rank"], errors="coerce")
    top3 = float(frame["top3_useful_family_hit"].astype(bool).mean())
    mrr = float((1.0 / ranks).fillna(0.0).mean())
    return top3, mrr, len(frame)


def print_baselines(baseline_dir: Path | None, log: list[str]) -> None:
    log.append(
        "Baselines of the STORED (folded-ASCII) queries. Not the faithful sets' baseline: "
        "their retrieval key is identical, but A54 re-ranks them in strict/mixed mode, so "
        "today's faithful-set numbers must be measured (addendum 2026-10-26)."
    )
    for name, (legacy, twin) in BASELINE_FILES.items():
        if baseline_dir is None or not (baseline_dir / legacy).exists():
            log.append(f"  {name}: attempt-2 files not available")
            continue
        l3, lm, n = _metrics(baseline_dir / legacy)
        t3, tm, _ = _metrics(baseline_dir / twin)
        log.append(
            f"  {name} ({n}): legacy pool L-auto {l3:.4f} / MRR {lm:.4f}; "
            f"twin-controlled T-auto {t3:.4f} / MRR {tm:.4f}  [attempt 2, {baseline_dir.name}]"
        )
    if Path(NAME_COMMITTED).exists():
        n3, nm, n = _metrics(Path(NAME_COMMITTED))
        log.append(
            f"  NAME-v1 ({n}): committed {n3:.4f} / MRR {nm:.4f}  [pre-audit D' tree; "
            "not re-measured in attempt 2 — step 3 must re-measure it]"
        )


# ----------------------------------------------------------------------------- main


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--out-csv", default="")
    parser.add_argument("--log", default="")
    parser.add_argument("--baseline-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    log: list[str] = ["Experiment 3, step 0 — faithful query variants (read-only, no ranker code)", ""]

    tokens, vocabulary, rows, sha = corpus_tokens(args.examples)
    merging, key_count = merging_keys(tokens)
    conservative, _ = merging_keys(tokens, conservative=True)
    log.append(f"Corpus {args.examples}: {rows} rows, sha256 {sha}")
    log.append(f"Distinct whitespace tokens {len(tokens)}; distinct folded keys {key_count}")
    for name, _, _ in PAIRS:
        log.append(
            f"  merging keys {name}: {len(merging[name])} (recorded 2026-09-07: "
            f"{RECORDED_MERGING_KEYS[name]}); conservative variant {len(conservative[name])}"
        )
    log.append(
        "  (not reproduced: 35,808 keys then, the fold has changed since (audit fixes) and "
        "the 2026-09-07 counting code was not kept; the conservative variant is a "
        "sensitivity check on the mover counts)"
    )
    log.append("")

    records: list[dict] = []
    summary: list[str] = []
    for set_name, path in BENCHMARKS.items():
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        recipe_bad: list[str] = []
        aligned_bad: list[str] = []
        key_differs: list[str] = []
        notations: dict[str, int] = defaultdict(int)
        modes: dict[str, int] = defaultdict(int)
        residue_ids: list[str] = []
        movers_pre: list[str] = []
        movers_strict: list[str] = []
        movers_conservative: list[str] = []
        for row in frame.itertuples(index=False):
            source = row.expected_transliteration
            if set_name == "NAME-v1":
                source = apply_respelling(source, row.notes)
            stored = row.query_input
            recipe = recipe_query(source, row.query_type)
            aligned, residue = aligned_query(stored, source)
            recipe_ok = search_fold(recipe) == stored
            aligned_ok = search_fold(aligned) == stored
            stored_parse = parse_query(stored, vocabulary=vocabulary)
            faithful_parse = parse_query(aligned, vocabulary=vocabulary)
            same_key = stored_parse.search_key == faithful_parse.search_key
            notations[faithful_parse.notation] += 1
            # The re-rank mode A54 would use for this query (suggest_top_readings
            # builds QueryForms from the resolved reading and the query as typed).
            mode = QueryForms.build(faithful_parse.reading or aligned, aligned).mode
            modes[mode] += 1
            loose_hits, strict_hits = mover_tokens(aligned, merging)
            _, conservative_hits = mover_tokens(aligned, conservative)
            if not recipe_ok:
                recipe_bad.append(row.benchmark_id)
            if not aligned_ok:
                aligned_bad.append(row.benchmark_id)
            if not same_key:
                key_differs.append(row.benchmark_id)
            if residue:
                residue_ids.append(f"{row.benchmark_id}({' '.join(residue)})")
            if loose_hits:
                movers_pre.append(row.benchmark_id)
            if strict_hits:
                movers_strict.append(row.benchmark_id)
            if conservative_hits:
                movers_conservative.append(row.benchmark_id)
            records.append(
                {
                    "set": set_name,
                    "benchmark_id": row.benchmark_id,
                    "query_type": row.query_type,
                    "query_input": stored,
                    "faithful_recipe": recipe,
                    "recipe_foldback_ok": recipe_ok,
                    "faithful_query": aligned,
                    "foldback_ok": aligned_ok,
                    "stored_notation": stored_parse.notation,
                    "faithful_notation": faithful_parse.notation,
                    "same_retrieval_key": same_key,
                    "a54_rerank_mode": mode,
                    "ascii_residue_tokens": " ".join(residue),
                    "merging_tokens": " ".join(loose_hits),
                    "merging_tokens_with_pair_letter": " ".join(strict_hits),
                    "can_move": bool(loose_hits),
                    "can_move_strict": bool(strict_hits),
                }
            )
        n = len(frame)
        log.append(f"== {set_name} ({n} queries, {path})")
        log.append(f"  recipe fold-back differs: {len(recipe_bad)}  {' '.join(recipe_bad)}")
        log.append(f"  aligned fold-back differs: {len(aligned_bad)}  {' '.join(aligned_bad)}")
        log.append(
            f"  retrieval key (parse_query with the corpus vocabulary) differs from the "
            f"stored query's: {len(key_differs)}  {' '.join(key_differs)}"
        )
        log.append(f"  faithful queries read as: {dict(sorted(notations.items()))}")
        log.append(f"  A54 re-rank mode of the faithful queries: {dict(sorted(modes.items()))}")
        log.append(f"  queries with ASCII residue tokens: {len(residue_ids)}  {' '.join(residue_ids)}")
        log.append(f"  can move (pre-registered rule): {len(movers_pre)}  {' '.join(movers_pre)}")
        log.append(
            f"  can move (token carries a letter of the pair): {len(movers_strict)}  "
            f"{' '.join(movers_strict)}"
        )
        log.append(
            f"  can move (conservative merging keys, sensitivity): "
            f"{len(movers_conservative)}"
        )
        summary.append(
            f"  {set_name}: recipe residue {len(recipe_bad)}/{n}, aligned residue "
            f"{len(aligned_bad)}/{n}, movers {len(movers_pre)}/{n} (strict {len(movers_strict)}/{n}), retrieval key differs {len(key_differs)}/{n}"
        )

    total_movers = sum(1 for record in records if record["can_move"])
    log.append("")
    log.append("Summary")
    log.extend(summary)
    log.append(
        "Stop rule (0 movers on every set): "
        + ("STOP — null, build a set for the effect" if total_movers == 0 else "not triggered")
    )
    log.append("")
    print_baselines(Path(args.baseline_dir).expanduser() if args.baseline_dir else None, log)

    text = "\n".join(log) + "\n"
    print(text, end="")
    if args.log:
        Path(args.log).write_text(text, encoding="utf-8")
    if args.out_csv:
        pd.DataFrame(records).to_csv(args.out_csv, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

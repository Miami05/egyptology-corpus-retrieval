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
* **aligned** (the repair, used only where the recipe's fold-back fails) — each
  stored query token is replaced by a faithful spelling from the expected
  transliteration that folds to exactly that token (whole tokens first, repeated
  occurrences kept, suffix pronouns keep their `=`); a token with no such spelling is
  then aligned character by character against the expected words (the fewest
  skipped characters; e.g. `kh` -> `ḫ` from `wḫꜣ{ḫ}`, `maa-hr-b` -> `mꜣꜥ-ḥr-b`), and
  only a token with neither stays as stored (ASCII residue).

The faithful query is the recipe's where its fold-back holds, otherwise the aligned
one (revision 2026-10-26 after the Opus/Astra review; the first run replaced every
recipe output, which lost distinctions in HOLD_024 and HOLD_027).

The movers are counted on the faithful query. A token counts under the
pre-registered rule when its `search_fold` key is a merging key; the stricter count
also requires the token itself to carry a letter of that pair (a token typed as
plain `nb` cannot be told apart by any key).

Merging keys, two methods. *Pre-registered*: a reconstruction of the method of the
2026-09-07 measurement (its write-up and code were never tracked, so it cannot be
checked): every raw whitespace token of `transliteration_gold` is folded with
`search_fold`; a key merges pair (x, y) when tokens with and without the second letter
y fold to it. Raw tokens keep editorial text (`n{ꜣ}`, `{ꜥ}〈n〉`) that `search_fold`
deletes, so `n`, `m`, `nb`, `pn` become "merging" keys: inflated. *Cleaned* (the
meaningful number): the same grouping on the pieces of `unfolded_reading_form` (the
faithful words with editorial text removed). Both are printed, next to the recorded
681 / 242 / 638 (which were probably inflated the same way).

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
    "v4": ("v4_L_auto.csv", "v4_C_auto.csv", "v4_T_auto.csv"),
    "held-out 1": ("holdout_L_auto.csv", "holdout_C_auto.csv", "holdout_T_auto.csv"),
    "LE-v1": ("le_v1_L_auto.csv", "le_v1_C_auto.csv", "le_v1_T_auto.csv"),
}
NAME_COMMITTED = "data/benchmarks/ceval_name_v1_app_auto_results.csv"
RESPELLED_RE = re.compile(r"respelled (\S+) -> (\S+?)\.?$")
# ASCII angle brackets (Ramses' editorial `=<ꞽ>`) survive the unfolded form but not
# the search key; nobody types them, so they are removed from a faithful spelling.
ASCII_EDITORIAL_RE = re.compile(r"[<>]")


# --------------------------------------------------------------------------- pieces


def faithful_tokens(transliteration: str) -> list[tuple[str, str, bool]]:
    """(faithful token, its loose fold, glued) for every token the builder's loose form
    has; `glued` marks a suffix pronoun written inline (`tw=ꞽ`), which is joined to
    the token before it without a space when that token is kept (`_join`).

    The editor-supplied yod in round brackets is removed first because the search
    key (and so the loose form) drops it; a piece whose loose fold is empty (`ʾ`,
    `?`) is dropped for the same reason. A piece that folds to several tokens keeps
    its fold as one string — it never occurs in the four sets, and the fold-back
    check would show it.

    A suffix pronoun keeps its `=` (it folds away, so fold-back holds), both when it
    stands alone (`n =f`) and when it is written inline (`tw=ꞽ`; revision round 2:
    the inline boundary was lost, `tw=ꞽ` became `tw ꞽ`, and A54 reads the two
    differently — `tw` alone is an ASCII-only word).
    """
    text = PARENTHESISED_YOD_RE.sub("", normalize_notation(str(transliteration)))
    out: list[tuple[str, str, bool]] = []
    for word in text.split():
        for segment_index, segment in enumerate(word.replace("⸗", "=").split("=")):
            first = True
            for piece in unfolded_reading_form(segment).split():
                piece = ASCII_EDITORIAL_RE.sub("", piece)
                folded = loose_reading_form(piece)
                if not (piece and folded):
                    continue
                if segment_index > 0 and first:
                    # Glued only when the word has text before the `=` (`tw=ꞽ`).
                    glued = bool(word.replace("⸗", "=").split("=")[0].strip())
                    out.append(("=" + piece, folded, glued))
                else:
                    out.append((piece, folded, False))
                first = False
    return out


def faithful_pairs(transliteration: str) -> list[tuple[str, str]]:
    """(faithful token, its loose fold), see `faithful_tokens`."""
    return [(faithful, folded) for faithful, folded, _ in faithful_tokens(transliteration)]


def _join(tokens: list[tuple[str, bool]]) -> str:
    """Join (spelling, glue to the previous one) pairs into a query."""
    text = ""
    for spelling, glue in tokens:
        text += spelling if (glue and text) else (" " + spelling if text else spelling)
    return text


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
    entries = faithful_tokens(transliteration)
    pairs = [_strip_ending((faithful, folded)) for faithful, folded, _ in entries]
    indexed = list(enumerate(pairs))
    content = [item for item in indexed if item[1][1] not in STOP_TOKENS] or indexed
    if query_type == "partial_transliteration":
        keep = max(2, min(len(content), round(len(content) * 0.6)))
        chosen = content[:keep]
    else:
        chosen = content[:8]
    # An inline suffix is glued back only when its host token is kept right before it.
    out: list[tuple[str, bool]] = []
    previous = None
    for index, (faithful, _) in chosen:
        out.append((faithful, entries[index][2] and previous == index - 1))
        previous = index
    return _join(out)


def _candidate_spellings(
    transliteration: str,
) -> tuple[list[str], list[str], list[tuple[int, bool]]]:
    """The faithful spellings the expected reading offers, in reading order: first
    the tokens and their light-ending-stripped forms, then (second tier, tried only
    when no token fits) whole whitespace words, for hyphenated reading-order tokens.
    The third list gives, per token, (index of its `faithful_tokens` entry, glued)."""
    tokens: list[str] = []
    origin: list[tuple[int, bool]] = []
    for entry, (faithful, folded, glued) in enumerate(faithful_tokens(transliteration)):
        tokens.append(faithful)
        origin.append((entry, glued))
        stripped, _ = _strip_ending((faithful, folded))
        if stripped != faithful:
            tokens.append(stripped)
            origin.append((entry, glued))
    text = PARENTHESISED_YOD_RE.sub("", normalize_notation(str(transliteration)))
    words: list[str] = []
    for word in text.split():
        whole = ASCII_EDITORIAL_RE.sub("", fold_strict_aliases(strict_reading_key(word)))
        # Repeated words are kept: each occurrence can be used once (`used` below).
        if whole and whole not in tokens:
            words.append(whole)
    return tokens, words, origin


def _raw_words(transliteration: str) -> list[str]:
    """The expected reading's whitespace words, notation normalised, nothing removed
    (the character alignment may need text the search key deletes, e.g. `{ḫ}`)."""
    text = PARENTHESISED_YOD_RE.sub("", normalize_notation(str(transliteration)))
    return [fold_strict_aliases(word) for word in text.split()]


def char_align(token: str, spelling: str) -> tuple[str, int] | None:
    """A faithful spelling for the ASCII `token` built from `spelling`'s characters in
    order: each kept chunk (1-3 code points: letters, combining marks, digits or `-`)
    folds to the next piece of the token, any other character is skipped. Returns (spelling, skipped) with the fewest skips, or
    None. Upper-case ASCII (`PL`) is lower-cased; the result must fold back exactly."""
    n, m = len(spelling), len(token)
    best: dict[tuple[int, int], tuple[int, str]] = {(0, 0): (0, "")}
    for i in range(n + 1):
        for j in range(m + 1):
            state = best.get((i, j))
            if state is None or i == n:
                continue
            cost, built = state
            moves = [((i + 1, j), cost + 1, built)]
            for k in range(i + 1, min(n, i + 3) + 1):
                chunk = spelling[i:k]
                if not all(
                    unicodedata.category(char)[0] in "LMN" or char == "-" for char in chunk
                ):
                    continue  # brackets, dots, `=`: skipped, never carried inside a chunk
                folded = search_fold(chunk) if chunk != "-" else "-"
                if folded and token.startswith(folded, j):
                    text = chunk.lower() if chunk.isascii() else chunk
                    moves.append(((k, j + len(folded)), cost, built + text))
            for key, new_cost, new_built in moves:
                if key not in best or new_cost < best[key][0]:
                    best[key] = (new_cost, new_built)
    final = best.get((n, m))
    if final is None or search_fold(final[1]) != token:
        return None
    return final[1], final[0]


def aligned_query(
    query_input: str, transliteration: str
) -> tuple[str, list[str], list[str]]:
    """Each stored token rewritten as a faithful spelling that folds to it exactly;
    returns (query, stored tokens left as typed, tokens repaired by character
    alignment as `stored->faithful`). The first unused match at or after the previous
    match wins, then any unused match, so repeated words keep order."""
    tokens, words, origin = _candidate_spellings(transliteration)
    spellings = tokens + words
    folds = [search_fold(spelling) for spelling in spellings]
    used: set[int] = set()
    cursor = 0
    out: list[tuple[str, bool]] = []
    previous_entry: int | None = None
    residue: list[str] = []
    char_aligned: list[str] = []
    raw_words = _raw_words(transliteration)
    for token in str(query_input).split():
        order = (
            list(range(cursor, len(tokens)))
            + list(range(0, min(cursor, len(tokens))))
            + list(range(len(tokens), len(spellings)))
        )
        match = next((i for i in order if i not in used and folds[i] == token), None)
        if match is None:
            options = [
                (result[1], index, result[0])
                for index, word in enumerate(raw_words)
                if (result := char_align(token, word)) is not None
            ]
            if options:
                _, _, spelling = min(options)
                out.append((spelling, False))
                char_aligned.append(f"{token}->{spelling}")
            else:
                out.append((token, False))
                residue.append(token)
            previous_entry = None
            continue
        used.add(match)
        glue = False
        if match < len(tokens):
            cursor = match + 1
            entry, glued = origin[match]
            # An inline suffix (`tw=ꞽ`) is glued back only right after its host token.
            glue = glued and previous_entry == entry - 1
            previous_entry = entry
        else:
            previous_entry = None
        out.append((spellings[match], glue))
    return _join(out), residue, char_aligned


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


def corpus_tokens(path: str) -> tuple[set[str], set[str], set[str], int, str]:
    """(lower-cased NFC whitespace tokens of `transliteration_gold`, the lower-cased
    pieces of its `unfolded_reading_form` (editorial text removed), the search
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
    cleaned: set[str] = set()
    for value in frame["transliteration_gold"]:
        tokens.update(nfc_lower(value).split())
    for value in frame["transliteration_gold"].unique():
        cleaned.update(cleaned_pieces(value))
    has_reading = frame["transliteration_gold"].str.strip() != ""
    keys = frame["transliteration_gold"].map(search_fold).where(
        has_reading, frame["mdc"].map(normalize_mdc)
    )
    vocabulary = vocabulary_from(keys)
    return tokens, cleaned, vocabulary, len(frame), sha


def nfc_lower(value: str) -> str:
    return unicodedata.normalize("NFC", str(value)).lower()


def cleaned_pieces(text: str) -> list[str]:
    """The cleaned method's tokenisation, used for the corpus keys *and* the query
    tokens matched against them (revision round 2: the query side used whitespace
    tokens, so `pr-ḫrw` or `tw=ꞽ` never met the corpus pieces `ḫrw`, `ꞽ`)."""
    return unfolded_reading_form(unicodedata.normalize("NFC", str(text))).lower().split()


def mover_tokens(
    query: str, merging: dict[str, set[str]], tokenise=str.split
) -> tuple[list[str], list[str]]:
    """(pre-registered: key merges; strict: key merges and the token carries a letter
    of that pair) as `token[pair]` strings. `tokenise` must match how the merging
    keys' tokens were made: whitespace for the raw method, `cleaned_pieces` for the
    cleaned one."""
    loose_hits: list[str] = []
    strict_hits: list[str] = []
    for token in tokenise(query):
        key = search_fold(token)
        for name, first, second in PAIRS:
            if key in merging[name]:
                loose_hits.append(f"{token}[{name}]")
                lowered = token.lower()
                if first in lowered or second in lowered:
                    strict_hits.append(f"{token}[{name}]")
    return loose_hits, strict_hits


# ------------------------------------------------------------------------ baselines


def _metrics(path: Path) -> tuple[float, float, int, int]:
    """(top-3 useful, MRR, rank-1 count, queries)."""
    frame = pd.read_csv(path)
    ranks = pd.to_numeric(frame["useful_family_rank"], errors="coerce")
    top3 = float(frame["top3_useful_family_hit"].astype(bool).mean())
    mrr = float((1.0 / ranks).fillna(0.0).mean())
    return top3, mrr, int((ranks == 1).sum()), len(frame)


def print_baselines(baseline_dir: Path | None, log: list[str]) -> None:
    log.append(
        "Baselines of the STORED (folded-ASCII) queries. Not the faithful sets' baseline: "
        "their retrieval key is identical, but A54 re-ranks them in strict/mixed mode, so "
        "today's faithful-set numbers must be measured (addendum 2026-10-26)."
    )
    log.append(
        "  (top-3 / MRR / rank-1; L = legacy pool, --expected-tokens frozen; C = legacy "
        "pool, current; T = twin-controlled 0.7, current. Experiment 3 compares C and T.)"
    )
    for name, files in BASELINE_FILES.items():
        if baseline_dir is None or not all((baseline_dir / f).exists() for f in files):
            log.append(f"  {name}: attempt-2 files not available")
            continue
        parts = []
        for label, file in zip(("L-auto", "C-auto", "T-auto"), files):
            top3, mrr, rank1, n = _metrics(baseline_dir / file)
            parts.append(f"{label} {top3:.4f} / {mrr:.4f} / {rank1}")
        log.append(f"  {name} ({n}): " + "; ".join(parts) + f"  [attempt 2, {baseline_dir.name}]")
    if Path(NAME_COMMITTED).exists():
        n3, nm, r1, n = _metrics(Path(NAME_COMMITTED))
        log.append(
            f"  NAME-v1 ({n}): committed {n3:.4f} / {nm:.4f} / {r1}  [pre-audit D' tree; "
            "not re-measured in attempt 2 — the baseline run must re-measure it]"
        )


# ----------------------------------------------------------------------------- main


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--out-csv", default="")
    parser.add_argument("--log", default="")
    parser.add_argument("--baseline-dir", default="")
    parser.add_argument(
        "--faithful-benchmarks-dir",
        default="",
        help="Also write each set's benchmark file with query_input replaced by the "
        "faithful query (other columns unchanged; the stored query kept as "
        "stored_query_input), for the baseline and F-a runs.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    log: list[str] = ["Experiment 3, step 0 — faithful query variants (read-only, no ranker code)", ""]

    tokens, cleaned_tokens, vocabulary, rows, sha = corpus_tokens(args.examples)
    merging, key_count = merging_keys(tokens)
    conservative, _ = merging_keys(tokens, conservative=True)
    cleaned, cleaned_key_count = merging_keys(cleaned_tokens)
    log.append(f"Corpus {args.examples}: {rows} rows, sha256 {sha}")
    log.append(f"Distinct whitespace tokens {len(tokens)}; distinct folded keys {key_count}")
    log.append(
        f"Distinct cleaned words (unfolded_reading_form pieces) {len(cleaned_tokens)}; "
        f"distinct folded keys {cleaned_key_count}"
    )
    for name, _, _ in PAIRS:
        log.append(
            f"  merging keys {name}: pre-registered (raw tokens) {len(merging[name])} "
            f"(recorded 2026-09-07: {RECORDED_MERGING_KEYS[name]}); conservative variant "
            f"{len(conservative[name])}; CLEANED {len(cleaned[name])}"
        )
    log.append(
        "  (the recorded counts are not reproduced: 35,808 keys then; the 2026-09-07 "
        "counting code and write-up were never tracked, so the method here is a "
        "reconstruction and the cause of the difference is unknown. Raw tokens keep "
        "editorial text that search_fold deletes (n{ꜣ} -> n), which inflates the raw "
        "and conservative counts; the recorded numbers were probably inflated the same "
        "way. The cleaned count is the meaningful one.)"
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
        movers_cleaned: list[str] = []
        movers_cleaned_strict: list[str] = []
        char_ids: list[str] = []
        faithful_inputs: list[str] = []
        for row in frame.itertuples(index=False):
            source = row.expected_transliteration
            if set_name == "NAME-v1":
                source = apply_respelling(source, row.notes)
            stored = row.query_input
            recipe = recipe_query(source, row.query_type)
            recipe_ok = search_fold(recipe) == stored
            if recipe_ok:
                aligned, residue, char_aligned = recipe, [], []
            else:
                aligned, residue, char_aligned = aligned_query(stored, source)
            aligned_ok = search_fold(aligned) == stored
            faithful_inputs.append(aligned)
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
            cleaned_hits, cleaned_strict_hits = mover_tokens(aligned, cleaned, cleaned_pieces)
            if not recipe_ok:
                recipe_bad.append(row.benchmark_id)
            if not aligned_ok:
                aligned_bad.append(row.benchmark_id)
            if not same_key:
                key_differs.append(row.benchmark_id)
            if residue:
                residue_ids.append(f"{row.benchmark_id}({' '.join(residue)})")
            if char_aligned:
                char_ids.append(f"{row.benchmark_id}({' '.join(char_aligned)})")
            if cleaned_hits:
                movers_cleaned.append(row.benchmark_id)
            if cleaned_strict_hits:
                movers_cleaned_strict.append(row.benchmark_id)
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
                    "faithful_source": "recipe" if recipe_ok else "aligned",
                    "faithful_query": aligned,
                    "foldback_ok": aligned_ok,
                    "stored_notation": stored_parse.notation,
                    "faithful_notation": faithful_parse.notation,
                    "same_retrieval_key": same_key,
                    "a54_rerank_mode": mode,
                    "ascii_residue_tokens": " ".join(residue),
                    "char_aligned_tokens": " ".join(char_aligned),
                    "merging_tokens": " ".join(loose_hits),
                    "merging_tokens_with_pair_letter": " ".join(strict_hits),
                    "can_move": bool(loose_hits),
                    "can_move_strict": bool(strict_hits),
                    "merging_tokens_cleaned": " ".join(cleaned_hits),
                    "can_move_cleaned": bool(cleaned_hits),
                    "can_move_cleaned_strict": bool(cleaned_strict_hits),
                }
            )
        n = len(frame)
        log.append(f"== {set_name} ({n} queries, {path})")
        log.append(f"  recipe fold-back differs: {len(recipe_bad)}  {' '.join(recipe_bad)}")
        log.append(
            f"  faithful query (recipe where it folds back, else aligned) fold-back "
            f"differs: {len(aligned_bad)}  {' '.join(aligned_bad)}"
        )
        log.append(
            f"  retrieval key (parse_query with the corpus vocabulary) differs from the "
            f"stored query's: {len(key_differs)}  {' '.join(key_differs)}"
        )
        log.append(f"  faithful queries read as: {dict(sorted(notations.items()))}")
        log.append(f"  A54 re-rank mode of the faithful queries: {dict(sorted(modes.items()))}")
        log.append(
            f"  queries with tokens repaired by character alignment: {len(char_ids)}  "
            f"{' '.join(char_ids)}"
        )
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
        log.append(
            f"  can move (CLEANED merging keys): {len(movers_cleaned)}; token carries a "
            f"letter of the pair: {len(movers_cleaned_strict)}  {' '.join(movers_cleaned_strict)}"
        )
        if args.faithful_benchmarks_dir:
            out_dir = Path(args.faithful_benchmarks_dir).expanduser()
            out_dir.mkdir(parents=True, exist_ok=True)
            faithful_frame = frame.copy()
            faithful_frame.insert(
                faithful_frame.columns.get_loc("query_input") + 1,
                "stored_query_input",
                faithful_frame["query_input"],
            )
            faithful_frame["query_input"] = faithful_inputs
            faithful_frame.to_csv(out_dir / f"faithful_{Path(path).name}", index=False)
        summary.append(
            f"  {set_name}: recipe fold-back fails {len(recipe_bad)}/{n}, faithful fold-back "
            f"fails {len(aligned_bad)}/{n}, residue queries {len(residue_ids)}, char-aligned "
            f"queries {len(char_ids)}, movers {len(movers_pre)}/{n} (strict "
            f"{len(movers_strict)}/{n}; cleaned {len(movers_cleaned)}/{n}, cleaned strict "
            f"{len(movers_cleaned_strict)}/{n}), retrieval key differs {len(key_differs)}/{n}"
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

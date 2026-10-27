"""Experiment 3, step 1 — build held-out 2 and held-out 3. No ranker code.

Frozen rule (ROADMAP.md, "Experiment 3", step 1 and the 2026-10-26 addendum, which
reuse Experiment 2's step 1): 20 queries each, the fixed twin guard
(`--exhaustive-twins`, exact Fraction probes), disjoint by row and by source_text_id
from each other and from every existing benchmark set, BBAW +-20 sentence window,
build log with rows removed per rule. Each set carries the builder's folded query
(`query_input`) and a faithful one (`faithful_query_input`) made by
scripts/exp3_step0_faithful_queries.py's derivation (the recipe where it folds back,
otherwise the aligned repair); the fold-back check is run on every row.

Both sets come from scripts/build_competitive_ambiguity_benchmark.py (the builder that
made v4, held-out 1, LE-v1 and NAME-v1), which is deterministic: it ranks candidates by
their number of genuine rivals and has no random seed. Held-out 2 is built first;
held-out 3 is the same build with held-out 2 added to the exclusions.

Held-out 3 is SEALED until Experiment 3's step 4: this script writes it and records
its sha256, and the log reports counts only, never its queries.

    python scripts/exp3_build_heldouts.py
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import search_fold  # noqa: E402
from scripts.exp3_step0_faithful_queries import aligned_query, recipe_query  # noqa: E402

BUILDER = "scripts/build_competitive_ambiguity_benchmark.py"
EXAMPLES_PATH = "data/processed/examples.csv"
B = "data/benchmarks"
# Every committed query set that names corpus rows (expected_source_text_id /
# expected_source_sentence_id). v1-v3 and the drift-corrected v4 are included although
# they are history: "disjoint from existing benchmark sets" is cheaper than arguing
# which ones still count.
EXISTING = (
    f"{B}/competitive_ambiguity_eval_queries.csv",
    f"{B}/competitive_ambiguity_eval_queries_v2.csv",
    f"{B}/competitive_ambiguity_eval_queries_v3.csv",
    f"{B}/competitive_ambiguity_eval_queries_v4.csv",
    f"{B}/competitive_ambiguity_eval_queries_v4_driftcorrected.csv",
    f"{B}/competitive_ambiguity_eval_queries_holdout_2026-09-05.csv",
    f"{B}/competitive_ambiguity_eval_queries_le_v1.csv",
    f"{B}/competitive_ambiguity_eval_queries_name_v1.csv",
    f"{B}/ambiguous_reading_eval_queries.csv",
)
HELD_OUT_2 = f"{B}/competitive_ambiguity_eval_queries_holdout2_2026-10-27.csv"
HELD_OUT_3 = f"{B}/competitive_ambiguity_eval_queries_holdout3_2026-10-27_SEALED.csv"
BBAW_WINDOW = 20
LIMIT = 20
AES_TEXT_RE = re.compile(r"#text=([^&]+)")
RAMSES_LINE_RE = re.compile(r"^ramses-trl \S+ (\S+) line (\d+)$")


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _build(raw_out: Path, prefix: str, excludes: list[str], examples: str) -> list[str]:
    command = [
        sys.executable, BUILDER, "--examples", examples, "--output", str(raw_out),
        "--limit", str(LIMIT), "--exhaustive-twins", "--exclude-same-text",
        "--bbaw-window", str(BBAW_WINDOW), "--id-prefix", prefix,
    ]
    for path in excludes:
        command += ["--exclude-benchmark", path]
    result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)
    shown = " ".join(command[1:]).replace(str(raw_out), "<raw output>")
    return [f"$ python {shown}"] + result.stdout.rstrip("\n").split("\n")


def _add_faithful(raw: Path) -> tuple[pd.DataFrame, list[str], list[str], list[str]]:
    """The builder's frame with `faithful_query_input` / `faithful_source` inserted
    after `query_input`; returns (frame, fold-back failures, residue ids, char-aligned ids)."""
    frame = pd.read_csv(raw, dtype=str, keep_default_na=False)
    faithful, origin, bad, residue_ids, char_ids = [], [], [], [], []
    for row in frame.itertuples(index=False):
        recipe = recipe_query(row.expected_transliteration, row.query_type)
        if search_fold(recipe) == row.query_input:
            query, source, residue, char_aligned = recipe, "recipe", [], []
        else:
            query, residue, char_aligned = aligned_query(row.query_input, row.expected_transliteration)
            source = "aligned"
        if search_fold(query) != row.query_input:
            bad.append(row.benchmark_id)
        if residue:
            residue_ids.append(row.benchmark_id)
        if char_aligned:
            char_ids.append(row.benchmark_id)
        faithful.append(query)
        origin.append(source)
    at = frame.columns.get_loc("query_input") + 1
    frame.insert(at, "faithful_query_input", faithful)
    frame.insert(at + 1, "faithful_source", origin)
    return frame, bad, residue_ids, char_ids


def _keys(frame: pd.DataFrame) -> set[tuple[str, str]]:
    return set(zip(frame["expected_source_text_id"].astype(str), frame["expected_source_sentence_id"].astype(str)))


def _disjointness(corpus: pd.DataFrame, sets: dict[str, pd.DataFrame]) -> list[str]:
    """Post-hoc check of the frozen rules between every pair (new set, other set), plus
    two diagnostics the frozen rule does not ask for (AES text in source_ref, Ramses
    line +-20 in the same split), reported as counts."""
    index = corpus.set_index(["source_text_id", "source_sentence_id"])
    info: dict[str, list[dict]] = {}
    for name, frame in sets.items():
        rows = []
        for key in _keys(frame):
            record = {"key": key, "text": key[0], "bbaw": None, "aes": None, "ramses": None}
            if key in index.index:
                hit = index.loc[key]
                hit = hit.iloc[0] if isinstance(hit, pd.DataFrame) else hit
                ref = str(hit["source_ref"])
                if str(hit["source"]) == "BBAW":
                    record["bbaw"] = int(key[1][1:])
                if (m := AES_TEXT_RE.search(ref)):
                    record["aes"] = m.group(1)
                if (m := RAMSES_LINE_RE.match(ref)):
                    record["ramses"] = (m.group(1), int(m.group(2)))
            rows.append(record)
        info[name] = rows
    out = []
    for new in ("held-out 2", "held-out 3"):
        for other in info:
            if other == new or (new == "held-out 2" and other == "held-out 3"):
                continue
            a, b = info[new], info[other]
            same_row = len({r["key"] for r in a} & {r["key"] for r in b})
            same_text = sum(
                1 for r in a if r["bbaw"] is None and r["text"] in {s["text"] for s in b if s["bbaw"] is None}
            )
            window = sum(
                1 for r in a if r["bbaw"] is not None
                and any(s["bbaw"] is not None and abs(r["bbaw"] - s["bbaw"]) <= BBAW_WINDOW for s in b)
            )
            aes = sum(1 for r in a if r["aes"] and r["aes"] in {s["aes"] for s in b if s["aes"]})
            ramses = sum(
                1 for r in a if r["ramses"] and any(
                    s["ramses"] and s["ramses"][0] == r["ramses"][0]
                    and abs(s["ramses"][1] - r["ramses"][1]) <= BBAW_WINDOW for s in b
                )
            )
            out.append(
                f"  {new} vs {other}: same row {same_row}, same source_text_id {same_text}, "
                f"BBAW within +-{BBAW_WINDOW} {window} | diagnostics (not frozen rules): "
                f"same AES text (source_ref) {aes}, Ramses line within +-{BBAW_WINDOW} same split {ramses}"
            )
    return out


def _describe(frame: pd.DataFrame, corpus: pd.DataFrame) -> list[str]:
    merged = frame.merge(
        corpus[["source_text_id", "source_sentence_id", "source"]],
        left_on=["expected_source_text_id", "expected_source_sentence_id"],
        right_on=["source_text_id", "source_sentence_id"], how="left",
    )
    types = dict(sorted(frame["query_type"].value_counts().items()))
    sources = dict(sorted(merged["source"].fillna("?").value_counts().items()))
    stages = dict(sorted(frame["language_stage"].replace("", "(blank)").value_counts().items()))
    return [f"  rows {len(frame)}; query types {types}; sources {sources}; stages {stages}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--scratch", required=True, help="Directory for the builder's raw outputs.")
    parser.add_argument("--log", default=f"{B}/exp3_heldout_build_log.txt")
    args = parser.parse_args()
    scratch = Path(args.scratch).expanduser()
    scratch.mkdir(parents=True, exist_ok=True)

    log = [
        "Experiment 3, step 1 — held-out 2 and held-out 3 (build log, no ranker code)",
        f"Corpus {args.examples}: sha256 {_sha256(PROJECT_ROOT / args.examples)}",
        "Selection is deterministic (builder ranks by rival count; no random seed exists).",
        f"Twin guard: --exhaustive-twins (exact Fraction probes), overlap >= 0.9; "
        f"BBAW window +-{BBAW_WINDOW}; limit {LIMIT}.",
        "Excluded sets: " + ", ".join(Path(p).name for p in EXISTING),
        "",
        "== held-out 2 (selection set)",
    ]
    raw2 = scratch / "holdout2_raw.csv"
    log += _build(raw2, "HOLD2", list(EXISTING), args.examples)
    h2, bad2, res2, char2 = _add_faithful(raw2)
    h2.to_csv(PROJECT_ROOT / HELD_OUT_2, index=False)

    log += ["", "== held-out 3 (SEALED until step 4; counts only)"]
    raw3 = scratch / "holdout3_raw.csv"
    log += _build(raw3, "HOLD3", list(EXISTING) + [HELD_OUT_2], args.examples)
    h3, bad3, res3, char3 = _add_faithful(raw3)
    h3.to_csv(PROJECT_ROOT / HELD_OUT_3, index=False)

    corpus = pd.read_csv(PROJECT_ROOT / args.examples, dtype=str, keep_default_na=False)
    log += ["", "== faithful column (step 0 derivation: recipe where it folds back, else aligned)"]
    log.append(
        f"  held-out 2: fold-back fails {len(bad2)}/{len(h2)} {' '.join(bad2)}; "
        f"recipe {int((h2.faithful_source == 'recipe').sum())}, aligned "
        f"{int((h2.faithful_source == 'aligned').sum())}; ASCII residue {len(res2)} "
        f"{' '.join(res2)}; char-aligned {len(char2)} {' '.join(char2)}"
    )
    log.append(
        f"  held-out 3: fold-back fails {len(bad3)}/{len(h3)}; recipe "
        f"{int((h3.faithful_source == 'recipe').sum())}, aligned "
        f"{int((h3.faithful_source == 'aligned').sum())}; ASCII residue {len(res3)}; "
        f"char-aligned {len(char3)}"
    )
    log += ["", "== composition"]
    log += ["  held-out 2:"] + _describe(h2, corpus)
    log += ["  held-out 3:"] + _describe(h3, corpus)

    sets = {"held-out 2": h2, "held-out 3": h3}
    for path in EXISTING:
        sets[Path(path).name] = pd.read_csv(PROJECT_ROOT / path, dtype=str, keep_default_na=False)
    log += ["", "== disjointness, checked after the build"] + _disjointness(corpus, sets)

    log += [
        "",
        "== files",
        f"  {HELD_OUT_2} sha256 {_sha256(PROJECT_ROOT / HELD_OUT_2)}",
        f"  {HELD_OUT_3} sha256 {_sha256(PROJECT_ROOT / HELD_OUT_3)}",
    ]
    text = "\n".join(log) + "\n"
    (PROJECT_ROOT / args.log).write_text(text, encoding="utf-8")
    print(text, end="")
    return 1 if (bad2 or bad3) else 0


if __name__ == "__main__":
    raise SystemExit(main())

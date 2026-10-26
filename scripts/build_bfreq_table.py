"""Build and freeze the B-freq glyph → reading table (plan 2026-10-26 §4e, endpoint G).

One light pass over the pinned public corpus. It writes two tables and one header:

    bfreq_table_all.csv             the primary table: no stage filter, no context
    bfreq_table_late_egyptian.csv   §4e's secondary, descriptive restriction
    bfreq_header.json / .txt        corpus sha256, code commit, row counts,
                                    tie-break rule, and each table's sha256

**Where the output goes.** Not into `data/processed/`. That directory is the corpus
itself — tracked, licence-bearing, and hashed by the release gates — and a derived
lookup table of tens of thousands of rows has no business changing its sha256 or its
licence story. The default is `~/egyptology-baselines/kri-bfreq-2026-10-26/`, outside
the checkout and outside iCloud. The table is pinned the way every other frozen
artefact in this project is pinned: by sha256 recorded in a committed document
(`docs/kri-bfreq-baseline-2026-10-26.md`), beside the corpus sha256 and the code
commit it was built from. Those three fix the file exactly, and `--out-dir` lets
anyone rebuild it and compare hashes.

Usage:

    ~/venvs/egyptology/bin/python scripts/build_bfreq_table.py \\
        --examples data/processed/examples.csv \\
        --out-dir ~/egyptology-baselines/kri-bfreq-2026-10-26

Never `--private-dir`, never a KRI path: `assert_public_path` refuses both, and the
baseline's whole evidentiary value is that it was frozen before any KRI line was
opened.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bfreq_baseline import (
    DEFAULT_TOP_K,
    LATE_EGYPTIAN,
    SUCCESS_THRESHOLD,
    TABLE_COLUMNS,
    TIE_BREAK_RULE,
    BFreqTable,
    assert_public_path,
    build_table,
    load_corpus,
    table_rows,
)

DEFAULT_EXAMPLES = PROJECT_ROOT / "data" / "processed" / "examples.csv"
DEFAULT_OUT_DIR = Path.home() / "egyptology-baselines" / "kri-bfreq-2026-10-26"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - not in tests
        return "unknown"


def git_dirty() -> bool:
    try:
        out = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(out.stdout.strip())
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        return True


def write_table(table: BFreqTable, path: Path, *, top_k: int) -> str:
    """Write one table deterministically and return its sha256.

    `newline=""` and `\\n` line endings so the bytes do not depend on the platform:
    the sha256 in the committed document has to mean the same thing everywhere.
    """
    rows = table_rows(table, top_k=top_k)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TABLE_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return sha256_file(path)


def table_summary(table: BFreqTable, *, top_k: int) -> dict:
    return {
        "stage_filter": table.stage_filter,
        "corpus_rows_read": table.rows_read,
        "rows_used": table.rows_used,
        "rows_text_only": table.rows_text_only,
        "rows_misaligned": table.rows_misaligned,
        "word_pairs": table.pairs,
        "word_pairs_dropped": table.pairs_dropped,
        "sign_groups": table.groups,
        "table_rows": len(table_rows(table, top_k=top_k)),
        "groups_with_one_reading": sum(
            1 for entries in table.entries.values() if len(entries) == 1
        ),
        "groups_with_more_than_top_k": sum(
            1 for entries in table.entries.values() if len(entries) > top_k
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--examples", default=str(DEFAULT_EXAMPLES))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    args = parser.parse_args(argv)

    examples = assert_public_path(args.examples, what="corpus")
    out_dir = assert_public_path(args.out_dir, what="output directory")
    if out_dir == PROCESSED_DIR or PROCESSED_DIR in out_dir.parents:
        parser.error(
            "refusing to write the derived table into data/processed: that directory "
            "is the corpus, not a cache (see this script's docstring)"
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.time()
    corpus_sha = sha256_file(examples)
    frame = load_corpus(examples)
    print(f"corpus {examples} rows {len(frame)} sha256 {corpus_sha}", flush=True)

    primary = build_table(frame)
    late = build_table(frame, stage=LATE_EGYPTIAN)

    primary_path = out_dir / "bfreq_table_all.csv"
    late_path = out_dir / "bfreq_table_late_egyptian.csv"
    primary_sha = write_table(primary, primary_path, top_k=args.top_k)
    late_sha = write_table(late, late_path, top_k=args.top_k)

    header = {
        "artefact": "B-freq glyph -> reading baseline table",
        "plan": "docs/plan-data-cleanup-2026-10-26.md §4e, endpoint G",
        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "code_commit": git_commit(),
        "code_tree_dirty": git_dirty(),
        "python": sys.version.split()[0],
        "corpus_path": str(examples),
        "corpus_sha256": corpus_sha,
        "corpus_rows": len(frame),
        "top_k": args.top_k,
        "success_threshold": SUCCESS_THRESHOLD,
        "tie_break_rule": TIE_BREAK_RULE,
        "reading_identity": "app.services.suggestions.strict_reading_key (primary); "
        "app.data.normalizer.search_fold reported secondary",
        "sign_group_key": "app.data.normalizer.normalize_hieroglyphs then "
        "scripts.import_ud_egyptian_pc.glyph_key (plan §4a `signs`)",
        "unseen_group": "empty reading list, scored as a miss; no fallback to the app",
        "module_sha256": {
            "scripts/bfreq_baseline.py": sha256_file(PROJECT_ROOT / "scripts" / "bfreq_baseline.py"),
            "scripts/build_bfreq_table.py": sha256_file(Path(__file__).resolve()),
        },
        "tables": {
            primary_path.name: {"sha256": primary_sha, **table_summary(primary, top_k=args.top_k)},
            late_path.name: {"sha256": late_sha, **table_summary(late, top_k=args.top_k)},
        },
        "elapsed_seconds": round(time.time() - started, 1),
    }
    (out_dir / "bfreq_header.json").write_text(
        json.dumps(header, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = [
        "B-freq glyph -> reading baseline (plan 2026-10-26 §4e, endpoint G)",
        f"built            {header['built_utc']}",
        f"code commit      {header['code_commit']}{' (DIRTY TREE)' if header['code_tree_dirty'] else ''}",
        f"corpus           {examples}",
        f"corpus sha256    {corpus_sha}",
        f"corpus rows      {len(frame)}",
        f"top-k            {args.top_k}",
        f"tie-break        {TIE_BREAK_RULE}",
        "",
    ]
    for name, info in header["tables"].items():
        lines += [
            f"{name}",
            f"  sha256         {info['sha256']}",
            f"  stage filter   {info['stage_filter'] or 'none (whole public corpus)'}",
            f"  rows used      {info['rows_used']} "
            f"(text-only {info['rows_text_only']}, misaligned {info['rows_misaligned']})",
            f"  word pairs     {info['word_pairs']} (dropped {info['word_pairs_dropped']})",
            f"  sign groups    {info['sign_groups']}",
            f"  table rows     {info['table_rows']}",
            "",
        ]
    (out_dir / "bfreq_header.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

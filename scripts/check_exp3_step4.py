"""Experiment 3, step 4: the frozen non-regression rule, applied mechanically.

ROADMAP.md, Experiment 3 addendum 2026-10-26, "Step 4 (held-out 3, opened once)": in BOTH
pools, C (`--exclude-twins 0`) and T (`--exclude-twins 0.7`), on held-out 3 faithful, the F-a
arm passes iff

    top-3 useful >= base   and   MRR >= base   and   rank-1 count >= base.

No strict improvement is required (it is reported, not demanded). The overall verdict is PASS
only if both pools pass. It reads only the four per-query result CSVs the competitive harness
wrote (`--results`), never the benchmark file itself:

    python scripts/check_exp3_step4.py --base-c B_C.csv --fa-c F_C.csv \
        --base-t B_T.csv --fa-t F_T.csv [--out gate_step4.txt]

Metrics are recomputed from `useful_family_rank` (blank = no useful candidate in the top
three): top-3 useful = rank 1 to 3; MRR = mean of 1/rank with a miss counted as 0, as an exact
fraction (no float comparison); rank-1 count = rank 1. When the harness's own
`top3_useful_family_hit` / `top1_useful_family_hit` columns exist they must agree.

Exit code: 0 = PASS, 1 = FAIL, 2 = the inputs cannot be judged (missing column, the two arms
rank different queries, a duplicate id, an empty file). An unjudgeable input is never a PASS.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


class InputError(ValueError):
    """The result files cannot be judged by the rule."""


@dataclass(frozen=True)
class Metrics:
    queries: int
    top3: int
    rank1: int
    mrr: Fraction


def _parse_rank(text: str, where: str) -> int | None:
    text = text.strip()
    if text == "":
        return None
    try:
        rank = int(text)
    except ValueError:
        try:
            as_float = float(text)
        except ValueError:
            raise InputError(f"{where}: useful_family_rank {text!r} is not a number") from None
        if as_float != int(as_float):
            raise InputError(f"{where}: useful_family_rank {text!r} is not an integer") from None
        rank = int(as_float)
    if rank < 1:
        raise InputError(f"{where}: useful_family_rank {rank} is below 1")
    return rank


def _truth(text: str) -> bool:
    return text.strip().lower() == "true"


def read_ranks(path: str | Path) -> dict[str, int | None]:
    """benchmark_id -> rank of the first useful candidate (None = none in the top three)."""
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        for needed in ("benchmark_id", "useful_family_rank"):
            if needed not in fields:
                raise InputError(f"{path}: no {needed} column")
        ranks: dict[str, int | None] = {}
        for line, row in enumerate(reader, start=2):
            where = f"{path} line {line}"
            bid = row["benchmark_id"].strip()
            if not bid:
                raise InputError(f"{where}: empty benchmark_id")
            if bid in ranks:
                raise InputError(f"{where}: duplicate benchmark_id {bid}")
            rank = _parse_rank(row["useful_family_rank"], where)
            if "top3_useful_family_hit" in row and _truth(row["top3_useful_family_hit"]) != (
                rank is not None and rank <= 3
            ):
                raise InputError(f"{where}: top3_useful_family_hit disagrees with the rank ({bid})")
            if "top1_useful_family_hit" in row and _truth(row["top1_useful_family_hit"]) != (rank == 1):
                raise InputError(f"{where}: top1_useful_family_hit disagrees with the rank ({bid})")
            ranks[bid] = rank
    if not ranks:
        raise InputError(f"{path}: no result rows")
    return ranks


def metrics(ranks: dict[str, int | None]) -> Metrics:
    top3 = sum(1 for r in ranks.values() if r is not None and r <= 3)
    rank1 = sum(1 for r in ranks.values() if r == 1)
    mrr = sum((Fraction(1, r) for r in ranks.values() if r is not None and r <= 3), Fraction(0))
    return Metrics(len(ranks), top3, rank1, mrr / len(ranks))


@dataclass(frozen=True)
class PoolVerdict:
    pool: str
    base: Metrics
    fa: Metrics
    top3_ok: bool
    mrr_ok: bool
    rank1_ok: bool

    @property
    def passed(self) -> bool:
        return self.top3_ok and self.mrr_ok and self.rank1_ok

    @property
    def strictly_better(self) -> bool:
        return (
            self.fa.top3 > self.base.top3 or self.fa.mrr > self.base.mrr or self.fa.rank1 > self.base.rank1
        )


def judge_pool(pool: str, base_path: str | Path, fa_path: str | Path) -> PoolVerdict:
    base_ranks = read_ranks(base_path)
    fa_ranks = read_ranks(fa_path)
    if set(base_ranks) != set(fa_ranks):
        only_base = sorted(set(base_ranks) - set(fa_ranks))
        only_fa = sorted(set(fa_ranks) - set(base_ranks))
        raise InputError(f"pool {pool}: the arms rank different queries (only base {only_base}, only fa {only_fa})")
    base, fa = metrics(base_ranks), metrics(fa_ranks)
    return PoolVerdict(pool, base, fa, fa.top3 >= base.top3, fa.mrr >= base.mrr, fa.rank1 >= base.rank1)


def _yn(ok: bool) -> str:
    return "ok" if ok else "FAILS"


def render(verdicts: list[PoolVerdict]) -> str:
    lines = [
        "Experiment 3, step 4: held-out 3 faithful, F-a against base (frozen rule, both pools)",
        "pass iff in BOTH pools: top-3 useful >= base and MRR >= base and rank-1 count >= base",
    ]
    for v in verdicts:
        lines.append(
            f"pool {v.pool} ({v.base.queries} queries): "
            f"top-3 useful base {v.base.top3} fa {v.fa.top3} [{_yn(v.top3_ok)}]; "
            f"MRR base {float(v.base.mrr):.4f} fa {float(v.fa.mrr):.4f} [{_yn(v.mrr_ok)}] "
            f"({v.base.mrr} vs {v.fa.mrr}); "
            f"rank-1 base {v.base.rank1} fa {v.fa.rank1} [{_yn(v.rank1_ok)}]"
        )
        lines.append(f"STEP4 POOL {v.pool}: {'PASS' if v.passed else 'FAIL'}")
        lines.append(f"  (strictly better somewhere, informational only: {'yes' if v.strictly_better else 'no'})")
    overall = all(v.passed for v in verdicts)
    lines.append(f"STEP4 OVERALL: {'PASS' if overall else 'FAIL'}")
    return "\n".join(lines) + "\n"


def run(base_c, fa_c, base_t, fa_t) -> tuple[str, bool]:
    verdicts = [judge_pool("C", base_c, fa_c), judge_pool("T", base_t, fa_t)]
    return render(verdicts), all(v.passed for v in verdicts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-c", required=True)
    parser.add_argument("--fa-c", required=True)
    parser.add_argument("--base-t", required=True)
    parser.add_argument("--fa-t", required=True)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    try:
        text, passed = run(args.base_c, args.fa_c, args.base_t, args.fa_t)
    except (InputError, OSError) as error:
        text, passed = f"STEP4 OVERALL: UNJUDGEABLE ({error})\n", None
    sys.stdout.write(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 2 if passed is None else (0 if passed else 1)


if __name__ == "__main__":
    raise SystemExit(main())

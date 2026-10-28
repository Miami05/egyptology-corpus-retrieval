"""The Experiment 3 step-4 checker, on synthetic result CSVs only (no benchmark, no corpus)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_exp3_step4 import InputError, main, metrics, read_ranks, run


def write(path: Path, ranks: list, hits: bool = True) -> str:
    """A result CSV with one row per rank ('' = no useful candidate in the top three)."""
    header = "benchmark_id,useful_family_rank" + (",top1_useful_family_hit,top3_useful_family_hit" if hits else "")
    rows = [header]
    for i, r in enumerate(ranks, start=1):
        row = f"H3_{i:03d},{r}"
        if hits:
            row += f",{r == 1},{r in (1, 2, 3)}"
        rows.append(row)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return str(path)


def four(tmp_path, base_c, fa_c, base_t, fa_t, hits=True):
    return (
        write(tmp_path / "bc.csv", base_c, hits),
        write(tmp_path / "fc.csv", fa_c, hits),
        write(tmp_path / "bt.csv", base_t, hits),
        write(tmp_path / "ft.csv", fa_t, hits),
    )


def test_metrics_are_exact(tmp_path):
    m = metrics(read_ranks(write(tmp_path / "x.csv", [1, 2, 3, ""])))
    assert (m.queries, m.top3, m.rank1) == (4, 3, 1)
    assert str(m.mrr) == "11/24"  # (1 + 1/2 + 1/3 + 0) / 4


def test_identical_arms_pass_without_strict_improvement(tmp_path):
    ranks = [1, 1, 2, 3, ""]
    text, passed = run(*four(tmp_path, ranks, ranks, ranks, ranks))
    assert passed is True
    assert "STEP4 POOL C: PASS" in text and "STEP4 POOL T: PASS" in text
    assert "STEP4 OVERALL: PASS" in text
    assert "informational only: no" in text


def test_strict_improvement_in_both_pools_passes(tmp_path):
    text, passed = run(*four(tmp_path, [2, 1, ""], [1, 1, 3], [2, 1, ""], [1, 1, 3]))
    assert passed is True and "informational only: yes" in text


def test_pool_c_fail_fails_overall_even_if_t_passes(tmp_path):
    # C: fa loses a top-3 hit; T: identical.
    text, passed = run(*four(tmp_path, [1, 2, 3], [1, 2, ""], [1, 2, 3], [1, 2, 3]))
    assert passed is False
    assert "STEP4 POOL C: FAIL" in text and "STEP4 POOL T: PASS" in text
    assert "STEP4 OVERALL: FAIL" in text


def test_pool_t_fail_fails_overall(tmp_path):
    text, passed = run(*four(tmp_path, [1, 2], [1, 2], [1, 2], [2, 2]))
    assert passed is False
    assert "STEP4 POOL C: PASS" in text and "STEP4 POOL T: FAIL" in text


def test_rank1_lost_fails_even_when_top3_and_mrr_hold(tmp_path):
    base = [1, 3, 3, 3, 3, 3]  # rank-1 1, MRR (1 + 5/3)/6 = 0.4444
    fa = [2, 2, 2, 2, 2, 2]  # rank-1 0, MRR 0.5, top-3 6 >= 6
    text, passed = run(*four(tmp_path, base, fa, base, base))
    assert passed is False
    assert "rank-1 base 1 fa 0 [FAILS]" in text
    assert "MRR base 0.4444 fa 0.5000 [ok]" in text


def test_mrr_lost_fails_even_when_counts_hold(tmp_path):
    base = [1, 2]
    fa = [2, 1]  # same top-3, same rank-1 count, same MRR -> passes
    assert run(*four(tmp_path, base, fa, base, base))[1] is True
    fa = [1, 3]  # same top-3 and rank-1, MRR lower
    text, passed = run(*four(tmp_path, base, fa, base, base))
    assert passed is False and "[FAILS]" in text


def test_mrr_compared_exactly_not_as_float(tmp_path):
    # 1/3 + 1/3 + 1/3 against 1/3 + 1/3 + 1/3 in another order is equal, not "close".
    base = [3, 3, 3, 1, 2, 3]
    fa = [1, 2, 3, 3, 3, 3]
    assert run(*four(tmp_path, base, fa, base, fa))[1] is True


def test_different_query_sets_are_unjudgeable(tmp_path):
    a = write(tmp_path / "a.csv", [1, 2])
    b = write(tmp_path / "b.csv", [1, 2, 3])
    with pytest.raises(InputError, match="different queries"):
        run(a, b, a, a)


def test_duplicate_id_and_empty_file_are_unjudgeable(tmp_path):
    dup = tmp_path / "d.csv"
    dup.write_text("benchmark_id,useful_family_rank\nA,1\nA,2\n", encoding="utf-8")
    with pytest.raises(InputError, match="duplicate"):
        read_ranks(dup)
    empty = tmp_path / "e.csv"
    empty.write_text("benchmark_id,useful_family_rank\n", encoding="utf-8")
    with pytest.raises(InputError, match="no result rows"):
        read_ranks(empty)


def test_missing_column_and_bad_rank_are_unjudgeable(tmp_path):
    nocol = tmp_path / "n.csv"
    nocol.write_text("benchmark_id,something\nA,1\n", encoding="utf-8")
    with pytest.raises(InputError, match="no useful_family_rank"):
        read_ranks(nocol)
    bad = tmp_path / "b.csv"
    bad.write_text("benchmark_id,useful_family_rank\nA,zero\n", encoding="utf-8")
    with pytest.raises(InputError, match="not a number"):
        read_ranks(bad)
    zero = tmp_path / "z.csv"
    zero.write_text("benchmark_id,useful_family_rank\nA,0\n", encoding="utf-8")
    with pytest.raises(InputError, match="below 1"):
        read_ranks(zero)


def test_hit_columns_must_agree_with_the_rank(tmp_path):
    bad = tmp_path / "h.csv"
    bad.write_text(
        "benchmark_id,useful_family_rank,top1_useful_family_hit,top3_useful_family_hit\nA,2,True,True\n",
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="top1_useful_family_hit disagrees"):
        read_ranks(bad)


def test_float_formatted_ranks_are_read(tmp_path):
    p = tmp_path / "f.csv"
    p.write_text("benchmark_id,useful_family_rank\nA,1.0\nB,\n", encoding="utf-8")
    assert read_ranks(p) == {"A": 1, "B": None}


def test_main_exit_codes_and_gate_file(tmp_path, capsys):
    ranks = [1, 2, ""]
    paths = four(tmp_path, ranks, ranks, ranks, ranks)
    out = tmp_path / "gate.txt"
    code = main(["--base-c", paths[0], "--fa-c", paths[1], "--base-t", paths[2], "--fa-t", paths[3], "--out", str(out)])
    assert code == 0
    assert "STEP4 OVERALL: PASS" in out.read_text(encoding="utf-8")
    assert "STEP4 OVERALL: PASS" in capsys.readouterr().out

    worse = write(tmp_path / "w.csv", [1, "", ""])
    assert main(["--base-c", paths[0], "--fa-c", worse, "--base-t", paths[2], "--fa-t", paths[3]]) == 1

    missing = str(tmp_path / "nope.csv")
    assert main(["--base-c", paths[0], "--fa-c", missing, "--base-t", paths[2], "--fa-t", paths[3], "--out", str(out)]) == 2
    assert "UNJUDGEABLE" in out.read_text(encoding="utf-8")

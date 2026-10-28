"""Route 1: the sealed cross-edition benchmark builder, on synthetic fixtures only.

No test reads the real corpus, the real pair file or any real query.
"""

from __future__ import annotations

import hashlib

import pandas as pd
import pytest

from scripts import build_route1_xed_benchmark as xed
from scripts.build_route1_xed_benchmark import (
    OUTPUT_COLUMNS,
    assign_directions,
    build_xed_queries,
    collect_target_keys,
    frame_to_bytes,
    hidden_item,
    load_removed_keys,
    render_log,
)

# Word families: tokens of family k never occur in another family, so every Jaccard below
# is exactly what the construction says.


def toks(family: str, letters: str) -> str:
    return " ".join(f"{family}{ch}" for ch in letters)


def corpus_row(source: str, text_id: str, sentence_id: str, reading: str, **extra) -> dict:
    row = {
        "source": source,
        "source_text_id": text_id,
        "source_sentence_id": sentence_id,
        "transliteration_gold": reading,
        "lemma_sequence": "",
        "language_stage": "Late Egyptian",
    }
    row.update(extra)
    return row


def pair_row(pair_id: str, source_pair: str, a: dict, b: dict, jaccard: float = 0.5) -> dict:
    return {
        "pair_id": pair_id,
        "source_pair": source_pair,
        "jaccard": f"{jaccard:.6f}",
        "a_source": a["source"],
        "a_text_id": a["source_text_id"],
        "a_sentence_id": a["source_sentence_id"],
        "a_transliteration": a["transliteration_gold"],
        "b_source": b["source"],
        "b_text_id": b["source_text_id"],
        "b_sentence_id": b["source_sentence_id"],
        "b_transliteration": b["transliteration_gold"],
    }


def simple_pair(k: int, source_pair: str = "Alpha<->Beta", shared: int = 5):
    """A pair of rows from two sources that share `shared` of 8 distinct tokens (J = shared/(12-shared))."""
    family = f"wf{chr(97 + k)}"
    a = corpus_row("Alpha", f"ALPHA_{k}", f"A{k}", toks(family, "abcdefg"[:shared] + "hij"[: 6 - shared]))
    b = corpus_row("Beta", f"BETA_{k}", f"B{k}", toks(family, "abcdefg"[:shared] + "mno"[: 6 - shared]))
    return a, b, pair_row(f"XED_{k:03d}", source_pair, a, b)


def build(rows: list[dict], pairs: list[dict], removed=frozenset(), targets=frozenset(), seed=7):
    queries, report = build_xed_queries(
        pd.DataFrame(pairs), pd.DataFrame(rows), set(removed), set(targets), seed=seed
    )
    return queries, report


# ------------------------------------------------------------------- directions


def test_directions_are_half_and_half_per_source_pair_and_deterministic():
    groups = {"P1": [f"XED_{i:03d}" for i in range(1, 11)], "P2": [f"XED_{i:03d}" for i in range(11, 18)]}
    first = assign_directions(groups, seed=1)
    assert first == assign_directions(groups, seed=1)
    assert sum(first[i] == "A2B" for i in groups["P1"]) == 5
    assert sum(first[i] == "A2B" for i in groups["P2"]) == 3  # odd group: the extra goes to B2A
    assert set(first.values()) == {"A2B", "B2A"}
    assert assign_directions(groups, seed=2) != first


def test_group_order_in_the_input_does_not_change_directions():
    ids = [f"XED_{i:03d}" for i in range(1, 9)]
    assert assign_directions({"P": ids}, 5) == assign_directions({"P": list(reversed(ids))}, 5)


def test_excluding_a_pair_does_not_move_another_pairs_direction():
    rows, pairs = [], []
    for k in range(6):
        a, b, p = simple_pair(k)
        rows += [a, b]
        pairs.append(p)
    full, _ = build(rows, pairs)
    # Remove pair 2 through the cleanup rule; every other pair keeps its direction.
    cut, _ = build(rows, pairs, removed={("ALPHA_2", "A2")})
    assert "XED_002" not in set(cut["pair_id"])
    before = dict(zip(full["pair_id"], full["direction"]))
    after = dict(zip(cut["pair_id"], cut["direction"]))
    assert all(before[pair_id] == direction for pair_id, direction in after.items())


# ------------------------------------------------------- query, answer, leave-one-out


def test_query_is_one_side_verbatim_and_the_other_side_is_the_answer():
    a, b, pair = simple_pair(0)
    queries, report = build([a, b], [pair])
    assert report["queries_out"] == 1
    row = queries.iloc[0]
    assert row["benchmark_id"] == "XED1_000"
    assert row["query_type"] == "cross_edition_transliteration"
    assert row["expected_in_pool"] == "1"
    if row["direction"] == "A2B":
        query, answer = a, b
    else:
        query, answer = b, a
    assert row["query_input"] == query["transliteration_gold"]
    assert row["expected_transliteration"] == answer["transliteration_gold"]
    assert row["expected_source_text_id"] == answer["source_text_id"]
    assert row["expected_source_sentence_id"] == answer["source_sentence_id"]
    assert row["query_source"] == query["source"]
    assert row["expected_source"] == answer["source"]
    assert list(queries.columns) == OUTPUT_COLUMNS
    assert row["acceptable_token_overlap_threshold"] == "0.26"
    assert row["language_stage"] == "Late Egyptian"


def test_hidden_keys_hold_the_query_row_and_its_twins_but_never_the_answer():
    # Pair 0 at J = 5/7 = 0.714 >= 0.7: the answer is itself a near-twin of the query,
    # and must still be left out of the hidden set.
    a, b, pair = simple_pair(0, shared=5)
    family = "wfa"
    twin_of_a = corpus_row("Gamma", "GAMMA_0", "G0", toks(family, "abcdeh") + " " + family + "k")
    unrelated = corpus_row("Gamma", "GAMMA_1", "G1", toks("wzz", "abcdef"))
    queries, _ = build([a, b, twin_of_a, unrelated], [pair])
    row = queries.iloc[0]
    hidden = set(row["hidden_row_keys"].split())
    query_row = a if row["direction"] == "A2B" else b
    answer_row = b if row["direction"] == "A2B" else a
    assert hidden_item(query_row["source_text_id"], query_row["source_sentence_id"]) in hidden
    assert hidden_item(answer_row["source_text_id"], answer_row["source_sentence_id"]) not in hidden
    assert hidden_item("GAMMA_1", "G1") not in hidden


def test_a_near_twin_of_the_query_is_hidden():
    family = "wfq"
    a = corpus_row("Alpha", "ALPHA_Q", "AQ", toks(family, "abcdefg"))
    b = corpus_row("Beta", "BETA_Q", "BQ", toks(family, "abcdemn"))  # 5/9 = 0.556
    twin_a = corpus_row("Gamma", "GAMMA_Q", "GQ", toks(family, "abcdefgh"))  # 7/8 of a, 5/10 of b
    twin_b = corpus_row("Delta", "DELTA_Q", "DQ", toks(family, "abcdemnp"))  # twin of b only
    pair = pair_row("XED_001", "Alpha<->Beta", a, b)
    queries, _ = build([a, b, twin_a, twin_b], [pair])
    row = queries.iloc[0]
    hidden = set(row["hidden_row_keys"].split())
    if row["direction"] == "A2B":
        assert hidden_item("GAMMA_Q", "GQ") in hidden
        assert hidden_item("DELTA_Q", "DQ") not in hidden
    else:
        assert hidden_item("DELTA_Q", "DQ") in hidden
        assert hidden_item("GAMMA_Q", "GQ") not in hidden


# ------------------------------------------------------------------ exclusion rules


def one_pair_corpus(**overrides):
    """A single clean pair (pair 1, 'wfb' words) plus the means to break it."""
    a, b, pair = simple_pair(1)
    return [a, b], [pair]


def test_clean_pair_is_kept_by_default():
    rows, pairs = one_pair_corpus()
    queries, report = build(rows, pairs)
    assert len(queries) == 1
    assert sum(report["excluded_by_reason"].values()) == 0


def test_row_missing_from_corpus():
    rows, pairs = one_pair_corpus()
    _, report = build(rows[:1], pairs)
    assert report["excluded_by_reason"]["row_missing_from_corpus"] == 1


def test_row_key_not_unique():
    rows, pairs = one_pair_corpus()
    duplicate = dict(rows[0], transliteration_gold="zz1 zz2 zz3 zz4 zz5 zz6")
    _, report = build(rows + [duplicate], pairs)
    assert report["excluded_by_reason"]["row_key_not_unique"] == 1


def test_transliteration_changed_since_the_pair_file_was_frozen():
    rows, pairs = one_pair_corpus()
    rows[1] = dict(rows[1], transliteration_gold=rows[1]["transliteration_gold"] + " wfbz")
    _, report = build(rows, pairs)
    assert report["excluded_by_reason"]["transliteration_changed_since_freeze"] == 1


@pytest.mark.parametrize("which", [0, 1])
def test_pair_with_a_row_removed_by_cleanup_is_excluded(which):
    rows, pairs = one_pair_corpus()
    key = (rows[which]["source_text_id"], rows[which]["source_sentence_id"])
    queries, report = build(rows, pairs, removed={key})
    assert len(queries) == 0
    assert report["excluded_by_reason"]["removed_by_cleanup_part_1"] == 1


@pytest.mark.parametrize("which", [0, 1])
def test_pair_with_a_benchmark_target_row_is_excluded(which):
    rows, pairs = one_pair_corpus()
    key = (rows[which]["source_text_id"], rows[which]["source_sentence_id"])
    _, report = build(rows, pairs, targets={key})
    assert report["excluded_by_reason"]["benchmark_target_row"] == 1


def test_pair_row_that_is_a_near_copy_of_a_benchmark_target_is_excluded():
    a = corpus_row("Alpha", "ALPHA_N", "AN", toks("wfe", "abcdefghij"))
    b = corpus_row("Beta", "BETA_N", "BN", toks("wfe", "abcdefgklm"))
    target = corpus_row("Gamma", "GAMMA_T", "GT", toks("wfe", "abcdefghi"))  # 9 of 10 = 0.9 with a
    pairs = [pair_row("XED_001", "Alpha<->Beta", a, b)]
    queries, report = build([a, b, target], pairs, targets={("GAMMA_T", "GT")})
    assert len(queries) == 0
    assert report["excluded_by_reason"]["near_twin_of_benchmark_target"] == 1


def test_a_pair_row_just_below_the_near_copy_line_is_kept():
    a = corpus_row("Alpha", "ALPHA_N", "AN", toks("wfe", "abcdefghij"))
    b = corpus_row("Beta", "BETA_N", "BN", toks("wfe", "abcdefgklm"))
    target = corpus_row("Gamma", "GAMMA_T", "GT", toks("wfe", "abcdefgh"))  # 8 of 10 = 0.8 with a
    pairs = [pair_row("XED_001", "Alpha<->Beta", a, b)]
    queries, _ = build([a, b, target], pairs, targets={("GAMMA_T", "GT")})
    assert len(queries) == 1


def test_pair_row_sharing_a_non_bbaw_text_id_with_a_target_is_excluded():
    rows, pairs = one_pair_corpus()
    sibling = corpus_row("Alpha", rows[0]["source_text_id"], "A_other", toks("wzy", "abcdef"))
    _, report = build(rows + [sibling], pairs, targets={(rows[0]["source_text_id"], "A_other")})
    assert report["excluded_by_reason"]["same_text_as_benchmark_target"] == 1


def bbaw_pair(number: int):
    a = corpus_row("BBAW", "bbaw_egyptian_2018", f"B{number:06d}", toks("wfc", "abcdefg"))
    b = corpus_row("Ramses", "RAMSES_1", "R1", toks("wfc", "abcdemn"))
    return a, b, pair_row("XED_001", "BBAW<->Ramses", a, b)


@pytest.mark.parametrize("distance,excluded", [(20, 1), (21, 0)])
def test_bbaw_window_is_plus_minus_twenty_sentence_numbers(distance, excluded):
    a, b, pair = bbaw_pair(500)
    target = corpus_row("BBAW", "bbaw_egyptian_2018", f"B{500 + distance:06d}", toks("wzz", "abcdef"))
    _, report = build([a, b, target], [pair], targets={("bbaw_egyptian_2018", f"B{500 + distance:06d}")})
    assert report["excluded_by_reason"]["bbaw_window_of_benchmark_target"] == excluded


def test_query_side_with_too_few_tokens_is_excluded():
    # One pair in its source pair: half = 0, so the direction is B2A and the query is b.
    short_b = corpus_row("Beta", "BETA_S", "BS", "wfd1 wfd2 wfd3")
    long_a = corpus_row("Alpha", "ALPHA_S", "AS", toks("wfd", "abcdef"))
    pairs = [pair_row("XED_001", "Alpha<->Beta", long_a, short_b)]
    queries, report = build([long_a, short_b], pairs)
    assert len(queries) == 0 and report["excluded_by_reason"]["query_side_too_short"] == 1
    # The same short row on the answer side is no reason to drop the pair.
    short_a = dict(short_b, source="Alpha")
    long_b = dict(long_a, source="Beta")
    pairs = [pair_row("XED_001", "Alpha<->Beta", short_a, long_b)]
    queries, _ = build([short_a, long_b], pairs)
    assert len(queries) == 1


def test_each_pair_is_dropped_under_exactly_one_reason():
    rows, pairs = one_pair_corpus()
    key = (rows[0]["source_text_id"], rows[0]["source_sentence_id"])
    # Removed AND a target: counted once, under the earlier rule.
    queries, report = build(rows, pairs, removed={key}, targets={key})
    assert len(queries) == 0
    assert sum(report["excluded_by_reason"].values()) == 1
    assert report["excluded_by_reason"]["removed_by_cleanup_part_1"] == 1


# ------------------------------------------------------------------- file helpers


def test_load_removed_keys_reads_only_decision_removed(tmp_path):
    path = tmp_path / "removal_manifest.csv"
    path.write_text(
        "key,source,decision,old_reading\n"
        "BBAW|bbaw_egyptian_2018|B000001,BBAW,removed,x\n"
        "BBAW|bbaw_egyptian_2018|B000002,BBAW,kept: exception stratum,y\n"
        "Ramses|RAMSES_9|R9,Ramses,removed,z\n",
        encoding="utf-8",
    )
    assert load_removed_keys(path) == {("bbaw_egyptian_2018", "B000001"), ("RAMSES_9", "R9")}


def test_load_removed_keys_rejects_a_malformed_key(tmp_path):
    path = tmp_path / "m.csv"
    path.write_text("key,decision\nonly|two,removed\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_removed_keys(path)


def test_collect_target_keys_uses_any_file_with_the_two_columns_and_skips_its_own(tmp_path):
    (tmp_path / "set_a.csv").write_text(
        "benchmark_id,expected_source_text_id,expected_source_sentence_id\nX1,T1,S1\nX2,T2,S2\n",
        encoding="utf-8",
    )
    (tmp_path / "results_a.csv").write_text(
        "expected_source_text_id,expected_source_sentence_id,suggestions\nT2,S2,foo\nT3,S3,bar\n",
        encoding="utf-8",
    )
    (tmp_path / "other.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "queries_xed_route1_SEALED.csv").write_text(
        "expected_source_text_id,expected_source_sentence_id\nTX,SX\n", encoding="utf-8"
    )
    keys, per_file = collect_target_keys(tmp_path)
    assert keys == {("T1", "S1"), ("T2", "S2"), ("T3", "S3")}
    assert per_file == {"results_a.csv": 2, "set_a.csv": 2}


def test_hidden_item_refuses_ids_it_cannot_encode():
    assert hidden_item("T", "S1") == "T|S1"
    for bad in [("T X", "S"), ("T", "S|1"), ("", "S")]:
        with pytest.raises(ValueError):
            hidden_item(*bad)


# -------------------------------------------------------- determinism and the log


def many_pairs():
    rows, pairs = [], []
    for k in range(8):
        a, b, p = simple_pair(k, source_pair="Alpha<->Beta" if k < 5 else "Alpha<->Delta")
        rows += [a, b]
        pairs.append(p)
    return rows, pairs


def test_build_is_deterministic_and_does_not_depend_on_pair_file_order():
    rows, pairs = many_pairs()
    first, _ = build(rows, pairs)
    again, _ = build(rows, pairs)
    reordered, _ = build(rows, list(reversed(pairs)))
    assert frame_to_bytes(first) == frame_to_bytes(again) == frame_to_bytes(reordered)


def test_report_counts_per_source_pair_and_the_log_has_no_query_text():
    rows, pairs = many_pairs()
    queries, report = build(rows, pairs)
    assert report["pairs_per_source_pair"] == {"Alpha<->Beta": 5, "Alpha<->Delta": 3}
    assert report["queries_per_source_pair"] == report["pairs_per_source_pair"]
    assert sum(report["queries_per_direction"].values()) == 8
    out_sha = hashlib.sha256(frame_to_bytes(queries)).hexdigest()
    context = {
        "seed": "7", "script": "s", "pairs_sha": "p" * 64, "corpus_sha": "c" * 64,
        "manifest_name": "m", "manifest_sha": "m" * 64, "removed_total": "0",
        "target_files": "0", "per_file": {},
    }
    log = render_log(report, context, out_sha)
    assert out_sha in log
    for text in list(queries["query_input"]) + list(queries["expected_transliteration"]):
        assert text not in log


def test_main_refuses_to_overwrite_the_sealed_file_and_enforces_the_minimum(tmp_path, monkeypatch):
    rows, pairs = many_pairs()
    corpus = pd.DataFrame(rows)
    # Columns load_examples_csv requires are many; bypass the loader with a stub.
    monkeypatch.setattr(xed, "load_examples_csv", lambda path: corpus)
    pairs_path = tmp_path / "pairs.csv"
    pd.DataFrame(pairs).to_csv(pairs_path, index=False)
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("key,decision\n", encoding="utf-8")
    corpus_path = tmp_path / "examples.csv"
    corpus_path.write_text("stub", encoding="utf-8")
    out = tmp_path / "out" / "set_SEALED.csv"
    log = tmp_path / "out" / "log.txt"
    base = [
        "--pairs", str(pairs_path), "--examples", str(corpus_path),
        "--removal-manifest", str(manifest), "--out", str(out), "--log", str(log),
    ]
    with pytest.raises(SystemExit):  # 8 queries < the default minimum of 100: nothing written
        xed.main(base)
    assert not out.exists()
    assert xed.main(base + ["--minimum", "5"]) == 0
    first = out.read_bytes()
    assert xed.main(base + ["--minimum", "5"]) == 2  # sealed: never rebuilt over
    assert out.read_bytes() == first
    assert xed.main(base + ["--minimum", "5", "--verify"]) == 0
    assert hashlib.sha256(first).hexdigest() in log.read_text(encoding="utf-8")

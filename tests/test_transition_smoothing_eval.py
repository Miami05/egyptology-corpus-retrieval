"""Unit tests for the transition-smoothing harness (scripts/run_transition_smoothing_eval.py).

A measurement harness that is wrong is worse than none: its output looks like evidence. The
fixtures are synthetic frames built through the real constructors. What is pinned: the dev
draw is a deterministic function of the corpus, the rate and the seed; the dev hygiene leaves
no dev row with a twin in the fit data; the mechanism population is defined by gold data;
every arm decodes under the `off` routing; the `off` arm IS the shipped decoder.
"""

from __future__ import annotations

import hashlib

import pandas as pd
import pytest

import app.services.reading_model as reading_model_module
from scripts import run_transition_smoothing_eval as harness
from scripts.run_transition_smoothing_eval import (
    ARMS,
    Arm,
    HarnessFault,
    band_of,
    build_resources,
    context_of,
    counts_ok,
    draw_units,
    evaluate,
    gold_population,
    split_dev,
    summarise,
    write_manifest,
)

SIGN_A = "𓂋"
SIGN_B = "𓆑"
SIGN_E = "𓄿"
SIGN_H = "𓆓"
SIGN_Z = "𓃀"


def frame(specs):
    """(source, text id, sentence id, signs, readings, stage, source_ref) -> a corpus frame."""
    return pd.DataFrame(
        [
            {
                "source": source,
                "source_text_id": text_id,
                "source_sentence_id": sentence_id,
                "hieroglyphs_norm": signs,
                "transliteration_gold": readings,
                "language_stage": stage,
                "source_ref": ref,
                "mdc_norm": readings,
            }
            for source, text_id, sentence_id, signs, readings, stage, ref in specs
        ]
    )


def synthetic_train(n_tla=40, n_bbaw=40, n_aes_texts=10, per_text=3) -> pd.DataFrame:
    specs = []
    for i in range(n_tla):
        specs.append(("TLA", f"TLA_{i}", "S", f"{SIGN_A}{i} {SIGN_B}{i}", "a b", "Earlier Egyptian", ""))
    for i in range(n_bbaw):
        specs.append(("BBAW", "bbaw", f"B{i}", f"{SIGN_H}{i} {SIGN_E}{i}", "h e", "Earlier Egyptian", ""))
    for t in range(n_aes_texts):
        for s in range(per_text):
            specs.append(
                ("AES", f"AES_{t}_{s}", f"S{s}", f"{SIGN_Z}{t}{s} {SIGN_A}", "z a", "Earlier Egyptian", f"x#text=T{t}&sentence={s}")
            )
    return frame(specs)


# ---------- the dev draw ----------


def test_the_draw_is_deterministic_and_independent_of_row_order():
    train = synthetic_train()
    first = draw_units(train, 0.10)
    assert first == draw_units(train, 0.10)
    shuffled = train.sample(frac=1.0, random_state=3)
    assert draw_units(shuffled, 0.10) == first
    assert draw_units(train, 0.20) != first


def test_the_draw_takes_a_tenth_of_each_sources_units_and_whole_texts():
    train = synthetic_train()
    chosen = draw_units(train, 0.10)
    tla = {k for k in chosen if k.startswith("TLA:")}
    bbaw = {k for k in chosen if k.startswith("BBAW:")}
    aes = {k for k in chosen if k.startswith("AES:")}
    assert (len(tla), len(bbaw), len(aes)) == (4, 4, 1)  # 40, 40 and 10 units at 10%
    # an AES draw is a text: every sentence of it is drawn
    split = split_dev(train, 0.10, lexicon_on=False)
    assert split.drawn == 4 + 4 + 3
    # a source with one unit still contributes one
    assert len(draw_units(frame([("TLA", "t", "s", SIGN_A, "a", "", "")]), 0.10)) == 1


def test_dev_hygiene_leaves_no_row_with_a_twin_in_the_fit_data():
    train = synthetic_train()
    split = split_dev(train, 0.20, lexicon_on=True)
    assert set(split.dev["source"]) <= {"TLA", "BBAW"}  # AES (lexicon-leaking) is out
    assert split.dropped_leaky > 0
    fit_signs = set(split.fit["hieroglyphs_norm"])
    assert not (set(split.dev["hieroglyphs_norm"]) & fit_signs)
    # dev and fit are disjoint; only the exact/near-duplicate drops leave the experiment,
    # the drawn leaking rows stay in fit (R4)
    assert not (set(split.dev.index) & set(split.fit.index))
    assert len(split.dev) + len(split.fit) + split.dropped_exact + split.dropped_near == len(train)


def test_drawn_lexicon_leaking_rows_stay_in_the_training_partition():
    train = synthetic_train()
    split = split_dev(train, 0.20, lexicon_on=True)
    drawn_keys = draw_units(train, 0.20)
    leaking = train[train["source"].isin({"AES", "Ramses"})]
    assert split.dropped_leaky > 0
    # every leaking row of the train partition is in fit, drawn or not
    assert set(leaking.index) <= set(split.fit.index)
    assert not (set(leaking.index) & set(split.dev.index))
    assert len(split.fit) == len(train) - len(split.dev) - split.dropped_exact - split.dropped_near
    assert drawn_keys  # the draw itself is unchanged by the hygiene


def test_a_dev_row_that_duplicates_a_fit_row_is_dropped():
    train = frame(
        [("TLA", f"T{i}", "S", f"{SIGN_A}{i}", "a", "", "") for i in range(30)]
        + [("TLA", f"U{i}", "S", f"{SIGN_B}", "b", "", "") for i in range(30)]  # all the same string
    )
    split = split_dev(train, 0.20, lexicon_on=False)
    # whichever "same string" rows are drawn have an identical row left in the fit data
    assert split.dropped_exact >= 1
    assert SIGN_B not in set(split.dev["hieroglyphs_norm"])


def test_lexicon_off_keeps_the_leaking_sources():
    train = synthetic_train()
    with_lexicon = split_dev(train, 0.20, lexicon_on=True)
    without = split_dev(train, 0.20, lexicon_on=False)
    assert "AES" in set(without.dev["source"]) and with_lexicon.dropped_leaky > 0
    assert without.dropped_leaky == 0


def test_the_manifest_sha_is_the_sha_of_the_written_file(tmp_path):
    train = synthetic_train()
    dev = split_dev(train, 0.10, lexicon_on=True).dev
    sha = write_manifest(dev, tmp_path / "m" / "dev.csv")
    assert sha == hashlib.sha256((tmp_path / "m" / "dev.csv").read_bytes()).hexdigest()
    again = write_manifest(dev, tmp_path / "again.csv")
    assert again == sha
    header = (tmp_path / "again.csv").read_text().splitlines()[0]
    assert header == "source,source_text_id,source_sentence_id,hieroglyphs_norm"


def test_the_minimum_counts_are_the_registered_ones():
    assert (harness.MIN_DEV_POSITIONS, harness.MIN_DEV_MEMBERS) == (2000, 100)
    assert counts_ok({"dev_positions": 2000, "dev_members": 100})
    assert not counts_ok({"dev_positions": 1999, "dev_members": 100})
    assert not counts_ok({"dev_positions": 2000, "dev_members": 99})
    assert harness.DEV_RATES == (0.10, 0.20) and harness.SEED == 20261026


# ---------- the mechanism population (R5 d', R8) ----------


def _model_with_contexts():
    from app.services.reading_model import train_reading_model

    train = frame(
        [("T", "a", "s", f"{SIGN_A} {SIGN_B}", "p q", "", "")]  # p -> q once: N = 1, V = 1
        + [("T", f"b{i}", "s", f"{SIGN_A} {SIGN_B}", "r s", "", "") for i in range(5)]  # r -> s x5
        + [("T", "c", "s", f"{SIGN_A} {SIGN_B}", "t u", "", ""), ("T", "d", "s", f"{SIGN_A} {SIGN_B}", "t v", "", "")]
        + [("T", f"e{i}", "s", f"{SIGN_A} {SIGN_B}", "w x", "", "") for i in range(2)]
        + [("T", "f", "s", f"{SIGN_A} {SIGN_B}", "w y", "", "")]
    )
    return train_reading_model(train)


def test_context_of_and_bands():
    model = _model_with_contexts()
    assert context_of(model, "p") == (1, 1)
    assert context_of(model, "r") == (5, 1)
    assert context_of(model, "t") == (2, 2)
    assert context_of(model, "never") == (0, 0)
    assert [band_of(n) for n in (0, 1, 2, 3, 4, 40)] == ["", "1", "2-3", "2-3", "4+", "4+"]


def test_membership_is_defined_by_the_gold_previous_reading_only():
    model = _model_with_contexts()
    info = gold_population(model, ["p", "q", "r", "s", "t", "w", "", "x"])
    members = [i["member1"] for i in info]
    # position 0: never; previous 'p' (V=1): member; 'q' (never a context): not; 'r' V=1: member;
    # 's': not; 't' V=2, N=2: secondary; 'w' V=2, N=3: secondary; '' previous: outside; 'x'
    # follows ''. (Position 5's previous is 't'; position 6's previous is 'w'.)
    assert members == [0, 1, 0, 1, 0, 0, 0, 0]
    assert [i["band"] for i in info] == ["", "1", "", "4+", "", "", "", ""]
    assert [i["member2"] for i in info] == [0, 0, 0, 0, 0, 1, 1, 0]
    assert info[1]["prev_n"] == 1 and info[3]["prev_n"] == 5
    assert info[0]["member1"] == 0 and info[0]["prev_gold"] == ""


# ---------- decoding ----------


def _resources():
    train = frame(
        [("TLA", f"T{i}", "S", f"{SIGN_E} {SIGN_H}", "e hy", "Earlier Egyptian", "") for i in range(3)]
        + [("TLA", f"U{i}", "S", f"{SIGN_E} {SIGN_H}", "e wsht", "Earlier Egyptian", "") for i in range(2)]
        + [("TLA", "V", "S", f"{SIGN_E} {SIGN_H}", "ea haw", "Earlier Egyptian", "")]
        + [("TLA", f"L{i}", "S", f"{SIGN_B} {SIGN_A}", "b a", "Late Egyptian", "") for i in range(4)]
    )
    return build_resources(train, lexicon_on=False)


def test_the_arms_are_the_registered_four_and_off_is_the_baseline():
    assert [arm.name for arm in ARMS] == ["off", "c2_transition_only", "c2", "c3"]
    assert all(arm.name == arm.scheme for arm in ARMS)
    assert harness.BASELINE_ARM == "off"
    assert harness.SIMPLICITY_ORDER == ("c2_transition_only", "c2", "c3")


def test_every_arm_decodes_under_the_same_routed_stage_and_off_is_the_shipped_decoder():
    resources = _resources()
    test = frame([("TLA", "X", "S", f"{SIGN_E} {SIGN_H}", "e hy", "", "")])
    positions, lines = evaluate(test, resources, ARMS)
    assert len(lines) == len(ARMS) == 4
    assert {row["stage"] for row in lines} == {"Earlier Egyptian"}
    assert {row["arm"] for row in positions} == {a.name for a in ARMS}
    model = resources.model_for("Earlier Egyptian")
    shipped = [p.predicted for p in model.predict_sequence([SIGN_E, SIGN_H])]
    off = [r["predicted"] for r in positions if r["arm"] == "off"]
    assert off == shipped
    for scheme in ("c2", "c3", "c2_transition_only"):
        mine = [r["predicted"] for r in positions if r["arm"] == scheme]
        assert mine == [p.predicted for p in model.predict_sequence([SIGN_E, SIGN_H], smoothing=scheme)]


def test_positions_carry_the_population_and_the_transition_scores():
    resources = _resources()
    test = frame([("TLA", "X", "S", f"{SIGN_E} {SIGN_H}", "e hy", "", "")])
    positions, lines = evaluate(test, resources, ARMS)
    by = {(r["arm"], r["position"]): r for r in positions}
    # gold previous reading 'e' is followed by two readings in training -> V_obs = 2: no member
    assert by[("off", 1)]["member1"] == 0 and by[("off", 1)]["prev_vobs"] == 2
    assert by[("off", 1)]["prev_n"] == 5 and by[("off", 1)]["member2"] == 0  # N = 5 > 3
    assert by[("off", 0)]["prev_gold"] == ""
    # the transition columns are the model's own scores under off and under the arm
    model = resources.model_for("Earlier Egyptian")
    chosen = by[("c2", 1)]["predicted"]
    previous = by[("c2", 0)]["predicted"]
    assert by[("c2", 1)]["t_chosen_off"] == model._transition(previous, chosen, "off")
    assert by[("c2", 1)]["t_chosen_arm"] == model._transition(previous, chosen, "wb")
    assert by[("c2_transition_only", 1)]["t_chosen_arm"] == model._transition(previous, by[("c2_transition_only", 1)]["predicted"], "wb")
    assert by[("off", 1)]["t_chosen_arm"] == by[("off", 1)]["t_chosen_off"]
    assert by[("off", 1)]["group_key"].startswith("TLA:sentence:")
    # the hypothetical routing is recorded and is the off routing for the baseline arm
    off_line = next(r for r in lines if r["arm"] == "off")
    assert off_line["hyp_stage"] == off_line["stage"]
    assert off_line["off_scores"] == off_line["hyp_scores"]


def test_misaligned_rows_are_skipped_not_scored():
    resources = _resources()
    test = frame([("TLA", "X", "S", f"{SIGN_E} {SIGN_H}", "e", "", "")])  # 2 signs, 1 reading
    positions, lines = evaluate(test, resources, ARMS)
    assert positions == [] and lines == []


def test_a_prediction_count_mismatch_is_a_harness_fault(monkeypatch):
    resources = _resources()
    model = resources.model_for("Earlier Egyptian")
    monkeypatch.setattr(type(model), "predict_sequence", lambda self, groups, **kw: [])
    test = frame([("TLA", "X", "S", f"{SIGN_E} {SIGN_H}", "e hy", "", "")])
    with pytest.raises(HarnessFault):
        evaluate(test, resources, (Arm("off", "off"),))


def test_summarise_counts_what_it_says_it_counts():
    resources = _resources()
    test = frame(
        [
            ("TLA", "X", "S", f"{SIGN_E} {SIGN_H}", "e hy", "", ""),
            ("TLA", "Y", "S", f"{SIGN_B} {SIGN_A}", "b a", "", ""),
        ]
    )
    positions, lines = evaluate(test, resources, ARMS)
    summary, calibration = summarise(pd.DataFrame(positions), pd.DataFrame(lines))
    rows = {(r["arm"], r["scope"]): r for r in summary}
    assert rows[("off", "all")]["positions"] == 4
    assert rows[("off", "all")]["better_than_off"] == 0 == rows[("off", "all")]["worse_than_off"]
    for arm in ("c2", "c3"):
        r = rows[(arm, "all")]
        assert r["better_than_off"] + r["worse_than_off"] + r["unchanged_vs_off"] == 4
        assert r["stage_changed_vs_off"] == 0
        assert r["boundary_errors"] == rows[("off", "all")]["boundary_errors"]
    assert {c["arm"] for c in calibration} == {a.name for a in ARMS}


def test_the_harness_refuses_to_run_when_the_default_scheme_is_not_off(monkeypatch, tmp_path):
    monkeypatch.setattr(reading_model_module, "TRANSITION_SMOOTHING_BY_DEFAULT", "c2")
    assert harness.main(["--phase", "manifests", "--out-dir", str(tmp_path)]) == 2


def test_the_harness_refuses_to_overwrite_existing_evidence(tmp_path, capsys):
    (tmp_path / "dev_counts.json").write_text("{}")
    assert harness.main(["--phase", "dev", "--out-dir", str(tmp_path)]) == 2
    assert "evidence is never overwritten" in capsys.readouterr().err
    assert (tmp_path / "dev_counts.json").read_text() == "{}"
    assert "dev_counts.json" in harness.phase_outputs("dev")
    assert "test_manifest_used.csv" in harness.phase_outputs("test")

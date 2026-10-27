"""Paired on/off measurement of the three KRI-self-test changes (2026-10-26).

Why a new harness. The changes of `docs/kri-selftest-fixes-2026-10-26.md` live in the
*decoder* and the *segmenter*:

  pooled fallback   `ReadingModel.uses_pooled_evidence` — a stage-restricted model
                    reads a group whose stage evidence the filter emptied from the
                    pooled counts instead
  singleton /k      `ReadingPrediction.confidence` divides the chosen reading's share
                    by the number of readings tied with it on one attestation each
  cartouche         `Segmenter.segment` forbids a boundary inside a cartouche

Nothing already in the repository can see them:

* the competitive benchmarks (v4, held-out, LE-v1) are *retrieval and suggestion*
  evaluations. They never call `ReadingModel.predict_sequence` or `Segmenter.segment`
  at all, so re-running them can only show that nothing else broke;
* `scripts/run_reading_model_eval.py` trains exactly one model on the training split
  and never attaches a pooled model to it, so the pooled fallback can never fire there
  — `uses_pooled_evidence` returns False whenever `ReadingModel.pooled` is None.

So this script builds what the pre-registration needs: the same test split as that
eval, decoded **stage-aware**, with each feature toggled independently and all-on
against all-off, writing one row per position and one row per line.

**Training/test hygiene.** Every model here — the pooled one and each stage-restricted
one — is fitted on the *training* partition only. The stage subsets are taken from the
training frame (`compatible_frame(train, stage)`), never from the whole corpus, so no
test row reaches either side of the pooled/stage comparison. The split itself is
`scripts.run_reading_model_eval.select_test_rows`, unchanged and with its own
defaults, so this harness measures on the split that already existed rather than on a
new one.

**Two tracks, because the three features do not act in the same place.**

  reading track       decode the row's own (gold) sign grouping. The pooled fallback
                      and the confidence discount act here. The cartouche constraint
                      cannot act on the grouping — there is no segmentation step — but
                      it can still reach this track through the stage router, which
                      segments, and that coupling is the point of measuring it.
  segmentation track  re-segment the row's signs with the spaces removed, the protocol
                      `scripts/run_segmentation_eval.py` uses, and score boundaries
                      against the gold grouping. The cartouche constraint acts here.

**What is reported** (see `--summary`): accuracy at the positions the pooled fallback
fires on, paired on/off; what happens at the positions *beside* a firing one and at
positions that never fire, because Viterbi couples them; whole-line outcomes; boundary
F1 and how often a cartouche is split; how often the chosen stage moves and the
attested coverage that moved it; and calibration of the chosen reading's confidence
(reliability bins and a Brier score) for three confidence numbers — the pre-branch one,
the corrected undiscounted one, and the /k-discounted one — over all positions and over
positions with a reading.

**Cohorts are per position, not per arm.** A position's class (firing / neighbour /
other) is decided once per row from the pooled arms and carried unchanged into every arm,
`all_off` included, so every paired comparison is over the same positions. Every rate
is written beside the integer counts it comes from; an empty cohort's rate is blank.

Nothing here decides anything. The decision rules are in
`docs/kri-fixes-preregistration-2026-10-26.md`; this script only produces the numbers
they are applied to.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.services.segmentation as segmentation_module  # noqa: E402
from app.data.loader import load_examples_csv  # noqa: E402
from app.data.normalizer import cartouche_spans  # noqa: E402
from app.services.lexicon import load_lexicon  # noqa: E402
from app.services.reading_model import ReadingModel, train_reading_model  # noqa: E402
from app.services.segmentation import (  # noqa: E402
    DEFAULT_SEGMENTATION_WEIGHTS,
    Segmenter,
    segment_paste,
)
from app.services.stage import (  # noqa: E402
    STAGES,
    StageResources,
    choose_stage_by_likelihood,
    compatible_frame,
    count_own_aligned_rows,
)
from scripts.run_reading_model_eval import (  # noqa: E402
    EXAMPLES_PATH,
    LEXICON_EXCLUDE_TEST_SOURCES,
    aligned_rows,
    parse_source_list,
    select_test_rows,
    test_mix,
)

POSITIONS_PATH = "data/benchmarks/kri_fixes_positions.csv"
LINES_PATH = "data/benchmarks/kri_fixes_lines.csv"
SUMMARY_PATH = "data/benchmarks/kri_fixes_summary.csv"
# Reliability bins for the calibration report. Ten equal-width bins over [0, 1] is the
# usual choice and nothing here depends on it; the bin edges are written out with the
# counts so a reader can re-bin.
CALIBRATION_BINS = 10


# ---------------------------------------------------------------------------
# Arms
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Arm:
    """One configuration of the three features.

    `pooled` and `cartouche` change what the model does; `discount` changes only the
    number `ReadingPrediction.confidence` reports, so it cannot move an accuracy and
    appears only in the calibration section. It is still a separate arm because
    reporting a calibration without saying which confidence it is would be useless.
    """

    name: str
    pooled: bool
    discount: bool
    cartouche: bool


ARMS: tuple[Arm, ...] = (
    Arm("all_off", pooled=False, discount=False, cartouche=False),
    Arm("pooled_only", pooled=True, discount=False, cartouche=False),
    Arm("discount_only", pooled=False, discount=True, cartouche=False),
    Arm("cartouche_only", pooled=False, discount=False, cartouche=True),
    Arm("all_on", pooled=True, discount=True, cartouche=True),
)
BASELINE_ARM = "all_off"


@contextmanager
def cartouche_constraint(enabled: bool):
    """Run the block with the cartouche constraint on or off.

    The constraint is not a weight or a flag — it is a hard restriction in
    `Segmenter.segment`, expressed through the module-level `cartouche_spans`. The
    "off" arm has to be the behaviour that shipped *before* this branch, and the exact
    way to get that is to make `cartouche_spans` report nothing, which is what
    `tests/test_segmentation.py` does to show the constraint is what keeps a royal
    name together. Swapping the module attribute here keeps that seam in the
    measurement code instead of adding a production switch that only a measurement
    would ever set.
    """
    if enabled:
        yield
        return
    original = segmentation_module.cartouche_spans
    segmentation_module.cartouche_spans = lambda stream: []
    try:
        yield
    finally:
        segmentation_module.cartouche_spans = original


# ---------------------------------------------------------------------------
# Resources, built from the training partition only
# ---------------------------------------------------------------------------


@dataclass
class HarnessResources:
    """Pooled and stage-restricted models, plus the one pooled segmenter.

    `build_stage_resources` is not used: it also builds a `SearchIndex` (an n-gram
    index over every row) that nothing in this harness reads, and it would be built
    four times. The reading/segmenting half is reproduced here exactly as that
    function does it — the stage model is fitted on `compatible_frame(frame, stage)`,
    the pooled model is attached to it, and the segmenter is built from the *pooled*
    model for every stage ("segment pooled, read by stage").
    """

    pooled: ReadingModel
    by_stage: dict[str, ReadingModel]
    segmenter: Segmenter
    own_aligned: dict[str, int]
    _resources: dict[str | None, StageResources] = field(default_factory=dict)

    def stage_resources(self, stage: str | None) -> StageResources:
        """A `StageResources` carrying only what `choose_stage_by_likelihood` reads.

        That function uses `.reading_model`, `.segmenter` and `.own_aligned_rows` and
        nothing else, so `frame`, `index` and `sign_index` are left empty rather than
        built: filling them would cost an n-gram index per stage and change no result.
        """
        if stage not in self._resources:
            self._resources[stage] = StageResources(
                stage=stage,
                frame=pd.DataFrame(),
                index=None,  # type: ignore[arg-type]
                reading_model=self.pooled if stage is None else self.by_stage[stage],
                segmenter=self.segmenter,
                sign_index={},
                own_aligned_rows=None if stage is None else self.own_aligned[stage],
            )
        return self._resources[stage]

    def model_for(self, stage: str | None) -> ReadingModel:
        return self.pooled if stage is None else self.by_stage[stage]


def build_resources(train: pd.DataFrame, lexicon_on: bool) -> HarnessResources:
    lexicon = load_lexicon() if lexicon_on else None
    pooled = train_reading_model(train, lexicon)
    by_stage: dict[str, ReadingModel] = {}
    own_aligned: dict[str, int] = {}
    for stage in STAGES:
        model = train_reading_model(compatible_frame(train, stage), lexicon)
        model.attach_pooled(pooled)
        by_stage[stage] = model
        own_aligned[stage] = count_own_aligned_rows(train, stage)
    segmenter = Segmenter(pooled, DEFAULT_SEGMENTATION_WEIGHTS, use_lexicon=lexicon_on)
    return HarnessResources(
        pooled=pooled, by_stage=by_stage, segmenter=segmenter, own_aligned=own_aligned
    )


# ---------------------------------------------------------------------------
# Per-row work, memoised on what actually determines each result
# ---------------------------------------------------------------------------


def boundaries(groups: list[str]) -> set[int]:
    """Glyph positions where a group ends, excluding the end of the stream.

    The same convention as `scripts/run_segmentation_eval.py`, so the F1 reported here
    is comparable with that eval's.
    """
    out: set[int] = set()
    position = 0
    for group in groups[:-1]:
        position += len(group)
        out.add(position)
    return out


@dataclass
class Routing:
    stage: str | None
    coverage: dict[str, int]
    scores: dict[str, float]
    resegmented: list[str]


def route_and_segment(
    resources: HarnessResources, gold_groups: list[str], with_cartouche: bool
) -> Routing:
    """Choose a stage for the row and re-segment its signs without their spaces.

    The paste handed to the router is the row's own grouping, which is what a reader
    pasting this line would have. The *re-segmentation* scored on the segmentation
    track is of the same signs with the spaces removed, the protocol
    `run_segmentation_eval.py` uses, so the boundary score is not inflated by handing
    the segmenter the answer.

    Known limit (review, Opus, 2026-10-26): because the router gets the gold-spaced
    paste, its spaces act as hints and the cartouche constraint rarely gets to change
    the routing segmentation. `stage_changed_vs_baseline` therefore understates the
    routing effect on real pastes that arrive unspaced or spaced by quadrat. The
    pre-registration states this in §7; it is not measured here.
    """
    with cartouche_constraint(with_cartouche):
        coverage: dict[str, int] = {}
        stage, scores = choose_stage_by_likelihood(
            " ".join(gold_groups), resources.stage_resources, coverage=coverage
        )
        unspaced, _as_pasted = segment_paste("".join(gold_groups), resources.segmenter)
    return Routing(
        stage=stage, coverage=coverage, scores=scores, resegmented=unspaced.groups
    )


def confidence_of(prediction, discount: bool) -> float:
    """`ReadingPrediction.confidence`, with the /k singleton discount on or off.

    Off is the undiscounted share — `reading_probability` — which is what the property
    returns for every prediction that is not a singleton tie, so the two arms differ
    only where a tie exists.
    """
    if discount:
        return float(prediction.confidence)
    return float(prediction.reading_probability)


def legacy_confidence(prediction) -> float:
    """The confidence this app shipped *before* this branch (pre-`be24b96`).

    It was the **leading candidate's** score divided by the summed scores of the
    displayed top-five `candidates` — not the chosen reading's share of the full
    distribution, which is what `reading_probability` is since be24b96 #1. Review fix
    (Opus + Astra, 2026-10-26): without this column the `all_off` arm reproduces the
    pre-branch *predictions* but not the pre-branch *confidence*, so a calibration
    comparison against it would have mixed the correction with the /k discount.
    """
    candidates = list(prediction.candidates or [])
    if not candidates:
        return 0.0
    total = sum(score for _, score in candidates)
    if total <= 0:
        return 0.0
    return float(candidates[0][1] / total)


# The three confidence numbers recorded for every position, so the calibration can
# separate the confidence *correction* (legacy -> undiscounted) from the /k *discount*
# (undiscounted -> discounted) instead of comparing two arms that differ in both.
CONFIDENCE_KINDS = ("legacy", "undiscounted", "discounted")
# Position cohorts. A position's cohort is a property of the *position*, fixed once per
# row from the pooled arms, and the same in every arm (see `evaluate`).
COHORTS = ("firing", "neighbour", "other")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def calibration_rows(records: list[tuple[float, bool]], bins: int) -> list[dict]:
    """Reliability bins plus the Brier score, over (confidence, was_correct) pairs."""
    out: list[dict] = []
    if not records:
        return out
    brier = sum((confidence - float(correct)) ** 2 for confidence, correct in records)
    brier /= len(records)
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        in_bin = [
            (confidence, correct)
            for confidence, correct in records
            if (low <= confidence < high) or (index == bins - 1 and confidence == 1.0)
        ]
        if not in_bin:
            out.append(
                {
                    "bin_low": round(low, 3),
                    "bin_high": round(high, 3),
                    "n": 0,
                    "mean_confidence": "",
                    "accuracy": "",
                }
            )
            continue
        out.append(
            {
                "bin_low": round(low, 3),
                "bin_high": round(high, 3),
                "n": len(in_bin),
                "mean_confidence": round(
                    sum(c for c, _ in in_bin) / len(in_bin), 4
                ),
                "accuracy": round(
                    sum(1 for _, correct in in_bin if correct) / len(in_bin), 4
                ),
            }
        )
    for row in out:
        row["brier"] = round(brier, 5)
        row["n_total"] = len(records)
    return out


def ratio(numerator: int, denominator: int) -> "float | None":
    """An unrounded rate, or None (a blank cell) when there is nothing to divide by.

    Review fix (Opus + Astra, 2026-10-26): this used to return 0.0 for 0/0, which made
    an empty cohort read as "0% accurate" and let a comparison against it pass. Gates
    are decided on the integer counts written beside every rate, never on a rate.
    """
    return numerator / denominator if denominator else None


def sign_test_p(better: int, worse: int) -> "float | None":
    """Two-sided exact sign test on the discordant pairs (better vs worse).

    Reported for uncertainty only; no gate reads it except the improvement-claim
    condition of rule (b). None when there are no discordant pairs.
    """
    n = better + worse
    if n == 0:
        return None
    k = min(better, worse)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def evaluate(
    test: pd.DataFrame, resources: HarnessResources, arms: tuple[Arm, ...]
) -> tuple[list[dict], list[dict]]:
    """Decode every test row under every arm. Returns (position rows, line rows).

    Work is memoised on what determines it, not on the arm: routing and
    re-segmentation depend only on the cartouche setting (the router decodes with the
    pooled fallback off by design), the reading decode depends on the routed stage and
    the pooled setting, and the discount is applied afterwards to the same prediction.
    So a five-arm run costs two routings and four decodes per row, not fifteen.

    **Cohorts are fixed per position, not per arm** (review fix, Opus + Astra,
    2026-10-26). A position is `firing` if the pooled fallback fires there in *any*
    pooled arm run (the union, because `pooled_only` and `all_on` route with different
    cartouche settings and so can fire on different positions), `neighbour` if it is
    beside a firing position and does not fire itself, and `other` otherwise — and it
    carries that same class in **every** arm, `all_off` included. The earlier version
    classified each arm by its own predictions, so in `all_off` nothing could fire,
    `acc_firing(all_off)` was 0/0, and rules (a) and (b) compared different
    populations. `used_pooled_evidence` still records whether *this* arm fired there.
    """
    position_rows: list[dict] = []
    line_rows: list[dict] = []

    for row_index, row in enumerate(test.itertuples(index=False)):
        gold_groups = str(row.hieroglyphs_norm).split()
        gold_readings = str(row.transliteration_gold).split()
        if not gold_groups or len(gold_groups) != len(gold_readings):
            continue
        source = str(getattr(row, "source", ""))
        row_id = f"{source}:{row_index}"
        gold_boundaries = boundaries(gold_groups)

        routings: dict[bool, Routing] = {}
        decodes: dict[tuple[bool, bool], list] = {}
        for arm in arms:
            if arm.cartouche not in routings:
                routings[arm.cartouche] = route_and_segment(
                    resources, gold_groups, arm.cartouche
                )
            routing = routings[arm.cartouche]
            key = (arm.cartouche, arm.pooled)
            if key not in decodes:
                model = resources.model_for(routing.stage)
                decodes[key] = model.predict_sequence(
                    gold_groups, use_pooled_fallback=arm.pooled
                )

        cohort_firing: set[int] = set()
        for (_cartouche, pooled), predictions in decodes.items():
            if pooled:
                cohort_firing |= {
                    i for i, p in enumerate(predictions) if p.used_pooled_evidence
                }
        cohort_neighbour = {
            i + d
            for i in cohort_firing
            for d in (-1, 1)
            if 0 <= i + d < len(gold_groups)
        } - cohort_firing

        def cohort_of(index: int) -> str:
            if index in cohort_firing:
                return "firing"
            if index in cohort_neighbour:
                return "neighbour"
            return "other"

        # Always the real function, never the one the "off" arm disables: the point of
        # that arm is to count the cartouches it splits, which it cannot do if it has
        # also forgotten where they are.
        spans = cartouche_spans("".join(gold_groups))
        inside = {b for start, end in spans for b in range(start + 1, end)}

        for arm in arms:
            routing = routings[arm.cartouche]
            predictions = decodes[(arm.cartouche, arm.pooled)]
            fired_here = sum(1 for p in predictions if p.used_pooled_evidence)
            correct_count = 0
            for index, (prediction, truth) in enumerate(zip(predictions, gold_readings)):
                is_correct = prediction.predicted == truth
                correct_count += int(is_correct)
                position_rows.append(
                    {
                        "arm": arm.name,
                        "row_id": row_id,
                        "source": source,
                        "position": index,
                        "group": prediction.sign,
                        "gold_reading": truth,
                        "predicted": prediction.predicted,
                        "correct": int(is_correct),
                        "stage": routing.stage or "",
                        "was_seen": int(prediction.was_seen),
                        "is_borrowed": int(prediction.is_borrowed),
                        "used_pooled_evidence": int(prediction.used_pooled_evidence),
                        "stage_attested_count": prediction.stage_attested_count,
                        "attested_count": prediction.attested_count,
                        "reading_count": prediction.reading_count,
                        "is_singleton_tie": int(prediction.is_singleton_tie),
                        "n_tied": len(prediction.tied_singleton_readings),
                        "reading_probability": round(
                            float(prediction.reading_probability), 6
                        ),
                        "confidence": round(confidence_of(prediction, arm.discount), 6),
                        "confidence_legacy": round(legacy_confidence(prediction), 6),
                        "confidence_undiscounted": round(
                            confidence_of(prediction, False), 6
                        ),
                        "confidence_discounted": round(
                            confidence_of(prediction, True), 6
                        ),
                        "class": cohort_of(index),
                    }
                )
            predicted_boundaries = boundaries(routing.resegmented)
            line_rows.append(
                {
                    "arm": arm.name,
                    "row_id": row_id,
                    "source": source,
                    "stage": routing.stage or "",
                    "coverage": ";".join(
                        f"{s}={n}" for s, n in sorted(routing.coverage.items())
                    ),
                    "n_positions": len(gold_groups),
                    "n_correct": correct_count,
                    "line_exact": int(correct_count == len(gold_groups)),
                    "n_firing": fired_here,
                    "n_cohort_firing": len(cohort_firing),
                    "seg_exact": int(routing.resegmented == gold_groups),
                    "boundary_tp": len(predicted_boundaries & gold_boundaries),
                    "boundary_fp": len(predicted_boundaries - gold_boundaries),
                    "boundary_fn": len(gold_boundaries - predicted_boundaries),
                    "boundary_fp_outside_cartouche": len(
                        (predicted_boundaries - gold_boundaries) - inside
                    ),
                    "boundary_fn_outside_cartouche": len(
                        (gold_boundaries - predicted_boundaries) - inside
                    ),
                    "cartouches": len(spans),
                    # Review nit (Opus + Astra): the old `cartouches_split` counted
                    # predicted boundaries inside cartouches, not cartouches. Both are
                    # now written, under names that say which is which.
                    "cartouches_split": sum(
                        1
                        for start, end in spans
                        if any(start < b < end for b in predicted_boundaries)
                    ),
                    "boundaries_inside_cartouches": len(predicted_boundaries & inside),
                }
            )
    return position_rows, line_rows


def _paired(
    arm_positions: pd.DataFrame, baseline_by_key: dict
) -> tuple[int, int, int]:
    """(better, worse, changed) of these positions against the baseline arm."""
    better = worse = changed = 0
    for key, correct, predicted in zip(
        zip(arm_positions["row_id"], arm_positions["position"]),
        arm_positions["correct"],
        arm_positions["predicted"],
    ):
        base = baseline_by_key.get(key)
        if base is None:
            continue
        base_correct, base_predicted = base
        if predicted != base_predicted:
            changed += 1
        better += int(correct == 1 and base_correct == 0)
        worse += int(correct == 0 and base_correct == 1)
    return better, worse, changed


def _summary_row(
    arm_name: str,
    scope: str,
    arm_positions: pd.DataFrame,
    arm_lines: pd.DataFrame,
    baseline_by_key: dict,
    baseline_lines: pd.DataFrame,
) -> dict:
    record: dict = {"arm": arm_name, "scope": scope, "positions": len(arm_positions)}
    record["correct"] = int(arm_positions["correct"].sum())
    record["acc_all"] = ratio(record["correct"], len(arm_positions))
    better, worse, changed = _paired(arm_positions, baseline_by_key)
    record["better_than_baseline"] = better
    record["worse_than_baseline"] = worse
    record["positions_changed_vs_baseline"] = changed
    for cohort in COHORTS:
        part = arm_positions[arm_positions["class"] == cohort]
        c_better, c_worse, c_changed = _paired(part, baseline_by_key)
        record[f"{cohort}_positions"] = len(part)
        record[f"{cohort}_lines"] = int(part["row_id"].nunique()) if len(part) else 0
        record[f"{cohort}_correct"] = int(part["correct"].sum())
        record[f"acc_{cohort}"] = ratio(int(part["correct"].sum()), len(part))
        record[f"{cohort}_better"] = c_better
        record[f"{cohort}_worse"] = c_worse
        record[f"{cohort}_unchanged_outcome"] = len(part) - c_better - c_worse
        record[f"{cohort}_changed"] = c_changed
        record[f"{cohort}_sign_test_p"] = sign_test_p(c_better, c_worse)

    base_exact = dict(zip(baseline_lines["row_id"], baseline_lines["line_exact"]))
    base_stage = dict(zip(baseline_lines["row_id"], baseline_lines["stage"].astype(str)))
    record["lines"] = len(arm_lines)
    record["lines_exact"] = int(arm_lines["line_exact"].sum())
    record["lines_exact_gained"] = sum(
        1
        for row_id, exact in zip(arm_lines["row_id"], arm_lines["line_exact"])
        if row_id in base_exact and exact == 1 and base_exact[row_id] == 0
    )
    record["lines_exact_lost"] = sum(
        1
        for row_id, exact in zip(arm_lines["row_id"], arm_lines["line_exact"])
        if row_id in base_exact and exact == 0 and base_exact[row_id] == 1
    )
    record["seg_exact"] = int(arm_lines["seg_exact"].sum())
    tp = int(arm_lines["boundary_tp"].sum())
    fp = int(arm_lines["boundary_fp"].sum())
    fn = int(arm_lines["boundary_fn"].sum())
    record["boundary_tp"], record["boundary_fp"], record["boundary_fn"] = tp, fp, fn
    record["boundary_precision"] = ratio(tp, tp + fp)
    record["boundary_recall"] = ratio(tp, tp + fn)
    record["boundary_f1"] = ratio(2 * tp, 2 * tp + fp + fn)
    fp_out = int(arm_lines["boundary_fp_outside_cartouche"].sum())
    fn_out = int(arm_lines["boundary_fn_outside_cartouche"].sum())
    record["boundary_fp_outside_cartouche"] = fp_out
    record["boundary_fn_outside_cartouche"] = fn_out
    record["boundary_errors_outside_cartouche"] = fp_out + fn_out
    record["cartouches"] = int(arm_lines["cartouches"].sum())
    record["cartouches_split"] = int(arm_lines["cartouches_split"].sum())
    record["boundaries_inside_cartouches"] = int(
        arm_lines["boundaries_inside_cartouches"].sum()
    )
    # Compared as strings: a stage the router left unset is "" in both arms and must
    # not read as a move (review fix: NaN != NaN once a CSV round trip is involved).
    record["stage_changed_vs_baseline"] = sum(
        1
        for row_id, stage in zip(arm_lines["row_id"], arm_lines["stage"].astype(str))
        if row_id in base_stage and base_stage[row_id] != stage
    )
    return record


def summarise(positions: pd.DataFrame, lines: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Per-arm aggregates and, against the baseline arm, paired counts.

    One row per arm with `scope == "all"`, then one per arm and test source
    (`scope == "source:<name>"`) — source-stratified because the BBAW rows' lexicon-
    assisted numbers are not held-out (`LEXICON_TAINTED_SOURCES` in
    `run_reading_model_eval.py`). The calibration has one block per arm, per confidence
    kind (`CONFIDENCE_KINDS`) and per subset (`all` positions, and `with_reading`: only
    those where a reading was predicted, since a no-reading position at confidence 0 is
    "perfectly calibrated" and would flatter the Brier score).
    """
    summary: list[dict] = []
    calibration: list[dict] = []
    baseline_positions = positions[positions["arm"] == BASELINE_ARM]
    baseline_lines = lines[lines["arm"] == BASELINE_ARM]
    baseline_by_key = dict(
        zip(
            zip(baseline_positions["row_id"], baseline_positions["position"]),
            zip(baseline_positions["correct"], baseline_positions["predicted"]),
        )
    )
    sources = sorted(set(positions["source"].astype(str))) if "source" in positions else []

    for arm_name, arm_positions in positions.groupby("arm", sort=False):
        arm_lines = lines[lines["arm"] == arm_name]
        summary.append(
            _summary_row(
                arm_name, "all", arm_positions, arm_lines, baseline_by_key, baseline_lines
            )
        )
        for kind in CONFIDENCE_KINDS:
            column = f"confidence_{kind}"
            if column not in arm_positions:
                continue
            for subset, part in (
                ("all", arm_positions),
                ("with_reading", arm_positions[arm_positions["predicted"].astype(str) != ""]),
            ):
                records = [
                    (float(confidence), bool(correct))
                    for confidence, correct in zip(part[column], part["correct"])
                ]
                for calibration_row in calibration_rows(records, CALIBRATION_BINS):
                    calibration_row["arm"] = arm_name
                    calibration_row["confidence_kind"] = kind
                    calibration_row["subset"] = subset
                    calibration.append(calibration_row)

    for source in sources:
        for arm_name, arm_positions in positions.groupby("arm", sort=False):
            arm_positions = arm_positions[arm_positions["source"].astype(str) == source]
            arm_lines = lines[(lines["arm"] == arm_name) & (lines["source"].astype(str) == source)]
            summary.append(
                _summary_row(
                    arm_name,
                    f"source:{source}",
                    arm_positions,
                    arm_lines,
                    baseline_by_key,
                    baseline_lines,
                )
            )
    return summary, calibration


def _fmt(value) -> str:
    return "  n/a " if value is None else f"{value:.4f}"


def _parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--positions", default=POSITIONS_PATH)
    parser.add_argument("--lines", default=LINES_PATH)
    parser.add_argument("--summary", default=SUMMARY_PATH)
    parser.add_argument(
        "--calibration",
        default="",
        help="Where to write the reliability bins; defaults beside --summary.",
    )
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--split", default="text", choices=("text", "sentence"))
    parser.add_argument(
        "--lexicon-exclude-test-sources", default=LEXICON_EXCLUDE_TEST_SOURCES
    )
    parser.add_argument("--no-lexicon", action="store_true")
    parser.add_argument(
        "--exclude-duplicates", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--near-duplicate-overlap", type=float, default=0.8)
    parser.add_argument(
        "--max-test-rows",
        type=int,
        default=0,
        help=(
            "Decode only the first N test rows. 0 = all of them. For the timing dry "
            "run: the split is built in full either way, so only the decode is cut."
        ),
    )
    parser.add_argument(
        "--split-manifest",
        default="",
        help=(
            "Write the identity of every TEST row (source, text id, sentence id, sign "
            "string) to this file. The split is a deterministic function of the corpus "
            "and the split code, but a pre-registration that names it by code sha alone "
            "cannot be checked afterwards; hashing this file pins it by content."
        ),
    )
    parser.add_argument(
        "--arms",
        default="",
        help="Comma-separated arm names to run; empty = all of them.",
    )
    return parser.parse_args(argv)


def main(argv: "list[str] | None" = None) -> None:
    args = _parse_args(argv)
    started = time.monotonic()

    full = aligned_rows(load_examples_csv(args.examples))
    lexicon_on = not args.no_lexicon
    lexicon_exclude = (
        parse_source_list(args.lexicon_exclude_test_sources) if lexicon_on else set()
    )
    split = select_test_rows(
        full,
        args.test_fraction,
        args.exclude_duplicates,
        args.near_duplicate_overlap,
        lexicon_on,
        lexicon_exclude,
        split_by=args.split,
    )
    train, test = split.train, split.test
    print(f"aligned sentences: {len(full)}  train: {len(train)}  test: {len(test)}")
    print(f"test sentences by source ({args.split} split): {test_mix(test)}")
    print(
        f"dropped from test: {split.exact_duplicates} exact duplicates, "
        f"{split.near_duplicates} near-duplicates, "
        f"{split.excluded_for_lexicon} lexicon-leaking rows"
    )
    if args.split_manifest:
        columns = [
            c
            for c in ("source", "source_text_id", "source_sentence_id", "hieroglyphs_norm")
            if c in test.columns
        ]
        Path(args.split_manifest).parent.mkdir(parents=True, exist_ok=True)
        test[columns].to_csv(args.split_manifest, index=False)
        print(f"wrote the test-split manifest to {args.split_manifest}")

    if args.max_test_rows:
        test = test.head(args.max_test_rows)
        print(f"DRY RUN: decoding only the first {len(test)} test rows")

    arms = ARMS
    if args.arms:
        wanted = parse_source_list(args.arms)
        arms = tuple(arm for arm in ARMS if arm.name in wanted)
        if not any(arm.name == BASELINE_ARM for arm in arms):
            raise SystemExit(f"--arms must include {BASELINE_ARM}: it is the baseline")

    built = time.monotonic()
    resources = build_resources(train, lexicon_on)
    print(f"models built in {time.monotonic() - built:.1f}s")

    decode_started = time.monotonic()
    position_rows, line_rows = evaluate(test, resources, arms)
    decode_seconds = time.monotonic() - decode_started
    positions = pd.DataFrame(position_rows)
    lines = pd.DataFrame(line_rows)
    summary, calibration = summarise(positions, lines)

    for path, frame in (
        (args.positions, positions),
        (args.lines, lines),
        (args.summary, pd.DataFrame(summary)),
    ):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
    calibration_path = args.calibration or str(
        Path(args.summary).with_name(Path(args.summary).stem + "_calibration.csv")
    )
    pd.DataFrame(calibration).to_csv(calibration_path, index=False)

    print()
    for record in summary:
        if record["scope"] != "all":
            continue
        print(
            f"{record['arm']:>14}  acc_all {_fmt(record['acc_all'])}  "
            f"firing {record['firing_positions']:>5} acc {_fmt(record['acc_firing'])} "
            f"(+{record['firing_better']}/-{record['firing_worse']})  "
            f"neighbour acc {_fmt(record['acc_neighbour'])} "
            f"(+{record['neighbour_better']}/-{record['neighbour_worse']})  "
            f"other acc {_fmt(record['acc_other'])} "
            f"(+{record['other_better']}/-{record['other_worse']})  "
            f"lines +{record['lines_exact_gained']}/-{record['lines_exact_lost']}  "
            f"seg F1 {_fmt(record['boundary_f1'])}  split cartouches "
            f"{record['cartouches_split']}  stage moved {record['stage_changed_vs_baseline']}"
        )
    print()
    print(
        f"decoded {len(lines) // max(len(arms), 1)} rows x {len(arms)} arms in "
        f"{decode_seconds:.1f}s "
        f"({decode_seconds / max(len(lines) // max(len(arms), 1), 1):.3f}s per row)"
    )
    print(f"total {time.monotonic() - started:.1f}s")
    print(f"wrote {args.positions}, {args.lines}, {args.summary}, {calibration_path}")


if __name__ == "__main__":
    main()

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
(reliability bins and a Brier score) with and without the /k discount.

Nothing here decides anything. The decision rules are in
`docs/kri-fixes-preregistration-2026-10-26.md`; this script only produces the numbers
they are applied to.
"""

from __future__ import annotations

import argparse
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
    return out


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


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
    """
    position_rows: list[dict] = []
    line_rows: list[dict] = []

    for row_index, row in enumerate(test.itertuples(index=False)):
        gold_groups = str(row.hieroglyphs_norm).split()
        gold_readings = str(row.transliteration_gold).split()
        if not gold_groups or len(gold_groups) != len(gold_readings):
            continue
        row_id = f"{getattr(row, 'source', '')}:{row_index}"
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

        for arm in arms:
            routing = routings[arm.cartouche]
            predictions = decodes[(arm.cartouche, arm.pooled)]
            fired = [index for index, p in enumerate(predictions) if p.used_pooled_evidence]
            neighbours = {i + d for i in fired for d in (-1, 1)} - set(fired)
            correct_count = 0
            for index, (prediction, truth) in enumerate(zip(predictions, gold_readings)):
                is_correct = prediction.predicted == truth
                correct_count += int(is_correct)
                position_rows.append(
                    {
                        "arm": arm.name,
                        "row_id": row_id,
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
                        "class": (
                            "firing"
                            if index in fired
                            else "neighbour"
                            if index in neighbours
                            else "other"
                        ),
                    }
                )
            predicted_boundaries = boundaries(routing.resegmented)
            # Always the real function, never the one the "off" arm disables: the
            # point of that arm is to count the cartouches it splits, which it cannot
            # do if it has also forgotten where they are.
            spans = cartouche_spans("".join(gold_groups))
            inside = {b for start, end in spans for b in range(start + 1, end)}
            line_rows.append(
                {
                    "arm": arm.name,
                    "row_id": row_id,
                    "stage": routing.stage or "",
                    "coverage": ";".join(
                        f"{s}={n}" for s, n in sorted(routing.coverage.items())
                    ),
                    "n_positions": len(gold_groups),
                    "n_correct": correct_count,
                    "line_exact": int(correct_count == len(gold_groups)),
                    "n_firing": len(fired),
                    "seg_exact": int(routing.resegmented == gold_groups),
                    "boundary_tp": len(predicted_boundaries & gold_boundaries),
                    "boundary_fp": len(predicted_boundaries - gold_boundaries),
                    "boundary_fn": len(gold_boundaries - predicted_boundaries),
                    "boundary_fp_outside_cartouche": len(
                        (predicted_boundaries - gold_boundaries) - inside
                    ),
                    "cartouches": len(spans),
                    "cartouches_split": len(predicted_boundaries & inside),
                }
            )
    return position_rows, line_rows


def summarise(positions: pd.DataFrame, lines: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Per-arm aggregates and, against the baseline arm, paired counts."""
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
    baseline_stage = dict(zip(baseline_lines["row_id"], baseline_lines["stage"]))

    for arm_name, arm_positions in positions.groupby("arm", sort=False):
        arm_lines = lines[lines["arm"] == arm_name]
        firing = arm_positions[arm_positions["class"] == "firing"]
        neighbour = arm_positions[arm_positions["class"] == "neighbour"]
        other = arm_positions[arm_positions["class"] == "other"]
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
        stage_moved = sum(
            1
            for row_id, stage in zip(arm_lines["row_id"], arm_lines["stage"])
            if baseline_stage.get(row_id, stage) != stage
        )
        tp = int(arm_lines["boundary_tp"].sum())
        fp = int(arm_lines["boundary_fp"].sum())
        fn = int(arm_lines["boundary_fn"].sum())
        precision = ratio(tp, tp + fp)
        recall = ratio(tp, tp + fn)
        summary.append(
            {
                "arm": arm_name,
                "positions": len(arm_positions),
                "acc_all": ratio(int(arm_positions["correct"].sum()), len(arm_positions)),
                "firing_positions": len(firing),
                "acc_firing": ratio(int(firing["correct"].sum()), len(firing)),
                "neighbour_positions": len(neighbour),
                "acc_neighbour": ratio(int(neighbour["correct"].sum()), len(neighbour)),
                "other_positions": len(other),
                "acc_other": ratio(int(other["correct"].sum()), len(other)),
                "positions_changed_vs_baseline": changed,
                "better_than_baseline": better,
                "worse_than_baseline": worse,
                "lines": len(arm_lines),
                "lines_exact": int(arm_lines["line_exact"].sum()),
                "seg_exact": int(arm_lines["seg_exact"].sum()),
                "boundary_precision": precision,
                "boundary_recall": recall,
                "boundary_f1": ratio(2 * tp, 2 * tp + fp + fn),
                "boundary_fp_outside_cartouche": int(
                    arm_lines["boundary_fp_outside_cartouche"].sum()
                ),
                "cartouches": int(arm_lines["cartouches"].sum()),
                "cartouches_split": int(arm_lines["cartouches_split"].sum()),
                "stage_changed_vs_baseline": stage_moved,
            }
        )
        records = [
            (float(confidence), bool(correct))
            for confidence, correct in zip(
                arm_positions["confidence"], arm_positions["correct"]
            )
        ]
        for calibration_row in calibration_rows(records, CALIBRATION_BINS):
            calibration_row["arm"] = arm_name
            calibration.append(calibration_row)
    return summary, calibration


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
        print(
            f"{record['arm']:>14}  acc_all {record['acc_all']:.4f}  "
            f"firing {record['firing_positions']:>5} acc {record['acc_firing']:.4f}  "
            f"neighbour acc {record['acc_neighbour']:.4f}  other acc {record['acc_other']:.4f}  "
            f"better/worse {record['better_than_baseline']}/{record['worse_than_baseline']}  "
            f"seg F1 {record['boundary_f1']:.4f}  split cartouches "
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

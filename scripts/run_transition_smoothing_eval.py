"""Paired measurement of the transition-smoothing candidates (2026-10-28).

The experiment is `docs/transition-smoothing-preregistration-2026-10-28.md`; this script
only produces the numbers its rules are applied to (`scripts/check_transition_smoothing_
gates.py` applies them). Four arms, one baseline:

  off                  today's add-k, byte for byte
  c2_transition_only   Witten-Bell on `_transition` only
  c2                   Witten-Bell on `_transition`, `_sign_context`, `_next_sign_context`
  c3                   interpolated absolute discounting on the same three

Three phases (`--phase`):

  manifests   split only, no model: writes the TEST manifest and the two candidate DEV
              manifests (10% and 20% draw), and prints their sha256. Cheap.
  dev         fits on training-minus-dev, checks the pre-registered minimum counts BEFORE
              any arm is decoded (10% draw; once, at 20% if the counts are short; else
              exit 4 "not runnable"), then decodes the dev rows under every arm.
  test        fits on the whole training partition and decodes the test split under every
              arm. Run only after the dev record is committed (the runner enforces it).

**Routing is the `off` routing in every arm (R2).** The stage of a row is chosen once, by
`choose_stage_by_likelihood` with the default (add-k) estimator, and every arm decodes
under that stage. What each arm's estimator *would* have routed to is computed besides,
for diagnosis only (`hyp_stage`, `hyp_scores` in the lines file). Segmentation reads
`sign_reading` counts only, so boundary scores cannot differ between arms; they are
written per arm anyway and the checker gates on them.

**Scoring is on the reading track (R8).** Every row is decoded on its own gold sign
grouping, prediction k is aligned to gold position k by index, correct iff
`prediction.predicted == gold_reading`. A length mismatch is a harness fault (exit 3).

The split is `scripts.run_reading_model_eval.select_test_rows`, called with the arguments
the pre-registration names; the dev draw is `split_dev` below. No private or KRI data is
read: the only input is `data/processed/examples.csv`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.services.reading_model as reading_model_module  # noqa: E402
from app.data.loader import load_examples_csv  # noqa: E402
from app.services.reading_model import BOUNDARY, smoothing_modes  # noqa: E402
from app.services.segmentation import segment_paste  # noqa: E402
from app.services.stage import STAGES, choose_stage_by_likelihood  # noqa: E402
from scripts.eval_guards import text_group_keys  # noqa: E402
from scripts.run_kri_fixes_eval import (  # noqa: E402
    CALIBRATION_BINS,
    HarnessResources,
    boundaries,
    build_resources,
    calibration_rows,
    ratio,
)
from scripts.run_reading_model_eval import (  # noqa: E402
    EXAMPLES_PATH,
    aligned_rows,
    near_duplicate_mask,
    parse_source_list,
    select_test_rows,
    test_mix,
)

# ---------------------------------------------------------------------------
# Constants fixed by the pre-registration (sections 4 and 5). Changing one needs a dated
# addendum there; scripts/check_transition_smoothing_gates.py repeats those it needs.
# ---------------------------------------------------------------------------

SEED = 20261026
DEV_RATES = (0.10, 0.20)
MIN_DEV_POSITIONS = 2000
MIN_DEV_MEMBERS = 100
TEST_FRACTION = 0.2
NEAR_DUPLICATE_OVERLAP = 0.8
LEXICON_EXCLUDE_SOURCES = "Ramses,AES"
SPLIT_BY = "text"

BASELINE_ARM = "off"
EXIT_FAULT = 3  # a harness fault: a length mismatch, a routing that differs between arms
EXIT_NOT_RUNNABLE = 4  # the dev counts are short even at the 20% draw


@dataclass(frozen=True)
class Arm:
    name: str
    scheme: str  # an `app.services.reading_model.SMOOTHING_SCHEMES` member


ARMS: tuple[Arm, ...] = (
    Arm("off", "off"),
    Arm("c2_transition_only", "c2_transition_only"),
    Arm("c2", "c2"),
    Arm("c3", "c3"),
)
# Simplest first (R7): the order a tie and the dev walk are decided in.
SIMPLICITY_ORDER = ("c2_transition_only", "c2", "c3")
MANIFEST_COLUMNS = ("source", "source_text_id", "source_sentence_id", "hieroglyphs_norm")


class HarnessFault(Exception):
    """The harness itself is wrong (exit 3); never scored, never retried silently."""


# ---------------------------------------------------------------------------
# The dev split (R4)
# ---------------------------------------------------------------------------


@dataclass
class DevSplit:
    rate: float
    dev: pd.DataFrame
    fit: pd.DataFrame  # the training partition minus every drawn row
    drawn: int
    drawn_units: int
    dropped_exact: int
    dropped_near: int
    dropped_leaky: int


def draw_units(train: pd.DataFrame, rate: float, seed: int = SEED) -> set[str]:
    """Which text groups are drawn: `rate` of each source's units, whole units at a time.

    Units are `eval_guards.text_group_keys` — an AES text is one unit, every other row
    (TLA, BBAW, and Ramses, whose rows carry no text identity beyond the official split)
    is its own unit. Per source, in sorted source order, the unit keys are sorted and
    `max(1, int(rate * n + 0.5))` of them are taken without replacement by a single
    `numpy.random.default_rng(seed)` stream, so the draw is a function of the corpus, the
    rate and the seed and of nothing else (not of row order).
    """
    keys = text_group_keys(train)
    units: dict[str, set[str]] = {}
    for key, source in zip(keys, train["source"].astype(str)):
        units.setdefault(source, set()).add(key)
    rng = np.random.default_rng(seed)
    chosen: set[str] = set()
    for source in sorted(units):
        ordered = sorted(units[source])
        take = max(1, int(rate * len(ordered) + 0.5))
        picked = rng.choice(len(ordered), size=take, replace=False)
        chosen.update(ordered[i] for i in sorted(int(p) for p in picked))
    return chosen


def split_dev(
    train: pd.DataFrame,
    rate: float,
    lexicon_on: bool = True,
    lexicon_exclude: "set[str] | None" = None,
    near_duplicate_overlap: float = NEAR_DUPLICATE_OVERLAP,
    seed: int = SEED,
) -> DevSplit:
    """Draw the dev rows from `train`, then apply the test split's hygiene (R4).

    Order and wording follow `select_test_rows`: exact sign-string duplicates of a row in
    the fit data are counted and dropped, then rows at sign-group Jaccard >= the overlap
    to a fit row, then (lexicon on) rows of the lexicon-leaking sources. Every comparison
    is against `fit` = the training partition minus ALL drawn rows, so no dev row can
    have a duplicate or a near-duplicate in the data a dev model is fitted on. A drawn row
    that the hygiene drops leaves the experiment: it is in neither dev nor `fit`, as a
    dropped test row is in neither test nor train.
    """
    if lexicon_exclude is None:
        lexicon_exclude = parse_source_list(LEXICON_EXCLUDE_SOURCES)
    chosen = draw_units(train, rate, seed)
    keys = text_group_keys(train)
    drawn_mask = np.array([key in chosen for key in keys], dtype=bool)
    drawn = train[drawn_mask]
    fit = train[~drawn_mask]
    fit_signs = set(fit["hieroglyphs_norm"].astype(str))
    exact_mask = drawn["hieroglyphs_norm"].astype(str).isin(fit_signs)
    dropped_exact = int(exact_mask.sum())
    dev = drawn[~exact_mask]
    near_mask = near_duplicate_mask(dev, fit, near_duplicate_overlap)
    dropped_near = int(near_mask.sum())
    dev = dev[~near_mask]
    dropped_leaky = 0
    if lexicon_on and lexicon_exclude:
        leaky = dev["source"].astype(str).isin(lexicon_exclude)
        dropped_leaky = int(leaky.sum())
        dev = dev[~leaky]
    return DevSplit(
        rate=rate,
        dev=dev,
        fit=fit,
        drawn=len(drawn),
        drawn_units=len(chosen),
        dropped_exact=dropped_exact,
        dropped_near=dropped_near,
        dropped_leaky=dropped_leaky,
    )


def manifest_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[[c for c in MANIFEST_COLUMNS if c in frame.columns]]


def write_manifest(frame: pd.DataFrame, path: "str | Path") -> str:
    """Write a split manifest and return its sha256 (the identity that gets pinned)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest_frame(frame).to_csv(path, index=False)
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Routing, populations, scoring
# ---------------------------------------------------------------------------


@dataclass
class Routing:
    stage: "str | None"
    coverage: dict
    scores: dict
    resegmented: list


def route_row(resources: HarnessResources, gold_groups: list[str]) -> Routing:
    """The `off` routing of the row (the router's own default) and its re-segmentation.

    The paste handed to the router is the row's own grouping; the re-segmentation scored
    for the boundary rule is of the same signs with the spaces removed.
    """
    coverage: dict[str, int] = {}
    stage, scores = choose_stage_by_likelihood(
        " ".join(gold_groups), resources.stage_resources, coverage=coverage
    )
    unspaced, _as_pasted = segment_paste("".join(gold_groups), resources.segmenter)
    return Routing(stage=stage, coverage=coverage, scores=scores, resegmented=unspaced.groups)


def context_of(model, previous: str) -> tuple[int, int]:
    """(N(h), V_obs(h)) of a previous reading in the `_transition` table."""
    counts = model.reading_bigram.get(previous)
    if not counts:
        return 0, 0
    return sum(counts.values()), len(counts)


def band_of(total: int) -> str:
    """The N(h) bands of R1: 1, 2-3, 4 and above."""
    if total <= 0:
        return ""
    if total == 1:
        return "1"
    return "2-3" if total <= 3 else "4+"


def gold_population(model, gold_readings: list[str]) -> list[dict]:
    """Per position: the gold-defined mechanism population of R5 (d') / R8.

    Position 0 has the BOUNDARY context, which no arm changes, and a gold previous
    reading of `''` is outside the experiment (R3): neither is ever a member. Membership
    depends on the gold data and the routed stage's fitted model only, never on a decode.
    """
    out: list[dict] = []
    for i in range(len(gold_readings)):
        info = {"prev_gold": "", "prev_n": 0, "prev_vobs": 0, "band": "", "member1": 0, "member2": 0}
        if i >= 1 and gold_readings[i - 1] != "":
            previous = gold_readings[i - 1]
            total, observed = context_of(model, previous)
            info.update(
                prev_gold=previous,
                prev_n=total,
                prev_vobs=observed,
                band=band_of(total) if observed == 1 else "",
                member1=int(observed == 1),
                member2=int(observed == 2 and total <= 3),
            )
        out.append(info)
    return out


def dev_counts(
    rows: "pd.DataFrame", resources: HarnessResources, routings: dict[int, Routing]
) -> dict:
    """The minimum-count quantities of R4: dev positions and R5-population members."""
    positions = members = 0
    for index, row in enumerate(rows.itertuples(index=False)):
        gold_groups = str(row.hieroglyphs_norm).split()
        gold_readings = str(row.transliteration_gold).split()
        if not gold_groups or len(gold_groups) != len(gold_readings):
            continue
        positions += len(gold_groups)
        model = resources.model_for(routings[index].stage)
        members += sum(info["member1"] for info in gold_population(model, gold_readings))
    return {"dev_positions": positions, "dev_members": members}


def counts_ok(counts: dict) -> bool:
    return (
        counts["dev_positions"] >= MIN_DEV_POSITIONS and counts["dev_members"] >= MIN_DEV_MEMBERS
    )


def runner_up_of(prediction, chosen: str) -> str:
    """The best-attested candidate other than the chosen reading ('' when there is none)."""
    for reading, _share in prediction.candidates:
        if reading != chosen:
            return reading
    return ""


def evaluate(
    rows: pd.DataFrame,
    resources: HarnessResources,
    arms: tuple[Arm, ...],
    routings: "dict[int, Routing] | None" = None,
    timing: "dict[str, float] | None" = None,
) -> tuple[list[dict], list[dict]]:
    """Decode every row under every arm. Returns (position rows, line rows).

    The stage of a row comes from the `off` routing and is the same in every arm. Work is
    memoised on what determines it: one routing, one re-segmentation and one decode per
    arm, plus one diagnostic routing per non-baseline arm.
    """
    timing = timing if timing is not None else {}
    keys = text_group_keys(rows)
    position_rows: list[dict] = []
    line_rows: list[dict] = []
    for row_index, row in enumerate(rows.itertuples(index=False)):
        gold_groups = str(row.hieroglyphs_norm).split()
        gold_readings = str(row.transliteration_gold).split()
        if not gold_groups or len(gold_groups) != len(gold_readings):
            continue
        source = str(getattr(row, "source", ""))
        row_id = f"{source}:{row_index}"
        group_key = keys[row_index]
        gold_boundaries = boundaries(gold_groups)

        started = time.perf_counter()
        routing = (routings or {}).get(row_index) or route_row(resources, gold_groups)
        timing["routing_off"] = timing.get("routing_off", 0.0) + time.perf_counter() - started
        model = resources.model_for(routing.stage)
        population = gold_population(model, gold_readings)
        predicted_boundaries = boundaries(routing.resegmented)

        for arm in arms:
            started = time.perf_counter()
            predictions = model.predict_sequence(gold_groups, smoothing=arm.scheme)
            timing[f"decode_{arm.name}"] = (
                timing.get(f"decode_{arm.name}", 0.0) + time.perf_counter() - started
            )
            if len(predictions) != len(gold_groups):
                raise HarnessFault(
                    f"{row_id}: {len(predictions)} predictions for {len(gold_groups)} gold groups"
                )
            if arm.scheme == "off":
                hyp_stage, hyp_scores, hyp_coverage = routing.stage, routing.scores, routing.coverage
            else:
                started = time.perf_counter()
                hyp_coverage = {}
                hyp_stage, hyp_scores = choose_stage_by_likelihood(
                    " ".join(gold_groups),
                    resources.stage_resources,
                    coverage=hyp_coverage,
                    smoothing=arm.scheme,
                )
                timing[f"routing_hyp_{arm.name}"] = (
                    timing.get(f"routing_hyp_{arm.name}", 0.0) + time.perf_counter() - started
                )
            transition_mode, _sign_mode = smoothing_modes(arm.scheme)
            correct_count = 0
            for index, (prediction, truth) in enumerate(zip(predictions, gold_readings)):
                is_correct = prediction.predicted == truth
                correct_count += int(is_correct)
                previous = BOUNDARY if index == 0 else predictions[index - 1].predicted
                runner = runner_up_of(prediction, prediction.predicted)
                own_total, own_observed = (
                    context_of(model, previous) if index >= 1 and previous != "" else (0, 0)
                )
                position_rows.append(
                    {
                        "arm": arm.name,
                        "row_id": row_id,
                        "source": source,
                        "group_key": group_key,
                        "position": index,
                        "group": prediction.sign,
                        "gold_reading": truth,
                        "predicted": prediction.predicted,
                        "correct": int(is_correct),
                        "stage": routing.stage or "",
                        "was_seen": int(prediction.was_seen),
                        "is_borrowed": int(prediction.is_borrowed),
                        "attested_count": prediction.attested_count,
                        "reading_count": prediction.reading_count,
                        "reading_probability": round(float(prediction.reading_probability), 6),
                        "confidence": round(float(prediction.confidence), 6),
                        **population[index],
                        "own_prev_vobs1": int(index >= 1 and own_observed == 1),
                        "runner_up": runner,
                        "t_chosen_off": model._transition(previous, prediction.predicted, "off"),
                        "t_chosen_arm": model._transition(
                            previous, prediction.predicted, transition_mode
                        ),
                        "t_runner_off": (
                            model._transition(previous, runner, "off") if runner else ""
                        ),
                        "t_runner_arm": (
                            model._transition(previous, runner, transition_mode) if runner else ""
                        ),
                    }
                )
            line_rows.append(
                {
                    "arm": arm.name,
                    "row_id": row_id,
                    "source": source,
                    "group_key": group_key,
                    "stage": routing.stage or "",
                    "coverage": ";".join(f"{s}={n}" for s, n in sorted(routing.coverage.items())),
                    "off_scores": ";".join(f"{s}={v:.6f}" for s, v in routing.scores.items()),
                    "hyp_stage": hyp_stage or "",
                    "hyp_coverage": ";".join(f"{s}={n}" for s, n in sorted(hyp_coverage.items())),
                    "hyp_scores": ";".join(f"{s}={v:.6f}" for s, v in hyp_scores.items()),
                    "n_positions": len(gold_groups),
                    "n_correct": correct_count,
                    "line_exact": int(correct_count == len(gold_groups)),
                    "seg_exact": int(routing.resegmented == gold_groups),
                    "boundary_tp": len(predicted_boundaries & gold_boundaries),
                    "boundary_fp": len(predicted_boundaries - gold_boundaries),
                    "boundary_fn": len(gold_boundaries - predicted_boundaries),
                }
            )
    return position_rows, line_rows


# ---------------------------------------------------------------------------
# Summary and calibration
# ---------------------------------------------------------------------------


def summarise(positions: pd.DataFrame, lines: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Per-arm aggregates (all, and per source) with paired counts against `off`."""
    base = positions[positions["arm"] == BASELINE_ARM]
    base_correct = dict(zip(zip(base["row_id"], base["position"]), base["correct"]))
    base_stage = dict(
        zip(lines[lines["arm"] == BASELINE_ARM]["row_id"], lines[lines["arm"] == BASELINE_ARM]["stage"].astype(str))
    )
    summary: list[dict] = []
    calibration: list[dict] = []
    scopes = [("all", None)] + [
        (f"source:{s}", s) for s in sorted(set(positions["source"].astype(str)))
    ]
    for arm_name, arm_positions in positions.groupby("arm", sort=False):
        arm_lines = lines[lines["arm"] == arm_name]
        for scope, source in scopes:
            part = arm_positions if source is None else arm_positions[arm_positions["source"].astype(str) == source]
            part_lines = arm_lines if source is None else arm_lines[arm_lines["source"].astype(str) == source]
            better = worse = 0
            for key, correct in zip(zip(part["row_id"], part["position"]), part["correct"]):
                other = base_correct.get(key)
                if other is None:
                    continue
                better += int(correct == 1 and other == 0)
                worse += int(correct == 0 and other == 1)
            tp, fp, fn = (int(part_lines[c].sum()) for c in ("boundary_tp", "boundary_fp", "boundary_fn"))
            summary.append(
                {
                    "arm": arm_name,
                    "scope": scope,
                    "positions": len(part),
                    "correct": int(part["correct"].sum()),
                    "acc_all": ratio(int(part["correct"].sum()), len(part)),
                    "better_than_off": better,
                    "worse_than_off": worse,
                    "unchanged_vs_off": len(part) - better - worse,
                    "lines": len(part_lines),
                    "lines_exact": int(part_lines["line_exact"].sum()),
                    "seg_exact": int(part_lines["seg_exact"].sum()),
                    "boundary_tp": tp,
                    "boundary_fp": fp,
                    "boundary_fn": fn,
                    "boundary_errors": fp + fn,
                    "boundary_f1": ratio(2 * tp, 2 * tp + fp + fn),
                    "stage_changed_vs_off": sum(
                        1
                        for row_id, stage in zip(part_lines["row_id"], part_lines["stage"].astype(str))
                        if base_stage.get(row_id, stage) != stage
                    ),
                    "hyp_stage_changed_vs_off": sum(
                        1
                        for row_id, stage in zip(part_lines["row_id"], part_lines["hyp_stage"].astype(str))
                        if base_stage.get(row_id, stage) != stage
                    ),
                }
            )
        for subset, part in (
            ("all", arm_positions),
            ("with_reading", arm_positions[arm_positions["predicted"].astype(str) != ""]),
        ):
            records = [
                (float(confidence), bool(correct))
                for confidence, correct in zip(part["confidence"], part["correct"])
            ]
            for entry in calibration_rows(records, CALIBRATION_BINS):
                entry["arm"] = arm_name
                entry["subset"] = subset
                calibration.append(entry)
    return summary, calibration


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--phase", required=True, choices=("manifests", "dev", "test"))
    parser.add_argument("--examples", default=EXAMPLES_PATH)
    parser.add_argument("--out-dir", required=True, help="Where every output of the phase goes.")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=0,
        help="Decode only the first N rows of the dev/test frame (dry runs only; 0 = all).",
    )
    return parser.parse_args(argv)


def _fmt(value) -> str:
    return "  n/a " if value is None else f"{value:.4f}"


def _write_outputs(out: Path, prefix: str, positions, lines, summary, calibration) -> None:
    out.mkdir(parents=True, exist_ok=True)
    positions.to_csv(out / f"{prefix}_positions.csv", index=False)
    lines.to_csv(out / f"{prefix}_lines.csv", index=False)
    pd.DataFrame(summary).to_csv(out / f"{prefix}_summary.csv", index=False)
    pd.DataFrame(calibration).to_csv(out / f"{prefix}_calibration.csv", index=False)


def _log_models(out: Path, resources: HarnessResources, prefix: str) -> dict:
    """Vocabulary sizes and Ney discounts of every fitted model, for the run log."""
    started = time.perf_counter()
    report = {"pooled": resources.pooled.smoothing_report()}
    for stage in STAGES:
        report[stage] = resources.by_stage[stage].smoothing_report()
    seconds = time.perf_counter() - started
    (out / f"{prefix}_smoothing_report.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    for name, entry in report.items():
        d = {t: (round(entry[t]["d"], 4), entry[t]["fallback"]) for t in ("transition", "sign_context", "next_sign_context")}
        print(f"smoothing[{name}]: |R|={entry['vocabulary']} N={entry['unigram_total']} d(fallback)={d}")
    print(f"smoothing report derived in {seconds:.2f}s")
    return {"seconds": seconds}


def main(argv: "list[str] | None" = None) -> int:
    args = _parse_args(argv)
    started = time.monotonic()
    if reading_model_module.TRANSITION_SMOOTHING_BY_DEFAULT != "off":
        print(
            "refusing to run: the decoder's default scheme is not 'off' "
            f"({reading_model_module.TRANSITION_SMOOTHING_ENV} is set); the baseline arm "
            "must be today's code",
            file=sys.stderr,
        )
        return 2
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lexicon_on = True
    lexicon_exclude = parse_source_list(LEXICON_EXCLUDE_SOURCES)

    full = aligned_rows(load_examples_csv(args.examples))
    split = select_test_rows(
        full,
        TEST_FRACTION,
        True,
        NEAR_DUPLICATE_OVERLAP,
        lexicon_on,
        lexicon_exclude,
        split_by=SPLIT_BY,
    )
    train, test = split.train, split.test
    print(f"aligned sentences: {len(full)}  train: {len(train)}  test: {len(test)}")
    print(f"test sentences by source ({SPLIT_BY} split): {test_mix(test)}")
    print(
        f"dropped from test: {split.exact_duplicates} exact duplicates, "
        f"{split.near_duplicates} near-duplicates, {split.excluded_for_lexicon} lexicon-leaking rows"
    )

    if args.phase == "manifests":
        info = {"test_manifest_sha256": write_manifest(test, out / "split_manifest.csv")}
        info["test_rows"] = len(test)
        for rate in DEV_RATES:
            dev = split_dev(train, rate, lexicon_on, lexicon_exclude)
            tag = f"{int(round(rate * 100))}"
            info[f"dev_manifest_sha256_r{tag}"] = write_manifest(dev.dev, out / f"dev_manifest_r{tag}.csv")
            info[f"dev_r{tag}"] = {
                "drawn_rows": dev.drawn,
                "drawn_units": dev.drawn_units,
                "dropped_exact": dev.dropped_exact,
                "dropped_near": dev.dropped_near,
                "dropped_leaky": dev.dropped_leaky,
                "dev_rows": len(dev.dev),
                "fit_rows": len(dev.fit),
                "dev_sources": test_mix(dev.dev),
            }
            print(f"dev draw {rate:.2f}: {info[f'dev_r{tag}']}")
        (out / "manifests.json").write_text(json.dumps(info, indent=2, sort_keys=True))
        for key, value in info.items():
            if key.endswith("_sha256") or "_sha256_" in key:
                print(f"{key}: {value}")
        print(f"total {time.monotonic() - started:.1f}s")
        return 0

    try:
        if args.phase == "dev":
            return _run_dev(args, out, train, lexicon_on, lexicon_exclude, started)
        return _run_test(args, out, train, test, lexicon_on, started)
    except HarnessFault as fault:
        print(f"HARNESS FAULT: {fault}", file=sys.stderr)
        return EXIT_FAULT


def _decode_and_write(
    args, out: Path, prefix: str, frame: pd.DataFrame, resources, routings, fit_seconds: float
) -> None:
    if args.max_rows:
        frame = frame.head(args.max_rows)
        print(f"DRY RUN: decoding only the first {len(frame)} rows")
    timing: dict[str, float] = {"fit_all_models": fit_seconds}
    decode_started = time.monotonic()
    position_rows, line_rows = evaluate(frame, resources, ARMS, routings, timing)
    positions = pd.DataFrame(position_rows)
    lines = pd.DataFrame(line_rows)
    summary, calibration = summarise(positions, lines)
    _write_outputs(out, prefix, positions, lines, summary, calibration)
    pd.DataFrame(
        [{"component": name, "seconds": round(seconds, 3)} for name, seconds in sorted(timing.items())]
    ).to_csv(out / f"{prefix}_timing.csv", index=False)
    print()
    for record in summary:
        if record["scope"] != "all":
            continue
        print(
            f"{record['arm']:>20}  acc {_fmt(record['acc_all'])} "
            f"(+{record['better_than_off']}/-{record['worse_than_off']})  "
            f"lines exact {record['lines_exact']}/{record['lines']}  "
            f"boundary errors {record['boundary_errors']}  stage moved {record['stage_changed_vs_off']}  "
            f"hypothetical stage moves {record['hyp_stage_changed_vs_off']}"
        )
    print(f"decoded {len(lines) // len(ARMS)} rows x {len(ARMS)} arms in {time.monotonic() - decode_started:.1f}s")
    for name, seconds in sorted(timing.items()):
        print(f"timing {name}: {seconds:.1f}s")


def _run_dev(args, out: Path, train, lexicon_on, lexicon_exclude, started) -> int:
    chosen = None
    attempts: list[dict] = []
    for rate in DEV_RATES:
        dev = split_dev(train, rate, lexicon_on, lexicon_exclude)
        fit_started = time.monotonic()
        resources = build_resources(dev.fit, lexicon_on)
        fit_seconds = time.monotonic() - fit_started
        print(f"dev draw {rate:.2f}: models built on {len(dev.fit)} rows in {fit_seconds:.1f}s")
        routings = {
            index: route_row(resources, str(row.hieroglyphs_norm).split())
            for index, row in enumerate(dev.dev.itertuples(index=False))
            if str(row.hieroglyphs_norm).split()
            and len(str(row.hieroglyphs_norm).split()) == len(str(row.transliteration_gold).split())
        }
        counts = dev_counts(dev.dev, resources, routings)
        entry = {
            "rate": rate,
            **counts,
            "ok": counts_ok(counts),
            "drawn_rows": dev.drawn,
            "dropped_exact": dev.dropped_exact,
            "dropped_near": dev.dropped_near,
            "dropped_leaky": dev.dropped_leaky,
            "dev_rows": len(dev.dev),
            "fit_rows": len(dev.fit),
            "dev_sources": test_mix(dev.dev),
        }
        attempts.append(entry)
        print(f"dev counts at {rate:.2f}: {entry}")
        if entry["ok"]:
            chosen = (dev, resources, routings, fit_seconds, entry)
            break
    (out / "dev_counts.json").write_text(
        json.dumps(
            {
                "attempts": attempts,
                "chosen_rate": chosen[4]["rate"] if chosen else None,
                "min_dev_positions": MIN_DEV_POSITIONS,
                "min_dev_members": MIN_DEV_MEMBERS,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if chosen is None:
        print("NOT RUNNABLE: the minimum dev counts are short even at the 20% draw", file=sys.stderr)
        return EXIT_NOT_RUNNABLE
    dev, resources, routings, fit_seconds, entry = chosen
    write_manifest(dev.dev, out / "dev_manifest_used.csv")
    _log_models(out, resources, "dev")
    _decode_and_write(args, out, "dev", dev.dev, resources, routings, fit_seconds)
    print(f"total {time.monotonic() - started:.1f}s")
    return 0


def _run_test(args, out: Path, train, test, lexicon_on, started) -> int:
    fit_started = time.monotonic()
    resources = build_resources(train, lexicon_on)
    fit_seconds = time.monotonic() - fit_started
    print(f"models built on {len(train)} rows in {fit_seconds:.1f}s")
    write_manifest(test, out / "test_manifest_used.csv")
    _log_models(out, resources, "test")
    _decode_and_write(args, out, "test", test, resources, None, fit_seconds)
    print(f"total {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

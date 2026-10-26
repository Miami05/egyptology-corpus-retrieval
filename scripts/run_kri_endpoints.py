"""The KRI endpoint driver: declaration in, per-line and summary results out.

One command ties together everything §4d and §4e ask for, in the order they ask for
it, so that no step can be skipped by accident:

    declaration (validated, sha256 printed)
      -> overlap report (§4a): only `new`, non-excluded lines may be run
        -> endpoint G: the app's paste path -> segmentation -> per-group top 3
             -> the app-segment → gold-span mapping
             -> scripts.bfreq_baseline.score_endpoint_g (the frozen scorer, B-freq)
        -> endpoint R: Camilla's blind judgements, one binary per side per line
      -> per endpoint: exact sign test + Newcombe paired interval
      -> Holm across the family of two, power floor per endpoint
      -> per-line CSVs and a summary, written to --out

    python -I scripts/run_kri_endpoints.py \
        --declaration ~/egyptology-private-kri/declaration.csv \
        --lines ~/egyptology-private-kri/lines.csv \
        --overlap-report ~/egyptology-private-kri/overlap-report.csv \
        --examples data/processed/examples.csv \
        --bfreq-table ~/egyptology-baselines/kri-bfreq-2026-10-26/bfreq_table_all.csv \
        --judgements ~/egyptology-private-kri/judgements.csv \
        --out ~/egyptology-private-kri/run-2026-11-XX

What it refuses to do, deliberately:

* run without a valid declaration, or on a corpus whose sha256 is not the declared
  one, or from a commit that is not the declared one (§4e: "one evaluation on a
  pinned commit and a pinned corpus sha");
* run a line the §4a checker did not label `new`, or one the (B) manifest excludes
  (§4d: "The tool runs only on `new` lines");
* score a line whose app output is not the same sign string as its gold division —
  that is a mis-assembled run, and it is reported as a failure rather than scored;
* pool the two endpoints, or report a percentage for an endpoint with fewer than 30
  lines (§4d: "case by case … no percentages or intervals while n < 30").

The outputs hold ids, counts and numbers — never a KRI line, never a gold reading,
never a glyph. They are still derived from KRI material, so they belong in the
custody directory, not in the repo.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import load_examples_csv  # noqa: E402
from app.services.lexicon import load_lexicon  # noqa: E402
from app.services.reading_model import ReadingPrediction  # noqa: E402
from app.services.retrieval import resolve_auto_stage  # noqa: E402
from app.services.segmentation import segment_paste  # noqa: E402
from app.services.stage import StageResources, build_stage_resources  # noqa: E402
from scripts.bfreq_baseline import (  # noqa: E402
    DEFAULT_TOP_K,
    BFreqEntry,
    BFreqTable,
    assert_public_path,
    build_table,
    folded_reading_key,
    load_corpus,
    score_endpoint_g,
    score_line,
)
from scripts.kri_declaration import (  # noqa: E402
    ENDPOINT_G,
    ENDPOINT_R,
    read_declaration,
    validate,
)
from scripts.kri_exclusion_manifest import sha256_file  # noqa: E402
from scripts.kri_segment_mapping import MappingError, map_app_segments_to_gold  # noqa: E402
from scripts.kri_stats import POWER_FLOOR, analyse_family  # noqa: E402

#: What counts as "the app's top 3 for that group". The app's own per-group view
#: (`app/ui/whyptology_app.py`, the sign table) shows the chosen reading — the
#: context-aware Viterbi decode — and then the group's other attested readings in
#: frequency order. This rule mirrors that view exactly, so the number measured is
#: the number a reader of the app would have seen.
APP_TOP3_RULE = (
    "the app's chosen reading first (ReadingPrediction.predicted, the Viterbi "
    "decode the UI labels 'Chosen reading'), then the group's remaining candidates "
    "in frequency order (ReadingPrediction.candidates), truncated to the top k"
)

#: §4d: below 30 lines, case by case — no percentages, no intervals, no claim
#: beyond "on these lines".
SMALL_N = 30

LINE_COLUMNS = ("line_id", "glyph_input", "gold_groups", "gold_reading", "query_transliteration")
JUDGEMENT_COLUMNS = ("line_id", "app_success", "baseline_success")

G_REPORT_COLUMNS = (
    "declaration_id", "line_id", "cohort", "stage_used", "stage_inferred",
    "gold_groups", "scorable_groups", "placeholder_only_groups", "no_signs_groups",
    "app_segments", "exact", "merged", "split", "partial_overlap", "absent",
    "no_signs", "repeated_sign_strings",
    "app_hits", "app_score", "app_success", "baseline_hits", "baseline_score",
    "baseline_success", "app_hits_folded", "baseline_hits_folded", "error",
)
R_REPORT_COLUMNS = (
    "declaration_id", "line_id", "cohort", "app_success", "baseline_success", "judged", "error",
)


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        return "unknown"


# --------------------------------------------------------------------------- inputs


def read_csv_rows(path: str | Path, required: tuple[str, ...], what: str) -> list[dict]:
    resolved = Path(path).expanduser()
    with open(resolved, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in required if column not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"{resolved}: {what} is missing column(s) {missing}")
        return [dict(row) for row in reader]


def load_bfreq_table(path: str | Path) -> BFreqTable:
    """Rebuild the frozen B-freq table from its committed CSV.

    The table is a deterministic function of the corpus and the frozen rules, and it
    is not committed (it is derived CC BY-SA data). Reading it back here — rather
    than rebuilding it — is what makes a run quotable against the sha256 in
    `docs/kri-bfreq-baseline-2026-10-26.md`.
    """
    rows = read_csv_rows(path, ("sign_key", "rank", "reading_key", "count", "surface_reading"), "B-freq table")
    entries: dict[str, list[BFreqEntry]] = {}
    for row in rows:
        entries.setdefault(row["sign_key"], []).append(
            BFreqEntry(
                rank=int(row["rank"]),
                reading_key=row["reading_key"],
                count=int(row["count"]),
                surface_reading=row["surface_reading"],
            )
        )
    table = BFreqTable()
    for key, items in entries.items():
        table.entries[key] = tuple(sorted(items, key=lambda entry: entry.rank))
    return table


def runnable_lines(overlap_report: list[dict]) -> dict[str, dict]:
    return {row["line_id"]: row for row in overlap_report}


# --------------------------------------------------------------------------- the app


@dataclass
class AppResources:
    """The app's own resources, one build per language stage, built lazily."""

    frame: object
    lexicon: object
    cache: dict[str | None, StageResources]
    use_lexicon: bool = True

    def get(self, stage: str | None) -> StageResources:
        if stage not in self.cache:
            pooled = self.get(None).reading_model if stage is not None else None
            self.cache[stage] = build_stage_resources(
                self.frame,
                stage,
                lexicon=self.lexicon,
                use_lexicon=self.use_lexicon,
                pooled_reading_model=pooled,
            )
        return self.cache[stage]


def app_top_readings(prediction: ReadingPrediction, top_k: int) -> list[str]:
    """One sign group's top k, per `APP_TOP3_RULE`."""
    ranked: list[str] = []
    if prediction.predicted:
        ranked.append(prediction.predicted)
    for reading, _share in prediction.candidates:
        if reading and reading not in ranked:
            ranked.append(reading)
    return ranked[:top_k]


def run_app_on_line(resources: AppResources, glyph_input: str, top_k: int):
    """Segment a paste and read it, exactly as the app's own paste path does.

    Returns `(stage, inferred, segments, per-segment top k)`.
    """
    stage, inferred, _scores = resolve_auto_stage(glyph_input, resources.get)
    staged = resources.get(stage)
    segmentation, _as_pasted = segment_paste(glyph_input, staged.segmenter)
    predictions = staged.reading_model.predict_sequence(segmentation.groups)
    return (
        stage,
        inferred,
        segmentation.groups,
        [app_top_readings(prediction, top_k) for prediction in predictions],
    )


# --------------------------------------------------------------------------- endpoints


def score_g_line(
    resources: AppResources,
    table: BFreqTable,
    record: dict,
    top_k: int,
) -> dict:
    """One endpoint-G line: app paste path → mapping → the frozen scorer."""
    gold_groups = str(record["gold_groups"]).split()
    gold_readings = str(record["gold_reading"]).split()
    glyph_input = str(record["glyph_input"])
    row: dict[str, object] = {column: "" for column in G_REPORT_COLUMNS}
    row["line_id"] = record["line_id"]

    if not gold_groups or len(gold_groups) != len(gold_readings):
        row["error"] = (
            f"the line has {len(gold_groups)} gold groups and {len(gold_readings)} gold "
            f"readings; §4e needs one reading per group"
        )
        return row

    stage, inferred, segments, candidates = run_app_on_line(resources, glyph_input, top_k)
    row["stage_used"] = stage or "(pooled)"
    row["stage_inferred"] = "yes" if inferred else "no"
    row["app_segments"] = len(segments)

    try:
        mapping = map_app_segments_to_gold(gold_groups, segments, candidates, top_k=top_k)
    except MappingError as error:
        row["error"] = str(error)
        return row

    report, app_score, baseline_score = score_endpoint_g(
        table, gold_groups, gold_readings, mapping.app_candidates, top_k=top_k
    )
    baseline_candidates = table.predict_line(gold_groups, top_k=top_k)
    app_folded = score_line(
        gold_readings, mapping.app_candidates, top_k=top_k, key=folded_reading_key
    )
    baseline_folded = score_line(
        gold_readings, baseline_candidates, top_k=top_k, key=folded_reading_key
    )

    counts = mapping.counts
    row.update(
        {
            "gold_groups": report.groups,
            "scorable_groups": report.scorable,
            "placeholder_only_groups": report.placeholder_only,
            "no_signs_groups": report.no_signs,
            "exact": counts["exact"],
            "merged": counts["merged"],
            "split": counts["split"],
            "partial_overlap": counts["partial_overlap"],
            "absent": counts["absent"],
            "no_signs": counts["no_signs"],
            "repeated_sign_strings": mapping.repeated_groups,
            "app_hits": app_score.hits,
            "app_score": f"{app_score.score:.4f}",
            "app_success": "yes" if app_score.success else "no",
            "baseline_hits": baseline_score.hits,
            "baseline_score": f"{baseline_score.score:.4f}",
            "baseline_success": "yes" if baseline_score.success else "no",
            "app_hits_folded": app_folded.hits,
            "baseline_hits_folded": baseline_folded.hits,
        }
    )
    return row


def score_r_line(record: dict | None, line_id: str) -> dict:
    """One endpoint-R line: Camilla's blind judgement, one binary per side."""
    row = {column: "" for column in R_REPORT_COLUMNS}
    row["line_id"] = line_id
    if record is None:
        row["judged"] = "no"
        row["error"] = "no blind judgement supplied for this line"
        return row
    row["judged"] = "yes"
    row["app_success"] = "yes" if str(record["app_success"]).strip() in {"1", "yes", "true"} else "no"
    row["baseline_success"] = (
        "yes" if str(record["baseline_success"]).strip() in {"1", "yes", "true"} else "no"
    )
    return row


# --------------------------------------------------------------------------- the run


def write_rows(path: Path, columns: tuple[str, ...], rows: list[dict]) -> str:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return sha256_file(path)


def summarise(results: dict, out_dir: Path) -> str:
    """A short human summary beside the JSON, worded as §4d requires."""
    lines = ["# KRI endpoint run", ""]
    lines.append(f"commit {results['commit']}  corpus sha256 {results['corpus_sha256']}")
    lines.append(f"declaration sha256 {results['declaration_sha256']}")
    lines.append("")
    for endpoint in (ENDPOINT_G, ENDPOINT_R):
        block = results["endpoints"][endpoint]
        lines.append(f"## Endpoint {endpoint} — {block['description']}")
        lines.append("")
        lines.append(f"* lines declared: {block['declared']}, scored: {block['scored']}")
        if block["failed"]:
            lines.append(f"* **failed lines: {block['failed']}** (see the per-line CSV's `error`)")
        lines.append(f"* {block['verdict_line']}")
        if block["small_n"]:
            lines.append(
                f"* n < {SMALL_N}: reported case by case, k of n, with no percentages or "
                f"intervals and no claim beyond \"on these lines\" (§4d)."
            )
        if block["underpowered"]:
            lines.append(
                f"* below the power floor of about {POWER_FLOOR} lines for this endpoint: "
                f"reported as uninformative; it still counts in the Holm family of two."
            )
        if endpoint == ENDPOINT_G and block["exploratory"]:
            lines.append(
                f"* {block['exploratory']} of {block['declared']} lines are exploratory "
                f"(material received before the B-freq freeze): no endpoint-G number from "
                f"those lines goes to experts."
            )
        lines.append("")
    lines.append(
        "B-freq is given the gold word division; the app has to find it. That favours "
        "the baseline and is stated here because §4e requires the report to say so."
    )
    lines.append("")
    lines.append("Endpoints R and G are never pooled: no combined rate, no combined test.")
    text = "\n".join(lines) + "\n"
    (out_dir / "summary.md").write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--declaration", required=True)
    parser.add_argument("--lines", required=True, help="the private lines file (custody)")
    parser.add_argument("--overlap-report", required=True, help="output of scripts/check_overlap.py")
    parser.add_argument("--examples", required=True, help="the public corpus CSV")
    parser.add_argument("--bfreq-table", default=None, help="the frozen B-freq table CSV")
    parser.add_argument(
        "--build-bfreq",
        action="store_true",
        help="rebuild B-freq from --examples instead of reading the frozen table",
    )
    parser.add_argument("--judgements", default=None, help="endpoint R's blind judgements")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--no-lexicon",
        action="store_true",
        help=(
            "Read with the corpus alone, without the Helsinki sign-reading lexicon. "
            "The shipped app uses the lexicon, so a declared run normally does too; "
            "this exists for hermetic tests and for a lexicon-free comparison."
        ),
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. The declaration, and the pins it carries.
    declaration = read_declaration(args.declaration)
    problems = validate(declaration)
    if problems:
        for problem in problems:
            print(f"INVALID {problem}", file=sys.stderr)
        raise SystemExit("the declaration is not valid; nothing was run (§4d)")

    examples_path = assert_public_path(args.examples, what="corpus")
    corpus_sha = sha256_file(examples_path)
    if corpus_sha != declaration.corpus_sha256:
        raise SystemExit(
            f"the declaration pins corpus sha256 {declaration.corpus_sha256}, but "
            f"{examples_path} is {corpus_sha}. §4e allows one evaluation on one pinned "
            f"corpus; nothing was run."
        )
    commit = git_commit()
    if commit != declaration.commit:
        raise SystemExit(
            f"the declaration pins commit {declaration.commit}, but HEAD is {commit}. "
            f"§4e allows one evaluation on one pinned commit; nothing was run."
        )

    # 2. The §4a overlap check: only `new`, non-excluded lines may be run.
    overlap = runnable_lines(
        read_csv_rows(args.overlap_report, ("line_id", "label", "runnable"), "overlap report")
    )
    declared_lines = {run.line_id for run in declaration.runs}
    unchecked = sorted(declared_lines - set(overlap))
    if unchecked:
        raise SystemExit(
            f"{len(unchecked)} declared line(s) are not in the overlap report {unchecked}: "
            f"§4d overlap-checks every line first; nothing was run."
        )
    not_runnable = sorted(
        line for line in declared_lines if overlap[line]["runnable"] != "yes"
    )
    if not_runnable:
        raise SystemExit(
            f"{len(not_runnable)} declared line(s) are not runnable {not_runnable}: the "
            f"tool runs only on `new` lines that the (B) manifest does not exclude (§4d). "
            f"A `contained` or `partial` line is reported as \"found\", never as \"read\"."
        )

    # 3. Inputs.
    records = {row["line_id"]: row for row in read_csv_rows(args.lines, LINE_COLUMNS, "lines file")}
    judgements = (
        {row["line_id"]: row for row in read_csv_rows(args.judgements, JUDGEMENT_COLUMNS, "judgements")}
        if args.judgements
        else {}
    )
    if args.build_bfreq:
        table = build_table(load_corpus(examples_path))
        bfreq_source, bfreq_sha = f"rebuilt from {examples_path}", ""
    elif args.bfreq_table:
        table = load_bfreq_table(args.bfreq_table)
        bfreq_source = str(Path(args.bfreq_table).expanduser())
        bfreq_sha = sha256_file(args.bfreq_table)
    else:
        raise SystemExit("one of --bfreq-table or --build-bfreq is required")

    frame = load_examples_csv(str(examples_path))
    resources = AppResources(
        frame=frame,
        lexicon=None if args.no_lexicon else load_lexicon(),
        cache={},
        use_lexicon=not args.no_lexicon,
    )

    # 4. Score each declared run.
    g_rows: list[dict] = []
    r_rows: list[dict] = []
    for run in declaration.runs:
        record = records.get(run.line_id)
        if record is None:
            row = {column: "" for column in (G_REPORT_COLUMNS if run.endpoint == ENDPOINT_G else R_REPORT_COLUMNS)}
            row.update({"line_id": run.line_id, "error": "declared but missing from the lines file"})
        elif run.endpoint == ENDPOINT_G:
            row = score_g_line(resources, table, record, args.top_k)
        else:
            row = score_r_line(judgements.get(run.line_id), run.line_id)
        row["declaration_id"] = run.declaration_id
        row["cohort"] = run.cohort
        (g_rows if run.endpoint == ENDPOINT_G else r_rows).append(row)

    # 5. The statistics, per endpoint, never pooled.
    def pairs_of(rows: list[dict]) -> list[tuple[bool, bool]]:
        return [
            (row["app_success"] == "yes", row["baseline_success"] == "yes")
            for row in rows
            if not row["error"]
        ]

    pairs = {ENDPOINT_G: pairs_of(g_rows), ENDPOINT_R: pairs_of(r_rows)}
    analysis = analyse_family(pairs)

    results = {
        "commit": commit,
        "corpus": str(examples_path),
        "corpus_sha256": corpus_sha,
        "declaration": str(Path(args.declaration).expanduser()),
        "declaration_sha256": declaration.sha256(),
        "overlap_report_sha256": sha256_file(args.overlap_report),
        "bfreq_table": bfreq_source,
        "bfreq_table_sha256": bfreq_sha,
        "app_top3_rule": APP_TOP3_RULE,
        "lexicon": "off" if args.no_lexicon else "on",
        "top_k": args.top_k,
        "endpoints": {},
    }
    for endpoint, rows in ((ENDPOINT_G, g_rows), (ENDPOINT_R, r_rows)):
        result = analysis[endpoint]
        failed = sum(1 for row in rows if row["error"])
        results["endpoints"][endpoint] = {
            "description": (
                "glyph input → reading, baseline B-freq"
                if endpoint == ENDPOINT_G
                else "transliteration input → retrieval, baseline word overlap (protocol B)"
            ),
            "declared": len(rows),
            "scored": result.counts.n,
            "failed": failed,
            "app_successes": result.counts.both + result.counts.app_only,
            "baseline_successes": result.counts.both + result.counts.baseline_only,
            "wins": result.counts.app_only,
            "losses": result.counts.baseline_only,
            "ties": result.counts.ties,
            "margin": result.counts.margin,
            "interval": list(result.interval),
            "p_value": result.p_value,
            "p_value_exact": f"{result.p_value_exact.numerator}/{result.p_value_exact.denominator}",
            "holm_threshold": result.holm_threshold,
            "holm_reject": result.holm_reject,
            "beats_baseline": result.beats_baseline,
            "underpowered": result.underpowered,
            "small_n": result.counts.n < SMALL_N,
            "exploratory": sum(1 for row in rows if row["cohort"] == "exploratory"),
            "verdict_line": result.describe(),
        }

    g_sha = write_rows(out_dir / "endpoint_g_lines.csv", G_REPORT_COLUMNS, g_rows)
    r_sha = write_rows(out_dir / "endpoint_r_lines.csv", R_REPORT_COLUMNS, r_rows)
    results["endpoint_g_lines_sha256"] = g_sha
    results["endpoint_r_lines_sha256"] = r_sha
    (out_dir / "summary.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(summarise(results, out_dir))

    failures = sum(block["failed"] for block in results["endpoints"].values())
    if failures:
        print(
            f"{failures} line(s) could not be scored; they are listed with their reason in "
            f"the per-line CSVs and are NOT silently dropped from the record.",
            file=sys.stderr,
        )
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

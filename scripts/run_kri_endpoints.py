"""The KRI endpoint driver: declaration in, per-line and summary results out.

One command ties together everything §4d and §4e ask for, in the order they ask for
it, so that no step can be skipped by accident:

    declaration (validated, sha256 printed)
      -> corpus sha and commit pins
      -> overlap report (§4a), bound by its sidecar to these lines, this corpus and
         this checker code: only `new` lines run; a confirmation line must also be
         excluded by no manifest entry, under a complete manifest
      -> every declared record checked before anything is run (ids unique, gold
         division = glyph input, judgements in the Boolean vocabulary)
      -> endpoint G: the app's paste path -> segmentation -> per-group top 3
           -> the app-segment → gold-span mapping
           -> scripts.bfreq_baseline.score_endpoint_g (the frozen scorer, B-freq)
      -> endpoint R: Camilla's blind judgements, one binary per side per line
      -> per endpoint, on CONFIRMATION lines only: exact sign test + Newcombe
         paired interval; Holm across the family of two, power floor per endpoint
      -> exploratory lines and §4e's secondaries: descriptive counts only
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
* trust an overlap report it cannot tie to the lines file, the corpus and the
  checker code it is given, or run a line the report does not label `new` (§4d:
  "The tool runs only on `new` lines");
* run a confirmation line that any (B) manifest entry covers, or under a manifest
  that is not complete (pending hashes, missing private texts);
* run a confirmation with a B-freq table that is not the frozen one for the declared
  corpus, or with an experimental override (`--build-bfreq`, `--no-lexicon`,
  `--top-k` other than 3);
* start at all if a declared record is missing, duplicated or malformed, or if a gold
  division is not the glyph input it divides — a data-entry error is refused before
  any app call, so no output exists to tempt a second evaluation;
* pool the two endpoints, mix exploratory lines into a confirmatory statistic, or
  report a percentage, an interval or a p-value for fewer than 30 lines (§4d: "case
  by case … no percentages or intervals while n < 30");
* write a verdict for a run with any failed line (an unjudged endpoint-R line): the
  counts are written, the verdict fields are not.

If the app's *own* output drops or changes signs of a correctly divided line, that is
the app not producing those groups, which §4e scores as misses: the line is scored
with every group a miss for the app, flagged `app_sign_mismatch`, and not failed.

The outputs hold ids, counts and numbers — never a KRI line, never a gold reading,
never a glyph. They are still derived from KRI material, so they belong in the
custody directory, not in the repo.

Not built (documented in `docs/kri-official-test-tooling-2026-10-26.md`): endpoint
R's blind pack (both systems' top 3, merged and shuffled), BM25's per-pool
statistics, and clustering by passage. BM25 is reported only as descriptive counts,
when the judgements carry a `bm25_success` column.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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
    LATE_EGYPTIAN,
    BFreqEntry,
    BFreqTable,
    assert_public_path,
    build_table,
    folded_reading_key,
    load_corpus,
    score_endpoint_g,
    score_line,
)
from scripts.check_overlap import checker_sha256  # noqa: E402
from scripts.kri_declaration import (  # noqa: E402
    ENDPOINT_G,
    ENDPOINT_R,
    EXPLORATORY,
    read_declaration,
    validate,
)
from scripts.kri_exclusion_manifest import (  # noqa: E402
    parse_kri_span,
    read_manifest,
    sha256_file,
    validate as validate_manifest,
)
from scripts.kri_overlap import LINES_FILE_COLUMNS  # noqa: E402
from scripts.kri_segment_mapping import (  # noqa: E402
    MappingError,
    alignment_key,
    map_app_segments_to_gold,
)
from scripts.kri_stats import POWER_FLOOR, SMALL_N, PairedCounts, analyse_family  # noqa: E402

#: What counts as "the app's top 3 for that group" — a frozen operational
#: definition, in the order of the app's own per-group view
#: (`app/ui/whyptology_app.py`): the chosen reading — the context-aware Viterbi
#: decode the UI labels "Chosen reading" — then the group's other attested readings
#: in frequency order, truncated to three. The UI lists more alternatives than three,
#: so this is not a copy of the screen; it is the first three of the order a reader
#: of the app sees.
APP_TOP3_RULE = (
    "the app's chosen reading first (ReadingPrediction.predicted, the Viterbi "
    "decode the UI labels 'Chosen reading'), then the group's remaining candidates "
    "in frequency order (ReadingPrediction.candidates), truncated to the top k"
)

#: The one lines file, shared with `scripts/check_overlap.py`.
LINE_COLUMNS = LINES_FILE_COLUMNS
JUDGEMENT_COLUMNS = ("line_id", "app_success", "baseline_success")
#: Optional: BM25's binary outcome per line, judged in the same blind pack (§4e
#: "BM25 is secondary"). Descriptive only, never in the Holm family.
BM25_COLUMN = "bm25_success"

#: The explicit Boolean vocabulary of a judgement. Anything else — including an
#: empty cell — is refused before scoring, never read as a failure.
JUDGEMENT_VALUES = {"1": True, "yes": True, "true": True, "0": False, "no": False, "false": False}

#: The official configuration (§4d/§4e): the shipped app (lexicon on), top 3, the
#: frozen B-freq table. Anything else is an experimental run: allowed for
#: exploratory lines, refused for confirmation lines, and never given a verdict.
OFFICIAL_TOP_K = DEFAULT_TOP_K

#: The freeze record whose table sha256 a confirmation run must match.
BFREQ_DOC = PROJECT_ROOT / "docs" / "kri-bfreq-baseline-2026-10-26.md"
BFREQ_CODE = ("scripts/bfreq_baseline.py", "scripts/build_bfreq_table.py")
BFREQ_PRIMARY = "bfreq_table_all.csv"
BFREQ_LATE = "bfreq_table_late_egyptian.csv"

DEFAULT_MANIFEST = PROJECT_ROOT / "docs" / "kri" / "exclusion-manifest.csv"

G_REPORT_COLUMNS = (
    "declaration_id", "line_id", "cohort", "confirmation", "stage_used", "stage_inferred",
    "gold_groups", "scorable_groups", "placeholder_only_groups", "no_signs_groups",
    "app_segments", "exact", "merged", "split", "partial_overlap", "absent",
    "no_signs", "repeated_sign_strings", "app_sign_mismatch",
    "app_hits", "app_score", "app_success", "baseline_hits", "baseline_score",
    "baseline_success", "app_hits_folded", "baseline_hits_folded",
    "baseline_le_hits", "baseline_le_success", "error",
)
R_REPORT_COLUMNS = (
    "declaration_id", "line_id", "cohort", "confirmation", "app_success",
    "baseline_success", "bm25_success", "judged", "error",
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


def unique_by_line(rows: list[dict], what: str) -> dict[str, dict]:
    """Key rows by `line_id`, refusing an empty or repeated id (by row number)."""
    keyed: dict[str, dict] = {}
    for row_number, row in enumerate(rows, start=2):
        line_id = (row.get("line_id") or "").strip()
        if not line_id:
            raise SystemExit(f"{what}: row {row_number} has no line_id; nothing was run")
        if line_id in keyed:
            raise SystemExit(
                f"{what}: row {row_number} repeats line {line_id}; a later row would "
                f"silently replace an earlier one, so nothing was run"
            )
        row["line_id"] = line_id
        keyed[line_id] = row
    return keyed


def parse_judgement(value: object) -> bool | None:
    """`JUDGEMENT_VALUES`, case-insensitive; `None` for anything else."""
    return JUDGEMENT_VALUES.get(str(value if value is not None else "").strip().lower())


def load_bfreq_table(path: str | Path) -> BFreqTable:
    """Rebuild the frozen B-freq table from its CSV.

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


def recorded_table_sha(name: str, doc: Path = BFREQ_DOC) -> str:
    """The table sha256 the freeze record holds for `name` — the LAST one recorded,
    so an amendment that rebuilds the table on a new corpus supersedes the old."""
    found = re.findall(
        rf"`{re.escape(name)}`\s*\|\s*`([0-9a-f]{{64}})`", doc.read_text(encoding="utf-8")
    )
    return found[-1] if found else ""


def verify_bfreq_table(path: str | Path, corpus_sha: str, *, confirmation: bool) -> dict:
    """Tie a B-freq table to the declared corpus and the frozen code, or refuse.

    The builder writes `bfreq_header.json` beside the tables, with the corpus
    sha256, top k, the code's sha256s and each table's sha256. All of it must agree
    with what this run is given. A confirmation run must additionally use the
    primary table whose sha256 the freeze record holds.
    """
    table_path = Path(path).expanduser()
    header_path = table_path.parent / "bfreq_header.json"
    if not header_path.exists():
        raise SystemExit(
            f"{header_path} not found: a B-freq table is only trusted with the header its "
            f"builder wrote beside it; nothing was run"
        )
    header = json.loads(header_path.read_text(encoding="utf-8"))
    actual = sha256_file(table_path)
    problems = []
    if header.get("corpus_sha256") != corpus_sha:
        problems.append("its header's corpus sha256 is not the declared corpus")
    if (header.get("tables", {}).get(table_path.name) or {}).get("sha256") != actual:
        problems.append("the table's sha256 is not the one its header records")
    if header.get("top_k") != OFFICIAL_TOP_K:
        problems.append(f"it was built for top {header.get('top_k')}, not top {OFFICIAL_TOP_K}")
    for name in BFREQ_CODE:
        if (header.get("module_sha256") or {}).get(name) != sha256_file(PROJECT_ROOT / name):
            problems.append(f"it was built by a {name} other than the frozen one")
    if confirmation:
        if table_path.name != BFREQ_PRIMARY:
            problems.append(f"a confirmation uses {BFREQ_PRIMARY}, the frozen primary table")
        elif actual != recorded_table_sha(BFREQ_PRIMARY):
            problems.append(
                f"its sha256 is not the {BFREQ_PRIMARY} sha256 recorded (or last amended) in "
                f"{BFREQ_DOC.name}"
            )
    if problems:
        raise SystemExit(
            f"the B-freq table {table_path} cannot be used: " + "; ".join(problems)
            + ". Nothing was run."
        )
    return header


def verify_overlap_report(
    report_path: str | Path,
    lines_path: str | Path,
    corpus_sha: str,
    declaration,
    manifest_path: str | Path,
) -> dict:
    """Check the §4a report belongs to these inputs, and that every declared line may
    run. Returns the sidecar. Refuses (SystemExit) on anything else.
    """
    report = Path(report_path).expanduser()
    sidecar_path = report.with_suffix(report.suffix + ".json")
    if not sidecar_path.exists():
        raise SystemExit(
            f"{sidecar_path} not found: an overlap report is only trusted with the sidecar "
            f"scripts/check_overlap.py writes beside it; nothing was run"
        )
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    stale = []
    if sidecar.get("report_sha256") != sha256_file(report):
        stale.append("the report was changed after the checker wrote it")
    if sidecar.get("lines_sha256") != sha256_file(Path(lines_path).expanduser()):
        stale.append("it was made from a different lines file (or the lines changed since)")
    if sidecar.get("examples_sha256") != corpus_sha:
        stale.append("it was made on a different corpus than the declared one")
    if sidecar.get("checker_sha256") != checker_sha256():
        stale.append("it was made by different checker code than this commit's")
    if stale:
        raise SystemExit(
            "the overlap report cannot be used: " + "; ".join(stale)
            + ". Re-run scripts/check_overlap.py; nothing was run."
        )

    rows = unique_by_line(
        read_csv_rows(
            report,
            ("line_id", "label", "runnable", "confirmation_eligible", "excluded_by",
             "kri_reference_checked"),
            "overlap report",
        ),
        "overlap report",
    )
    declared_lines = {run.line_id for run in declaration.runs}
    unchecked = sorted(declared_lines - set(rows))
    if unchecked:
        raise SystemExit(
            f"{len(unchecked)} declared line(s) are not in the overlap report {unchecked}: "
            f"§4d overlap-checks every line first; nothing was run."
        )
    not_runnable = sorted(
        line for line in declared_lines
        if rows[line]["label"] != "new" or rows[line]["runnable"] != "yes"
    )
    if not_runnable:
        raise SystemExit(
            f"{len(not_runnable)} declared line(s) are not runnable {not_runnable}: the "
            f"tool runs only on `new` lines (§4d). A `contained` or `partial` line is "
            f"reported as \"found\", never as \"read\"."
        )

    confirmation_lines = sorted(
        {run.line_id for run in declaration.runs if run.eligible_for_confirmation}
    )
    if confirmation_lines:
        if not sidecar.get("manifest_complete"):
            raise SystemExit(
                "the overlap report was made without a complete exclusion manifest "
                f"({len(sidecar.get('manifest_incomplete_reasons') or [])} problem(s) in its "
                "sidecar): a confirmation needs every hash filled and every excluded text "
                "supplied; nothing was run."
            )
        excluded = sorted(
            line for line in confirmation_lines
            if rows[line]["confirmation_eligible"] != "yes" or rows[line]["excluded_by"].strip()
        )
        if excluded:
            raise SystemExit(
                f"{len(excluded)} confirmation line(s) are covered by the (B) exclusion "
                f"manifest {excluded}: they can never count toward §4e. Declare them "
                f"{EXPLORATORY!r} or drop them; nothing was run."
            )
        unreferenced = sorted(
            line for line in confirmation_lines if rows[line]["kri_reference_checked"] != "yes"
        )
        if unreferenced:
            raise SystemExit(
                f"{len(unreferenced)} confirmation line(s) have no parseable kri_reference "
                f"{unreferenced}, so exclusion by reference was not checked; nothing was run."
            )
        manifest = Path(manifest_path).expanduser()
        if sidecar.get("manifest_sha256") != sha256_file(manifest):
            raise SystemExit(
                f"the overlap report was checked against a different manifest than "
                f"{manifest}; nothing was run."
            )
        problems = validate_manifest(read_manifest(manifest), strict=True)
        if problems:
            raise SystemExit(
                f"{manifest} is not strictly valid ({len(problems)} problem(s)); a "
                f"confirmation needs a complete manifest; nothing was run."
            )
    return sidecar


def precheck_records(declaration, records: dict[str, dict], judgements: dict[str, dict]) -> None:
    """Every declared record, checked before the app is called once.

    A gold division that is not the glyph input it divides is a data-entry error:
    refused here, not discovered after outputs exist. Messages give line ids and
    reasons, never content.
    """
    problems: list[str] = []
    for run in declaration.runs:
        record = records.get(run.line_id)
        if record is None:
            problems.append(f"{run.line_id}: declared but missing from the lines file")
            continue
        if run.eligible_for_confirmation and parse_kri_span(record.get("kri_reference", "")) is None:
            problems.append(f"{run.line_id}: a confirmation line needs a parseable kri_reference")
        if run.endpoint == ENDPOINT_G:
            glyph_input = str(record.get("glyph_input") or "")
            gold_groups = str(record.get("gold_groups") or "").split()
            gold_readings = str(record.get("gold_reading") or "").split()
            if not alignment_key(glyph_input):
                problems.append(f"{run.line_id}: endpoint G needs a glyph_input")
            elif not gold_groups or len(gold_groups) != len(gold_readings):
                problems.append(
                    f"{run.line_id}: {len(gold_groups)} gold groups and {len(gold_readings)} "
                    f"gold readings; §4e needs one reading per group"
                )
            elif alignment_key("".join(gold_groups)) != alignment_key(glyph_input):
                gold, given = alignment_key("".join(gold_groups)), alignment_key(glyph_input)
                first = next(
                    (i for i in range(min(len(gold), len(given))) if gold[i] != given[i]),
                    min(len(gold), len(given)),
                )
                problems.append(
                    f"{run.line_id}: the gold division is not the glyph input it divides "
                    f"({len(gold)} vs {len(given)} signs, first difference at offset {first})"
                )
        else:
            if not str(record.get("query_transliteration") or "").strip():
                problems.append(f"{run.line_id}: endpoint R needs a query_transliteration")
            judgement = judgements.get(run.line_id)
            if judgement is not None:
                for column in JUDGEMENT_COLUMNS[1:] + ((BM25_COLUMN,) if BM25_COLUMN in judgement else ()):
                    if parse_judgement(judgement.get(column)) is None:
                        problems.append(
                            f"{run.line_id}: judgement column {column} is not one of "
                            f"{sorted(JUDGEMENT_VALUES)}"
                        )
    if problems:
        for problem in problems:
            print(f"REFUSED {problem}", file=sys.stderr)
        raise SystemExit(
            f"{len(problems)} declared record(s) are missing or malformed; nothing was run "
            f"and no output was written"
        )


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
    late_table: BFreqTable | None = None,
) -> dict:
    """One endpoint-G line: app paste path → mapping → the frozen scorer.

    `precheck_records` has already established that the gold division is the glyph
    input. If the app's output nevertheless is not that sign string, the app did not
    produce the gold groups: every group is a miss for the app (§4e), the line is
    flagged `app_sign_mismatch`, and it is scored, not failed.
    """
    gold_groups = str(record["gold_groups"]).split()
    gold_readings = str(record["gold_reading"]).split()
    glyph_input = str(record["glyph_input"])
    row: dict[str, object] = {column: "" for column in G_REPORT_COLUMNS}
    row["line_id"] = record["line_id"]

    stage, inferred, segments, candidates = run_app_on_line(resources, glyph_input, top_k)
    row["stage_used"] = stage or "(pooled)"
    row["stage_inferred"] = "yes" if inferred else "no"
    row["app_segments"] = len(segments)

    try:
        mapping = map_app_segments_to_gold(gold_groups, segments, candidates, top_k=top_k)
        app_candidates = mapping.app_candidates
        counts = mapping.counts
        repeated = mapping.repeated_groups
        mismatch = False
    except MappingError:
        app_candidates = [None] * len(gold_groups)
        counts = {name: "" for name in ("exact", "merged", "split", "partial_overlap", "absent", "no_signs")}
        repeated = ""
        mismatch = True

    report, app_score, baseline_score = score_endpoint_g(
        table, gold_groups, gold_readings, app_candidates, top_k=top_k
    )
    baseline_candidates = table.predict_line(gold_groups, top_k=top_k)
    app_folded = score_line(gold_readings, app_candidates, top_k=top_k, key=folded_reading_key)
    baseline_folded = score_line(
        gold_readings, baseline_candidates, top_k=top_k, key=folded_reading_key
    )
    if late_table is not None:
        _report, _app, late_score = score_endpoint_g(
            late_table, gold_groups, gold_readings, app_candidates, top_k=top_k
        )
        row["baseline_le_hits"] = late_score.hits
        row["baseline_le_success"] = "yes" if late_score.success else "no"

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
            "repeated_sign_strings": repeated,
            "app_sign_mismatch": "yes" if mismatch else "no",
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
    """One endpoint-R line: Camilla's blind judgement, one binary per side.

    Values were checked against `JUDGEMENT_VALUES` before the run started. A missing
    judgement is recorded as unjudged — never as a loss — and makes the run
    incomplete, so no verdict is written for it.
    """
    row = {column: "" for column in R_REPORT_COLUMNS}
    row["line_id"] = line_id
    if record is None:
        row["judged"] = "no"
        row["error"] = "no blind judgement supplied for this line"
        return row
    row["judged"] = "yes"
    row["app_success"] = "yes" if parse_judgement(record["app_success"]) else "no"
    row["baseline_success"] = "yes" if parse_judgement(record["baseline_success"]) else "no"
    if BM25_COLUMN in record:
        row["bm25_success"] = "yes" if parse_judgement(record[BM25_COLUMN]) else "no"
    return row


# --------------------------------------------------------------------------- analysis


def _pairs(rows: list[dict], cohort_filter) -> list[tuple[bool, bool]]:
    return [
        (row["app_success"] == "yes", row["baseline_success"] == "yes")
        for row in rows
        if not row["error"] and cohort_filter(row)
    ]


def _k_of_n(pairs: list[tuple[bool, bool]]) -> dict:
    """Descriptive counts only: k of n per side and the discordant pairs."""
    counts = PairedCounts.from_pairs(pairs)
    return {
        "n": counts.n,
        "app_successes": counts.both + counts.app_only,
        "baseline_successes": counts.both + counts.baseline_only,
        "wins": counts.app_only,
        "losses": counts.baseline_only,
        "ties": counts.ties,
    }


def analyse(rows_by_endpoint: dict[str, list[dict]], *, verdict_allowed: bool, why_not: list[str]) -> dict:
    """The per-endpoint result blocks. Pure: no files, no app.

    * The confirmatory statistics use only rows declared `confirmation` that are
      eligible (`confirmation == "yes"`); exploratory rows never enter a p-value, an
      interval, the Holm family or a flag (review round 2026-10-26).
    * The Holm family is always both endpoints, an empty one included (n 0, p 1).
    * Below `SMALL_N` confirmation lines, only k of n is written: no rate, margin,
      interval or p-value (§4d).
    * No verdict field is written at all unless `verdict_allowed` (a complete run in
      the official configuration). Below the power floor the endpoint is
      "uninformative" and `beats_baseline` is false whatever the test says.
    """
    confirm = {
        endpoint: _pairs(rows, lambda row: row["confirmation"] == "yes")
        for endpoint, rows in rows_by_endpoint.items()
    }
    analysis = analyse_family(confirm)
    blocks: dict[str, dict] = {}
    for endpoint, rows in rows_by_endpoint.items():
        result = analysis[endpoint]
        block: dict[str, object] = {
            "declared": len(rows),
            "failed": sum(1 for row in rows if row["error"]),
            "confirmation_declared": sum(1 for row in rows if row["confirmation"] == "yes"),
            "exploratory_declared": sum(1 for row in rows if row["confirmation"] != "yes"),
            "confirmation": _k_of_n(confirm[endpoint]),
            "exploratory": _k_of_n(_pairs(rows, lambda row: row["confirmation"] != "yes")),
            "small_n": result.counts.n < SMALL_N,
            "underpowered": result.underpowered,
        }
        if not verdict_allowed:
            block["verdict_line"] = (
                f"endpoint {endpoint}: no verdict — " + "; ".join(why_not)
                + f". Counts only: {result.describe() if result.small_n else _k_of_n(confirm[endpoint])}"
            )
        elif result.counts.n == 0:
            block["verdict_line"] = f"endpoint {endpoint}: no confirmation lines; no verdict"
        elif result.small_n:
            block["verdict_line"] = result.describe()
        else:
            block.update(
                {
                    "margin": result.counts.margin,
                    "interval": list(result.interval),
                    "p_value": result.p_value,
                    "p_value_exact": f"{result.p_value_exact.numerator}/{result.p_value_exact.denominator}",
                    "holm_threshold": result.holm_threshold,
                    "holm_threshold_exact": (
                        f"{result.holm_threshold_exact.numerator}/"
                        f"{result.holm_threshold_exact.denominator}"
                    ),
                    "holm_reject": result.holm_reject,
                    "beats_baseline": bool(result.beats_baseline and not result.underpowered),
                    "verdict_line": result.describe(),
                }
            )
        blocks[endpoint] = block
    return blocks


def secondary_outputs(g_rows: list[dict], r_rows: list[dict]) -> dict:
    """§4e's descriptive secondaries, outside the Holm family. Counts only."""
    scored_g = [row for row in g_rows if not row["error"]]
    late = [row for row in scored_g if row["baseline_le_success"] in ("yes", "no")]
    judged_bm25 = [row for row in r_rows if row["bm25_success"] in ("yes", "no")]

    def total(column: str) -> int:
        return sum(int(row[column]) for row in scored_g if str(row[column]).strip() != "")

    return {
        "G_group_level_hits": {
            "gold_groups": total("gold_groups"),
            "app_hits": total("app_hits"),
            "baseline_hits": total("baseline_hits"),
            "baseline_le_hits": total("baseline_le_hits") if late else None,
            "app_sign_mismatch_lines": sum(1 for row in scored_g if row["app_sign_mismatch"] == "yes"),
        },
        "G_late_egyptian_bfreq": (
            _k_of_n([(row["app_success"] == "yes", row["baseline_le_success"] == "yes") for row in late])
            if late
            else "not computed (no Late-Egyptian table)"
        ),
        "R_bm25": (
            _k_of_n([(row["app_success"] == "yes", row["bm25_success"] == "yes") for row in judged_bm25])
            if judged_bm25
            else "not supplied (no bm25_success column)"
        ),
        "R_bm25_per_pool": "not built",
    }


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
    lines.append(f"configuration: {results['configuration']}")
    if not results["verdict_allowed"]:
        lines.append(f"**No verdict is given: {'; '.join(results['no_verdict_because'])}.**")
    lines.append("")
    for endpoint in (ENDPOINT_G, ENDPOINT_R):
        block = results["endpoints"][endpoint]
        confirmation, exploratory = block["confirmation"], block["exploratory"]
        lines.append(f"## Endpoint {endpoint} — {block['description']}")
        lines.append("")
        lines.append(
            f"* lines declared: {block['declared']} ({block['confirmation_declared']} "
            f"confirmation, {block['exploratory_declared']} exploratory)"
        )
        if block["failed"]:
            lines.append(f"* **failed lines: {block['failed']}** (see the per-line CSV's `error`)")
        lines.append(f"* confirmatory: {block['verdict_line']}")
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
        if exploratory["n"] or block["exploratory_declared"]:
            lines.append(
                f"* exploratory (descriptive only, never in a test): app {exploratory['app_successes']} "
                f"of {exploratory['n']}, baseline {exploratory['baseline_successes']} of "
                f"{exploratory['n']}; W={exploratory['wins']} L={exploratory['losses']} "
                f"ties={exploratory['ties']}."
            )
            if endpoint == ENDPOINT_G:
                lines.append(
                    "* no endpoint-G number from exploratory lines (material received "
                    "before the B-freq freeze) goes to experts."
                )
        lines.append("")
    secondary = results["secondary"]
    lines.append("## Secondary, descriptive (outside the Holm family)")
    lines.append("")
    lines.append(f"* G group-level hits: {secondary['G_group_level_hits']}")
    lines.append(f"* G vs B-freq restricted to Late Egyptian: {secondary['G_late_egyptian_bfreq']}")
    lines.append(f"* R vs BM25: {secondary['R_bm25']}; per-pool statistics: {secondary['R_bm25_per_pool']}")
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
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="the (B) exclusion manifest")
    parser.add_argument("--bfreq-table", default=None, help="the frozen B-freq table CSV")
    parser.add_argument(
        "--build-bfreq",
        action="store_true",
        help="EXPERIMENTAL: rebuild B-freq from --examples instead of reading the frozen table",
    )
    parser.add_argument("--judgements", default=None, help="endpoint R's blind judgements")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument(
        "--top-k", type=int, default=OFFICIAL_TOP_K, help=f"EXPERIMENTAL unless {OFFICIAL_TOP_K}"
    )
    parser.add_argument(
        "--no-lexicon",
        action="store_true",
        help=(
            "EXPERIMENTAL: read with the corpus alone, without the Helsinki sign-reading "
            "lexicon. The shipped app uses the lexicon; this exists for hermetic tests."
        ),
    )
    args = parser.parse_args(argv)

    # 1. The declaration, and the pins it carries.
    declaration = read_declaration(args.declaration)
    problems = validate(declaration)
    if problems:
        for problem in problems:
            print(f"INVALID {problem}", file=sys.stderr)
        raise SystemExit("the declaration is not valid; nothing was run (§4d)")
    has_confirmation = any(run.eligible_for_confirmation for run in declaration.runs)

    overrides = [
        flag
        for flag, used in (
            ("--build-bfreq", args.build_bfreq),
            ("--no-lexicon", args.no_lexicon),
            (f"--top-k {args.top_k}", args.top_k != OFFICIAL_TOP_K),
        )
        if used
    ]
    if overrides and has_confirmation:
        raise SystemExit(
            f"experimental override(s) {overrides} with confirmation lines declared: a "
            f"confirmation runs only in the frozen configuration (top {OFFICIAL_TOP_K}, "
            f"lexicon on, the frozen B-freq table); nothing was run."
        )
    if not args.build_bfreq and not args.bfreq_table:
        raise SystemExit("one of --bfreq-table or --build-bfreq is required")

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

    # 2. The §4a overlap report, bound to these inputs.
    sidecar = verify_overlap_report(
        args.overlap_report, args.lines, corpus_sha, declaration, args.manifest
    )

    # 3. Inputs, every declared record checked before anything runs.
    records = unique_by_line(read_csv_rows(args.lines, LINE_COLUMNS, "lines file"), "lines file")
    judgements = (
        unique_by_line(read_csv_rows(args.judgements, JUDGEMENT_COLUMNS, "judgements"), "judgements")
        if args.judgements
        else {}
    )
    precheck_records(declaration, records, judgements)

    late_table: BFreqTable | None = None
    if args.build_bfreq:
        corpus_frame = load_corpus(examples_path)
        table = build_table(corpus_frame)
        late_table = build_table(corpus_frame, stage=LATE_EGYPTIAN)
        bfreq_source, bfreq_sha, bfreq_header = f"rebuilt from {examples_path}", "", {}
    else:
        bfreq_header = verify_bfreq_table(args.bfreq_table, corpus_sha, confirmation=has_confirmation)
        table_path = Path(args.bfreq_table).expanduser()
        table = load_bfreq_table(table_path)
        bfreq_source, bfreq_sha = str(table_path), sha256_file(table_path)
        late_path = table_path.parent / BFREQ_LATE
        if late_path.exists() and (bfreq_header.get("tables", {}).get(BFREQ_LATE) or {}).get(
            "sha256"
        ) == sha256_file(late_path):
            late_table = load_bfreq_table(late_path)

    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

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
        record = records[run.line_id]
        if run.endpoint == ENDPOINT_G:
            row = score_g_line(resources, table, record, args.top_k, late_table)
        else:
            row = score_r_line(judgements.get(run.line_id), run.line_id)
        row["declaration_id"] = run.declaration_id
        row["cohort"] = run.cohort
        row["confirmation"] = "yes" if run.eligible_for_confirmation else "no"
        (g_rows if run.endpoint == ENDPOINT_G else r_rows).append(row)

    # 5. The statistics, per endpoint, never pooled, confirmation lines only.
    failures = sum(1 for row in g_rows + r_rows if row["error"])
    why_not = []
    if failures:
        why_not.append(f"{failures} declared line(s) could not be scored, so the run is incomplete")
    if overrides:
        why_not.append(f"experimental configuration {overrides}")
    blocks = analyse(
        {ENDPOINT_G: g_rows, ENDPOINT_R: r_rows}, verdict_allowed=not why_not, why_not=why_not
    )
    blocks[ENDPOINT_G]["description"] = "glyph input → reading, baseline B-freq"
    blocks[ENDPOINT_R]["description"] = (
        "transliteration input → retrieval, baseline word overlap (protocol B)"
    )

    results = {
        "commit": commit,
        "corpus": str(examples_path),
        "corpus_sha256": corpus_sha,
        "declaration": str(Path(args.declaration).expanduser()),
        "declaration_sha256": declaration.sha256(),
        "lines_sha256": sha256_file(Path(args.lines).expanduser()),
        "overlap_report_sha256": sha256_file(Path(args.overlap_report).expanduser()),
        "overlap_checker_sha256": sidecar.get("checker_sha256"),
        "private_sha256": sidecar.get("private_sha256", ""),
        "manifest_sha256": sidecar.get("manifest_sha256", ""),
        "manifest_complete": bool(sidecar.get("manifest_complete")),
        "bfreq_table": bfreq_source,
        "bfreq_table_sha256": bfreq_sha,
        "bfreq_header_corpus_sha256": bfreq_header.get("corpus_sha256", ""),
        "app_top3_rule": APP_TOP3_RULE,
        "lexicon": "off" if args.no_lexicon else "on",
        "top_k": args.top_k,
        "configuration": "experimental " + " ".join(overrides) if overrides else "official",
        "run_complete": not failures,
        "verdict_allowed": not why_not,
        "no_verdict_because": why_not,
        "endpoints": blocks,
        "secondary": secondary_outputs(g_rows, r_rows),
    }

    g_sha = write_rows(out_dir / "endpoint_g_lines.csv", G_REPORT_COLUMNS, g_rows)
    r_sha = write_rows(out_dir / "endpoint_r_lines.csv", R_REPORT_COLUMNS, r_rows)
    results["endpoint_g_lines_sha256"] = g_sha
    results["endpoint_r_lines_sha256"] = r_sha
    (out_dir / "summary.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(summarise(results, out_dir))

    if failures:
        print(
            f"{failures} line(s) could not be scored; they are listed with their reason in "
            f"the per-line CSVs, NOT silently dropped, and no verdict was written.",
            file=sys.stderr,
        )
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

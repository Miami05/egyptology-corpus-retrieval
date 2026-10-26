"""§4a overlap checker: label every KRI line `contained`, `partial` or `new`.

    python -I scripts/check_overlap.py --lines ~/egyptology-private-kri/lines.csv \
        --examples data/processed/examples.csv \
        [--private-dir ~/egyptology-private-kri/standrews] \
        [--manifest docs/kri/exclusion-manifest.csv] \
        --output ~/egyptology-private-kri/overlap-report.csv

    # the gate (and, with the dev corpus, the dev fixture the checker is built on)
    python -I scripts/check_overlap.py --fixture tests/fixtures/overlap_dev_v1.csv \
        --examples tests/fixtures/overlap_dev_corpus.csv

The rules live in `scripts/kri_overlap.py`; this file is the front end, the fixture
runner, and the custody boundary.

Custody (§4b). `--lines` is the one argument that may point into
`~/egyptology-private-kri/`, and it is never written back, echoed or copied: the
report holds `line_id`s, labels, predicate names, corpus witnesses and Jaccard
values — no transliteration, no signs, no KRI text of any kind. `--examples` is
guarded by `scripts.bfreq_baseline.assert_public_path`, so the public corpus can
never be read out of the custody directory by a slip of the shell.

Fixtures (§4a "Timing"). Two fixtures, one mechanism:

* the **dev fixture** (`tests/fixtures/overlap_dev_v1.csv`, against the synthetic
  `tests/fixtures/overlap_dev_corpus.csv`) is what the checker may be developed and
  fixed against. It is synthetic by construction, so no gate row can leak into it.
* the **gate fixture** is drawn from the real gate corpus G *after* the part-3
  commit, adjudicated independently by two reviewers, and frozen with G's sha256 in
  its own `corpus_sha` column. The runner refuses to score it against any other
  corpus: §4a retires a fixture whose corpus changed, and a gate that quietly ran on
  a different corpus would be no gate at all.

**No tuning on the gate fixture.** A failed gate is fixed against the dev fixture;
the failed gate fixture is retired to dev and a new one is drawn with a new seed.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bfreq_baseline import assert_public_path  # noqa: E402
from scripts.kri_exclusion_manifest import Manifest, read_manifest, sha256_file  # noqa: E402
from scripts.kri_overlap import (  # noqa: E402
    CORPUS_COLUMNS,
    LINE_COLUMNS,
    LineResult,
    check_lines,
    prepare_corpus,
    prepare_lines,
)

#: The file the private corpus contributes to G (§4a: "With `--private-dir`, G also
#: includes `standrews.csv` at a recorded sha256"). Exactly this name, exactly this
#: file — the allowlist of §4b, in code.
PRIVATE_FILE = "standrews.csv"

#: The gate fixture's columns. `expected_predicates` is the adjudicated set; an
#: empty value means the stratum fixed only the label (the UD spread stratum).
FIXTURE_COLUMNS = (
    "stratum",
    "line_id",
    "transliteration",
    "hieroglyphs",
    "expected_label",
    "expected_predicates",
    "witness_key",
    "max_jaccard",
    "corpus_sha",
    "private_sha",
)

REPORT_COLUMNS = (
    "line_id",
    "label",
    "runnable",
    "predicates_fired",
    "evidence",
    "max_jaccard",
    "max_jaccard_witness",
    "nearest_ramses_jaccard",
    "nearest_ramses_witness",
    "excluded_by",
    "rows_checked",
)


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        return "unknown"


def read_corpus(path: str | Path) -> pd.DataFrame:
    """Read a corpus CSV, keeping only the columns the predicates need."""
    checked = assert_public_path(path, what="corpus")
    frame = pd.read_csv(checked, dtype=str, keep_default_na=False)
    missing = [c for c in ("transliteration_gold",) if c not in frame.columns]
    if missing:
        raise SystemExit(f"{checked}: corpus is missing column(s) {missing}")
    return frame[[c for c in CORPUS_COLUMNS if c in frame.columns]]


def read_lines(path: str | Path) -> list[dict]:
    """Read the lines under test. This path may be the custody directory (§4b)."""
    with open(Path(path).expanduser(), "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "transliteration" not in reader.fieldnames:
            raise SystemExit(
                f"{path}: a --lines file needs columns {list(LINE_COLUMNS)} "
                f"(hieroglyphs may be empty)"
            )
        return [{key: (row.get(key) or "") for key in LINE_COLUMNS} for row in reader]


def corpus_streams(examples: str | Path, private_dir: str | Path | None):
    """The gate corpus G: the public corpus, plus `standrews.csv` when asked for.

    Returns `(stream factory, provenance dict)`. The factory is called once per run
    and yields prepared rows, so nothing larger than one row is held at a time.
    """
    public = read_corpus(examples)
    provenance = {
        "examples": str(Path(examples).expanduser()),
        "examples_sha256": sha256_file(Path(examples).expanduser()),
        "examples_rows": int(len(public)),
        "private_sha256": "",
        "private_rows": 0,
    }
    private = None
    if private_dir:
        private_path = Path(private_dir).expanduser() / PRIVATE_FILE
        if not private_path.exists():
            raise SystemExit(f"{private_path} not found: --private-dir must hold {PRIVATE_FILE}")
        private = pd.read_csv(private_path, dtype=str, keep_default_na=False)
        private = private[[c for c in CORPUS_COLUMNS if c in private.columns]]
        provenance["private_sha256"] = sha256_file(private_path)
        provenance["private_rows"] = int(len(private))

    def stream():
        yield from prepare_corpus(public, label="G")
        if private is not None:
            yield from prepare_corpus(private, label="private")

    return stream, provenance


def apply_manifest(results: list[LineResult], records: list[dict], manifest: Manifest) -> None:
    """Record, per line, which exclusion entries already cover it (§4d/§4e)."""
    by_id = {record["line_id"]: record for record in records}
    for result in results:
        record = by_id.get(result.line_id, {})
        hits = list(manifest.excludes_text(record.get("transliteration", "")))
        hits += [
            entry
            for entry in manifest.excludes_text(record.get("hieroglyphs", ""))
            if entry not in hits
        ]
        result.excluded_by = tuple(sorted(entry.entry_id for entry in hits))


def report_rows(results: list[LineResult]) -> list[dict]:
    rows = []
    for result in results:
        rows.append(
            {
                "line_id": result.line_id,
                "label": result.label,
                "runnable": "yes" if result.runnable else "no",
                "predicates_fired": " ".join(result.fired),
                "evidence": "; ".join(
                    result.evidence[p].describe() for p in sorted(result.evidence)
                ),
                "max_jaccard": f"{float(result.max_jaccard):.4f}",
                "max_jaccard_witness": result.max_jaccard_witness,
                "nearest_ramses_jaccard": f"{float(result.nearest_ramses):.4f}",
                "nearest_ramses_witness": result.nearest_ramses_witness,
                "excluded_by": " ".join(result.excluded_by),
                "rows_checked": result.rows_checked,
            }
        )
    return rows


def write_report(results: list[LineResult], path: str | Path, provenance: dict) -> str:
    """Write the per-line report (no KRI text) and a provenance sidecar."""
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REPORT_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(report_rows(results))
    sidecar = out.with_suffix(out.suffix + ".json")
    sidecar.write_text(
        json.dumps({**provenance, "commit": git_commit(), "lines": len(results)}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return sha256_file(out)


# --------------------------------------------------------------------------- fixtures


def read_fixture(path: str | Path) -> list[dict]:
    with open(Path(path).expanduser(), "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in FIXTURE_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"{path}: fixture is missing column(s) {missing}")
        return [dict(row) for row in reader]


def run_fixture(fixture_path: str | Path, examples: str | Path, private_dir: str | None) -> int:
    """Score a fixture and report every row that did not get its expected label."""
    fixture = read_fixture(fixture_path)
    if not fixture:
        raise SystemExit(f"{fixture_path}: empty fixture")

    stream, provenance = corpus_streams(examples, private_dir)
    expected_sha = {row["corpus_sha"].strip() for row in fixture}
    if len(expected_sha) != 1:
        raise SystemExit(f"{fixture_path}: rows disagree about corpus_sha {sorted(expected_sha)}")
    frozen = expected_sha.pop()
    if frozen and frozen != provenance["examples_sha256"]:
        raise SystemExit(
            f"{fixture_path} was frozen on corpus sha256 {frozen}, but --examples is "
            f"{provenance['examples_sha256']}. §4a retires a fixture whose corpus "
            f"changed: re-verify every label on the new sha and draw a new fixture "
            f"with a new seed. The gate is NOT run."
        )
    expected_private = {row.get("private_sha", "").strip() for row in fixture}
    expected_private.discard("")
    if expected_private and provenance["private_sha256"] not in expected_private:
        raise SystemExit(
            f"{fixture_path} was frozen with private sha256 {sorted(expected_private)}, "
            f"got {provenance['private_sha256'] or '(no --private-dir)'}"
        )

    lines = prepare_lines(fixture)
    results = {result.line_id: result for result in check_lines(lines, stream())}

    failures = 0
    for row in fixture:
        result = results[row["line_id"].strip()]
        problems = []
        if result.label != row["expected_label"].strip():
            problems.append(f"label {result.label} != expected {row['expected_label'].strip()}")
        expected_predicates = row["expected_predicates"].split()
        if expected_predicates and list(result.fired) != expected_predicates:
            problems.append(
                f"predicates {' '.join(result.fired) or '(none)'} != expected "
                f"{' '.join(expected_predicates)}"
            )
        mark = "PASS" if not problems else "FAIL"
        failures += bool(problems)
        print(f"[{mark}] {row['stratum']:<22} {result.summary()}")
        for problem in problems:
            print(f"        {problem}")
    print(
        f"\n{len(fixture)} fixture rows, {failures} failed; corpus "
        f"{provenance['examples_rows']} rows, sha256 {provenance['examples_sha256']}"
    )
    if failures:
        print(
            "A gate failure is fixed against the DEV fixture, never by tuning on this "
            "one; this fixture is then retired to dev and a new gate fixture is drawn "
            "with a new seed (§4a).",
            file=sys.stderr,
        )
    return 1 if failures else 0


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lines", help="CSV of the lines under test (may be in custody)")
    parser.add_argument("--examples", required=True, help="the public corpus CSV (gate corpus G)")
    parser.add_argument("--private-dir", default=None, help=f"directory holding {PRIVATE_FILE}")
    parser.add_argument("--manifest", default=None, help="the (B) exclusion manifest")
    parser.add_argument("--output", help="where the per-line report is written")
    parser.add_argument("--fixture", default=None, help="run a dev/gate fixture instead")
    args = parser.parse_args(argv)

    if args.fixture:
        return run_fixture(args.fixture, args.examples, args.private_dir)

    if not args.lines or not args.output:
        parser.error("--lines and --output are required unless --fixture is given")

    records = read_lines(args.lines)
    if not records:
        raise SystemExit(f"{args.lines}: no lines to check")
    stream, provenance = corpus_streams(args.examples, args.private_dir)
    results = check_lines(prepare_lines(records), stream())

    if args.manifest:
        apply_manifest(results, records, read_manifest(args.manifest))
        provenance["manifest"] = str(args.manifest)
        provenance["manifest_sha256"] = sha256_file(args.manifest)

    digest = write_report(results, args.output, provenance)
    for result in results:
        print(result.summary())
        print(
            f"    nearest Ramses row {result.nearest_ramses_witness or '(none)'} "
            f"J={float(result.nearest_ramses):.3f}"
            + (f"; excluded by {' '.join(result.excluded_by)}" if result.excluded_by else "")
        )
    runnable = [r for r in results if r.runnable]
    print(
        f"\n{len(results)} lines: "
        + ", ".join(
            f"{label} {sum(1 for r in results if r.label == label)}"
            for label in ("contained", "partial", "new")
        )
        + f"; {len(runnable)} runnable (new and not excluded)"
    )
    print(f"report {args.output} sha256 {digest}")
    print(
        "Reminder (§4d): `contained` / `partial` lines are reported as \"found\", "
        "never as \"read\"; the tool runs only on `new` lines."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

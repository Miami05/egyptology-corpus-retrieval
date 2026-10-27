"""§4a overlap checker: label every KRI line `contained`, `partial` or `new`.

    python -I scripts/check_overlap.py --lines ~/egyptology-private-kri/lines.csv \
        --examples data/processed/examples.csv \
        [--private-dir ~/egyptology-private-kri/standrews] \
        [--manifest docs/kri/exclusion-manifest.csv \
         --excluded-texts ~/egyptology-private-kri/excluded-texts.csv] \
        --output ~/egyptology-private-kri/overlap-report.csv

`--lines` is the same file `scripts/run_kri_endpoints.py` reads
(`kri_overlap.LINES_FILE_COLUMNS`). Each line is checked through both of its views
(`kri_overlap.LINE_VIEWS`: the gold reading over the glyph input, and endpoint R's
query transliteration) and labelled by the more severe.

    # the gate (and, with the dev corpus, the dev fixture the checker is built on)
    python -I scripts/check_overlap.py --fixture tests/fixtures/overlap_dev_v1.csv \
        --examples tests/fixtures/overlap_dev_corpus.csv

The rules live in `scripts/kri_overlap.py`; this file is the front end, the fixture
runner, and the custody boundary.

Custody (§4b). `--lines` and `--excluded-texts` are the arguments that may point
into `~/egyptology-private-kri/`, and they are never written back, echoed or copied:
the report holds `line_id`s, labels, predicate names, corpus witnesses, manifest
entry ids, word offsets and Jaccard values — no transliteration, no signs, no KRI
text of any kind (a P2 hit reports how many runs are shared and where, never which
words).

Binding (review round 2026-10-26). The sidecar `<report>.json` records the sha256 of
the lines file, the corpus, the private corpus, the manifest and the excluded texts,
the checker's own code and the source of every project function it imports
(`checker_sha256`, `dependency_sources`), whether the manifest is complete, and the
report's own sha256. The driver refuses a report whose sidecar does not match the
files it is given, so a stale or hand-edited report cannot open the gate. `--examples` is
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
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import hashlib  # noqa: E402

from scripts.bfreq_baseline import assert_public_path  # noqa: E402
from scripts.kri_exclusion_manifest import (  # noqa: E402
    ExcludedText,
    Manifest,
    ManifestError,
    completeness_problems,
    parse_kri_spans,
    read_excluded_texts,
    read_manifest,
    sha256_file,
    validate as validate_manifest,
)
from scripts.kri_overlap import (  # noqa: E402
    CONTAINMENT_PREDICATES,
    CORPUS_COLUMNS,
    LINE_VIEWS,
    LINES_FILE_COLUMNS,
    PARTIAL_PREDICATES,
    LineResult,
    check_lines,
    label_for,
    prepare,
    prepare_corpus,
    prepare_lines,
)

#: The code that decides a label or an exclusion. Its combined sha256 is written to
#: every report's sidecar, and the driver refuses a report made by other code.
CHECKER_FILES = (
    "scripts/check_overlap.py",
    "scripts/kri_exclusion_manifest.py",
    "scripts/kri_overlap.py",
)

#: Separates a line id from its view in the internal keys (never written out).
_VIEW_SEP = "\x1f"


#: The checker modules by import name. Anything they import from the project (the
#: app's normalisation and tokenisation, the B-freq sign key, the Jaccard) is a
#: *dependency*: it decides a label too, so its source is part of the fingerprint.
CHECKER_MODULES = (
    "scripts.check_overlap",
    "scripts.kri_exclusion_manifest",
    "scripts.kri_overlap",
)
_PROJECT_PREFIXES = ("app.", "scripts.")


def _is_project_code(obj: object) -> bool:
    module = getattr(obj, "__module__", "") or ""
    return (
        (inspect.isfunction(obj) or inspect.isclass(obj))
        and module.startswith(_PROJECT_PREFIXES)
        and module not in CHECKER_MODULES
    )


def _constant_fingerprint(value: object) -> str | None:
    """A stable text for a module-level constant a dependency reads, or `None`."""
    if isinstance(value, re.Pattern):
        return f"re({value.pattern!r}, {int(value.flags)})"
    if isinstance(value, (set, frozenset)):
        return f"{type(value).__name__}({sorted(repr(item) for item in value)})"
    if isinstance(value, dict):
        return "dict(" + ", ".join(sorted(f"{k!r}: {v!r}" for k, v in value.items())) + ")"
    if isinstance(value, (str, bytes, int, float, bool, tuple, list)) or value is None:
        return repr(value)
    return None


def _code_names(code) -> set[str]:
    names = set(code.co_names)
    for const in code.co_consts:
        if inspect.iscode(const):
            names |= _code_names(const)
    return names


def dependency_sources() -> dict[str, str]:
    """`module.qualname` -> sha256 of the source (or value) of every piece of project
    code the checker modules import, closed transitively over the names it reads.

    Review round 2 (2026-10-26): hashing only `CHECKER_FILES` let a change to, say,
    `app.services.suggestions.strict_reading_key` or `app.data.normalizer.search_fold`
    re-label lines while every old report still matched the fingerprint.
    """
    seeds: list[object] = []
    for module_name in CHECKER_MODULES:
        module = sys.modules.get(module_name)
        if module is None and module_name == "scripts.check_overlap":
            module = sys.modules.get(__name__)  # run as a script
        if module is None:
            __import__(module_name)
            module = sys.modules[module_name]
        seeds.extend(value for value in vars(module).values() if _is_project_code(value))

    found: dict[str, str] = {}
    pending = list(seeds)
    while pending:
        obj = inspect.unwrap(pending.pop())
        key = f"{obj.__module__}.{obj.__qualname__}"
        if key in found:
            continue
        found[key] = hashlib.sha256(inspect.getsource(obj).encode("utf-8")).hexdigest()
        functions = (
            [v for v in vars(obj).values() if inspect.isfunction(v)]
            if inspect.isclass(obj)
            else [obj]
        )
        for function in functions:
            namespace = function.__globals__
            for name in sorted(_code_names(function.__code__)):
                if name not in namespace:
                    continue
                value = namespace[name]
                if _is_project_code(value):
                    pending.append(value)
                elif not inspect.ismodule(value) and not callable(value):
                    text = _constant_fingerprint(value)
                    if text is not None:
                        found[f"{function.__module__}.{name}"] = hashlib.sha256(
                            text.encode("utf-8")
                        ).hexdigest()
    return dict(sorted(found.items()))


def checker_sha256() -> str:
    """One sha256 over the checker's code files, in name order, and over the source
    of every project function they depend on (`dependency_sources`)."""
    digest = hashlib.sha256()
    for name in CHECKER_FILES:
        digest.update(name.encode("utf-8") + b"\n")
        digest.update((PROJECT_ROOT / name).read_bytes())
    for key, source_digest in dependency_sources().items():
        digest.update(f"dep {key} {source_digest}\n".encode("utf-8"))
    return digest.hexdigest()

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
    "confirmation_eligible",
    "predicates_fired",
    "evidence",
    "max_jaccard",
    "max_jaccard_witness",
    "nearest_ramses_jaccard",
    "nearest_ramses_witness",
    "excluded_by",
    "exclusion_evidence",
    "kri_reference_checked",
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
    """Read the shared lines file. This path may be the custody directory (§4b).

    Errors name a row number and a column, never a value.
    """
    with open(Path(path).expanduser(), "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in LINES_FILE_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(
                f"{path}: the lines file needs columns {list(LINES_FILE_COLUMNS)} "
                f"(the same file run_kri_endpoints.py reads); missing {missing}"
            )
        records = [{key: (row.get(key) or "") for key in LINES_FILE_COLUMNS} for row in reader]
    seen: set[str] = set()
    for row_number, record in enumerate(records, start=2):
        line_id = record["line_id"].strip()
        if not line_id:
            raise SystemExit(f"{path}: row {row_number} has no line_id")
        if line_id in seen:
            raise SystemExit(f"{path}: row {row_number} repeats a line_id; a line is one unit")
        seen.add(line_id)
        if not any(record[text].strip() for _view, text, _glyphs in LINE_VIEWS) and not any(
            record[glyphs].strip() for _view, _text, glyphs in LINE_VIEWS
        ):
            raise SystemExit(f"{path}: row {row_number} carries nothing to check")
        record["line_id"] = line_id
    return records


def line_views(records: list[dict]) -> list[dict]:
    """One checkable record per (line, view) that has any text, keyed internally."""
    views = []
    for record in records:
        for view, text_column, glyph_column in LINE_VIEWS:
            if record[text_column].strip() or record[glyph_column].strip():
                views.append(
                    {
                        "line_id": f"{record['line_id']}{_VIEW_SEP}{view}",
                        "transliteration": record[text_column],
                        "hieroglyphs": record[glyph_column],
                    }
                )
    return views


def merge_views(view_results: list[LineResult], records: list[dict]) -> list[LineResult]:
    """Fold each line's per-view results into one: the most severe label wins.

    Per predicate the witness with the highest Jaccard is kept, as `check_lines` does
    within one view, so the merged evidence is what a single view would have shown.
    """
    merged = {record["line_id"]: LineResult(line_id=record["line_id"]) for record in records}
    for result in view_results:
        line_id = result.line_id.split(_VIEW_SEP, 1)[0]
        target = merged[line_id]
        target.rows_checked = max(target.rows_checked, result.rows_checked)
        if result.max_jaccard > target.max_jaccard:
            target.max_jaccard, target.max_jaccard_witness = (
                result.max_jaccard,
                result.max_jaccard_witness,
            )
        if result.nearest_ramses_witness and (
            not target.nearest_ramses_witness or result.nearest_ramses > target.nearest_ramses
        ):
            target.nearest_ramses, target.nearest_ramses_witness = (
                result.nearest_ramses,
                result.nearest_ramses_witness,
            )
        for predicate, evidence in result.evidence.items():
            previous = target.evidence.get(predicate)
            if previous is None or evidence.jaccard > previous.jaccard:
                target.evidence[predicate] = evidence
    for result in merged.values():
        result.label = label_for(result.fired)
    return [merged[record["line_id"]] for record in records]


def check_records(records: list[dict], rows) -> list[LineResult]:
    """§4a over every view of every line, merged per line."""
    return merge_views(check_lines(prepare_lines(line_views(records)), rows), records)


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


#: Which evidence makes an excluded text cover a line: any §4a containment or
#: partial predicate (pinned Jaccard >= 0.5, identical fold, containment, shared
#: word run, shared sign trigrams) and the extra-fold identity. Deliberately wider
#: than a label: an exclusion errs toward excluding.
EXCLUSION_PREDICATES = CONTAINMENT_PREDICATES + PARTIAL_PREDICATES + ("EXTRA_FOLD",)


def apply_manifest(
    results: list[LineResult],
    records: list[dict],
    manifest: Manifest,
    excluded_texts: list[ExcludedText] | None = None,
) -> None:
    """Record, per line, which exclusion entries cover it, and by which route.

    Three routes (see `scripts/kri_exclusion_manifest.py`): the canonical hash of any
    of the line's texts, its KRI reference inside an entry's span, and the §4a
    predicates against each entry's private excluded text.
    """
    by_id = {record["line_id"]: record for record in records}
    views_by_line: dict[str, list] = {}
    for view in prepare_lines(line_views(records)):
        views_by_line.setdefault(view.key.split(_VIEW_SEP, 1)[0], []).append(view)
    prepared_texts = [
        (
            text.entry_id,
            prepare(
                key=f"manifest/{text.entry_id}",
                transliteration=text.transliteration,
                hieroglyphs=text.hieroglyphs,
                source="excluded",
            ),
        )
        for text in (excluded_texts or [])
    ]
    for result in results:
        record = by_id.get(result.line_id, {})
        routes: dict[str, set[str]] = {}
        for column in ("glyph_input", "gold_reading", "query_transliteration"):
            for entry in manifest.excludes_text(record.get(column, "")):
                routes.setdefault(entry.entry_id, set()).add("hash")
        reference = record.get("kri_reference", "")
        result.reference_checked = bool(parse_kri_spans(reference))
        for entry in manifest.excludes_reference(reference):
            routes.setdefault(entry.entry_id, set()).add("reference")
        for entry_id, prepared_text in prepared_texts:
            for view_result in check_lines(views_by_line.get(result.line_id, []), [prepared_text]):
                fired = [p for p in EXCLUSION_PREDICATES if p in view_result.evidence]
                if fired:
                    routes.setdefault(entry_id, set()).update(fired)
        result.excluded_by = tuple(sorted(routes))
        result.exclusion_evidence = tuple(
            f"{entry_id}:{'+'.join(sorted(routes[entry_id]))}" for entry_id in sorted(routes)
        )


def report_rows(results: list[LineResult]) -> list[dict]:
    rows = []
    for result in results:
        rows.append(
            {
                "line_id": result.line_id,
                "label": result.label,
                "runnable": "yes" if result.runnable else "no",
                "confirmation_eligible": "yes" if result.confirmation_eligible else "no",
                "predicates_fired": " ".join(result.fired),
                "evidence": "; ".join(
                    result.evidence[p].describe() for p in sorted(result.evidence)
                ),
                "max_jaccard": f"{float(result.max_jaccard):.4f}",
                "max_jaccard_witness": result.max_jaccard_witness,
                "nearest_ramses_jaccard": f"{float(result.nearest_ramses):.4f}",
                "nearest_ramses_witness": result.nearest_ramses_witness,
                "excluded_by": " ".join(result.excluded_by),
                "exclusion_evidence": " ".join(result.exclusion_evidence),
                "kri_reference_checked": "yes" if result.reference_checked else "no",
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
    digest = sha256_file(out)
    sidecar = out.with_suffix(out.suffix + ".json")
    sidecar.write_text(
        json.dumps(
            {
                **provenance,
                "commit": git_commit(),
                "checker_sha256": checker_sha256(),
                "lines": len(results),
                "report_sha256": digest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return digest


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
    if not frozen:
        raise SystemExit(
            f"{fixture_path}: corpus_sha is empty. A fixture is frozen on one corpus "
            f"(§4a); without its sha256 it would run on any corpus. The gate is NOT run."
        )
    if frozen != provenance["examples_sha256"]:
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
    parser.add_argument(
        "--excluded-texts",
        default=None,
        help="private (custody) CSV of each manifest entry's text: entry_id, "
        "transliteration, hieroglyphs; bound to the manifest by sha256",
    )
    parser.add_argument("--output", help="where the per-line report is written")
    parser.add_argument("--fixture", default=None, help="run a dev/gate fixture instead")
    args = parser.parse_args(argv)

    if args.fixture:
        return run_fixture(args.fixture, args.examples, args.private_dir)

    if not args.lines or not args.output:
        parser.error("--lines and --output are required unless --fixture is given")

    if args.excluded_texts and not args.manifest:
        parser.error("--excluded-texts binds to a manifest: pass --manifest too")

    records = read_lines(args.lines)
    if not records:
        raise SystemExit(f"{args.lines}: no lines to check")
    stream, provenance = corpus_streams(args.examples, args.private_dir)
    provenance["lines_sha256"] = sha256_file(Path(args.lines).expanduser())
    results = check_records(records, stream())

    provenance.update(
        {
            "manifest": "",
            "manifest_sha256": "",
            "excluded_texts_sha256": "",
            "manifest_complete": False,
            "manifest_incomplete_reasons": ["no --manifest"],
        }
    )
    if args.manifest:
        try:
            manifest = read_manifest(args.manifest)
            problems = validate_manifest(manifest)
            if problems:
                for problem in problems:
                    print(f"INVALID {problem}", file=sys.stderr)
                raise SystemExit(f"{args.manifest}: the manifest is not valid; nothing was checked")
            texts = (
                read_excluded_texts(args.excluded_texts, manifest) if args.excluded_texts else None
            )
        except ManifestError as error:
            raise SystemExit(f"error: {error}")
        apply_manifest(results, records, manifest, texts)
        incomplete = completeness_problems(manifest, texts)
        provenance.update(
            {
                "manifest": str(args.manifest),
                "manifest_sha256": sha256_file(args.manifest),
                "excluded_texts_sha256": (
                    sha256_file(Path(args.excluded_texts).expanduser()) if args.excluded_texts else ""
                ),
                "manifest_complete": not incomplete,
                # Entry ids and fixed sentences only (see `validate_entry`).
                "manifest_incomplete_reasons": incomplete,
            }
        )

    digest = write_report(results, args.output, provenance)
    for result in results:
        print(result.summary())
        print(
            f"    nearest Ramses row {result.nearest_ramses_witness or '(none)'} "
            f"J={float(result.nearest_ramses):.3f}"
            + (f"; excluded by {' '.join(result.excluded_by)}" if result.excluded_by else "")
        )
    runnable = [r for r in results if r.runnable]
    eligible = [r for r in results if r.confirmation_eligible]
    print(
        f"\n{len(results)} lines: "
        + ", ".join(
            f"{label} {sum(1 for r in results if r.label == label)}"
            for label in ("contained", "partial", "new")
        )
        + f"; {len(runnable)} runnable (new), {len(eligible)} confirmation-eligible "
        f"(new and not excluded)"
    )
    if not provenance["manifest_complete"]:
        print(
            "The manifest is not complete (see the sidecar's manifest_incomplete_reasons): "
            "no line of this report can enter a confirmation run."
        )
    print(f"report {args.output} sha256 {digest}")
    print(
        "Reminder (§4d): `contained` / `partial` lines are reported as \"found\", "
        "never as \"read\"; the tool runs only on `new` lines."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

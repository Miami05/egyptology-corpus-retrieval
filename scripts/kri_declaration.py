"""The declaration file: what will be run, fixed before anything is run.

`docs/plan-data-cleanup-2026-10-26.md` §4d:

    **Declared before any run, per line, in `~/egyptology-private-kri/declaration.csv`**
    (its sha256 committed before the first run):
      * the input modality;
      * the endpoint;
      * the stage setting (`--stage auto`);
      * the commit;
      * the corpus sha.
    … There are two pairings:
      * glyph input → reading endpoint …
      * transliteration input → retrieval endpoint …
    A line with both kinds of input gets two declared runs, reported separately.
    **Nothing is re-declared after results.**

and §4e adds that each line's modality and endpoint are declared up front, that the
run is "one evaluation on a pinned commit and a pinned corpus sha", and that endpoint
G on material which arrived before the B-freq freeze is **exploratory** — a
confirmation needs a cohort that arrives afterwards
(`docs/kri-bfreq-baseline-2026-10-26.md`, freeze statement).

This module is the schema, the validator and the template generator. It never writes
into the custody directory: `template` writes an empty, headers-only file to a path
you name, and you move or fill it yourself.

    python -I scripts/kri_declaration.py template --output /tmp/declaration.csv
    python -I scripts/kri_declaration.py validate --declaration ~/egyptology-private-kri/declaration.csv

`validate` prints the sha256 that §4d says must be committed before the first run,
and refuses a file that is not internally consistent — one commit, one corpus sha,
one row per (line, endpoint), `--stage auto` throughout, the two pairings only, and
no Egyptian text in any field (the declaration is private, but its sha256 and its
counts are quoted in public, and a field that can hold a line will eventually hold
one).
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import contains_hieroglyphs  # noqa: E402
from app.services.suggestions import has_egyptological_letters  # noqa: E402
from scripts.kri_exclusion_manifest import sha256_file  # noqa: E402

DECLARATION_COLUMNS = (
    "declaration_id",
    "line_id",
    "input_modality",
    "endpoint",
    "stage",
    "cohort",
    "material_received",
    "declared_on",
    "commit",
    "corpus_sha256",
    "notes",
)

#: §4d's two pairings, and only these. A line with both kinds of input is two rows.
ENDPOINT_G = "G"
ENDPOINT_R = "R"
PAIRINGS = {
    "glyphs": ENDPOINT_G,  # glyph input  → reading endpoint (top-3 readings)
    "transliteration": ENDPOINT_R,  # transliteration input → retrieval endpoint
}
ENDPOINTS = (ENDPOINT_G, ENDPOINT_R)

#: §4d: "the stage setting (`--stage auto`)". One value, declared, not an option.
REQUIRED_STAGE = "auto"

EXPLORATORY = "exploratory"
CONFIRMATION = "confirmation"
COHORTS = (EXPLORATORY, CONFIRMATION)

#: The B-freq freeze (`docs/kri-bfreq-baseline-2026-10-26.md`): code committed
#: 2026-10-26 08:37:08 +01:00, after the KRI PDFs were received the same morning.
#: §4e wants the freeze *before the material arrives*, so material received on or
#: before this date can only be exploratory for endpoint G; a G confirmation needs a
#: cohort that arrived strictly later.
FREEZE_DATE = "2026-10-26"

#: §4e: "about 150 lines of this endpoint", judged separately per endpoint.
POWER_FLOOR = 150

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DeclarationError(ValueError):
    """The declaration is malformed, inconsistent, or carries text it must not."""


@dataclass(frozen=True)
class DeclaredRun:
    declaration_id: str
    line_id: str
    input_modality: str
    endpoint: str
    stage: str
    cohort: str
    material_received: str
    declared_on: str
    commit: str
    corpus_sha256: str
    notes: str = ""

    @property
    def eligible_for_confirmation(self) -> bool:
        """Endpoint G on pre-freeze material is exploratory, whatever it says."""
        if self.cohort != CONFIRMATION:
            return False
        if self.endpoint != ENDPOINT_G:
            return True
        return self.material_received > FREEZE_DATE

    def as_row(self) -> dict[str, str]:
        return {column: getattr(self, column) for column in DECLARATION_COLUMNS}


@dataclass
class Declaration:
    runs: list[DeclaredRun] = field(default_factory=list)
    path: Path | None = None

    def for_endpoint(self, endpoint: str) -> list[DeclaredRun]:
        return [run for run in self.runs if run.endpoint == endpoint]

    @property
    def commit(self) -> str:
        return self.runs[0].commit if self.runs else ""

    @property
    def corpus_sha256(self) -> str:
        return self.runs[0].corpus_sha256 if self.runs else ""

    def counts(self) -> dict[str, int]:
        return {endpoint: len(self.for_endpoint(endpoint)) for endpoint in ENDPOINTS}

    def underpowered(self) -> dict[str, bool]:
        """§4e: below its own floor an endpoint is reported "uninformative"."""
        return {endpoint: count < POWER_FLOOR for endpoint, count in self.counts().items()}

    def sha256(self) -> str:
        if self.path is None:
            raise DeclarationError("this declaration was not read from a file")
        return sha256_file(self.path)


def _dirty_fields(run: DeclaredRun) -> list[str]:
    return [
        column
        for column in ("line_id", "notes", "declaration_id")
        if contains_hieroglyphs(getattr(run, column))
        or has_egyptological_letters(getattr(run, column))
    ]


def validate_run(run: DeclaredRun) -> list[str]:
    """Every problem with one declared run. Empty list = valid.

    Messages name the field and, where it helps, the allowed values — never the
    field's own content: a malformed field may be exactly where a line was pasted by
    mistake, and these messages go to the terminal (review round 2026-10-26).
    """
    problems: list[str] = []
    if not run.declaration_id.strip():
        problems.append("declaration_id is empty")
    if not run.line_id.strip():
        problems.append("line_id is empty")
    if run.input_modality not in PAIRINGS:
        problems.append(f"input_modality is not one of {sorted(PAIRINGS)}")
    elif PAIRINGS[run.input_modality] != run.endpoint:
        # input_modality is from PAIRINGS here, so naming it echoes no free text.
        problems.append(
            f"§4d pairs {run.input_modality} input with endpoint "
            f"{PAIRINGS[run.input_modality]}, not the endpoint declared; a line with both "
            f"kinds of input gets two declared runs"
        )
    elif run.endpoint not in ENDPOINTS:
        problems.append(f"endpoint is not one of {list(ENDPOINTS)}")
    if run.stage != REQUIRED_STAGE:
        problems.append(f"stage must be {REQUIRED_STAGE!r} (§4d)")
    if run.cohort not in COHORTS:
        problems.append(f"cohort is not one of {list(COHORTS)}")
    if not _ISO_DATE.match(run.material_received):
        problems.append("material_received is not an ISO date")
    if not _ISO_DATE.match(run.declared_on):
        problems.append("declared_on is not an ISO date")
    if not _HEX40.match(run.commit):
        problems.append("commit is not a 40-character sha")
    if not _HEX64.match(run.corpus_sha256):
        problems.append("corpus_sha256 is not a sha256")
    if (
        run.cohort == CONFIRMATION
        and run.endpoint == ENDPOINT_G
        and _ISO_DATE.match(run.material_received)
        and run.material_received <= FREEZE_DATE
    ):
        problems.append(
            f"endpoint G material received {run.material_received} is not eligible for a "
            f"confirmation: the B-freq freeze is dated {FREEZE_DATE} and §4e requires the "
            f"freeze before the material arrives. Declare it {EXPLORATORY!r}."
        )
    dirty = _dirty_fields(run)
    if dirty:
        problems.append(
            f"{', '.join(dirty)} contains hieroglyphs or Egyptological letters: the "
            f"declaration records ids and settings, never the line itself"
        )
    return problems


def validate(declaration: Declaration) -> list[str]:
    """Every problem with the whole declaration, row problems prefixed by id."""
    problems: list[str] = []
    if not declaration.runs:
        return ["the declaration is empty: there is nothing declared to run"]
    seen_ids: set[str] = set()
    seen_pairs: dict[tuple[str, str], int] = {}
    for row_number, run in enumerate(declaration.runs, start=2):
        # Rows are named by their line in the file (the header is line 1), never by a
        # field's content.
        label = f"row {row_number}"
        problems.extend(f"{label}: {p}" for p in validate_run(run))
        if run.declaration_id in seen_ids:
            problems.append(f"{label}: duplicate declaration_id")
        seen_ids.add(run.declaration_id)
        pair = (run.line_id, run.endpoint)
        if pair in seen_pairs:
            endpoint = run.endpoint if run.endpoint in ENDPOINTS else "(invalid)"
            problems.append(
                f"{label}: the line of row {seen_pairs[pair]} is declared twice for endpoint "
                f"{endpoint}; one line is one unit per endpoint (§4e)"
            )
        seen_pairs.setdefault(pair, row_number)
    commits = {run.commit for run in declaration.runs}
    if len(commits) > 1:
        problems.append(
            f"the declaration pins {len(commits)} different commits; "
            f"§4e allows one evaluation on one pinned commit"
        )
    shas = {run.corpus_sha256 for run in declaration.runs}
    if len(shas) > 1:
        problems.append(
            f"the declaration pins {len(shas)} different corpus sha256s; §4e allows one"
        )
    return problems


# --------------------------------------------------------------------------- file i/o


def read_declaration(path: str | Path) -> Declaration:
    resolved = Path(path).expanduser()
    with open(resolved, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != DECLARATION_COLUMNS:
            raise DeclarationError(
                f"declaration header is {reader.fieldnames}, expected "
                f"{list(DECLARATION_COLUMNS)}"
            )
        runs = [
            DeclaredRun(
                **{column: (row.get(column) or "").strip() for column in DECLARATION_COLUMNS}
            )
            for row in reader
        ]
    return Declaration(runs=runs, path=resolved)


def write_declaration(declaration: Declaration, path: str | Path) -> str:
    """Write a declaration deterministically and return its sha256."""
    resolved = Path(path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with open(resolved, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(DECLARATION_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(run.as_row() for run in declaration.runs)
    return sha256_file(resolved)


HELP_LINES = (
    "declaration_id   unique id of one declared run, e.g. KRI_01_G",
    "line_id          the line, as it is named in the private lines file",
    f"input_modality   one of {sorted(PAIRINGS)}",
    "endpoint         G (glyph input -> reading) or R (transliteration -> retrieval)",
    f"stage            always {REQUIRED_STAGE!r} (§4d)",
    f"cohort           {EXPLORATORY} or {CONFIRMATION}; G material received on or before "
    f"{FREEZE_DATE} can only be {EXPLORATORY}",
    "material_received  ISO date the material for this line arrived",
    "declared_on      ISO date this row was written — before the run",
    "commit           the 40-character commit the run is pinned to",
    "corpus_sha256    sha256 of data/processed/examples.csv as run",
    "notes            free text; never the line itself",
)


# --------------------------------------------------------------------------- CLI


def _cmd_template(args: argparse.Namespace) -> int:
    path = Path(args.output).expanduser()
    if path.exists() and not args.force:
        print(f"{path} exists; pass --force to overwrite", file=sys.stderr)
        return 2
    digest = write_declaration(Declaration(), path)
    print(f"wrote empty declaration template {path}")
    print(f"sha256 of the empty template {digest}")
    print("\ncolumns:")
    for help_line in HELP_LINES:
        print(f"  {help_line}")
    print(
        "\nFill it in the custody directory (~/egyptology-private-kri/declaration.csv), "
        "validate it, and commit the sha256 BEFORE the first run (§4d)."
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    declaration = read_declaration(args.declaration)
    problems = validate(declaration)
    for problem in problems:
        print(f"INVALID {problem}", file=sys.stderr)
    counts = declaration.counts()
    print(f"{len(declaration.runs)} declared runs: " + ", ".join(
        f"endpoint {endpoint} {count}" for endpoint, count in counts.items()
    ))
    for endpoint, under in declaration.underpowered().items():
        if under and counts[endpoint]:
            print(
                f"  endpoint {endpoint}: {counts[endpoint]} lines is below the power floor "
                f"of about {POWER_FLOOR}; §4e reports it as \"uninformative\", and it still "
                f"counts in the Holm family of two"
            )
    exploratory_g = [
        run for run in declaration.for_endpoint(ENDPOINT_G) if run.cohort == EXPLORATORY
    ]
    if exploratory_g:
        print(
            f"  endpoint G: {len(exploratory_g)} of {counts[ENDPOINT_G]} lines are "
            f"exploratory; no exploratory G number goes to experts"
        )
    if declaration.runs and not problems:
        # Echoed only once valid: a 40/64-hex pin cannot carry a line.
        print(f"commit {declaration.commit}  corpus {declaration.corpus_sha256}")
    print(f"declaration sha256 {declaration.sha256()}")
    print("Commit that sha256 before the first run (§4d). Nothing is re-declared after results.")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    template = sub.add_parser("template", help="write an EMPTY template (headers only)")
    template.add_argument("--output", required=True, help="where to write the template")
    template.add_argument("--force", action="store_true")
    template.set_defaults(func=_cmd_template)

    validate_cmd = sub.add_parser("validate", help="check a declaration and print its sha256")
    validate_cmd.add_argument("--declaration", required=True)
    validate_cmd.set_defaults(func=_cmd_validate)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DeclarationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

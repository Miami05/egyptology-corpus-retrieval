"""The (B) exclusion manifest: what may never count toward a KRI confirmation.

Why this exists. `docs/plan-data-cleanup-2026-10-26.md` §4d ends with a permanent
exclusion:

    "every line seen here, its whole passage (KRI vol./page range), and every other
    edition of the same text … go into the (B) exclusion manifest as sha256 +
    reference the day the material arrives. They can never count toward 4e."

and §4e begins by requiring that "the exclusion manifest is committed first,
including the 4d exclusions". A manifest is therefore a *committed* file, and a
committed file may not contain KRI text. What it holds per entry is a **reference**
(a citation, in plain English) and a **sha256** of the excluded text — never the
text, never a fragment of it, never a transliteration of it.

The hash is a one-way fingerprint, so `scripts/check_overlap.py` can ask "is this
line already excluded?" without the manifest ever having carried the line. Hashing is
done here, in this process, from a file the caller names; the hashed string is
canonicalised first (see `HASH_BASES`) so that two editions' spacing and editorial
apparatus do not make one passage look like two.

Commands
--------

    # start a manifest
    python -I scripts/kri_exclusion_manifest.py init --manifest docs/kri/exclusion-manifest.csv

    # add an entry whose hash the lead will fill in later (no text is read)
    python -I scripts/kri_exclusion_manifest.py add \
        --manifest docs/kri/exclusion-manifest.csv \
        --scope passage --reference "KRI II 569 (lines 3-16), Karnak …" \
        --source "KRI PDFs received 2026-10-26" --note "exploratory self-test" --pending

    # add an entry, hashing a private file *in place* (its content is never written out)
    python -I scripts/kri_exclusion_manifest.py add … --text-file ~/egyptology-private-kri/line_07.txt \
        --hash-basis canonical_transliteration

    # check the manifest is well formed, carries no text, and print its sha256
    python -I scripts/kri_exclusion_manifest.py validate --manifest docs/kri/exclusion-manifest.csv

`validate` is the gate: it refuses a manifest whose reference or note contains
hieroglyphs or Egyptological letters, because that is how a line leaks into git one
"helpful" field at a time.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.normalizer import contains_hieroglyphs  # noqa: E402
from app.services.suggestions import (  # noqa: E402
    has_egyptological_letters,
    strict_reading_key,
)
from scripts.bfreq_baseline import sign_key  # noqa: E402

#: Manifest columns, in file order. A reader with only the header must be able to
#: tell what each entry excludes and how its hash was formed.
MANIFEST_COLUMNS = (
    "entry_id",
    "added",
    "scope",
    "reference",
    "hash_basis",
    "sha256",
    "source",
    "note",
)

#: What one entry excludes.
SCOPES = ("line", "passage", "edition")

#: The literal written in `sha256` when the hash is not yet known. It is not a
#: placeholder the tooling may quietly resolve: `validate --strict` fails on it, and
#: `check_overlap` can never match a line against it.
PENDING_HASH = "to-be-filled-by-the-lead"

#: How the hashed string is canonicalised before hashing. Two editions of one
#: passage differ in spacing and editorial apparatus; hashing the raw bytes would
#: make them two different exclusions, which is exactly the leak §4d closes.
HASH_BASES = {
    #: `app.services.suggestions.strict_reading_key` — the app's reading identity.
    "canonical_transliteration": strict_reading_key,
    #: `scripts.bfreq_baseline.sign_key` — the §4a `signs` definition.
    "canonical_glyphs": sign_key,
    #: No hash yet (`PENDING_HASH`).
    "pending": None,
}

#: Prefixed into every hash so a manifest sha can never be confused with a bare
#: sha256 of a file, and so a future change of canonicalisation is visible.
HASH_DOMAIN = "kri-exclusion-v1"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ENTRY_ID = re.compile(r"^EX\d{3,}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ManifestError(ValueError):
    """The manifest is malformed, incomplete, or carries text it must not carry."""


# ---------------------------------------------------------------------------
# hashing
# ---------------------------------------------------------------------------


def content_hash(text: str, *, basis: str) -> str:
    """The sha256 recorded for one excluded line or passage.

    The text is canonicalised by `basis` first and the domain string is prefixed, so
    the digest is reproducible from the rule written in the manifest's own
    `hash_basis` column and from nothing else.
    """
    canonicaliser = HASH_BASES.get(basis)
    if canonicaliser is None:
        raise ManifestError(
            f"hash_basis {basis!r} cannot hash text; expected one of "
            f"{sorted(k for k, v in HASH_BASES.items() if v)}"
        )
    canonical = canonicaliser(text)
    if not canonical:
        raise ManifestError(
            "the text canonicalises to the empty string, so it has no fingerprint "
            f"under hash_basis {basis!r}"
        )
    return hashlib.sha256(f"{HASH_DOMAIN}\n{basis}\n{canonical}".encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    """sha256 of a file's bytes — used for the manifest's own committed digest."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# entries
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestEntry:
    entry_id: str
    added: str
    scope: str
    reference: str
    hash_basis: str
    sha256: str
    source: str = ""
    note: str = ""

    @property
    def pending(self) -> bool:
        return self.sha256 == PENDING_HASH

    def as_row(self) -> dict[str, str]:
        return {column: getattr(self, column) for column in MANIFEST_COLUMNS}


@dataclass
class Manifest:
    entries: list[ManifestEntry] = field(default_factory=list)

    @property
    def hashes(self) -> set[str]:
        """Every real hash in the manifest (a pending entry contributes none)."""
        return {entry.sha256 for entry in self.entries if not entry.pending}

    @property
    def pending_entries(self) -> list[ManifestEntry]:
        return [entry for entry in self.entries if entry.pending]

    def next_entry_id(self) -> str:
        used = [int(entry.entry_id[2:]) for entry in self.entries if _ENTRY_ID.match(entry.entry_id)]
        return f"EX{(max(used) + 1 if used else 1):03d}"

    def excludes_hash(self, digest: str) -> list[ManifestEntry]:
        return [entry for entry in self.entries if not entry.pending and entry.sha256 == digest]

    def excludes_text(self, text: str) -> list[ManifestEntry]:
        """Which entries fingerprint `text`, under each basis the manifest uses."""
        hits: list[ManifestEntry] = []
        for basis in sorted({entry.hash_basis for entry in self.entries} & set(HASH_BASES)):
            if HASH_BASES[basis] is None:
                continue
            try:
                digest = content_hash(text, basis=basis)
            except ManifestError:
                continue
            hits.extend(
                entry for entry in self.excludes_hash(digest) if entry.hash_basis == basis
            )
        return hits


def _text_fields_are_clean(entry: ManifestEntry) -> list[str]:
    """Which free-text fields look like they carry Egyptian rather than a citation."""
    bad: list[str] = []
    for column in ("reference", "source", "note"):
        value = getattr(entry, column)
        if contains_hieroglyphs(value) or has_egyptological_letters(value):
            bad.append(column)
    return bad


def validate_entry(entry: ManifestEntry, *, strict: bool = False) -> list[str]:
    """Every problem with one entry, as plain sentences. Empty list = valid."""
    problems: list[str] = []
    if not _ENTRY_ID.match(entry.entry_id):
        problems.append(f"entry_id {entry.entry_id!r} is not of the form EX001")
    if not _ISO_DATE.match(entry.added):
        problems.append(f"added {entry.added!r} is not an ISO date (YYYY-MM-DD)")
    if entry.scope not in SCOPES:
        problems.append(f"scope {entry.scope!r} is not one of {list(SCOPES)}")
    if not entry.reference.strip():
        problems.append("reference is empty: an exclusion with no citation excludes nothing")
    if entry.hash_basis not in HASH_BASES:
        problems.append(f"hash_basis {entry.hash_basis!r} is not one of {sorted(HASH_BASES)}")
    if entry.pending:
        if entry.hash_basis != "pending":
            problems.append("a pending hash must carry hash_basis 'pending'")
        if strict:
            problems.append(
                f"sha256 is still {PENDING_HASH!r}: the lead must fill it in before a run"
            )
    elif not _HEX64.match(entry.sha256):
        problems.append(
            f"sha256 {entry.sha256!r} is neither 64 lower-case hex digits nor {PENDING_HASH!r}"
        )
    elif entry.hash_basis == "pending":
        problems.append("hash_basis 'pending' but a hash is present; name the basis used")
    dirty = _text_fields_are_clean(entry)
    if dirty:
        problems.append(
            f"{', '.join(dirty)} contains hieroglyphs or Egyptological letters: the "
            f"manifest records references and hashes, never text (§4d)"
        )
    return problems


def validate(manifest: Manifest, *, strict: bool = False) -> list[str]:
    """Every problem with the whole manifest, entry problems prefixed by entry id."""
    problems: list[str] = []
    seen: set[str] = set()
    for entry in manifest.entries:
        problems.extend(f"{entry.entry_id}: {problem}" for problem in validate_entry(entry, strict=strict))
        if entry.entry_id in seen:
            problems.append(f"{entry.entry_id}: duplicate entry_id")
        seen.add(entry.entry_id)
    return problems


# ---------------------------------------------------------------------------
# file i/o
# ---------------------------------------------------------------------------


def read_manifest(path: str | Path) -> Manifest:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != MANIFEST_COLUMNS:
            raise ManifestError(
                f"manifest header is {reader.fieldnames}, expected {list(MANIFEST_COLUMNS)}"
            )
        entries = [
            ManifestEntry(**{column: (row.get(column) or "").strip() for column in MANIFEST_COLUMNS})
            for row in reader
        ]
    return Manifest(entries=entries)


def write_manifest(manifest: Manifest, path: str | Path) -> str:
    """Write the manifest deterministically and return its sha256.

    `\\n` line endings and no platform-dependent quoting, because the digest this
    returns is what §4e has committed before a run.
    """
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MANIFEST_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(entry.as_row() for entry in manifest.entries)
    return sha256_file(path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    if path.exists() and not args.force:
        print(f"{path} exists; pass --force to overwrite", file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = write_manifest(Manifest(), path)
    print(f"wrote empty manifest {path}\nsha256 {digest}")
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    manifest = read_manifest(path) if path.exists() else Manifest()

    if args.pending:
        basis, digest = "pending", PENDING_HASH
    elif args.sha256:
        basis, digest = args.hash_basis, args.sha256.strip().lower()
    elif args.text_file:
        basis = args.hash_basis
        # Read, hash, drop. The text never reaches the manifest, stdout or a variable
        # that outlives this call.
        digest = content_hash(Path(args.text_file).expanduser().read_text(encoding="utf-8"), basis=basis)
    else:
        print("one of --pending, --sha256 or --text-file is required", file=sys.stderr)
        return 2

    entry = ManifestEntry(
        entry_id=args.entry_id or manifest.next_entry_id(),
        added=args.added,
        scope=args.scope,
        reference=args.reference,
        hash_basis=basis,
        sha256=digest,
        source=args.source,
        note=args.note,
    )
    problems = validate_entry(entry)
    if problems:
        for problem in problems:
            print(f"refused: {problem}", file=sys.stderr)
        return 1
    manifest.entries.append(entry)
    file_digest = write_manifest(manifest, path)
    print(f"added {entry.entry_id} ({entry.scope}) to {path}")
    print(f"manifest sha256 {file_digest}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    manifest = read_manifest(path)
    problems = validate(manifest, strict=args.strict)
    for problem in problems:
        print(f"INVALID {problem}", file=sys.stderr)
    pending = manifest.pending_entries
    print(f"{len(manifest.entries)} entries, {len(pending)} with a pending hash")
    for entry in pending:
        print(f"  pending: {entry.entry_id}  {entry.reference}")
    print(f"manifest sha256 {sha256_file(path)}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="write an empty manifest (headers only)")
    init.add_argument("--manifest", required=True)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=_cmd_init)

    add = sub.add_parser("add", help="append one exclusion entry")
    add.add_argument("--manifest", required=True)
    add.add_argument("--scope", required=True, choices=list(SCOPES))
    add.add_argument("--reference", required=True, help="citation only — never text")
    add.add_argument("--added", default="", help="ISO date; defaults to today")
    add.add_argument("--source", default="")
    add.add_argument("--note", default="")
    add.add_argument("--entry-id", default="")
    add.add_argument("--hash-basis", default="canonical_transliteration", choices=sorted(HASH_BASES))
    group = add.add_mutually_exclusive_group()
    group.add_argument("--sha256", default="", help="a digest computed elsewhere")
    group.add_argument("--text-file", default="", help="hash this file's text here, in place")
    group.add_argument("--pending", action="store_true", help="record the reference, hash later")
    add.set_defaults(func=_cmd_add)

    validate_cmd = sub.add_parser("validate", help="check the manifest and print its sha256")
    validate_cmd.add_argument("--manifest", required=True)
    validate_cmd.add_argument(
        "--strict", action="store_true", help="also fail on an entry whose hash is still pending"
    )
    validate_cmd.set_defaults(func=_cmd_validate)

    args = parser.parse_args(argv)
    if getattr(args, "added", None) == "":
        from datetime import date

        args.added = date.today().isoformat()
    try:
        return args.func(args)
    except ManifestError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

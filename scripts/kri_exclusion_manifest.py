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
"helpful" field at a time. Its messages name the entry and the field, never the
field's content.

How an entry excludes a line (review round 2026-10-26)
------------------------------------------------------

§4e's exclusion checks are "pinned Jaccard >= 0.5, identical fold, same text, edition
link". An exact hash alone catches only an identical canonical text, so an entry now
excludes a line by any of three routes, all reported by entry id:

* **hash** — the line's canonical text has the entry's sha256 (`excludes_text`);
* **reference** — any KRI span cited in the line's `kri_reference` falls inside any
  KRI span cited in the entry's reference (`excludes_reference`; `parse_kri_spans`
  reads *every* `KRI <vol> <page>…` citation in a field, not only the leading one, and
  `validate --strict` requires every entry's reference to carry one);
* **edition link** — an entry of scope `edition` relates references: it cites the
  other edition(s) of an excluded passage, either as further KRI spans or by naming
  the excluded entry's id (`EX001`). A line that falls in any span of a linked group
  is excluded by every entry of that group (review round 2, 2026-10-26), so a second
  edition of an excluded passage can never be a confirmation line;
* **text** — the §4a predicates C1-C4/P1-P3 (pinned Jaccard >= 0.5, identical fold,
  containment, shared word run, shared sign trigrams) fire between the line and the
  entry's excluded text, which lives in a *private* file in custody
  (`read_excluded_texts`) and is bound to the committed entry by its sha256. This is
  what catches a subsection of an excluded passage, a near-twin, and another edition.

A manifest is **complete** (`completeness_problems`) only when it is strictly valid
and every entry has its private text: only then can a run be a confirmation.
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

#: The citation grammar both the manifest's `reference` and a lines file's
#: `kri_reference` are read with: `KRI <volume> <page>[-<page>]`, optionally followed
#: by `(line n)`, `(lines a-b)` or `, line n`. Anything after it is free text.
_KRI_SPAN = re.compile(
    r"^\s*KRI\s+(?P<vol>[IVXLC]+)\s+(?P<p1>\d+)(?:\s*[-–]\s*(?P<p2>\d+))?"
    r"(?:\s*(?:,|\()\s*lines?\s+(?P<l1>\d+)(?:\s*[-–]\s*(?P<l2>\d+))?\)?)?"
)

#: The same grammar, unanchored: every citation in a field. Each citation must carry
#: its own `KRI` prefix ("KRI II 569 = KRI VII 45", not "KRI II 569 = VII 45").
_KRI_SPAN_ANYWHERE = re.compile(
    r"\bKRI\s+(?P<vol>[IVXLC]+)\s+(?P<p1>\d+)(?:\s*[-–]\s*(?P<p2>\d+))?"
    r"(?:\s*(?:,|\()\s*lines?\s+(?P<l1>\d+)(?:\s*[-–]\s*(?P<l2>\d+))?\)?)?"
)
#: An entry id named inside an `edition` entry's reference: the link to the entry it
#: is another edition of.
_ENTRY_LINK = re.compile(r"\bEX\d{3,}\b")

#: The private excluded-text file's columns (custody only, never committed).
EXCLUDED_TEXT_COLUMNS = ("entry_id", "transliteration", "hieroglyphs")
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
# references
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KriSpan:
    """A KRI citation: volume, page range, optional line range."""

    volume: str
    page_start: int
    page_end: int
    line_start: int | None = None
    line_end: int | None = None


def _span_from_match(match: re.Match) -> KriSpan | None:
    p1 = int(match["p1"])
    p2 = int(match["p2"]) if match["p2"] else p1
    l1 = int(match["l1"]) if match["l1"] else None
    l2 = int(match["l2"]) if match["l2"] else l1
    if p2 < p1 or (l1 is not None and l2 < l1):
        return None
    return KriSpan(match["vol"], p1, p2, l1, l2)


def parse_kri_span(text: str) -> KriSpan | None:
    """Read a *leading* KRI citation by `_KRI_SPAN`; `None` when it is not one."""
    match = _KRI_SPAN.match(text or "")
    return _span_from_match(match) if match else None


def parse_kri_spans(text: str) -> list[KriSpan]:
    """Every well-formed KRI citation anywhere in `text`, in order.

    Exclusion checks use this, never `parse_kri_span`: a reference that cites two
    editions ("KRI II 569 (lines 3-16) = KRI VII 45-46") excludes both.
    """
    spans = []
    for match in _KRI_SPAN_ANYWHERE.finditer(text or ""):
        span = _span_from_match(match)
        if span is not None:
            spans.append(span)
    return spans


def any_spans_overlap(lines: list[KriSpan], entries: list[KriSpan]) -> bool:
    return any(spans_overlap(line, entry) for line in lines for entry in entries)


def spans_overlap(line: KriSpan, entry: KriSpan) -> bool:
    """Whether a line's citation falls inside an entry's. Errs toward overlap.

    Different volumes or disjoint pages never overlap. Line ranges are only used to
    rule a line *out* when both citations are on one and the same page and both name
    lines; a multi-page entry's line range is ambiguous, so it covers whole pages.
    """
    if line.volume != entry.volume:
        return False
    if line.page_end < entry.page_start or entry.page_end < line.page_start:
        return False
    single_same_page = (
        line.page_start == line.page_end == entry.page_start == entry.page_end
    )
    if single_same_page and line.line_start is not None and entry.line_start is not None:
        return not (line.line_end < entry.line_start or entry.line_end < line.line_start)
    return True


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

    def edition_links(self) -> dict[str, set[str]]:
        """The undirected links `edition` entries make, by entry id.

        An `edition` entry is linked to every entry it names by id and to every entry
        one of whose KRI spans overlaps one of its own. Other scopes link nothing:
        two passage entries that happen to share a page are two exclusions, not one.
        """
        links: dict[str, set[str]] = {entry.entry_id: set() for entry in self.entries}
        spans = {entry.entry_id: parse_kri_spans(entry.reference) for entry in self.entries}
        ids = set(links)
        for entry in self.entries:
            if entry.scope != "edition":
                continue
            named = set(_ENTRY_LINK.findall(entry.reference)) & ids
            overlapping = {
                other.entry_id
                for other in self.entries
                if other.entry_id != entry.entry_id
                and any_spans_overlap(spans[entry.entry_id], spans[other.entry_id])
            }
            for other_id in (named | overlapping) - {entry.entry_id}:
                links[entry.entry_id].add(other_id)
                links[other_id].add(entry.entry_id)
        return links

    def excludes_reference(self, kri_reference: str) -> list[ManifestEntry]:
        """Which entries cover this line's citation, directly or by an edition link.

        Every KRI span in the line's reference is compared with every KRI span in each
        entry's reference. The entries hit directly are then closed over
        `edition_links`, so a line in the second edition of an excluded passage is
        excluded by the passage's entry as well as by the edition entry. A pending
        entry counts: its reference is real even before its hash is.
        """
        line_spans = parse_kri_spans(kri_reference)
        if not line_spans:
            return []
        hit_ids = {
            entry.entry_id
            for entry in self.entries
            if any_spans_overlap(line_spans, parse_kri_spans(entry.reference))
        }
        if hit_ids:
            links = self.edition_links()
            frontier = list(hit_ids)
            while frontier:
                for linked in links.get(frontier.pop(), ()):
                    if linked not in hit_ids:
                        hit_ids.add(linked)
                        frontier.append(linked)
        return [entry for entry in self.entries if entry.entry_id in hit_ids]

    def entry(self, entry_id: str) -> ManifestEntry | None:
        return next((entry for entry in self.entries if entry.entry_id == entry_id), None)


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
    # Messages name the field, never its content: a malformed field may be exactly
    # where a line was pasted by mistake.
    problems: list[str] = []
    if not _ENTRY_ID.match(entry.entry_id):
        problems.append("entry_id is not of the form EX001")
    if not _ISO_DATE.match(entry.added):
        problems.append("added is not an ISO date (YYYY-MM-DD)")
    if entry.scope not in SCOPES:
        problems.append(f"scope is not one of {list(SCOPES)}")
    if not entry.reference.strip():
        problems.append("reference is empty: an exclusion with no citation excludes nothing")
    elif strict and entry.scope in ("line", "passage") and not parse_kri_spans(entry.reference):
        problems.append(
            "reference carries no KRI citation (`KRI <vol> <page>[-<page>]"
            " [(lines a-b)]`), so no line can be excluded by reference"
        )
    elif entry.scope == "edition" and strict and not parse_kri_spans(entry.reference):
        problems.append(
            "an edition entry's reference carries no KRI citation, so no line of that "
            "edition can be excluded by reference"
        )
    if entry.hash_basis not in HASH_BASES:
        problems.append(f"hash_basis is not one of {sorted(HASH_BASES)}")
    if entry.pending:
        if entry.hash_basis != "pending":
            problems.append("a pending hash must carry hash_basis 'pending'")
        if strict:
            problems.append(
                f"sha256 is still {PENDING_HASH!r}: the lead must fill it in before a run"
            )
    elif not _HEX64.match(entry.sha256):
        problems.append(
            f"sha256 is neither 64 lower-case hex digits nor {PENDING_HASH!r}"
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


def entry_label(index: int) -> str:
    """How a message names an entry: its position, never a field of it.

    Review round 2 (2026-10-26): even a well-formed-looking `entry_id` is a field the
    lead typed, so messages about an entry say "entry N" (1-based, file order) only.
    """
    return f"entry {index}"


def validate(manifest: Manifest, *, strict: bool = False) -> list[str]:
    """Every problem with the whole manifest, each prefixed by the entry's position."""
    problems: list[str] = []
    seen: dict[str, int] = {}
    ids = {entry.entry_id for entry in manifest.entries}
    links = manifest.edition_links()
    for index, entry in enumerate(manifest.entries, start=1):
        label = entry_label(index)
        problems.extend(f"{label}: {problem}" for problem in validate_entry(entry, strict=strict))
        if entry.entry_id in seen:
            problems.append(f"{label}: duplicate entry_id (same as {entry_label(seen[entry.entry_id])})")
        else:
            seen[entry.entry_id] = index
        if entry.scope == "edition":
            named = set(_ENTRY_LINK.findall(entry.reference))
            if named - ids:
                problems.append(f"{label}: an edition entry names an entry id the manifest does not have")
            if strict and not links.get(entry.entry_id) and len(parse_kri_spans(entry.reference)) < 2:
                problems.append(
                    f"{label}: an edition entry relates no references: cite every edition "
                    f"as a KRI span, or name the excluded entry's id (EX001)"
                )
    return problems


# ---------------------------------------------------------------------------
# the private excluded texts (custody only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExcludedText:
    entry_id: str
    transliteration: str
    hieroglyphs: str


def read_excluded_texts(path: str | Path, manifest: Manifest) -> list[ExcludedText]:
    """Read the private excluded texts and bind each to its committed manifest entry.

    Every row must name a manifest entry. When that entry has a real hash, the row's
    text — transliteration for `canonical_transliteration`, hieroglyphs for
    `canonical_glyphs` — must hash to it: that is what ties the private comparison
    material to the committed manifest. Errors give the row number and entry id,
    never the text.
    """
    texts: list[ExcludedText] = []
    with open(Path(path).expanduser(), "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in EXCLUDED_TEXT_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ManifestError(f"excluded-texts file is missing column(s) {missing}")
        for row_number, row in enumerate(reader, start=2):
            entry_id = (row.get("entry_id") or "").strip()
            entry = manifest.entry(entry_id) if _ENTRY_ID.match(entry_id) else None
            if entry is None:
                raise ManifestError(
                    f"excluded-texts row {row_number}: entry_id is not an entry of the manifest"
                )
            text = ExcludedText(
                entry_id=entry_id,
                transliteration=row.get("transliteration") or "",
                hieroglyphs=row.get("hieroglyphs") or "",
            )
            if not entry.pending:
                hashed = (
                    text.transliteration
                    if entry.hash_basis == "canonical_transliteration"
                    else text.hieroglyphs
                )
                try:
                    digest = content_hash(hashed, basis=entry.hash_basis)
                except ManifestError:
                    digest = ""
                if digest != entry.sha256:
                    raise ManifestError(
                        f"excluded-texts row {row_number} ({entry_id}): the text does not hash "
                        f"to the manifest's sha256 under {entry.hash_basis}; it is not the "
                        f"excluded text, or the manifest is stale"
                    )
            texts.append(text)
    return texts


def completeness_problems(manifest: Manifest, texts: list[ExcludedText] | None) -> list[str]:
    """Why this manifest cannot back a confirmation run. Empty list = complete.

    Complete = strictly valid (no pending hash, every KRI reference parses) and every
    entry's text supplied privately, so the near-match and edition checks of §4e can
    run against it.
    """
    problems = validate(manifest, strict=True)
    if not manifest.entries:
        problems.append("the manifest has no entries; §4e requires the 4d exclusions in it")
    if texts is None:
        problems.append("no excluded-texts file: near-match exclusion cannot be checked")
    else:
        covered = {text.entry_id for text in texts}
        problems.extend(
            f"{entry_label(index)}: no private excluded text, so near-match exclusion "
            f"cannot be checked against it"
            for index, entry in enumerate(manifest.entries, start=1)
            if entry.entry_id not in covered
        )
    return problems


# ---------------------------------------------------------------------------
# file i/o
# ---------------------------------------------------------------------------


def read_manifest(path: str | Path) -> Manifest:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != MANIFEST_COLUMNS:
            # The header is a field the file's author typed: never echoed.
            raise ManifestError(f"manifest header is not {list(MANIFEST_COLUMNS)}")
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
    if entry.entry_id in {existing.entry_id for existing in manifest.entries}:
        problems.append("entry_id is already in the manifest")
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
    for index, entry in enumerate(manifest.entries, start=1):
        if not entry.pending:
            continue
        # Review round 2: a field is echoed only for an entry with no problem at all;
        # a rejected entry is named by its position and nothing else.
        if validate_entry(entry):
            print(f"  pending: {entry_label(index)}  (rejected: fields withheld, see INVALID)")
        else:
            print(f"  pending: {entry_label(index)}  {entry.entry_id}  {entry.reference}")
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

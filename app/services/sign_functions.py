"""What each hieroglyph *does* in a writing — the a-priori knowledge behind item C.

Two tables are read here and folded into one inventory:

* `data/processed/sign_functions.csv` — Mark-Jan Nederhof's sign-function list for the
  Unicode 5.2 hieroglyphs, converted by `scripts/import_sign_functions.py`, **CC BY
  4.0** under his written grant of 2026-09-04 (see DATA-LICENSE.md). 1,444 entries
  covering 780 signs.
* `data/processed/sign_functions_supplement.csv` — thirteen rows written by this
  project for the most frequent corpus signs Nederhof's Unicode 5.2 list does not
  cover (Z7 𓏲 alone is 36k tokens). Source: the Gardiner sign list; licence CC BY-SA
  4.0 like the rest of this project's own data. Every row carries `source_note =
  "project supplement"` so it is never mistaken for one of Nederhof's.

The five-class fold. Nederhof's seven labels are folded to the classes the models
actually branch on, and a label that names two possibilities folds to *both* — the
uncertainty is real and the models keep it soft rather than picking a side:

    logogram                            -> {log}
    determinative                       -> {det}
    logogram or determinative           -> {log, det}
    phonogram                           -> {phon}
    phonetic determinative              -> {phondet}
    phonogram or phonetic determinative -> {phon, phondet}
    typographic                         -> {typ}

A sign in neither table gets `{unk}` — including every TLA `<g>…</g>` placeholder,
which is not a sign at all. `unk` is a class like the others, not a missing value: the
boundary model estimates statistics for it and so is never asked to guess.

`P(class | sign)` is **uniform over the sign's class set**. The tables give no
frequencies, and inventing them would be tuning dressed as data.

Note on sign ids. Nederhof writes the Gardiner variants lower-case (`Z3a`, `V31a`,
`N35a`); the supplement uses the upper-case form the pre-registration named (`Z3A`,
`V31A`, `N35A`). Nothing joins on `gardiner` — every lookup here is by the Unicode
character — so the two conventions sit side by side without colliding.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
SIGN_FUNCTIONS_PATH = _DATA_DIR / "sign_functions.csv"
SUPPLEMENT_PATH = _DATA_DIR / "sign_functions_supplement.csv"

SUPPLEMENT_NOTE = "project supplement"

#: The five classes, plus `unk` for a sign neither table covers.
PHON = "phon"
LOG = "log"
DET = "det"
PHONDET = "phondet"
TYP = "typ"
UNK = "unk"
CLASSES = (PHON, LOG, DET, PHONDET, TYP, UNK)

#: Nederhof's own class names (the `function` column) -> the folded class set.
CLASS_FOLD: dict[str, frozenset[str]] = {
    "logogram": frozenset({LOG}),
    "determinative": frozenset({DET}),
    "logogram or determinative": frozenset({LOG, DET}),
    "phonogram": frozenset({PHON}),
    "phonetic determinative": frozenset({PHONDET}),
    "phonogram or phonetic determinative": frozenset({PHON, PHONDET}),
    "typographic": frozenset({TYP}),
}

UNKNOWN_CLASSES = frozenset({UNK})

# Shown wherever a composed reading is displayed; attribution is a licence condition
# for Nederhof's half of the table.
SIGN_FUNCTION_CREDIT = (
    "Sign functions: Mark-Jan Nederhof, sign-function list for the Unicode 5.2 "
    'hieroglyphs, <a href="https://mjn.host.cs.st-andrews.ac.uk/egyptian/unicode/">'
    "mjn.host.cs.st-andrews.ac.uk/egyptian/unicode/</a>, CC BY 4.0, plus this "
    "project's own supplement for thirteen uncovered signs (Gardiner sign list, "
    "CC BY-SA 4.0)."
)


#: Qualifiers that make a row unusable for reading a sign standing on its own: the
#: reading belongs to a plural, a dual or a numeral writing, which is a different
#: token from the bare sign. `period` and `texttype` are *not* filtered — they say
#: when a reading is attested, not that it is conditional on other signs.
NON_STANDALONE_QUALIFIERS = ("plural", "dual", "numeral")


@dataclass(frozen=True)
class FunctionEntry:
    """One row of either table: this sign, used this way, reads this."""

    sign: str
    gardiner: str
    function: str
    value: str
    meaning: str
    source_note: str
    #: Nederhof's RES sign combination when the reading belongs to a *combination*
    #: rather than to the sign alone (`A1:Z2` -> rḥw "men"). Empty for a standalone row.
    group: str = ""
    #: `period`, `texttype`, `plural`, `dual`, `numeral`, `certain`, `root`, joined
    #: with "; " by `scripts/import_sign_functions.py`.
    qualifier: str = ""

    @property
    def classes(self) -> frozenset[str]:
        return CLASS_FOLD.get(self.function, UNKNOWN_CLASSES)

    @property
    def is_supplement(self) -> bool:
        return self.source_note == SUPPLEMENT_NOTE

    @property
    def qualifiers(self) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for part in self.qualifier.split(";"):
            part = part.strip()
            if not part:
                continue
            name, _, value = part.partition("=")
            parsed[name.strip()] = value.strip()
        return parsed

    @property
    def is_standalone(self) -> bool:
        """May this row be used to read the sign *on its own*? (item C2, amended)

        Three exclusions, all of them because the row does not describe the bare
        sign:

        * a row scoped to a sign **combination** (`group` non-empty) — A1 with the
          plural strokes reads *rḥw*, but A1 alone does not, and this project cannot
          yet match RES combinations against a corpus sign group;
        * a row Nederhof himself hedges as uncertain (`certain=false`);
        * a row qualified `plural`, `dual` or `numeral`.

        `period` and `texttype` are deliberately not filtered: they date a reading,
        they do not make it conditional on neighbouring signs.
        """
        if self.group:
            return False
        qualifiers = self.qualifiers
        if qualifiers.get("certain", "").lower() == "false":
            return False
        return not any(name in qualifiers for name in NON_STANDALONE_QUALIFIERS)


@dataclass
class SignFunctions:
    """sign character -> its folded class set and its ordered function entries."""

    #: sign -> the union of the folded classes of all its entries.
    classes: dict[str, frozenset[str]] = field(default_factory=dict)
    #: sign -> entries in table order (Nederhof's rows first, then the supplement).
    entries: dict[str, tuple[FunctionEntry, ...]] = field(default_factory=dict)
    paths: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.classes)

    def __contains__(self, sign: str) -> bool:
        return sign in self.classes

    def classes_for(self, sign: str) -> frozenset[str]:
        """The sign's class set; `{unk}` for anything the tables do not cover."""
        return self.classes.get(sign, UNKNOWN_CLASSES)

    def class_distribution(self, sign: str) -> dict[str, float]:
        """`P(class | sign)`, uniform over the sign's classes (see module docstring)."""
        classes = self.classes_for(sign)
        weight = 1.0 / len(classes)
        return {c: weight for c in classes}

    def entries_for(self, sign: str) -> tuple[FunctionEntry, ...]:
        return self.entries.get(sign, ())

    def standalone_entries_for(self, sign: str) -> tuple[FunctionEntry, ...]:
        """Only the rows that describe the sign on its own (see `is_standalone`).

        This is what `app.services.composition` reads. An empty result means "this
        table says nothing about this sign standing alone" — which the amended C2
        rule turns into an abstention, not into silence.
        """
        return tuple(
            entry for entry in self.entries.get(sign, ()) if entry.is_standalone
        )


def _read(path: Path) -> list[FunctionEntry]:
    if not path.exists():
        return []
    rows: list[FunctionEntry] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            sign = (row.get("sign") or "").strip()
            function = (row.get("function") or "").strip()
            if not sign or not function:
                continue
            rows.append(
                FunctionEntry(
                    sign=sign,
                    gardiner=(row.get("gardiner") or "").strip(),
                    function=function,
                    value=(row.get("value") or "").strip(),
                    meaning=(row.get("meaning") or "").strip(),
                    source_note=(row.get("source_note") or "").strip(),
                    group=(row.get("group") or "").strip(),
                    qualifier=(row.get("qualifier") or "").strip(),
                )
            )
    return rows


def load_sign_functions(
    path: str | Path | None = None,
    supplement_path: str | Path | None = None,
) -> SignFunctions:
    """Load Nederhof's table and the project supplement as one inventory.

    An absent file yields an empty inventory rather than an error — the same rule
    `load_lexicon` follows — and every sign then falls to `{unk}`, which is exactly
    the state the models must degrade to when the table is not shipped.
    """
    main = Path(path) if path is not None else SIGN_FUNCTIONS_PATH
    extra = Path(supplement_path) if supplement_path is not None else SUPPLEMENT_PATH
    rows = _read(main) + _read(extra)

    by_sign: dict[str, list[FunctionEntry]] = defaultdict(list)
    for entry in rows:
        by_sign[entry.sign].append(entry)

    inventory = SignFunctions(paths=(str(main), str(extra)))
    for sign, sign_entries in by_sign.items():
        folded: set[str] = set()
        for entry in sign_entries:
            folded |= entry.classes
        inventory.classes[sign] = frozenset(folded) or UNKNOWN_CLASSES
        inventory.entries[sign] = tuple(sign_entries)
    return inventory

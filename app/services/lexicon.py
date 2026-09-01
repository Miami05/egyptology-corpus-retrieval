"""The sign-reading lexicon: attested spelling → reading counts from outside our corpus.

Built by `scripts/import_helsinki_lexicon.py` from the University of Helsinki
"Transliteration Model" files (CC BY 4.0), which tabulate how every hieroglyphic word
in the AES and Ramses corpora is transliterated, and how often. Read the module
docstring there for provenance.

How the app uses it. `ReadingModel` consults the lexicon only for a sign group the
corpus has never attested — after the corpus, before guessing from a similar group.
Such a reading is attested evidence with a count, but it is not a sentence we can show,
and every surface that displays it says so. Nothing here is generated.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

LEXICON_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "helsinki_lexicon.csv"

# Shown wherever a lexicon reading is displayed; the licence condition is attribution.
LEXICON_LABEL = "Helsinki AES+Ramses lexicon"
LEXICON_CREDIT = (
    "Sign-reading lexicon: Heidi Jauhiainen & Tommi Jauhiainen (University of Helsinki), "
    "<em>Transliteration Model for Egyptian Words</em>, 2023, "
    '<a href="https://doi.org/10.5281/zenodo.7991241">doi:10.5281/zenodo.7991241</a>, '
    "CC BY 4.0 — word-level spelling→reading counts derived from AES (S. Schweitzer, "
    "BBAW) and the Ramses Transliteration Corpus (S. Rosmorduc / Université de Liège, "
    "Projet Ramsès). Used only for sign groups this corpus does not attest."
)


@dataclass
class Lexicon:
    """group (normalised Unicode signs) → Counter(reading → attested frequency)."""

    readings: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    #: group → "AES", "Ramses" or "AES+Ramses"
    sources: dict[str, str] = field(default_factory=dict)
    path: str = ""

    def __len__(self) -> int:
        return len(self.readings)

    def __contains__(self, group: str) -> bool:
        return group in self.readings

    def candidates_for(self, group: str) -> list[tuple[str, int]]:
        return self.readings.get(group, Counter()).most_common()

    def total(self, group: str) -> int:
        return sum(self.readings.get(group, Counter()).values())

    def source_of(self, group: str) -> str:
        return self.sources.get(group, "")


def load_lexicon(path: str | Path | None = None) -> Lexicon:
    """Load the CSV; an absent file yields an empty lexicon, never an error.

    Empty is a legitimate state — a fresh clone before the import has run, or a
    deployment that chose not to ship the file — and the model then behaves exactly
    as it did before the lexicon existed.
    """
    target = Path(path) if path is not None else LEXICON_PATH
    lexicon = Lexicon(path=str(target))
    if not target.exists():
        return lexicon
    per_group_sources: dict[str, set[str]] = defaultdict(set)
    with target.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            group = (row.get("group") or "").strip()
            reading = (row.get("reading") or "").strip()
            if not group or not reading:
                continue
            lexicon.readings[group][reading] += int(row.get("freq") or 0)
            for source in (row.get("source") or "").split("+"):
                if source:
                    per_group_sources[group].add(source)
    lexicon.sources = {g: "+".join(sorted(s)) for g, s in per_group_sources.items()}
    return lexicon

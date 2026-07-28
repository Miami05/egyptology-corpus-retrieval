"""Sign-to-reading index: which readings is each sign group actually attested with?

This is the direct view of multivalence. Hieroglyphs and transliteration are token
aligned in the TLA data, so for every sign group we can count the readings it carries
across the corpus and show the sentences behind each one.

It also separates two things that look identical in a naive count:

  editorial variation - `n.t` vs `n(.ꞽ).t`, the same reading with different bracketing
                        of unwritten signs
  distinct readings   - `sw` ("he") vs `nswt` ("king") for 𓇓𓅱, genuinely different words

Only the second is the multivalence problem worth solving, so the two are reported
separately rather than being added together.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from app.services.suggestions import loose_reading_form


@dataclass
class SignReadings:
    sign: str
    total_instances: int
    literal_readings: Counter = field(default_factory=Counter)
    distinct_readings: Counter = field(default_factory=Counter)
    examples: dict[str, list[dict]] = field(default_factory=dict)

    @property
    def literal_count(self) -> int:
        return len(self.literal_readings)

    @property
    def distinct_count(self) -> int:
        return len(self.distinct_readings)

    @property
    def is_multivalent(self) -> bool:
        """More than one reading even after collapsing editorial bracketing."""
        return self.distinct_count > 1

    def is_well_attested_multivalent(self, min_support: int = 3) -> bool:
        """At least two readings each attested `min_support` times.

        This is the stricter and more defensible test. Counting any sign with a second
        reading as multivalent overstates the phenomenon badly: on the full corpus 1,211
        signs have more than one reading, but for 82% of them every extra reading occurs
        once or twice, which is usually a one-off spelling or a slip in the sign/reading
        alignment rather than a real alternative a model could learn.
        """
        supported = [count for count in self.distinct_readings.values() if count >= min_support]
        return len(supported) >= 2

    @property
    def editorial_variants_only(self) -> int:
        """Readings that differ only by editorial marks."""
        return self.literal_count - self.distinct_count


def build_sign_index(
    df: pd.DataFrame,
    max_examples: int = 4,
) -> dict[str, SignReadings]:
    """Map each sign group to the readings it is attested with.

    Rows whose sign and reading token counts disagree are skipped: without a
    one-to-one alignment a sign cannot be paired with a reading, and guessing would
    invent evidence.
    """
    index: dict[str, SignReadings] = {}
    for _, row in df.iterrows():
        glyphs = str(row.get("hieroglyphs_norm") or row.get("hieroglyphs") or "").split()
        readings = str(row.get("transliteration_gold") or "").split()
        if not glyphs or len(glyphs) != len(readings):
            continue
        for glyph, reading in zip(glyphs, readings):
            entry = index.get(glyph)
            if entry is None:
                entry = SignReadings(sign=glyph, total_instances=0)
                index[glyph] = entry
            entry.total_instances += 1
            entry.literal_readings[reading] += 1
            entry.distinct_readings[loose_reading_form(reading).strip()] += 1
            examples = entry.examples.setdefault(reading, [])
            if len(examples) < max_examples:
                examples.append(
                    {
                        "source_text_id": str(row.get("source_text_id", "")),
                        "source_sentence_id": str(row.get("source_sentence_id", "")),
                        "transliteration": str(row.get("transliteration_gold", "")),
                        "translation": str(row.get("translation", "")),
                        "period": str(row.get("period", "")),
                    }
                )
    return index


def multivalence_summary(
    index: dict[str, SignReadings],
    min_support: int = 3,
) -> dict[str, int]:
    multivalent = [entry for entry in index.values() if entry.is_multivalent]
    literal_multi = [entry for entry in index.values() if entry.literal_count > 1]
    well_attested = [
        entry for entry in index.values() if entry.is_well_attested_multivalent(min_support)
    ]
    ambiguous_instances = sum(entry.total_instances for entry in multivalent)
    total_instances = sum(entry.total_instances for entry in index.values())
    return {
        "sign_groups": len(index),
        "literal_multi": len(literal_multi),
        "genuinely_multivalent": len(multivalent),
        "editorial_only": len(literal_multi) - len(multivalent),
        # The defensible headline: both readings actually recur.
        "well_attested_multivalent": len(well_attested),
        "min_support": min_support,
        "ambiguous_instances": ambiguous_instances,
        "total_instances": total_instances,
    }


def ranked_multivalent(
    index: dict[str, SignReadings],
    limit: int = 0,
) -> list[SignReadings]:
    """Genuinely multivalent signs, most attested first."""
    entries = [entry for entry in index.values() if entry.is_multivalent]
    entries.sort(key=lambda e: (-e.total_instances, -e.distinct_count))
    return entries[:limit] if limit else entries

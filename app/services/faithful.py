"""Experiment 3, configuration F-a: the notation-faithful search key (OFF by default).

Frozen definition: ROADMAP.md, "Experiment 3 — the notation-faithful search key —
pre-registered 2026-09-07", addendum 2026-10-26, "F-a, frozen definition (revision)".
In short, for a query with `parse_query(query, vocabulary=<corpus vocabulary>).notation
== "unicode"`, and only for such a query:

- the faithful key of a token is its `unfolded_reading_form` piece (lossless letters,
  `fold_strict_aliases` applied, editorial text and markers removed), on the query side
  and on the corpus side;
- (i) retrieval matches and weighs tokens by that key: the per-row token sets, document
  frequencies, n-gram index, exact match and fuzzy string are all computed on the
  faithful corpus column instead of `mdc_norm` (`app.services.retrieval`);
- (ii) the re-rank runs `QueryForms` in `strict` mode for the whole query, with no
  per-word A54 decision (`app.services.suggestions`).

Queries in `ascii`, `mdc` or hieroglyph notation take today's path untouched, and with
the switch off nothing here is ever computed: no faithful column, no faithful index, no
branch taken, so every output is byte-identical to the code before this module.

The switch. `EXP3_FA_DEFAULT` is the code default (False). The environment variable
`WHYPTOLOGY_EXP3_FA` overrides it either way (`1/on/true/yes`, `0/off/false/no`; unset
or empty = the code default), for tests and manual probes. The pre-registered run does
NOT use the variable: its two arms differ only in the commit ("the arms differ only in
the commit"), so the F-a arm is a one-line child commit that sets `EXP3_FA_DEFAULT =
True`, and `scripts/run_exp3_prereg.sh` refuses to start while the variable is set.
"""

from __future__ import annotations

import os

import pandas as pd

# Flipped to True only by the F-a arm commit of the Experiment 3 run (see above).
EXP3_FA_DEFAULT = False
EXP3_FA_ENV = "WHYPTOLOGY_EXP3_FA"

# The corpus-side faithful key per row. Computed only when F-a is on; a caller that
# searches many sub-frames of one corpus (the competitive harness) adds it once to the
# full frame so every sub-frame inherits it instead of recomputing it.
FAITHFUL_COLUMN = "faithful_norm"

_ON = {"1", "on", "true", "yes"}
_OFF = {"0", "off", "false", "no"}


def faithful_search_enabled() -> bool:
    """Whether configuration F-a is switched on (code default, env override)."""
    value = os.environ.get(EXP3_FA_ENV, "").strip().lower()
    if not value:
        return EXP3_FA_DEFAULT
    if value in _ON:
        return True
    if value in _OFF:
        return False
    raise ValueError(f"{EXP3_FA_ENV}={value!r}: use one of {sorted(_ON | _OFF)}")


def applies_to(notation: str) -> bool:
    """F-a runs for a query exactly when the switch is on and its notation is unicode.

    The switch is read first, so with it off not even the notation is looked at.
    """
    return faithful_search_enabled() and notation == "unicode"


def faithful_key(value: object) -> str:
    """The faithful key of a reading: its `unfolded_reading_form` pieces, space-joined."""
    # Imported here: app.services.suggestions imports this module for the switch.
    from app.services.suggestions import unfolded_reading_form

    return unfolded_reading_form(value)


def faithful_search_column(df: pd.DataFrame) -> pd.Series:
    """Every row's faithful key, aligned with `df`.

    Taken from `FAITHFUL_COLUMN` when the frame already carries it. Otherwise it is
    `faithful_key(transliteration_gold)`; a row with no transliteration has no written
    letters to be faithful to and gets an empty key, so no text query reaches it (its
    `mdc_norm` comes from the stored, already-folded `mdc` column, which a faithful
    comparison cannot use).
    """
    if FAITHFUL_COLUMN in df.columns:
        return df[FAITHFUL_COLUMN].astype(str)
    if "transliteration_gold" not in df.columns:
        return pd.Series("", index=df.index, dtype=object)
    readings = df["transliteration_gold"].fillna("").astype(str)
    keys = readings.map(faithful_key)
    return keys.where(readings.str.strip() != "", "")


def with_faithful_column(df: pd.DataFrame) -> pd.DataFrame:
    """`df` with `FAITHFUL_COLUMN` added in place (once), returned for chaining."""
    if FAITHFUL_COLUMN not in df.columns:
        df[FAITHFUL_COLUMN] = faithful_search_column(df)
    return df


def faithful_view(df: pd.DataFrame) -> pd.DataFrame:
    """A copy of `df` whose `mdc_norm` is the faithful key, same index and row order.

    Retrieval's scorers read the search key from `mdc_norm`; handing them this view is
    how every retrieval signal is computed on the faithful key without a second copy
    of the scoring code.
    """
    return df.assign(mdc_norm=faithful_search_column(df).to_numpy())


def build_faithful_index(
    df: pd.DataFrame,
    folded_index,
    stats_frame: pd.DataFrame | None = None,
    pooled_faithful=None,
):
    """The faithful twin of a `SearchIndex` built over `df` (the pooled frame).

    `folded_index` is the ordinary index of the same frame and stage; its sign-side
    parts (glyph token table, glyph weights and frequencies) do not depend on the text
    key and are shared as they are. `stats_frame` is the frame the document
    frequencies are counted over (a stage subset; `df` itself when None), exactly as
    for the folded index. `pooled_faithful`, the pooled faithful index, supplies the
    n-gram index and the text token table when they were built from this same frame,
    as the folded build reuses the pooled ones.
    """
    from app.retrieval.scorer import CorpusStats, document_frequencies
    from app.retrieval.tfidf import NgramIndex
    from app.retrieval.tokens import ScoringTables, TokenTable, TokenWeights
    from app.services.retrieval import SearchIndex

    view = faithful_view(df)
    stats_keys = faithful_search_column(df if stats_frame is None else stats_frame)
    folded_stats = folded_index.stats
    stats = CorpusStats(
        mdc_frequencies=document_frequencies(stats_keys),
        glyph_frequencies=folded_stats.glyph_frequencies,
        n_rows=folded_stats.n_rows if folded_stats.n_rows is not None else len(stats_keys),
    )
    if pooled_faithful is not None and len(pooled_faithful.text_index) == len(view):
        text_index = pooled_faithful.text_index
    else:
        text_index = NgramIndex.build(view["mdc_norm"])
    tables = None
    folded_tables = folded_index.tables
    if folded_tables is not None and folded_tables.matches(view):
        shared = (
            pooled_faithful.tables
            if pooled_faithful is not None
            and pooled_faithful.tables is not None
            and pooled_faithful.tables.matches(view)
            else None
        )
        text = shared.text if shared is not None else TokenTable.build(view["mdc_norm"])
        tables = ScoringTables(
            row_ids=folded_tables.row_ids,
            text=text,
            text_weights=TokenWeights.build(text, stats.mdc_frequencies, stats.n_rows),
            glyph=folded_tables.glyph,
            glyph_weights=folded_tables.glyph_weights,
        )
    return SearchIndex(stats=stats, text_index=text_index, tables=tables)

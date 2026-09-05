from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.data.normalizer import (
    PLACEHOLDER_COLLISIONS,
    normalize_hieroglyphs,
    normalize_label,
    normalize_mdc,
    normalize_pipe_list,
    normalize_sign_sequence,
    normalize_transliteration,
    search_fold,
    parse_bool,
)

REQUIRED_COLUMNS = [
    "source",
    "source_text_id",
    "source_sentence_id",
    "language_stage",
    "script_type",
    "genre",
    "period",
    "hieroglyphs",
    "mdc",
    "sign_sequence",
    "transliteration_gold",
    "translation",
    "lemma_sequence",
    "upos",
    "glossing",
    "grammar_notes",
    "source_ref",
    "review_status",
    "formula_type",
    "deity",
    "recipient",
    "offering_items",
    "formula_slot",
    "display_sequence",
    "normalized_reading_order",
    "alt_transliterations",
    "variant_writing_note",
    "morphology_note",
    "syntax_note",
    "aesthetic_arrangement_flag",
]

# Text columns that are empty for most rows (only the TLA/AES rows carry them). pandas
# infers a dtype per chunk, so a chunk of all-empty cells comes back as float and a chunk
# with text as str — the "Columns (...) have mixed types" warning, and a column whose
# per-cell type depends on row order and chunk size. Pinning them to str is identical
# for every present value and keeps missing cells as NaN, so downstream fillna("") is
# unchanged.
SPARSE_TEXT_COLUMNS: dict[str, type] = {
    "mdc": str,
    "lemma_sequence": str,
    "upos": str,
    "glossing": str,
    "grammar_notes": str,
    "normalized_reading_order": str,
}


logger = logging.getLogger(__name__)


@dataclass
class AlignmentReport:
    """How many corpus rows the sign-level model can actually use.

    A row is usable when its normalised sign groups line up one-to-one with its
    transliteration tokens. Rows that do not are skipped by the reading model and
    the sign index, so the count must be visible rather than a silent `continue`.
    The raw CSV is 100% aligned; every misalignment is introduced by normalisation,
    which makes this number a regression check on the normaliser itself.

    Rows with no hieroglyphs at all (BBAW text-only rows, Demotic) are a separate,
    expected state, not a defect: they legitimately carry no sign evidence but still
    have a transliteration and take part in transliteration search. They are counted
    in `text_only_rows`, not in `misaligned_rows`. `usable_rows` = rows with usable
    sign alignment = `total_rows` − `misaligned_rows` − `text_only_rows`.
    """

    total_rows: int
    misaligned_rows: int
    text_only_rows: int = 0
    misaligned_indices: list[int] = field(default_factory=list)
    placeholder_collisions: int = 0

    @property
    def usable_rows(self) -> int:
        return self.total_rows - self.misaligned_rows - self.text_only_rows


def alignment_report(df: pd.DataFrame, max_listed: int = 50) -> AlignmentReport:
    signs = df["hieroglyphs_norm"].astype(str).str.split()
    readings = df["transliteration_gold"].astype(str).str.split()
    text_only = 0
    bad: list[int] = []
    for index, (s, r) in enumerate(zip(signs, readings)):
        if not s:
            text_only += 1
        elif len(s) != len(r):
            bad.append(int(index))
    return AlignmentReport(
        total_rows=len(df),
        misaligned_rows=len(bad),
        text_only_rows=text_only,
        misaligned_indices=bad[:max_listed],
        placeholder_collisions=len(PLACEHOLDER_COLLISIONS),
    )


def _normalize_corpus_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Shared normalisation for any frame with the `examples.csv` schema.

    Used by both `load_examples_csv` (the public, redistributed corpus) and
    `load_private_examples` (gitignored, non-commercial corpora) so the two never
    drift apart: a private row must be searchable and readable exactly like a
    public one, just kept out of the database, exports and API.
    """
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")
    # The search index is folded from the transliteration, not from the stored
    # `mdc` column, so that one function defines the key on both sides (see
    # `search_fold`). Trusting the column was two bugs at once: every one of the
    # 9,823 AES rows ships with `mdc` empty, so 37% of the corpus could not be
    # reached by any transliteration query — searching an AES sentence verbatim
    # returned five other rows and never itself — and the TLA rows that do have a
    # value were folded by a slightly different rule (ẖ → h there, ẖ → kh here),
    # so the same word indexed differently depending on which corpus it came from.
    # The column is still displayed and still used where no transliteration exists.
    folded = df["transliteration_gold"].astype(str).map(search_fold)
    stored = df["mdc"].astype(str).map(normalize_mdc)
    df["mdc_norm"] = folded.where(folded.str.strip() != "", stored)
    df["sign_sequence_norm"] = (
        df["sign_sequence"].astype(str).map(normalize_sign_sequence)
    )
    # Searchable sign key. Without this the hieroglyphs are only ever displayed,
    # so a user holding signs rather than a transliteration cannot query at all.
    df["hieroglyphs_norm"] = df["hieroglyphs"].astype(str).map(normalize_hieroglyphs)
    df["transliteration_norm"] = (
        df["transliteration_gold"].astype(str).map(normalize_transliteration)
    )
    df["formula_type_norm"] = df["formula_type"].astype(str).map(normalize_label)
    df["deity_norm"] = df["deity"].astype(str).map(normalize_label)
    df["recipient_norm"] = df["recipient"].astype(str).map(normalize_label)
    df["offering_items_norm"] = (
        df["offering_items"].astype(str).map(normalize_pipe_list)
    )
    df["formula_slot_norm"] = df["formula_slot"].astype(str).map(normalize_label)

    df["display_sequence_norm"] = (
        df["display_sequence"].astype(str).map(normalize_sign_sequence)
    )
    df["normalized_reading_order_norm"] = (
        df["normalized_reading_order"].astype(str).map(normalize_sign_sequence)
    )
    df["alt_transliterations_norm"] = (
        df["alt_transliterations"].astype(str).map(normalize_pipe_list)
    )
    df["aesthetic_arrangement_flag_bool"] = df["aesthetic_arrangement_flag"].map(
        parse_bool
    )
    report = alignment_report(df)
    df.attrs["alignment"] = report
    if report.misaligned_rows:
        logger.warning(
            "%d of %d corpus rows have sign groups that do not align with their "
            "transliteration and will be skipped by the reading model (first: %s)",
            report.misaligned_rows,
            report.total_rows,
            report.misaligned_indices[:10],
        )
    else:
        logger.info("corpus alignment: %d/%d rows usable", report.usable_rows, report.total_rows)
    if report.text_only_rows:
        logger.info(
            "%d of %d corpus rows have a transliteration but no hieroglyphs "
            "(text-only rows); they are searchable by transliteration but carry no "
            "sign evidence",
            report.text_only_rows,
            report.total_rows,
        )
    return df


def load_examples_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=SPARSE_TEXT_COLUMNS)
    return _normalize_corpus_frame(df)


def load_private_examples(directory: str | Path) -> pd.DataFrame:
    """Load every `*.csv` under `directory` as private, non-redistributed corpus rows.

    These are the NC-licensed corpora (Ramses, the St Andrews texts) that can never
    enter `data/processed/examples.csv` — CC BY-SA is share-alike and cannot carry
    NC material. `directory` is expected to be gitignored (see `.gitignore` and
    `test_private_data_dir_is_gitignored`); nothing here writes to it or reads
    anywhere else, and the caller is responsible for keeping the result away from
    the database, exports and the API — see `app/ui/whyptology_app.py` for where the
    public corpus is loaded and the private rows appended only afterwards.

    Returns a frame with the same columns `load_examples_csv` produces (empty, but
    correctly shaped, if the directory is missing or has no CSVs) so it can be
    concatenated directly onto the public corpus.
    """
    directory = Path(directory)
    if not directory.is_dir():
        logger.info(
            "private data directory %s does not exist; no private rows loaded",
            directory,
        )
        return _normalize_corpus_frame(pd.DataFrame(columns=REQUIRED_COLUMNS))

    csv_paths = sorted(directory.glob("*.csv"))
    if not csv_paths:
        logger.info(
            "private data directory %s has no CSV files; no private rows loaded",
            directory,
        )
        return _normalize_corpus_frame(pd.DataFrame(columns=REQUIRED_COLUMNS))

    frames: list[pd.DataFrame] = []
    for path in csv_paths:
        frame = pd.read_csv(path)
        sources = frame["source"] if "source" in frame.columns else pd.Series(dtype=object)
        blank = sources.isna() | (sources.astype(str).str.strip() == "")
        if "source" not in frame.columns or blank.any():
            raise ValueError(
                f"{path} has one or more rows with an empty 'source' column; every "
                "private row must be attributed to a named corpus (e.g. 'Ramses', "
                "'StAndrews')"
            )
        logger.info("loaded %d private rows from %s", len(frame), path.name)
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)
    logger.info(
        "loaded %d private rows in total from %d file(s) in %s",
        len(combined),
        len(csv_paths),
        directory,
    )
    return _normalize_corpus_frame(combined)

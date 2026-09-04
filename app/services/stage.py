"""Language-stage awareness (item A): keep other-stage rows from outvoting evidence.

Why this exists. `language_stage` is a per-row corpus column, but every statistic the
ranker and the reading model use — token IDF, sign->reading counts, segmenter group
counts — was pooled across all stages. Late Egyptian (Ramses, 40k rows) and Demotic
(TLA, 13k rows) spell differently from Middle/Earlier Egyptian, and once they are
loaded they are numerous enough to outvote the evidence a Middle Egyptian paste
actually needs (ROADMAP.md, "Item 4 landed 2026-09-04" and "Fri 09-04, night").

The fix here is not a nested per-stage counter inside each statistic. It is simpler:
subset the corpus frame to the rows compatible with a target stage, and build the
*existing* statistics (`SearchIndex`, `ReadingModel`, `Segmenter`, the sign index) on
that subset, exactly as they are built on the full frame today. `target=None` must
subset to nothing — the full frame — so the pooled behaviour is reproduced exactly.

Two-thirds of the corpus carries no stage at all (`Unspecified (AES)`,
`Unspecified (BBAW)`, or a blank column). Those rows are compatible with every
target stage: excluding them would starve every stage of the bulk of the corpus for
no reason, since an unlabelled row was never the thing that outvoted the evidence —
a large *labelled* population of a different stage was.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:  # pragma: no cover - import cycle avoidance at runtime
    from app.services.lexicon import Lexicon
    from app.services.reading_model import ReadingModel
    from app.services.retrieval import SearchIndex
    from app.services.segmentation import Segmenter, SegmentationWeights
    from app.services.signs import SignReadings

# The three stages the corpus distinguishes. Order matters only for display; nothing
# here depends on it.
STAGES: tuple[str, ...] = ("Earlier Egyptian", "Late Egyptian", "Demotic")

_STAGE_SET = set(STAGES)


def normalize_stage(value: object) -> str | None:
    """A raw `language_stage` cell -> one of STAGES, or None.

    None covers every "no usable stage" shape the corpus contains: a blank/NaN cell,
    `Unspecified (AES)`, `Unspecified (BBAW)`, or any value this project has not
    defined a stage for (a defensive default, not a case the current corpus hits).
    """
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    if text in _STAGE_SET:
        return text
    return None


def stage_compatible(row_stage: object, target: str | None) -> bool:
    """Whether a row's raw `language_stage` value may stand as evidence for `target`.

    True when there is no restriction (`target is None`), when the row itself carries
    no known stage (compatible with everything, per the module docstring), or when
    the row's normalised stage equals `target`. False only when the row's stage is
    known and differs from `target`.
    """
    if target is None:
        return True
    row_normalized = normalize_stage(row_stage)
    return row_normalized is None or row_normalized == target


def compatible_frame(df: pd.DataFrame, target: str | None) -> pd.DataFrame:
    """Rows of `df` compatible with `target` (the whole frame when `target is None`).

    Vectorised: no per-row Python loop. A row with no `language_stage` column at all
    is treated as fully unspecified (compatible with everything), which matches
    `normalize_stage`'s treatment of a blank cell.
    """
    if target is None or "language_stage" not in df.columns:
        return df
    normalized = df["language_stage"].map(normalize_stage)
    mask = normalized.isna() | (normalized == target)
    return df.loc[mask]


def stage_base_rates(df: pd.DataFrame) -> dict[str, float]:
    """Share of each known stage among `df`'s labelled rows.

    Meant to be computed once on the *pooled* frame and passed into `infer_stage` as
    `base_rates`, so a query's retrieved-row stage mix can be judged against how
    common each stage is in the corpus, not just against the other retrieved rows.
    Empty (not an error) when `df` has no `language_stage` column or no labelled
    rows at all.
    """
    if "language_stage" not in df.columns:
        return {}
    normalized = df["language_stage"].map(normalize_stage).dropna()
    if normalized.empty:
        return {}
    counts = Counter(normalized)
    total = len(normalized)
    return {stage: count / total for stage, count in counts.items()}


def infer_stage(
    result_df: pd.DataFrame,
    min_labelled: int = 3,
    min_share: float = 0.7,
    base_rates: dict[str, float] | None = None,
    min_lift: float = 1.5,
) -> str | None:
    """Guess a query's stage from the stages of its retrieved rows.

    Considers only rows whose `language_stage` normalises to a known stage (unlabelled
    rows say nothing about which stage the query belongs to, so they are dropped
    rather than counted as a fourth "unknown" bucket). Returns the majority stage only
    when there is enough labelled evidence (`min_labelled` rows) and it is decisive
    enough (`min_share` of the labelled rows) — both thresholds are conservative on
    purpose: a wrong inferred stage silently narrows the evidence a query sees, which
    is worse than declining to infer. Pure function of the frame; no I/O.

    `base_rates`/`min_lift`: a corpus where one stage is simply more common among
    labelled rows than another (Ramses makes Late Egyptian ~3x more common than
    Earlier Egyptian among labelled rows) will pass `min_share` for that stage on
    many queries by sheer prior weight, not because the retrieved rows are actually
    decisive evidence for it. `base_rates` (from `stage_base_rates` on the *pooled*
    frame, passed in by the caller rather than recomputed here — this function stays
    a pure function of its arguments) gives each stage's corpus-wide share; lift is
    the retrieved share divided by that base share, and `min_lift` (default 1.5,
    i.e. the retrieved rows must favour the stage at least 50% more than its base
    rate would predict on its own) must also be cleared. Omitting `base_rates`
    (`None`, the default) skips the lift check entirely, reproducing the
    share-only behaviour this function had before the check existed. A stage with
    no recorded base rate (or a zero one) cannot clear a lift requirement and fails
    closed — declining to infer is the safe default, per the module's stated
    preference throughout.
    """
    if "language_stage" not in result_df.columns or result_df.empty:
        return None
    normalized = result_df["language_stage"].map(normalize_stage).dropna()
    if len(normalized) < min_labelled:
        return None
    counts = Counter(normalized)
    stage, count = counts.most_common(1)[0]
    share = count / len(normalized)
    if share < min_share:
        return None
    if base_rates is not None:
        base = base_rates.get(stage, 0.0)
        if base <= 0.0 or (share / base) < min_lift:
            return None
    return stage


@dataclass(frozen=True)
class StageResources:
    """Everything built from a stage-compatible subset of the corpus.

    Mirrors exactly what `app/ui/whyptology_app.py` builds per corpus today
    (`load_search_index`, `load_reading_model`, `load_segmenter`/`resegment_query`,
    `load_sign_index`) — this is the same four/five constructors, run once on
    `compatible_frame(df, stage)` instead of on the full frame. `stage=None` yields
    resources byte-identical in behaviour to today's pooled build, because
    `compatible_frame(df, None)` is `df` itself.
    """

    stage: str | None
    frame: pd.DataFrame
    index: "SearchIndex"
    reading_model: "ReadingModel"
    segmenter: "Segmenter"
    sign_index: dict[str, "SignReadings"]
    # subset aligned-sign-token mass / pooled aligned-sign-token mass — see
    # `_aligned_sign_group_mass` and `build_stage_resources`. Exactly 1.0 at
    # stage=None (the subset IS the pooled frame there), reported so a caller can
    # audit what the lexicon weight was actually scaled to for this stage.
    lexicon_weight_factor: float = 1.0


def _aligned_sign_group_mass(frame: pd.DataFrame) -> int:
    """Total aligned sign-group tokens in `frame`.

    Exactly what `Segmenter.total` (the denominator of the discounted unigram model)
    would sum to for a `ReadingModel` fitted on `frame` — every position of every
    row whose hieroglyph and transliteration token counts match contributes one to
    `ReadingModel.fit`'s `sign_reading` counts, so this is that same total without
    the cost of actually fitting a model. Used only to scale `lexicon_weight` (see
    `build_stage_resources`); it deliberately mirrors `ReadingModel.fit`'s own
    alignment rule (`len(signs) == len(readings)`, `signs` non-empty) rather than
    re-deriving it, so the two can never quietly drift apart.
    """
    if "hieroglyphs_norm" not in frame.columns or "transliteration_gold" not in frame.columns:
        return 0
    signs = frame["hieroglyphs_norm"].astype(str).str.split()
    readings = frame["transliteration_gold"].astype(str).str.split()
    sign_counts = signs.map(len)
    aligned = (sign_counts > 0) & (sign_counts == readings.map(len))
    return int(sign_counts[aligned].sum())


def build_stage_resources(
    df: pd.DataFrame,
    target: str | None,
    lexicon: "Lexicon | None" = None,
    segmentation_weights: "SegmentationWeights | None" = None,
    use_lexicon: bool = True,
) -> StageResources:
    """Build `StageResources` for `target` from `df`, subsetting first.

    `lexicon` is accepted rather than loaded here (as `train_reading_model` and the
    UI's own `load_reading_model` already do) so that a caller passing the same
    lexicon it always passed gets exactly today's pooled behaviour at `target=None`.

    Lexicon-weight scaling. `SegmentationWeights.lexicon_weight` was calibrated
    (see `app/services/segmentation.py`'s module docstring) against the *pooled*
    corpus's group-count mass. Subsetting to a stage shrinks that mass — a declared
    stage excludes a whole other labelled population — while the lexicon's own
    counts do not shrink with it, which is exactly the failure mode the segmentation
    module documents for `lexicon_weight=0.39` at full corpus size: the lexicon's
    fixed weight can outbid a real, well-attested corpus split once the corpus mass
    it is being compared against gets smaller. The fix is not a new constant: scale
    `lexicon_weight` by this subset's aligned-sign-token mass relative to the pooled
    frame's, so the lexicon's *effective* weight shrinks in step with the corpus
    mass it competes against. At `target=None` the subset IS the pooled frame, so
    the factor is exactly 1.0 and pooled behaviour is unchanged by construction.
    """
    # Imported here, not at module scope: app.services.retrieval imports this module
    # (for build_stage_resources' own use in retrieve_with_stage), so a top-level
    # import back into retrieval.py would be circular.
    from app.services.reading_model import train_reading_model
    from app.services.retrieval import build_search_index
    from app.services.segmentation import DEFAULT_SEGMENTATION_WEIGHTS, Segmenter
    from app.services.signs import build_sign_index

    weights = (
        segmentation_weights if segmentation_weights is not None else DEFAULT_SEGMENTATION_WEIGHTS
    )
    frame = compatible_frame(df, target)

    lexicon_weight_factor = 1.0
    if use_lexicon and target is not None:
        pooled_mass = _aligned_sign_group_mass(df)
        subset_mass = _aligned_sign_group_mass(frame)
        if pooled_mass > 0:
            lexicon_weight_factor = subset_mass / pooled_mass
    if lexicon_weight_factor != 1.0:
        weights = weights.replace(lexicon_weight=weights.lexicon_weight * lexicon_weight_factor)

    reading_model = train_reading_model(frame, lexicon)
    segmenter = Segmenter(reading_model, weights, use_lexicon=use_lexicon)
    return StageResources(
        stage=target,
        frame=frame,
        index=build_search_index(frame),
        reading_model=reading_model,
        segmenter=segmenter,
        sign_index=build_sign_index(frame),
        lexicon_weight_factor=lexicon_weight_factor,
    )

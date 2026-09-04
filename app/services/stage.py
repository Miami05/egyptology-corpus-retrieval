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


def infer_stage(
    result_df: pd.DataFrame,
    min_labelled: int = 3,
    min_share: float = 0.7,
) -> str | None:
    """Guess a query's stage from the stages of its retrieved rows.

    Considers only rows whose `language_stage` normalises to a known stage (unlabelled
    rows say nothing about which stage the query belongs to, so they are dropped
    rather than counted as a fourth "unknown" bucket). Returns the majority stage only
    when there is enough labelled evidence (`min_labelled` rows) and it is decisive
    enough (`min_share` of the labelled rows) — both thresholds are conservative on
    purpose: a wrong inferred stage silently narrows the evidence a query sees, which
    is worse than declining to infer. Pure function of the frame; no I/O.
    """
    if "language_stage" not in result_df.columns or result_df.empty:
        return None
    normalized = result_df["language_stage"].map(normalize_stage).dropna()
    if len(normalized) < min_labelled:
        return None
    counts = Counter(normalized)
    stage, count = counts.most_common(1)[0]
    if count / len(normalized) >= min_share:
        return stage
    return None


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
    reading_model = train_reading_model(frame, lexicon)
    segmenter = Segmenter(reading_model, weights, use_lexicon=use_lexicon)
    return StageResources(
        stage=target,
        frame=frame,
        index=build_search_index(frame),
        reading_model=reading_model,
        segmenter=segmenter,
        sign_index=build_sign_index(frame),
    )

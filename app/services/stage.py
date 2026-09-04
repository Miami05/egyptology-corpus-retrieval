"""Language-stage awareness (item A): keep other-stage rows from outvoting evidence.

Why this exists. `language_stage` is a per-row corpus column, but every statistic the
ranker and the reading model use — token IDF, sign->reading counts, segmenter group
counts — was pooled across all stages. Late Egyptian (Ramses, 40k rows) and Demotic
(TLA, 13k rows) spell differently from Middle/Earlier Egyptian, and once they are
loaded they are numerous enough to outvote the evidence a Middle Egyptian paste
actually needs (ROADMAP.md, "Item 4 landed 2026-09-04" and "Fri 09-04, night").

The fix here is not a nested per-stage counter inside each statistic. It is simpler:
subset the corpus frame to the rows compatible with a target stage, and build the
*existing* statistics (`SearchIndex`, `ReadingModel`, the sign index) on that subset,
exactly as they are built on the full frame today. `target=None` must subset to
nothing — the full frame — so the pooled behaviour is reproduced exactly.

One statistic is the deliberate exception: the `Segmenter` is always built from the
*pooled* frame regardless of `target` (see `build_stage_resources`) — sign-group
boundaries measured far more stable across stages than spellings/readings do, and
restricting them to a subset was the direct cause of a segmentation-driven miss
(fewer attested groups survive a subset, so a lattice merges spans a full-corpus
segmenter keeps apart). "Segment pooled, read by stage."

Two-thirds of the corpus carries no stage at all (`Unspecified (AES)`,
`Unspecified (BBAW)`, or a blank column). Those rows are compatible with every
target stage: excluding them would starve every stage of the bulk of the corpus for
no reason, since an unlabelled row was never the thing that outvoted the evidence —
a large *labelled* population of a different stage was.

Stage as a *preference*, not a filter (ROADMAP.md, "Item A closed" -> "Open after
A" -> "Still to be done", step 4). Measured problem: on the 130k corpus, COMP_014's
target is a Middle Kingdom (Earlier Egyptian) row whose two useful-family parallels
are Late Egyptian formula rows (`TLA_LATE_783`, `TLA_LATE_1324`) -- formulaic
phrases cross language stages, so a *correct* Earlier Egyptian declaration was
excluding real evidence from `compatible_frame`'s candidate pool. Retrieval must not
do that; reading must (that is what made the paste gate pass, and it is unaffected
here). So `StageResources.frame`/`.index.text_index` (the candidate pool and its
n-gram index) are now always the *pooled* frame/index, for every stage including a
concrete one -- `compatible_frame` itself is unchanged and is still what a stage's
`reading_model` (and the segmenter's shared pooled build) are computed from. Only
`index.stats` (the per-token document-frequency counts `combine_scores` uses for
the IDF-overlap signal) stays stage-restricted, built from `compatible_frame(df,
target)` -- a query is still weighted by its own stage's vocabulary (rare in that
stage's rows counts as rare), it just is no longer prevented from matching a
cross-stage row that carries the shared evidence. `target=None` is unaffected by
any of this: `compatible_frame(df, None)` is `df`, so the "restricted" stats and the
pooled stats are the same computation on the same rows either way.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

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


# TLA source-id prefix -> stage. A TLA row names its own stage in its id, so this
# takes priority over the period-keyword table below. Moved here (from
# scripts/run_competitive_ambiguity_eval.py, which originated it for the v4
# benchmark's `language_stage` column) so `derive_v4_declared_stage` there and
# `derive_stage_from_period` here share one table rather than two that could
# quietly drift apart.
_TLA_PREFIX_STAGE: list[tuple[str, str]] = [
    ("TLA_EARLIER_", "Earlier Egyptian"),
    ("TLA_LATE_", "Late Egyptian"),
    ("TLA_DEMOTIC_", "Demotic"),
]

# `period` keyword -> stage, consulted only when the TLA prefix rule above did not
# resolve (AES, BBAW rows have no TLA-style id). A period string resolves only when
# every keyword it contains maps to the *same* stage: "Middle Kingdom / Second
# Intermediate Period" matches two keywords that both mean Earlier Egyptian, so it
# resolves; "Third Intermediate Period to Roman" matches one Late Egyptian keyword
# and one Demotic keyword, so it does not — that row's real period spans two
# stages, and guessing which one it actually is would not be a documented rule, it
# would be a guess. Zero keyword matches (e.g. "unknown") also does not resolve.
_PERIOD_STAGE_KEYWORDS: list[tuple[str, str]] = [
    ("Old Kingdom", "Earlier Egyptian"),
    ("First Intermediate", "Earlier Egyptian"),
    ("Middle Kingdom", "Earlier Egyptian"),
    ("Second Intermediate", "Earlier Egyptian"),
    ("New Kingdom", "Late Egyptian"),
    ("Third Intermediate", "Late Egyptian"),
    ("Late Period", "Late Egyptian"),
    ("Ptolemaic", "Demotic"),
    ("Roman", "Demotic"),
]


def derive_stage_from_period(source_text_id: object, period: object) -> str | None:
    """A stage derived from a row's own id/period, when its `language_stage`
    column does not name one.

    The documented rule the v4 benchmark's `language_stage` column was built with
    (`scripts/run_competitive_ambiguity_eval.py`'s `derive_v4_declared_stage`,
    which now simply calls this): a TLA source-id prefix first (`_TLA_PREFIX_STAGE`
    — it already names its own stage); otherwise the `period` text via
    `_PERIOD_STAGE_KEYWORDS`, resolved only when every keyword it contains agrees
    on one stage. `None` (leave unresolved) for anything else — a missing period,
    an unrecognised one, or one whose keywords disagree.

    Used only to populate that one precomputed benchmark column, not at load time.
    An item A part 3 iteration tried also using it inside `compatible_frame`/
    `infer_stage`/`stage_base_rates` (a derived row would gain a stage for both
    filtering and inference) and reverted it, on the reasoning that turning a
    previously-"compatible with everything" unspecified row into an excluded one
    changes retrieval evidence and should be a considered, separate design step —
    stage as a *preference*, not a filter — rather than a side effect of a
    load-time convenience. (P's own `declared` v4 accuracy was re-measured after
    the revert and did NOT recover to a higher number: it stayed at the same
    0.90/COMP_007+COMP_014 both before and after this function was wired into
    those three functions and unwired again — that shortfall predates this
    function entirely, from the v4 CSV's own precomputed `language_stage` column
    already declaring a stage for COMP_014's target once `compatible_frame`
    restricts evidence to it, on the unmodified `dda12fc` code. An earlier report
    misattributed that shortfall to this function; it does not cause it.)
    """
    text = "" if source_text_id is None else str(source_text_id)
    for prefix, stage in _TLA_PREFIX_STAGE:
        if text.startswith(prefix):
            return stage
    period_text = "" if period is None else str(period)
    stages = {stage for keyword, stage in _PERIOD_STAGE_KEYWORDS if keyword in period_text}
    if len(stages) == 1:
        return stages.pop()
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
    """A stage's resources: stage-restricted reading, pooled retrieval (preference,
    not filter — see the module docstring's "Stage as a preference" section).

    `frame` is always the *pooled* corpus (`compatible_frame(df, None)`, i.e. `df`
    itself), for every `stage` including a concrete one — retrieval's candidate
    pool never shrinks, so a formulaic parallel from a different stage stays
    reachable. `index` (a `SearchIndex`) mirrors that split: `index.text_index`
    (the n-gram index the cosine/tfidf signal reads) is the pooled one too, but
    `index.stats` (the per-token document frequencies `combine_scores` uses for the
    IDF-overlap signal) is built from `compatible_frame(df, stage)` — a query is
    still weighted by its own stage's vocabulary, only the candidate pool it can
    match against is unrestricted. `reading_model` stays exactly as before: trained
    on `compatible_frame(df, stage)`, because reading (unlike retrieval) is right
    to filter — a cross-stage spelling must not be offered as this stage's reading.
    `sign_index` is also built from the pooled frame: nothing in retrieval or
    reading reads `StageResources.sign_index` today (the one page that shows sign
    multivalence, `app/ui/whyptology_app.py`'s "Sign readings & multivalence" view,
    calls `load_sign_index` on the corpus directly rather than through a stage's
    resources), so there is no reading behaviour to preserve by restricting it, and
    building it from the same already-pooled frame avoids a second, wasted subset
    pass. `stage=None` reproduces today's pooled build exactly at every field,
    because `compatible_frame(df, None)` is `df` for both the frame and the stats.

    `segmenter` is unaffected by any of the above: it is always built from the
    *pooled* frame, regardless of `stage` — see `build_stage_resources`.
    """

    stage: str | None
    frame: pd.DataFrame
    index: "SearchIndex"
    reading_model: "ReadingModel"
    segmenter: "Segmenter"
    sign_index: dict[str, "SignReadings"]
    # Always 1.0. Kept (rather than removed) for interface stability: it used to
    # scale SegmentationWeights.lexicon_weight down for a stage subset, back when
    # the segmenter's own group counts were stage-restricted too and so competed
    # against a shrunken mass. Now that the segmenter is always built from the
    # pooled frame (see build_stage_resources), the mass it competes against
    # never shrinks, so there is nothing left to scale.
    lexicon_weight_factor: float = 1.0


def build_stage_resources(
    df: pd.DataFrame,
    target: str | None,
    lexicon: "Lexicon | None" = None,
    segmentation_weights: "SegmentationWeights | None" = None,
    use_lexicon: bool = True,
    pooled_reading_model: "ReadingModel | None" = None,
    pooled_index: "SearchIndex | None" = None,
) -> StageResources:
    """Build `StageResources` for `target` from `df`. Read by stage, retrieved pooled.

    `lexicon` is accepted rather than loaded here (as `train_reading_model` and the
    UI's own `load_reading_model` already do) so that a caller passing the same
    lexicon it always passed gets exactly today's pooled behaviour at `target=None`.

    Stage as a preference, not a filter (see the module docstring). `reading_model`
    is trained on `compatible_frame(df, target)`, the stage-restricted subset,
    exactly as before — reading is right to filter. Retrieval is not: `frame` is
    always `df` (the pooled corpus, at every `target`), and `index.text_index` (the
    n-gram index) is built from `df` too; only `index.stats` — the document
    frequencies `combine_scores` reads for the IDF-overlap signal — is built from
    the stage-restricted subset, so a query is still weighted by its own stage's
    vocabulary without losing a cross-stage row as a candidate. At `target=None`
    the subset IS `df`, so every field here is unchanged from today's pooled build.

    `segmenter`, like before, is always built from the *pooled* corpus's group
    counts, never the subset's — measured reason: word/sign-group boundaries are
    far more stable across language stages than spellings and readings are
    (segmentation came out byte-identical across all three stages on every one of
    the eight expert Urk. IV pastes tried), while restricting the segmenter's own
    group counts to one stage's subset is what caused the one segmentation-driven
    miss item A core measured (`declared` mode's PASTE_003 on the Earlier-Egyptian-
    only subset: fewer attested three-way splits survive the cut, so the lattice
    merges groups a full-corpus segmenter would keep apart). Building the segmenter
    from the pooled frame also means `SegmentationWeights.lexicon_weight`
    (calibrated against the *pooled* corpus's group-count mass, see
    `app/services/segmentation.py`) is competing against that same pooled mass
    regardless of `target` — the mass never shrinks, so no lexicon-weight scaling
    is needed any more (`lexicon_weight_factor` is always 1.0; a shrinking-mass
    rescale was this module's own prior fix for a problem that segmenting pooled
    now removes at the source).

    `sign_index` is built from the pooled frame too (see `StageResources`'s own
    docstring for why: nothing reads a stage's `sign_index` today).

    `pooled_reading_model`, if given, is used to build the pooled segmenter
    directly instead of re-fitting one from `df` — a caller that already built
    (and cached) the `target=None` `StageResources` should pass its
    `reading_model` here so three per-stage builds do not each re-fit the whole
    corpus just to build a segmenter. Ignored when `target is None`: the subset IS
    `df` there, so the just-fitted `reading_model` already *is* the pooled one.

    `pooled_index`, if given, is used for its `.text_index` instead of rebuilding
    the n-gram index from `df` — the same shortcut as `pooled_reading_model`, for
    the same reason: `index.text_index` no longer depends on `target` (it is
    always the pooled n-gram index), so a caller holding the `target=None`
    `StageResources` already has it built and should pass `.index` in rather than
    have every concrete stage rebuild an identical index from scratch. Ignored
    when `target is None`, for the same reason as `pooled_reading_model`.
    """
    # Imported here, not at module scope: app.services.retrieval imports this module
    # (for build_stage_resources' own use in retrieve_with_stage), so a top-level
    # import back into retrieval.py would be circular.
    from app.retrieval.scorer import build_corpus_stats
    from app.retrieval.tfidf import NgramIndex
    from app.services.reading_model import train_reading_model
    from app.services.retrieval import SearchIndex
    from app.services.segmentation import DEFAULT_SEGMENTATION_WEIGHTS, Segmenter
    from app.services.signs import build_sign_index

    weights = (
        segmentation_weights if segmentation_weights is not None else DEFAULT_SEGMENTATION_WEIGHTS
    )
    stage_subset = compatible_frame(df, target)
    reading_model = train_reading_model(stage_subset, lexicon)

    if target is None:
        pooled_model = reading_model
    elif pooled_reading_model is not None:
        pooled_model = pooled_reading_model
    else:
        pooled_model = train_reading_model(df, lexicon)
    segmenter = Segmenter(pooled_model, weights, use_lexicon=use_lexicon)

    if target is not None and pooled_index is not None:
        text_index = pooled_index.text_index
    else:
        text_index = NgramIndex.build(df["mdc_norm"])
    index = SearchIndex(stats=build_corpus_stats(stage_subset), text_index=text_index)

    return StageResources(
        stage=target,
        frame=df,
        index=index,
        reading_model=reading_model,
        segmenter=segmenter,
        sign_index=build_sign_index(df),
        lexicon_weight_factor=1.0,
    )


def choose_stage_by_likelihood(
    paste_hieroglyphs_norm: str,
    resources_by_stage: Callable[[str | None], StageResources],
) -> tuple[str | None, dict[str, float]]:
    """Language identification for a hieroglyph paste, by per-sign log-likelihood.

    Why this exists (item A part 3). `infer_stage` reads stage labels off the
    pooled top-k hits, which fails a paste like Camilla's Urk. IV line once a
    large labelled population of a different stage (Ramses' Late Egyptian) is in
    the corpus: too few labelled hits clear it, or the wrong stage does. A
    hieroglyph paste is not text — it has no reading of its own to match against
    a stage's rows — but the reading model already computes how likely a stage's
    own statistics find a candidate reading of it, and that generalises language
    identification directly, without inventing a new score or a new threshold.

    Segmentation is not part of the comparison. `build_stage_resources` now
    builds the segmenter from the *pooled* frame for every stage (measured
    reason on that function), so `resources_by_stage(candidate).segmenter` is
    the same segmenter regardless of `candidate` — segmenting is done exactly
    once here, via the pooled resources, rather than once per candidate stage.
    An earlier version of this function included each stage's own
    `Segmentation.score` in the comparison; it was dropped because that score is
    a raw, corpus-size-dependent count (a bigger corpus reports bigger counts for
    the same common sign group regardless of dialect fit — Late Egyptian's
    corpus, being far larger, was winning on that alone even where its own
    *reading* was worse), which the reading model's terms below are not: every
    `ReadingModel` emission/transition/context term is a conditional probability
    normalised by its own local count (`_emission`'s denominator is that one
    sign group's own total, not the corpus's), so it does not grow with corpus
    size.

    For each concrete stage in `STAGES`: read the (pooled, shared) segmentation
    with that stage's own reading model — `ReadingModel.predict_sequence_scored`,
    `use_lexicon=False` (the external Helsinki lexicon is stage-agnostic, so
    letting a lexicon-only group decide the *stage* would be evidence from the
    wrong place; reading happens afterwards, once a stage is chosen, on that
    stage's full resources including the lexicon, exactly as every other item A
    path already does) — and take its Viterbi path log-probability, normalised
    by the number of sign groups in that (shared) segmentation. The winner is a
    plain argmax over these per-sign likelihoods: no tunable threshold.

    Two guards: (1) a stage whose reading model was fitted on zero aligned rows
    (`reading_model.sentences_seen == 0` — e.g. Demotic, which this corpus holds
    as text-only rows with no hieroglyphs to align) has nothing to score with and
    is skipped rather than scored as if it had an opinion. (2) a near-tie between
    the top two candidates (within 1e-9) is not trusted to decide a language —
    ties fall back to `None`, so the caller uses the pooled/label-based path
    instead of a coin flip.

    Returns `(winning stage or None, {stage: per-sign log-likelihood})` — the
    dict covers every *scored* (non-degenerate) stage, in `STAGES` order, so a
    caller can print/audit the comparison that decided (or declined to decide)
    the choice.
    """
    groups_as_pasted = paste_hieroglyphs_norm.split()
    if not groups_as_pasted:
        return None, {}

    pooled = resources_by_stage(None)
    groups = pooled.segmenter.segment(groups_as_pasted).groups
    n_groups = len(groups)
    if n_groups == 0:
        return None, {}

    scores: dict[str, float] = {}
    for candidate in STAGES:
        resources = resources_by_stage(candidate)
        if resources.reading_model.sentences_seen == 0:
            # Degenerate: no aligned rows to fit a reading model on (this corpus
            # holds Demotic as text-only), so this stage has no likelihood to
            # offer and must not be scored as though it did.
            continue
        _predictions, reading_score = resources.reading_model.predict_sequence_scored(
            groups, use_lexicon=False
        )
        scores[candidate] = reading_score / n_groups

    if not scores:
        return None, scores
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if len(ranked) > 1 and abs(ranked[0][1] - ranked[1][1]) <= 1e-9:
        return None, scores
    return ranked[0][0], scores

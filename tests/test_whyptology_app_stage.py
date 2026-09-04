"""Item A, UI half: the workspace's language-stage control.

`app/ui/whyptology_app.py` is importable without a Streamlit runtime (see
`tests/test_private_corpus.py`), so the pure helpers here are tested directly on
the module, and `st.cache_resource` caches are cleared around any test that
touches one — a stale entry from another test could otherwise return the wrong
object and make the identity assertions meaningless.

What is covered:

- the ?stage= <-> internal-value <-> selectbox-label round trip
- `load_stage_resources(None, ...)` reuses the app's own pooled loaders, object
  for object, rather than building a second, memory-doubling copy
  (`app/services/stage.py`'s `build_stage_resources(df, None, ...)` would
  reproduce the pooled *behaviour* exactly but as new objects — this is the guard
  that the UI's own wrapper does not do that)
- `load_stage_resources(<a declared stage>, ...)` really does call into
  `app.services.stage.build_stage_resources`, which restricts the *reading* model
  to the stage but keeps retrieval's candidate pool pooled (stage as a preference)
- the four caption strings `stage_caption` can produce
- `evidence_stage_label`'s normalisation, including the "stage not recorded"
  fallback for every unspecified shape the corpus uses
"""

from __future__ import annotations

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import app.ui.whyptology_app as w
from app.services.stage import STAGES

APP_PATH = "app/ui/whyptology_app.py"


# ---------- fixtures ----------


@pytest.fixture()
def clear_stage_caches():
    """Clear every `st.cache_resource` this module's tests can populate.

    Run before *and* after: a prior test in the same process may have already
    warmed a cache keyed on a signature/stage pair this test also uses.
    """

    def _clear():
        w.load_stage_resources.clear()
        w.load_search_index.clear()
        w.load_reading_model.clear()
        w.load_segmenter.clear()
        w.load_sign_index.clear()

    _clear()
    yield
    _clear()


def _two_stage_corpus() -> pd.DataFrame:
    """A sign group ('A') attested only in an Earlier Egyptian row, and one ('B')
    attested only in a Late Egyptian row — the same shape `tests/test_stage.py`
    uses for `build_stage_resources` itself, reused here to check the app's own
    wrapper wires up to it correctly."""
    return pd.DataFrame(
        [
            {
                "hieroglyphs_norm": "A",
                "transliteration_gold": "x",
                "language_stage": "Earlier Egyptian",
                "source_text_id": "T0",
                "source_sentence_id": "S0",
                "mdc_norm": "x",
            },
            {
                "hieroglyphs_norm": "B",
                "transliteration_gold": "y",
                "language_stage": "Late Egyptian",
                "source_text_id": "T1",
                "source_sentence_id": "S1",
                "mdc_norm": "y",
            },
        ]
    )


# ---------- stage <-> display <-> ?stage= round trip ----------


def test_stage_display_options_are_auto_then_stages_then_all():
    assert w.STAGE_DISPLAY_OPTIONS == ["Auto", *STAGES, "All (no stage)"]


@pytest.mark.parametrize(
    "internal",
    ["auto", None, "Earlier Egyptian", "Late Egyptian", "Demotic"],
)
def test_stage_internal_display_round_trip(internal):
    display = w.stage_internal_to_display(internal)
    assert w.stage_display_to_internal(display) == internal


@pytest.mark.parametrize(
    "internal,param",
    [
        ("auto", "auto"),
        (None, "all"),
        ("Earlier Egyptian", "Earlier Egyptian"),
        ("Late Egyptian", "Late Egyptian"),
        ("Demotic", "Demotic"),
    ],
)
def test_stage_internal_param_round_trip(internal, param):
    assert w.stage_internal_to_param(internal) == param
    assert w.stage_param_to_internal(param) == internal


@pytest.mark.parametrize("bogus", [None, "", "not-a-stage", "AUTO", "All"])
def test_stage_param_to_internal_defaults_unknown_to_auto(bogus):
    # A missing, empty, or hand-edited/stale ?stage= must not silently restrict
    # the search to nothing found — "auto" is the same safe default the
    # selectbox itself opens on.
    assert w.stage_param_to_internal(bogus) == "auto"


# ---------- stage_caption: the four states ----------


def test_stage_caption_all_is_silent():
    assert w.stage_caption(None, None, False) is None
    # A declared/auto stage_used must not leak a caption when the request itself
    # was "All" — the function trusts `requested`, not `stage_used`.
    assert w.stage_caption(None, "Earlier Egyptian", False) is None


def test_stage_caption_declared():
    assert (
        w.stage_caption("Earlier Egyptian", "Earlier Egyptian", False)
        == "Restricted to Earlier Egyptian and rows without a stage label."
    )
    assert (
        w.stage_caption("Demotic", "Demotic", False)
        == "Restricted to Demotic and rows without a stage label."
    )


def test_stage_caption_auto_inferred():
    assert (
        w.stage_caption("auto", "Late Egyptian", True)
        == "Stage inferred: Late Egyptian — change"
    )


def test_stage_caption_auto_found_nothing():
    assert (
        w.stage_caption("auto", None, False)
        == "No stage could be inferred; showing all stages."
    )


def test_stage_caption_auto_fails_safe_with_no_stage_even_if_inferred_is_set():
    # `resolve_ui_stage` never actually returns inferred=True alongside
    # stage_used=None (inferred is only True when infer_stage picked a concrete
    # stage), but the caption function is not told that invariant holds — it must
    # not claim a stage name that isn't there.
    assert (
        w.stage_caption("auto", None, True)
        == "No stage could be inferred; showing all stages."
    )


# ---------- evidence_stage_label ----------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Earlier Egyptian", "Earlier Egyptian"),
        ("Late Egyptian", "Late Egyptian"),
        ("Demotic", "Demotic"),
        ("Unspecified (AES)", "stage not recorded"),
        ("Unspecified (BBAW)", "stage not recorded"),
        ("", "stage not recorded"),
        (None, "stage not recorded"),
        (float("nan"), "stage not recorded"),
        ("Middle Kingdom", "stage not recorded"),
    ],
)
def test_evidence_stage_label(raw, expected):
    assert w.evidence_stage_label(raw) == expected


# ---------- load_stage_resources: the no-duplicate guarantee ----------


def test_load_stage_resources_pooled_reuses_the_pooled_loaders(clear_stage_caches):
    df = _two_stage_corpus()
    signature = w.corpus_signature(df)

    pooled = w.load_stage_resources(None, signature, df)

    assert pooled.stage is None
    assert pooled.frame is df
    assert pooled.index is w.load_search_index(df, signature)
    reading_model = w.load_reading_model(signature, df)
    assert pooled.reading_model is reading_model
    assert pooled.segmenter is w.load_segmenter(signature, reading_model)
    assert pooled.sign_index is w.load_sign_index(df, signature)

    # And the cache itself: asking twice returns the identical StageResources.
    assert w.load_stage_resources(None, signature, df) is pooled


def test_load_stage_resources_declared_stage_subsets_the_corpus(clear_stage_caches):
    df = _two_stage_corpus()
    signature = w.corpus_signature(df)

    resources = w.load_stage_resources("Earlier Egyptian", signature, df)

    assert resources.stage == "Earlier Egyptian"
    # Retrieval's candidate pool is always the pooled frame -- stage is a
    # preference, not a filter, for retrieval (ROADMAP.md, "Item A closed" ->
    # "Still to be done", step 4) -- so both rows are present, not just the
    # Earlier Egyptian one.
    assert len(resources.frame) == 2
    assert resources.frame is df
    # The reading model, unlike retrieval, IS stage-restricted: the Late Egyptian
    # row is a *known* different stage, so its reading is excluded.
    assert "A" in resources.reading_model.sign_reading
    assert "B" not in resources.reading_model.sign_reading
    # The segmenter, unlike the reading model, is always built from the POOLED
    # frame (app.services.stage.build_stage_resources) — segment pooled, read by
    # stage — so it knows "B" too even though this stage would never offer it as
    # a reading.
    assert resources.segmenter.is_known("A")
    assert resources.segmenter.is_known("B")

    # A declared stage is never routed through the pooled loaders.
    pooled = w.load_stage_resources(None, signature, df)
    assert resources.index is not pooled.index
    assert resources.reading_model is not pooled.reading_model


def test_load_stage_resources_is_cached_per_stage(clear_stage_caches):
    df = _two_stage_corpus()
    signature = w.corpus_signature(df)
    first = w.load_stage_resources("Late Egyptian", signature, df)
    second = w.load_stage_resources("Late Egyptian", signature, df)
    assert first is second


# ---------- ?stage= deep link, end to end (AppTest) ----------


def _query_param(app: AppTest, name: str) -> str | None:
    """AppTest hands query parameters back as lists; the app sets scalars."""
    if name not in app.query_params:
        return None
    raw = app.query_params[name]
    return raw[0] if isinstance(raw, list) else raw


def _stage_selectbox(app: AppTest):
    return next(s for s in app.selectbox if s.label == "Language stage")


def test_stage_defaults_to_auto_with_no_link():
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["view"] = "workspace"
    app.run()
    assert not app.exception
    assert _stage_selectbox(app).value == "Auto"
    assert "stage" not in app.query_params


def test_stage_deep_link_sets_the_selectbox_on_arrival():
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["q"] = "htp di nsw"
    app.query_params["stage"] = "Earlier Egyptian"
    app.run()
    assert not app.exception
    assert app.session_state["page"] == "Workspace"
    assert _stage_selectbox(app).value == "Earlier Egyptian"


def test_stage_deep_link_ignores_a_bogus_value():
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["view"] = "workspace"
    app.query_params["stage"] = "Not A Stage"
    app.run()
    assert not app.exception
    assert _stage_selectbox(app).value == "Auto"


def test_a_declared_stage_search_writes_the_stage_query_param():
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["view"] = "workspace"
    app.run()
    _stage_selectbox(app).set_value("Demotic").run(timeout=240)
    app.text_area[0].set_value("htp di nsw").run(timeout=240)
    [b for b in app.button if b.label.startswith("Suggest top")][0].click().run(
        timeout=240
    )
    assert not app.exception
    assert _query_param(app, "stage") == "Demotic"
    assert any(
        c.value == "Restricted to Demotic and rows without a stage label."
        for c in app.caption
    )


def test_selecting_all_stages_writes_the_all_query_param_and_shows_no_caption():
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["view"] = "workspace"
    app.run()
    _stage_selectbox(app).set_value("All (no stage)").run(timeout=240)
    app.text_area[0].set_value("htp di nsw").run(timeout=240)
    [b for b in app.button if b.label.startswith("Suggest top")][0].click().run(
        timeout=240
    )
    assert not app.exception
    assert _query_param(app, "stage") == "all"
    stage_captions = [
        "Restricted to",
        "Stage inferred:",
        "No stage could be inferred",
    ]
    assert not any(
        any(prefix in c.value for prefix in stage_captions) for c in app.caption
    )

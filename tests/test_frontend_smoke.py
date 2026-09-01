from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = "app/ui/whyptology_app.py"


def run_app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=120).run()


def click_button(app: AppTest, label: str) -> AppTest:
    next(button for button in app.button if button.label == label).click()
    return app.run(timeout=120)


def assert_clean(app: AppTest) -> None:
    assert not app.exception


def test_all_enabled_sidebar_destinations_render() -> None:
    app = run_app()
    assert_clean(app)

    destinations = [
        ("▤  Text workspace", "Workspace"),
        ("⌕  Corpus explorer", "Corpus"),
        ("◇  Projects", "Projects"),
        ("✓  Reviews", "Reviews"),
        ("𓂀  Sign readings", "Signs"),
        ("⌂  Home", "Home"),
    ]
    for label, page in destinations:
        app = click_button(app, label)
        assert app.session_state["page"] == page
        assert_clean(app)


def test_home_links_have_working_query_parameter_destinations() -> None:
    expected_pages = {
        "home": "Home",
        "workspace": "Workspace",
        "corpus": "Corpus",
        "projects": "Projects",
        "reviews": "Reviews",
        "signs": "Signs",
    }

    for view, expected_page in expected_pages.items():
        app = AppTest.from_file(APP_PATH, default_timeout=120)
        app.query_params["view"] = view
        app.run()
        assert app.session_state["page"] == expected_page
        assert_clean(app)


def test_sidebar_navigation_works_after_arriving_via_a_deep_link() -> None:
    """The hero buttons open ?view=... in a new tab, so that is how most visitors
    arrive. The sidebar has to keep working from there.

    Regression guard: the ?view= handler runs on every rerun, so leaving the
    parameter in the URL overwrote whatever the sidebar buttons set and pinned the
    page permanently — the click appeared to do nothing.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.query_params["view"] = "corpus"
    app.run()
    assert app.session_state["page"] == "Corpus"
    assert "view" not in app.query_params, "the deep link must be consumed, not kept"
    assert_clean(app)

    for label, expected_page in [
        ("▤  Text workspace", "Workspace"),
        ("✓  Reviews", "Reviews"),
        ("⌂  Home", "Home"),
    ]:
        app = click_button(app, label)
        assert app.session_state["page"] == expected_page
        assert_clean(app)


def test_corpus_table_paginates_and_uses_the_transliteration_font() -> None:
    """The corpus table is hand-rendered HTML, not st.dataframe.

    st.dataframe draws on a canvas and ignores CSS font-family, so the Egyptological
    characters rendered as empty boxes in the reading column. HTML can use the font,
    but it cannot virtualise 12,772 rows, so it has to page — and paging is easy to
    get subtly wrong (off-by-one slices, a stepper that resets every rerun).
    """
    import re

    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.query_params["view"] = "corpus"
    app.run()
    assert_clean(app)

    def table_html(a: AppTest) -> str:
        for md in a.markdown:
            if 'class="corpus-table"' in md.value:
                return md.value
        raise AssertionError("corpus table markup not rendered")

    first_page = table_html(app)
    assert 'class="corpus-cell-reading"' in first_page, (
        "reading cells must carry the class the transliteration font is bound to"
    )
    assert re.search(r"TLA_EARLIER_0*1\b", first_page)

    # Page 4 of 50-row pages starts at record 151.
    app = app.number_input[0].set_value(4).run()
    assert_clean(app)
    fourth_page = table_html(app)

    assert "TLA_EARLIER_151" in fourth_page
    assert "TLA_EARLIER_001" not in fourth_page, "paging must replace rows, not append"
    assert any("Showing 151–200" in c.value for c in app.caption)


def test_workspace_empty_search_is_handled_without_an_exception() -> None:
    app = click_button(run_app(), "▤  Text workspace")
    search = next(
        button for button in app.button if button.label.startswith("Suggest top")
    )
    search.click()
    app.run(timeout=120)

    assert_clean(app)
    assert any(
        "Enter a transliteration" in warning.value for warning in app.warning
    )


def test_corpus_search_can_be_changed_repeatedly() -> None:
    app = click_button(run_app(), "⌕  Corpus explorer")
    app.text_input[0].input("Hetep")
    app.run(timeout=120)
    assert_clean(app)
    assert any("matching corpus records" in item.value for item in app.caption)

    app.text_input[0].input("nonexistent-zzzz")
    app.run(timeout=120)
    assert_clean(app)
    assert any(
        item.value == "0 matching corpus records" for item in app.caption
    )


def test_mobile_breakpoints_cover_navigation_and_dense_views() -> None:
    css = Path("app/ui/whyptology_theme.css").read_text(encoding="utf-8")

    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 520px)" in css
    assert 'button[data-testid="stExpandSidebarButton"]' in css
    assert ".hero-actions" in css
    assert ".st-key-corpus_table" in css
    assert ".st-key-corpus_cards" in css
    assert ".project-grid" in css
    assert ".workspace-head {\n    flex-direction: column;" in css
    assert "min-height: 2.75rem;" in css
    assert "flex-wrap: wrap;" in css


def test_one_click_populates_every_tab():
    """Regression: after Phase 3 removed the post-search st.rerun(), the tabs kept
    reading `results`/`suggestions`/`top_row` captured *before* the search wrote them,
    so a visitor had to click Suggest twice. Every tab must be populated after one.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["view"] = "workspace"
    app.run()
    app.text_area[0].set_value("𓆓𓂧 𓆑𓆓𓂧 𓀀 𓈖 𓏏𓈖𓏼 𓂋𓍿 𓀀 𓏼𓎟𓏏").run()
    [b for b in app.button if b.label.startswith("Suggest top")][0].click().run()
    assert_clean(app)
    text = "\n".join(m.value for m in app.markdown)
    assert text.count('class="suggestion-card"') >= 2, "suggestion cards missing"
    assert len(app.expander) >= 1, "corpus parallels missing"
    assert app.dataframe, "results table / analysis missing"
    stale = [i.value for i in app.info if i.value.startswith("Run a query")]
    assert not stale, f"tabs still showing pre-search placeholders: {stale}"


def test_palette_inserts_a_character_and_keeps_what_was_typed() -> None:
    """The click-to-insert row is the answer to "I don't have that keyboard", so it
    has to survive the query box living inside a form.

    Two earlier arrangements silently dropped every insert: a plain button outside
    the form (a widget inside a form ignores session-state writes from outside it),
    then a submit button whose callback tried to read the freshly submitted text.
    """
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["view"] = "workspace"
    app.run()
    app.text_area[0].set_value("aHa.n st").run()
    next(b for b in app.button if b.label == "ẖ").click().run()
    assert_clean(app)
    assert app.text_area[0].value == "aHa.n stẖ"


def workspace() -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["view"] = "workspace"
    app.run()
    return app


def heading_html(app: AppTest) -> str:
    for md in app.markdown:
        if 'class="workspace-title"' in md.value:
            return md.value
    raise AssertionError("workspace header not rendered")


def searched(app: AppTest) -> bool:
    text = "\n".join(m.value for m in app.markdown)
    return 'class="suggestion-card"' in text


def query_param(app: AppTest, name: str) -> str:
    """AppTest hands query parameters back as lists; the app sets scalars."""
    raw = app.query_params[name]
    return raw[0] if isinstance(raw, list) else raw


def test_example_button_fills_the_box_and_searches_in_one_click() -> None:
    """A blank box makes a first-time visitor guess a notation; the tester who
    reported "found nothing" had guessed one we mishandled. One click on a worked
    example must both show the text and run it."""
    app = workspace()
    next(b for b in app.button if b.label == "aHa.n stX Hr Dd").click().run()
    assert_clean(app)
    assert app.text_area[0].value == "aHa.n stX Hr Dd"
    assert searched(app), "the example must run the search, not only fill the box"
    assert any("Manuel de Codage" in c.value for c in app.caption)


def test_shared_link_runs_the_query_once_and_stays_in_the_url() -> None:
    """?q= lets an expert send "this one is wrong" as a link. It must run the search
    on arrival, land on the workspace, stay in the URL so the link remains copyable —
    and be consumed once, or the user could never type anything else."""
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["q"] = "ꜥḥꜥ.n stẖ ḥr ḏd n =f"
    app.run()
    assert_clean(app)
    assert app.session_state["page"] == "Workspace"
    assert app.text_area[0].value == "ꜥḥꜥ.n stẖ ḥr ḏd n =f"
    assert searched(app)
    assert query_param(app, "q") =="ꜥḥꜥ.n stẖ ḥr ḏd n =f"

    # Consumed: editing the box afterwards must not be overwritten by the link.
    app.text_area[0].set_value("htp di nsw").run()
    assert_clean(app)
    assert app.text_area[0].value == "htp di nsw"


def test_a_search_writes_a_shareable_query_parameter() -> None:
    app = workspace()
    app.text_area[0].set_value("htp di nsw").run()
    [b for b in app.button if b.label.startswith("Suggest top")][0].click().run()
    assert_clean(app)
    assert query_param(app, "q") =="htp di nsw"


def test_heading_names_the_top_result_in_the_same_run_as_the_search() -> None:
    """The header used to be rendered before the search block from stale session
    state, so results appeared under a title still saying "Enter a reading…"."""
    app = workspace()
    assert "Reading workspace" in heading_html(app)
    app.text_area[0].set_value("ꜥḥꜥ.n stẖ ḥr ḏd n =f").run()
    [b for b in app.button if b.label.startswith("Suggest top")][0].click().run()
    assert_clean(app)
    header = heading_html(app)
    assert "Reading workspace" not in header
    assert "Enter a reading to search the corpus" not in header
    assert "TLA_" in header, header


def test_ephemeral_storage_makes_the_annotation_form_read_only() -> None:
    """Locally the database is SQLite, which is exactly the deployed situation the
    gating exists for: a correction saved to a container-local file is lost at the
    next restart. Every annotation control must be disabled and the reason stated."""
    app = workspace()
    app.text_area[0].set_value("ꜥḥꜥ.n stẖ ḥr ḏd n =f").run()
    [b for b in app.button if b.label.startswith("Suggest top")][0].click().run()
    assert_clean(app)
    decisions = [s for s in app.selectbox if s.label == "Decision"]
    assert decisions, "annotation form not rendered"
    assert all(s.disabled for s in decisions)
    fields = [t for t in app.text_input if t.label == "Transliteration"]
    assert fields and all(t.disabled for t in fields)
    assert any(
        "cannot be stored on this deployment" in w.value for w in app.warning
    )


def test_tab_labels_fit_a_phone() -> None:
    app = workspace()
    assert [t.label for t in app.tabs] == [
        "Readings", "Sign by sign", "Parallels", "Analysis", "Source",
    ]


def test_palette_has_nine_quiet_keys() -> None:
    app = workspace()
    keys = [b.label for b in app.button if len(b.label) == 1 and b.label.isalpha()]
    assert keys == ["ꜣ", "ꜥ", "ꞽ", "ḥ", "ḫ", "ẖ", "š", "ṯ", "ḏ"]
    assert any("Tap to insert" in c.value for c in app.caption)


def test_corpus_cards_offer_copyable_hieroglyphs() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["view"] = "corpus"
    app.run()
    assert_clean(app)
    assert any("copy hieroglyphs" in e.label for e in app.expander)
    assert app.code, "each card must render its hieroglyphs in a copyable block"


def test_translation_is_labelled_as_german_corpus_data() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["view"] = "corpus"
    app.run()
    table = next(md.value for md in app.markdown if 'class="corpus-table"' in md.value)
    assert "Translation (German, from the corpus)" in table


def test_the_query_box_and_the_search_button_submit_together() -> None:
    """Pins the "it gave me no response" bug: a bare text area only sends its value
    on blur, so the tap that blurred it was swallowed and the search never ran. The
    box and the button must belong to one form, whose submit carries both."""
    app = AppTest.from_file(APP_PATH, default_timeout=240)
    app.query_params["view"] = "workspace"
    app.run()
    assert app.text_area[0].form_id, "the query box must live in a form"
    search = next(b for b in app.button if b.label.startswith("Suggest top"))
    assert search.form_id == app.text_area[0].form_id, (
        "the search button must submit the same form as the query box"
    )

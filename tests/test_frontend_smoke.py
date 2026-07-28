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

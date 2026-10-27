"""Audit batch "ops" (A11, A12, A13, A19, A40-A43, A45, A46, A57).

Everything here runs against stubs: no systemd, B2, ntfy or live server is touched.
"""

from __future__ import annotations

import fcntl
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"


# ---------------------------------------------------------------------------
# A45 + A57: requirements split, pinned hieropy
# ---------------------------------------------------------------------------


def _requirement_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_app_requirements_hold_no_dev_or_import_tools():
    names = [
        re.split(r"[=<>\[ ]", line, maxsplit=1)[0].lower()
        for line in _requirement_lines(PROJECT_ROOT / "requirements.txt")
    ]
    for tool in ("pytest", "datasets", "hieropy"):
        assert tool not in names


def test_app_requirements_stay_exactly_pinned():
    for line in _requirement_lines(PROJECT_ROOT / "requirements.txt"):
        assert re.fullmatch(r"[A-Za-z0-9_.\-]+(\[[a-z,]+\])?==[0-9][^\s=<>]*", line), line


def test_dev_requirements_include_app_pins_and_a_pinned_hieropy():
    lines = _requirement_lines(PROJECT_ROOT / "requirements-dev.txt")
    assert lines[0] == "-r requirements.txt"
    assert any(line.startswith("pytest==") for line in lines)
    assert any(line.startswith("datasets") for line in lines)
    assert any(re.fullmatch(r"hieropy==\d+\.\d+\.\d+", line) for line in lines)


# ---------------------------------------------------------------------------
# A19: the public site must not show tracebacks
# ---------------------------------------------------------------------------


def test_streamlit_config_hides_error_details_and_keeps_the_light_theme():
    config = tomllib.loads((PROJECT_ROOT / ".streamlit" / "config.toml").read_text())
    assert config["client"]["showErrorDetails"] == "none"
    assert config["theme"]["base"] == "light"
    # Local hot-reload must keep working; the server turns the watcher off in its unit.
    assert "fileWatcherType" not in config.get("server", {})


# ---------------------------------------------------------------------------
# A43: the database path no longer depends on the current folder
# ---------------------------------------------------------------------------

from app.core.config import PROJECT_ROOT as CONFIG_ROOT  # noqa: E402
from app.core.config import resolve_database_url  # noqa: E402


@pytest.mark.parametrize(
    "given, expected",
    [
        ("sqlite:///egyptology.db", f"sqlite:///{CONFIG_ROOT}/egyptology.db"),
        ("sqlite:///egyptology.db?timeout=5", f"sqlite:///{CONFIG_ROOT}/egyptology.db?timeout=5"),
        ("sqlite:///data/x.db", f"sqlite:///{CONFIG_ROOT}/data/x.db"),
        ("sqlite:////abs/path/x.db", "sqlite:////abs/path/x.db"),
        ("sqlite://", "sqlite://"),
        ("sqlite:///:memory:", "sqlite:///:memory:"),
        ("sqlite:///file:x.db?mode=ro&uri=true", "sqlite:///file:x.db?mode=ro&uri=true"),
        ("postgres://u:pw@host/db", "postgres://u:pw@host/db"),
        ("postgresql+psycopg://u:pw@host/db", "postgresql+psycopg://u:pw@host/db"),
    ],
)
def test_resolve_database_url(given, expected):
    assert resolve_database_url(given) == expected


def test_resolve_database_url_uses_the_root_it_is_given(tmp_path):
    assert resolve_database_url("sqlite:///a.db", root=tmp_path) == f"sqlite:///{tmp_path}/a.db"


def _settings_from(cwd: Path, **env: str) -> subprocess.CompletedProcess:
    environment = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    environment.update(env)
    environment["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(
        [sys.executable, "-c", "from app.core.config import settings; print(settings.database_url)"],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_default_database_is_next_to_the_code_from_any_folder(tmp_path):
    result = _settings_from(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"sqlite:///{PROJECT_ROOT}/egyptology.db"
    assert f"database: {PROJECT_ROOT}/egyptology.db (from default next to the code)" in result.stderr


def test_explicit_database_url_is_reported_and_passes_through(tmp_path):
    result = _settings_from(tmp_path, DATABASE_URL=f"sqlite:///{tmp_path}/x.db")
    assert result.stdout.strip() == f"sqlite:///{tmp_path}/x.db"
    assert f"database: {tmp_path}/x.db (from DATABASE_URL)" in result.stderr


def test_a_postgres_url_prints_nothing_so_no_password_leaks(tmp_path):
    result = _settings_from(tmp_path, DATABASE_URL="postgres://user:secret@host/db")
    assert result.stdout.strip() == "postgres://user:secret@host/db"
    assert "secret" not in result.stderr and "database:" not in result.stderr


# ---------------------------------------------------------------------------
# A11: the warm-up fails when the app raises
# ---------------------------------------------------------------------------

from streamlit.proto.ForwardMsg_pb2 import ForwardMsg  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
import warm_streamlit  # noqa: E402


def _exception_msg(type_: str = "KeyError", message: str = "boom", is_warning: bool = False) -> ForwardMsg:
    forward = ForwardMsg()
    forward.delta.new_element.exception.type = type_
    forward.delta.new_element.exception.message = message
    forward.delta.new_element.exception.is_warning = is_warning
    return forward


def _markdown_msg(body: str, allow_html: bool = True) -> ForwardMsg:
    """Like the app's st.markdown(..., unsafe_allow_html=True) unless allow_html=False."""
    forward = ForwardMsg()
    forward.delta.new_element.markdown.body = body
    forward.delta.new_element.markdown.allow_html = allow_html
    return forward


def _element_msg(kind: str, body: str) -> ForwardMsg:
    forward = ForwardMsg()
    getattr(forward.delta.new_element, kind).body = body
    return forward


def test_inspect_forward_flags_an_exception_element():
    state = warm_streamlit.RunState()
    warm_streamlit.inspect_forward(_exception_msg(), state)
    assert state.exceptions == [("KeyError", "boom")]


def test_inspect_forward_still_flags_a_redacted_exception():
    """showErrorDetails="none" empties the type and genericises the message."""
    state = warm_streamlit.RunState()
    warm_streamlit.inspect_forward(
        _exception_msg(type_="", message="This app has encountered an error."), state
    )
    assert [kind for kind, _ in state.exceptions] == ["<redacted>"]


def test_inspect_forward_ignores_warning_style_exceptions_and_other_messages():
    state = warm_streamlit.RunState()
    warm_streamlit.inspect_forward(_exception_msg(is_warning=True), state)
    warm_streamlit.inspect_forward(ForwardMsg(), state)
    assert state.exceptions == []


def test_inspect_forward_recognises_the_expected_text():
    state = warm_streamlit.RunState(expect_text="suggestion-card")
    warm_streamlit.inspect_forward(_markdown_msg("nothing here"), state)
    assert not state.expect_seen
    warm_streamlit.inspect_forward(_markdown_msg('<div class="suggestion-card">x</div>'), state)
    assert state.expect_seen


def test_inspect_forward_ignores_the_expected_text_inside_a_stylesheet():
    """Regression for the A11 review: the app injects its theme on every page, and the
    theme names `.suggestion-card`, so a page with no result used to count as one."""
    for expect in ("suggestion-card", 'class="suggestion-card"'):
        state = warm_streamlit.RunState(expect_text=expect)
        warm_streamlit.inspect_forward(
            _markdown_msg('<style>.suggestion-card { color: red; }\n/* class="suggestion-card" */</style>'), state
        )
        warm_streamlit.inspect_forward(_markdown_msg('<STYLE media="all">.suggestion-card {}'), state)  # unclosed
        assert not state.expect_seen, expect
        warm_streamlit.inspect_forward(
            _markdown_msg('<style>.x {}</style><article class="suggestion-card">r</article>'), state
        )
        assert state.expect_seen, expect


_CARD = '<div class="suggestion-card">removed result</div>'


@pytest.mark.parametrize(
    "message",
    [
        _markdown_msg(f"<!-- {_CARD} -->"),                                  # commented out
        _markdown_msg(f"<p>before</p><!-- {_CARD}"),                         # unclosed comment
        _element_msg("text", _CARD),                                         # st.text shows it literally
        _markdown_msg(_CARD, allow_html=False),                              # escaped, shown as text
        _markdown_msg('<p>the class="suggestion-card" attribute</p>'),       # text, not a tag
        _markdown_msg(f"<textarea>{_CARD}</textarea>"),                      # not drawn as markup
        _markdown_msg(f"<script>var s = '{_CARD}';</script>"),
        _markdown_msg(f"<template>{_CARD}</template>"),
        _markdown_msg('<style class="suggestion-card">.x {}</style>'),
    ],
    ids=["comment", "unclosed-comment", "text-element", "markdown-no-html", "plain-text",
         "textarea", "script", "template", "style-tag"],
)
def test_an_attribute_expectation_needs_a_real_rendered_start_tag(message):
    """Regression for Astra's round-2 A11 finding: a substring check passed on a commented-out
    card and on the card's markup shown as plain text."""
    state = warm_streamlit.RunState(expect_text='class="suggestion-card"')
    warm_streamlit.inspect_forward(message, state)
    assert not state.expect_seen


@pytest.mark.parametrize(
    "message",
    [
        _markdown_msg('<article class="suggestion-card">r</article>'),
        _markdown_msg("<div class='suggestion-card rank-1'>r</div>"),       # one of several classes
        _element_msg("html", "<!-- old --><textarea></textarea>" + _CARD),
    ],
    ids=["markdown", "class-list", "html-element"],
)
def test_an_attribute_expectation_passes_on_a_real_result(message):
    state = warm_streamlit.RunState(expect_text='class="suggestion-card"')
    warm_streamlit.inspect_forward(message, state)
    assert state.expect_seen


@pytest.mark.parametrize(
    "body",
    [
        f"see `{_CARD}` here",                                              # inline code
        f"``{_CARD} with ` inside``",                                       # longer backtick run
        f"text\n\n```html\n{_CARD}\n```\n",                               # fenced code
        f"~~~\n{_CARD}\n~~~",                                              # tilde fence
        f"```\n{_CARD}",                                                    # unclosed fence
        f"intro\n\n    {_CARD}",                                            # indented code block
        f"    {_CARD}",                                                     # indented at the start
    ],
    ids=["inline", "double-backtick", "fenced", "tilde-fence", "unclosed-fence", "indented", "indented-start"],
)
def test_an_attribute_expectation_ignores_markdown_code(body):
    """Regression for Astra's round-3 A11 finding: the HTML parser saw raw Markdown, so a
    card tag shown as code (which Streamlit draws as text) counted as a rendered result."""
    state = warm_streamlit.RunState(expect_text='class="suggestion-card"')
    warm_streamlit.inspect_forward(_markdown_msg(body), state)
    assert not state.expect_seen


@pytest.mark.parametrize(
    "body",
    [
        f"> ~~~\n> {_CARD}\n> ~~~",                                       # fence in a block quote
        f">     {_CARD}",                                                 # indented code in a quote
        f"> intro\n>\n>     {_CARD}",
        f"- item\n\n  ```\n  {_CARD}\n  ```",                         # fence in a list item
        f"- ```\n  {_CARD}",
        f"- item\n\n      {_CARD}",                                     # indented code in a list item
        f"> ~~~\n~~~\n{_CARD}",                                         # quote ends, a new fence opens
        f"# Heading\n    {_CARD}",                                       # indented code after a heading
        f"Title\n===\n    {_CARD}",
        '<div class="sug`x`gestion-card">r</div>',                         # attribute around a code span
        'see <span class="sug`x`gestion-card">r</span>',
        "a <div class=sug`x`gestion-card>r</div>",
        '[a](<div class="suggestion-card">)',                              # a link destination
        '\\<div class="suggestion-card">r',                               # an escaped `<`
        # Astra's 0f8a052 review: dash setext underlines, balanced link destinations, images
        f"Title\n--\n    {_CARD}",                                        # dash setext heading
        f"Title\n-\n    {_CARD}",
        f"> Title\n> --\n>     {_CARD}",
        f"- Title\n  --\n      {_CARD}",
        '[x](url(foo) "<span class=\'suggestion-card\'>r</span>")',       # a link title
        "[x](a(b(c)) '<span class=\"suggestion-card\">r</span>')",
        '![<span class="suggestion-card">r</span>](image.png)',            # an image description
        '![a <b title="]"> <span class="suggestion-card">r</span>](i.png)',
        '![<span class="suggestion-card">r</span>][ref]\n\n[ref]: i.png',
        '[a]: <x class="suggestion-card">\n---',                          # a definition, not a heading
        '[a]: <x class="suggestion-card">\n===',
    ],
    ids=["quote-fence", "quote-indented", "quote-indented-later", "list-fence", "list-item-fence",
         "list-indented", "quote-then-fence", "heading-indented", "setext-indented",
         "synth-quoted", "synth-inline", "synth-unquoted", "link-destination", "escaped",
         "setext-dash", "setext-one-dash", "setext-dash-quote", "setext-dash-list",
         "link-title-parens", "link-title-nested-parens", "image-alt", "image-alt-bracket-in-tag",
         "image-alt-reference", "definition-then-dashes", "definition-then-equals"],
)
def test_an_attribute_expectation_ignores_code_in_containers_and_never_joins_attributes(body):
    """Regression for Astra's round-3 A11 re-review: code inside block quotes and list items
    still counted, and cutting code spans out of the raw text put `class="suggestion-card"`
    together from `class="sug`x`gestion-card"`."""
    state = warm_streamlit.RunState(expect_text='class="suggestion-card"')
    warm_streamlit.inspect_forward(_markdown_msg(body), state)
    assert not state.expect_seen


@pytest.mark.parametrize(
    "body",
    [
        # what render_suggestion_card sends: dedented, nested lines indented 2 and 4 spaces
        '<article class="suggestion-card">\n  <div class="suggestion-head">\n'
        '    <span class="suggestion-rank">1</span>\n  </div>\n</article>',
        f"`code` first\n\n{_CARD}",
        f"```\ncode\n```\n{_CARD}",
        f"> {_CARD}",                                                       # Markdown containers render HTML
        f"- {_CARD}",
        f"- ~~~\n  x\n  ~~~\n\n{_CARD}",                                  # a closed fence in a list
        'text `x` <span class="suggestion-card">r</span>',                 # a tag after a code span
        f"para\n    {_CARD}",                                              # paragraph continuation, not code
        f'[x](url(foo) "t") {_CARD}',                                      # after a balanced link
        f"![alt](i.png) {_CARD}",                                          # after an image
        f"[{_CARD}](url(foo))",                                            # link text renders HTML
        f"Title\n--\n\n{_CARD}",                                         # after a dash setext heading
    ],
    ids=["app-card", "after-inline-code", "after-fence", "in-quote", "in-list", "after-list-fence",
         "after-code-span", "continuation", "after-link", "after-image", "in-link-text",
         "after-setext-dash"],
)
def test_a_card_outside_markdown_code_still_counts(body):
    state = warm_streamlit.RunState(expect_text='class="suggestion-card"')
    warm_streamlit.inspect_forward(_markdown_msg(body), state)
    assert state.expect_seen


def test_a_plain_expectation_ignores_comments():
    state = warm_streamlit.RunState(expect_text="suggestion-card")
    warm_streamlit.inspect_forward(_markdown_msg(f"<!-- {_CARD} -->"), state)
    assert not state.expect_seen


# Like the real app, the probe injects a stylesheet naming the result class on every run.
_PROBE_APP = textwrap.dedent(
    '''
    import streamlit as st

    st.markdown("<style>.suggestion-card { border: 1px solid; }</style>", unsafe_allow_html=True)
    mode = st.query_params.get("q", "")
    if mode == "boom":
        raise KeyError("renamed_column")
    elif mode == "card":
        st.markdown('<div class="suggestion-card">a result</div>', unsafe_allow_html=True)
    elif mode == "comment":
        st.markdown('<!-- <div class="suggestion-card">removed</div> -->', unsafe_allow_html=True)
    elif mode == "as-text":
        st.text('<div class="suggestion-card">shown as text</div>')
    elif mode == "rerun":
        if not st.session_state.get("did_rerun"):
            st.session_state["did_rerun"] = True
            st.rerun()
        st.markdown('<div class="suggestion-card">after rerun</div>', unsafe_allow_html=True)
    else:
        st.write("plain page")
    '''
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module", params=["details-default", "details-none"])
def probe_server(request, tmp_path_factory):
    import urllib.request

    app = tmp_path_factory.mktemp("probe") / "probe_app.py"
    app.write_text(_PROBE_APP)
    port = _free_port()
    environment = dict(os.environ)
    if request.param == "details-none":
        # The env spelling of `[client] showErrorDetails`; STREAMLIT_CLIENT_SHOWERRORDETAILS is ignored.
        environment["STREAMLIT_CLIENT_SHOW_ERROR_DETAILS"] = "none"
    process = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", str(app),
            "--server.port", str(port), "--server.address", "127.0.0.1",
            "--server.headless", "true", "--browser.gatherUsageStats", "false",
        ],
        cwd=app.parent,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.skip("streamlit could not start the probe app here")
        try:
            urllib.request.urlopen(url + "/_stcore/health", timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    else:
        process.kill()
        pytest.skip("streamlit never answered on a local port")
    yield url
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _warm(url: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "warm_streamlit.py"), "--url", url, "--timeout", "60", *extra],
        capture_output=True,
        text=True,
        timeout=90,
    )


def test_warm_up_fails_when_the_app_raises(probe_server):
    """Regression for A11: this used to print FINISHED_SUCCESSFULLY and exit 0."""
    result = _warm(probe_server, "--query", "boom")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "raised an exception" in result.stderr


def test_warm_up_passes_a_plain_run_and_a_run_that_renders_the_expected_text(probe_server):
    assert _warm(probe_server, "--query", "card").returncode == 0
    ok = _warm(probe_server, "--query", "card", "--expect-text", "suggestion-card")
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_warm_up_fails_when_the_expected_text_never_appears(probe_server):
    """The page carries the stylesheet naming the class, but no result element."""
    for expect in ("suggestion-card", 'class="suggestion-card"'):
        result = _warm(probe_server, "--query", "none-here", "--expect-text", expect)
        assert result.returncode == 1, expect
        assert "never rendered" in result.stderr


def test_warm_up_passes_with_the_deploy_scripts_exact_expectation(probe_server):
    expect = re.search(r"^EXPECT_TEXT='(.+)'$", DEPLOY_SCRIPT.read_text(), re.M).group(1)
    result = _warm(probe_server, "--query", "card", "--expect-text", expect)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["comment", "as-text"])
def test_warm_up_fails_on_result_markup_that_is_not_a_rendered_result(probe_server, mode):
    expect = re.search(r"^EXPECT_TEXT='(.+)'$", DEPLOY_SCRIPT.read_text(), re.M).group(1)
    result = _warm(probe_server, "--query", mode, "--expect-text", expect)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "never rendered" in result.stderr


def test_warm_up_waits_through_a_rerun_when_text_is_expected(probe_server):
    result = _warm(probe_server, "--query", "rerun", "--expect-text", "suggestion-card")
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# A13 + A42 + A43: backup_db.sh
# ---------------------------------------------------------------------------

import gzip  # noqa: E402
import shutil  # noqa: E402
import sqlite3  # noqa: E402

BACKUP_SCRIPT = SCRIPTS / "backup_db.sh"


def _make_db(path: Path, examples: int = 10, annotations: int = 5) -> Path:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE examples (id INTEGER PRIMARY KEY, text TEXT)")
    connection.execute("CREATE TABLE annotations (id INTEGER PRIMARY KEY, note TEXT)")
    connection.executemany("INSERT INTO examples (text) VALUES (?)", [(f"e{i}",) for i in range(examples)])
    connection.executemany("INSERT INTO annotations (note) VALUES (?)", [(f"a{i}",) for i in range(annotations)])
    connection.commit()
    connection.close()
    return path


def _stub(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


@pytest.fixture
def backup_env(tmp_path):
    """A scratch DB, a backup folder, and stub curl/rclone that log their arguments."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    curl_log = tmp_path / "curl.log"
    rclone_log = tmp_path / "rclone.log"
    _stub(stubs / "curl", f'echo "$@" >> "{curl_log}"\n')
    _stub(
        stubs / "rclone",
        f'echo "$@" >> "{rclone_log}"\n'
        'if [ "$1" = delete ] && [ -n "$RCLONE_FAIL_DELETE" ]; then exit 1; fi\n',
    )
    db = _make_db(tmp_path / "live.db")
    backups = tmp_path / "backups"

    class Env:
        pass

    env = Env()
    env.tmp, env.db, env.backups = tmp_path, db, backups
    env.curl_log, env.rclone_log = curl_log, rclone_log
    env.rclone = stubs / "rclone"

    def run(stamp: str, *, db_arg: bool = True, **extra: str) -> subprocess.CompletedProcess:
        environment = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "DB_PATH", "OFFSITE_TARGET")}
        environment.update(
            PATH=f"{stubs}:{os.environ['PATH']}",
            PYTHON=sys.executable,
            BACKUP_DIR=str(backups),
            BACKUP_STAMP=stamp,
            RCLONE=str(env.rclone),
        )
        environment.update(extra)
        command = ["bash", str(BACKUP_SCRIPT)]
        if db_arg:
            command.append(str(db))
        return subprocess.run(command, env=environment, capture_output=True, text=True, timeout=120)

    env.run = run
    return env


def _archive_counts(archive: Path) -> tuple[int, int]:
    scratch = archive.parent / "restored-check.db"
    scratch.write_bytes(gzip.decompress(archive.read_bytes()))
    connection = sqlite3.connect(scratch)
    counts = tuple(connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("examples", "annotations"))
    connection.close()
    scratch.unlink()
    return counts


def _age(path: Path, days: int) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_backup_script_passes_bash_n():
    assert subprocess.run(["bash", "-n", str(BACKUP_SCRIPT)]).returncode == 0


def test_backup_happy_path_writes_the_archive_and_a_monthly_copy(backup_env):
    result = backup_env.run("2026-01-10")
    assert result.returncode == 0, result.stderr
    archive = backup_env.backups / "egyptology-2026-01-10.db.gz"
    assert _archive_counts(archive) == (10, 5)
    assert (backup_env.backups / "monthly" / "egyptology-2026-01.db.gz").is_file()
    assert "no earlier snapshot to compare" in result.stdout


def test_a_drop_in_annotations_fails_and_keeps_the_older_snapshots(backup_env):
    """Regression for A13: this used to exit 0 and let retention age the good copy out."""
    assert backup_env.run("2026-01-10").returncode == 0
    good = backup_env.backups / "egyptology-2026-01-10.db.gz"
    _age(good, 60)  # past retention: only the early exit keeps it
    connection = sqlite3.connect(backup_env.db)
    connection.execute("DELETE FROM annotations WHERE id > 2")
    connection.commit()
    connection.close()

    result = backup_env.run("2026-01-11")

    assert result.returncode == 3, result.stdout + result.stderr
    assert "annotations fell from 5 to 2" in result.stderr
    assert (backup_env.backups / "egyptology-2026-01-11.db.gz.suspect").is_file()
    assert not (backup_env.backups / "egyptology-2026-01-11.db.gz").exists()
    assert good.is_file(), "retention ran after a suspect snapshot"

    # The next night compares with the last GOOD snapshot again, not the suspect one.
    again = backup_env.run("2026-01-12")
    assert again.returncode == 3


def test_allow_annotation_drop_accepts_a_deliberate_deletion(backup_env):
    assert backup_env.run("2026-01-10").returncode == 0
    connection = sqlite3.connect(backup_env.db)
    connection.execute("DELETE FROM annotations")
    connection.commit()
    connection.close()
    result = backup_env.run("2026-01-11", ALLOW_ANNOTATION_DROP="1")
    assert result.returncode == 0, result.stderr
    assert _archive_counts(backup_env.backups / "egyptology-2026-01-11.db.gz") == (10, 0)


def test_examples_dropping_to_zero_fails_but_a_partial_drop_only_warns(backup_env):
    assert backup_env.run("2026-01-10").returncode == 0
    connection = sqlite3.connect(backup_env.db)
    connection.execute("DELETE FROM examples WHERE id > 4")
    connection.commit()
    connection.close()
    warned = backup_env.run("2026-01-11")
    assert warned.returncode == 0
    assert "examples fell from 10 to 4" in warned.stderr
    connection = sqlite3.connect(backup_env.db)
    connection.execute("DELETE FROM examples")
    connection.commit()
    connection.close()
    assert backup_env.run("2026-01-12").returncode == 3


def test_retention_spares_the_monthly_folder_and_removes_old_dailies(backup_env):
    assert backup_env.run("2026-01-10").returncode == 0
    monthly = backup_env.backups / "monthly" / "egyptology-2026-01.db.gz"
    old_daily = backup_env.backups / "egyptology-2025-01-01.db.gz"
    shutil.copy(monthly, old_daily)
    _age(monthly, 400)
    _age(old_daily, 400)
    assert backup_env.run("2026-02-10").returncode == 0
    assert monthly.is_file()
    assert not old_daily.exists()
    assert (backup_env.backups / "monthly" / "egyptology-2026-02.db.gz").is_file()


def test_offsite_prune_is_depth_limited_and_never_fatal(backup_env):
    result = backup_env.run(
        "2026-01-10", OFFSITE_TARGET="b2:bucket/path", RCLONE_FAIL_DELETE="1"
    )
    assert result.returncode == 0, result.stderr
    log = backup_env.rclone_log.read_text().splitlines()
    assert any(line.startswith("delete b2:bucket/path --max-depth 1 ") for line in log)
    assert any(line.startswith(f"copy {backup_env.backups}/monthly b2:bucket/path/monthly ") for line in log)
    assert "off-site prune failed" in result.stderr


def test_offsite_prune_can_be_switched_off(backup_env):
    result = backup_env.run("2026-01-10", OFFSITE_TARGET="b2:bucket/path", OFFSITE_PRUNE="0")
    assert result.returncode == 0, result.stderr
    assert not any(line.startswith("delete") for line in backup_env.rclone_log.read_text().splitlines())


def test_healthcheck_pings_success_and_fail(backup_env):
    ok = backup_env.run("2026-01-10", HEALTHCHECK_URL="https://hc.example/ping/abc")
    assert ok.returncode == 0
    assert backup_env.curl_log.read_text().strip().endswith("https://hc.example/ping/abc")

    backup_env.curl_log.unlink()
    missing = backup_env.run("2026-01-11", HEALTHCHECK_URL="https://hc.example/ping/abc/", DB_PATH=str(backup_env.tmp / "nope.db"), db_arg=False)
    assert missing.returncode == 1
    assert backup_env.curl_log.read_text().strip().endswith("https://hc.example/ping/abc/fail")


def test_a_broken_healthcheck_never_changes_the_exit_code(backup_env):
    _stub(backup_env.tmp / "stubs" / "curl", "exit 22\n")
    result = backup_env.run("2026-01-10", HEALTHCHECK_URL="https://hc.example/ping/abc")
    assert result.returncode == 0
    assert "could not reach the health check URL" in result.stderr


def test_the_database_path_comes_from_database_url_when_not_given(backup_env):
    other = _make_db(backup_env.tmp / "elsewhere.db", examples=3, annotations=1)
    result = backup_env.run("2026-01-10", db_arg=False, DATABASE_URL=f"sqlite:///{other}?timeout=5")
    assert result.returncode == 0, result.stderr
    assert _archive_counts(backup_env.backups / "egyptology-2026-01-10.db.gz") == (3, 1)


def _set_annotations(db: Path, count: int) -> None:
    connection = sqlite3.connect(db)
    connection.execute("DELETE FROM annotations")
    connection.executemany("INSERT INTO annotations (note) VALUES (?)", [(f"a{i}",) for i in range(count)])
    connection.commit()
    connection.close()


def test_a_same_day_rerun_never_overwrites_and_compares_with_todays_snapshot(backup_env):
    """Regression for the A13 review: the rerun deleted the day's archive first and
    compared with yesterday, so annotation 6 could vanish with exit 0."""
    assert backup_env.run("2026-01-09").returncode == 0               # 5 annotations
    _set_annotations(backup_env.db, 6)
    assert backup_env.run("2026-01-10").returncode == 0               # this morning: 6
    morning = backup_env.backups / "egyptology-2026-01-10.db.gz"
    _set_annotations(backup_env.db, 5)                                # the accidental deletion

    rerun = backup_env.run("2026-01-10")

    assert rerun.returncode == 3, rerun.stdout + rerun.stderr
    assert "annotations fell from 6 to 5" in rerun.stderr
    assert _archive_counts(morning) == (10, 6), "the only snapshot holding annotation 6 was replaced"
    assert (backup_env.backups / "egyptology-2026-01-10-r02.db.gz.suspect").is_file()
    assert not list(backup_env.backups.glob(".candidate-*"))


def test_an_accepted_same_day_rerun_is_published_beside_the_first(backup_env):
    assert backup_env.run("2026-01-10").returncode == 0
    _set_annotations(backup_env.db, 7)
    again = backup_env.run("2026-01-10")
    assert again.returncode == 0, again.stderr
    assert _archive_counts(backup_env.backups / "egyptology-2026-01-10.db.gz") == (10, 5)
    assert _archive_counts(backup_env.backups / "egyptology-2026-01-10-r02.db.gz") == (10, 7)
    # ...and the next comparison is against the rerun, the newest accepted snapshot.
    _set_annotations(backup_env.db, 6)
    assert backup_env.run("2026-01-11").returncode == 3


def test_an_unreadable_newest_snapshot_fails_closed(backup_env):
    assert backup_env.run("2026-01-09").returncode == 0
    old_good = backup_env.backups / "egyptology-2026-01-09.db.gz"
    _age(old_good, 60)                                                # retention would remove it
    (backup_env.backups / "egyptology-2026-01-10.db.gz").write_bytes(b"not gzip")
    _set_annotations(backup_env.db, 0)

    result = backup_env.run("2026-01-11", OFFSITE_TARGET="b2:bucket/path")

    assert result.returncode == 4, result.stdout + result.stderr
    assert "cannot read the newest accepted snapshot" in result.stderr
    assert (backup_env.backups / "egyptology-2026-01-11.db.gz.unverified").is_file()
    assert not (backup_env.backups / "egyptology-2026-01-11.db.gz").exists()
    assert old_good.is_file(), "retention ran without a readable baseline"
    assert not backup_env.rclone_log.exists()


def test_a_monthly_snapshot_is_a_baseline_when_no_daily_is_left(backup_env):
    assert backup_env.run("2026-01-10").returncode == 0
    (backup_env.backups / "egyptology-2026-01-10.db.gz").unlink()     # e.g. aged out
    _set_annotations(backup_env.db, 2)
    result = backup_env.run("2026-03-01")
    assert result.returncode == 3, result.stdout + result.stderr
    assert "compared with egyptology-2026-01.db.gz" in result.stderr


def test_an_emptied_backup_folder_is_not_mistaken_for_a_first_backup(backup_env):
    assert backup_env.run("2026-01-10").returncode == 0
    for archive in backup_env.backups.rglob("egyptology-*.db.gz"):
        archive.unlink()
    result = backup_env.run("2026-01-11")
    assert result.returncode == 4, result.stdout + result.stderr
    assert "none is left" in result.stderr
    assert (backup_env.backups / "egyptology-2026-01-11.db.gz.unverified").is_file()


def test_offsite_reconciles_every_retained_daily_and_monthly_archive(backup_env):
    """Regression for the A13 review: only the current month's file was ever sent, so a
    failed upload across a month boundary was never retried."""
    assert backup_env.run("2026-01-31").returncode == 0               # no off-site yet
    result = backup_env.run("2026-02-01", OFFSITE_TARGET="b2:bucket/path", OFFSITE_PRUNE="0")
    assert result.returncode == 0, result.stderr
    log = backup_env.rclone_log.read_text().splitlines()
    assert f"copy {backup_env.backups}/monthly b2:bucket/path/monthly --include egyptology-*.db.gz --checksum" in log
    assert f"copy {backup_env.backups} b2:bucket/path --max-depth 1 --include egyptology-*.db.gz --checksum" in log
    assert not any(line.startswith(("sync", "delete", "move")) for line in log)


def test_rsync_offsite_reconciles_dailies_and_the_whole_monthly_folder(backup_env, tmp_path):
    if shutil.which("rsync") is None:
        pytest.skip("no rsync here")
    target = tmp_path / "offsite"
    target.mkdir()
    assert backup_env.run("2026-01-31").returncode == 0
    result = backup_env.run("2026-02-01", OFFSITE_TARGET=f"{target}/")
    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in target.glob("egyptology-*.db.gz")) == [
        "egyptology-2026-01-31.db.gz", "egyptology-2026-02-01.db.gz"]
    assert sorted(path.name for path in (target / "monthly").iterdir()) == [
        "egyptology-2026-01.db.gz", "egyptology-2026-02.db.gz"]


class _Flock:
    """Hold the kernel lock another run would hold, from this test process."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(path, "a")
        fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def release(self) -> None:
        if not self.handle.closed:
            self.handle.close()


def test_a_backup_waits_for_a_running_one_and_never_publishes_beside_it(backup_env):
    """Regression for the round-2 A13 review (Astra blocker): two overlapping runs could
    pick the same name, and the later `mv -f` replaced an accepted snapshot."""
    lock = backup_env.backups / ".backup.lock"
    holder = _Flock(lock)
    try:
        result = backup_env.run("2026-01-10", LOCK_WAIT="1")
    finally:
        holder.release()
    assert result.returncode == 5, result.stdout + result.stderr
    assert "still holds" in result.stderr
    assert sorted(path.name for path in backup_env.backups.iterdir()) == [".backup.lock"]


def test_a_held_lock_is_never_broken_whatever_pid_it_names(backup_env):
    """Regression for Astra's round-3 A13 blocker: two runs could both read the same dead
    owner, one took the lock over, and the other then deleted that NEW owner's lock with
    its stale observation, so both ran. The kernel lock has no owner record to go stale:
    a file naming a dead pid, or an old-style lock directory, never lets a run past a
    live holder."""
    dead = subprocess.Popen(["true"])
    dead.wait()
    lock = backup_env.backups / ".backup.lock"
    holder = _Flock(lock)
    lock.write_text(f"{dead.pid}\n")
    (backup_env.backups / ".lock").mkdir()
    (backup_env.backups / ".lock" / "pid").write_text(f"{dead.pid}\n")
    try:
        result = backup_env.run("2026-01-10", LOCK_WAIT="1")
        assert lock.exists(), "the lock file was deleted"
    finally:
        holder.release()
    assert result.returncode == 5, result.stdout + result.stderr
    assert not list(backup_env.backups.glob("egyptology-*"))


def test_an_old_style_lock_directory_stops_the_run_and_is_kept(backup_env):
    """Regression for Astra's round-3 A13 re-review: the script before the flock one locked
    with a BACKUP_DIR/.lock directory and took no flock, so a run of it still going when
    the script was replaced could pick the same revision as a new run. Its directory is
    refused, not removed, whatever pid (or none) it records."""
    legacy = backup_env.backups / ".lock"
    legacy.mkdir(parents=True)
    (legacy / "pid").write_text(f"{os.getpid()}\n")                        # a live owner
    result = backup_env.run("2026-01-10", LOCK_WAIT="0")
    assert result.returncode == 5, result.stdout + result.stderr
    assert "old-style lock" in result.stderr
    assert (legacy / "pid").is_file(), "the old run's lock must not be deleted"
    assert not list(backup_env.backups.glob("egyptology-*"))
    shutil.rmtree(legacy)                                                  # once removed by hand
    assert backup_env.run("2026-01-10", LOCK_WAIT="0").returncode == 0


def test_a_backup_runs_once_the_other_run_releases_the_lock(backup_env):
    lock = backup_env.backups / ".backup.lock"
    holder = _Flock(lock)
    releaser = threading.Timer(2, holder.release)
    releaser.start()
    try:
        result = backup_env.run("2026-01-10", LOCK_WAIT="30")
    finally:
        releaser.cancel()
        holder.release()
    assert result.returncode == 0, result.stdout + result.stderr
    assert (backup_env.backups / "egyptology-2026-01-10.db.gz").is_file()
    assert lock.exists(), "the lock file must stay: deleting it is what let two runs both hold one"
    _Flock(lock).release()                                               # and it is free again


def test_a_lock_file_left_by_a_dead_run_does_not_block(backup_env):
    backup_env.backups.mkdir()
    (backup_env.backups / ".backup.lock").write_text("12345\n")
    result = backup_env.run("2026-01-10", LOCK_WAIT="0")
    assert result.returncode == 0, result.stdout + result.stderr


def test_simultaneous_runs_over_a_stale_lock_publish_one_snapshot_each(backup_env):
    """The race interleaving itself: several runs start together over a lock file a dead
    run left. Each must run alone, so each publishes its own revision and none is lost."""
    backup_env.run("2026-01-10")                                         # the day's first
    (backup_env.backups / ".backup.lock").write_text("12345\n")
    environment = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "DB_PATH", "OFFSITE_TARGET")}
    environment.update(
        PATH=f"{backup_env.rclone.parent}:{os.environ['PATH']}", PYTHON=sys.executable,
        BACKUP_DIR=str(backup_env.backups), BACKUP_STAMP="2026-01-10", LOCK_WAIT="60",
    )
    runs = [
        subprocess.Popen(["bash", str(BACKUP_SCRIPT), str(backup_env.db)], env=environment,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(4)
    ]
    outputs = [run.communicate(timeout=120)[0] for run in runs]
    assert [run.returncode for run in runs] == [0, 0, 0, 0], outputs
    published = sorted(path.name for path in backup_env.backups.glob("egyptology-2026-01-10*.db.gz"))
    assert len(published) == 5, published


def test_an_offsite_helper_left_running_does_not_keep_the_lock(backup_env, tmp_path):
    """rclone or rsync can leave a helper behind (an ssh ControlMaster); it must not
    inherit the lock, or every later run gives up with exit 5."""
    sleeper_pid = tmp_path / "sleeper.pid"
    lingering = _stub(
        tmp_path / "lingering-rclone",
        f'sleep 30 >/dev/null 2>&1 </dev/null &\necho $! >> "{sleeper_pid}"\nexit 0\n',
    )
    try:
        first = backup_env.run("2026-01-10", OFFSITE_TARGET="remote:bucket", RCLONE=str(lingering))
        assert first.returncode == 0, first.stdout + first.stderr
        second = backup_env.run("2026-01-11", LOCK_WAIT="1")
        assert second.returncode == 0, second.stdout + second.stderr
    finally:
        for pid in sleeper_pid.read_text().split() if sleeper_pid.exists() else []:
            try:
                os.kill(int(pid), 9)
            except ProcessLookupError:
                pass


def test_revisions_compare_as_numbers_past_r99(backup_env):
    """Regression for the round-2 A13 review: `-r100` sorted before `-r99`, and the first
    free gap was reused, so the baseline could be an older snapshot."""
    day = backup_env.backups
    assert backup_env.run("2026-01-10").returncode == 0                # 5 annotations
    _set_annotations(backup_env.db, 6)
    assert backup_env.run("2026-01-10").returncode == 0
    (day / "egyptology-2026-01-10-r02.db.gz").rename(day / "egyptology-2026-01-10-r99.db.gz")
    _set_annotations(backup_env.db, 7)
    assert backup_env.run("2026-01-10").returncode == 0
    assert _archive_counts(day / "egyptology-2026-01-10-r100.db.gz") == (10, 7)
    _set_annotations(backup_env.db, 6)                                 # annotation 7 deleted
    result = backup_env.run("2026-01-11")
    assert result.returncode == 3, result.stdout + result.stderr
    assert "compared with egyptology-2026-01-10-r100.db.gz" in result.stderr


def test_a_revision_number_is_never_reused_after_a_gap(backup_env):
    day = backup_env.backups
    assert backup_env.run("2026-01-10").returncode == 0
    _set_annotations(backup_env.db, 6)
    assert backup_env.run("2026-01-10").returncode == 0
    (day / "egyptology-2026-01-10-r02.db.gz").rename(day / "egyptology-2026-01-10-r03.db.gz")
    (day / "egyptology-2026-01-10-r04.db.gz.suspect").write_bytes(b"kept for a human")
    _set_annotations(backup_env.db, 7)
    assert backup_env.run("2026-01-10").returncode == 0
    assert _archive_counts(day / "egyptology-2026-01-10-r05.db.gz") == (10, 7)
    assert not (day / "egyptology-2026-01-10-r02.db.gz").exists()


@pytest.mark.parametrize("name", ["live%23.db", "live#x.db", "li ve%41.db"])
def test_the_python_snapshot_reads_exactly_the_named_file(backup_env, name):
    """Regression for the round-2 A43 review: the Python path put the file name straight
    into a SQLite URI, so `%23` decoded to `#` (another file) and `#` began a fragment."""
    target = _make_db(backup_env.tmp / name, examples=3, annotations=1)
    if "%" in name:                                     # the file a decoded URI would name
        _make_db(backup_env.tmp / name.replace("%23", "#").replace("%41", "A"), examples=8, annotations=4)
    result = backup_env.run("2026-01-10", db_arg=False, DB_PATH=str(target), SQLITE3="no-such-sqlite3-cli")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no sqlite3 CLI; snapshotting with" in result.stdout
    assert _archive_counts(backup_env.backups / "egyptology-2026-01-10.db.gz") == (3, 1)


@pytest.mark.parametrize(
    "url",
    ["sqlite:///rel/x.db", "sqlite+pysqlite:///rel/x.db?timeout=5", "sqlite:///{tmp}/abs.db"],
)
def test_the_backup_reads_database_url_the_way_the_app_does(backup_env, url):
    """Regression for A43: `sqlite+pysqlite:///` fell back to the default file."""
    url = url.format(tmp=backup_env.tmp)
    expected = resolve_database_url(url, root=backup_env.tmp).split(":///", 1)[1].split("?", 1)[0]
    Path(expected).parent.mkdir(parents=True, exist_ok=True)
    _make_db(Path(expected), examples=3, annotations=1)
    result = backup_env.run("2026-01-10", db_arg=False, DATABASE_URL=url, REPO_DIR=str(backup_env.tmp))
    assert result.returncode == 0, result.stderr
    assert f"backup: database {expected}" in result.stdout
    assert _archive_counts(backup_env.backups / "egyptology-2026-01-10.db.gz") == (3, 1)


@pytest.mark.parametrize(
    "url",
    ["postgresql+psycopg://user:secret@host/db", "sqlite:///:memory:", "sqlite://",
     "sqlite:///file:x.db?mode=ro&uri=true"],
)
def test_the_backup_refuses_a_database_url_it_cannot_back_up(backup_env, url):
    result = backup_env.run("2026-01-10", db_arg=False, DATABASE_URL=url)
    assert result.returncode == 1
    assert "refusing" in result.stderr
    assert "secret" not in result.stdout + result.stderr
    assert not list(backup_env.backups.glob("*")) if backup_env.backups.exists() else True


# ---------------------------------------------------------------------------
# A12 + A40 + A41 + A46 + A11: egyptology-deploy.sh (against stubs)
# ---------------------------------------------------------------------------

DEPLOY_SCRIPT = SCRIPTS / "egyptology-deploy.sh"
_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}


def _vcs(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, env={**os.environ, **_GIT_ENV}, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


class DeployBox:
    """A fake server: origin repo, a clone as the live tree, the original (real-directory)
    venv, a stub base interpreter that creates release venvs, stub systemctl."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.home = tmp / "home"
        self.work = tmp / "work"
        self.origin = tmp / "origin.git"
        self.repo = self.home / "egyptology"
        self.venv = self.home / "venvs" / "egyptology"
        self.releases = self.home / "venvs" / "egyptology-releases"
        self.calls = tmp / "calls.log"
        self.stubs = tmp / "stubs"
        self.calls.write_text("")
        self.home.mkdir()
        self.stubs.mkdir()

        self.work.mkdir()
        _vcs(self.work, "init", "-q", "-b", "main")
        self.write("requirements.txt", "streamlit==1.49.0\n")
        self.write("app.py", "v1\n")
        self.write("data/processed/examples.csv", "id\n1\n")
        self.write("deploy/systemd/egyptology.service", "[Service]\nExecStart=/bin/true\n")
        for name in ("backup_db.sh", "warm_streamlit.py", "import_examples.py"):
            self.write(f"scripts/{name}", f"# {name}\n")
        shutil.copy(DEPLOY_SCRIPT, self.work / "scripts" / "egyptology-deploy.sh")
        self.commit("v1")
        _vcs(tmp, "clone", "-q", "--bare", str(self.work), str(self.origin))
        _vcs(self.work, "remote", "add", "origin", str(self.origin))
        _vcs(tmp, "clone", "-q", str(self.origin), str(self.repo))

        # Every pip and python logs which venv it belongs to ($0).
        _stub(self.stubs / "venv-pip", 'echo "pip[$0] $*" >> "$CALL_LOG"\n'
              'if [ "$1" = freeze ]; then [ -n "$FAIL_FREEZE" ] && exit 1\n'
              '  printf "altair==5.0.0\\nStreamlit==1.49.0\\nprotobuf==6.31.1\\n"; exit 0; fi\n'
              'prev=""; for a in "$@"; do\n'
              '  [ "$prev" = -c ] && cp "$a" "$CALL_LOG.constraints"\n'
              '  [ "$prev" = -r ] && cp "$a" "$CALL_LOG.installed"\n'
              '  prev="$a"; done\n'
              '[ -n "$FAIL_PIP" ] && exit 1\nexit 0\n')
        _stub(self.stubs / "venv-python", 'echo "python[$0] $*" >> "$CALL_LOG"\n'
              'case "$*" in *warm_streamlit.py*)\n'
              '  [ "$FAIL_WARM" = always ] && exit 1\n'
              f'  [ -n "$FAIL_WARM" ] && grep -qx "$FAIL_WARM" "{self.repo}/app.py" && exit 1;;\n'
              'esac\n'
              'case "$*" in *import_examples.py*) [ -n "$FAIL_IMPORT" ] && exit 1;; esac\nexit 0\n')
        (self.venv / "bin").mkdir(parents=True)
        shutil.copy(self.stubs / "venv-pip", self.venv / "bin" / "pip")
        shutil.copy(self.stubs / "venv-python", self.venv / "bin" / "python")
        _stub(self.stubs / "base-python", 'echo "base-python $*" >> "$CALL_LOG"\n'
              '[ -n "$FAIL_VENV" ] && exit 1\n'
              f'mkdir -p "$3/bin" && cp "{self.stubs}/venv-pip" "$3/bin/pip" && cp "{self.stubs}/venv-python" "$3/bin/python"\n')
        # `show -p MainPID` (a read, not logged) names a fake process whose environment
        # lives under $PROC_DIR; by default it was started with the file watcher off.
        self.proc = tmp / "proc"
        self.set_running_environment("STREAMLIT_SERVER_FILE_WATCHER_TYPE=none")
        _stub(self.stubs / "systemctl",
              'if [ "$2" = show ]; then echo "${MAIN_PID-4242}"; exit 0; fi\n'
              '[ "$2" = start ] && [ -n "$SIGNAL_ON_START" ] && [ ! -e "$CALL_LOG.signalled" ] '
              '&& { touch "$CALL_LOG.signalled"; echo "systemctl $* (signalled)" >> "$CALL_LOG"; '
              'kill -"$SIGNAL_ON_START" "$PPID"; sleep 0.2; exit 1; }\n'
              f'echo "systemctl $* (head $(git -C "{self.repo}" rev-parse --short HEAD), '
              f'venv $(readlink "{self.venv}" || echo original))" >> "$CALL_LOG"\n'
              'case "$2" in\n'
              '  stop) [ -n "$FAIL_STOP" ] && exit 1;;\n'
              '  is-active) echo "${ACTIVE_STATE:-active}"; [ "${ACTIVE_STATE:-active}" = active ] || exit 3;;\n'
              'esac\nexit 0\n')
        _stub(self.stubs / "journalctl", 'echo "(journal)"\n')
        _stub(self.stubs / "curl", 'exit 0\n')

    def set_running_environment(self, *lines: str, pid: str = "4242") -> None:
        (self.proc / pid).mkdir(parents=True, exist_ok=True)
        (self.proc / pid / "environ").write_bytes(b"".join(line.encode() + b"\0" for line in ("HOME=/x", *lines)))

    def write(self, rel: str, text: str) -> None:
        path = self.work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message: str) -> str:
        _vcs(self.work, "add", "-A")
        _vcs(self.work, "commit", "-q", "-m", message)
        return _vcs(self.work, "rev-parse", "HEAD")

    def publish(self, message: str) -> str:
        sha = self.commit(message)
        _vcs(self.work, "push", "-q", "origin", "main")
        return sha

    def head(self) -> str:
        return _vcs(self.repo, "rev-parse", "HEAD")

    def log(self) -> list[str]:
        return self.calls.read_text().splitlines()

    def live_venv(self) -> str:
        return os.readlink(self.venv) if self.venv.is_symlink() else "original"

    def release_dirs(self) -> list[str]:
        return sorted(path.name for path in self.releases.iterdir()) if self.releases.exists() else []

    def _environment(self, extra: dict[str, str]) -> dict[str, str]:
        self.calls.write_text("")
        environment = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "STOP_BEFORE_UPDATE")}
        environment.update(
            _GIT_ENV, PATH=f"{self.stubs}:{os.environ['PATH']}", DEPLOY_HOME=str(self.home),
            CALL_LOG=str(self.calls), HEALTH_TRIES="2", HEALTH_INTERVAL="0", GIT_TERMINAL_PROMPT="0",
            BASE_PYTHON=str(self.stubs / "base-python"), LOCK_PYTHON=sys.executable,
            PROC_DIR=str(self.proc),
        )
        environment.update(extra)
        return environment

    def run(self, **extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(DEPLOY_SCRIPT)], env=self._environment(extra), capture_output=True, text=True, timeout=120
        )

    def start(self, **extra: str) -> subprocess.Popen:
        return subprocess.Popen(
            ["bash", str(DEPLOY_SCRIPT)], env=self._environment(extra),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )


@pytest.fixture
def deploy_box(tmp_path):
    return DeployBox(tmp_path)


def _calls_matching(box: DeployBox, text: str) -> list[str]:
    return [line for line in box.log() if text in line]


def test_deploy_script_passes_bash_n_and_has_no_shell_sourcing_or_grep_pipe():
    assert subprocess.run(["bash", "-n", str(DEPLOY_SCRIPT)]).returncode == 0
    code = "\n".join(
        line for line in DEPLOY_SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#")
    )
    assert not re.search(r"^\s*(source|\.)\s+\S*egyptology\.env", code, re.M)
    assert not re.search(r"git diff[^\n]*\|\s*grep", code)


def _source_and_run(snippet: str, **env: str) -> subprocess.CompletedProcess:
    environment = {**os.environ, **_GIT_ENV, **env}
    return subprocess.run(
        ["bash", "-c", f'source "{DEPLOY_SCRIPT}"; {snippet}'],
        env=environment, capture_output=True, text=True, timeout=120,
    )


def test_corpus_change_is_detected_even_in_a_huge_diff(deploy_box):
    """Regression for A41: with `git diff --name-only | grep -qx` under pipefail, a
    commit touching thousands of files could make the corpus check report 'unchanged'."""
    before = deploy_box.head()
    big = deploy_box.work / "zzz"
    big.mkdir()
    for index in range(4000):
        (big / f"file_{index:05d}_{'x' * 40}.txt").write_text("x")
    deploy_box.write("data/processed/examples.csv", "id\n1\n2\n")
    deploy_box.publish("corpus plus 4000 files")
    _vcs(deploy_box.repo, "pull", "-q", "--ff-only")
    after = deploy_box.head()
    for _ in range(5):
        assert _corpus_verdict(deploy_box, before, after) == "changed"


def _corpus_verdict(box: DeployBox, before: str, after: str) -> str:
    result = _source_and_run(
        f'corpus_changed "{before}" "{after}" && echo changed || echo unchanged',
        DEPLOY_HOME=str(box.home),
    )
    return result.stdout.strip()


def test_corpus_unchanged_is_reported_unchanged(deploy_box):
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("app only")
    _vcs(deploy_box.repo, "pull", "-q", "--ff-only")
    assert _corpus_verdict(deploy_box, before, deploy_box.head()) == "unchanged"


def test_load_env_file_keeps_values_literally(tmp_path):
    env_file = tmp_path / "egyptology.env"
    env_file.write_text(
        "# a comment\n"
        "\n"
        "REVIEWER_KEY=correct horse battery staple\n"
        "DOLLARS=pa$$word & more $HOME `x` $(y)\n"
        'QUOTED="in double quotes"\n'
        "SINGLE='in single quotes'\n"
        "  SPACED  =  padded value  \n"
        "not a valid line\n"
        "1BAD=skipped\n"
        "EMPTY=\n"
    )
    snippet = (
        f'load_env_file "{env_file}"; '
        'printf "[%s]\\n" "$REVIEWER_KEY" "$DOLLARS" "$QUOTED" "$SINGLE" "$SPACED" "${EMPTY-unset}"'
    )
    result = _source_and_run(snippet)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "[correct horse battery staple]",
        "[pa$$word & more $HOME `x` $(y)]",
        "[in double quotes]",
        "[in single quotes]",
        "[padded value]",
        "[]",
    ]


def test_a_failing_pip_leaves_the_tree_the_venv_and_the_service_untouched(deploy_box):
    """Regression for the A12/A45 review: pip installed into the running service's venv."""
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.write("requirements.txt", "streamlit==1.50.0\n")
    deploy_box.publish("v2")
    result = deploy_box.run(FAIL_PIP="1")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "untouched" in result.stderr
    assert deploy_box.head() == before
    assert (deploy_box.repo / "app.py").read_text() == "v1\n"
    assert _vcs(deploy_box.repo, "status", "--porcelain") == ""
    assert not _calls_matching(deploy_box, "systemctl")
    assert not _calls_matching(deploy_box, f"pip[{deploy_box.venv}/bin/pip] install")
    assert deploy_box.live_venv() == "original"
    assert deploy_box.release_dirs() == [], "the half-built release venv was left behind"
    # Recorded before anything changed, so the manual recovery has a target even now.
    assert (deploy_box.home / "egyptology-last-good").read_text().strip() == before


def test_a_successful_deploy_switches_to_a_release_venv_while_stopped(deploy_box):
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    after = deploy_box.publish("v2")
    result = deploy_box.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert deploy_box.head() == after
    # The live venv was never installed into; the service now runs a release venv.
    assert not _calls_matching(deploy_box, f"pip[{deploy_box.venv}/bin/pip] install")
    live = deploy_box.live_venv()
    assert Path(live).parent == deploy_box.releases and Path(live).name.startswith(after[:7])
    assert (Path(live) / ".egyptology-deps").is_file()
    # The original directory is kept, as the rollback target, and recorded as such.
    (original,) = [name for name in deploy_box.release_dirs() if name.startswith("original-")]
    assert (deploy_box.home / "egyptology-last-good").read_text().strip() == before
    assert (deploy_box.home / "egyptology-last-good-venv").read_text().strip() == str(deploy_box.releases / original)
    # stop -> switch -> start, never a restart with the venv changing underneath.
    service = [line for line in deploy_box.log() if line.startswith("systemctl --user")]
    assert service[0].startswith("systemctl --user stop egyptology.service") and service[0].endswith("venv original)")
    assert service[1].startswith("systemctl --user start egyptology.service") and service[1].endswith(f"venv {live})")
    assert not _calls_matching(deploy_box, "restart")
    warm = _calls_matching(deploy_box, "warm_streamlit.py")
    assert len(warm) == 1 and '--expect-text class="suggestion-card"' in warm[0]
    assert "𓆓𓂧" in warm[0]
    # The operational copy of the script is refreshed from the repo, beside it.
    assert (deploy_box.home / "egyptology-deploy.sh").read_text() == DEPLOY_SCRIPT.read_text()
    assert os.access(deploy_box.home / "egyptology-deploy.sh", os.X_OK)


def test_without_a_lock_unpinned_packages_are_held_at_the_running_versions(deploy_box):
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    assert deploy_box.run().returncode == 0
    constraints = Path(f"{deploy_box.calls}.constraints").read_text().split()
    assert constraints == ["altair==5.0.0", "protobuf==6.31.1"]   # streamlit is requirements.txt's


def test_a_lock_file_is_what_the_release_venv_is_built_from(deploy_box):
    lock = "altair==5.0.0\nprotobuf==6.31.1\nstreamlit==1.49.0\n"
    deploy_box.write("requirements.lock", lock)
    deploy_box.publish("lock")
    result = deploy_box.run()
    assert result.returncode == 0, result.stdout + result.stderr
    install = _calls_matching(deploy_box, "install")
    assert len(install) == 1 and install[0].endswith("/requirements.lock") and " -c " not in install[0]
    assert Path(f"{deploy_box.calls}.installed").read_text() == lock


def test_a_lock_that_disagrees_with_requirements_stops_the_deploy(deploy_box):
    before = deploy_box.head()
    deploy_box.write("requirements.lock", "streamlit==1.48.0\n")
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("stale lock")
    result = deploy_box.run()
    assert result.returncode == 1
    assert "streamlit==1.49.0" in result.stderr and "regenerate the lock" in result.stderr
    assert deploy_box.head() == before and deploy_box.live_venv() == "original"
    assert not _calls_matching(deploy_box, "systemctl")


def test_unchanged_dependencies_reuse_the_venv_and_old_releases_are_pruned(deploy_box):
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    assert deploy_box.run().returncode == 0
    first = deploy_box.live_venv()

    deploy_box.write("app.py", "v3\n")
    deploy_box.publish("v3, code only")
    assert deploy_box.run().returncode == 0
    assert deploy_box.live_venv() == first
    assert not _calls_matching(deploy_box, "base-python")

    deploy_box.write("requirements.txt", "streamlit==1.50.0\n")
    deploy_box.publish("v4, new streamlit")
    assert deploy_box.run().returncode == 0
    second = deploy_box.live_venv()
    assert second != first
    # Kept: the venv now serving and the one it replaced. The original is gone.
    assert deploy_box.release_dirs() == sorted([Path(first).name, Path(second).name])


def test_stop_before_update_defaults_off_and_can_be_switched_on(deploy_box):
    """Opus review decision for A40: no public downtime by default."""
    deploy_box.write("app.py", "v2\n")
    after = deploy_box.publish("v2")
    assert deploy_box.run().returncode == 0
    stops = _calls_matching(deploy_box, "systemctl --user stop")
    assert len(stops) == 1 and f"(head {after[:7]}," in stops[0], "stopped before the merge"

    deploy_box.write("app.py", "v3\n")
    deploy_box.publish("v3")
    assert deploy_box.run(STOP_BEFORE_UPDATE="1").returncode == 0
    stops = _calls_matching(deploy_box, "systemctl --user stop")
    assert len(stops) == 2 and f"(head {after[:7]}," in stops[0]
    assert re.search(r'^STOP_BEFORE_UPDATE="\$\{STOP_BEFORE_UPDATE:-0\}"$', DEPLOY_SCRIPT.read_text(), re.M)


def test_a_deploy_with_nothing_new_still_checks_the_app(deploy_box):
    result = deploy_box.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing to pull" in result.stdout
    assert len(_calls_matching(deploy_box, "systemctl --user start egyptology.service")) == 1
    assert _calls_matching(deploy_box, "warm_streamlit.py")


def test_a_failed_check_stops_rolls_back_and_rechecks(deploy_box):
    """Regression for the A12 review: the rollback left the new app running while it
    reset files, and judged the old one by /_stcore/health alone."""
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.write("requirements.txt", "streamlit==1.50.0\n")
    after = deploy_box.publish("v2")
    result = deploy_box.run(FAIL_WARM="v2")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ROLLED BACK" in result.stderr
    assert deploy_box.head() == before
    assert (deploy_box.repo / "app.py").read_text() == "v1\n"
    service = [line.split(" (")[0] for line in deploy_box.log() if line.startswith("systemctl --user")]
    assert service == [
        "systemctl --user stop egyptology.service", "systemctl --user start egyptology.service",
        "systemctl --user stop egyptology.service", "systemctl --user start egyptology.service",
    ]
    rollback_stop = [line for line in deploy_box.log() if line.startswith("systemctl --user stop")][1]
    assert f"(head {after[:7]}," in rollback_stop, "the rollback reset the tree before stopping"
    # The same paste check, twice: the failed deploy and the rollback.
    assert len(_calls_matching(deploy_box, "warm_streamlit.py")) == 2
    # Back on the original venv; the failed commit's release venv is gone.
    (original,) = deploy_box.release_dirs()
    assert original.startswith("original-") and deploy_box.live_venv() == str(deploy_box.releases / original)
    assert (deploy_box.home / "egyptology-last-good").read_text().strip() == before


def test_a_rollback_whose_check_fails_asks_for_a_human(deploy_box):
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    result = deploy_box.run(FAIL_WARM="always")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "MANUAL" in result.stderr
    assert f"$(cat {deploy_box.home}/egyptology-last-good)" in result.stderr
    assert f"$(cat {deploy_box.home}/egyptology-last-good-venv)" in result.stderr
    assert (deploy_box.home / "egyptology-last-good").read_text().strip() == before


def test_a_rollback_that_cannot_stop_the_service_changes_nothing_and_asks_for_a_human(deploy_box):
    """Regression for Astra's round-2 A12 finding: a failed stop was only a warning, so the
    rollback reset files under the running new app and `start` + the check 'passed'."""
    deploy_box.write("app.py", "v2\n")
    deploy_box.write("requirements.txt", "streamlit==1.50.0\n")
    after = deploy_box.publish("v2")
    result = deploy_box.run(FAIL_STOP="1")                       # the service stays active
    assert result.returncode == 2, result.stdout + result.stderr
    assert "not rolling back under a running app" in result.stderr and "MANUAL" in result.stderr
    assert "ROLLED BACK" not in result.stderr
    assert deploy_box.head() == after, "files were reset under the running app"
    assert deploy_box.live_venv() == "original"
    assert not _calls_matching(deploy_box, "systemctl --user start")
    assert _calls_matching(deploy_box, "systemctl --user is-active egyptology.service")


def test_a_rollback_goes_on_when_the_stop_failed_but_the_service_is_down(deploy_box):
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    result = deploy_box.run(FAIL_STOP="1", ACTIVE_STATE="failed")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ROLLED BACK" in result.stderr
    assert deploy_box.head() == before


def test_after_a_failed_rollback_no_deploy_runs_until_the_marker_is_removed(deploy_box):
    """Opus round-2 review: a rerun after exit 2 rewrote the last-good records and deleted
    the saved units, so the MANUAL steps then pointed at the failed state."""
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    assert deploy_box.run(FAIL_WARM="always").returncode == 2
    marker = deploy_box.home / "egyptology-deploy.FAILED"
    assert "MANUAL" in marker.read_text() and f"rm {marker}" in marker.read_text()
    last_good = deploy_box.home / "egyptology-last-good"
    last_good_venv = deploy_box.home / "egyptology-last-good-venv"
    records = (last_good.read_text(), last_good_venv.read_text())

    rerun = deploy_box.run()

    assert rerun.returncode == 1, rerun.stdout + rerun.stderr
    assert "an earlier rollback failed" in rerun.stderr
    assert (last_good.read_text(), last_good_venv.read_text()) == records
    assert records[0].strip() == before
    assert deploy_box.log() == []
    marker.unlink()
    assert deploy_box.run().returncode == 0


def test_a_second_deploy_while_one_is_running_touches_nothing(deploy_box):
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    lock = deploy_box.home / ".egyptology-deploy.lock"
    holder = _Flock(lock)                                        # a running deploy
    try:
        result = deploy_box.run()
    finally:
        holder.release()                                         # that run finished
    assert result.returncode == 1, result.stdout + result.stderr
    assert "another deploy" in result.stderr
    assert deploy_box.head() == before and deploy_box.log() == []
    assert not (deploy_box.home / "egyptology-last-good").exists()
    assert deploy_box.run().returncode == 0
    assert lock.is_file(), "the lock file stays; only the kernel lock on it is released"
    _Flock(lock).release()                                       # and it is free again


def test_a_held_deploy_lock_is_never_broken_whatever_pid_it_names(deploy_box):
    """Regression for Astra's round-3 blocker: a contender that read a dead owner deleted
    the lock a NEW owner had just taken, and both deploys ran."""
    dead = subprocess.Popen(["true"])
    dead.wait()
    lock = deploy_box.home / ".egyptology-deploy.lock"
    holder = _Flock(lock)
    lock.write_text(f"{dead.pid}\n")
    try:
        result = deploy_box.run()
        assert lock.is_file(), "the held lock was deleted"
    finally:
        holder.release()
    assert result.returncode == 1, result.stdout + result.stderr
    assert deploy_box.log() == []


def test_a_helper_git_fetch_leaves_running_does_not_keep_the_deploy_lock(deploy_box, tmp_path):
    """git's ssh can leave a ControlMaster running; it must not inherit the lock."""
    real_git = shutil.which("git")
    sleeper_pid = tmp_path / "sleeper.pid"
    wrapper = tmp_path / "git-wrapper"
    wrapper.mkdir()
    _stub(wrapper / "git", f'if [ "$1" = fetch ]; then sleep 30 >/dev/null 2>&1 </dev/null & echo $! >> "{sleeper_pid}"; fi\n'
          f'exec "{real_git}" "$@"\n')
    path = f"{deploy_box.stubs}:{wrapper}:{os.environ['PATH']}"
    try:
        assert deploy_box.run(PATH=path).returncode == 0
        second = deploy_box.run(PATH=path)
        assert second.returncode == 0, second.stdout + second.stderr
    finally:
        for pid in sleeper_pid.read_text().split() if sleeper_pid.exists() else []:
            try:
                os.kill(int(pid), 9)
            except ProcessLookupError:
                pass


def test_an_old_style_lock_directory_is_left_alone(deploy_box):
    lock = deploy_box.home / ".egyptology-deploy.lock"
    lock.mkdir()
    result = deploy_box.run()
    assert result.returncode == 1 and "old-style lock directory" in result.stderr
    assert lock.is_dir() and deploy_box.log() == []


def test_the_failed_marker_is_checked_under_the_lock(deploy_box):
    """Regression for Astra's round-3 should_fix: the marker was checked before the lock,
    so a run waiting on the lock while another failed its rollback went on to overwrite
    the records that run's MANUAL block points at."""
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    lock = deploy_box.home / ".egyptology-deploy.lock"
    holder = _Flock(lock)                                        # the deploy that is failing
    try:
        waiting = deploy_box.start(DEPLOY_LOCK_WAIT="30")
        time.sleep(1.5)                                          # it is past any early check
        (deploy_box.home / "egyptology-deploy.FAILED").write_text("MANUAL ...\n")
    finally:
        holder.release()                                         # the failing run exits 2
    out, err = waiting.communicate(timeout=60)
    assert waiting.returncode == 1, out + err
    assert "an earlier rollback failed" in err
    assert not (deploy_box.home / "egyptology-last-good").exists()
    assert deploy_box.log() == []


def test_a_failed_freeze_without_a_lock_stops_before_anything_changes(deploy_box):
    """Regression for Astra's round-2 A12/A45 finding: a failed `pip freeze` left the
    constraints empty and the build resolved every transitive dependency afresh."""
    before = deploy_box.head()
    deploy_box.write("requirements.txt", "streamlit==1.50.0\n")
    deploy_box.publish("new streamlit")
    result = deploy_box.run(FAIL_FREEZE="1")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "pip freeze failed" in result.stderr and "untouched" in result.stderr
    assert not _calls_matching(deploy_box, "install")
    assert deploy_box.head() == before and deploy_box.live_venv() == "original"
    assert deploy_box.release_dirs() == [] and not _calls_matching(deploy_box, "systemctl")


def test_a_failed_build_without_a_lock_says_how_to_get_past_it(deploy_box):
    deploy_box.write("requirements.txt", "streamlit==1.50.0\n")
    deploy_box.publish("new streamlit")
    result = deploy_box.run(FAIL_PIP="1")
    assert result.returncode == 1
    assert "Commit a requirements.lock" in result.stderr


def test_a_failed_corpus_import_rolls_back_too(deploy_box):
    before = deploy_box.head()
    deploy_box.write("data/processed/examples.csv", "id\n1\n2\n")
    deploy_box.write("requirements.txt", "streamlit==1.50.0\n")
    deploy_box.publish("more corpus")
    result = deploy_box.run(FAIL_IMPORT="1")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ROLLED BACK" in result.stderr
    assert deploy_box.head() == before
    (dry_run,) = _calls_matching(deploy_box, "import_examples.py --dry-run")
    assert f"python[{deploy_box.releases}/" in dry_run, "the import must run on the new release venv"
    # started once, after the rollback, never on the half-imported tree
    assert len(_calls_matching(deploy_box, "systemctl --user start egyptology.service")) == 1
    assert deploy_box.live_venv() == "original"
    assert deploy_box.release_dirs() == []


def test_a_corpus_change_runs_the_dry_run_then_the_sync(deploy_box):
    deploy_box.write("data/processed/examples.csv", "id\n1\n2\n")
    deploy_box.publish("more corpus")
    result = deploy_box.run()
    assert result.returncode == 0, result.stdout + result.stderr
    imports = _calls_matching(deploy_box, "import_examples.py")
    assert [line.endswith("--dry-run") for line in imports] == [True, False]


def test_a_dirty_clone_is_refused_without_touching_anything(deploy_box):
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    (deploy_box.repo / "app.py").write_text("hand edit\n")
    result = deploy_box.run()
    assert result.returncode == 1
    assert "modified tracked files" in result.stderr
    assert deploy_box.head() == before
    assert (deploy_box.repo / "app.py").read_text() == "hand edit\n"
    assert deploy_box.log() == []


def test_a_non_fast_forward_upstream_is_refused(deploy_box):
    (deploy_box.repo / "local.txt").write_text("local commit\n")
    _vcs(deploy_box.repo, "add", "local.txt")
    _vcs(deploy_box.repo, "commit", "-q", "-m", "local only")
    local = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("diverging upstream")
    result = deploy_box.run()
    assert result.returncode == 1
    assert "not a fast-forward" in result.stderr
    assert deploy_box.head() == local
    assert deploy_box.log() == []


def test_unit_files_are_only_installed_when_asked(deploy_box):
    installed = deploy_box.home / ".config" / "systemd" / "user" / "egyptology.service"
    plain = deploy_box.run()
    assert plain.returncode == 0, plain.stdout + plain.stderr
    assert not installed.exists()
    assert "unit files differ" in plain.stdout
    assert not _calls_matching(deploy_box, "daemon-reload")

    forced = deploy_box.run(INSTALL_UNITS="1")
    assert forced.returncode == 0, forced.stdout + forced.stderr
    assert installed.read_text() == (deploy_box.repo / "deploy" / "systemd" / "egyptology.service").read_text()
    assert _calls_matching(deploy_box, "systemctl --user daemon-reload")


def test_a_unit_that_differs_only_in_comments_is_neither_reported_nor_installed(deploy_box):
    """Review round 2026-10-26: the repo units gained a header and a commented-out block
    the box does not have, so a byte-for-byte `cmp` reported every unit as differing on
    every deploy, which turned the warning into noise."""
    unit_dir = deploy_box.home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    live = "  [Service]\n\nExecStart=/bin/true   \n"
    (unit_dir / "egyptology.service").write_text(live)
    deploy_box.write(
        "deploy/systemd/egyptology.service",
        "# header copied from the box\n[Service]\nExecStart=/bin/true\n\n# NOT INSTALLED\n; MemoryMax=6G\n",
    )
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2: comments only in the unit")
    plain = deploy_box.run()
    assert plain.returncode == 0, plain.stdout + plain.stderr
    assert "unit files differ" not in plain.stdout
    forced = deploy_box.run(INSTALL_UNITS="1")
    assert forced.returncode == 0, forced.stdout + forced.stderr
    assert (unit_dir / "egyptology.service").read_text() == live
    assert not _calls_matching(deploy_box, "daemon-reload")


def test_a_unit_whose_directives_differ_is_still_reported(deploy_box):
    unit_dir = deploy_box.home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "egyptology.service").write_text("# same comment\n[Service]\nExecStart=/bin/false\n")
    plain = deploy_box.run()
    assert plain.returncode == 0, plain.stdout + plain.stderr
    assert "unit files differ" in plain.stdout


def test_the_reconciled_repo_units_compare_equal_to_their_directive_lines(tmp_path):
    """The repo copies equal the box once comments are ignored; the deploy comparison must
    therefore call the box's comment-free text the same unit."""
    for name in ("egyptology.service", "egyptology-backup.service", "egyptology-backup.timer"):
        repo = PROJECT_ROOT / "deploy" / "systemd" / name
        live = tmp_path / name
        live.write_text("\n".join(
            line for line in repo.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith(("#", ";"))
        ) + "\n")
        result = _source_and_run(f'same_unit_directives "{repo}" "{live}"')
        assert result.returncode == 0, (name, result.stderr)


def test_a_rollback_restores_the_unit_files_from_before_the_deploy(deploy_box):
    """Regression for the A12/A46 review: new units stayed installed after a rollback."""
    unit_dir = deploy_box.home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "egyptology.service").write_text("[Service]\n# the live, hand-made unit\n")
    deploy_box.write("deploy/systemd/egyptology.service", "[Service]\nExecStart=/bin/false\n")
    deploy_box.write("deploy/systemd/egyptology-extra.timer", "[Timer]\n")
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2 with new units")
    result = deploy_box.run(INSTALL_UNITS="1", FAIL_WARM="v2")
    assert result.returncode == 1, result.stdout + result.stderr
    assert (unit_dir / "egyptology.service").read_text() == "[Service]\n# the live, hand-made unit\n"
    assert not (unit_dir / "egyptology-extra.timer").exists()
    calls = [line.split(" (")[0] for line in deploy_box.log() if line.startswith("systemctl")]
    reloads = [i for i, call in enumerate(calls) if call == "systemctl --user daemon-reload"]
    last_start = max(i for i, call in enumerate(calls) if call == "systemctl --user start egyptology.service")
    assert len(reloads) == 2 and reloads[1] < last_start, "units restored after the old app started"


def test_the_deploy_check_depends_on_markup_only_a_result_carries():
    expect = re.search(r"^EXPECT_TEXT='(.+)'$", DEPLOY_SCRIPT.read_text(), re.M).group(1)
    assert expect == 'class="suggestion-card"'
    assert expect in (PROJECT_ROOT / "app" / "ui" / "whyptology_app.py").read_text()
    # The stylesheet the app injects on every page names the class but never this attribute.
    theme = (PROJECT_ROOT / "app" / "ui" / "whyptology_theme.css").read_text()
    assert ".suggestion-card" in theme and expect not in theme


# ---------------------------------------------------------------------------
# A46 + A42 + A40: the unit files live in the repo
# ---------------------------------------------------------------------------

UNIT_DIR = PROJECT_ROOT / "deploy" / "systemd"


def _parse_unit(name: str) -> dict[str, dict[str, list[str]]]:
    """Section -> key -> every value, in file order (systemd allows repeated keys)."""
    sections: dict[str, dict[str, list[str]]] = {}
    current = None
    for raw in (UNIT_DIR / name).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
        elif current is not None and "=" in line:
            key, value = line.split("=", 1)
            current.setdefault(key.strip(), []).append(value.strip())
    return sections


# The three installed units were read off the box on 2026-10-26 (read-only ssh) and the
# repo copies were made equal to them, directive for directive. These tests pin the repo
# files to the values read off the box on that date. They cannot see the box: a later
# change made on the box is caught only by re-reading it (DEPLOYMENT.md, "The unit files"),
# and the deploy script's directive comparison reports it on the next deploy. They also
# assert selected directives, not complete directive equality.
RECONCILED_UNITS = ("egyptology.service", "egyptology-backup.service", "egyptology-backup.timer")

# Settings the repo wants but the box has never run. They live in the unit files as
# commented-out lines with a note, so that adopting one is a deliberate edit.
PENDING_IN_UNIT = {
    "egyptology.service": (
        "OnFailure=egyptology-notify@%n.service",
        "Environment=STREAMLIT_SERVER_FILE_WATCHER_TYPE=none",
        "MemoryMax=6G",
    ),
    "egyptology-backup.service": (
        "OnFailure=egyptology-notify@%n.service",
        "EnvironmentFile=-/home/ledio/egyptology.env",
    ),
}


def test_the_service_unit_matches_the_one_installed_on_the_box():
    unit = _parse_unit("egyptology.service")
    service = unit["Service"]
    assert unit["Unit"]["After"] == ["network-online.target"]
    assert service["TimeoutStartSec"] == ["600"]
    assert service["ExecStartPost"][0].startswith("-"), "a failed warm-up must not fail the unit"
    assert service["Restart"] == ["on-failure"]
    assert service["RestartSec"] == ["5"]
    assert service["WorkingDirectory"] == ["/home/ledio/egyptology"]
    # The leading `-` makes a missing env file non-fatal; the box has it.
    assert service["EnvironmentFile"] == ["-/home/ledio/egyptology.env"]
    assert {
        "PYTHONUNBUFFERED=1",
        "PRIVATE_DATA_DIR=/home/ledio/egyptology-private",
        "ANNOTATIONS_DURABLE=1",
        "WARM_STAGE_RESOURCES=1",
    } == set(service["Environment"])
    start = service["ExecStart"][0]
    assert start.startswith("/home/ledio/venvs/egyptology/bin/streamlit run "), "the box runs the venv's streamlit binary, not `python -m streamlit`"
    assert "app/ui/whyptology_app.py" in start and "--server.port 8502" in start and "127.0.0.1" in start
    assert "--browser.gatherUsageStats false" in start
    assert "--timeout 420" in service["ExecStartPost"][0]
    assert unit["Install"]["WantedBy"] == ["default.target"]
    # Not installed, so not an active directive here either.
    assert "OnFailure" not in unit.get("Unit", {})
    assert "MemoryMax" not in service


def test_the_backup_units_match_the_ones_installed_on_the_box():
    unit = _parse_unit("egyptology-backup.service")
    service = unit["Service"]
    assert service["Type"] == ["oneshot"]
    assert service["ExecStart"] == ["/home/ledio/bin/backup_db.sh"]
    assert service["Environment"] == [
        "OFFSITE_TARGET=b2:egyptology-backups-ledio",
        "RETENTION_DAYS=30",
    ]
    assert unit["Unit"]["Documentation"] == ["file:///home/ledio/egyptology/DEPLOYMENT.md"]
    # The box's backup unit reads no env file, so the job sees no DATABASE_URL or
    # HEALTHCHECK_URL. Adopting it is pending (see PENDING_IN_UNIT and DEPLOYMENT.md).
    assert "OnFailure" not in unit.get("Unit", {})
    assert "EnvironmentFile" not in service
    timer = _parse_unit("egyptology-backup.timer")["Timer"]
    assert timer["Persistent"] == ["true"]
    assert timer["OnCalendar"] == ["*-*-* 03:30:00"]
    assert timer["RandomizedDelaySec"] == ["300"]


def test_settings_the_box_does_not_run_are_kept_commented_out_not_dropped():
    for name, pending in PENDING_IN_UNIT.items():
        text = (UNIT_DIR / name).read_text()
        assert "NOT INSTALLED" in text, f"{name} does not say which settings are pending"
        for line in pending:
            assert f"# {line}" in text, f"{name} lost the pending line {line!r}"


def test_the_notify_unit_reads_its_topic_from_the_env_file_and_no_topic_is_committed():
    notify = _parse_unit("egyptology-notify@.service")["Service"]
    assert "${NTFY_TOPIC}" in notify["ExecStart"][0]
    assert notify["EnvironmentFile"] == ["-/home/ledio/egyptology.env"]
    for path in UNIT_DIR.iterdir():
        for topic in re.findall(r"ntfy\.sh/(\S+)", path.read_text()):
            assert topic == "${NTFY_TOPIC}", f"{path.name} names a literal ntfy topic"
    # Final ops audit: a placeholder topic copied as-is is a public topic anyone can guess.
    example = (UNIT_DIR / "egyptology.env.example").read_text()
    assert re.findall(r"^NTFY_TOPIC=(.*)$", example, re.M) == [""]


def test_every_script_a_unit_runs_from_bin_exists_in_the_repo():
    found = set()
    for path in UNIT_DIR.glob("*.service"):
        found |= set(re.findall(r"/home/ledio/bin/(\S+)", path.read_text()))
    assert {"backup_db.sh", "warm_streamlit.py"} <= found
    for name in found:
        assert (SCRIPTS / name).is_file(), f"unit runs {name} but scripts/{name} does not exist"


def test_the_unit_warm_up_query_matches_the_deploy_check_and_the_docs():
    deploy = re.search(r'^PASTE_001="(.+)"$', DEPLOY_SCRIPT.read_text(), re.M).group(1)
    assert f'--query "{deploy}"' in (UNIT_DIR / "egyptology.service").read_text()
    assert f'--query "{deploy}"' in (PROJECT_ROOT / "DEPLOYMENT.md").read_text()


def test_the_reconciled_units_guess_nothing_and_say_where_they_came_from():
    for name in RECONCILED_UNITS:
        text = (UNIT_DIR / name).read_text()
        assert "GUESSED:" not in text, f"{name} was copied from the box; nothing in it is a guess"
        assert "COPIED FROM THE BOX ON 2026-10-26" in text, f"{name} does not record its provenance"


def test_the_notify_unit_is_still_a_guess_because_it_is_not_installed():
    # There is no live copy to reconcile it against: the box has no notify unit and no
    # OnFailure= line that would call one (DEPLOYMENT.md, "The unit files").
    text = (UNIT_DIR / "egyptology-notify@.service").read_text()
    assert "NOT INSTALLED" in text
    assert text.count("GUESSED:") >= 1


# ---------------------------------------------------------------------------
# DEPLOYMENT.md names what the scripts really read
# ---------------------------------------------------------------------------


def test_deployment_doc_points_at_files_and_variables_that_exist():
    doc = (PROJECT_ROOT / "DEPLOYMENT.md").read_text()
    for relative in (
        "deploy/systemd/egyptology.service",
        "deploy/systemd/egyptology-backup.service",
        "deploy/systemd/egyptology-backup.timer",
        "deploy/systemd/egyptology-notify@.service",
        "deploy/systemd/egyptology.env.example",
        "scripts/backup_db.sh",
        "scripts/egyptology-deploy.sh",
        "requirements-dev.txt",
    ):
        assert relative in doc, f"DEPLOYMENT.md never mentions {relative}"
        assert (PROJECT_ROOT / relative).exists(), relative
    for variable in ("HEALTHCHECK_URL", "NTFY_TOPIC", "ALLOW_ANNOTATION_DROP", "INSTALL_UNITS",
                     "STOP_BEFORE_UPDATE", "OFFSITE_PRUNE", "STREAMLIT_SERVER_FILE_WATCHER_TYPE"):
        assert variable in doc, f"DEPLOYMENT.md never mentions {variable}"
    for variable in ("HEALTHCHECK_URL", "ALLOW_ANNOTATION_DROP", "OFFSITE_PRUNE"):
        assert variable in BACKUP_SCRIPT.read_text()
    for variable in ("INSTALL_UNITS", "STOP_BEFORE_UPDATE"):
        assert variable in DEPLOY_SCRIPT.read_text()
    assert "Rollback" in doc and "egyptology-last-good" in doc


def test_deployment_doc_states_the_reviewed_settings_and_monitors():
    doc = (PROJECT_ROOT / "DEPLOYMENT.md").read_text()
    (row,) = [line for line in doc.splitlines() if line.startswith("| `REVIEWER_KEY` |")]
    assert "unset = annotation saving off" in row and "anyone may save" not in doc
    # Healthchecks receives heartbeats; it is not an HTTP monitor (A42 review).
    assert "healthchecks.io HTTP check" not in doc and "Uptime Kuma" in doc
    (stop_row,) = [line for line in doc.splitlines() if line.startswith("| `INSTALL_UNITS` / `STOP_BEFORE_UPDATE` |")]
    assert "default `0`" in stop_row
    for name in ("egyptology-last-good-venv", "egyptology-last-good-units", "requirements.lock", "restic"):
        assert name in doc, name


# ---------------------------------------------------------------------------
# Final ops audit (2026-10-25)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("signal_name", ["HUP", "INT", "TERM"])
def test_an_interrupted_deploy_rolls_back_and_leaves_no_marker(deploy_box, signal_name):
    """ops-1: the only trap was `cleanup EXIT`, so a dropped ssh session mid-deploy left
    the new tree on a stopped service, and the rerun recorded that as "last good"."""
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.write("requirements.txt", "streamlit==1.50.0\n")
    deploy_box.publish("v2")
    result = deploy_box.run(SIGNAL_ON_START=signal_name)
    output = result.stdout + result.stderr
    if signal_name == "HUP":
        output += (deploy_box.home / "egyptology-deploy.interrupted.log").read_text()
    assert result.returncode == 1, output
    assert f"interrupted by SIG{signal_name}" in output and "ROLLED BACK" in output
    assert deploy_box.head() == before
    assert (deploy_box.repo / "app.py").read_text() == "v1\n"
    (original,) = deploy_box.release_dirs()
    assert deploy_box.live_venv() == str(deploy_box.releases / original)
    assert _calls_matching(deploy_box, "systemctl --user start egyptology.service (head")
    assert not (deploy_box.home / "egyptology-deploy.INPROGRESS").exists()
    assert not (deploy_box.home / "egyptology-deploy.FAILED").exists()
    assert (deploy_box.home / "egyptology-last-good").read_text().strip() == before


def test_a_deploy_killed_outright_blocks_the_next_run_and_keeps_the_records(deploy_box):
    """ops-1: SIGKILL or power loss gives no trap a chance; the marker stops the rerun from
    overwriting the records of what ran before the cut-off deploy."""
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    deploy_box.run(SIGNAL_ON_START="KILL")
    marker = deploy_box.home / "egyptology-deploy.INPROGRESS"
    assert marker.exists()
    assert f"reset --hard {before}" in marker.read_text() and f"rm {marker}" in marker.read_text()
    last_good = deploy_box.home / "egyptology-last-good"
    records = last_good.read_text()

    rerun = deploy_box.run()

    assert rerun.returncode == 1, rerun.stdout + rerun.stderr
    assert "cut off" in rerun.stderr
    assert last_good.read_text() == records and records.strip() == before
    assert deploy_box.log() == []
    marker.unlink()
    assert deploy_box.run().returncode == 0


def test_interrupting_a_deploy_that_waits_for_the_lock_keeps_the_other_runs_marker(deploy_box):
    """Follow-up (Astra): the signal traps are installed before the lock is taken, and
    the handler removed the INPROGRESS marker unconditionally, so a Ctrl-C on a run still
    waiting for the lock deleted the marker of the deploy that holds it."""
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    lock = deploy_box.home / ".egyptology-deploy.lock"
    marker = deploy_box.home / "egyptology-deploy.INPROGRESS"
    holder = _Flock(lock)                                        # a deploy mid-change
    marker.write_text("the running deploy's marker\n")
    try:
        waiting = deploy_box.start(DEPLOY_LOCK_WAIT="3")
        time.sleep(1.0)                                          # it is waiting for the lock
        waiting.send_signal(signal.SIGTERM)
        out, err = waiting.communicate(timeout=60)
    finally:
        holder.release()
    assert waiting.returncode == 1, out + err
    assert marker.read_text() == "the running deploy's marker\n"
    assert deploy_box.log() == []
    assert not (deploy_box.home / "egyptology-last-good").exists()


def test_a_successful_deploy_leaves_no_in_progress_marker(deploy_box):
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    assert deploy_box.run().returncode == 0
    assert not (deploy_box.home / "egyptology-deploy.INPROGRESS").exists()


def test_a_service_started_with_the_file_watcher_on_is_stopped_before_the_merge(deploy_box):
    """Astra ops-3: STREAMLIT_SERVER_FILE_WATCHER_TYPE=none only protects a process started
    with it; installing the unit does not change the running one."""
    before = deploy_box.head()
    deploy_box.set_running_environment("PRIVATE_DATA_DIR=/x")
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    result = deploy_box.run()
    assert result.returncode == 0, result.stdout + result.stderr
    stops = _calls_matching(deploy_box, "systemctl --user stop")
    assert len(stops) == 2 and f"(head {before[:7]}," in stops[0], "the tree changed under a watching process"
    assert "STREAMLIT_SERVER_FILE_WATCHER_TYPE=none" in result.stdout


def test_an_unreadable_running_environment_also_stops_before_the_merge(deploy_box):
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    assert deploy_box.run(MAIN_PID="0").returncode == 0
    stops = _calls_matching(deploy_box, "systemctl --user stop")
    assert f"(head {before[:7]}," in stops[0]


def test_inspect_forward_records_a_rejected_text_in_an_alert():
    """Astra ops-4: the app's database-outage notice is an st.warning (an alert element),
    and the app still draws result cards then."""
    state = warm_streamlit.RunState(expect_text='class="suggestion-card"', reject_texts=("Read-only mode.",))
    warm_streamlit.inspect_forward(_element_msg("alert", "**Read-only mode.** The project database ..."), state)
    warm_streamlit.inspect_forward(_markdown_msg('<div class="suggestion-card">x</div>'), state)
    assert state.expect_seen and state.rejected == ["Read-only mode."]
    clean = warm_streamlit.RunState(reject_texts=("Read-only mode.",))
    warm_streamlit.inspect_forward(_element_msg("alert", "Some other notice"), clean)
    assert clean.rejected == []


def test_the_deploy_check_rejects_the_apps_read_only_notice(deploy_box):
    reject = re.search(r"^REJECT_TEXT='(.+)'$", DEPLOY_SCRIPT.read_text(), re.M).group(1)
    app = (PROJECT_ROOT / "app" / "ui" / "whyptology_app.py").read_text()
    notice = app[app.index('if database_status != "ok":\n    st.warning('):]
    assert reject in notice[:400]
    assert deploy_box.run().returncode == 0
    (check,) = _calls_matching(deploy_box, "warm_streamlit.py")
    assert f"--reject-text {reject}" in check


def test_the_docs_name_the_deploy_checks_real_arguments():
    """Opus ops-3: the doc said `--expect-text suggestion-card`, the bare form that the same
    document explains is not what the deploy uses."""
    doc = (PROJECT_ROOT / "DEPLOYMENT.md").read_text()
    assert "--expect-text suggestion-card" not in doc
    assert "--expect-text 'class=\"suggestion-card\"'" in doc and "--reject-text 'Read-only mode.'" in doc
    assert "egyptology-deploy.INPROGRESS" in doc and "tmux" in doc


def _restore_live_db(env_text: str) -> subprocess.CompletedProcess:
    doc = (PROJECT_ROOT / "DEPLOYMENT.md").read_text()
    restore = doc[doc.index("### Restore"):doc.index("## Alerts")]
    script = restore[restore.index("# The file the service really opens"):restore.index('echo "live database')]
    home = tempfile.mkdtemp()
    Path(home, "egyptology.env").write_text(env_text)
    result = subprocess.run(
        ["bash", "-c", script + 'printf %s "$LIVE_DB"'], env={**os.environ, "HOME": home},
        capture_output=True, text=True,
    )
    result.home = home  # type: ignore[attr-defined]
    return result


@pytest.mark.parametrize(
    "url, expected",
    [
        ("sqlite+pysqlite:////srv/data/egyptology.db", "/srv/data/egyptology.db"),
        ("sqlite+pysqlite:///rel.db", "HOME/egyptology/rel.db"),
        ("sqlite:////srv/data/egyptology.db?timeout=5", "/srv/data/egyptology.db"),
        ("", "HOME/egyptology/egyptology.db"),
    ],
)
def test_the_restore_reads_database_url_the_way_the_app_and_backup_do(url, expected):
    """Follow-up (Astra): the restore's sed only knew `sqlite:///`, so a supported
    `sqlite+pysqlite:///` URL fell back to the clone's default database."""
    result = _restore_live_db(f"DATABASE_URL={url}\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected.replace("HOME", result.home)


@pytest.mark.parametrize(
    "url", ["postgresql://u:secret@host/db", "sqlite://", "sqlite:///:memory:", "sqlite:///file:x.db?mode=ro"]
)
def test_the_restore_refuses_a_database_url_it_cannot_restore(url):
    result = _restore_live_db(f"DATABASE_URL={url}\n")
    assert result.returncode != 0 and result.stdout == ""
    assert "secret" not in result.stderr


def test_the_restore_steps_use_the_database_the_service_really_opens():
    """Astra ops-2: after the move out of the clone, the restore still replaced
    ~/egyptology/egyptology.db, which the service no longer opens."""
    doc = (PROJECT_ROOT / "DEPLOYMENT.md").read_text()
    restore = doc[doc.index("### Restore"):doc.index("## Alerts")]
    assert "~/egyptology/egyptology.db" not in restore
    assert 'cp "$TMP/restored.db" "$LIVE_DB"' in restore and 'for DB in "$LIVE_DB"' in restore
    script = restore[restore.index("# The file the service really opens"):restore.index('echo "live database')]
    for env_line, expected in (
        ("DATABASE_URL=sqlite:////home/ledio/egyptology-data/egyptology.db\n", "/home/ledio/egyptology-data/egyptology.db"),
        ("# DATABASE_URL=sqlite:////elsewhere.db\n", "HOME/egyptology/egyptology.db"),
        ("DATABASE_URL=sqlite:///other.db\n", "HOME/egyptology/other.db"),
    ):
        with tempfile.TemporaryDirectory() as home:
            Path(home, "egyptology.env").write_text(env_line)
            out = subprocess.run(
                ["bash", "-c", script + 'printf %s "$LIVE_DB"'], env={**os.environ, "HOME": home},
                capture_output=True, text=True, check=True,
            ).stdout
        assert out == expected.replace("HOME", home), (env_line, out)

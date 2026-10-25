"""Audit batch "ops" (A11, A12, A13, A19, A40-A43, A45, A46, A57).

Everything here runs against stubs: no systemd, B2, ntfy or live server is touched.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import textwrap
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


def _markdown_msg(body: str) -> ForwardMsg:
    forward = ForwardMsg()
    forward.delta.new_element.markdown.body = body
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


_PROBE_APP = textwrap.dedent(
    '''
    import streamlit as st

    mode = st.query_params.get("q", "")
    if mode == "boom":
        raise KeyError("renamed_column")
    elif mode == "card":
        st.markdown('<div class="suggestion-card">a result</div>', unsafe_allow_html=True)
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
    result = _warm(probe_server, "--query", "none-here", "--expect-text", "suggestion-card")
    assert result.returncode == 1
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
    assert any(" b2:bucket/path/monthly/egyptology-2026-01.db.gz" in line and line.startswith("copyto") for line in log)
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
    """A fake server: origin repo, a clone as the live tree, a fake venv, stub systemctl."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.home = tmp / "home"
        self.work = tmp / "work"
        self.origin = tmp / "origin.git"
        self.repo = self.home / "egyptology"
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

        venv_bin = self.home / "venvs" / "egyptology" / "bin"
        venv_bin.mkdir(parents=True)
        # pip fails only for the *target* requirements (a scratch path), never for the restore.
        _stub(venv_bin / "pip", 'echo "pip $*" >> "$CALL_LOG"\n'
              'case "$*" in *"/egyptology/requirements.txt"*) exit 0;; esac\n'
              '[ -n "$FAIL_PIP" ] && exit 1\nexit 0\n')
        _stub(venv_bin / "python", 'echo "python $*" >> "$CALL_LOG"\n'
              'case "$*" in *warm_streamlit.py*) [ -n "$FAIL_WARM" ] && exit 1;; esac\n'
              'case "$*" in *import_examples.py*) [ -n "$FAIL_IMPORT" ] && exit 1;; esac\nexit 0\n')
        _stub(self.stubs / "systemctl",
              f'echo "systemctl $* (head $(git -C "{self.repo}" rev-parse --short HEAD))" >> "$CALL_LOG"\n')
        _stub(self.stubs / "journalctl", 'echo "(journal)"\n')
        _stub(self.stubs / "curl", 'exit 0\n')

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

    def run(self, **extra: str) -> subprocess.CompletedProcess:
        environment = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        environment.update(
            _GIT_ENV, PATH=f"{self.stubs}:{os.environ['PATH']}", DEPLOY_HOME=str(self.home),
            CALL_LOG=str(self.calls), HEALTH_TRIES="2", HEALTH_INTERVAL="0", GIT_TERMINAL_PROMPT="0",
        )
        environment.update(extra)
        return subprocess.run(
            ["bash", str(DEPLOY_SCRIPT)], env=environment, capture_output=True, text=True, timeout=120
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


def test_a_failing_pip_leaves_the_tree_and_the_service_untouched(deploy_box):
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    result = deploy_box.run(FAIL_PIP="1")
    assert result.returncode == 1, result.stdout + result.stderr
    assert deploy_box.head() == before
    assert (deploy_box.repo / "app.py").read_text() == "v1\n"
    assert _vcs(deploy_box.repo, "status", "--porcelain") == ""
    assert not _calls_matching(deploy_box, "systemctl")
    # the restore install from the old tree's requirements
    assert _calls_matching(deploy_box, f"pip install -q -r {deploy_box.repo}/requirements.txt")


def test_a_successful_deploy_stops_before_the_merge_and_records_last_good(deploy_box):
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    after = deploy_box.publish("v2")
    result = deploy_box.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert deploy_box.head() == after
    assert (deploy_box.home / "egyptology-last-good").read_text().strip() == after
    stop = _calls_matching(deploy_box, "systemctl --user stop egyptology.service")
    assert stop and stop[0].endswith(f"(head {before[:7]})"), stop
    assert _calls_matching(deploy_box, "systemctl --user restart egyptology.service")
    warm = _calls_matching(deploy_box, "warm_streamlit.py")
    assert warm and "--expect-text suggestion-card" in warm[-1]
    assert "𓆓𓂧" in warm[-1]
    # The operational copy of the script is refreshed from the repo, beside it.
    assert (deploy_box.home / "egyptology-deploy.sh").read_text() == DEPLOY_SCRIPT.read_text()
    assert os.access(deploy_box.home / "egyptology-deploy.sh", os.X_OK)


def test_a_deploy_with_nothing_new_does_not_stop_the_service(deploy_box):
    result = deploy_box.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert not _calls_matching(deploy_box, "systemctl --user stop")
    assert _calls_matching(deploy_box, "systemctl --user restart egyptology.service")
    assert "nothing to pull" in result.stdout


def test_stop_before_update_can_be_switched_off(deploy_box):
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    result = deploy_box.run(STOP_BEFORE_UPDATE="0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not _calls_matching(deploy_box, "systemctl --user stop")


def test_a_failed_warm_up_rolls_the_deploy_back(deploy_box):
    """Regression for A12/A11: the new commit stayed in place and the deploy printed 'healthy'."""
    before = deploy_box.head()
    deploy_box.write("app.py", "v2\n")
    deploy_box.publish("v2")
    result = deploy_box.run(FAIL_WARM="1")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ROLLED BACK" in result.stderr
    assert deploy_box.head() == before
    assert (deploy_box.repo / "app.py").read_text() == "v1\n"
    assert len(_calls_matching(deploy_box, "systemctl --user restart egyptology.service")) == 2
    assert not (deploy_box.home / "egyptology-last-good").exists()


def test_a_failed_corpus_import_rolls_back_too(deploy_box):
    before = deploy_box.head()
    deploy_box.write("data/processed/examples.csv", "id\n1\n2\n")
    deploy_box.publish("more corpus")
    result = deploy_box.run(FAIL_IMPORT="1")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ROLLED BACK" in result.stderr
    assert deploy_box.head() == before
    assert _calls_matching(deploy_box, "import_examples.py --dry-run")
    # restarted once, after the rollback, never on the half-imported tree
    assert len(_calls_matching(deploy_box, "systemctl --user restart egyptology.service")) == 1


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


def test_the_deploy_check_depends_on_a_css_class_the_app_really_emits():
    assert 'class="suggestion-card"' in (PROJECT_ROOT / "app" / "ui" / "whyptology_app.py").read_text()
    assert re.search(r'^EXPECT_TEXT="suggestion-card"$', DEPLOY_SCRIPT.read_text(), re.M)


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


def test_the_service_unit_has_the_settings_the_audit_asked_for():
    unit = _parse_unit("egyptology.service")
    service = unit["Service"]
    assert service["TimeoutStartSec"] == ["600"]
    assert service["ExecStartPost"][0].startswith("-"), "a failed warm-up must not fail the unit"
    assert "MemoryMax" in service
    assert service["Restart"] == ["on-failure"]
    assert "STREAMLIT_SERVER_FILE_WATCHER_TYPE=none" in service["Environment"]
    assert {"PRIVATE_DATA_DIR=/home/ledio/egyptology-private", "ANNOTATIONS_DURABLE=1", "WARM_STAGE_RESOURCES=1"} <= set(service["Environment"])
    start = service["ExecStart"][0]
    assert "app/ui/whyptology_app.py" in start and "--server.port 8502" in start and "127.0.0.1" in start
    assert unit["Unit"]["OnFailure"] == ["egyptology-notify@%n.service"]
    assert unit["Install"]["WantedBy"] == ["default.target"]


def test_the_backup_units_match_the_documented_setup():
    service = _parse_unit("egyptology-backup.service")
    assert service["Service"]["Type"] == ["oneshot"]
    assert service["Service"]["ExecStart"] == ["/home/ledio/bin/backup_db.sh"]
    assert service["Service"]["Environment"] == ["OFFSITE_TARGET=b2:egyptology-backups-ledio"]
    assert service["Unit"]["OnFailure"] == ["egyptology-notify@%n.service"]
    timer = _parse_unit("egyptology-backup.timer")["Timer"]
    assert timer["Persistent"] == ["true"]
    assert timer["OnCalendar"] == ["*-*-* 03:30:00"]


def test_the_notify_unit_reads_its_topic_from_the_env_file_and_no_topic_is_committed():
    notify = _parse_unit("egyptology-notify@.service")["Service"]
    assert "${NTFY_TOPIC}" in notify["ExecStart"][0]
    assert notify["EnvironmentFile"] == ["-/home/ledio/egyptology.env"]
    for path in UNIT_DIR.iterdir():
        for topic in re.findall(r"ntfy\.sh/(\S+)", path.read_text()):
            assert topic == "${NTFY_TOPIC}", f"{path.name} names a literal ntfy topic"
    assert "NTFY_TOPIC=CHANGE_ME" in (UNIT_DIR / "egyptology.env.example").read_text()


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


def test_every_guessed_line_is_marked():
    markers = sum(path.read_text().count("GUESSED:") for path in UNIT_DIR.iterdir())
    # no After=, exact ExecStart flags, warm-up timeout, RestartSec, MemoryMax, backup
    # timeout, RandomizedDelaySec, the notify command (the list in DEPLOYMENT.md)
    assert markers >= 8


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

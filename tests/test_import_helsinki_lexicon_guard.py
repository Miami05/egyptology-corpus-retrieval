"""The Helsinki importer must not replace the tracked lexicon by default (audit A38:
the 0.2 weight and the Urk. IV gate were tuned on the committed file)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import import_helsinki_lexicon as mod  # noqa: E402


@pytest.fixture
def no_build(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise AssertionError("build() reached: the tracked lexicon would be rewritten")

    monkeypatch.setattr(mod, "build", boom)


def test_bare_run_does_not_reach_the_tracked_lexicon(monkeypatch, no_build) -> None:
    monkeypatch.setattr(sys, "argv", ["import_helsinki_lexicon.py"])
    with pytest.raises(SystemExit):
        mod.main()


def test_explicit_tracked_path_needs_the_replace_flag(monkeypatch, no_build) -> None:
    monkeypatch.setattr(sys, "argv", ["x", "--output", str(mod.OUTPUT_PATH)])
    with pytest.raises(SystemExit) as info:
        mod.main()
    assert "--replace-tracked-lexicon" in str(info.value)


def test_replace_flag_lets_a_deliberate_rebuild_through(monkeypatch, no_build) -> None:
    monkeypatch.setattr(sys, "argv", ["x", "--output", str(mod.OUTPUT_PATH), "--replace-tracked-lexicon"])
    with pytest.raises(AssertionError, match="build"):
        mod.main()

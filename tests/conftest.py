"""Pytest configuration.

Puts the project root on `sys.path` so `import app...` works regardless of how
pytest is invoked or from which directory. Until this file existed the imports
resolved only by accident: `tests/__init__.py` made the suite a package, which
happened to add the root — a property nothing documented and any packaging change
would have removed.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# The private, non-redistributed corpus (data/private/, PRIVATE_DATA_DIR) is
# machine-local by design, so the suite must never see whatever a developer happens
# to have there — otherwise a test asserting "no sentence in this corpus" passes on
# one laptop and fails on another. Pin it to an empty directory before
# app.ui.whyptology_app is imported (it resolves the variable at import time).
# Tests that want private rows use the `private_app` fixture, which swaps the
# directory on the already-imported module.
import os
import tempfile

_EMPTY_PRIVATE_DIR = Path(tempfile.mkdtemp(prefix="egyptology-empty-private-"))
os.environ["PRIVATE_DATA_DIR"] = str(_EMPTY_PRIVATE_DIR)

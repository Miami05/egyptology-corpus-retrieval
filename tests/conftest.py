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

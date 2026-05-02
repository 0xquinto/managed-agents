"""Make `evals/score.py` importable as a module for these tests.

`evals/` is a flat script directory (no package __init__), so we splice the
parent dir onto sys.path before any test imports `score`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_EVALS_DIR = Path(__file__).resolve().parent.parent
if str(_EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(_EVALS_DIR))

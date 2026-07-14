"""Ensure the repo root and the tests directory are importable so tests can
``import core...`` and ``from _v1_helpers import ...`` regardless of pytest's
import mode."""

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent

for _p in (_REPO_ROOT, _TESTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

"""Pytest bootstrap.

Ensures the repository root is importable so tests can ``import simulate`` and
``from core import ...`` regardless of the invoking working directory.
"""

import pathlib
import sys

_ROOT = pathlib.Path(__file__).parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

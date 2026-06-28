"""Pytest bootstrap.

Ensures the repository root is on ``sys.path`` so the top-level ``backend`` and
``benchmark`` packages import correctly during test collection, regardless of how
pytest is invoked (and even if ``PYTHONPATH`` is not set).
"""

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

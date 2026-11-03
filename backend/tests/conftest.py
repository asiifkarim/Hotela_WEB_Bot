"""Make the backend importable no matter where pytest is started from.

`pytest backend/tests` from the repository root and `pytest tests` from
`backend/` must behave the same, so the backend package directory is put on
the path here instead of relying on the working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

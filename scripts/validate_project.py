from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yt_nonstop.contracts.validators import *  # noqa: F401,F403,E402
from yt_nonstop.contracts.validators import main  # noqa: E402


if __name__ == "__main__":
    main()

"""Root-level convenience wrapper for the project export tool.

Usage:
    python export.py                     # default output: project_compact_export.txt
    python export.py --output out.txt    # custom output path
    python export.py --max-bytes-per-file 50000
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure tools/ is importable regardless of cwd
sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

from export_project_compact import main  # type: ignore

if __name__ == "__main__":
    raise SystemExit(main())

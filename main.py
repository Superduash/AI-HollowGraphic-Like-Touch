"""Root launcher so `python main.py` works from project directory."""

from pathlib import Path
import sys


def _bootstrap_src_path() -> None:
    project_root = Path(__file__).resolve().parent
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


def main() -> None:
    _bootstrap_src_path()
    from main import run  # Imports src/main.py after path bootstrap.

    run()


if __name__ == "__main__":
    main()

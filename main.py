"""Root launcher so `python main.py` works from project directory."""

from pathlib import Path
import runpy
import sys


def main() -> None:
    project_root = Path(__file__).resolve().parent
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    src_main = src_dir / "main.py"
    runpy.run_path(str(src_main), run_name="__main__")


if __name__ == "__main__":
    main()

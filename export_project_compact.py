from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".vscode",
    "node_modules",
}

DEFAULT_EXCLUDE_FILES = {
    ".requirements.sha256",
}

TEXT_EXTENSIONS = {
    ".py",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".bat",
    ".ps1",
    ".sh",
    ".gitignore",
}


def is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True

    try:
        with path.open("rb") as f:
            chunk = f.read(2048)
    except OSError:
        return False

    if b"\x00" in chunk:
        return False
    return True


def collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir():
            if path.name in DEFAULT_EXCLUDE_DIRS:
                continue
            continue

        if path.name in DEFAULT_EXCLUDE_FILES:
            continue

        if any(part in DEFAULT_EXCLUDE_DIRS for part in path.parts):
            continue

        if not is_probably_text(path):
            continue

        files.append(path)

    return sorted(files)


def export_project(root: Path, output: Path, max_bytes_per_file: int) -> int:
    files = collect_files(root)
    written = 0

    with output.open("w", encoding="utf-8", newline="\n") as out:
        out.write(f"PROJECT: {root.name}\n")
        out.write(f"ROOT: {root.resolve()}\n")
        out.write(f"FILES: {len(files)}\n\n")

        for file_path in files:
            rel_path = file_path.relative_to(root).as_posix()
            out.write(f"=== {rel_path} ===\n")
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                out.write(f"<unreadable: {exc}>\n\n")
                continue

            encoded = content.encode("utf-8", errors="replace")
            if len(encoded) > max_bytes_per_file:
                truncated = encoded[:max_bytes_per_file].decode("utf-8", errors="ignore")
                out.write(truncated)
                out.write("\n\n<... truncated ...>\n\n")
            else:
                out.write(content)
                if not content.endswith("\n"):
                    out.write("\n")
                out.write("\n")

            written += 1

    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export project text files into one compact snapshot file."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Project root to scan (default: script directory)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("project_compact_export.txt"),
        help="Output text file path",
    )
    parser.add_argument(
        "--max-bytes-per-file",
        type=int,
        default=100_000,
        help="Max bytes written per file before truncation",
    )

    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()

    count = export_project(root=root, output=output, max_bytes_per_file=args.max_bytes_per_file)
    print(f"Export complete: {count} files written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
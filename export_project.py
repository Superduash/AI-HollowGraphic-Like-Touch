#!/usr/bin/env python3
"""
export_project.py

Exports only YOUR project source code into a compact single file for ChatGPT.
Skips virtual environments, dependencies, caches, and large files.
"""

from pathlib import Path
import os

# Only include actual source/config files
ALLOWED_EXTENSIONS = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini"}
ALLOWED_FILENAMES = {"requirements.txt"}

# Ignore ALL of these directories (including .venv, env, .env, eggs, etc.)
IGNORED_DIRS = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    ".env",
    "node_modules",
    ".idea",
    ".vscode",
    "build",
    "dist",
    ".next",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".eggs",
    "egg-info",
    ".gemini",
    ".agents",
}

# Skip files bigger than 50 KB — no real source file should be this large
MAX_FILE_SIZE = 50_000

# Also skip these specific filenames
SKIP_FILES = {"project_export.txt", "export_project.py", "package-lock.json", "uv.lock"}

OUTPUT_FILENAME = "project_export.txt"


def should_include(filepath: Path, root: Path) -> bool:
    rel = filepath.relative_to(root)

    # Skip ignored directories
    for part in rel.parts:
        if part in IGNORED_DIRS or part.endswith(".egg-info"):
            return False

    # Skip output/self and known junk
    if filepath.name in SKIP_FILES:
        return False

    # Match by exact name or extension
    if filepath.name in ALLOWED_FILENAMES:
        return True
    if filepath.suffix.lower() in ALLOWED_EXTENSIONS:
        return True

    return False


def collect_files(root: Path):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored dirs so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.endswith(".egg-info")]

        for f in filenames:
            path = Path(dirpath) / f
            if not should_include(path, root):
                continue

            # Skip large files
            try:
                if path.stat().st_size > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue

            files.append(path)

    return sorted(files)


def main():
    root = Path.cwd()
    files = collect_files(root)

    exported = 0
    total_bytes = 0

    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as out:
        for file in files:
            rel = file.relative_to(root)

            try:
                content = file.read_text(encoding="utf-8")
            except Exception:
                continue

            # Strip trailing whitespace per line, collapse 3+ blank lines into 2
            lines = [l.rstrip() for l in content.splitlines()]
            cleaned_lines = []
            blank_count = 0
            for line in lines:
                if line == "":
                    blank_count += 1
                    if blank_count <= 2:
                        cleaned_lines.append(line)
                else:
                    blank_count = 0
                    cleaned_lines.append(line)

            cleaned = "\n".join(cleaned_lines)

            section = f"===== FILE: {rel} =====\n{cleaned}\n\n"
            out.write(section)
            total_bytes += len(section.encode("utf-8"))
            exported += 1

    size_kb = total_bytes / 1024
    size_mb = total_bytes / (1024 * 1024)

    print(f"Export complete → {OUTPUT_FILENAME}")
    print(f"Files exported : {exported}")
    if size_mb >= 1:
        print(f"Output size    : {size_mb:.2f} MB")
    else:
        print(f"Output size    : {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
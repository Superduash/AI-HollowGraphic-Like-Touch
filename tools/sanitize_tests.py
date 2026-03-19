#!/usr/bin/env python3
"""One-time script to sanitize test files."""
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
test_dir = project_root / "tests"
for test_file in test_dir.glob("*.py"):
    if "fix_encoding" in test_file.name or "run_tests" in test_file.name:
        continue
    
    with open(test_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace any unicode
    content = content.replace('\u2713', '[PASS]')  # Check mark
    content = content.replace('\u2705', '[SUCCESS]')  # Check mark green
    content = content.replace('\u274c', '[FAIL]')  # X mark
    content = content.replace('\u26a0', '[WARN]')  # Warning  
    
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(content)

print("[DONE] Sanitized all test files")

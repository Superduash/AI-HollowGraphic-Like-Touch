"""Quick script to remove unicode characters from test files."""
from pathlib import Path

test_dir = Path(__file__).parent

for test_file in test_dir.glob("test_*.py"):
    with open(test_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace unicode chars
    content = content.replace('\u2713', '[PASS]')
    content = content.replace('\u2705', '[SUCCESS]')
    content = content.replace('\u274c', '[FAIL]')
    content = content.replace('\u26a0', '[WARN]')
    
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Fixed {test_file.name}")

print("[SUCCESS] All test files fixed")

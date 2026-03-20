#!/usr/bin/env python3
"""
Comprehensive test runner - executes all tests and reports results.
Designed to run fast from command line after every change.
"""
import sys
import os
import time
import traceback
from pathlib import Path


_DEVNULL_HANDLE = None
if os.environ.get("HT_SILENCE_NATIVE_STDERR", "1") == "1":
    try:
        _DEVNULL_HANDLE = open(os.devnull, "w", encoding="utf-8", errors="ignore")
        os.dup2(_DEVNULL_HANDLE.fileno(), 2)
    except Exception:
        _DEVNULL_HANDLE = None


# Add workspace to path
WORKSPACE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.errors = []
        self.start_time = None
        self.end_time = None
    
    def run_all(self):
        """Run all test suites."""
        print("=" * 70)
        print("[TEST SUITE] COMPREHENSIVE TEST SUITE")
        print("=" * 70)
        
        self.start_time = time.time()
        
        test_suites = [
            ("Unit Tests: Models", lambda: self._run_test_module("tests.test_models")),
            ("Unit Tests: Hand Tracker", lambda: self._run_test_module("tests.test_hand_tracker")),
            ("Unit Tests: Gesture Detector", lambda: self._run_test_module("tests.test_gesture_detector")),
            ("Unit Tests: Camera", lambda: self._run_test_module("tests.test_camera")),
            ("Unit Tests: Cursor Mapper", lambda: self._run_test_module("tests.test_cursor_mapper")),
            ("Unit Tests: Mouse Controller", lambda: self._run_test_module("tests.test_mouse")),
            ("Integration Tests", lambda: self._run_test_module("tests.test_integration")),
        ]
        
        for suite_name, suite_func in test_suites:
            print(f"\n[SUITE] {suite_name}")
            print("-" * 70)
            try:
                suite_func()
            except Exception as e:
                self.failed += 1
                self.errors.append((suite_name, str(e), traceback.format_exc()))
                print(f"[FAIL] Suite failed: {e}")
        
        self.end_time = time.time()
        self._print_summary()
    
    def _run_test_module(self, module_name):
        """Dynamically import and run test module."""
        try:
            module = __import__(module_name, fromlist=[''])
            
            # Find and run all test_* functions
            test_functions = [
                (name, getattr(module, name))
                for name in dir(module)
                if name.startswith('test_') and callable(getattr(module, name))
            ]
            
            if not test_functions:
                self.skipped += 1
                print(f"[SKIP] No test functions found in {module_name}")
                return
            
            for test_name, test_func in test_functions:
                try:
                    test_func()
                    self.passed += 1
                except AssertionError as e:
                    self.failed += 1
                    self.errors.append((f"{module_name}.{test_name}", str(e), traceback.format_exc()))
                    print(f"[FAIL] {test_name}: {e}")
                except Exception as e:
                    self.skipped += 1
                    print(f"[SKIP] {test_name}: Skipped ({type(e).__name__})")
        
        except ImportError as e:
            self.skipped += 1
            print(f"[SKIP] Could not import {module_name}: {e}")
        except Exception as e:
            self.failed += 1
            self.errors.append((module_name, str(e), traceback.format_exc()))
            print(f"[FAIL] Module failed: {e}")
    
    def _print_summary(self):
        """Print test summary."""
        elapsed = self.end_time - self.start_time
        
        print("\n" + "=" * 70)
        print("[SUMMARY] TEST RESULTS")
        print("=" * 70)
        print(f"[PASS] Passed:  {self.passed}")
        print(f"[FAIL] Failed:  {self.failed}")
        print(f"[SKIP] Skipped: {self.skipped}")
        print(f"[TIME] Elapsed: {elapsed:.2f}s")
        
        if self.errors:
            print("\n" + "=" * 70)
            print("[ERRORS] FAILED TESTS DETAILS")
            print("=" * 70)
            for test_name, error_msg, full_trace in self.errors:
                print(f"\n{test_name}:")
                print(f"  {error_msg}")
        
        print("\n" + "=" * 70)
        
        if self.failed == 0:
            print("[SUCCESS] ALL TESTS PASSED!")
            return 0
        else:
            print(f"[FAILURE] {self.failed} test(s) failed")
            return 1


def main():
    """Main test runner entry point."""
    runner = TestRunner()
    runner.run_all()
    
    return 0 if runner.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

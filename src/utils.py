from __future__ import annotations

import platform

try:
    import mediapipe as mp  # type: ignore
except Exception:  # ImportError on missing package; also guard weird install states
    mp = None  # type: ignore[assignment]


def _mediapipe_diagnostic() -> str:
    try:
        if mp is None:
            return "mediapipe import failed (package not installed or import error)"
        file_path = getattr(mp, "__file__", None)
        version = getattr(mp, "__version__", None)
        has_solutions = hasattr(mp, "solutions")
        return f"mediapipe version={version} file={file_path} has_solutions={has_solutions}"
    except Exception:
        return "mediapipe diagnostic unavailable"


def _ensure_mediapipe_solutions() -> None:
    if mp is None:
        raise RuntimeError(
            "MediaPipe is not installed (or failed to import).\n\n"
            "Fix (inside this app's .venv):\n"
            "1) Open a terminal in this folder\n"
            "2) Run: .venv\\Scripts\\python -m pip install -r requirements.txt\n"
        )

    if hasattr(mp, "solutions"):
        return

    detail = _mediapipe_diagnostic()
    raise RuntimeError(
        "MediaPipe import looks wrong: 'mediapipe' has no attribute 'solutions'.\n"
        f"{detail}\n\n"
        "Most common causes:\n"
        "- A different 'mediapipe' module is being imported (shadowing).\n"
        "- A broken/partial mediapipe install in the venv.\n\n"
        "Fix (inside this app's .venv):\n"
        "1) Open a terminal in this folder\n"
        "2) Run: .venv\\Scripts\\python -m pip uninstall -y mediapipe\n"
        "3) Run: .venv\\Scripts\\python -m pip install mediapipe==0.10.21\n"
    )


def _configure_input_latency() -> None:
    pass


def _boost_runtime_priority() -> None:
    # Best-effort: prefer responsiveness on Windows.
    if platform.system() != "Windows":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        GetCurrentProcess = kernel32.GetCurrentProcess
        GetCurrentThread = kernel32.GetCurrentThread
        SetPriorityClass = kernel32.SetPriorityClass
        SetThreadPriority = kernel32.SetThreadPriority

        HIGH_PRIORITY_CLASS = 0x00000080
        THREAD_PRIORITY_HIGHEST = 2

        SetPriorityClass(GetCurrentProcess(), HIGH_PRIORITY_CLASS)
        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_HIGHEST)
    except Exception:
        pass

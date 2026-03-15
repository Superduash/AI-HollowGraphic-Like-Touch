"""Central configuration for the AI gesture mouse controller."""

# ---------------------------------------------------------------------------
# Runtime-toggleable flags (defaults — GUI can change at runtime)
# ---------------------------------------------------------------------------
DEBUG_MODE = False
PERFORMANCE_MODE = False
ENABLE_MOUSE_CONTROL = True

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_INDEX = 0
CAMERA_INDEXES = [0, 1, 2]

# Processing resolution — MediaPipe runs on this smaller frame.
PROCESS_WIDTH = 320
PROCESS_HEIGHT = 240

# ---------------------------------------------------------------------------
# MediaPipe Hands
# ---------------------------------------------------------------------------
MAX_NUM_HANDS = 1
MIN_DETECTION_CONFIDENCE = 0.45
MIN_TRACKING_CONFIDENCE = 0.45

# OpenCV runtime tuning for low-end CPUs.
CV2_USE_OPTIMIZED = True
CV2_NUM_THREADS = 4

# ---------------------------------------------------------------------------
# Adaptive smoothing
# ---------------------------------------------------------------------------
ALPHA_SLOW = 0.25          # strong smoothing for slow movements
ALPHA_FAST = 0.70          # light smoothing for fast movements
SPEED_THRESHOLD = 50.0     # pixels — above this counts as "fast"

# ---------------------------------------------------------------------------
# Gesture thresholds
# ---------------------------------------------------------------------------
PINCH_DISTANCE_THRESHOLD = 20
PINCH_RELEASE_FACTOR = 1.3
GESTURE_STABILITY_FRAMES = 2
CLICK_COOLDOWN = 0.40
DOUBLE_CLICK_WINDOW = 0.40
DRAG_HOLD_TIME = 0.30
SCROLL_SENSITIVITY = 2.0
SCROLL_THRESHOLD = 10
CURSOR_MOVE_THRESHOLD = 3

# Cursor latency and stability tuning.
CURSOR_THREAD_HZ = 240
CURSOR_DEADZONE_PX = 2.0
CURSOR_PREDICTION_SECONDS = 0.1
CURSOR_MAX_BOOST = 2.0
CURSOR_SPEED_FOR_MAX_BOOST = 1800.0

# One Euro filter (required low-latency parameters).
ONE_EURO_MIN_CUTOFF = 1.0
ONE_EURO_BETA = 0.3
ONE_EURO_D_CUTOFF = 1.0

# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------
TARGET_FPS = 60

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
WINDOW_NAME = "AI-HollowGraphic-Like-Touch"

"""Central configuration for the AI gesture mouse controller."""

# Camera settings
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_INDEX = 0
# Try multiple indexes in order for systems where default camera is not index 0.
CAMERA_INDEXES = [0, 1, 2]

# MediaPipe Hands settings
MAX_NUM_HANDS = 1
MIN_DETECTION_CONFIDENCE = 0.7
MIN_TRACKING_CONFIDENCE = 0.7

# Cursor and gesture behavior
SMOOTHING_WINDOW = 5
SMOOTHING_ALPHA = 0.35
LEFT_CLICK_PINCH_THRESHOLD = 35
RIGHT_CLICK_PINCH_THRESHOLD = 40
CLICK_COOLDOWN_SECONDS = 0.35

# UI settings
WINDOW_NAME = "AI-HollowGraphic-Like-Touch"
TEXT_COLOR = (0, 255, 0)
ALERT_COLOR = (0, 0, 255)

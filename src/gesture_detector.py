from __future__ import annotations

import math
import time

try:
    from .fast_math import pinch_dist_2d, ema_step
except Exception:
    def pinch_dist_2d(x1, y1, x2, y2):
        dx = x1 - x2; dy = y1 - y2
        return math.sqrt(dx * dx + dy * dy)
    def ema_step(prev, target, alpha):
        return prev + alpha * (target - prev)

from .models import GestureResult, GestureType
from .tuning import (
    GESTURE_ACTION_COOLDOWN_S,
    GESTURE_CONFIRM_HOLD_S,
    GESTURE_DOUBLE_CLICK_WINDOW_S,
    GESTURE_DRAG_ACTIVATE_S,
    GESTURE_RIGHT_CLICK_HOLD_S,
    GESTURE_SCROLL_DIR_SWITCH_COOLDOWN_S,
)


class GestureDetector:
    def __init__(self) -> None:
        self._state = GestureType.PAUSE
        self._candidate = GestureType.PAUSE
        self._stable_start_t = 0.0

        self._dragging = False
        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_since: float | None = None
        self._right_pinch_start_t: float | None = None
        self._left_click_emitted_this_hold = False
        self._right_click_emitted_this_hold = False

        self._scroll_prev_y: float | None = None
        self._scroll_velocity_ema = 0.0
        self._scroll_direction = 0
        self._scroll_accumulator = 0.0
        self._scroll_last_switch_time = 0.0

        self._action_cooldown_s = float(GESTURE_ACTION_COOLDOWN_S)
        self._drag_activate_s = float(GESTURE_DRAG_ACTIVATE_S)

        self._pinch_enter = 0.22
        self._pinch_exit = 0.36
        self._confirm_hold_s = float(GESTURE_CONFIRM_HOLD_S)
        self._hand_scale = 24.0

        self._last_click_time = 0.0
        self._last_right_click_time = 0.0
        self._left_click_release_time = -float('inf')

        self._scroll_step_factor = 0.06
        self._scroll_deadband_factor = 0.04
        self._double_click_window_s = float(GESTURE_DOUBLE_CLICK_WINDOW_S)
        self._scroll_dir_switch_cooldown_s = float(GESTURE_SCROLL_DIR_SWITCH_COOLDOWN_S)
        self._scroll_step_limit = 8
        self._scroll_gain = 1.0
        self._right_click_hold_s = max(0.14, float(GESTURE_RIGHT_CLICK_HOLD_S))
        self._right_click_hold_s = min(self._right_click_hold_s, 0.18)

        # EMA-smoothed pinch ratios reduce false click flicker while keeping response quick.
        self._li_ema: float | None = None
        self._ri_ema: float | None = None
        self._pm_ema: float | None = None

        self._per_action_cooldown = {
            GestureType.LEFT_CLICK: 0.25,
            GestureType.RIGHT_CLICK: 0.50,
            GestureType.DOUBLE_CLICK: 0.50,
            GestureType.SCROLL: 0.0,
            GestureType.DRAG: 0.0,
            GestureType.MOVE: 0.0,
        }
        self._last_action_time: dict[GestureType, float] = {}
        self._action_lock_until: float = 0.0
        self._action_lock_type: GestureType = GestureType.PAUSE

        # Z-tap (kept for settings compat, disabled by default)
        self._z_tap_enabled = False
        self._prev_wrist_pos: tuple[float, float] | None = None

    @property
    def dragging(self) -> bool:
        return self._dragging

    def reset_cooldowns(self) -> None:
        self._last_action_time.clear()

    def _make_result(self, gesture: GestureType, scroll_delta: int = 0) -> GestureResult:
        return GestureResult(gesture, scroll_delta)

    def _pinch_ratios(self, xy, hand_scale: float) -> tuple[float, float, float]:
        hs = max(1.0, hand_scale)
        p4 = xy[4]; p8 = xy[8]; p12 = xy[12]
        li = pinch_dist_2d(float(p4[0]), float(p4[1]), float(p8[0]), float(p8[1])) / hs
        ri = pinch_dist_2d(float(p4[0]), float(p4[1]), float(p12[0]), float(p12[1])) / hs
        pm = pinch_dist_2d(float(p8[0]), float(p8[1]), float(p12[0]), float(p12[1])) / hs
        return li, ri, pm

    def _check_action_cooldown(self, gesture: GestureType, now: float) -> bool:
        cooldown = self._per_action_cooldown.get(gesture, self._action_cooldown_s)
        last = self._last_action_time.get(gesture, 0.0)
        return (now - last) >= cooldown

    def _record_action(self, gesture: GestureType, now: float) -> None:
        self._last_action_time[gesture] = now
        # Lock out cross-triggering for 200ms after any discrete action
        if gesture in {GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK,
                   GestureType.DOUBLE_CLICK}:
            self._action_lock_until = now + 0.20
            self._action_lock_type = gesture

    def _resolve_scroll(self, current_y: float, hand_scale: float) -> int:
        if self._scroll_prev_y is None:
            self._scroll_prev_y = current_y
            self._scroll_velocity_ema = 0.0
            self._scroll_direction = 0
            self._scroll_accumulator = 0.0
            return 0

        dy = float(self._scroll_prev_y) - current_y
        self._scroll_prev_y = current_y

        self._scroll_velocity_ema = ema_step(self._scroll_velocity_ema, dy, 0.25)
        v = self._scroll_velocity_ema

        deadband = max(1.0, hand_scale * self._scroll_deadband_factor)
        if abs(v) <= deadband:
            self._scroll_accumulator *= 0.5
            return 0

        step = max(1.0, hand_scale * self._scroll_step_factor)
        self._scroll_accumulator += v / step

        steps = int(self._scroll_accumulator)
        if steps == 0:
            return 0
        self._scroll_accumulator -= steps
        steps = max(-self._scroll_step_limit, min(self._scroll_step_limit, steps))

        direction = 1 if steps > 0 else -1
        if self._scroll_direction == 0:
            self._scroll_direction = direction
        elif direction != self._scroll_direction:
            # Ignore weak opposite spikes to avoid pause/freeze while scrolling steadily.
            if abs(v) < (deadband * 2.2):
                return 0
            now = time.monotonic()
            if now - self._scroll_last_switch_time < self._scroll_dir_switch_cooldown_s:
                # Keep momentum; do not hard-reset accumulator on blocked flips.
                self._scroll_accumulator *= 0.35
                return 0
            self._scroll_direction = direction
            self._scroll_last_switch_time = now
            # Dampen but preserve continuity when direction really changes.
            self._scroll_velocity_ema *= 0.5
            self._scroll_accumulator *= 0.5

        return int(steps * max(1, self._scroll_gain))

    def _clear_scroll(self) -> None:
        self._scroll_prev_y = None
        self._scroll_velocity_ema = 0.0
        self._scroll_direction = 0
        self._scroll_accumulator = 0.0

    # =====================================================================
    # DUAL-HAND MODE (default) — right hand = cursor, left hand = actions
    # =====================================================================
    def detect_dual(
        self,
        hands_dict: dict,
        is_grace: bool = False,
        cursor_label: str = "Right",
    ) -> GestureResult:
        """Process gestures from dual-hand input.

        By default RIGHT hand: cursor tracking, LEFT hand: click/scroll/drag.
        When cursor_label="Left", roles are swapped.

        If only cursor hand visible: return MOVE (cursor follows cursor hand)
        If only action hand visible: no cursor hand, keep MOVE (no action gestures)
        If neither: PAUSE
        """
        now = time.monotonic()
        cursor_label_norm = "Left" if str(cursor_label) == "Left" else "Right"
        action_label = "Right" if cursor_label_norm == "Left" else "Left"

        cursor_hand = hands_dict.get(cursor_label_norm)
        action_hand = hands_dict.get(action_label)

        # No hands at all
        if not cursor_hand and not action_hand:
            self._reset_all(now)
            return self._make_result(GestureType.PAUSE, 0)

        # Cursor hand missing: stay in MOVE and suppress actions to avoid accidental clicks.
        if not cursor_hand:
            self._state = GestureType.MOVE
            self._dragging = False
            return self._make_result(GestureType.MOVE, 0)

        # Cursor hand present but action hand absent: just MOVE.
        if action_hand is None:
            self._state = GestureType.MOVE
            self._dragging = False
            return self._make_result(GestureType.MOVE, 0)

        # Process gestures from left action hand.
        return self._process_action_hand(action_hand, now, is_grace)

    # =====================================================================
    # SINGLE-HAND MODE (legacy compat) — one hand does cursor + actions
    # =====================================================================
    def detect(self, hand_data: dict | None, is_grace_frame: bool = False) -> GestureResult:
        """Legacy single-hand detect. Same hand does cursor + gestures."""
        now = time.monotonic()
        if hand_data is None:
            self._reset_all(now)
            return self._make_result(GestureType.PAUSE, 0)

        return self._process_action_hand(hand_data, now, is_grace_frame)

    # =====================================================================
    # SHARED ACTION ENGINE — processes one hand for click/scroll/drag
    # =====================================================================
    def _process_action_hand(self, hand_data: dict, now: float,
                              is_grace: bool = False) -> GestureResult:
        xy = hand_data.get("xy")
        if not xy or len(xy) < 21:
            return self._make_result(GestureType.PAUSE, 0)

        confidence = float(hand_data.get("confidence", 0.0))
        if confidence < 0.10:
            return self._make_result(GestureType.PAUSE, 0)

        # Action lock: if we recently fired a discrete action, suppress other discrete actions
        if now < self._action_lock_until:
            locked_type = self._action_lock_type
            # Allow the same gesture type to continue (e.g., drag after click)
            # but block OTHER discrete gestures from firing
            if locked_type in {GestureType.LEFT_CLICK, GestureType.DOUBLE_CLICK}:
                # After a click, only allow MOVE, DRAG, SCROLL (not right-click)
                pass  # Don't return — just let the normal flow handle it
            elif locked_type == GestureType.RIGHT_CLICK:
                # After right-click, block all other clicks for the lock duration
                pass
            elif locked_type == GestureType.SCROLL:
                # During scroll, block clicks entirely
                if self._left_pinch_active or self._right_pinch_active:
                    self._left_pinch_active = False
                    self._right_pinch_active = False
                    self._right_pinch_start_t = None

        # Compute hand scale
        try:
            wrist = xy[0]; mcp9 = xy[9]
            self._hand_scale = max(24.0, pinch_dist_2d(
                float(wrist[0]), float(wrist[1]),
                float(mcp9[0]), float(mcp9[1])))
        except (IndexError, TypeError):
            return self._make_result(GestureType.PAUSE, 0)

        li_raw, ri_raw, pm_raw = self._pinch_ratios(xy, self._hand_scale)
        pinch_alpha = 0.50 if confidence < 0.6 else 0.65
        if self._li_ema is None:
            self._li_ema = li_raw
            self._ri_ema = ri_raw
            self._pm_ema = pm_raw
        else:
            self._li_ema = ema_step(self._li_ema, li_raw, pinch_alpha)
            self._ri_ema = ema_step(self._ri_ema, ri_raw, pinch_alpha)
            self._pm_ema = ema_step(self._pm_ema, pm_raw, pinch_alpha)

        li = float(self._li_ema)
        ri = float(self._ri_ema)
        pm = float(self._pm_ema)
        enter = float(self._pinch_enter)
        exit_ = float(self._pinch_exit)

        # Movement priority: if hand moved significantly, suppress click entry.
        # This prevents accidental clicks during fast cursor movement when
        # thumb brushes against index/middle finger.
        _movement_suppress = False
        if self._li_ema is not None:
            # Compare current pinch ratios to previous - if hand geometry
            # is changing rapidly, likely moving not pinching
            li_raw_now, ri_raw_now, pm_raw_now = self._pinch_ratios(xy, self._hand_scale)
            _wrist_x, _wrist_y = float(xy[0][0]), float(xy[0][1])
            _tip8_x, _tip8_y = float(xy[8][0]), float(xy[8][1])
            # If index tip is far from thumb AND hand is big (close to camera),
            # trust the pinch detection. Otherwise, if pinch ratios are near
            # the threshold boundary, apply movement suppression.
            if li_raw_now > (enter * 0.7) and li_raw_now < (exit_ * 1.1):
                # In the ambiguous zone - check if wrist is moving fast
                if hasattr(self, '_prev_wrist_pos') and self._prev_wrist_pos is not None:
                    _pw = self._prev_wrist_pos
                    _wrist_move = ((_wrist_x - _pw[0])**2 + (_wrist_y - _pw[1])**2)**0.5
                    if _wrist_move > self._hand_scale * 0.08:
                        _movement_suppress = True
            self._prev_wrist_pos = (_wrist_x, _wrist_y)
        else:
            self._prev_wrist_pos = (float(xy[0][0]), float(xy[0][1]))

        # --- Left pinch (thumb+index) = click/drag ---
        prev_left = self._left_pinch_active
        if self._left_pinch_active:
            if li > exit_:
                self._left_pinch_active = False
                self._left_click_release_time = now
                self._left_click_emitted_this_hold = False
        elif li <= enter and not _movement_suppress:
            self._left_pinch_active = True
            self._left_click_emitted_this_hold = False

        # --- Scroll pose: index+middle raised together, vertically oriented ---
        idx_tip = xy[8]; idx_pip = xy[6]
        mid_tip = xy[12]; mid_pip = xy[10]
        wrist = xy[0]
        idx_tip_dist = pinch_dist_2d(float(idx_tip[0]), float(idx_tip[1]), float(wrist[0]), float(wrist[1]))
        idx_pip_dist = pinch_dist_2d(float(idx_pip[0]), float(idx_pip[1]), float(wrist[0]), float(wrist[1]))
        mid_tip_dist = pinch_dist_2d(float(mid_tip[0]), float(mid_tip[1]), float(wrist[0]), float(wrist[1]))
        mid_pip_dist = pinch_dist_2d(float(mid_pip[0]), float(mid_pip[1]), float(wrist[0]), float(wrist[1]))
        extend_margin = max(4.0, self._hand_scale * 0.05)
        fingers_extended = (
            idx_tip_dist > (idx_pip_dist + extend_margin)
            and mid_tip_dist > (mid_pip_dist + extend_margin)
        )
        fingers_together = pm <= 0.50
        aligned_vertical = (
            abs(float(idx_tip[0]) - float(mid_tip[0])) <= (self._hand_scale * 0.30)
            and abs(float(idx_tip[1]) - float(mid_tip[1])) <= (self._hand_scale * 0.35)
        )
        scroll_pose = (
            fingers_extended
            and fingers_together
            and aligned_vertical
            and li > exit_
            and ri > exit_
        )

        # --- Right pinch (thumb+middle) = right-click ---
        # Requires: index finger clearly open (li > exit_),
        # middle+thumb close, held for _right_click_hold_s
        right_enter = enter * 0.88
        if self._right_pinch_active:
            if ri > exit_:
                self._right_pinch_active = False
                self._right_pinch_start_t = None
                self._right_click_emitted_this_hold = False
        elif (
            not self._left_pinch_active
            and not scroll_pose
            and not _movement_suppress
            and ri <= right_enter
            and li > (enter * 1.2)
            and pm > 0.22
        ):
            if self._right_pinch_start_t is None:
                self._right_pinch_start_t = now
            elif now - self._right_pinch_start_t >= self._right_click_hold_s:
                self._right_pinch_active = True
                self._right_click_emitted_this_hold = False
        else:
            self._right_pinch_start_t = None

        # --- Track pinch duration for drag ---
        if self._left_pinch_active:
            if self._left_pinch_since is None:
                self._left_pinch_since = now
        else:
            self._left_pinch_since = None

        # --- Route to raw state ---
        raw_state = GestureType.MOVE

        if self._left_pinch_active and self._left_pinch_since is not None:
            held = now - self._left_pinch_since
            if held >= self._drag_activate_s:
                raw_state = GestureType.DRAG
            else:
                raw_state = GestureType.LEFT_CLICK
        elif self._right_pinch_active:
            raw_state = GestureType.RIGHT_CLICK
        elif scroll_pose:
            raw_state = GestureType.SCROLL
            # Force-clear pinch states during scroll to prevent click cross-triggers
            self._left_pinch_active = False
            self._right_pinch_active = False
            self._left_pinch_since = None
            self._right_pinch_start_t = None
            self._left_click_emitted_this_hold = False
            self._right_click_emitted_this_hold = False

        # --- Stability filter ---
        if raw_state != self._candidate:
            self._candidate = raw_state
            self._stable_start_t = now

        hold_elapsed = max(0.0, now - self._stable_start_t)
        if is_grace:
            stable_state = self._state if self._state not in {
                GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK,
                GestureType.DOUBLE_CLICK} else GestureType.MOVE
        elif hold_elapsed >= self._confirm_hold_s:
            stable_state = self._candidate
        else:
            stable_state = self._state

        # --- Clear scroll when not scrolling ---
        if stable_state != GestureType.SCROLL and self._state != GestureType.SCROLL:
            self._clear_scroll()

        # --- Emit actions ---
        if stable_state == GestureType.LEFT_CLICK:
            if (not self._left_click_emitted_this_hold) and self._check_action_cooldown(GestureType.LEFT_CLICK, now):
                # Double-click detection
                if (self._left_click_release_time > 0.0
                    and 0.0 < (now - self._left_click_release_time) <= self._double_click_window_s
                    and self._check_action_cooldown(GestureType.DOUBLE_CLICK, now)):
                    self._state = GestureType.DOUBLE_CLICK
                    self._record_action(GestureType.DOUBLE_CLICK, now)
                    self._record_action(GestureType.LEFT_CLICK, now)
                    self._left_click_emitted_this_hold = True
                    self._dragging = False
                    return self._make_result(GestureType.DOUBLE_CLICK, 0)

                self._state = GestureType.LEFT_CLICK
                self._record_action(GestureType.LEFT_CLICK, now)
                self._left_click_emitted_this_hold = True
                self._dragging = False
                return self._make_result(GestureType.LEFT_CLICK, 0)
            # Keep state as LEFT_CLICK so cursor stays frozen (don't switch to MOVE)
            self._state = GestureType.LEFT_CLICK
            return self._make_result(GestureType.LEFT_CLICK, 0)

        if stable_state == GestureType.RIGHT_CLICK:
            if (not self._right_click_emitted_this_hold) and self._check_action_cooldown(GestureType.RIGHT_CLICK, now):
                self._state = GestureType.RIGHT_CLICK
                self._record_action(GestureType.RIGHT_CLICK, now)
                self._right_click_emitted_this_hold = True
                self._dragging = False
                return self._make_result(GestureType.RIGHT_CLICK, 0)
            self._state = GestureType.RIGHT_CLICK
            return self._make_result(GestureType.RIGHT_CLICK, 0)

        if stable_state == GestureType.DRAG:
            self._dragging = True
            self._state = GestureType.DRAG
            return self._make_result(GestureType.DRAG, 0)

        if stable_state == GestureType.SCROLL:
            scroll_y = (float(xy[8][1]) + float(xy[12][1])) * 0.5
            delta = self._resolve_scroll(scroll_y, self._hand_scale)
            self._state = GestureType.SCROLL
            self._dragging = False
            self._action_lock_until = now + 0.10
            self._action_lock_type = GestureType.SCROLL
            return self._make_result(GestureType.SCROLL, delta)

        self._state = GestureType.MOVE
        self._dragging = False
        return self._make_result(GestureType.MOVE, 0)

    def _reset_all(self, now: float) -> None:
        self._state = GestureType.PAUSE
        self._candidate = GestureType.PAUSE
        self._stable_start_t = now
        self._dragging = False
        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_since = None
        self._left_click_emitted_this_hold = False
        self._right_click_emitted_this_hold = False
        self._li_ema = None
        self._ri_ema = None
        self._pm_ema = None
        self._right_pinch_start_t = None
        self._action_lock_until = 0.0
        self._action_lock_type = GestureType.PAUSE
        self._prev_wrist_pos = None
        self._clear_scroll()

# Holographic Touch — Manual Test Checklist

Run through each item. All must pass before release.

## Startup
- [ ] App launches without errors
- [ ] Camera detects and starts
- [ ] No console spam (only startup messages)
- [ ] FPS counter shows 20+ FPS

## Dual-Hand Mode (default)
- [ ] Show LEFT hand: cursor follows left index finger smoothly
- [ ] Show RIGHT hand: cursor follows right index (fallback)
- [ ] Show BOTH hands: cursor follows LEFT, gestures use RIGHT
- [ ] Move left hand across camera view: cursor reaches all screen edges
- [ ] Cursor is smooth — no jitter, no pausing, no teleporting

## Left Click (Right hand: thumb+index pinch)
- [ ] Pinch right thumb+index: single left click fires
- [ ] Release and pinch again: another click (no spam)
- [ ] Click registers on UI elements (try clicking buttons, links)

## Double Click
- [ ] Quick pinch-release-pinch within 0.45s: double click fires
- [ ] Slow pinch-release-pinch (>0.5s): two single clicks, not double

## Right Click
- [ ] Right hand: pinch thumb+middle while index is extended
- [ ] Must hold 0.18s before triggering (no accidental fires)
- [ ] Context menu appears at cursor position

## Scroll
- [ ] Right hand: peace sign (index+middle extended)
- [ ] Move hand UP: page scrolls UP
- [ ] Move hand DOWN: page scrolls DOWN  
- [ ] Scroll is smooth — no jerking
- [ ] Stop hand: scroll stops

## Drag
- [ ] Right hand: hold thumb+index pinch for 0.45s
- [ ] Drag activates — move left hand to drag
- [ ] Release pinch: drag ends cleanly
- [ ] No stuck drags

## Eye Tracking (experimental)
- [ ] Change to eye tracking mode in Settings → Gestures
- [ ] Restart camera
- [ ] Cursor follows eye/head movement
- [ ] Right hand gestures still work for clicks/scroll

## UI
- [ ] Badge shows "DUAL HAND" in dual mode, "IRIS TRACK" in eye mode
- [ ] Hand status shows L: ● R: ● when both hands visible
- [ ] Settings dialog opens and closes without crash
- [ ] Cursor mode dropdown works in settings
- [ ] Window resizes without layout breaking
- [ ] All text readable, no clipping

## Stability
- [ ] Wave hand in/out of view: no crashes, no ghost clicks
- [ ] Cover camera: app handles gracefully
- [ ] Run for 5 minutes: no memory leak, no FPS degradation
- [ ] Enable Mouse → Minimize → Overlay appears → works

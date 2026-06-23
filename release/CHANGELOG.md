# Changelog

All notable changes to **HoloTouch** will be documented in this file.

## [1.0.0] - 2026-06-23

### Added
- Standard single-file executable packaging (`HoloTouch.exe`).
- High-fidelity Windows application icon support.
- Fully integrated MediaPipe + PySide6 mouse mapping framework.
- Core gestures: Left Click, Double Click, Right Click, Drag, and Vertical Scroll.
- Dynamic control region mapping to capture corners of physical screen accurately.

### Fixed
- Fixed critical camera thread loop exception by correcting the missing `self._edge_ratio` attribute.
- Resolved skeleton visual flickering on micro-drops by adding a stable 3-frame grace buffer.
- Corrected cursor tracking latency by tuning fingertip blend speed and smoothing coefficients.

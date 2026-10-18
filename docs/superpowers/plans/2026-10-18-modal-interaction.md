# Modal Interaction Mode, Precision Layer & Left Hand v2 — Implementation Plan

**Goal:** Implement the design in four independently reviewable PRs, keeping `classic` mode as the default and fully working at every step.

**Spec:** `docs/superpowers/specs/2026-10-18-modal-interaction-design.md`

**Tech stack:** Python 3.13, MediaPipe Tasks API (VIDEO mode), pynput + ctypes SendInput, 1€ filter, tkinter (HUD), winsound, pytest (dev only).

**Conventions:** Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`), one logical change per commit, every new constant lives in `config.py`, every task ends with `pytest` green and `python test_startup.py` 4/4.

---

## Branch Layout

```
main (upstream)
 └─ fix/gesture-bugs                 → PR 1
     └─ feat/precision-layer         → PR 2
         └─ feat/modal-mode          → PR 3
             └─ feat/left-hand-v2    → PR 4
```

Each branch is rebased on its parent when the parent changes. After PR N is merged upstream, PR N+1 is rebased onto `main`.

---

## PR 1 — `fix/gesture-bugs`

### Task 1.1: Test scaffolding
- [ ] Create `requirements-dev.txt` (`pytest`)
- [ ] Create `tests/conftest.py` (adds repo root to `sys.path`)
- [ ] Create `tests/fakes.py` → `FakeActuator` recording every call and tracking pressed keys/buttons
- [ ] Create `tests/fixtures/hands.py` → `make_hand(pose, scale, rotation_deg, center)` returning 21 `Landmark`s
- [ ] Commit: `test: add pytest scaffolding, FakeActuator and synthetic hand fixtures`

### Task 1.2: Fix double click
- [ ] Test: two pinches 0.25 s apart → `double_click` called once, no extra `left_click`
- [ ] In `right_hand.py`, apply the cooldown only between *different* gesture types; measure the double-click window from the first click's release
- [ ] Commit: `fix: double click could never fire because cooldown equalled the double-click window`

### Task 1.3: Edge-triggered right click
- [ ] Test: thumb+middle held 2 s → exactly one `right_click`
- [ ] Track `_right_pinch_active`; fire on enter, re-arm on release
- [ ] Commit: `fix: right click no longer auto-repeats while thumb and middle stay together`

### Task 1.4: Honour hand-count flags
- [ ] Add `LEFT_HAND_ENABLED`, `TWO_HAND_GESTURES_ENABLED` to `config.py` (default `True`, current behaviour)
- [ ] `tracker.py`: `num_hands = 1 if not LEFT_HAND_ENABLED else MP_MAX_HANDS`; set `MP_MAX_HANDS = 2`; log the real value
- [ ] `orchestrator.py`: skip left / two-hand processors when disabled
- [ ] Commit: `fix: respect MP_MAX_HANDS and add flags to disable left-hand and two-hand gestures`

### Task 1.5: LICENSE + docs
- [ ] Add MIT `LICENSE` (© Rcidshacker) — only if the maintainer agrees in the issue
- [ ] README: document the new flags; "Running tests" section
- [ ] Commit: `docs: add LICENSE file and document hand flags and tests`

**Acceptance:** classic behaviour unchanged except the fixed bugs; `pytest` green.

---

## PR 2 — `feat/precision-layer`

### Task 2.1: VIDEO-mode tracking
- [ ] `RunningMode.VIDEO` + `detect_for_video(image, int(time_ms))` with monotonic timestamps
- [ ] Verify FPS and CPU vs IMAGE mode (log both in the PR description)
- [ ] Commit: `feat: use MediaPipe VIDEO running mode for temporal hand tracking`

### Task 2.2: Handedness stabilization + dominant hand
- [ ] Label persistence over `HANDEDNESS_STABLE_FRAMES`; x-position tie-break when labels collide
- [ ] `DOMINANT_HAND`; `HandsResult.dominant` / `.support`
- [ ] Tests: label flicker suppressed; collision resolved; swap works
- [ ] Commit: `feat: stabilize handedness labels and add DOMINANT_HAND setting`

### Task 2.3: PoseClassifier
- [ ] `core/gestures/poses.py`: pixel-space geometry, hand scale, rotation-invariant extension, `Pose` enum, pinch hysteresis
- [ ] Tests: every pose × 3 scales × 3 rotations; hysteresis enter/exit
- [ ] Commit: `feat: add scale- and rotation-invariant pose classifier with pinch hysteresis`

### Task 2.4: PoseStabilizer + hold timers
- [ ] `core/gestures/stabilizer.py`: `PoseStabilizer(stable_ms)`, `HoldTimer(duration, stillness=None)` with injected clock
- [ ] Tests: short flickers ignored; hold completes / aborts; stillness check
- [ ] Commit: `feat: add pose stabilizer and hold timers`

### Task 2.5: Pointer module
- [ ] `core/pointer.py`: absolute (existing logic moved), relative with acceleration, click freeze + rollback buffer, clutch
- [ ] Classic `right_hand.py` uses `Pointer` (absolute by default → no behaviour change)
- [ ] Tests: relative deltas, acceleration cap, rollback position, clutch without jump
- [ ] Commit: `refactor: extract cursor mapping into Pointer and add relative mode`

**Acceptance:** classic unchanged by default; `CURSOR_MAPPING = "relative"` usable in classic.

---

## PR 3 — `feat/modal-mode`

### Task 3.1: Actions registry + actuator helpers
- [ ] `MouseActuator`: `press_combo`, `key_down`, `key_up`, `hscroll`, `release_all`
- [ ] `core/actions.py`: registry of named actions (spec §6)
- [ ] Tests (FakeActuator): each action emits the expected combo
- [ ] Commit: `feat: add named actions registry and generic key helpers`

### Task 3.2: ModeManager
- [ ] `core/gestures/mode_manager.py`: DISARMED / armed modes; arm (still ONE), switch (hold N), pause (fist), disarm (fist hold), auto-disarm; switch paused during pinch; `exit()` on every transition
- [ ] Tests: all transitions, including the safety invariant (nothing pressed after any transition)
- [ ] Commit: `feat: add modal ModeManager with arm, switch, pause and disarm`

### Task 3.3: Modes
- [ ] `modes/move.py` — clicks, double, drag, right click, clutch (uses `Pointer`)
- [ ] `modes/scroll.py` — joystick center, dead zone, accumulator, horizontal, zoom, re-center
- [ ] `modes/shortcuts.py` — swipe detector (user-space directions, re-arm), pinch bindings
- [ ] `modes/media.py` — volume joystick, play/pause, mute, tracks
- [ ] Tests per mode with FakeActuator
- [ ] One commit per mode: `feat(modal): add MOVE mode`, …

### Task 3.4: Orchestrator wiring
- [ ] `INTERACTION_MODE` selects classic vs modal pipeline; modal defaults (`CURSOR_MAPPING="relative"`, two-hand off) applied unless explicitly set
- [ ] `main.py`: `release_all()` in `finally`
- [ ] Commit: `feat: wire modal pipeline behind INTERACTION_MODE`

### Task 3.5: HUD + sounds
- [ ] `core/hud.py`: Tk thread, click-through topmost pill, progress bar, hand dot, badges, toast; `HUD_ENABLED`, `HUD_POSITION`
- [ ] `core/feedback.py`: async cues; `SOUNDS_ENABLED`
- [ ] Manual verification on Windows (screenshot / GIF for the PR)
- [ ] Commit: `feat: add on-screen HUD and sound cues for modal state`

### Task 3.6: Docs
- [ ] README "Modal mode" section: global rules, mode tables, config, calibration tips
- [ ] Commit: `docs: document modal interaction mode`

**Acceptance:** manual checklist (spec) passes for dominant hand; classic untouched.

---

## PR 4 — `feat/left-hand-v2`

### Task 4.1: Support hand processor
- [ ] `core/gestures/support_hand.py`: armed-only, hold-to-fire, edge triggering, neutral re-arm
- [ ] Window switcher (Alt held, Tab / Shift+Tab taps, release on V drop / hand lost / disarm / timeout)
- [ ] Ctrl only while dominant hand visible
- [ ] ONE + swipe bindings; `LEFT_HAND_BINDINGS`
- [ ] Tests: switcher lifecycle, Ctrl gating, every binding, safety invariant
- [ ] Commit: `feat: add left hand v2 with held window switcher and configurable bindings`

### Task 4.2: HUD integration + docs
- [ ] HUD badges (`CTRL`, `ALT+TAB`) and action toasts
- [ ] README left-hand table (modal) next to the classic one
- [ ] Commit: `feat: show support-hand state in HUD` / `docs: document left hand v2`

**Acceptance:** full manual checklist passes; `DOMINANT_HAND="left"` verified.

---

## Contribution Workflow

1. Fork `Rcidshacker/airmouse`; local remotes: `origin` = fork, `upstream` = original.
2. Open an issue linking this spec (proposal + open questions) before the first PR.
3. Open PR 1 as soon as it is ready; open later PRs as drafts that reference the previous one.
4. PR description template: *What / Why / How tested (pytest output + manual checklist) / Screenshots or GIF / Breaking changes: none (classic default)*.

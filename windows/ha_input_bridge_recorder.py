from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pynput import keyboard, mouse


RecordingMode = Literal["mouse", "mouse_keyboard"]

MIN_DELAY_MS = 80
DELAY_ROUND_MS = 50
MAX_DELAY_MS = 5000

TEXT_PAUSE_SPLIT_MS = 700

START_RECORDING_IGNORE_MS = 1000

DOUBLE_CLICK_MS = 350
DOUBLE_CLICK_DISTANCE_PX = 6

CLICK_MAX_MS = 500
CLICK_MAX_DISTANCE_PX = 8

DRAG_START_MIN_MS = 120
DRAG_START_MIN_DISTANCE_PX = 12
DRAG_MOVE_MIN_INTERVAL_MS = 120
DRAG_MOVE_MIN_DISTANCE_PX = 20

SCROLL_MULTIPLIER = 10
MAX_SCROLL_AMOUNT = 120

DEFAULT_ALIAS = "PC - Recorded input"

MODIFIER_ORDER = ["ctrl", "alt", "shift", "win"]

SPECIAL_KEY_MAP = {
    keyboard.Key.enter: "enter",
    keyboard.Key.esc: "esc",
    keyboard.Key.tab: "tab",
    keyboard.Key.backspace: "backspace",
    keyboard.Key.delete: "delete",
    keyboard.Key.left: "left",
    keyboard.Key.right: "right",
    keyboard.Key.up: "up",
    keyboard.Key.down: "down",
    keyboard.Key.home: "home",
    keyboard.Key.end: "end",
    keyboard.Key.page_up: "pageup",
    keyboard.Key.page_down: "pagedown",
    keyboard.Key.space: "space",
}

MODIFIER_KEY_MAP = {
    keyboard.Key.ctrl: "ctrl",
    keyboard.Key.ctrl_l: "ctrl",
    keyboard.Key.ctrl_r: "ctrl",
    keyboard.Key.alt: "alt",
    keyboard.Key.alt_l: "alt",
    keyboard.Key.alt_r: "alt",
    keyboard.Key.alt_gr: "alt",
    keyboard.Key.shift: "shift",
    keyboard.Key.shift_l: "shift",
    keyboard.Key.shift_r: "shift",
    keyboard.Key.cmd: "win",
    keyboard.Key.cmd_l: "win",
    keyboard.Key.cmd_r: "win",
}

MOUSE_BUTTON_MAP = {
    mouse.Button.left: "left",
    mouse.Button.right: "right",
    mouse.Button.middle: "middle",
}


@dataclass
class MouseDownState:
    button: str
    x: int
    y: int
    time_ms: int
    emitted_down: bool = False
    last_drag_move_x: int | None = None
    last_drag_move_y: int | None = None
    last_drag_move_time_ms: int | None = None


class RecorderError(Exception):
    """Raised when the recorder cannot start or stop safely."""


class HAInputBridgeRecorder:
    """Record mouse and optional keyboard input and generate Home Assistant script YAML."""

    def __init__(
        self,
        recordings_dir: Path,
        mode: RecordingMode = "mouse",
        alias: str = DEFAULT_ALIAS,
        virtual_desktop: dict[str, Any] | None = None,
        start_ignore_ms: int = START_RECORDING_IGNORE_MS,
    ) -> None:
        self.recordings_dir = Path(recordings_dir)
        self.mode: RecordingMode = mode
        self.alias = alias.strip() or DEFAULT_ALIAS
        self.virtual_desktop = virtual_desktop or {}
        self.start_ignore_ms = int(start_ignore_ms)

        self._lock = threading.RLock()

        self._recording = False
        self._cancelled = False

        self._started_at_ms = 0
        self._ignore_until_ms = 0
        self._stopped_at_ms = 0

        self._actions: list[dict[str, Any]] = []

        self._last_output_time_ms: int | None = None
        self._last_mouse_x: int | None = None
        self._last_mouse_y: int | None = None
        self._last_emitted_mouse_x: int | None = None
        self._last_emitted_mouse_y: int | None = None

        self._mouse_down: dict[str, MouseDownState] = {}

        self._text_buffer = ""
        self._text_start_time_ms: int | None = None
        self._text_last_time_ms: int | None = None

        self._pressed_modifiers: set[str] = set()
        self._hotkey_down_keys: set[str] = set()

        self._mouse_listener: mouse.Listener | None = None
        self._keyboard_listener: keyboard.Listener | None = None

        self._last_recording_file: Path | None = None

        self._ignore_rects: list[tuple[int, int, int, int]] = []

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    @property
    def last_recording_file(self) -> Path | None:
        with self._lock:
            return self._last_recording_file

    def set_ignore_rects(self, rects: list[tuple[int, int, int, int]]) -> None:
        """Set screen rectangles that should be ignored by mouse recording.

        Rect tuple format:
        (left, top, right, bottom)
        """

        normalized: list[tuple[int, int, int, int]] = []

        for rect in rects:
            try:
                left, top, right, bottom = rect
                left = int(left)
                top = int(top)
                right = int(right)
                bottom = int(bottom)
            except (TypeError, ValueError):
                continue

            if right < left:
                left, right = right, left

            if bottom < top:
                top, bottom = bottom, top

            normalized.append((left, top, right, bottom))

        with self._lock:
            self._ignore_rects = normalized

    def start(self) -> None:
        """Start listeners."""

        with self._lock:
            if self._recording:
                raise RecorderError("Recorder is already running")

            self._reset_state()
            now = self._now_ms()
            self._recording = True
            self._started_at_ms = now
            self._ignore_until_ms = now + max(0, self.start_ignore_ms)

            self._mouse_listener = mouse.Listener(
                on_move=self._on_mouse_move,
                on_click=self._on_mouse_click,
                on_scroll=self._on_mouse_scroll,
            )
            self._mouse_listener.start()

            if self.mode == "mouse_keyboard":
                self._keyboard_listener = keyboard.Listener(
                    on_press=self._on_key_press,
                    on_release=self._on_key_release,
                )
                self._keyboard_listener.start()

    def stop_and_save(self) -> tuple[str, Path]:
        """Stop listeners, generate YAML, save it, and return content plus path."""

        with self._lock:
            if not self._recording:
                raise RecorderError("Recorder is not running")

            self._stopped_at_ms = self._now_ms()
            self._recording = False

        self._stop_listeners()

        with self._lock:
            self._flush_text_locked(self._stopped_at_ms)
            self._finalize_open_mouse_buttons_locked(self._stopped_at_ms)

            if (
                not self._actions
                and self._last_mouse_x is not None
                and self._last_mouse_y is not None
            ):
                self._emit_move_locked(
                    self._stopped_at_ms,
                    self._last_mouse_x,
                    self._last_mouse_y,
                    force=True,
                )

            yaml_text = self._build_yaml_locked()
            path = self._save_yaml_locked(yaml_text)
            self._last_recording_file = path

            return yaml_text, path

    def stop_without_saving(self) -> None:
        """Stop listeners and discard current recording."""

        with self._lock:
            if not self._recording:
                return

            self._recording = False
            self._cancelled = True

        self._stop_listeners()

    def get_status(self) -> dict[str, Any]:
        """Return recorder status for UI."""

        with self._lock:
            now = self._now_ms()
            duration_ms = max(0, now - self._started_at_ms) if self._started_at_ms else 0

            return {
                "recording": self._recording,
                "mode": self.mode,
                "duration_ms": duration_ms,
                "action_count": len([a for a in self._actions if a.get("type") != "delay"]),
                "raw_action_count": len(self._actions),
                "last_mouse_x": self._last_mouse_x,
                "last_mouse_y": self._last_mouse_y,
                "text_buffer_length": len(self._text_buffer),
                "last_recording_file": str(self._last_recording_file) if self._last_recording_file else "",
            }

    def _reset_state(self) -> None:
        self._recording = False
        self._cancelled = False

        self._started_at_ms = 0
        self._ignore_until_ms = 0
        self._stopped_at_ms = 0

        self._actions = []

        self._last_output_time_ms = None
        self._last_mouse_x = None
        self._last_mouse_y = None
        self._last_emitted_mouse_x = None
        self._last_emitted_mouse_y = None

        self._mouse_down = {}

        self._text_buffer = ""
        self._text_start_time_ms = None
        self._text_last_time_ms = None

        self._pressed_modifiers = set()
        self._hotkey_down_keys = set()

        self._mouse_listener = None
        self._keyboard_listener = None

    def _stop_listeners(self) -> None:
        with self._lock:
            mouse_listener = self._mouse_listener
            keyboard_listener = self._keyboard_listener
            self._mouse_listener = None
            self._keyboard_listener = None

        if mouse_listener is not None:
            try:
                mouse_listener.stop()
            except Exception:
                pass

        if keyboard_listener is not None:
            try:
                keyboard_listener.stop()
            except Exception:
                pass

    def _now_ms(self) -> int:
        return int(time.monotonic() * 1000)

    def _inside_ignore_rect_locked(self, x: int, y: int) -> bool:
        for left, top, right, bottom in self._ignore_rects:
            if left <= x <= right and top <= y <= bottom:
                return True

        return False

    def _should_ignore_locked(self, event_time_ms: int) -> bool:
        return (
            not self._recording
            or self._cancelled
            or event_time_ms < self._ignore_until_ms
        )

    def _should_ignore_mouse_locked(self, event_time_ms: int, x: int, y: int) -> bool:
        return self._should_ignore_locked(event_time_ms) or self._inside_ignore_rect_locked(x, y)

    def _round_delay_ms(self, delay_ms: int) -> int:
        delay_ms = max(0, min(int(delay_ms), MAX_DELAY_MS))
        return int(round(delay_ms / DELAY_ROUND_MS) * DELAY_ROUND_MS)

    def _emit_delay_if_needed_locked(self, action_time_ms: int) -> None:
        if self._last_output_time_ms is None:
            self._last_output_time_ms = action_time_ms
            return

        delay_ms = action_time_ms - self._last_output_time_ms

        if delay_ms < MIN_DELAY_MS:
            return

        rounded = self._round_delay_ms(delay_ms)

        if rounded < MIN_DELAY_MS:
            return

        self._actions.append(
            {
                "type": "delay",
                "milliseconds": rounded,
                "_time_ms": action_time_ms,
            }
        )

    def _emit_action_locked(
        self,
        action_time_ms: int,
        action: dict[str, Any],
        output_end_time_ms: int | None = None,
    ) -> None:
        self._emit_delay_if_needed_locked(action_time_ms)

        normalized = dict(action)
        normalized["_time_ms"] = action_time_ms
        self._actions.append(normalized)

        self._last_output_time_ms = output_end_time_ms or action_time_ms

    def _distance(self, x1: int, y1: int, x2: int, y2: int) -> float:
        return math.hypot(x2 - x1, y2 - y1)

    def _emit_move_locked(
        self,
        action_time_ms: int,
        x: int,
        y: int,
        force: bool = False,
    ) -> None:
        if (
            not force
            and self._last_emitted_mouse_x == x
            and self._last_emitted_mouse_y == y
        ):
            return

        self._emit_action_locked(
            action_time_ms,
            {
                "type": "move",
                "x": int(x),
                "y": int(y),
            },
        )

        self._last_emitted_mouse_x = int(x)
        self._last_emitted_mouse_y = int(y)

    def _emit_click_locked(
        self,
        action_time_ms: int,
        x: int,
        y: int,
        button: str,
    ) -> None:
        self._flush_text_locked(action_time_ms)

        last_index = self._find_last_non_delay_action_index_locked()

        if last_index is not None:
            previous = self._actions[last_index]
            previous_time = int(previous.get("_time_ms", 0))

            if (
                previous.get("type") == "click"
                and previous.get("button") == button
                and int(previous.get("clicks", 1)) < 3
                and action_time_ms - previous_time <= DOUBLE_CLICK_MS
                and self._distance(
                    int(previous.get("x", x)),
                    int(previous.get("y", y)),
                    x,
                    y,
                )
                <= DOUBLE_CLICK_DISTANCE_PX
            ):
                previous["clicks"] = int(previous.get("clicks", 1)) + 1
                previous["_time_ms"] = action_time_ms
                self._last_output_time_ms = action_time_ms
                return

        self._emit_move_locked(action_time_ms, x, y)

        self._emit_action_locked(
            action_time_ms,
            {
                "type": "click",
                "button": button,
                "clicks": 1,
                "x": int(x),
                "y": int(y),
            },
        )

    def _find_last_non_delay_action_index_locked(self) -> int | None:
        for index in range(len(self._actions) - 1, -1, -1):
            if self._actions[index].get("type") != "delay":
                return index

        return None

    def _on_mouse_move(self, x: int, y: int) -> None:
        event_time_ms = self._now_ms()

        with self._lock:
            x = int(x)
            y = int(y)

            if self._should_ignore_mouse_locked(event_time_ms, x, y):
                return

            self._last_mouse_x = x
            self._last_mouse_y = y

            for state in list(self._mouse_down.values()):
                self._maybe_emit_drag_move_locked(event_time_ms, state, x, y)

    def _on_mouse_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        event_time_ms = self._now_ms()
        mapped_button = MOUSE_BUTTON_MAP.get(button)

        if not mapped_button:
            return

        with self._lock:
            x = int(x)
            y = int(y)

            if self._should_ignore_mouse_locked(event_time_ms, x, y):
                return

            self._last_mouse_x = x
            self._last_mouse_y = y

            if pressed:
                self._flush_text_locked(event_time_ms)
                self._mouse_down[mapped_button] = MouseDownState(
                    button=mapped_button,
                    x=x,
                    y=y,
                    time_ms=event_time_ms,
                )
                return

            state = self._mouse_down.pop(mapped_button, None)

            if state is None:
                self._flush_text_locked(event_time_ms)
                self._emit_move_locked(event_time_ms, x, y)
                self._emit_action_locked(
                    event_time_ms,
                    {
                        "type": "mouse_up",
                        "button": mapped_button,
                    },
                )
                return

            duration_ms = event_time_ms - state.time_ms
            movement_px = self._distance(state.x, state.y, x, y)

            if (
                not state.emitted_down
                and duration_ms <= CLICK_MAX_MS
                and movement_px <= CLICK_MAX_DISTANCE_PX
            ):
                self._emit_click_locked(event_time_ms, x, y, mapped_button)
                return

            if not state.emitted_down:
                self._flush_text_locked(state.time_ms)
                self._emit_move_locked(state.time_ms, state.x, state.y, force=True)
                self._emit_action_locked(
                    state.time_ms,
                    {
                        "type": "mouse_down",
                        "button": mapped_button,
                    },
                )

            self._emit_move_locked(event_time_ms, x, y, force=True)
            self._emit_action_locked(
                event_time_ms,
                {
                    "type": "mouse_up",
                    "button": mapped_button,
                },
            )

    def _maybe_emit_drag_move_locked(
        self,
        event_time_ms: int,
        state: MouseDownState,
        x: int,
        y: int,
    ) -> None:
        duration_ms = event_time_ms - state.time_ms
        movement_from_start = self._distance(state.x, state.y, x, y)

        if (
            not state.emitted_down
            and duration_ms >= DRAG_START_MIN_MS
            and movement_from_start >= DRAG_START_MIN_DISTANCE_PX
        ):
            self._flush_text_locked(state.time_ms)
            self._emit_move_locked(state.time_ms, state.x, state.y, force=True)
            self._emit_action_locked(
                state.time_ms,
                {
                    "type": "mouse_down",
                    "button": state.button,
                },
            )
            state.emitted_down = True
            state.last_drag_move_x = state.x
            state.last_drag_move_y = state.y
            state.last_drag_move_time_ms = state.time_ms

        if not state.emitted_down:
            return

        if state.last_drag_move_time_ms is None:
            should_emit = True
        else:
            interval_ok = event_time_ms - state.last_drag_move_time_ms >= DRAG_MOVE_MIN_INTERVAL_MS
            distance_ok = (
                self._distance(
                    int(state.last_drag_move_x or state.x),
                    int(state.last_drag_move_y or state.y),
                    x,
                    y,
                )
                >= DRAG_MOVE_MIN_DISTANCE_PX
            )
            should_emit = interval_ok and distance_ok

        if not should_emit:
            return

        self._emit_move_locked(event_time_ms, x, y, force=True)

        state.last_drag_move_x = x
        state.last_drag_move_y = y
        state.last_drag_move_time_ms = event_time_ms

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        event_time_ms = self._now_ms()

        with self._lock:
            x = int(x)
            y = int(y)

            if self._should_ignore_mouse_locked(event_time_ms, x, y):
                return

            self._last_mouse_x = x
            self._last_mouse_y = y

            self._flush_text_locked(event_time_ms)
            self._emit_move_locked(event_time_ms, x, y)

            amount = int(dy * SCROLL_MULTIPLIER)
            amount = max(-MAX_SCROLL_AMOUNT, min(MAX_SCROLL_AMOUNT, amount))

            if amount == 0:
                return

            self._emit_action_locked(
                event_time_ms,
                {
                    "type": "scroll",
                    "amount": amount,
                },
            )

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        event_time_ms = self._now_ms()

        with self._lock:
            if self._should_ignore_locked(event_time_ms):
                return

            modifier = MODIFIER_KEY_MAP.get(key)

            if modifier:
                self._pressed_modifiers.add(modifier)
                return

            key_name = self._keyboard_key_name(key)
            printable = self._keyboard_printable_char(key)

            if self._pressed_modifiers and key_name:
                combo = self._normalized_hotkey_keys(key_name)
                combo_key = "+".join(combo)

                if combo_key in self._hotkey_down_keys:
                    return

                self._hotkey_down_keys.add(combo_key)
                self._flush_text_locked(event_time_ms)
                self._emit_action_locked(
                    event_time_ms,
                    {
                        "type": "hotkey",
                        "keys": combo,
                    },
                )
                return

            if printable is not None:
                self._append_text_locked(event_time_ms, printable)
                return

            if key_name:
                self._flush_text_locked(event_time_ms)
                self._emit_action_locked(
                    event_time_ms,
                    {
                        "type": "press",
                        "key": key_name,
                    },
                )

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        with self._lock:
            modifier = MODIFIER_KEY_MAP.get(key)

            if modifier:
                self._pressed_modifiers.discard(modifier)

                if not self._pressed_modifiers:
                    self._hotkey_down_keys.clear()

    def _keyboard_key_name(self, key: keyboard.Key | keyboard.KeyCode | None) -> str | None:
        if key is None:
            return None

        if key in SPECIAL_KEY_MAP:
            return SPECIAL_KEY_MAP[key]

        try:
            char = getattr(key, "char", None)
        except Exception:
            char = None

        if isinstance(char, str) and len(char) == 1:
            return char.lower()

        return None

    def _keyboard_printable_char(self, key: keyboard.Key | keyboard.KeyCode | None) -> str | None:
        if key is None:
            return None

        if key == keyboard.Key.space:
            return " "

        if key in SPECIAL_KEY_MAP:
            return None

        try:
            char = getattr(key, "char", None)
        except Exception:
            return None

        if isinstance(char, str) and len(char) == 1 and char.isprintable():
            return char

        return None

    def _normalized_hotkey_keys(self, key_name: str) -> list[str]:
        keys = [modifier for modifier in MODIFIER_ORDER if modifier in self._pressed_modifiers]

        if key_name not in keys:
            keys.append(key_name)

        return keys

    def _append_text_locked(self, event_time_ms: int, char: str) -> None:
        if (
            self._text_buffer
            and self._text_last_time_ms is not None
            and event_time_ms - self._text_last_time_ms >= TEXT_PAUSE_SPLIT_MS
        ):
            self._flush_text_locked(event_time_ms)

        if not self._text_buffer:
            self._text_start_time_ms = event_time_ms

        self._text_buffer += char
        self._text_last_time_ms = event_time_ms

    def _flush_text_locked(self, fallback_time_ms: int) -> None:
        if not self._text_buffer:
            return

        action_time_ms = self._text_start_time_ms or fallback_time_ms
        end_time_ms = self._text_last_time_ms or action_time_ms
        text = self._text_buffer

        self._text_buffer = ""
        self._text_start_time_ms = None
        self._text_last_time_ms = None

        self._emit_action_locked(
            action_time_ms,
            {
                "type": "write",
                "text": text,
                "interval": 0,
            },
            output_end_time_ms=end_time_ms,
        )

    def _finalize_open_mouse_buttons_locked(self, event_time_ms: int) -> None:
        for button, state in list(self._mouse_down.items()):
            if not state.emitted_down:
                self._emit_move_locked(state.time_ms, state.x, state.y, force=True)
                self._emit_action_locked(
                    state.time_ms,
                    {
                        "type": "mouse_down",
                        "button": button,
                    },
                )

            self._emit_action_locked(
                event_time_ms,
                {
                    "type": "mouse_up",
                    "button": button,
                },
            )

        self._mouse_down.clear()

    def _save_yaml_locked(self, yaml_text: str) -> Path:
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.recordings_dir / f"recording-{stamp}.yaml"
        path.write_text(yaml_text, encoding="utf-8")

        return path

    def _recording_duration_ms_locked(self) -> int:
        if not self._started_at_ms:
            return 0

        end = self._stopped_at_ms or self._now_ms()
        return max(0, end - self._started_at_ms - max(0, self.start_ignore_ms))

    def _arm_seconds_locked(self) -> int:
        duration_seconds = math.ceil(self._recording_duration_ms_locked() / 1000)
        return max(30, min(120, duration_seconds + 10))

    def _build_yaml_locked(self) -> str:
        actions = [
            action
            for action in self._actions
            if not str(action.get("type", "")).startswith("_")
        ]
        arm_seconds = self._arm_seconds_locked()

        lines: list[str] = []

        lines.append("# Recorded by HA Input Bridge")
        lines.append("# Review before running.")
        lines.append("# Coordinates depend on your Windows display layout.")

        if self.virtual_desktop:
            left = self.virtual_desktop.get("left")
            top = self.virtual_desktop.get("top")
            right = self.virtual_desktop.get("right")
            bottom = self.virtual_desktop.get("bottom")
            width = self.virtual_desktop.get("width")
            height = self.virtual_desktop.get("height")

            lines.append(
                f"# Virtual desktop: left={left} top={top} right={right} bottom={bottom} width={width} height={height}"
            )

        lines.append("")
        lines.append(f"alias: {self._yaml_scalar(self.alias)}")
        lines.append("sequence:")

        lines.extend(
            [
                "  - action: ha_input_bridge.arm",
                "    data:",
                f"      seconds: {arm_seconds}",
            ]
        )

        for action in actions:
            action_type = action.get("type")

            if action_type == "delay":
                lines.extend(
                    [
                        "",
                        "  - delay:",
                        f"      milliseconds: {int(action['milliseconds'])}",
                    ]
                )
                continue

            if action_type == "move":
                lines.extend(
                    [
                        "",
                        "  - action: ha_input_bridge.move",
                        "    data:",
                        f"      x: {int(action['x'])}",
                        f"      y: {int(action['y'])}",
                    ]
                )
                continue

            if action_type == "click":
                lines.extend(
                    [
                        "",
                        "  - action: ha_input_bridge.click",
                        "    data:",
                        f"      button: {action['button']}",
                        f"      clicks: {int(action.get('clicks', 1))}",
                    ]
                )
                continue

            if action_type == "mouse_down":
                lines.extend(
                    [
                        "",
                        "  - action: ha_input_bridge.mouse_down",
                        "    data:",
                        f"      button: {action['button']}",
                    ]
                )
                continue

            if action_type == "mouse_up":
                lines.extend(
                    [
                        "",
                        "  - action: ha_input_bridge.mouse_up",
                        "    data:",
                        f"      button: {action['button']}",
                    ]
                )
                continue

            if action_type == "scroll":
                lines.extend(
                    [
                        "",
                        "  - action: ha_input_bridge.scroll",
                        "    data:",
                        f"      amount: {int(action['amount'])}",
                    ]
                )
                continue

            if action_type == "write":
                lines.extend(
                    [
                        "",
                        "  - action: ha_input_bridge.write",
                        "    data:",
                        f"      text: {self._yaml_scalar(str(action['text']))}",
                        f"      interval: {float(action.get('interval', 0)):g}",
                    ]
                )
                continue

            if action_type == "press":
                lines.extend(
                    [
                        "",
                        "  - action: ha_input_bridge.press",
                        "    data:",
                        f"      key: {action['key']}",
                    ]
                )
                continue

            if action_type == "hotkey":
                lines.extend(
                    [
                        "",
                        "  - action: ha_input_bridge.hotkey",
                        "    data:",
                        "      keys:",
                    ]
                )

                for key in action.get("keys", []):
                    lines.append(f"        - {key}")

                continue

        lines.extend(
            [
                "",
                "  - action: ha_input_bridge.release_all",
                "    data: {}",
                "",
                "mode: single",
                "",
            ]
        )

        return "\n".join(lines)

    def _yaml_scalar(self, value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

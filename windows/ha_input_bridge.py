from __future__ import annotations

import ctypes
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import pyautogui
from flask import Flask, abort, jsonify, request
from waitress import serve
from werkzeug.exceptions import RequestEntityTooLarge

APP_NAME = "ha-input-bridge"

DEFAULT_DATA_DIR = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "HA Input Bridge"
DEFAULT_CONFIG_FILE = DEFAULT_DATA_DIR / "config.json"
DEFAULT_LOG_FILE = DEFAULT_DATA_DIR / "ha_input_bridge.log"

SAFE_MARGIN = 2
MAX_ABSOLUTE_XY = 100000
MAX_RELATIVE_STEP = 1000
MAX_SCROLL_AMOUNT = 2000
MAX_TEXT_LENGTH = 500
MAX_REQUEST_BODY_BYTES = 16 * 1024

LOG_MAX_BYTES = 1 * 1024 * 1024
LOG_BACKUP_COUNT = 3

DEFAULT_CANCEL_ON_MANUAL_MOUSE = True
DEFAULT_MANUAL_MOUSE_CANCEL_THRESHOLD_PX = 8
DEFAULT_MANUAL_MOUSE_GRACE_MS = 250
MIN_MANUAL_MOUSE_CANCEL_THRESHOLD_PX = 2
MAX_MANUAL_MOUSE_CANCEL_THRESHOLD_PX = 250
MIN_MANUAL_MOUSE_GRACE_MS = 0
MAX_MANUAL_MOUSE_GRACE_MS = 3000

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

MOUSE_BUTTONS = {"left", "right", "middle"}

ALLOWED_KEYS = {
    "ctrl",
    "shift",
    "alt",
    "win",
    "enter",
    "esc",
    "tab",
    "space",
    "left",
    "right",
    "up",
    "down",
    "backspace",
    "delete",
    "home",
    "end",
    "pageup",
    "pagedown",
    "a",
    "b",
    "c",
    "d",
    "e",
    "f",
    "g",
    "h",
    "i",
    "j",
    "k",
    "l",
    "m",
    "n",
    "o",
    "p",
    "q",
    "r",
    "s",
    "t",
    "u",
    "v",
    "w",
    "x",
    "y",
    "z",
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BODY_BYTES

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.0


@dataclass
class PlaybackState:
    armed_until: float = 0.0
    playback_active: bool = False
    cancelled: bool = False
    cancel_reason: str = ""
    cancel_on_manual_mouse: bool = DEFAULT_CANCEL_ON_MANUAL_MOUSE
    manual_mouse_cancel_threshold_px: int = DEFAULT_MANUAL_MOUSE_CANCEL_THRESHOLD_PX
    manual_mouse_grace_ms: int = DEFAULT_MANUAL_MOUSE_GRACE_MS
    expected_x: int | None = None
    expected_y: int | None = None
    ignore_manual_mouse_until: float = 0.0
    session_id: int = 0
    last_input_at: float = 0.0
    last_input_type: str = ""
    last_input_action: str = ""


STATE_LOCK = threading.RLock()
PLAYBACK_STATE = PlaybackState()


def set_process_dpi_aware() -> None:
    if os.name != "nt":
        return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


set_process_dpi_aware()


def load_config() -> dict[str, Any]:
    config_path = Path(os.environ.get("HA_INPUT_CONFIG_FILE", str(DEFAULT_CONFIG_FILE)))
    if not config_path.exists():
        return {}

    try:
        with config_path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


CONFIG = load_config()


def config_value(name: str, env_name: str, default: Any = "") -> Any:
    value = CONFIG.get(name)
    if value not in (None, ""):
        return value

    value = os.environ.get(env_name)
    if value not in (None, ""):
        return value

    return default


def config_int(name: str, env_name: str, default: int) -> int:
    value = config_value(name, env_name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def config_bool(name: str, env_name: str, default: bool) -> bool:
    value = config_value(name, env_name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def clamp(value: int | float, low: int | float, high: int | float) -> int | float:
    return max(low, min(high, value))


TOKEN = str(config_value("token", "HA_INPUT_TOKEN", ""))
ALLOWED_CLIENT_IP = str(config_value("allowed_client_ip", "HA_ALLOWED_CLIENT_IP", ""))
BIND_HOST = str(config_value("bind_host", "HA_INPUT_BIND_HOST", "127.0.0.1"))
PORT = config_int("port", "HA_INPUT_PORT", 8765)
LOG_FILE = str(config_value("log_file", "HA_INPUT_LOG_FILE", str(DEFAULT_LOG_FILE)))
CANCEL_ON_MANUAL_MOUSE = config_bool(
    "cancel_on_manual_mouse",
    "HA_INPUT_CANCEL_ON_MANUAL_MOUSE",
    DEFAULT_CANCEL_ON_MANUAL_MOUSE,
)
MANUAL_MOUSE_CANCEL_THRESHOLD_PX = int(
    clamp(
        config_int(
            "manual_mouse_cancel_threshold_px",
            "HA_INPUT_MANUAL_MOUSE_CANCEL_THRESHOLD_PX",
            DEFAULT_MANUAL_MOUSE_CANCEL_THRESHOLD_PX,
        ),
        MIN_MANUAL_MOUSE_CANCEL_THRESHOLD_PX,
        MAX_MANUAL_MOUSE_CANCEL_THRESHOLD_PX,
    )
)
MANUAL_MOUSE_GRACE_MS = int(
    clamp(
        config_int(
            "manual_mouse_grace_ms",
            "HA_INPUT_MANUAL_MOUSE_GRACE_MS",
            DEFAULT_MANUAL_MOUSE_GRACE_MS,
        ),
        MIN_MANUAL_MOUSE_GRACE_MS,
        MAX_MANUAL_MOUSE_GRACE_MS,
    )
)


def setup_logging() -> None:
    log_file = Path(LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root_logger.addHandler(file_handler)


def validate_startup_config() -> None:
    if not TOKEN:
        raise RuntimeError("Missing token. Set config.json token or HA_INPUT_TOKEN.")

    if PORT < 1 or PORT > 65535:
        raise RuntimeError("Invalid port. Use a value between 1 and 65535.")


def virtual_screen_bounds() -> tuple[int, int, int, int]:
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            left = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
            top = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
            width = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
            height = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
            if width > 0 and height > 0:
                return left, top, width, height
        except Exception:
            pass

    width, height = pyautogui.size()
    return 0, 0, int(width), int(height)


def virtual_screen_rect() -> tuple[int, int, int, int, int, int]:
    left, top, width, height = virtual_screen_bounds()
    right = left + width - 1
    bottom = top + height - 1
    return left, top, right, bottom, width, height


def screen_size() -> tuple[int, int]:
    _, _, width, height = virtual_screen_bounds()
    return int(width), int(height)


def clamp_screen_position(x: int | float, y: int | float) -> tuple[int, int]:
    left, top, right, bottom, _, _ = virtual_screen_rect()
    min_x = left + SAFE_MARGIN
    min_y = top + SAFE_MARGIN
    max_x = right - SAFE_MARGIN
    max_y = bottom - SAFE_MARGIN

    if max_x < min_x:
        max_x = min_x
    if max_y < min_y:
        max_y = min_y

    return (
        int(clamp(int(x), min_x, max_x)),
        int(clamp(int(y), min_y, max_y)),
    )


def safe_position() -> tuple[int, int]:
    x, y = pyautogui.position()
    return clamp_screen_position(x, y)


def safe_move_to(x: int | float, y: int | float) -> tuple[int, int]:
    safe_x, safe_y = clamp_screen_position(x, y)
    pyautogui.moveTo(safe_x, safe_y, duration=0)
    return safe_x, safe_y


def safe_move_relative(dx: int | float, dy: int | float) -> tuple[int, int]:
    safe_dx = int(clamp(int(dx), -MAX_RELATIVE_STEP, MAX_RELATIVE_STEP))
    safe_dy = int(clamp(int(dy), -MAX_RELATIVE_STEP, MAX_RELATIVE_STEP))
    current_x, current_y = pyautogui.position()
    target_x = int(current_x) + safe_dx
    target_y = int(current_y) + safe_dy
    return safe_move_to(target_x, target_y)


def validate_mouse_button(button: str) -> str:
    button = str(button).lower().strip()
    if button not in MOUSE_BUTTONS:
        abort(400, "Invalid mouse button")
    return button


def safe_click(
    button: str = "left",
    clicks: int = 1,
    x: int | None = None,
    y: int | None = None,
) -> tuple[int, int]:
    button = validate_mouse_button(button)
    safe_clicks = int(clamp(int(clicks), 1, 3))

    if x is not None and y is not None:
        safe_x, safe_y = safe_move_to(x, y)
        pyautogui.click(x=safe_x, y=safe_y, button=button, clicks=safe_clicks)
        return safe_x, safe_y

    safe_x, safe_y = safe_position()
    pyautogui.moveTo(safe_x, safe_y, duration=0)
    pyautogui.click(button=button, clicks=safe_clicks)
    return safe_x, safe_y


def safe_mouse_down(
    button: str = "left",
    x: int | None = None,
    y: int | None = None,
) -> tuple[int, int]:
    button = validate_mouse_button(button)

    if x is not None and y is not None:
        safe_x, safe_y = safe_move_to(x, y)
        pyautogui.mouseDown(x=safe_x, y=safe_y, button=button)
        return safe_x, safe_y

    safe_x, safe_y = safe_position()
    pyautogui.moveTo(safe_x, safe_y, duration=0)
    pyautogui.mouseDown(button=button)
    return safe_x, safe_y


def safe_mouse_up(
    button: str = "left",
    x: int | None = None,
    y: int | None = None,
) -> tuple[int, int]:
    button = validate_mouse_button(button)

    if x is not None and y is not None:
        safe_x, safe_y = safe_move_to(x, y)
        pyautogui.mouseUp(x=safe_x, y=safe_y, button=button)
        return safe_x, safe_y

    safe_x, safe_y = safe_position()
    pyautogui.moveTo(safe_x, safe_y, duration=0)
    pyautogui.mouseUp(button=button)
    return safe_x, safe_y


def release_all_mouse_buttons() -> None:
    for button in ("left", "right", "middle"):
        try:
            pyautogui.mouseUp(button=button)
        except Exception:
            logging.exception("Failed to release mouse button %s", button)


def safe_scroll(
    amount: int | float,
    x: int | None = None,
    y: int | None = None,
) -> tuple[int, int]:
    safe_amount = int(clamp(int(amount), -MAX_SCROLL_AMOUNT, MAX_SCROLL_AMOUNT))

    if x is not None and y is not None:
        safe_x, safe_y = safe_move_to(x, y)
        pyautogui.scroll(safe_amount, x=safe_x, y=safe_y)
        return safe_x, safe_y

    safe_x, safe_y = safe_position()
    pyautogui.moveTo(safe_x, safe_y, duration=0)
    pyautogui.scroll(safe_amount)
    return safe_x, safe_y


def require_security() -> None:
    if request.headers.get("X-HA-Token") != TOKEN:
        abort(403)

    if ALLOWED_CLIENT_IP:
        remote_ip = request.remote_addr
        if remote_ip != ALLOWED_CLIENT_IP:
            abort(403)


def request_json() -> dict[str, Any]:
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return {}
    return data


def bool_from_request(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def action_requires_armed(kind: Any, action: Any) -> bool:
    if kind == "mouse" and action in ("up", "release_all"):
        return False
    return True


def now_seconds() -> float:
    return time.monotonic()


def manual_mouse_distance(current_x: int, current_y: int, expected_x: int, expected_y: int) -> float:
    dx = current_x - expected_x
    dy = current_y - expected_y
    return (dx * dx + dy * dy) ** 0.5


def playback_state_payload() -> dict[str, Any]:
    current_x, current_y = pyautogui.position()
    left, top, right, bottom, width, height = virtual_screen_rect()

    with STATE_LOCK:
        state = PLAYBACK_STATE
        current_time = now_seconds()
        armed_remaining = max(0.0, state.armed_until - current_time)
        return {
            "ok": True,
            "armed": armed_remaining > 0,
            "armed_remaining_seconds": round(armed_remaining, 3),
            "playback_active": state.playback_active,
            "cancelled": state.cancelled,
            "cancel_reason": state.cancel_reason,
            "cancel_on_manual_mouse": state.cancel_on_manual_mouse,
            "manual_mouse_cancel_threshold_px": state.manual_mouse_cancel_threshold_px,
            "manual_mouse_grace_ms": state.manual_mouse_grace_ms,
            "session_id": state.session_id,
            "expected_x": state.expected_x,
            "expected_y": state.expected_y,
            "x": int(current_x),
            "y": int(current_y),
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "width": width,
            "height": height,
            "safe_margin": SAFE_MARGIN,
            "last_input_type": state.last_input_type,
            "last_input_action": state.last_input_action,
        }


def mark_synthetic_mouse_expected(x: int | None = None, y: int | None = None) -> None:
    if x is None or y is None:
        current_x, current_y = pyautogui.position()
        x = int(current_x)
        y = int(current_y)

    with STATE_LOCK:
        PLAYBACK_STATE.expected_x = int(x)
        PLAYBACK_STATE.expected_y = int(y)
        PLAYBACK_STATE.ignore_manual_mouse_until = now_seconds() + (
            PLAYBACK_STATE.manual_mouse_grace_ms / 1000.0
        )


def cancel_playback_locked(reason: str) -> None:
    PLAYBACK_STATE.cancelled = True
    PLAYBACK_STATE.cancel_reason = reason
    PLAYBACK_STATE.playback_active = False
    PLAYBACK_STATE.armed_until = 0.0


def cancel_playback(reason: str) -> None:
    with STATE_LOCK:
        cancel_playback_locked(reason)

    release_all_mouse_buttons()
    logging.warning("PLAYBACK_CANCELLED reason=%s from=%s", reason, request.remote_addr)


def require_armed_and_not_cancelled(kind: Any, action: Any) -> None:
    if not action_requires_armed(kind, action):
        return

    current_time = now_seconds()
    current_x, current_y = pyautogui.position()

    with STATE_LOCK:
        state = PLAYBACK_STATE

        if state.cancelled:
            abort(409, state.cancel_reason or "playback_cancelled")

        if current_time > state.armed_until:
            state.playback_active = False
            abort(423, "Input bridge is not armed")

        if (
            state.playback_active
            and state.cancel_on_manual_mouse
            and current_time >= state.ignore_manual_mouse_until
            and state.expected_x is not None
            and state.expected_y is not None
        ):
            distance = manual_mouse_distance(
                int(current_x),
                int(current_y),
                int(state.expected_x),
                int(state.expected_y),
            )
            if distance > state.manual_mouse_cancel_threshold_px:
                reason = (
                    "playback_cancelled_manual_mouse "
                    f"distance={distance:.1f} "
                    f"threshold={state.manual_mouse_cancel_threshold_px} "
                    f"expected={state.expected_x},{state.expected_y} "
                    f"actual={int(current_x)},{int(current_y)}"
                )
                cancel_playback_locked(reason)
                release_after_lock = True
            else:
                release_after_lock = False
        else:
            release_after_lock = False

    if release_after_lock:
        release_all_mouse_buttons()
        logging.warning("PLAYBACK_CANCELLED reason=%s from=%s", reason, request.remote_addr)
        abort(409, "playback_cancelled_manual_mouse")


def note_input_success(kind: Any, action: Any) -> None:
    with STATE_LOCK:
        PLAYBACK_STATE.last_input_at = now_seconds()
        PLAYBACK_STATE.last_input_type = str(kind or "")
        PLAYBACK_STATE.last_input_action = str(action or "")


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(409)
@app.errorhandler(423)
def handle_known_error(error: Any):
    return jsonify(ok=False, error=str(error.description)), error.code


@app.errorhandler(RequestEntityTooLarge)
def handle_request_too_large(error: RequestEntityTooLarge):
    return jsonify(ok=False, error="request_too_large"), 413


@app.errorhandler(Exception)
def handle_unexpected_error(error: Exception):
    logging.exception("Unhandled exception")
    return jsonify(ok=False, error="internal_error"), 500


@app.get("/health")
def health():
    require_security()
    left, top, right, bottom, width, height = virtual_screen_rect()
    state = playback_state_payload()
    return jsonify(
        ok=True,
        service=APP_NAME,
        screen={
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "width": width,
            "height": height,
        },
        playback={
            "armed": state["armed"],
            "playback_active": state["playback_active"],
            "cancelled": state["cancelled"],
            "cancel_reason": state["cancel_reason"],
            "cancel_on_manual_mouse": state["cancel_on_manual_mouse"],
        },
    )


@app.get("/position")
def position():
    require_security()
    x, y = pyautogui.position()
    left, top, right, bottom, width, height = virtual_screen_rect()
    return jsonify(
        ok=True,
        x=int(x),
        y=int(y),
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        width=width,
        height=height,
        safe_margin=SAFE_MARGIN,
    )


@app.get("/state")
def state():
    require_security()
    return jsonify(playback_state_payload())


@app.post("/cancel")
def cancel():
    require_security()
    cancel_playback("playback_cancelled_by_request")
    x, y = pyautogui.position()
    return jsonify(ok=True, cancelled=True, x=int(x), y=int(y))


@app.post("/arm")
def arm():
    require_security()
    data = request_json()

    seconds = int(data.get("seconds", 30))
    seconds = int(clamp(seconds, 1, 120))

    cancel_on_manual_mouse = bool_from_request(
        data,
        "cancel_on_manual_mouse",
        CANCEL_ON_MANUAL_MOUSE,
    )
    manual_mouse_cancel_threshold_px = int(
        clamp(
            int(data.get("manual_mouse_cancel_threshold_px", MANUAL_MOUSE_CANCEL_THRESHOLD_PX)),
            MIN_MANUAL_MOUSE_CANCEL_THRESHOLD_PX,
            MAX_MANUAL_MOUSE_CANCEL_THRESHOLD_PX,
        )
    )
    manual_mouse_grace_ms = int(
        clamp(
            int(data.get("manual_mouse_grace_ms", MANUAL_MOUSE_GRACE_MS)),
            MIN_MANUAL_MOUSE_GRACE_MS,
            MAX_MANUAL_MOUSE_GRACE_MS,
        )
    )

    current_x, current_y = pyautogui.position()
    current_time = now_seconds()

    with STATE_LOCK:
        PLAYBACK_STATE.session_id += 1
        PLAYBACK_STATE.armed_until = current_time + seconds
        PLAYBACK_STATE.playback_active = True
        PLAYBACK_STATE.cancelled = False
        PLAYBACK_STATE.cancel_reason = ""
        PLAYBACK_STATE.cancel_on_manual_mouse = cancel_on_manual_mouse
        PLAYBACK_STATE.manual_mouse_cancel_threshold_px = manual_mouse_cancel_threshold_px
        PLAYBACK_STATE.manual_mouse_grace_ms = manual_mouse_grace_ms
        PLAYBACK_STATE.expected_x = int(current_x)
        PLAYBACK_STATE.expected_y = int(current_y)
        PLAYBACK_STATE.ignore_manual_mouse_until = current_time + (manual_mouse_grace_ms / 1000.0)
        PLAYBACK_STATE.last_input_at = 0.0
        PLAYBACK_STATE.last_input_type = ""
        PLAYBACK_STATE.last_input_action = ""
        session_id = PLAYBACK_STATE.session_id

    logging.info(
        "ARM seconds=%s session=%s cancel_on_manual_mouse=%s threshold_px=%s grace_ms=%s from=%s",
        seconds,
        session_id,
        cancel_on_manual_mouse,
        manual_mouse_cancel_threshold_px,
        manual_mouse_grace_ms,
        request.remote_addr,
    )

    return jsonify(
        ok=True,
        armed_for_seconds=seconds,
        session_id=session_id,
        cancel_on_manual_mouse=cancel_on_manual_mouse,
        manual_mouse_cancel_threshold_px=manual_mouse_cancel_threshold_px,
        manual_mouse_grace_ms=manual_mouse_grace_ms,
        x=int(current_x),
        y=int(current_y),
    )


@app.post("/input")
def input_command():
    require_security()
    data = request_json()
    kind = data.get("type")
    action = data.get("action")

    require_armed_and_not_cancelled(kind, action)

    if kind == "mouse" and action in ("move", "move_relative", "scroll"):
        logging.debug(
            "INPUT_FAST from=%s type=%s action=%s",
            request.remote_addr,
            kind,
            action,
        )
    else:
        logging.info(
            "INPUT from=%s type=%s action=%s button=%s key=%s",
            request.remote_addr,
            kind,
            action,
            data.get("button"),
            data.get("key"),
        )

    if kind == "mouse":
        handle_mouse_action(action, data)
    elif kind == "keyboard":
        handle_keyboard_action(action, data)
    else:
        abort(400, "Invalid type")

    note_input_success(kind, action)
    x, y = pyautogui.position()
    mark_synthetic_mouse_expected(int(x), int(y))

    return jsonify(ok=True, x=int(x), y=int(y))


def handle_mouse_action(action: str | None, data: dict[str, Any]) -> None:
    if action == "move":
        x = int(clamp(int(data["x"]), -MAX_ABSOLUTE_XY, MAX_ABSOLUTE_XY))
        y = int(clamp(int(data["y"]), -MAX_ABSOLUTE_XY, MAX_ABSOLUTE_XY))
        safe_x, safe_y = safe_move_to(x, y)
        mark_synthetic_mouse_expected(safe_x, safe_y)
        return

    if action == "move_relative":
        dx = int(data.get("dx", 0))
        dy = int(data.get("dy", 0))
        safe_x, safe_y = safe_move_relative(dx, dy)
        mark_synthetic_mouse_expected(safe_x, safe_y)
        return

    if action == "click":
        button = str(data.get("button", "left"))
        clicks = int(data.get("clicks", 1))
        if "x" in data and "y" in data:
            safe_x, safe_y = safe_click(
                button=button,
                clicks=clicks,
                x=int(data["x"]),
                y=int(data["y"]),
            )
            mark_synthetic_mouse_expected(safe_x, safe_y)
            return

        safe_x, safe_y = safe_click(button=button, clicks=clicks)
        mark_synthetic_mouse_expected(safe_x, safe_y)
        return

    if action == "down":
        button = str(data.get("button", "left"))
        if "x" in data and "y" in data:
            safe_x, safe_y = safe_mouse_down(
                button=button,
                x=int(data["x"]),
                y=int(data["y"]),
            )
            mark_synthetic_mouse_expected(safe_x, safe_y)
            return

        safe_x, safe_y = safe_mouse_down(button=button)
        mark_synthetic_mouse_expected(safe_x, safe_y)
        return

    if action == "up":
        button = str(data.get("button", "left"))
        if "x" in data and "y" in data:
            safe_x, safe_y = safe_mouse_up(
                button=button,
                x=int(data["x"]),
                y=int(data["y"]),
            )
            mark_synthetic_mouse_expected(safe_x, safe_y)
            return

        safe_x, safe_y = safe_mouse_up(button=button)
        mark_synthetic_mouse_expected(safe_x, safe_y)
        return

    if action == "release_all":
        release_all_mouse_buttons()
        mark_synthetic_mouse_expected()
        return

    if action == "scroll":
        amount = int(data.get("amount", 0))
        if "x" in data and "y" in data:
            safe_x, safe_y = safe_scroll(
                amount=amount,
                x=int(data["x"]),
                y=int(data["y"]),
            )
            mark_synthetic_mouse_expected(safe_x, safe_y)
            return

        safe_x, safe_y = safe_scroll(amount=amount)
        mark_synthetic_mouse_expected(safe_x, safe_y)
        return

    abort(400, "Invalid mouse action")


def sanitize_write_text(text: str) -> str:
    sanitized_chars: list[str] = []
    for char in text:
        if char in {"\r", "\n", "\t"}:
            sanitized_chars.append(char)
            continue
        if not char.isprintable():
            continue
        if ord(char) > 0xFFFF:
            continue
        sanitized_chars.append(char)
    return "".join(sanitized_chars)[:MAX_TEXT_LENGTH]


def handle_keyboard_action(action: str | None, data: dict[str, Any]) -> None:
    if action == "write":
        text = sanitize_write_text(str(data.get("text", "")))
        interval = float(data.get("interval", 0))
        interval = float(clamp(interval, 0, 1))
        pyautogui.write(text, interval=interval)
        return

    if action == "press":
        key = str(data["key"]).lower()
        if key not in ALLOWED_KEYS:
            abort(400, "Disallowed key")
        pyautogui.press(key)
        return

    if action == "hotkey":
        keys = data.get("keys", [])
        if not isinstance(keys, list) or not keys:
            abort(400, "keys must be a non-empty list")

        normalized = [str(key).lower() for key in keys]
        if len(normalized) > 8:
            abort(400, "Too many hotkey keys")
        if any(key not in ALLOWED_KEYS for key in normalized):
            abort(400, "Disallowed key")

        pyautogui.hotkey(*normalized)
        return

    abort(400, "Invalid keyboard action")


def main() -> None:
    validate_startup_config()
    setup_logging()
    logging.info(
        "Starting ha-input-bridge on %s:%s cancel_on_manual_mouse=%s threshold_px=%s grace_ms=%s max_scroll=%s",
        BIND_HOST,
        PORT,
        CANCEL_ON_MANUAL_MOUSE,
        MANUAL_MOUSE_CANCEL_THRESHOLD_PX,
        MANUAL_MOUSE_GRACE_MS,
        MAX_SCROLL_AMOUNT,
    )
    serve(app, host=BIND_HOST, port=PORT)


if __name__ == "__main__":
    main()
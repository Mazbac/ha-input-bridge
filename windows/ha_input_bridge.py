from flask import Flask, request, jsonify, abort
from waitress import serve
import os
import time
import logging
import pyautogui

app = Flask(__name__)

TOKEN = os.environ.get("HA_INPUT_TOKEN", "")
ALLOWED_CLIENT_IP = os.environ.get("HA_ALLOWED_CLIENT_IP", "")
BIND_HOST = os.environ.get("HA_INPUT_BIND_HOST", "127.0.0.1")
PORT = int(os.environ.get("HA_INPUT_PORT", "8765"))

if not TOKEN:
    raise RuntimeError("Missing HA_INPUT_TOKEN environment variable")

logging.basicConfig(
    filename=r"C:\ha-input-bridge\ha_input_bridge.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.01

SAFE_MARGIN = 2
MAX_ABSOLUTE_XY = 10000
MAX_RELATIVE_STEP = 300
MAX_SCROLL_AMOUNT = 120
MAX_TEXT_LENGTH = 500

armed_until = 0


def require_security():
    if request.headers.get("X-HA-Token") != TOKEN:
        abort(403)

    if ALLOWED_CLIENT_IP:
        remote_ip = request.remote_addr
        if remote_ip != ALLOWED_CLIENT_IP:
            abort(403)


def require_armed():
    if time.time() > armed_until:
        abort(423, "Input bridge is not armed")


def clamp(value, low, high):
    return max(low, min(high, value))


def screen_size():
    width, height = pyautogui.size()
    return int(width), int(height)


def clamp_screen_position(x, y):
    width, height = screen_size()

    min_x = SAFE_MARGIN
    min_y = SAFE_MARGIN
    max_x = max(SAFE_MARGIN, width - 1 - SAFE_MARGIN)
    max_y = max(SAFE_MARGIN, height - 1 - SAFE_MARGIN)

    return (
        clamp(int(x), min_x, max_x),
        clamp(int(y), min_y, max_y),
    )


def safe_position():
    x, y = pyautogui.position()
    return clamp_screen_position(x, y)


def safe_move_to(x, y):
    x, y = clamp_screen_position(x, y)
    pyautogui.moveTo(x, y, duration=0)
    return x, y


def safe_move_relative(dx, dy):
    dx = clamp(int(dx), -MAX_RELATIVE_STEP, MAX_RELATIVE_STEP)
    dy = clamp(int(dy), -MAX_RELATIVE_STEP, MAX_RELATIVE_STEP)

    current_x, current_y = pyautogui.position()

    target_x = int(current_x) + dx
    target_y = int(current_y) + dy

    return safe_move_to(target_x, target_y)


def safe_click(button="left", clicks=1, x=None, y=None):
    if button not in ("left", "right", "middle"):
        abort(400, "Invalid mouse button")

    clicks = clamp(int(clicks), 1, 3)

    if x is not None and y is not None:
        x, y = safe_move_to(x, y)
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
    else:
        safe_x, safe_y = safe_position()
        pyautogui.moveTo(safe_x, safe_y, duration=0)
        pyautogui.click(button=button, clicks=clicks)


def safe_scroll(amount, x=None, y=None):
    amount = clamp(int(amount), -MAX_SCROLL_AMOUNT, MAX_SCROLL_AMOUNT)

    if x is not None and y is not None:
        x, y = safe_move_to(x, y)
        pyautogui.scroll(amount, x=x, y=y)
    else:
        safe_x, safe_y = safe_position()
        pyautogui.moveTo(safe_x, safe_y, duration=0)
        pyautogui.scroll(amount)


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(423)
def handle_known_error(error):
    return jsonify(ok=False, error=str(error.description)), error.code


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    logging.exception("Unhandled exception")
    return jsonify(ok=False, error="internal_error"), 500


@app.get("/health")
def health():
    require_security()
    return jsonify(ok=True, service="ha-input-bridge")


@app.get("/position")
def position():
    require_security()

    x, y = pyautogui.position()
    width, height = screen_size()

    return jsonify(
        ok=True,
        x=int(x),
        y=int(y),
        width=width,
        height=height,
        safe_margin=SAFE_MARGIN,
    )


@app.post("/arm")
def arm():
    global armed_until

    require_security()

    data = request.get_json(force=True, silent=True) or {}

    seconds = int(data.get("seconds", 30))
    seconds = clamp(seconds, 1, 120)

    armed_until = time.time() + seconds

    logging.info("ARM seconds=%s from=%s", seconds, request.remote_addr)

    return jsonify(ok=True, armed_for_seconds=seconds)


@app.post("/input")
def input_command():
    require_security()
    require_armed()

    data = request.get_json(force=True, silent=True) or {}

    kind = data.get("type")
    action = data.get("action")

    logging.info(
        "INPUT from=%s type=%s action=%s x=%s y=%s dx=%s dy=%s button=%s key=%s",
        request.remote_addr,
        kind,
        action,
        data.get("x"),
        data.get("y"),
        data.get("dx"),
        data.get("dy"),
        data.get("button"),
        data.get("key"),
    )

    if kind == "mouse":
        if action == "move":
            x = clamp(int(data["x"]), 0, MAX_ABSOLUTE_XY)
            y = clamp(int(data["y"]), 0, MAX_ABSOLUTE_XY)
            safe_move_to(x, y)

        elif action == "move_relative":
            dx = int(data.get("dx", 0))
            dy = int(data.get("dy", 0))
            safe_move_relative(dx, dy)

        elif action == "click":
            button = data.get("button", "left")
            clicks = int(data.get("clicks", 1))

            if "x" in data and "y" in data:
                safe_click(
                    button=button,
                    clicks=clicks,
                    x=int(data["x"]),
                    y=int(data["y"]),
                )
            else:
                safe_click(button=button, clicks=clicks)

        elif action == "scroll":
            amount = int(data.get("amount", 0))

            if "x" in data and "y" in data:
                safe_scroll(
                    amount=amount,
                    x=int(data["x"]),
                    y=int(data["y"]),
                )
            else:
                safe_scroll(amount=amount)

        else:
            abort(400, "Invalid mouse action")

    elif kind == "keyboard":
        if action == "write":
            text = str(data.get("text", ""))
            text = text[:MAX_TEXT_LENGTH]

            interval = float(data.get("interval", 0))
            interval = clamp(interval, 0, 1)

            pyautogui.write(text, interval=interval)

        elif action == "press":
            key = str(data["key"]).lower()

            allowed_keys = {
                "ctrl", "shift", "alt", "win",
                "enter", "esc", "tab", "space",
                "left", "right", "up", "down",
                "backspace", "delete",
                "home", "end", "pageup", "pagedown",
                "a", "b", "c", "d", "e", "f", "g",
                "h", "i", "j", "k", "l", "m", "n",
                "o", "p", "q", "r", "s", "t", "u",
                "v", "w", "x", "y", "z",
                "0", "1", "2", "3", "4",
                "5", "6", "7", "8", "9",
            }

            if key not in allowed_keys:
                abort(400, "Disallowed key")

            pyautogui.press(key)

        elif action == "hotkey":
            keys = data.get("keys", [])

            if not isinstance(keys, list) or not keys:
                abort(400, "keys must be a non-empty list")

            allowed_keys = {
                "ctrl", "shift", "alt", "win",
                "enter", "esc", "tab", "space",
                "left", "right", "up", "down",
                "backspace", "delete",
                "home", "end", "pageup", "pagedown",
                "a", "b", "c", "d", "e", "f", "g",
                "h", "i", "j", "k", "l", "m", "n",
                "o", "p", "q", "r", "s", "t", "u",
                "v", "w", "x", "y", "z",
                "0", "1", "2", "3", "4",
                "5", "6", "7", "8", "9",
            }

            normalized = [str(k).lower() for k in keys]

            if len(normalized) > 8:
                abort(400, "Too many hotkey keys")

            if any(k not in allowed_keys for k in normalized):
                abort(400, "Disallowed key")

            pyautogui.hotkey(*normalized)

        else:
            abort(400, "Invalid keyboard action")

    else:
        abort(400, "Invalid type")

    x, y = pyautogui.position()

    return jsonify(
        ok=True,
        x=int(x),
        y=int(y),
    )


if __name__ == "__main__":
    logging.info("Starting ha-input-bridge on %s:%s", BIND_HOST, PORT)
    serve(app, host=BIND_HOST, port=PORT)

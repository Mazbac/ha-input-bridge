from __future__ import annotations

import base64
import ctypes
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Literal

import pystray
from PIL import Image, ImageDraw

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:
    tk = None
    ttk = None
    messagebox = None

try:
    from ha_input_bridge_recorder import HAInputBridgeRecorder, RecordingMode
except Exception:
    HAInputBridgeRecorder = None  # type: ignore[assignment]
    RecordingMode = Literal["mouse", "mouse_keyboard"]  # type: ignore[misc,assignment]


APP_NAME = "HA Input Bridge"
TASK_NAME = "HA Input Bridge"
FIREWALL_RULE_NAME = "HA Input Bridge - Home Assistant only"

DEFAULT_PORT = 8765
DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_FIREWALL_REMOTE_ADDRESS = "LocalSubnet"

DEFAULT_CANCEL_ON_MANUAL_MOUSE = True
DEFAULT_MANUAL_MOUSE_CANCEL_THRESHOLD_PX = 8
DEFAULT_MANUAL_MOUSE_GRACE_MS = 250

STATUS_REFRESH_SECONDS = 5.0
COORDINATE_REFRESH_SECONDS = 2.0
VISIBLE_COORDINATE_REFRESH_MS = 250
RECORDER_COUNTDOWN_SECONDS = 3

MUTEX_PREFIX = "Global\\HAInputBridge"

PROGRAM_DATA = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "HA Input Bridge"
CONFIG_PATH = PROGRAM_DATA / "config.json"
LOG_PATH = PROGRAM_DATA / "ha_input_bridge.log"
TASK_RUNTIME_LOG_PATH = PROGRAM_DATA / "task_runtime.log"
RECORDINGS_DIR = PROGRAM_DATA / "recordings"

INSTALL_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)

AGENT_EXE = INSTALL_DIR / "ha-input-bridge-agent.exe"
TRAY_EXE = INSTALL_DIR / "ha-input-bridge-tray.exe"
CONNECTION_INFO_PATH = INSTALL_DIR / "connection-info.txt"
START_SCRIPT_PATH = INSTALL_DIR / "start_ha_input_bridge.ps1"
UNINSTALL_SCRIPT_PATH = INSTALL_DIR / "uninstall-cleanup.ps1"

STARTUP_SHORTCUT_PATH = (
    Path(os.environ.get("APPDATA", ""))
    / "Microsoft"
    / "Windows"
    / "Start Menu"
    / "Programs"
    / "Startup"
    / "HA Input Bridge Tray.lnk"
)

_status_lock = threading.RLock()
_status_running = False
_status_text = "Status: unknown"
_coordinate_text = "Mouse: unknown"
_last_position: dict[str, Any] = {}
_last_state: dict[str, Any] = {}
_single_instance_mutexes: list[Any] = []


def app_data_dir() -> Path:
    PROGRAM_DATA.mkdir(parents=True, exist_ok=True)
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    return PROGRAM_DATA


def generate_token() -> str:
    token = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    return token.rstrip("=")


def default_config() -> dict[str, Any]:
    return {
        "bind_host": DEFAULT_BIND_HOST,
        "allowed_client_ip": "",
        "firewall_remote_address": DEFAULT_FIREWALL_REMOTE_ADDRESS,
        "port": DEFAULT_PORT,
        "token": generate_token(),
        "log_file": str(LOG_PATH),
        "start_bridge_on_login": True,
        "start_tray_on_login": True,
        "cancel_on_manual_mouse": DEFAULT_CANCEL_ON_MANUAL_MOUSE,
        "manual_mouse_cancel_threshold_px": DEFAULT_MANUAL_MOUSE_CANCEL_THRESHOLD_PX,
        "manual_mouse_grace_ms": DEFAULT_MANUAL_MOUSE_GRACE_MS,
    }


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    result = dict(config)

    result["bind_host"] = (
        str(result.get("bind_host") or DEFAULT_BIND_HOST).strip()
        or DEFAULT_BIND_HOST
    )
    result["allowed_client_ip"] = str(result.get("allowed_client_ip") or "").strip()
    result["firewall_remote_address"] = str(
        result.get("firewall_remote_address")
        or (
            result["allowed_client_ip"]
            if result["allowed_client_ip"]
            else DEFAULT_FIREWALL_REMOTE_ADDRESS
        )
    ).strip()

    result["token"] = str(result.get("token") or "").strip() or generate_token()
    result["log_file"] = str(result.get("log_file") or LOG_PATH)

    try:
        port = int(result.get("port", DEFAULT_PORT))
    except Exception:
        port = DEFAULT_PORT

    if port < 1 or port > 65535:
        port = DEFAULT_PORT

    result["port"] = port

    result["start_bridge_on_login"] = bool(result.get("start_bridge_on_login", True))
    result["start_tray_on_login"] = bool(result.get("start_tray_on_login", True))
    result["cancel_on_manual_mouse"] = bool(
        result.get("cancel_on_manual_mouse", DEFAULT_CANCEL_ON_MANUAL_MOUSE)
    )

    try:
        threshold = int(
            result.get(
                "manual_mouse_cancel_threshold_px",
                DEFAULT_MANUAL_MOUSE_CANCEL_THRESHOLD_PX,
            )
        )
    except Exception:
        threshold = DEFAULT_MANUAL_MOUSE_CANCEL_THRESHOLD_PX

    result["manual_mouse_cancel_threshold_px"] = max(2, min(250, threshold))

    try:
        grace = int(result.get("manual_mouse_grace_ms", DEFAULT_MANUAL_MOUSE_GRACE_MS))
    except Exception:
        grace = DEFAULT_MANUAL_MOUSE_GRACE_MS

    result["manual_mouse_grace_ms"] = max(0, min(3000, grace))

    return result


def load_config() -> dict[str, Any]:
    app_data_dir()

    if not CONFIG_PATH.exists():
        config = default_config()
        save_config(config)
        write_connection_info(config)
        return config

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        data = {}

    if not isinstance(data, dict):
        data = {}

    merged = default_config()
    merged.update(data)

    if not str(merged.get("token", "")).strip():
        merged["token"] = generate_token()

    return normalize_config(merged)


def save_config(config: dict[str, Any]) -> None:
    app_data_dir()
    normalized = normalize_config(config)
    CONFIG_PATH.write_text(json.dumps(normalized, indent=2), encoding="utf-8")


def bridge_local_host(config: dict[str, Any]) -> str:
    bind_host = str(config.get("bind_host", DEFAULT_BIND_HOST)).strip()

    if bind_host in {"", "0.0.0.0", "::"}:
        return "127.0.0.1"

    return bind_host


def bridge_base_url(config: dict[str, Any]) -> str:
    return f"http://{bridge_local_host(config)}:{int(config.get('port', DEFAULT_PORT))}"


def bridge_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    config = load_config()
    url = f"{bridge_base_url(config)}{path}"
    body = None
    headers = {
        "X-HA-Token": str(config.get("token", "")),
    }

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url=url,
        data=body,
        headers=headers,
        method=method.upper(),
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        text = response.read().decode("utf-8", errors="replace")

        if not text:
            return {"ok": True}

        data = json.loads(text)

        if isinstance(data, dict):
            return data

        return {
            "ok": True,
            "data": data,
        }


def get_host_score(ip_address: str) -> int:
    parts = ip_address.split(".")

    if len(parts) < 2:
        return 50

    try:
        first = int(parts[0])
        second = int(parts[1])
    except ValueError:
        return 50

    if first == 192 and second == 168:
        return 10

    if first == 10:
        return 20

    if first == 172 and 16 <= second <= 31:
        return 30

    if first == 100 and 64 <= second <= 127:
        return 40

    return 50


def get_host_candidates() -> list[str]:
    candidates: set[str] = set()

    if os.name == "nt":
        command = (
            "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
            "Where-Object { "
            "$_.IPAddress -notlike '127.*' -and "
            "$_.IPAddress -notlike '169.254.*' -and "
            "$_.IPAddress -ne '0.0.0.0' "
            "} | Select-Object -ExpandProperty IPAddress"
        )

        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            if completed.returncode == 0:
                for line in completed.stdout.splitlines():
                    line = line.strip()

                    if line:
                        candidates.add(line)
        except Exception:
            pass

    try:
        hostname = socket.gethostname()

        for _, _, _, _, sockaddr in socket.getaddrinfo(
            hostname,
            None,
            socket.AF_INET,
        ):
            ip = str(sockaddr[0])

            if not ip.startswith(("127.", "169.254.")) and ip != "0.0.0.0":
                candidates.add(ip)
    except Exception:
        pass

    return sorted(candidates, key=lambda ip: (get_host_score(ip), ip))


def get_recommended_host(config: dict[str, Any] | None = None) -> str:
    candidates = get_host_candidates()

    if candidates:
        return candidates[0]

    if config is None:
        config = load_config()

    bind_host = str(config.get("bind_host", "")).strip()

    if bind_host and bind_host not in {"0.0.0.0", "::"}:
        return bind_host

    return "Use the Windows PC IP address"


def build_setup_info_text(config: dict[str, Any] | None = None) -> str:
    if config is None:
        config = load_config()

    config = normalize_config(config)
    recommended_host = get_recommended_host(config)
    candidates = get_host_candidates()
    other_hosts = [host for host in candidates if host != recommended_host]
    other_text = ", ".join(other_hosts) if other_hosts else "None"

    return (
        "HA Input Bridge setup info\n\n"
        "Use these values in Home Assistant:\n\n"
        f"Host: {recommended_host}\n"
        f"Port: {config.get('port', DEFAULT_PORT)}\n"
        f"Token: {config.get('token', '')}\n\n"
        f"Other host values: {other_text}\n"
        f"Bridge bind address: {config.get('bind_host', DEFAULT_BIND_HOST)}\n"
        f"Firewall remote address: {config.get('firewall_remote_address', DEFAULT_FIREWALL_REMOTE_ADDRESS)}\n\n"
        "Playback safety:\n"
        f"Cancel on manual mouse movement: {bool(config.get('cancel_on_manual_mouse', True))}\n"
        f"Manual mouse cancel threshold px: {config.get('manual_mouse_cancel_threshold_px', DEFAULT_MANUAL_MOUSE_CANCEL_THRESHOLD_PX)}\n"
        f"Manual mouse grace ms: {config.get('manual_mouse_grace_ms', DEFAULT_MANUAL_MOUSE_GRACE_MS)}\n\n"
        "Keep this token private.\n"
    )


def write_connection_info(config: dict[str, Any] | None = None) -> None:
    try:
        CONNECTION_INFO_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONNECTION_INFO_PATH.write_text(
            build_setup_info_text(config),
            encoding="utf-8",
        )
    except Exception:
        pass


def set_clipboard_text(text: str, root: Any | None = None) -> bool:
    if tk is None:
        return False

    owns_root = root is None

    try:
        if root is None:
            root = tk.Tk()
            root.withdraw()

        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        return True
    except Exception:
        return False
    finally:
        if owns_root and root is not None:
            try:
                root.destroy()
            except Exception:
                pass


def open_path(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        if not path.exists() and path.suffix:
            path.write_text("", encoding="utf-8")

        os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass


def open_folder(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass


def open_connection_info() -> None:
    write_connection_info(load_config())
    open_path(CONNECTION_INFO_PATH)


def open_logs_folder() -> None:
    open_folder(PROGRAM_DATA)


def open_recordings_folder() -> None:
    open_folder(RECORDINGS_DIR)


def open_install_folder() -> None:
    open_folder(INSTALL_DIR)


def run_powershell(
    command: str,
    elevated: bool = False,
) -> subprocess.CompletedProcess[str] | None:
    try:
        if elevated:
            script = tempfile.NamedTemporaryFile(
                "w",
                suffix=".ps1",
                delete=False,
                encoding="utf-8",
            )
            script.write(command)
            script.close()

            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    (
                        "Start-Process powershell.exe -Verb RunAs "
                        f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{script.name}\"'"
                    ),
                ],
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            return None

        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception:
        return None


def start_bridge() -> bool:
    completed = run_powershell(f"Start-ScheduledTask -TaskName '{TASK_NAME}'")
    time.sleep(1.0)
    update_status_cache()
    return bool(completed is None or completed.returncode == 0)


def stop_bridge() -> bool:
    completed = run_powershell(
        f"Stop-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue"
    )
    time.sleep(0.5)
    update_status_cache()
    return bool(completed is None or completed.returncode == 0)


def restart_bridge() -> bool:
    stop_bridge()
    return start_bridge()


def apply_system_settings_elevated(config: dict[str, Any]) -> None:
    config = normalize_config(config)

    save_config(config)
    write_connection_info(config)
    create_or_remove_startup_shortcut(
        bool(config.get("start_tray_on_login", True))
    )

    firewall_remote = str(
        config.get("firewall_remote_address") or DEFAULT_FIREWALL_REMOTE_ADDRESS
    ).replace("'", "''")
    port = int(config.get("port", DEFAULT_PORT))
    start_enabled = "$true" if config.get("start_bridge_on_login", True) else "$false"
    start_script = str(START_SCRIPT_PATH).replace("'", "''")
    agent_exe = str(AGENT_EXE).replace("'", "''")
    runtime_log = str(TASK_RUNTIME_LOG_PATH).replace("'", "''")
    config_path = str(CONFIG_PATH).replace("'", "''")

    script = f"""
$ErrorActionPreference = 'Continue'
$TaskName = '{TASK_NAME}'
$FirewallRuleName = '{FIREWALL_RULE_NAME}'
$StartScript = '{start_script}'
$AgentExe = '{agent_exe}'
$RuntimeLog = '{runtime_log}'
$ConfigPath = '{config_path}'
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$StartContent = @"
`$env:HA_INPUT_CONFIG_FILE = '$ConfigPath'
& "$AgentExe" *> "$RuntimeLog"
"@

Set-Content -Path $StartScript -Value $StartContent -Encoding UTF8

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue |
  Remove-NetFirewallRule -ErrorAction SilentlyContinue

New-NetFirewallRule `
  -DisplayName $FirewallRuleName `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort {port} `
  -Action Allow `
  -RemoteAddress '{firewall_remote}' | Out-Null

$Action = New-ScheduledTaskAction `
  -Execute 'powershell.exe' `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal `
  -UserId $CurrentUser `
  -LogonType Interactive `
  -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Principal $Principal `
  -Description 'HA Input Bridge Windows agent' `
  -Force | Out-Null

if ({start_enabled}) {{
  Enable-ScheduledTask -TaskName $TaskName | Out-Null
  Start-ScheduledTask -TaskName $TaskName
}} else {{
  Disable-ScheduledTask -TaskName $TaskName | Out-Null
}}
"""
    run_powershell(script, elevated=True)


def create_or_remove_startup_shortcut(enabled: bool) -> None:
    try:
        STARTUP_SHORTCUT_PATH.parent.mkdir(parents=True, exist_ok=True)

        if not enabled:
            STARTUP_SHORTCUT_PATH.unlink(missing_ok=True)
            return

        target = str(
            TRAY_EXE if getattr(sys, "frozen", False) else Path(sys.executable)
        )
        args = "" if getattr(sys, "frozen", False) else f'"{Path(__file__).resolve()}"'

        command = f"""
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut('{str(STARTUP_SHORTCUT_PATH).replace("'", "''")}')
$Shortcut.TargetPath = '{target.replace("'", "''")}'
$Shortcut.Arguments = '{args.replace("'", "''")}'
$Shortcut.WorkingDirectory = '{str(INSTALL_DIR).replace("'", "''")}'
$Shortcut.Save()
"""
        run_powershell(command)
    except Exception:
        pass


def release_stuck_mouse_buttons() -> bool:
    try:
        bridge_request(
            "POST",
            "/input",
            {
                "type": "mouse",
                "action": "release_all",
            },
            timeout_seconds=2,
        )
        return True
    except Exception:
        return False


def cancel_active_playback() -> bool:
    try:
        bridge_request("POST", "/cancel", None, timeout_seconds=2)
        return True
    except Exception:
        release_stuck_mouse_buttons()
        return False


def get_bridge_state() -> dict[str, Any]:
    try:
        return bridge_request("GET", "/state", None, timeout_seconds=2)
    except Exception:
        return {}


def update_status_cache() -> bool:
    global _status_running, _status_text, _last_state

    try:
        health = bridge_request("GET", "/health", None, timeout_seconds=1.5)
        state = get_bridge_state()
        running = bool(health.get("ok", False))
        playback = state.get("playback_active") if state else False
        cancelled = state.get("cancelled") if state else False

        if running and playback:
            text = "Status: running - playback active"
        elif running and cancelled:
            text = "Status: running - playback cancelled"
        elif running:
            text = "Status: running"
        else:
            text = "Status: stopped"

        with _status_lock:
            _status_running = running
            _status_text = text
            _last_state = state

        return running
    except Exception:
        with _status_lock:
            _status_running = False
            _status_text = "Status: stopped"
            _last_state = {}

        return False


def update_coordinate_cache() -> dict[str, Any]:
    global _coordinate_text, _last_position

    try:
        data = bridge_request("GET", "/position", None, timeout_seconds=1.5)
        x = int(data.get("x", 0))
        y = int(data.get("y", 0))
        text = f"Mouse: x={x}, y={y}"

        with _status_lock:
            _coordinate_text = text
            _last_position = data

        return data
    except Exception:
        with _status_lock:
            _coordinate_text = "Mouse: unavailable"
            _last_position = {}

        return {}


def get_cached_status_text() -> str:
    with _status_lock:
        return _status_text


def get_cached_coordinate_text() -> str:
    with _status_lock:
        return _coordinate_text


def get_cached_status_running() -> bool:
    with _status_lock:
        return _status_running


def format_coordinate_yaml(data: dict[str, Any] | None = None) -> str:
    if data is None:
        data = update_coordinate_cache()

    if not data:
        return ""

    x = int(data.get("x", 0))
    y = int(data.get("y", 0))

    return (
        "- action: ha_input_bridge.arm\n"
        "  data:\n"
        "    seconds: 10\n\n"
        "- action: ha_input_bridge.move\n"
        "  data:\n"
        f"    x: {x}\n"
        f"    y: {y}\n"
    )


def copy_setup_info_from_tray(icon: pystray.Icon | None = None) -> None:
    ok = set_clipboard_text(build_setup_info_text(load_config()))

    if icon:
        icon.notify(
            "Setup info copied." if ok else "Could not copy setup info.",
            APP_NAME,
        )


def copy_mouse_coordinates_from_tray(icon: pystray.Icon | None = None) -> None:
    text = format_coordinate_yaml(update_coordinate_cache())
    ok = bool(text and set_clipboard_text(text))

    if icon:
        icon.notify(
            "Mouse coordinates copied." if ok else "Could not copy coordinates.",
            APP_NAME,
        )


def release_buttons_from_tray(icon: pystray.Icon | None = None) -> None:
    ok = release_stuck_mouse_buttons()

    if icon:
        icon.notify(
            "Mouse buttons released." if ok else "Could not release mouse buttons.",
            APP_NAME,
        )


def cancel_playback_from_tray(icon: pystray.Icon | None = None) -> None:
    ok = cancel_active_playback()
    update_status_cache()

    if icon:
        icon.notify(
            "Playback cancelled."
            if ok
            else "Cancel request failed; release_all attempted.",
            APP_NAME,
        )


def run_async_operation(
    icon: pystray.Icon,
    pending_text: str,
    operation: Any,
    success_text: str,
    failure_text: str,
) -> None:
    def worker() -> None:
        try:
            icon.notify(pending_text, APP_NAME)
            ok = bool(operation())
            icon.notify(success_text if ok else failure_text, APP_NAME)
        except Exception:
            icon.notify(failure_text, APP_NAME)
        finally:
            update_status_cache()
            update_coordinate_cache()

            try:
                icon.update_menu()
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()


def create_icon_image(running: bool) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    fill = (40, 160, 80, 255) if running else (160, 70, 70, 255)

    draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill=fill)
    draw.rectangle((19, 20, 45, 27), fill=(255, 255, 255, 255))
    draw.rectangle((19, 36, 45, 43), fill=(255, 255, 255, 255))
    draw.rectangle((29, 18, 35, 45), fill=(255, 255, 255, 255))

    return image


def status_monitor(icon: pystray.Icon) -> None:
    last_running: bool | None = None

    while True:
        running = update_status_cache()

        if running != last_running:
            icon.icon = create_icon_image(running)
            icon.title = f"{APP_NAME} - {'running' if running else 'stopped'}"
            last_running = running

        try:
            icon.update_menu()
        except Exception:
            pass

        time.sleep(STATUS_REFRESH_SECONDS)


def coordinate_monitor(icon: pystray.Icon) -> None:
    while True:
        update_coordinate_cache()

        try:
            icon.update_menu()
        except Exception:
            pass

        time.sleep(COORDINATE_REFRESH_SECONDS)


def acquire_mutex(name: str) -> bool:
    if os.name != "nt":
        return True

    try:
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, name)
        last_error = kernel32.GetLastError()

        if last_error == 183:
            return False

        _single_instance_mutexes.append(mutex)
        return True
    except Exception:
        return True


def acquire_single_instance_lock() -> bool:
    return acquire_mutex(f"{MUTEX_PREFIX}Tray")


def acquire_settings_instance_lock() -> bool:
    return acquire_mutex(f"{MUTEX_PREFIX}Settings")


def acquire_coords_instance_lock() -> bool:
    return acquire_mutex(f"{MUTEX_PREFIX}Coords")


def acquire_recorder_instance_lock() -> bool:
    return acquire_mutex(f"{MUTEX_PREFIX}Recorder")


def launch_self(*args: str) -> None:
    try:
        if getattr(sys, "frozen", False):
            subprocess.Popen([str(TRAY_EXE), *args], close_fds=True)
        else:
            subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), *args],
                close_fds=True,
            )
    except Exception:
        pass


def launch_settings_window() -> None:
    launch_self("--settings")


def launch_coordinates_window() -> None:
    launch_self("--coords")


def launch_recorder_window(mode: RecordingMode) -> None:
    launch_self("--recorder", str(mode))


def open_coordinates_window() -> None:
    if tk is None or ttk is None:
        return

    root = tk.Tk()
    root.title("HA Input Bridge - Mouse Coordinates")
    root.resizable(False, False)

    try:
        root.attributes("-topmost", True)
    except Exception:
        pass

    main = ttk.Frame(root, padding=16)
    main.grid(row=0, column=0, sticky="nsew")

    coords_var = tk.StringVar(value="Mouse: loading...")
    bounds_var = tk.StringVar(value="")
    copy_var = tk.StringVar(value="")

    ttk.Label(
        main,
        text="Mouse coordinates",
        font=("Segoe UI", 12, "bold"),
    ).grid(row=0, column=0, columnspan=3, sticky="w")

    ttk.Label(
        main,
        textvariable=coords_var,
        font=("Segoe UI", 18, "bold"),
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))

    ttk.Label(main, textvariable=bounds_var).grid(
        row=2,
        column=0,
        columnspan=3,
        sticky="w",
        pady=(4, 0),
    )

    ttk.Label(main, textvariable=copy_var).grid(
        row=3,
        column=0,
        columnspan=3,
        sticky="w",
        pady=(8, 0),
    )

    def refresh() -> None:
        data = update_coordinate_cache()

        if data:
            coords_var.set(f"x={int(data.get('x', 0))}, y={int(data.get('y', 0))}")
            bounds_var.set(
                "desktop="
                f"{data.get('left')},{data.get('top')} -> "
                f"{data.get('right')},{data.get('bottom')} "
                f"({data.get('width')}x{data.get('height')})"
            )
        else:
            coords_var.set("unavailable")
            bounds_var.set("Check that the bridge is running.")

        root.after(VISIBLE_COORDINATE_REFRESH_MS, refresh)

    def copy_xy() -> None:
        data = update_coordinate_cache()

        if data and set_clipboard_text(
            f"x: {int(data.get('x', 0))}\ny: {int(data.get('y', 0))}",
            root,
        ):
            copy_var.set("Copied x/y.")
        else:
            copy_var.set("Could not copy x/y.")

    def copy_ha_move() -> None:
        text = format_coordinate_yaml(update_coordinate_cache())

        if text and set_clipboard_text(text, root):
            copy_var.set("Copied HA move action.")
        else:
            copy_var.set("Could not copy HA action.")

    def copy_details() -> None:
        data = update_coordinate_cache()

        if data and set_clipboard_text(json.dumps(data, indent=2), root):
            copy_var.set("Copied details.")
        else:
            copy_var.set("Could not copy details.")

    buttons = ttk.Frame(main)
    buttons.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))

    ttk.Button(buttons, text="Copy x/y", command=copy_xy).grid(
        row=0,
        column=0,
        padx=(0, 8),
    )
    ttk.Button(buttons, text="Copy HA move action", command=copy_ha_move).grid(
        row=0,
        column=1,
        padx=(0, 8),
    )
    ttk.Button(buttons, text="Copy details", command=copy_details).grid(
        row=0,
        column=2,
    )
    ttk.Button(main, text="Close", command=root.destroy).grid(
        row=5,
        column=0,
        sticky="w",
        pady=(12, 0),
    )

    refresh()
    root.mainloop()


def open_recorder_window(mode: RecordingMode) -> None:
    if tk is None or ttk is None or messagebox is None:
        return

    if HAInputBridgeRecorder is None:
        messagebox.showerror(
            APP_NAME,
            "Recorder dependency is missing. Rebuild the installer with pynput bundled.",
        )
        return

    if mode == "mouse_keyboard":
        accepted = messagebox.askokcancel(
            APP_NAME,
            "Mouse + keyboard recording can capture sensitive text.\n\n"
            "Do not record passwords, tokens, private messages, payment details, or other sensitive data.",
        )

        if not accepted:
            return

    root = tk.Tk()
    root.title("HA Input Bridge - Recorder")
    root.geometry("780x560")
    root.minsize(720, 500)

    try:
        root.attributes("-topmost", True)
    except Exception:
        pass

    main = ttk.Frame(root, padding=14)
    main.grid(row=0, column=0, sticky="nsew")

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    main.columnconfigure(0, weight=1)
    main.rowconfigure(5, weight=1)

    title = "Mouse recorder" if mode == "mouse" else "Mouse + keyboard recorder"
    status_var = tk.StringVar(value="Preparing...")
    info_var = tk.StringVar(value="Move away from this window before the countdown ends.")
    last_file_var = tk.StringVar(value="")
    clipboard_var = tk.StringVar(value="")

    ttk.Label(
        main,
        text=title,
        font=("Segoe UI", 13, "bold"),
    ).grid(row=0, column=0, sticky="w")

    ttk.Label(main, textvariable=status_var).grid(
        row=1,
        column=0,
        sticky="w",
        pady=(8, 0),
    )
    ttk.Label(main, textvariable=info_var, wraplength=720).grid(
        row=2,
        column=0,
        sticky="w",
        pady=(4, 0),
    )
    ttk.Label(main, textvariable=last_file_var, wraplength=720).grid(
        row=3,
        column=0,
        sticky="w",
        pady=(8, 0),
    )
    ttk.Label(main, textvariable=clipboard_var).grid(
        row=4,
        column=0,
        sticky="w",
        pady=(4, 0),
    )

    preview = tk.Text(main, height=18, wrap="none")
    preview.grid(row=5, column=0, sticky="nsew", pady=(8, 0))
    preview.configure(state="disabled")

    scrollbar_y = ttk.Scrollbar(main, orient="vertical", command=preview.yview)
    scrollbar_y.grid(row=5, column=1, sticky="ns", pady=(8, 0))
    preview.configure(yscrollcommand=scrollbar_y.set)

    try:
        virtual_desktop = bridge_request(
            "GET",
            "/position",
            None,
            timeout_seconds=1.5,
        )
    except Exception:
        virtual_desktop = {}

    recorder = HAInputBridgeRecorder(
        recordings_dir=RECORDINGS_DIR,
        mode=mode,
        virtual_desktop=virtual_desktop,
    )

    latest_yaml = ""
    latest_path: Path | None = None
    recording_finished = False

    def set_preview(text: str) -> None:
        preview.configure(state="normal")
        preview.delete("1.0", "end")
        preview.insert("1.0", text)
        preview.configure(state="disabled")

    def root_rect() -> tuple[int, int, int, int]:
        root.update_idletasks()
        left = root.winfo_rootx()
        top = root.winfo_rooty()
        return (
            left,
            top,
            left + root.winfo_width(),
            top + root.winfo_height(),
        )

    def update_status() -> None:
        if recording_finished:
            return

        try:
            recorder.set_ignore_rects([root_rect()])
            status = recorder.get_status()

            if status.get("recording"):
                duration = int(status.get("duration_ms", 0) / 1000)
                action_count = status.get("action_count", 0)
                pending_scroll = status.get("pending_scroll_amount", 0)
                skipped_chars = status.get("skipped_text_char_count", 0)

                status_var.set(
                    f"Recording... {duration}s, "
                    f"actions={action_count}, "
                    f"pending_scroll={pending_scroll}, "
                    f"skipped_chars={skipped_chars}"
                )
        except Exception:
            pass

        root.after(500, update_status)

    def start_recording_now() -> None:
        try:
            recorder.set_ignore_rects([root_rect()])
            recorder.start()
            status_var.set("Recording. Use Stop & Copy YAML when finished.")
            info_var.set(
                "Recorder window clicks are ignored. Generated YAML includes release_all at the end."
            )
            update_status()
        except Exception as err:
            status_var.set(f"Could not start recorder: {err}")

    def countdown(remaining: int) -> None:
        if recording_finished:
            return

        if remaining <= 0:
            start_recording_now()
            return

        status_var.set(f"Starting in {remaining}...")
        root.after(1000, lambda: countdown(remaining - 1))

    def stop_and_copy() -> None:
        nonlocal recording_finished, latest_yaml, latest_path

        if recording_finished:
            return

        try:
            latest_yaml, latest_path = recorder.stop_and_save()
        except Exception as err:
            status_var.set(f"Could not stop recorder: {err}")
            return

        recording_finished = True
        status_var.set("Recording stopped.")
        last_file_var.set(f"Saved: {latest_path}")
        set_preview(latest_yaml)

        if set_clipboard_text(latest_yaml, root):
            clipboard_var.set("YAML copied to clipboard.")
        else:
            clipboard_var.set("Could not copy YAML to clipboard.")

    def stop_and_open() -> None:
        stop_and_copy()

        if latest_path and latest_path.exists():
            os.startfile(str(latest_path))  # type: ignore[attr-defined]

    def copy_yaml_again() -> None:
        if not latest_yaml:
            clipboard_var.set("No YAML available yet.")
            return

        if set_clipboard_text(latest_yaml, root):
            clipboard_var.set("YAML copied to clipboard.")
        else:
            clipboard_var.set("Could not copy YAML.")

    def cancel_recording() -> None:
        nonlocal recording_finished

        try:
            if recorder.is_recording:
                recorder.stop_without_saving()
        except Exception:
            pass

        recording_finished = True
        root.destroy()

    buttons = ttk.Frame(main)
    buttons.grid(row=6, column=0, sticky="ew", pady=(12, 0))

    ttk.Button(buttons, text="Stop & Copy YAML", command=stop_and_copy).grid(
        row=0,
        column=0,
        padx=(0, 8),
    )
    ttk.Button(buttons, text="Stop & Open YAML", command=stop_and_open).grid(
        row=0,
        column=1,
        padx=(0, 8),
    )
    ttk.Button(buttons, text="Copy YAML again", command=copy_yaml_again).grid(
        row=0,
        column=2,
        padx=(0, 8),
    )
    ttk.Button(buttons, text="Open recordings folder", command=open_recordings_folder).grid(
        row=0,
        column=3,
        padx=(0, 8),
    )
    ttk.Button(buttons, text="Cancel", command=cancel_recording).grid(
        row=0,
        column=4,
    )

    root.protocol("WM_DELETE_WINDOW", cancel_recording)
    countdown(RECORDER_COUNTDOWN_SECONDS)
    root.mainloop()


def open_settings_window() -> None:
    if tk is None or ttk is None or messagebox is None:
        return

    config = load_config()

    root = tk.Tk()
    root.title("HA Input Bridge Control Center")
    root.geometry("760x540")
    root.minsize(720, 500)

    main = ttk.Frame(root, padding=14)
    main.grid(row=0, column=0, sticky="nsew")

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    main.columnconfigure(0, weight=1)
    main.rowconfigure(0, weight=1)

    status_var = tk.StringVar(value=get_cached_status_text())
    coords_var = tk.StringVar(value=get_cached_coordinate_text())
    state_var = tk.StringVar(value="Playback: unknown")

    token_var = tk.StringVar(value=str(config.get("token", "")))
    token_visible_var = tk.BooleanVar(value=False)

    bridge_login_var = tk.BooleanVar(
        value=bool(config.get("start_bridge_on_login", True))
    )
    tray_login_var = tk.BooleanVar(
        value=bool(config.get("start_tray_on_login", True))
    )
    cancel_mouse_var = tk.BooleanVar(
        value=bool(config.get("cancel_on_manual_mouse", True))
    )

    threshold_var = tk.StringVar(
        value=str(
            config.get(
                "manual_mouse_cancel_threshold_px",
                DEFAULT_MANUAL_MOUSE_CANCEL_THRESHOLD_PX,
            )
        )
    )
    grace_var = tk.StringVar(
        value=str(
            config.get(
                "manual_mouse_grace_ms",
                DEFAULT_MANUAL_MOUSE_GRACE_MS,
            )
        )
    )

    bind_host_var = tk.StringVar(value=str(config.get("bind_host", DEFAULT_BIND_HOST)))
    allowed_ip_var = tk.StringVar(value=str(config.get("allowed_client_ip", "")))
    firewall_remote_var = tk.StringVar(
        value=str(
            config.get(
                "firewall_remote_address",
                DEFAULT_FIREWALL_REMOTE_ADDRESS,
            )
        )
    )
    port_var = tk.StringVar(value=str(config.get("port", DEFAULT_PORT)))

    notebook = ttk.Notebook(main)
    notebook.grid(row=0, column=0, sticky="nsew")

    overview = ttk.Frame(notebook, padding=12)
    setup = ttk.Frame(notebook, padding=12)
    safety = ttk.Frame(notebook, padding=12)
    recorder_tab = ttk.Frame(notebook, padding=12)
    diagnostics = ttk.Frame(notebook, padding=12)
    advanced = ttk.Frame(notebook, padding=12)

    for frame in (
        overview,
        setup,
        safety,
        recorder_tab,
        diagnostics,
        advanced,
    ):
        frame.columnconfigure(1, weight=1)

    notebook.add(overview, text="Overview")
    notebook.add(setup, text="Setup")
    notebook.add(safety, text="Playback Safety")
    notebook.add(recorder_tab, text="Recorder")
    notebook.add(diagnostics, text="Diagnostics")
    notebook.add(advanced, text="Advanced")

    recommended_host = get_recommended_host(config)
    all_hosts = get_host_candidates()
    other_hosts = [host for host in all_hosts if host != recommended_host]
    other_hosts_text = ", ".join(other_hosts) if other_hosts else "None"

    ttk.Label(
        overview,
        text="HA Input Bridge",
        font=("Segoe UI", 14, "bold"),
    ).grid(row=0, column=0, columnspan=3, sticky="w")

    ttk.Label(overview, textvariable=status_var).grid(
        row=1,
        column=0,
        columnspan=3,
        sticky="w",
        pady=(12, 0),
    )
    ttk.Label(overview, textvariable=coords_var).grid(
        row=2,
        column=0,
        columnspan=3,
        sticky="w",
        pady=(4, 0),
    )
    ttk.Label(overview, textvariable=state_var).grid(
        row=3,
        column=0,
        columnspan=3,
        sticky="w",
        pady=(4, 0),
    )
    ttk.Label(
        overview,
        text=f"Windows bridge host: {recommended_host}",
    ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 0))
    ttk.Label(
        overview,
        text=f"Other host values: {other_hosts_text}",
        wraplength=650,
    ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
    ttk.Label(
        overview,
        text=f"Port: {config.get('port', DEFAULT_PORT)}",
    ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 0))

    ttk.Label(setup, text="Token:").grid(row=0, column=0, sticky="w")

    token_entry = ttk.Entry(
        setup,
        textvariable=token_var,
        show="•",
        width=52,
    )
    token_entry.grid(row=0, column=1, sticky="ew", padx=(12, 0))

    def toggle_token_visibility() -> None:
        if token_visible_var.get():
            token_entry.configure(show="•")
            token_visible_var.set(False)
            token_toggle.configure(text="Show")
        else:
            token_entry.configure(show="")
            token_visible_var.set(True)
            token_toggle.configure(text="Hide")

    token_toggle = ttk.Button(
        setup,
        text="Show",
        width=8,
        command=toggle_token_visibility,
    )
    token_toggle.grid(row=0, column=2, padx=(8, 0))

    ttk.Checkbutton(
        setup,
        text="Start bridge on Windows login",
        variable=bridge_login_var,
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(14, 0))

    ttk.Checkbutton(
        setup,
        text="Start tray icon on Windows login",
        variable=tray_login_var,
    ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

    ttk.Checkbutton(
        safety,
        text="Cancel playback when the Windows user physically moves the mouse",
        variable=cancel_mouse_var,
    ).grid(row=0, column=0, columnspan=3, sticky="w")

    ttk.Label(safety, text="Manual mouse threshold:").grid(
        row=1,
        column=0,
        sticky="w",
        pady=(12, 0),
    )
    ttk.Entry(safety, textvariable=threshold_var, width=12).grid(
        row=1,
        column=1,
        sticky="w",
        padx=(12, 0),
        pady=(12, 0),
    )
    ttk.Label(safety, text="px").grid(
        row=1,
        column=2,
        sticky="w",
        padx=(6, 0),
        pady=(12, 0),
    )

    ttk.Label(safety, text="Grace period after synthetic movement:").grid(
        row=2,
        column=0,
        sticky="w",
        pady=(8, 0),
    )
    ttk.Entry(safety, textvariable=grace_var, width=12).grid(
        row=2,
        column=1,
        sticky="w",
        padx=(12, 0),
        pady=(8, 0),
    )
    ttk.Label(safety, text="ms").grid(
        row=2,
        column=2,
        sticky="w",
        padx=(6, 0),
        pady=(8, 0),
    )

    ttk.Label(
        safety,
        text=(
            "Lower threshold cancels faster. Higher threshold avoids false cancels "
            "on unstable mice or touchpads."
        ),
        wraplength=640,
    ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(14, 0))

    ttk.Label(
        recorder_tab,
        text="Recorder",
        font=("Segoe UI", 12, "bold"),
    ).grid(row=0, column=0, columnspan=3, sticky="w")

    ttk.Label(
        recorder_tab,
        text=(
            "Mouse-only recording is safer. Mouse + keyboard recording is opt-in "
            "because it can capture private text."
        ),
        wraplength=640,
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

    ttk.Button(
        recorder_tab,
        text="Start mouse recording",
        command=lambda: launch_recorder_window("mouse"),
    ).grid(row=2, column=0, sticky="w", pady=(12, 0))

    ttk.Button(
        recorder_tab,
        text="Start mouse + keyboard recording",
        command=lambda: launch_recorder_window("mouse_keyboard"),
    ).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(12, 0))

    ttk.Button(
        recorder_tab,
        text="Open recordings folder",
        command=open_recordings_folder,
    ).grid(row=2, column=2, sticky="w", padx=(8, 0), pady=(12, 0))

    ttk.Button(
        diagnostics,
        text="Refresh status",
        command=lambda: refresh_settings_status(),
    ).grid(row=0, column=0, sticky="w")

    ttk.Button(
        diagnostics,
        text="Show mouse coordinates",
        command=launch_coordinates_window,
    ).grid(row=0, column=1, sticky="w", padx=(8, 0))

    ttk.Button(
        diagnostics,
        text="Copy mouse coordinates",
        command=lambda: copy_mouse_coordinates(),
    ).grid(row=0, column=2, sticky="w", padx=(8, 0))

    ttk.Button(
        diagnostics,
        text="Cancel active playback",
        command=lambda: cancel_playback_ui(),
    ).grid(row=1, column=0, sticky="w", pady=(8, 0))

    ttk.Button(
        diagnostics,
        text="Release mouse buttons",
        command=lambda: release_mouse_buttons(),
    ).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

    ttk.Button(
        diagnostics,
        text="Open logs",
        command=open_logs_folder,
    ).grid(row=2, column=0, sticky="w", pady=(8, 0))

    ttk.Button(
        diagnostics,
        text="Open connection info",
        command=open_connection_info,
    ).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

    ttk.Button(
        diagnostics,
        text="Open install folder",
        command=open_install_folder,
    ).grid(row=2, column=2, sticky="w", padx=(8, 0), pady=(8, 0))

    ttk.Label(advanced, text="Bind address:").grid(
        row=0,
        column=0,
        sticky="w",
    )
    ttk.Entry(advanced, textvariable=bind_host_var, width=48).grid(
        row=0,
        column=1,
        sticky="ew",
        padx=(12, 0),
    )

    ttk.Label(advanced, text="Allowed Home Assistant IP:").grid(
        row=1,
        column=0,
        sticky="w",
        pady=(8, 0),
    )
    ttk.Entry(advanced, textvariable=allowed_ip_var, width=48).grid(
        row=1,
        column=1,
        sticky="ew",
        padx=(12, 0),
        pady=(8, 0),
    )

    ttk.Label(advanced, text="Firewall remote address:").grid(
        row=2,
        column=0,
        sticky="w",
        pady=(8, 0),
    )
    ttk.Entry(advanced, textvariable=firewall_remote_var, width=48).grid(
        row=2,
        column=1,
        sticky="ew",
        padx=(12, 0),
        pady=(8, 0),
    )

    ttk.Label(advanced, text="Bridge port:").grid(
        row=3,
        column=0,
        sticky="w",
        pady=(8, 0),
    )
    ttk.Entry(advanced, textvariable=port_var, width=48).grid(
        row=3,
        column=1,
        sticky="ew",
        padx=(12, 0),
        pady=(8, 0),
    )

    ttk.Label(
        advanced,
        text=(
            "Use 0.0.0.0 to listen on all adapters. Leave Allowed Home Assistant IP "
            "empty for local subnet firewall scope."
        ),
        wraplength=640,
    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def refresh_settings_status() -> None:
        update_status_cache()
        update_coordinate_cache()
        state = get_bridge_state()

        status_var.set(get_cached_status_text())
        coords_var.set(get_cached_coordinate_text())

        if state:
            state_var.set(
                f"Playback: active={bool(state.get('playback_active'))}, "
                f"armed={bool(state.get('armed'))}, "
                f"cancelled={bool(state.get('cancelled'))}"
            )
        else:
            state_var.set("Playback: unavailable")

    def validate_form() -> dict[str, Any] | None:
        try:
            port = int(port_var.get().strip())
            threshold = int(threshold_var.get().strip())
            grace = int(grace_var.get().strip())
        except ValueError:
            messagebox.showerror(
                APP_NAME,
                "Port, threshold, and grace period must be numeric.",
            )
            return None

        if port < 1 or port > 65535:
            messagebox.showerror(
                APP_NAME,
                "Enter a bridge port between 1 and 65535.",
            )
            return None

        if threshold < 2 or threshold > 250:
            messagebox.showerror(
                APP_NAME,
                "Enter a manual mouse threshold between 2 and 250 px.",
            )
            return None

        if grace < 0 or grace > 3000:
            messagebox.showerror(
                APP_NAME,
                "Enter a grace period between 0 and 3000 ms.",
            )
            return None

        token = token_var.get().strip()

        if not token:
            messagebox.showerror(APP_NAME, "Token cannot be empty.")
            return None

        allowed_ip = allowed_ip_var.get().strip()
        firewall_remote = firewall_remote_var.get().strip() or (
            allowed_ip if allowed_ip else DEFAULT_FIREWALL_REMOTE_ADDRESS
        )

        return normalize_config(
            {
                "bind_host": bind_host_var.get().strip() or DEFAULT_BIND_HOST,
                "allowed_client_ip": allowed_ip,
                "firewall_remote_address": firewall_remote,
                "port": port,
                "token": token,
                "log_file": str(LOG_PATH),
                "start_bridge_on_login": bool(bridge_login_var.get()),
                "start_tray_on_login": bool(tray_login_var.get()),
                "cancel_on_manual_mouse": bool(cancel_mouse_var.get()),
                "manual_mouse_cancel_threshold_px": threshold,
                "manual_mouse_grace_ms": grace,
            }
        )

    def save_only() -> None:
        new_config = validate_form()

        if new_config is None:
            return

        save_config(new_config)
        write_connection_info(new_config)

        messagebox.showinfo(
            APP_NAME,
            "Settings saved. Restart the bridge to apply runtime settings.",
        )

    def save_and_restart() -> None:
        new_config = validate_form()

        if new_config is None:
            return

        save_config(new_config)
        write_connection_info(new_config)
        create_or_remove_startup_shortcut(
            bool(new_config.get("start_tray_on_login", True))
        )

        messagebox.showinfo(
            APP_NAME,
            "Windows may ask for administrator permission to apply firewall and startup changes.",
        )

        apply_system_settings_elevated(new_config)
        root.after(2500, refresh_settings_status)

    def regenerate_token() -> None:
        token_var.set(generate_token())

    def copy_info() -> None:
        new_config = validate_form()

        if new_config is None:
            return

        save_config(new_config)
        write_connection_info(new_config)

        if set_clipboard_text(build_setup_info_text(new_config), root):
            messagebox.showinfo(APP_NAME, "Connection info copied to clipboard.")
        else:
            messagebox.showerror(
                APP_NAME,
                "Could not copy connection info. Use Open connection info instead.",
            )

    def copy_mouse_coordinates() -> None:
        text = format_coordinate_yaml(update_coordinate_cache())

        if text and set_clipboard_text(text, root):
            messagebox.showinfo(APP_NAME, "Mouse coordinates copied to clipboard.")
        else:
            messagebox.showerror(
                APP_NAME,
                "Could not copy mouse coordinates. Check that the bridge is running.",
            )

    def release_mouse_buttons() -> None:
        ok = release_stuck_mouse_buttons()

        messagebox.showinfo(
            APP_NAME,
            "Mouse buttons released."
            if ok
            else "Could not release mouse buttons. Check that the bridge is running.",
        )

    def cancel_playback_ui() -> None:
        ok = cancel_active_playback()
        refresh_settings_status()

        messagebox.showinfo(
            APP_NAME,
            "Playback cancelled."
            if ok
            else "Cancel request failed. release_all was attempted.",
        )

    buttons = ttk.Frame(main)
    buttons.grid(row=1, column=0, sticky="ew", pady=(12, 0))

    ttk.Button(buttons, text="Save", command=save_only).grid(
        row=0,
        column=0,
        padx=(0, 8),
    )
    ttk.Button(buttons, text="Save & Restart Bridge", command=save_and_restart).grid(
        row=0,
        column=1,
        padx=(0, 8),
    )
    ttk.Button(buttons, text="Regenerate Token", command=regenerate_token).grid(
        row=0,
        column=2,
        padx=(0, 8),
    )
    ttk.Button(buttons, text="Copy Setup Info", command=copy_info).grid(
        row=0,
        column=3,
        padx=(0, 8),
    )
    ttk.Button(buttons, text="Close", command=root.destroy).grid(
        row=0,
        column=4,
    )

    refresh_settings_status()
    root.mainloop()


def run_uninstaller(icon: pystray.Icon) -> None:
    def worker() -> None:
        try:
            if UNINSTALL_SCRIPT_PATH.exists():
                script = str(UNINSTALL_SCRIPT_PATH).replace("'", "''")
                run_powershell(f"& '{script}'", elevated=True)
            else:
                run_powershell(
                    f"Stop-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue; "
                    f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue; "
                    f"Get-NetFirewallRule -DisplayName '{FIREWALL_RULE_NAME}' -ErrorAction SilentlyContinue | "
                    "Remove-NetFirewallRule -ErrorAction SilentlyContinue",
                    elevated=True,
                )

            icon.notify("Uninstall cleanup started.", APP_NAME)
        except Exception:
            icon.notify("Could not start uninstall cleanup.", APP_NAME)

    threading.Thread(target=worker, daemon=True).start()


def on_start(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    run_async_operation(
        icon,
        "Starting bridge...",
        start_bridge,
        "Bridge started.",
        "Bridge could not be started.",
    )


def on_stop(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    run_async_operation(
        icon,
        "Stopping bridge...",
        stop_bridge,
        "Bridge stopped.",
        "Bridge could not be stopped.",
    )


def on_restart(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    run_async_operation(
        icon,
        "Restarting bridge...",
        restart_bridge,
        "Bridge restarted.",
        "Bridge could not be restarted.",
    )


def on_settings(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    launch_settings_window()


def on_show_coordinates(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    launch_coordinates_window()


def on_start_recording_mouse(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    launch_recorder_window("mouse")


def on_start_recording_mouse_keyboard(
    icon: pystray.Icon,
    item: pystray.MenuItem,
) -> None:
    launch_recorder_window("mouse_keyboard")


def on_open_recordings(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    open_recordings_folder()


def on_copy_setup_info(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    threading.Thread(
        target=copy_setup_info_from_tray,
        args=(icon,),
        daemon=True,
    ).start()


def on_copy_mouse_coordinates(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    threading.Thread(
        target=copy_mouse_coordinates_from_tray,
        args=(icon,),
        daemon=True,
    ).start()


def on_release_buttons(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    threading.Thread(
        target=release_buttons_from_tray,
        args=(icon,),
        daemon=True,
    ).start()


def on_cancel_playback(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    threading.Thread(
        target=cancel_playback_from_tray,
        args=(icon,),
        daemon=True,
    ).start()


def on_open_connection_info(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    open_connection_info()


def on_open_logs(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    open_logs_folder()


def on_open_install_folder(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    open_install_folder()


def on_uninstall(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    run_uninstaller(icon)


def on_exit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    icon.stop()


def build_menu() -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem(
            lambda item: get_cached_status_text(),
            None,
            enabled=False,
        ),
        pystray.MenuItem(
            lambda item: get_cached_coordinate_text(),
            None,
            enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Control Center", on_settings),
        pystray.MenuItem("Copy setup info", on_copy_setup_info),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Playback",
            pystray.Menu(
                pystray.MenuItem("Cancel active playback", on_cancel_playback),
                pystray.MenuItem("Release stuck mouse buttons", on_release_buttons),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Show mouse coordinates", on_show_coordinates),
                pystray.MenuItem("Copy mouse coordinates", on_copy_mouse_coordinates),
            ),
        ),
        pystray.MenuItem(
            "Recorder",
            pystray.Menu(
                pystray.MenuItem("Start mouse recording", on_start_recording_mouse),
                pystray.MenuItem(
                    "Start mouse + keyboard recording",
                    on_start_recording_mouse_keyboard,
                ),
                pystray.MenuItem("Open recordings folder", on_open_recordings),
            ),
        ),
        pystray.MenuItem(
            "Bridge",
            pystray.Menu(
                pystray.MenuItem("Start bridge", on_start),
                pystray.MenuItem("Stop bridge", on_stop),
                pystray.MenuItem("Restart bridge", on_restart),
            ),
        ),
        pystray.MenuItem(
            "Diagnostics",
            pystray.Menu(
                pystray.MenuItem("Open connection info", on_open_connection_info),
                pystray.MenuItem("Open logs folder", on_open_logs),
                pystray.MenuItem("Open install folder", on_open_install_folder),
            ),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Uninstall HA Input Bridge", on_uninstall),
        pystray.MenuItem("Exit tray icon", on_exit),
    )


def main() -> None:
    app_data_dir()

    if "--settings" in sys.argv:
        if not acquire_settings_instance_lock():
            return

        update_status_cache()
        update_coordinate_cache()
        open_settings_window()
        return

    if "--coords" in sys.argv:
        if not acquire_coords_instance_lock():
            return

        update_coordinate_cache()
        open_coordinates_window()
        return

    if "--recorder" in sys.argv:
        if not acquire_recorder_instance_lock():
            return

        mode: RecordingMode = "mouse"  # type: ignore[assignment]

        if "mouse_keyboard" in sys.argv:
            mode = "mouse_keyboard"  # type: ignore[assignment]

        update_status_cache()
        update_coordinate_cache()
        open_recorder_window(mode)
        return

    if not acquire_single_instance_lock():
        return

    config = load_config()
    write_connection_info(config)

    update_status_cache()
    update_coordinate_cache()

    icon = pystray.Icon(
        "ha-input-bridge",
        create_icon_image(get_cached_status_running()),
        f"{APP_NAME} - {'running' if get_cached_status_running() else 'stopped'}",
        build_menu(),
    )

    threading.Thread(target=status_monitor, args=(icon,), daemon=True).start()
    threading.Thread(target=coordinate_monitor, args=(icon,), daemon=True).start()

    icon.run()


if __name__ == "__main__":
    main()
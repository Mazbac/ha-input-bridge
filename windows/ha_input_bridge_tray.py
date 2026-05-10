from __future__ import annotations

import ctypes
import json
import os
import re
import secrets
import socket
import string
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pystray
from PIL import Image, ImageDraw

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:
    tk = None
    messagebox = None
    ttk = None


APP_NAME = "HA Input Bridge"
TASK_NAME = "HA Input Bridge"
FIREWALL_RULE_NAME = "HA Input Bridge - Home Assistant only"

AGENT_EXE_NAME = "ha-input-bridge-agent.exe"
TRAY_EXE_NAME = "ha-input-bridge-tray.exe"
CONNECTION_INFO_NAME = "connection-info.txt"
UNINSTALL_EXE_NAME = "unins000.exe"

DEFAULT_PORT = 8765
STATUS_POLL_SECONDS = 5

_SINGLE_INSTANCE_MUTEX = None
_STATUS_LOCK = threading.Lock()
_STATUS_RUNNING = False
_STATUS_TEXT = "Status: checking..."


def acquire_single_instance_lock() -> bool:
    global _SINGLE_INSTANCE_MUTEX

    if os.name != "nt":
        return True

    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "Global\\HAInputBridgeTraySingleInstance")
    last_error = kernel32.GetLastError()

    _SINGLE_INSTANCE_MUTEX = mutex

    return last_error != 183


def get_install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


def get_data_dir() -> Path:
    return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "HA Input Bridge"


def get_config_path() -> Path:
    return get_data_dir() / "config.json"


def get_agent_path() -> Path:
    return get_install_dir() / AGENT_EXE_NAME


def get_tray_path() -> Path:
    return get_install_dir() / TRAY_EXE_NAME


def get_connection_info_path() -> Path:
    return get_install_dir() / CONNECTION_INFO_NAME


def get_uninstall_path() -> Path:
    return get_install_dir() / UNINSTALL_EXE_NAME


def get_start_script_path() -> Path:
    return get_install_dir() / "start_ha_input_bridge.ps1"


def get_runtime_log_path() -> Path:
    return get_data_dir() / "task_runtime.log"


def get_bridge_log_path() -> Path:
    return get_data_dir() / "ha_input_bridge.log"


def get_startup_shortcut_path() -> Path:
    return (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
        / "HA Input Bridge Tray.lnk"
    )


def default_config() -> dict[str, Any]:
    return {
        "bind_host": "0.0.0.0",
        "allowed_client_ip": "",
        "firewall_remote_address": "LocalSubnet",
        "port": DEFAULT_PORT,
        "token": "",
        "log_file": str(get_bridge_log_path()),
        "start_bridge_on_login": True,
        "start_tray_on_login": True,
    }


def load_config() -> dict[str, Any]:
    config = default_config()
    path = get_config_path()

    if not path.exists():
        return config

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return config

    if not isinstance(data, dict):
        return config

    config.update(data)

    if not config.get("firewall_remote_address"):
        allowed_client_ip = str(config.get("allowed_client_ip", "")).strip()
        config["firewall_remote_address"] = allowed_client_ip or "LocalSubnet"

    return config


def save_config(config: dict[str, Any]) -> None:
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    allowed_client_ip = str(config.get("allowed_client_ip", "")).strip()
    firewall_remote_address = str(config.get("firewall_remote_address", "")).strip()

    if not firewall_remote_address:
        firewall_remote_address = allowed_client_ip or "LocalSubnet"

    config["bind_host"] = str(config.get("bind_host", "0.0.0.0")).strip() or "0.0.0.0"
    config["allowed_client_ip"] = allowed_client_ip
    config["firewall_remote_address"] = firewall_remote_address
    config["port"] = int(config.get("port", DEFAULT_PORT))
    config["log_file"] = str(get_bridge_log_path())

    get_config_path().write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )


def generate_token() -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(43))


def is_usable_host_ip(ip_address: str) -> bool:
    return (
        ip_address
        and not ip_address.startswith("127.")
        and not ip_address.startswith("169.254.")
        and ip_address != "0.0.0.0"
    )


def get_host_candidates() -> list[str]:
    candidates: list[str] = []

    try:
        hostname = socket.gethostname()
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
    except OSError:
        infos = []

    for info in infos:
        ip_address = info[4][0]

        if is_usable_host_ip(ip_address) and ip_address not in candidates:
            candidates.append(ip_address)

    return candidates


def get_recommended_host(config: dict[str, Any]) -> str:
    bind_host = str(config.get("bind_host", "")).strip()

    if is_usable_host_ip(bind_host):
        return bind_host

    candidates = get_host_candidates()

    if candidates:
        return candidates[0]

    return bind_host or "0.0.0.0"


def build_setup_info_text(config: dict[str, Any]) -> str:
    return "\n".join(
        [
            "HA Input Bridge",
            f"Host: {get_recommended_host(config)}",
            f"Port: {config.get('port', DEFAULT_PORT)}",
            f"Token: {config.get('token', '')}",
        ]
    )


def write_connection_info(config: dict[str, Any]) -> None:
    candidates = get_host_candidates()
    candidates_text = ", ".join(candidates) if candidates else "Use the Windows PC IP address"

    text = "\n".join(
        [
            "HA Input Bridge connection details",
            "",
            "Use these values in Home Assistant:",
            "",
            f"Host: {get_recommended_host(config)}",
            f"Port: {config.get('port', DEFAULT_PORT)}",
            f"Token: {config.get('token', '')}",
            "",
            "Possible Host values:",
            candidates_text,
            "",
            "Bridge bind address:",
            str(config.get("bind_host", "0.0.0.0")),
            "",
            "Firewall remote address:",
            str(config.get("firewall_remote_address", "LocalSubnet")),
            "",
            "Tray app:",
            str(get_tray_path()),
            "",
            "Config:",
            str(get_config_path()),
            "",
            "Logs:",
            str(get_data_dir()),
            "",
            "Home Assistant setup:",
            "Settings -> Devices & services -> Add integration -> HA Input Bridge",
            "",
            "Keep this token private.",
            "",
        ]
    )

    get_connection_info_path().write_text(text, encoding="utf-8")


def read_connection_info() -> str:
    path = get_connection_info_path()

    if not path.exists():
        return ""

    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def read_bridge_port() -> int:
    config = load_config()

    try:
        port = int(config.get("port", DEFAULT_PORT))
    except (TypeError, ValueError):
        port = DEFAULT_PORT

    if 1 <= port <= 65535:
        return port

    text = read_connection_info()
    match = re.search(r"^Port:\s*(\d+)\s*$", text, re.MULTILINE)

    if not match:
        return DEFAULT_PORT

    try:
        port = int(match.group(1))
    except ValueError:
        return DEFAULT_PORT

    if port < 1 or port > 65535:
        return DEFAULT_PORT

    return port


def ps_quote(value: str | Path) -> str:
    text = str(value).replace("'", "''")
    return f"'{text}'"


def run_powershell(script: str, wait: bool = True) -> subprocess.CompletedProcess[str] | subprocess.Popen:
    creationflags = 0

    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]

    if wait:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            creationflags=creationflags,
            check=False,
        )

    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def set_clipboard_text(text: str, root: tk.Tk | tk.Toplevel | None = None) -> bool:
    try:
        temp_path = Path(tempfile.gettempdir()) / "ha-input-bridge-clipboard.txt"
        temp_path.write_text(text, encoding="utf-8")

        script = f"""
$Text = Get-Content -Path {ps_quote(temp_path)} -Raw -Encoding UTF8
Set-Clipboard -Value $Text
"""

        result = run_powershell(script)

        if isinstance(result, subprocess.CompletedProcess) and result.returncode == 0:
            return True
    except Exception:
        pass

    if root is not None:
        try:
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            return True
        except Exception:
            return False

    return False


def run_powershell_file_elevated(script: str) -> None:
    script_path = Path(tempfile.gettempdir()) / "ha-input-bridge-apply-settings.ps1"
    script_path.write_text(script, encoding="utf-8")

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "Start-Process powershell.exe "
            f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{script_path}\"' "
            "-Verb RunAs -Wait"
        ),
    ]

    subprocess.run(command, check=False)


def get_listener_process_id() -> int | None:
    port = read_bridge_port()

    script = f"""
$connection = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue |
  Select-Object -First 1

if ($null -ne $connection) {{
  Write-Output $connection.OwningProcess
}}
"""

    result = run_powershell(script)

    if not isinstance(result, subprocess.CompletedProcess):
        return None

    value = result.stdout.strip()

    if not value:
        return None

    try:
        return int(value.splitlines()[0].strip())
    except ValueError:
        return None


def is_agent_process(process_id: int) -> bool:
    script = f"""
$process = Get-Process -Id {process_id} -ErrorAction SilentlyContinue

if ($null -ne $process) {{
  Write-Output $process.ProcessName
}}
"""

    result = run_powershell(script)

    if not isinstance(result, subprocess.CompletedProcess):
        return False

    return result.stdout.strip().lower() == "ha-input-bridge-agent"


def detect_bridge_running() -> bool:
    listener_pid = get_listener_process_id()

    if listener_pid is None:
        return False

    return is_agent_process(listener_pid)


def update_status_cache() -> bool:
    global _STATUS_RUNNING
    global _STATUS_TEXT

    running = detect_bridge_running()

    with _STATUS_LOCK:
        _STATUS_RUNNING = running
        _STATUS_TEXT = "Status: running" if running else "Status: stopped"

    return running


def get_cached_status_text() -> str:
    with _STATUS_LOCK:
        return _STATUS_TEXT


def get_cached_status_running() -> bool:
    with _STATUS_LOCK:
        return _STATUS_RUNNING


def start_bridge() -> bool:
    if detect_bridge_running():
        update_status_cache()
        return True

    script = f"""
Start-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
"""

    result = run_powershell(script)

    if isinstance(result, subprocess.CompletedProcess) and result.returncode != 0:
        update_status_cache()
        return False

    return update_status_cache()


def stop_bridge() -> bool:
    listener_pid = get_listener_process_id()
    agent_path = str(get_agent_path()).replace("'", "''")

    listener_stop = ""

    if listener_pid is not None:
        listener_stop = f"Stop-Process -Id {listener_pid} -Force -ErrorAction SilentlyContinue"

    script = f"""
Stop-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue

{listener_stop}

Get-CimInstance Win32_Process |
  Where-Object {{
    $_.Name -eq '{AGENT_EXE_NAME}' -and
    (
      $_.ExecutablePath -eq '{agent_path}' -or
      $_.CommandLine -like '*{AGENT_EXE_NAME}*'
    )
  }} |
  ForEach-Object {{
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }}

Start-Sleep -Seconds 1
"""

    result = run_powershell(script)

    if isinstance(result, subprocess.CompletedProcess) and result.returncode != 0:
        update_status_cache()
        return False

    return not update_status_cache()


def restart_bridge() -> bool:
    stop_bridge()
    time.sleep(1)
    return start_bridge()


def apply_system_settings_elevated(config: dict[str, Any]) -> None:
    data_dir = get_data_dir()
    config_path = get_config_path()
    agent_path = get_agent_path()
    start_script_path = get_start_script_path()
    runtime_log_path = get_runtime_log_path()

    bridge_on_login = bool(config.get("start_bridge_on_login", True))
    bridge_on_login_ps = "$true" if bridge_on_login else "$false"

    firewall_remote_address = str(
        config.get("firewall_remote_address")
        or config.get("allowed_client_ip")
        or "LocalSubnet"
    ).strip()

    if not firewall_remote_address:
        firewall_remote_address = "LocalSubnet"

    task_enabled_script = (
        f"Enable-ScheduledTask -TaskName {ps_quote(TASK_NAME)} | Out-Null"
        if bridge_on_login
        else f"Disable-ScheduledTask -TaskName {ps_quote(TASK_NAME)} | Out-Null"
    )

    script = f"""
$ErrorActionPreference = "Stop"

$DataDir = {ps_quote(data_dir)}
$ConfigPath = {ps_quote(config_path)}
$AgentExe = {ps_quote(agent_path)}
$StartScript = {ps_quote(start_script_path)}
$RuntimeLog = {ps_quote(runtime_log_path)}
$TaskName = {ps_quote(TASK_NAME)}
$FirewallRuleName = {ps_quote(FIREWALL_RULE_NAME)}
$Port = {int(config.get("port", DEFAULT_PORT))}
$FirewallRemoteAddress = {ps_quote(firewall_remote_address)}
$StartBridgeOnLogin = {bridge_on_login_ps}
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
& icacls $DataDir /grant "${{CurrentUser}}:(OI)(CI)M" /T | Out-Null

$StartContent = @"
`$env:HA_INPUT_CONFIG_FILE = '$ConfigPath'
& "$AgentExe" *> "$RuntimeLog"
"@

Set-Content -Path $StartScript -Value $StartContent -Encoding UTF8

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

Get-CimInstance Win32_Process |
  Where-Object {{
    $_.Name -eq '{AGENT_EXE_NAME}' -and
    (
      $_.ExecutablePath -eq '{str(agent_path).replace("'", "''")}' -or
      $_.CommandLine -like '*{AGENT_EXE_NAME}*'
    )
  }} |
  ForEach-Object {{
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }}

Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue |
  Remove-NetFirewallRule -ErrorAction SilentlyContinue

New-NetFirewallRule `
  -DisplayName $FirewallRuleName `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort $Port `
  -Action Allow `
  -RemoteAddress $FirewallRemoteAddress | Out-Null

{task_enabled_script}

if ($StartBridgeOnLogin) {{
  Start-ScheduledTask -TaskName $TaskName
}}

Start-Sleep -Seconds 2
"""

    run_powershell_file_elevated(script)


def create_or_remove_startup_shortcut(enabled: bool) -> None:
    shortcut = get_startup_shortcut_path()
    tray_path = get_tray_path()

    if enabled:
        shortcut.parent.mkdir(parents=True, exist_ok=True)

        script = f"""
$ShortcutPath = {ps_quote(shortcut)}
$TargetPath = {ps_quote(tray_path)}
$WorkingDirectory = {ps_quote(get_install_dir())}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $WorkingDirectory
$Shortcut.Save()
"""
        run_powershell(script)
        return

    try:
        shortcut.unlink(missing_ok=True)
    except OSError:
        pass


def open_connection_info() -> None:
    path = get_connection_info_path()

    if path.exists():
        os.startfile(path)


def open_logs_folder() -> None:
    path = get_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(path)


def open_install_folder() -> None:
    path = get_install_dir()

    if path.exists():
        os.startfile(path)


def run_uninstaller(icon: pystray.Icon) -> None:
    uninstall_path = get_uninstall_path()

    if uninstall_path.exists():
        subprocess.Popen([str(uninstall_path)])
        icon.stop()


def create_icon_image(running: bool) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    fill = (35, 160, 80, 255) if running else (180, 55, 55, 255)
    outline = (255, 255, 255, 255)

    draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill=fill, outline=outline, width=3)
    draw.rectangle((18, 20, 46, 30), fill=(255, 255, 255, 255))
    draw.rectangle((26, 32, 38, 44), fill=(255, 255, 255, 255))
    draw.rectangle((20, 46, 44, 50), fill=(255, 255, 255, 255))

    return image


def notify(icon: pystray.Icon, message: str) -> None:
    try:
        icon.notify(message, APP_NAME)
    except Exception:
        pass


def refresh_icon(icon: pystray.Icon) -> None:
    running = get_cached_status_running()
    icon.icon = create_icon_image(running)
    icon.title = f"{APP_NAME} - {'running' if running else 'stopped'}"

    try:
        icon.update_menu()
    except Exception:
        pass


def status_monitor(icon: pystray.Icon) -> None:
    while True:
        update_status_cache()
        refresh_icon(icon)
        time.sleep(STATUS_POLL_SECONDS)


def run_async_operation(
    icon: pystray.Icon,
    busy_message: str,
    operation: Callable[[], bool],
    success_message: str,
    failure_message: str,
) -> None:
    notify(icon, busy_message)

    def worker() -> None:
        ok = operation()
        refresh_icon(icon)
        notify(icon, success_message if ok else failure_message)

    threading.Thread(target=worker, daemon=True).start()


def launch_settings_window() -> None:
    if getattr(sys, "frozen", False):
        subprocess.Popen([str(get_tray_path()), "--settings"], cwd=str(get_install_dir()))
        return

    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--settings"])


def copy_setup_info_from_tray(icon: pystray.Icon) -> None:
    config = load_config()
    text = build_setup_info_text(config)

    if set_clipboard_text(text):
        notify(icon, "Connection info copied.")
    else:
        notify(icon, "Could not copy connection info.")


def open_settings_window() -> None:
    if tk is None or ttk is None or messagebox is None:
        return

    config = load_config()

    root = tk.Tk()
    root.title("HA Input Bridge Settings")
    root.resizable(False, False)

    main = ttk.Frame(root, padding=16)
    main.grid(row=0, column=0, sticky="nsew")

    status_var = tk.StringVar(value=get_cached_status_text())
    token_var = tk.StringVar(value=str(config.get("token", "")))
    token_visible_var = tk.BooleanVar(value=False)
    bridge_login_var = tk.BooleanVar(value=bool(config.get("start_bridge_on_login", True)))
    tray_login_var = tk.BooleanVar(value=bool(config.get("start_tray_on_login", True)))

    bind_host_var = tk.StringVar(value=str(config.get("bind_host", "0.0.0.0")))
    allowed_ip_var = tk.StringVar(value=str(config.get("allowed_client_ip", "")))
    port_var = tk.StringVar(value=str(config.get("port", DEFAULT_PORT)))

    notebook = ttk.Notebook(main)
    notebook.grid(row=0, column=0, sticky="nsew")

    basic = ttk.Frame(notebook, padding=12)
    advanced = ttk.Frame(notebook, padding=12)

    notebook.add(basic, text="Basic")
    notebook.add(advanced, text="Advanced")

    recommended_host = get_recommended_host(config)

    ttk.Label(basic, textvariable=status_var).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(basic, text=f"Home Assistant host: {recommended_host}").grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
    ttk.Label(basic, text=f"Port: {config.get('port', DEFAULT_PORT)}").grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
    ttk.Label(basic, text="Listening mode: Automatic - all local network adapters").grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))

    ttk.Label(basic, text="Token:").grid(row=4, column=0, sticky="w", pady=(12, 0))
    token_entry = ttk.Entry(basic, textvariable=token_var, width=46, show="•")
    token_entry.grid(row=4, column=1, sticky="ew", padx=(12, 0), pady=(12, 0))

    def toggle_token_visibility() -> None:
        if token_visible_var.get():
            token_entry.configure(show="•")
            token_visible_var.set(False)
            token_toggle_button.configure(text="Show")
        else:
            token_entry.configure(show="")
            token_visible_var.set(True)
            token_toggle_button.configure(text="Hide")

    token_toggle_button = ttk.Button(basic, text="Show", width=8, command=toggle_token_visibility)
    token_toggle_button.grid(row=4, column=2, sticky="ew", padx=(8, 0), pady=(12, 0))

    ttk.Checkbutton(basic, text="Start bridge on Windows login", variable=bridge_login_var).grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 0))
    ttk.Checkbutton(basic, text="Start tray icon on Windows login", variable=tray_login_var).grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 0))

    ttk.Label(advanced, text="Bind address:").grid(row=0, column=0, sticky="w")
    ttk.Entry(advanced, textvariable=bind_host_var, width=46).grid(row=0, column=1, sticky="ew", padx=(12, 0))

    ttk.Label(advanced, text="Allowed Home Assistant IP:").grid(row=1, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(advanced, textvariable=allowed_ip_var, width=46).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(8, 0))

    ttk.Label(advanced, text="Bridge port:").grid(row=2, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(advanced, textvariable=port_var, width=46).grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=(8, 0))

    ttk.Label(
        advanced,
        text="Leave Allowed Home Assistant IP empty to allow the local subnet. Use 0.0.0.0 to listen on all adapters.",
        wraplength=520,
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def validate_form() -> dict[str, Any] | None:
        bind_host = bind_host_var.get().strip() or "0.0.0.0"
        allowed_ip = allowed_ip_var.get().strip()
        port_text = port_var.get().strip()
        token = token_var.get().strip()

        try:
            port = int(port_text)
        except ValueError:
            messagebox.showerror(APP_NAME, "Enter a numeric bridge port.")
            return None

        if port < 1 or port > 65535:
            messagebox.showerror(APP_NAME, "Enter a bridge port between 1 and 65535.")
            return None

        if not token:
            messagebox.showerror(APP_NAME, "Token cannot be empty.")
            return None

        firewall_remote_address = allowed_ip if allowed_ip else "LocalSubnet"

        return {
            "bind_host": bind_host,
            "allowed_client_ip": allowed_ip,
            "firewall_remote_address": firewall_remote_address,
            "port": port,
            "token": token,
            "log_file": str(get_bridge_log_path()),
            "start_bridge_on_login": bool(bridge_login_var.get()),
            "start_tray_on_login": bool(tray_login_var.get()),
        }

    def refresh_settings_status() -> None:
        update_status_cache()
        status_var.set(get_cached_status_text())

    def save_and_restart() -> None:
        new_config = validate_form()

        if new_config is None:
            return

        save_config(new_config)
        write_connection_info(new_config)
        create_or_remove_startup_shortcut(bool(new_config.get("start_tray_on_login", True)))

        status_var.set("Status: applying settings...")

        messagebox.showinfo(
            APP_NAME,
            "Windows will ask for administrator permission to apply firewall and startup changes.",
        )

        def worker() -> None:
            apply_system_settings_elevated(new_config)
            root.after(0, refresh_settings_status)

        threading.Thread(target=worker, daemon=True).start()

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
            messagebox.showerror(APP_NAME, "Could not copy connection info. Use Open Info File instead.")

    def open_info() -> None:
        new_config = validate_form()

        if new_config is not None:
            save_config(new_config)
            write_connection_info(new_config)

        open_connection_info()

    buttons = ttk.Frame(main)
    buttons.grid(row=1, column=0, sticky="ew", pady=(12, 0))

    ttk.Button(buttons, text="Save & Restart Bridge", command=save_and_restart).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons, text="Regenerate Token", command=regenerate_token).grid(row=0, column=1, padx=(0, 8))
    ttk.Button(buttons, text="Copy Setup Info", command=copy_info).grid(row=0, column=2, padx=(0, 8))
    ttk.Button(buttons, text="Open Info File", command=open_info).grid(row=0, column=3)

    buttons2 = ttk.Frame(main)
    buttons2.grid(row=2, column=0, sticky="ew", pady=(8, 0))

    ttk.Button(buttons2, text="Open Logs", command=open_logs_folder).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons2, text="Open Install Folder", command=open_install_folder).grid(row=0, column=1, padx=(0, 8))
    ttk.Button(buttons2, text="Close", command=root.destroy).grid(row=0, column=2)

    root.mainloop()


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


def on_copy_setup_info(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    threading.Thread(target=copy_setup_info_from_tray, args=(icon,), daemon=True).start()


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
        pystray.MenuItem(lambda item: get_cached_status_text(), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Settings...", on_settings),
        pystray.MenuItem("Copy setup info", on_copy_setup_info),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start bridge", on_start),
        pystray.MenuItem("Stop bridge", on_stop),
        pystray.MenuItem("Restart bridge", on_restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open connection info", on_open_connection_info),
        pystray.MenuItem("Open logs folder", on_open_logs),
        pystray.MenuItem("Open install folder", on_open_install_folder),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Uninstall HA Input Bridge", on_uninstall),
        pystray.MenuItem("Exit tray icon", on_exit),
    )


def main() -> None:
    if "--settings" in sys.argv:
        update_status_cache()
        open_settings_window()
        return

    if not acquire_single_instance_lock():
        return

    update_status_cache()

    icon = pystray.Icon(
        "ha-input-bridge",
        create_icon_image(get_cached_status_running()),
        f"{APP_NAME} - {'running' if get_cached_status_running() else 'stopped'}",
        build_menu(),
    )

    threading.Thread(target=status_monitor, args=(icon,), daemon=True).start()

    icon.run()


if __name__ == "__main__":
    main()

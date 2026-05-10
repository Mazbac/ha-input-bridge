from __future__ import annotations

import json
import os
import re
import secrets
import string
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

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
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "HA Input Bridge Tray.lnk"


def default_config() -> dict[str, Any]:
    return {
        "bind_host": "",
        "allowed_client_ip": "",
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
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return config

    if not isinstance(data, dict):
        return config

    config.update(data)
    return config


def save_config(config: dict[str, Any]) -> None:
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    config["port"] = int(config.get("port", DEFAULT_PORT))
    config["log_file"] = str(get_bridge_log_path())

    get_config_path().write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )


def generate_token() -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(43))


def write_connection_info(config: dict[str, Any]) -> None:
    text = "\n".join(
        [
            "HA Input Bridge connection details",
            "",
            "Use these values in Home Assistant:",
            "",
            f"Host: {config.get('bind_host', '')}",
            f"Port: {config.get('port', DEFAULT_PORT)}",
            f"Token: {config.get('token', '')}",
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
        return path.read_text(encoding="utf-8", errors="replace")
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


def run_powershell_file_elevated(script: str) -> None:
    temp_dir = Path(tempfile.gettempdir())
    script_path = temp_dir / "ha-input-bridge-apply-settings.ps1"
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


def ps_quote(value: str | Path) -> str:
    text = str(value).replace("'", "''")
    return f"'{text}'"


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


def get_agent_process_id() -> int | None:
    agent_path = str(get_agent_path()).replace("'", "''")

    script = f"""
$process = Get-CimInstance Win32_Process |
  Where-Object {{
    $_.Name -eq '{AGENT_EXE_NAME}' -and
    (
      $_.ExecutablePath -eq '{agent_path}' -or
      $_.CommandLine -like '*{AGENT_EXE_NAME}*'
    )
  }} |
  Select-Object -First 1

if ($null -ne $process) {{
  Write-Output $process.ProcessId
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


def is_bridge_running() -> bool:
    listener_pid = get_listener_process_id()
    agent_pid = get_agent_process_id()

    return listener_pid is not None and agent_pid is not None and listener_pid == agent_pid


def get_status_text() -> str:
    if is_bridge_running():
        return "Status: running"

    return "Status: stopped"


def start_bridge() -> bool:
    script = f"""
Start-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
"""

    result = run_powershell(script)

    if isinstance(result, subprocess.CompletedProcess) and result.returncode != 0:
        return False

    return is_bridge_running()


def stop_bridge() -> bool:
    agent_path = str(get_agent_path()).replace("'", "''")

    script = f"""
Stop-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue

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
        return False

    return not is_bridge_running()


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
$AllowedClientIp = {ps_quote(str(config.get("allowed_client_ip", "")))}
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
  -RemoteAddress $AllowedClientIp | Out-Null

{task_enabled_script}

if ({str(bridge_on_login).lower()}) {{
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


def copy_connection_info_to_clipboard(root: tk.Tk | tk.Toplevel) -> None:
    config = load_config()

    text = "\n".join(
        [
            "HA Input Bridge",
            f"Host: {config.get('bind_host', '')}",
            f"Port: {config.get('port', DEFAULT_PORT)}",
            f"Token: {config.get('token', '')}",
        ]
    )

    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()


def run_uninstaller(icon: pystray.Icon) -> None:
    uninstall_path = get_uninstall_path()

    if uninstall_path.exists():
        subprocess.Popen([str(uninstall_path)])
        icon.stop()


def create_icon_image(running: bool) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if running:
        fill = (35, 160, 80, 255)
    else:
        fill = (180, 55, 55, 255)

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
    running = is_bridge_running()
    icon.icon = create_icon_image(running)
    icon.title = f"{APP_NAME} - {'running' if running else 'stopped'}"

    try:
        icon.update_menu()
    except Exception:
        pass


def open_settings_window(icon: pystray.Icon | None = None) -> None:
    if tk is None or ttk is None or messagebox is None:
        if icon is not None:
            notify(icon, "Settings UI is unavailable.")
        return

    config = load_config()

    root = tk.Tk()
    root.title("HA Input Bridge Settings")
    root.resizable(False, False)

    main = ttk.Frame(root, padding=16)
    main.grid(row=0, column=0, sticky="nsew")

    bind_host_var = tk.StringVar(value=str(config.get("bind_host", "")))
    allowed_ip_var = tk.StringVar(value=str(config.get("allowed_client_ip", "")))
    port_var = tk.StringVar(value=str(config.get("port", DEFAULT_PORT)))
    token_var = tk.StringVar(value=str(config.get("token", "")))
    bridge_login_var = tk.BooleanVar(value=bool(config.get("start_bridge_on_login", True)))
    tray_login_var = tk.BooleanVar(value=bool(config.get("start_tray_on_login", True)))

    row = 0

    ttk.Label(main, text="Windows PC IP address to listen on:").grid(row=row, column=0, sticky="w")
    ttk.Entry(main, textvariable=bind_host_var, width=46).grid(row=row, column=1, sticky="ew", padx=(12, 0))
    row += 1

    ttk.Label(main, text="Home Assistant IP allowed to connect:").grid(row=row, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(main, textvariable=allowed_ip_var, width=46).grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=(8, 0))
    row += 1

    ttk.Label(main, text="Bridge port:").grid(row=row, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(main, textvariable=port_var, width=46).grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=(8, 0))
    row += 1

    ttk.Label(main, text="Token:").grid(row=row, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(main, textvariable=token_var, width=46, show="•").grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=(8, 0))
    row += 1

    ttk.Checkbutton(main, text="Start bridge on Windows login", variable=bridge_login_var).grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 0))
    row += 1

    ttk.Checkbutton(main, text="Start tray icon on Windows login", variable=tray_login_var).grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 0))
    row += 1

    status_var = tk.StringVar(value=get_status_text())
    ttk.Label(main, textvariable=status_var).grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 0))
    row += 1

    def validate_form() -> dict[str, Any] | None:
        bind_host = bind_host_var.get().strip()
        allowed_ip = allowed_ip_var.get().strip()
        port_text = port_var.get().strip()
        token = token_var.get().strip()

        if not bind_host:
            messagebox.showerror(APP_NAME, "Enter the Windows PC IP address.")
            return None

        if not allowed_ip:
            messagebox.showerror(APP_NAME, "Enter the Home Assistant IP address.")
            return None

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

        return {
            "bind_host": bind_host,
            "allowed_client_ip": allowed_ip,
            "port": port,
            "token": token,
            "log_file": str(get_bridge_log_path()),
            "start_bridge_on_login": bool(bridge_login_var.get()),
            "start_tray_on_login": bool(tray_login_var.get()),
        }

    def refresh_status() -> None:
        status_var.set(get_status_text())

        if icon is not None:
            refresh_icon(icon)

    def save_and_restart() -> None:
        new_config = validate_form()

        if new_config is None:
            return

        save_config(new_config)
        write_connection_info(new_config)
        create_or_remove_startup_shortcut(bool(new_config.get("start_tray_on_login", True)))

        messagebox.showinfo(
            APP_NAME,
            "Windows will ask for administrator permission to apply firewall and startup changes.",
        )

        def worker() -> None:
            apply_system_settings_elevated(new_config)
            root.after(0, refresh_status)
            if icon is not None:
                notify(icon, "Settings saved and bridge restarted.")

        threading.Thread(target=worker, daemon=True).start()

    def regenerate_token() -> None:
        token_var.set(generate_token())

    def copy_info() -> None:
        new_config = validate_form()

        if new_config is None:
            return

        save_config(new_config)
        write_connection_info(new_config)
        copy_connection_info_to_clipboard(root)
        messagebox.showinfo(APP_NAME, "Connection info copied to clipboard.")

    def open_info() -> None:
        new_config = validate_form()

        if new_config is not None:
            save_config(new_config)
            write_connection_info(new_config)

        open_connection_info()

    buttons = ttk.Frame(main)
    buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(16, 0))

    ttk.Button(buttons, text="Save & Restart Bridge", command=save_and_restart).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons, text="Regenerate Token", command=regenerate_token).grid(row=0, column=1, padx=(0, 8))
    ttk.Button(buttons, text="Copy Setup Info", command=copy_info).grid(row=0, column=2, padx=(0, 8))
    ttk.Button(buttons, text="Open Info File", command=open_info).grid(row=0, column=3)

    buttons2 = ttk.Frame(main)
    buttons2.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    ttk.Button(buttons2, text="Open Logs", command=open_logs_folder).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons2, text="Open Install Folder", command=open_install_folder).grid(row=0, column=1, padx=(0, 8))
    ttk.Button(buttons2, text="Close", command=root.destroy).grid(row=0, column=2)

    root.mainloop()


def on_start(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    if start_bridge():
        notify(icon, "Bridge started.")
    else:
        notify(icon, "Bridge could not be started.")

    refresh_icon(icon)


def on_stop(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    if stop_bridge():
        notify(icon, "Bridge stopped.")
    else:
        notify(icon, "Bridge could not be stopped.")

    refresh_icon(icon)


def on_restart(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    if restart_bridge():
        notify(icon, "Bridge restarted.")
    else:
        notify(icon, "Bridge could not be restarted.")

    refresh_icon(icon)


def on_settings(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    threading.Thread(target=open_settings_window, args=(icon,), daemon=True).start()


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
        pystray.MenuItem(lambda item: get_status_text(), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Settings...", on_settings),
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
    running = is_bridge_running()

    icon = pystray.Icon(
        "ha-input-bridge",
        create_icon_image(running),
        f"{APP_NAME} - {'running' if running else 'stopped'}",
        build_menu(),
    )

    icon.run()


if __name__ == "__main__":
    main()

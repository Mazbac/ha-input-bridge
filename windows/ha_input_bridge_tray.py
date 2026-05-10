from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pystray
from PIL import Image, ImageDraw


APP_NAME = "HA Input Bridge"
TASK_NAME = "HA Input Bridge"
AGENT_EXE_NAME = "ha-input-bridge-agent.exe"
CONNECTION_INFO_NAME = "connection-info.txt"
UNINSTALL_EXE_NAME = "unins000.exe"
DEFAULT_PORT = 8765


def get_install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


def get_data_dir() -> Path:
    return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "HA Input Bridge"


def get_agent_path() -> Path:
    return get_install_dir() / AGENT_EXE_NAME


def get_connection_info_path() -> Path:
    return get_install_dir() / CONNECTION_INFO_NAME


def get_uninstall_path() -> Path:
    return get_install_dir() / UNINSTALL_EXE_NAME


def read_connection_info() -> str:
    path = get_connection_info_path()

    if not path.exists():
        return ""

    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_bridge_port() -> int:
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

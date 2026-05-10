# HA Input Bridge

HA Input Bridge lets Home Assistant send mouse and keyboard input to a Windows PC.

It is designed for a simple setup:

1. Install the Windows app.
2. Copy setup info from the tray icon.
3. Paste it into Home Assistant.
4. Use the Home Assistant trackpad.

No Python, PowerShell, manual token editing, or manual config files are required for normal use.

---

## What it does

HA Input Bridge runs a small local bridge on your Windows PC.

Home Assistant can then send commands such as:

- move mouse
- click
- scroll
- type text
- press keys
- use hotkeys

The bridge is protected by:

- a private token
- Windows Firewall
- a short arm window before input commands are accepted

---

## Install on Windows

Download the latest Windows installer from the GitHub Releases page:

```text
HA-Input-Bridge-Setup.exe

# HA Input Bridge

Home Assistant custom integration for controlling a Windows PC through a local input bridge.

HA Input Bridge adds a sidebar trackpad panel to Home Assistant and exposes services for mouse movement, clicks, scrolling, keyboard input, and hotkeys.

## Status

Experimental.

The Home Assistant integration, bundled sidebar trackpad, and services are currently usable for testing. The Windows bridge currently requires manual setup. A Windows installer is planned.

## What this project includes

- Home Assistant custom integration
- UI config flow
- Automatic sidebar panel: **PC Trackpad**
- Bundled mobile-first trackpad UI
- Home Assistant services/actions for mouse and keyboard control
- Local HTTP client for a Windows bridge agent

## What this project does not include yet

- One-click Windows installer
- Automatic Windows Firewall setup
- Automatic Windows Scheduled Task setup
- Automatic token generation from Home Assistant
- Signed Windows executable
- Multi-PC selector in the trackpad UI

## Architecture

```text
Home Assistant
→ HA Input Bridge custom integration
→ Windows HA Input Bridge agent
→ PyAutoGUI
→ Windows mouse and keyboard input
```

Sidebar UI:

```text
Home Assistant sidebar
→ PC Trackpad
→ ha_input_bridge services
→ Windows bridge
```

## Requirements

- Home Assistant
- HACS
- Windows PC
- Python on the Windows PC
- Network access from Home Assistant to the Windows PC
- Shared secret token
- Windows bridge agent running on the target PC

## Installation through HACS

1. Open HACS.
2. Open the three-dot menu.
3. Select **Custom repositories**.
4. Add this repository URL.
5. Select category **Integration**.
6. Install **HA Input Bridge**.
7. Restart Home Assistant.
8. Go to **Settings → Devices & services → Add integration**.
9. Search for **HA Input Bridge**.
10. Enter the Windows PC host, port, token, and display name.

## Configuration

The setup flow asks for:

| Field | Description |
| --- | --- |
| Name | Display name for this bridge |
| Host | IP address or hostname of the Windows PC |
| Port | Bridge port, default `8765` |
| Token | Secret token used by the Windows bridge |

Example:

```text
Name: My Windows PC
Host: <WINDOWS_PC_IP_OR_HOSTNAME>
Port: 8765
Token: <BRIDGE_TOKEN>
```

Example using a generic private LAN address:

```text
Name: Office PC
Host: 192.168.1.50
Port: 8765
Token: <BRIDGE_TOKEN>
```

Do not publish your real token.

## Sidebar panel

After installation and setup, Home Assistant adds this sidebar item automatically:

```text
PC Trackpad
```

This opens the bundled trackpad UI.

You do not need to add a dashboard resource manually for the default sidebar experience.

## Dashboard card

The integration also serves the bundled dashboard card JavaScript from:

```text
/ha_input_bridge/pc-trackpad-card.js
```

Manual dashboard usage is optional. The main user experience is the automatic sidebar panel.

Example dashboard card:

```yaml
type: custom:pc-trackpad-card
```

If you use the card manually, add this resource first:

```text
/ha_input_bridge/pc-trackpad-card.js
```

Resource type:

```text
JavaScript module
```

## Services

After setup, this integration provides these Home Assistant services:

```text
ha_input_bridge.arm
ha_input_bridge.position
ha_input_bridge.move
ha_input_bridge.move_relative
ha_input_bridge.click
ha_input_bridge.scroll
ha_input_bridge.write
ha_input_bridge.press
ha_input_bridge.hotkey
```

## Example service calls

### Arm bridge

```yaml
action: ha_input_bridge.arm
data:
  seconds: 30
```

### Get mouse position

```yaml
action: ha_input_bridge.position
data: {}
response_variable: position
```

### Move mouse to absolute coordinates

```yaml
action: ha_input_bridge.move
data:
  x: 500
  y: 300
```

### Move mouse relative

```yaml
action: ha_input_bridge.move_relative
data:
  dx: 50
  dy: 0
```

### Click

```yaml
action: ha_input_bridge.click
data:
  button: left
  clicks: 1
```

### Scroll

```yaml
action: ha_input_bridge.scroll
data:
  amount: -10
```

### Write text

```yaml
action: ha_input_bridge.write
data:
  text: Hello from Home Assistant
```

### Press key

```yaml
action: ha_input_bridge.press
data:
  key: enter
```

### Hotkey

```yaml
action: ha_input_bridge.hotkey
data:
  keys:
    - ctrl
    - l
```

## Windows bridge

The Windows bridge is the local agent that receives commands from Home Assistant and performs input actions on Windows.

Current manual setup uses:

```text
C:\ha-input-bridge\
```

Expected Windows bridge settings:

```text
Host: <WINDOWS_PC_IP_OR_HOSTNAME>
Port: 8765
Token: <BRIDGE_TOKEN>
Allowed client IP: <HOME_ASSISTANT_IP>
```

The bridge should listen on the Windows PC address, for example:

```text
<WINDOWS_PC_IP>:8765
```

The Home Assistant integration should then be configured with:

```text
Host: <WINDOWS_PC_IP_OR_HOSTNAME>
Port: 8765
Token: <BRIDGE_TOKEN>
```

## Security warning

This project controls mouse and keyboard input on a Windows PC.

Do not expose the Windows bridge directly to the internet.

Recommended safeguards:

- Use a strong random token.
- Bind the Windows bridge only to LAN or Tailscale.
- Restrict Windows Firewall to the Home Assistant IP.
- Keep the arm-before-input safety model enabled.
- Do not log typed text.
- Do not publish your token.
- Do not publish your personal network details in issues.
- Do not use this on shared or untrusted networks.
- Do not port-forward this bridge.
- Do not expose it through a public reverse proxy.

## Recommended network layout

```text
Home Assistant LAN IP → allowed to call Windows bridge
Other clients → blocked by firewall or rejected by allowlist
Internet → no access
```

Generic example:

```text
Windows PC:       192.168.1.50
Home Assistant:   192.168.1.10
Bridge port:      8765
```

These are example addresses only.

## Development roadmap

- Add Windows installer
- Add Windows uninstaller
- Add automatic token generation
- Add Windows Firewall rule creation
- Add Windows Scheduled Task creation
- Add health sensor
- Add position sensor
- Add diagnostics
- Improve multi-bridge support
- Add HACS validation workflow
- Add Hassfest validation workflow
- Publish first GitHub release

## Troubleshooting

### Integration does not appear after HACS install

Restart Home Assistant.

If it still does not appear, clear browser cache or reload the Home Assistant frontend.

### Sidebar item is visible but blank

Hard-refresh the browser or restart Home Assistant.

Check that this URL loads JavaScript:

```text
/ha_input_bridge/pc-trackpad-panel.js
```

### Trackpad shows errors while moving

Check the Windows bridge log:

```powershell
Get-Content C:\ha-input-bridge\ha_input_bridge.log -Tail 120
Get-Content C:\ha-input-bridge\task_runtime.log -Tail 120
```

Check that the bridge is listening:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen
```

### Manual Windows bridge debug

Run the bridge through the start script or scheduled task. Do not double-click the `.py` file.

Syntax check:

```powershell
C:\ha-input-bridge\.venv\Scripts\python.exe -m py_compile C:\ha-input-bridge\ha_input_bridge.py
```

Scheduled task check:

```powershell
Get-ScheduledTask -TaskName "HA Input Bridge" | Select-Object TaskName, State
```

Listening port check:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen
```

## Privacy note

Avoid posting real tokens, public IP addresses, private hostnames, usernames, screenshots with secrets, or full logs containing sensitive values in public GitHub issues.

Private LAN IPs such as `192.168.x.x`, `10.x.x.x`, and `172.16.x.x` are not directly reachable from the public internet, but they can still reveal details about your local setup. Use placeholders when reporting issues.

## License

MIT

# Security Policy

## Supported versions

Security fixes are provided for the latest released version of HA Input Bridge.

| Version | Supported |
| ------- | --------- |
| latest | Yes |
| older versions | No |

Users should update to the latest release before reporting a security issue.

---

## Security model

HA Input Bridge is designed for trusted local-network use.

The Windows bridge accepts input commands from Home Assistant and converts them into mouse and keyboard actions on the Windows PC.

Security depends on:

- a private token
- Windows Firewall
- local network access
- a temporary arm window before input commands are accepted
- explicit mouse button release actions
- a release-all safety action for stuck mouse buttons

The token must be kept private.

Anyone who can reach the bridge over the network and has the token may be able to send input commands while the bridge is armed.

---

## Default network behavior

By default, the Windows bridge:

- binds to all local network adapters using `0.0.0.0`
- listens on TCP port `8765`
- creates a Windows Firewall rule
- limits firewall access to `LocalSubnet`
- requires the token on every request

Advanced users may restrict access further by setting the allowed Home Assistant IP address in the Windows tray settings.

---

## What not to expose

Do not expose HA Input Bridge directly to the public internet.

Do not port-forward the bridge port.

Do not share your token.

Do not include your token in:

- screenshots
- GitHub issues
- logs
- support requests
- release notes
- documentation examples
- public chats

If a token is exposed, regenerate it from the Windows tray settings:

```text
Right-click tray icon
→ Settings...
→ Regenerate Token
→ Save & Restart Bridge
→ Copy setup info
```

Then re-add or reconfigure the Home Assistant integration with the new setup info.

---

## Input safety

HA Input Bridge can control real mouse and keyboard input on the Windows PC.

Supported input actions include:

- mouse movement
- mouse click
- mouse down
- mouse up
- release all mouse buttons
- scroll
- text input
- key press
- hotkey

The bridge uses bounded values for mouse movement, scrolling, request size, and text length.

The bridge also requires a temporary arm window before most input actions are accepted.

Mouse release actions are intentionally available as safety actions so that stuck drag states can be recovered.

---

## Stuck mouse button recovery

If a mouse button appears stuck after a drag operation, use either recovery path.

From Home Assistant:

```text
Home Assistant trackpad
→ Quick keys
→ Release mouse
```

From Windows:

```text
Windows tray icon
→ Release stuck mouse buttons
```

This sends a release-all action for:

- left mouse button
- right mouse button
- middle mouse button

The release-all action still requires the private token.

---

## Reporting a vulnerability

Report security issues privately.

Do not open a public GitHub issue for vulnerabilities.

Send a private report to the repository maintainer.

Include:

- affected version
- operating system
- Home Assistant version
- clear reproduction steps
- expected impact
- whether the token, firewall, network boundary, or arm window is involved

Do not include real tokens. Use redacted examples.

Example:

```text
Token: <REDACTED>
Host: 192.168.1.50
Port: 8765
```

---

## Scope

Security reports may include:

- authentication bypass
- token leakage
- firewall rule weakness
- remote input without arming
- unexpected public network exposure
- unsafe installer behavior
- privilege escalation
- stuck mouse button state that cannot be recovered
- persistent process/resource abuse
- denial of service caused by malformed requests

Out of scope:

- issues requiring full local admin access to the Windows PC
- issues caused by intentionally exposing the bridge to the internet
- issues caused by sharing the token publicly
- unsupported old versions
- cosmetic UI issues

---

## Hardening notes

HA Input Bridge includes several defensive measures:

- token authentication
- temporary arm window
- Windows Firewall rule
- local subnet default firewall scope
- request body size limit
- bounded mouse movement values
- bounded scroll values
- bounded text input length
- explicit mouse down/up actions
- release-all mouse safety action
- tray panic action for stuck mouse buttons
- rotating log files
- frontend runtime cleanup
- Home Assistant config-entry runtime cleanup
- tray process single-instance handling
- settings process single-instance handling

These controls reduce risk but do not make the bridge safe to expose publicly.

---

## Recommended user configuration

Recommended normal setup:

```text
Bind address: 0.0.0.0
Allowed Home Assistant IP: empty
Firewall remote address: LocalSubnet
Port: 8765
```

Recommended stricter setup:

```text
Bind address: 0.0.0.0
Allowed Home Assistant IP: <your Home Assistant IP>
Firewall remote address: <your Home Assistant IP>
Port: 8765
```

Use the stricter setup if your local network has untrusted devices.

---

## Token rotation

Rotate the token if:

- it was pasted into a public chat
- it appeared in a screenshot
- it was committed to a repository
- another person had access to it
- you are moving the Windows PC to another network
- you are unsure whether it was exposed

After rotating the token, Home Assistant must be updated with the new setup info.

---

## Logs

The Windows bridge writes logs to:

```text
C:\ProgramData\HA Input Bridge
```

Important log files:

```text
ha_input_bridge.log
task_runtime.log
```

Logs are rotated to limit disk growth.

Logs should not contain the token.

When sharing logs, review and redact private network details if needed.

---

## Public internet warning

HA Input Bridge controls real mouse and keyboard input.

It should only be reachable from trusted local networks or trusted private overlays such as a properly secured VPN or Tailscale network.

Never expose the bridge directly to the internet.

---

## Release checklist for security-sensitive changes

Before publishing a release that changes input behavior, verify:

```text
1. Token authentication still works
2. Invalid token is rejected
3. Arm window is required for input actions
4. Mouse up works even after drag
5. Release all works from Home Assistant
6. Release stuck mouse buttons works from tray
7. Request body size limit still works
8. Movement limits still apply
9. Logs do not contain the token
10. Installer preserves or regenerates config safely
11. Windows Firewall rule is created correctly
12. Home Assistant services match services.yaml
13. README and SECURITY.md match the shipped behavior
```

# Security Policy

## Supported versions

Security fixes are provided for the latest released version of HA Input Bridge.

| Version | Supported |
| ------- | --------- |
| latest  | Yes       |
| older versions | No |

Users should update to the latest release before reporting a security issue.

---

## Security model

HA Input Bridge is designed for local-network use.

The Windows bridge accepts input commands from Home Assistant and converts them into mouse and keyboard actions on the Windows PC.

Security depends on:

- a private token
- Windows Firewall
- local network access
- a temporary arm window before input commands are accepted

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

If a token is exposed, regenerate it from the Windows tray settings:

```text
Right-click tray icon
→ Settings...
→ Regenerate Token
→ Save & Restart Bridge
→ Copy setup info

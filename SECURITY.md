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

The Windows bridge accepts authenticated input commands from Home Assistant and converts them into mouse and keyboard actions on the Windows PC.

Security depends on:

- a private token
- Windows Firewall
- trusted local network access
- a temporary arm window before most input commands are accepted
- playback cancellation when the Windows user manually moves the mouse
- explicit mouse button down/up actions
- a release-all safety action for stuck mouse buttons
- bounded request size
- bounded mouse, scroll, keyboard, and text input values
- local recorder storage
- explicit opt-in keyboard recording

The token must be kept private.

Anyone who can reach the bridge over the network and has the token may be able to send input commands while the bridge is armed.

Do not expose HA Input Bridge directly to the public internet.

---

## Default network behavior

By default, the Windows bridge:

- binds to all local network adapters using `0.0.0.0`
- listens on TCP port `8765`
- creates a Windows Firewall rule
- limits firewall access to `LocalSubnet`
- requires the token on every request

Advanced users may restrict access further by setting the Home Assistant IP address in the Windows Control Center.

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
Allowed Home Assistant IP: 192.168.x.x
Firewall remote address: 192.168.x.x
Port: 8765
```

Use the stricter setup if the local network contains untrusted devices.

---

## What not to expose

Do not expose HA Input Bridge directly to the public internet.

Do not port-forward the bridge port.

Do not share the token.

Do not include the token in:

- screenshots
- GitHub issues
- logs
- support requests
- release notes
- documentation examples
- public chats
- Home Assistant forum posts
- Discord messages
- Reddit posts

If a token is exposed, regenerate it from the Windows Control Center:

```text
Right-click tray icon → Open Control Center → Setup → Regenerate Token → Save & Restart Bridge → Copy Setup Info
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

The bridge uses bounded values for:

- absolute mouse coordinates
- relative mouse movement
- scroll amount
- text length
- request body size
- arm duration
- playback cancellation threshold
- playback cancellation grace period

The bridge requires a temporary arm window before most input actions are accepted.

Mouse release actions are intentionally available as safety actions so that stuck drag states can be recovered.

---

## Playback cancellation

HA Input Bridge supports Windows-side playback cancellation.

Default behavior:

1. Home Assistant arms the bridge.
2. A Home Assistant script or recorded YAML starts sending input commands.
3. The Windows agent tracks the expected mouse position.
4. If the Windows user physically moves the mouse outside the configured threshold, playback is cancelled.
5. The agent releases mouse buttons.
6. The next input command returns an error.
7. Home Assistant stops the remaining script sequence unless the user explicitly configured error continuation.

Default values:

```text
cancel_on_manual_mouse: true
manual_mouse_cancel_threshold_px: 8
manual_mouse_grace_ms: 250
```

The cancellation endpoint is:

```text
POST /cancel
```

The state endpoint is:

```text
GET /state
```

Cancellation can also be triggered from:

```text
Windows tray → Playback → Cancel active playback
```

or from Home Assistant:

```yaml
- action: ha_input_bridge.cancel
  data: {}
```

Do not add `continue_on_error: true` to recorder playback YAML unless you intentionally want the script to continue after cancellation or bridge errors.

---

## Stuck mouse button recovery

If a mouse button appears stuck after a drag operation, use either recovery path.

From Home Assistant:

```text
Home Assistant trackpad → Release mouse
```

From Windows:

```text
Windows tray icon → Playback → Release stuck mouse buttons
```

This sends a release-all action for:

- left mouse button
- right mouse button
- middle mouse button

The release-all action still requires the private token.

Generated recorder YAML ends with:

```yaml
- action: ha_input_bridge.release_all
  data: {}
```

This is intentional and should not be removed from recorded scripts.

---

## Script recorder safety

HA Input Bridge includes a local script recorder.

The recorder can generate Home Assistant script YAML from Windows input actions.

Recorder modes:

- mouse only
- mouse + keyboard

Mouse-only recording may capture:

- mouse coordinates
- clicks
- double clicks
- right clicks
- middle clicks
- scrolling
- drag actions
- timing delays
- virtual desktop bounds in comments

Mouse + keyboard recording may additionally capture:

- typed text
- hotkeys
- special keys
- keyboard timing

Keyboard recording is opt-in.

The app shows a warning before starting mouse + keyboard recording.

Do not use mouse + keyboard recording while typing:

- passwords
- API tokens
- recovery codes
- private messages
- emails
- personal information
- financial information
- anything you would not want stored in YAML

Generated YAML must be reviewed before use or sharing.

---

## Recorder storage

Recordings are stored locally on the Windows PC:

```text
C:\ProgramData\HA Input Bridge\recordings
```

Recordings are not automatically uploaded.

Recordings are not automatically sent to Home Assistant.

The user must manually copy or paste the generated YAML into Home Assistant.

Recorder output does not intentionally include:

- HA Input Bridge token
- bridge host
- bridge port
- Windows credentials

Recorder output may include:

- screen coordinates
- clicked positions
- typed text
- hotkeys
- timing delays
- virtual desktop bounds in comments

Delete recordings that contain sensitive text.

Do not upload recordings to public GitHub issues unless they have been reviewed and redacted.

---

## Generated YAML risk

Generated YAML can replay real mouse and keyboard actions on the Windows PC.

Before running generated YAML in Home Assistant, review it for:

- wrong coordinates
- unwanted clicks
- sensitive typed text
- destructive hotkeys
- excessive delays
- accidental drag operations
- accidental file or window interactions
- unexpected scroll amounts
- unsupported characters warning comments

Coordinates depend on the Windows display layout.

If monitor order, resolution, scaling, primary display, browser zoom, or page scroll state changes, recorded coordinates may no longer match the intended target.

For browser and app automations, record from a known starting state.

Example:

```text
browser opened
page loaded
zoom unchanged
scroll at top
same monitor layout
same window position
```

---

## Recorder YAML text safety

The recorder sanitizes text before writing YAML.

The recorder skips unsupported text characters instead of writing invisible or invalid characters into YAML.

Text is escaped in YAML-safe form.

Example:

```yaml
text: "caf\u00e9"
```

If unsupported characters were skipped, the generated YAML includes a warning comment:

```yaml
# Recorder warning: skipped 2 unsupported text character(s).
```

This prevents invisible/control/unsupported characters from breaking Home Assistant YAML parsing.

Unsupported skipped input may include:

- control characters
- invisible characters
- unsupported dead-key artifacts
- unsupported surrogate characters
- unsupported non-BMP characters
- unknown keyboard events

Do not assume keyboard recording preserves every international keyboard layout or IME behavior perfectly.

Review generated text before running it.

---

## Recorder scroll behavior

The recorder combines nearby mouse wheel events into scroll bursts.

This is intentional.

Live mouse wheel input often produces many small wheel events. Replaying those as many tiny Home Assistant actions is slow and can cause later clicks to land in the wrong place.

Expected recorder output may contain large scroll values:

```yaml
- action: ha_input_bridge.scroll
  data:
    amount: -520
```

Scroll values are bounded.

Current range:

```text
-2000 to 2000
```

Review scroll actions before running generated YAML.

Large scroll values can move a page or app further than expected if the starting scroll position is different from the recording session.

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

When sharing logs, review and redact:

- private IP addresses if needed
- usernames if present
- local paths if sensitive
- any accidental tokens or secrets

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

Token rotation path:

```text
Right-click tray icon → Open Control Center → Setup → Regenerate Token → Save & Restart Bridge → Copy Setup Info
```

Then update Home Assistant with the new token.

---

## Public internet warning

HA Input Bridge controls real mouse and keyboard input.

It should only be reachable from trusted local networks or trusted private overlays such as a properly secured VPN or Tailscale network.

Never expose the bridge directly to the internet.

Do not use router port forwarding for HA Input Bridge.

Do not place HA Input Bridge behind a public reverse proxy.

Do not publish the bridge token.

---

## Reporting a vulnerability

Report security issues privately.

Do not open a public GitHub issue for vulnerabilities.

Send a private report to the repository maintainer.

Include:

- affected version
- operating system
- Home Assistant version
- Windows installer version
- clear reproduction steps
- expected impact
- whether the token, firewall, network boundary, arm window, playback cancellation, or recorder is involved

Do not include real tokens.

Use redacted examples.

Example:

```text
Token: [redacted]
Host: 192.168.1.50
Port: 8765
```

If the issue involves recorder output, redact:

- passwords
- tokens
- private text
- personal information
- exact private paths if needed

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
- playback cancellation failing to stop input
- release-all failing after cancellation
- persistent process/resource abuse
- denial of service caused by malformed requests
- recorder storing token or host data unexpectedly
- recorder capturing keyboard input without explicit user action
- recorder failing to warn before keyboard capture
- generated YAML containing unintended sensitive bridge configuration
- generated YAML containing raw invalid control characters
- recorder output causing unintended input due to incorrect event conversion

Out of scope:

- issues requiring full local admin access to the Windows PC
- issues caused by intentionally exposing the bridge to the internet
- issues caused by sharing the token publicly
- issues caused by intentionally recording private text
- issues caused by running generated YAML without review
- issues caused by changing monitor layout after recording
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
- playback cancellation on manual mouse intervention
- explicit mouse down/up actions
- release-all mouse safety action
- tray panic action for stuck mouse buttons
- cancellation endpoint
- state endpoint
- rotating log files
- frontend runtime cleanup
- Home Assistant config-entry runtime cleanup
- tray process single-instance handling
- settings/control center process single-instance handling
- coordinate viewer single-instance handling
- recorder window single-instance handling
- recorder warning before keyboard capture
- recorder YAML text sanitizing
- recorder scroll-burst coalescing
- recorder local-only YAML storage
- generated YAML excludes bridge token and host configuration
- generated YAML ends with `release_all`

These controls reduce risk but do not make the bridge safe to expose publicly.

---

## Release checklist for security-sensitive changes

Before publishing a release that changes input, recorder, installer, network, or Home Assistant service behavior, verify:

```text
1. Token authentication still works
2. Invalid token is rejected
3. Arm window is required for input actions
4. Mouse up works after drag
5. Release all works from Home Assistant
6. Release stuck mouse buttons works from tray
7. Cancel active playback works from tray
8. Cancel action works from Home Assistant
9. Manual physical mouse movement cancels active playback
10. Cancelled playback releases mouse buttons
11. Cancelled playback causes Home Assistant script sequence to stop
12. Request body size limit still works
13. Movement limits still apply
14. Scroll limits still apply
15. Text length limits still apply
16. Logs do not contain the token
17. Installer preserves or regenerates config safely
18. Installer writes playback safety config defaults
19. Windows Firewall rule is created correctly
20. Home Assistant services match services.yaml
21. Home Assistant arm supports cancellation parameters
22. Home Assistant state service returns playback state
23. Home Assistant cancel service cancels playback
24. Recorder mouse-only mode works
25. Recorder mouse + keyboard mode shows a warning
26. Recorder output does not contain token, host, or port
27. Recorder output is saved locally only
28. Recorder output ends with release_all
29. Recorder does not silently start keyboard capture
30. Recorder YAML text is sanitized
31. Recorder YAML does not contain raw invalid control characters
32. Recorder scroll events are coalesced into scroll bursts
33. Generated YAML runs in Home Assistant
34. Generated YAML stops when the user manually moves the mouse
35. Trackpad Cancel playback button works
36. Trackpad Release mouse button works
37. README and SECURITY.md match the shipped behavior
```

---

## Version-specific note for v0.9.1

v0.9.1 adds safety and reliability changes:

- playback cancellation when the Windows user physically moves the mouse
- `/state` endpoint
- `/cancel` endpoint
- Home Assistant `ha_input_bridge.state`
- Home Assistant `ha_input_bridge.cancel`
- configurable manual mouse cancellation threshold
- configurable manual mouse grace period
- stronger scroll range for recorded playback
- recorder scroll-burst coalescing
- recorder YAML text sanitizing
- Windows Control Center Playback Safety tab

Users of older versions should update if they rely on recorder playback, scroll playback, or safe interruption of running Home Assistant scripts.
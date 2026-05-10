# HA Input Bridge

HA Input Bridge lets Home Assistant control mouse and keyboard input on a Windows PC.

The goal is simple:

1. Install the Windows app.
2. Copy setup info from the Windows tray icon.
3. Paste that setup info into Home Assistant.
4. Use the Home Assistant trackpad to control the Windows PC.

Normal users do **not** need Python, PowerShell, config files, IP knowledge, or manual token editing.

---

## What HA Input Bridge does

HA Input Bridge has two parts:

### 1. Windows app

The Windows app runs in the background on your PC.

It receives secure input commands from Home Assistant and turns them into:

- mouse movement
- left/right/middle click
- scrolling
- typing text
- keyboard shortcuts

The Windows app also adds a tray icon so you can:

- see if the bridge is running
- start or stop the bridge
- copy setup info
- open settings
- open logs
- uninstall the app

### 2. Home Assistant integration

The Home Assistant integration connects to the Windows app.

After setup, Home Assistant can send commands to the Windows PC.

---

## Security model

HA Input Bridge is local-network focused.

It uses:

- a private token
- Windows Firewall
- an arm window before input commands are accepted

The token is required for Home Assistant to connect.

The bridge also requires Home Assistant to arm it before actual input commands are accepted.

Keep the token private.

---

# Installation tutorial

Follow these steps in order.

---

# Part 1 — Install the Windows app

## Step 1 — Download the Windows installer

Go to the latest GitHub Release and download:

```text
HA-Input-Bridge-Setup.exe
```

This is the Windows installer.

Do not download the source code ZIP unless you are developing the app.

---

## Step 2 — Run the installer

Double-click:

```text
HA-Input-Bridge-Setup.exe
```

Windows may ask for permission.

Click:

```text
Yes
```

Continue through the installer.

The installer automatically:

- installs the bridge agent
- installs the tray app
- creates the config file
- generates a private token
- creates the Windows scheduled task
- creates the Windows Firewall rule
- starts the bridge
- starts the tray icon

You do not need to enter an IP address during installation.

---

## Step 3 — Find the tray icon

After installation, look at the Windows system tray.

It is usually in the bottom-right corner of the screen.

You may need to click the small arrow to show hidden tray icons.

Look for:

```text
HA Input Bridge
```

Right-click the tray icon.

You should see menu items like:

```text
Status: running
Settings...
Copy setup info
Start bridge
Stop bridge
Restart bridge
Open connection info
Open logs folder
Open install folder
Uninstall HA Input Bridge
Exit tray icon
```

---

## Step 4 — Check that the bridge is running

Right-click the tray icon.

The menu should show:

```text
Status: running
```

You can also open:

```text
Settings...
```

The Basic tab should show:

```text
Status: running
Windows bridge host: 192.168.x.x
Port: 8765
Listening mode: Automatic - all local network adapters
```

The exact IP address will depend on your Windows PC.

Example:

```text
Windows bridge host: 192.168.2.2
Other host values: 100.98.112.92
Port: 8765
```

Usually:

- `192.168.x.x` is your normal local network address
- `100.x.x.x` is usually a Tailscale address

For most users, use the `192.168.x.x` value.

---

## Step 5 — Copy setup info

Right-click the tray icon and click:

```text
Copy setup info
```

This copies the Windows connection details to your clipboard.

It looks like this:

```text
HA Input Bridge
Host: 192.168.2.2
Port: 8765
Token: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

You will paste this into Home Assistant later.

---

# Part 2 — Install the Home Assistant integration

## Step 1 — Install through HACS

Open Home Assistant.

Go to:

```text
HACS
→ Integrations
```

Search for:

```text
HA Input Bridge
```

Install the integration.

After installation, restart Home Assistant if HACS asks you to restart.

---

## Step 2 — Add the integration

In Home Assistant, go to:

```text
Settings
→ Devices & services
→ Add integration
```

Search for:

```text
HA Input Bridge
```

Click it.

---

## Step 3 — Paste the Windows setup info

Home Assistant will show a setup form.

Paste the setup info copied from the Windows tray icon.

Example:

```text
HA Input Bridge
Host: 192.168.2.2
Port: 8765
Token: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Click:

```text
Submit
```

Home Assistant will test the connection.

If the Windows bridge is running and the token is correct, setup will complete.

---

# Part 3 — Test the trackpad

After the integration is added, open the HA Input Bridge trackpad in Home Assistant.

Move your finger or mouse over the trackpad.

The Windows mouse cursor should move.

Test:

- movement
- click
- scroll
- keyboard input if available

If the cursor moves, setup is complete.

---

# Daily use

After setup, normal use is simple:

1. Windows starts.
2. HA Input Bridge starts automatically.
3. Home Assistant connects to it.
4. You use the Home Assistant trackpad.

You do not need to open PowerShell or manually start anything.

---

# Windows tray app

The tray icon is the control center for the Windows side.

Right-click the tray icon to access:

```text
Settings...
Copy setup info
Start bridge
Stop bridge
Restart bridge
Open connection info
Open logs folder
Open install folder
Uninstall HA Input Bridge
Exit tray icon
```

---

## Settings — Basic tab

The Basic tab is for normal users.

It shows:

- bridge status
- Windows bridge host
- alternative host values
- port
- token
- start bridge on Windows login
- start tray icon on Windows login

The token is hidden by default.

Click:

```text
Show
```

to reveal it.

Click:

```text
Hide
```

to hide it again.

---

## Settings — Advanced tab

The Advanced tab is for network troubleshooting.

It contains:

```text
Bind address
Allowed Home Assistant IP
Bridge port
```

Default values:

```text
Bind address: 0.0.0.0
Allowed Home Assistant IP: empty
Bridge port: 8765
```

Meaning:

```text
0.0.0.0
```

means the bridge listens on all local network adapters.

Leaving:

```text
Allowed Home Assistant IP
```

empty allows the local subnet through Windows Firewall.

That is easier for normal users.

For stricter security, enter the Home Assistant IP address.

Example:

```text
192.168.2.13
```

Then only that Home Assistant IP is allowed through the firewall.

---

# Which host should I use?

The Windows app chooses the best host automatically.

It prefers normal LAN addresses first.

Priority:

```text
1. 192.168.x.x
2. 10.x.x.x
3. 172.16.x.x - 172.31.x.x
4. 100.64.x.x - 100.127.x.x
5. other IPv4 addresses
```

Example:

```text
Windows bridge host: 192.168.2.2
Other host values: 100.98.112.92
```

Use:

```text
192.168.2.2
```

for normal local network use.

Use:

```text
100.98.112.92
```

only if Home Assistant reaches the Windows PC through Tailscale.

Most users should not need to choose manually. Use **Copy setup info**.

---

# Updating

To update HA Input Bridge:

1. Download the newest `HA-Input-Bridge-Setup.exe`.
2. Run it.
3. Install over the old version.

The installer keeps existing settings where possible:

- token
- port
- startup settings
- firewall settings

After updating, the bridge and tray app restart.

You normally do not need to re-add the Home Assistant integration after an update.

---

# Changing the token

To generate a new token:

1. Right-click the Windows tray icon.
2. Click `Settings...`.
3. Click `Regenerate Token`.
4. Click `Save & Restart Bridge`.
5. Click `Copy Setup Info`.
6. Reconfigure or re-add the integration in Home Assistant using the new setup info.

Generate a new token if:

- the token was shared accidentally
- you posted screenshots showing the token
- you want to reset access

---

# Uninstalling

You can uninstall from Windows:

```text
Windows Settings
→ Apps
→ HA Input Bridge
→ Uninstall
```

Or from the tray icon:

```text
Right-click tray icon
→ Uninstall HA Input Bridge
```

The uninstaller removes:

- bridge agent
- tray app
- scheduled task
- firewall rule
- startup shortcut
- config folder
- log folder

After uninstalling, Home Assistant can no longer connect to the Windows PC.

You can also remove the integration from Home Assistant:

```text
Settings
→ Devices & services
→ HA Input Bridge
→ Delete
```

---

# Troubleshooting

## Home Assistant cannot connect

On Windows:

```text
Right-click tray icon
→ Settings...
```

Check:

```text
Status: running
```

Then click:

```text
Copy setup info
```

In Home Assistant, remove and re-add the integration using the copied setup info.

---

## The wrong host is shown

Open:

```text
Right-click tray icon
→ Settings...
```

Check the Basic tab.

Usually the correct host is:

```text
192.168.x.x
```

If the shown host is a `100.x.x.x` address, that is probably Tailscale.

Use the local network host unless Home Assistant connects over Tailscale.

---

## Trackpad does not move the mouse

Check:

1. Windows bridge status is `running`.
2. Home Assistant integration is connected.
3. Setup info was copied from the current Windows installation.
4. Token matches.
5. Windows Firewall allows the local subnet or Home Assistant IP.
6. Home Assistant and Windows are on the same network.

---

## Tray icon is missing

Check hidden tray icons first.

If it is not there:

```text
Start Menu
→ HA Input Bridge
→ HA Input Bridge Tray
```

If the bridge is still running, only the tray icon may be closed.

---

## Bridge is stopped

Right-click the tray icon and click:

```text
Start bridge
```

Or open Settings and check:

```text
Start bridge on Windows login
```

---

## Logs

Open logs from the tray icon:

```text
Right-click tray icon
→ Open logs folder
```

Important files:

```text
ha_input_bridge.log
task_runtime.log
```

---

# Developer notes

Windows app source:

```text
windows/
```

Home Assistant integration source:

```text
custom_components/ha_input_bridge/
```

Windows installer source:

```text
windows/installer/
```

The Windows installer is built with GitHub Actions.

---

# Release checklist

Before publishing a release:

```text
1. Windows installer workflow is green
2. Fresh Windows install works
3. Tray process count is correct
4. Copy setup info works
5. Home Assistant setup accepts pasted setup info
6. Trackpad works
7. README is updated
8. Tag is created
9. GitHub Release includes the Windows installer
```

---

# License

MIT

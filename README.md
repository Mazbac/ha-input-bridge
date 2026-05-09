# HA Input Bridge

Home Assistant custom integration for controlling a Windows PC through HA Input Bridge.

This integration exposes Home Assistant services for mouse movement, mouse clicks, scrolling, keyboard input, and hotkeys. It is designed to work with the PC Trackpad Card and a Windows bridge agent running on the target PC.

## Status

Experimental.

This project is still being built. The Home Assistant integration is usable for testing, but the Windows installer and polished setup flow are still planned.

## Architecture

```text
Home Assistant
→ HA Input Bridge integration
→ Windows HA Input Bridge agent
→ Windows mouse and keyboard input

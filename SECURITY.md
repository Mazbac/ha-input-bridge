# Security Policy

HA Input Bridge controls mouse and keyboard input on a Windows PC.

Treat this project as sensitive remote-control software.

## Supported versions

This project is experimental. Security fixes are handled on the latest `main` branch until versioned releases are established.

## Security model

HA Input Bridge is designed for local/private networks only.

The Windows bridge should be protected by:

- A strong random token
- Binding only to a LAN or VPN/Tailscale IP
- Windows Firewall restricted to the Home Assistant IP
- Home Assistant integration config stored locally
- Arm-before-input behavior
- No public internet exposure

## Do not expose this bridge publicly

Do not:

- Port-forward the bridge
- Put it behind a public reverse proxy
- Expose it through Cloudflare Tunnel
- Expose it through Nabu Casa remote access
- Share the token
- Use it on untrusted Wi-Fi
- Use it where other network clients are not trusted

## Sensitive information

Do not post the following in public issues:

- Bridge token
- Full logs containing tokens
- Public IP addresses
- Private hostnames
- Screenshots showing secrets
- Personal usernames
- Full local network diagrams

Private LAN IPs such as `192.168.x.x`, `10.x.x.x`, and `172.16.x.x` are not directly reachable from the public internet, but they can still reveal setup details. Prefer placeholders.

## Reporting a vulnerability

Open a private security advisory on GitHub if available.

If private advisory reporting is not available, open a minimal public issue without secrets and say that you need a private channel for security details.

## Log handling

The Windows bridge should not log typed text.

Logs may include:

- Source IP
- Command type
- Mouse movement
- Mouse button
- Keyboard key names

Logs should not include:

- Tokens
- Full text payloads
- Passwords
- Personal data

## Token rotation

If a token is exposed:

1. Stop the Windows bridge.
2. Generate a new token.
3. Update the Windows start script.
4. Update the Home Assistant integration config.
5. Restart the Windows bridge.
6. Remove exposed logs or screenshots.

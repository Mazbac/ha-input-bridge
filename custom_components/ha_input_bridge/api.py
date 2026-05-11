"""API client for HA Input Bridge."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession
from async_timeout import timeout


class HAInputBridgeError(Exception):
    """Base exception for HA Input Bridge errors."""


class CannotConnect(HAInputBridgeError):
    """Raised when the bridge cannot be reached."""


class InvalidAuth(HAInputBridgeError):
    """Raised when the bridge rejects the token."""


class BridgeApiError(HAInputBridgeError):
    """Raised when the bridge returns an unexpected error."""


class HAInputBridgeClient:
    """Client for the Windows HA Input Bridge HTTP API."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        port: int,
        token: str,
        timeout_seconds: int = 5,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._host = host.strip()
        self._port = int(port)
        self._token = token.strip()
        self._timeout_seconds = int(timeout_seconds)

        if self._host.startswith(("http://", "https://")):
            self._base_url = self._host.rstrip("/")
        else:
            self._base_url = f"http://{self._host}:{self._port}"

    @property
    def base_url(self) -> str:
        """Return the bridge base URL."""
        return self._base_url

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request."""
        url = f"{self._base_url}{path}"
        headers = {
            "X-HA-Token": self._token,
        }

        try:
            async with timeout(self._timeout_seconds):
                async with self._session.request(
                    method,
                    url,
                    headers=headers,
                    json=json_data,
                ) as response:
                    if response.status == 403:
                        raise InvalidAuth("Invalid HA Input Bridge token")

                    if response.status >= 400:
                        text = await response.text()
                        raise BridgeApiError(
                            f"Bridge returned HTTP {response.status}: {text}"
                        )

                    data = await response.json(content_type=None)

        except InvalidAuth:
            raise
        except BridgeApiError:
            raise
        except (ClientError, ClientResponseError, TimeoutError) as err:
            raise CannotConnect(f"Cannot connect to HA Input Bridge: {err}") from err

        if not isinstance(data, dict):
            raise BridgeApiError("Bridge returned a non-object JSON response")

        return data

    async def health(self) -> dict[str, Any]:
        """Check bridge health."""
        return await self._request("GET", "/health")

    async def position(self) -> dict[str, Any]:
        """Get current mouse position and screen size."""
        return await self._request("GET", "/position")

    async def arm(self, seconds: int = 30) -> dict[str, Any]:
        """Arm the bridge temporarily."""
        return await self._request(
            "POST",
            "/arm",
            {
                "seconds": int(seconds),
            },
        )

    async def input(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a raw input payload."""
        return await self._request("POST", "/input", payload)

    async def move(self, x: int, y: int) -> dict[str, Any]:
        """Move mouse to absolute coordinates."""
        return await self.input(
            {
                "type": "mouse",
                "action": "move",
                "x": int(x),
                "y": int(y),
            }
        )

    async def move_relative(self, dx: int, dy: int) -> dict[str, Any]:
        """Move mouse relative to current position."""
        return await self.input(
            {
                "type": "mouse",
                "action": "move_relative",
                "dx": int(dx),
                "dy": int(dy),
            }
        )

    async def click(self, button: str = "left", clicks: int = 1) -> dict[str, Any]:
        """Click at the current mouse position."""
        return await self.input(
            {
                "type": "mouse",
                "action": "click",
                "button": str(button),
                "clicks": int(clicks),
            }
        )

    async def scroll(self, amount: int) -> dict[str, Any]:
        """Scroll at the current mouse position."""
        return await self.input(
            {
                "type": "mouse",
                "action": "scroll",
                "amount": int(amount),
            }
        )

    async def write(self, text: str, interval: float = 0) -> dict[str, Any]:
        """Write text to the active window."""
        return await self.input(
            {
                "type": "keyboard",
                "action": "write",
                "text": str(text),
                "interval": float(interval),
            }
        )

    async def press(self, key: str) -> dict[str, Any]:
        """Press a keyboard key."""
        return await self.input(
            {
                "type": "keyboard",
                "action": "press",
                "key": str(key),
            }
        )

    async def hotkey(self, keys: list[str]) -> dict[str, Any]:
        """Press a keyboard hotkey."""
        return await self.input(
            {
                "type": "keyboard",
                "action": "hotkey",
                "keys": [str(key) for key in keys],
            }
        )

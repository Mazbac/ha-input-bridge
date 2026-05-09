"""Home Assistant integration for HA Input Bridge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import BridgeApiError, CannotConnect, HAInputBridgeClient, InvalidAuth
from .const import DEFAULT_TIMEOUT, DOMAIN


SERVICE_ARM = "arm"
SERVICE_POSITION = "position"
SERVICE_MOVE = "move"
SERVICE_MOVE_RELATIVE = "move_relative"
SERVICE_CLICK = "click"
SERVICE_SCROLL = "scroll"
SERVICE_WRITE = "write"
SERVICE_PRESS = "press"
SERVICE_HOTKEY = "hotkey"

CARD_URL_PATH = "/ha_input_bridge/pc-trackpad-card.js"
CARD_FILE = Path(__file__).parent / "www" / "pc-trackpad-card.js"


SERVICE_ARM_SCHEMA = vol.Schema(
    {
        vol.Optional("seconds", default=30): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=120),
        ),
    }
)

SERVICE_POSITION_SCHEMA = vol.Schema({})

SERVICE_MOVE_SCHEMA = vol.Schema(
    {
        vol.Required("x"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10000)),
        vol.Required("y"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10000)),
    }
)

SERVICE_MOVE_RELATIVE_SCHEMA = vol.Schema(
    {
        vol.Required("dx"): vol.All(vol.Coerce(int), vol.Range(min=-300, max=300)),
        vol.Required("dy"): vol.All(vol.Coerce(int), vol.Range(min=-300, max=300)),
    }
)

SERVICE_CLICK_SCHEMA = vol.Schema(
    {
        vol.Optional("button", default="left"): vol.In(["left", "right", "middle"]),
        vol.Optional("clicks", default=1): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=3),
        ),
    }
)

SERVICE_SCROLL_SCHEMA = vol.Schema(
    {
        vol.Required("amount"): vol.All(vol.Coerce(int), vol.Range(min=-80, max=80)),
    }
)

SERVICE_WRITE_SCHEMA = vol.Schema(
    {
        vol.Required("text"): cv.string,
        vol.Optional("interval", default=0): vol.All(
            vol.Coerce(float),
            vol.Range(min=0, max=1),
        ),
    }
)

SERVICE_PRESS_SCHEMA = vol.Schema(
    {
        vol.Required("key"): cv.string,
    }
)

SERVICE_HOTKEY_SCHEMA = vol.Schema(
    {
        vol.Required("keys"): vol.All(
            cv.ensure_list,
            [cv.string],
            vol.Length(min=1, max=8),
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up HA Input Bridge services and bundled frontend card."""
    hass.data.setdefault(DOMAIN, {})

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                CARD_URL_PATH,
                str(CARD_FILE),
                True,
            )
        ]
    )

    async def get_client() -> HAInputBridgeClient:
        """Return the first loaded bridge client."""
        entries = hass.data.get(DOMAIN, {})

        if not entries:
            raise ServiceValidationError("No HA Input Bridge instance is configured")

        first_entry = next(iter(entries.values()))
        client = first_entry.get("client")

        if client is None:
            raise ServiceValidationError("HA Input Bridge instance is not loaded")

        return client

    async def call_bridge(method_name: str, *args: Any) -> dict[str, Any]:
        """Call a bridge API method and convert errors for Home Assistant."""
        client = await get_client()
        method = getattr(client, method_name)

        try:
            return await method(*args)
        except InvalidAuth as err:
            raise HomeAssistantError("Invalid HA Input Bridge token") from err
        except CannotConnect as err:
            raise HomeAssistantError("Cannot connect to HA Input Bridge") from err
        except BridgeApiError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_arm(call: ServiceCall) -> None:
        """Handle arm service."""
        await call_bridge("arm", call.data["seconds"])

    async def handle_position(call: ServiceCall) -> ServiceResponse:
        """Handle position service."""
        return await call_bridge("position")

    async def handle_move(call: ServiceCall) -> None:
        """Handle absolute mouse move service."""
        await call_bridge("move", call.data["x"], call.data["y"])

    async def handle_move_relative(call: ServiceCall) -> None:
        """Handle relative mouse move service."""
        await call_bridge("move_relative", call.data["dx"], call.data["dy"])

    async def handle_click(call: ServiceCall) -> None:
        """Handle click service."""
        await call_bridge("click", call.data["button"], call.data["clicks"])

    async def handle_scroll(call: ServiceCall) -> None:
        """Handle scroll service."""
        await call_bridge("scroll", call.data["amount"])

    async def handle_write(call: ServiceCall) -> None:
        """Handle write service."""
        await call_bridge("write", call.data["text"], call.data["interval"])

    async def handle_press(call: ServiceCall) -> None:
        """Handle press service."""
        await call_bridge("press", call.data["key"])

    async def handle_hotkey(call: ServiceCall) -> None:
        """Handle hotkey service."""
        await call_bridge("hotkey", call.data["keys"])

    hass.services.async_register(
        DOMAIN,
        SERVICE_ARM,
        handle_arm,
        schema=SERVICE_ARM_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_POSITION,
        handle_position,
        schema=SERVICE_POSITION_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_MOVE,
        handle_move,
        schema=SERVICE_MOVE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_MOVE_RELATIVE,
        handle_move_relative,
        schema=SERVICE_MOVE_RELATIVE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLICK,
        handle_click,
        schema=SERVICE_CLICK_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SCROLL,
        handle_scroll,
        schema=SERVICE_SCROLL_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_WRITE,
        handle_write,
        schema=SERVICE_WRITE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_PRESS,
        handle_press,
        schema=SERVICE_PRESS_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_HOTKEY,
        handle_hotkey,
        schema=SERVICE_HOTKEY_SCHEMA,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Input Bridge from a config entry."""
    session = async_get_clientsession(hass)

    client = HAInputBridgeClient(
        session=session,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        token=entry.data[CONF_TOKEN],
        timeout_seconds=DEFAULT_TIMEOUT,
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "entry": entry,
        "client": client,
    }

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload HA Input Bridge config entry."""
    hass.data[DOMAIN].pop(entry.entry_id, None)

    return True

"""Config flow for HA Input Bridge."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_TOKEN
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CannotConnect, HAInputBridgeClient, InvalidAuth
from .const import DEFAULT_NAME, DEFAULT_PORT, DEFAULT_TIMEOUT, DOMAIN

CONF_SETUP_INFO = "setup_info"
MAX_SETUP_INFO_LENGTH = 2000


def parse_setup_info(setup_info: str) -> dict[str, Any]:
    """Parse setup info copied from the Windows tray app."""
    text = setup_info.strip()[:MAX_SETUP_INFO_LENGTH]

    host = ""
    port = DEFAULT_PORT
    token = ""

    host_match = re.search(r"^Host:\s*(.+?)\s*$", text, re.MULTILINE | re.IGNORECASE)
    port_match = re.search(r"^Port:\s*(\d+)\s*$", text, re.MULTILINE | re.IGNORECASE)
    token_match = re.search(r"^Token:\s*(.+?)\s*$", text, re.MULTILINE | re.IGNORECASE)

    if host_match:
        host = host_match.group(1).strip()

    if port_match:
        port = int(port_match.group(1).strip())

    if token_match:
        token = token_match.group(1).strip()

    if not host and text and "\n" not in text and ":" not in text:
        host = text

    return {
        CONF_HOST: host,
        CONF_PORT: port,
        CONF_TOKEN: token,
    }


class HAInputBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Input Bridge."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME].strip() or DEFAULT_NAME
            setup_info = user_input[CONF_SETUP_INFO].strip()

            if len(setup_info) > MAX_SETUP_INFO_LENGTH:
                errors["base"] = "setup_info_too_long"
            else:
                parsed = parse_setup_info(setup_info)

                host = str(parsed[CONF_HOST]).strip()
                port = int(parsed[CONF_PORT])
                token = str(parsed[CONF_TOKEN]).strip()

                if not host:
                    errors["base"] = "missing_host"
                elif not token:
                    errors["base"] = "missing_token"
                elif port < 1 or port > 65535:
                    errors["base"] = "invalid_port"
                else:
                    await self.async_set_unique_id(f"{host}:{port}")
                    self._abort_if_unique_id_configured()

                    session = async_get_clientsession(self.hass)
                    client = HAInputBridgeClient(
                        session=session,
                        host=host,
                        port=port,
                        token=token,
                        timeout_seconds=DEFAULT_TIMEOUT,
                    )

                    try:
                        await client.health()
                    except CannotConnect:
                        errors["base"] = "cannot_connect"
                    except InvalidAuth:
                        errors["base"] = "invalid_auth"
                    except Exception:
                        errors["base"] = "unknown"
                    else:
                        return self.async_create_entry(
                            title=name,
                            data={
                                CONF_NAME: name,
                                CONF_HOST: host,
                                CONF_PORT: port,
                                CONF_TOKEN: token,
                            },
                        )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_SETUP_INFO): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

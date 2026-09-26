"""Config flow for Postown SmartWeb integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_TYPE,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    DEVICE_TYPE_LIGHT,
    DEVICE_TYPE_HEATER,
)
from .hub import CannotConnect, InvalidAuth, SmartWebHub, normalize_host

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPES = {
    DEVICE_TYPE_LIGHT: "조명 (Light)",
    DEVICE_TYPE_HEATER: "난방 (Heater)",
}


async def _async_validate_connection(
    hass: HomeAssistant, host: str, username: str, password: str
) -> str | None:
    """Try to log in and return an error key, or None on success."""
    if not host.startswith(("http://", "https://")):
        return "invalid_host"

    hub = SmartWebHub(host, username, password)
    try:
        await hass.async_add_executor_job(hub.authenticate)
    except CannotConnect:
        return "cannot_connect"
    except InvalidAuth:
        return "invalid_auth"
    except Exception:
        _LOGGER.exception("Unexpected error during connection test")
        return "unknown"
    finally:
        hub.close()
    return None


def _device_key(device: dict) -> str:
    """Return a key that uniquely identifies a configured device."""
    return f"{device[CONF_DEVICE_TYPE]}_{device[CONF_DEVICE_ID]}"


def _validate_device(
    user_input: dict[str, Any], devices: list[dict]
) -> tuple[dict, str | None]:
    """Build a device from user input and return it with an error key, if any."""
    device = {
        CONF_DEVICE_NAME: user_input[CONF_DEVICE_NAME].strip(),
        CONF_DEVICE_TYPE: user_input[CONF_DEVICE_TYPE],
        CONF_DEVICE_ID: user_input[CONF_DEVICE_ID].strip(),
    }
    if not device[CONF_DEVICE_ID].isdigit():
        return device, "invalid_device_id"
    if any(_device_key(d) == _device_key(device) for d in devices):
        return device, "device_exists"
    return device, None


class PostownSmartWebConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Postown SmartWeb."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._host: str = ""
        self._username: str = ""
        self._password: str = ""
        self._devices: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - connection setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = normalize_host(user_input[CONF_HOST])
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            error = await _async_validate_connection(
                self.hass, self._host, self._username, self._password
            )
            if error is None:
                await self.async_set_unique_id(f"{DOMAIN}_{self._host}")
                self._abort_if_unique_id_configured()
                return await self.async_step_add_device()
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default="http://"): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
            description_placeholders={
                "host_example": "http://sdexpo9.postown.net",
            },
        )

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle adding a device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device, error = _validate_device(user_input, self._devices)
            if error:
                errors["base"] = error
            else:
                self._devices.append(device)

                if not user_input.get("add_another", False):
                    return self.async_create_entry(
                        title=f"Postown SmartWeb ({self._host})",
                        data={
                            CONF_HOST: self._host,
                            CONF_USERNAME: self._username,
                            CONF_PASSWORD: self._password,
                            CONF_DEVICES: self._devices,
                        },
                    )

        return self.async_show_form(
            step_id="add_device",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_NAME): str,
                vol.Required(CONF_DEVICE_TYPE): vol.In(DEVICE_TYPES),
                vol.Required(CONF_DEVICE_ID): str,
                vol.Optional("add_another", default=False): bool,
            }),
            errors=errors,
            description_placeholders={
                "device_count": str(len(self._devices)),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> PostownSmartWebOptionsFlow:
        """Get the options flow for this handler."""
        return PostownSmartWebOptionsFlow(config_entry)


class PostownSmartWebOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Postown SmartWeb."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._devices: list[dict] = list(config_entry.data.get(CONF_DEVICES, []))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_device", "remove_device", "edit_credentials"],
        )

    def _save_devices(self) -> FlowResult:
        """Store the device list in the config entry and finish the flow."""
        new_data = dict(self._config_entry.data)
        new_data[CONF_DEVICES] = self._devices

        self.hass.config_entries.async_update_entry(
            self._config_entry, data=new_data
        )

        return self.async_create_entry(title="", data={})

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device, error = _validate_device(user_input, self._devices)
            if error:
                errors["base"] = error
            else:
                self._devices.append(device)
                return self._save_devices()

        return self.async_show_form(
            step_id="add_device",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_NAME): str,
                vol.Required(CONF_DEVICE_TYPE): vol.In(DEVICE_TYPES),
                vol.Required(CONF_DEVICE_ID): str,
            }),
            errors=errors,
        )

    async def async_step_remove_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove a device."""
        if not self._devices:
            return self.async_abort(reason="no_devices")

        if user_input is not None:
            device_to_remove = user_input["device"]
            self._devices = [
                d for d in self._devices if _device_key(d) != device_to_remove
            ]
            return self._save_devices()

        device_options = {
            _device_key(d): (
                f"{d[CONF_DEVICE_NAME]} "
                f"({DEVICE_TYPES.get(d[CONF_DEVICE_TYPE], d[CONF_DEVICE_TYPE])}, "
                f"{d[CONF_DEVICE_ID]})"
            )
            for d in self._devices
        }

        return self.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema({
                vol.Required("device"): vol.In(device_options),
            }),
        )

    async def async_step_edit_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            error = await _async_validate_connection(
                self.hass, host, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if error is None:
                new_data = dict(self._config_entry.data)
                new_data[CONF_HOST] = host
                new_data[CONF_USERNAME] = user_input[CONF_USERNAME]
                new_data[CONF_PASSWORD] = user_input[CONF_PASSWORD]

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )
                return self.async_create_entry(title="", data={})
            errors["base"] = error

        return self.async_show_form(
            step_id="edit_credentials",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_HOST, default=self._config_entry.data.get(CONF_HOST, "")
                ): str,
                vol.Required(
                    CONF_USERNAME, default=self._config_entry.data.get(CONF_USERNAME, "")
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )

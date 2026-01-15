"""Climate platform for Postown SmartWeb integration."""
from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_DEVICE_TYPE,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    DEVICE_TYPE_HEATER,
)
from .hub import SmartWebHub

_LOGGER = logging.getLogger(__name__)

PRESET_AWAY = "away"
PRESET_HOME = "home"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Postown SmartWeb climate entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    hub: SmartWebHub = data["hub"]
    devices: list[dict] = data["devices"]

    entities = []
    for device in devices:
        if device[CONF_DEVICE_TYPE] == DEVICE_TYPE_HEATER:
            entities.append(
                SmartWebHeater(
                    hub,
                    device[CONF_DEVICE_NAME],
                    device[CONF_DEVICE_ID],
                    entry.entry_id,
                )
            )

    async_add_entities(entities, True)


class SmartWebHeater(ClimateEntity):
    """Representation of a Postown SmartWeb heater."""

    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = [PRESET_HOME, PRESET_AWAY]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 10
    _attr_max_temp = 40

    def __init__(
        self,
        hub: SmartWebHub,
        name: str,
        device_id: str,
        entry_id: str,
    ) -> None:
        """Initialize the heater."""
        self._hub = hub
        self._attr_name = name
        self._device_id = device_id
        self._url = f"{hub.host}/SmartWeb/My_Home/Detail_Control_Heater.aspx?device_no={device_id}"
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_preset_mode = PRESET_HOME
        self._attr_target_temperature = 20
        self._attr_current_temperature = None
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_heater_{device_id}"

    def update(self) -> None:
        """Fetch new state data for this heater."""
        soup = self._hub.get_soup(self._url)
        if not soup:
            return

        page_content = str(soup)

        if "icon_b_boiler_away" in page_content:
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = PRESET_AWAY
        elif "icon_b_boiler_on" in page_content:
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = PRESET_HOME
        else:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = PRESET_HOME

        try:
            temp_input = soup.find(id="txtboxSetTemp")
            if temp_input:
                self._attr_target_temperature = float(temp_input.get("value", 20))
                self._attr_current_temperature = self._attr_target_temperature
        except (ValueError, TypeError):
            pass

    def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.HEAT:
            self._send_command("btnOn")
            self._attr_preset_mode = PRESET_HOME
        elif hvac_mode == HVACMode.OFF:
            self._send_command("btnOff")

    def set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode == PRESET_AWAY:
            self._send_command("btnAway")
        elif preset_mode == PRESET_HOME:
            if self._attr_hvac_mode == HVACMode.OFF:
                self._send_command("btnOn")
            elif self._attr_preset_mode == PRESET_AWAY:
                self._send_command("btnOn")

    def set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        self._attr_target_temperature = temp
        self._send_command("btnTmpSet")

    def _send_command(self, btn_id: str) -> None:
        """Send command to the heater."""
        soup = self._hub.get_soup(self._url)
        if not soup:
            return

        try:
            viewstate = soup.find(id="__VIEWSTATE")
            generator = soup.find(id="__VIEWSTATEGENERATOR")
            validation = soup.find(id="__EVENTVALIDATION")

            if not viewstate:
                _LOGGER.error("Could not find form fields for heater control")
                return

            payload = {
                "__VIEWSTATE": viewstate["value"],
                "__VIEWSTATEGENERATOR": generator["value"] if generator else "",
                "__EVENTVALIDATION": validation["value"] if validation else "",
                "__ASYNCPOST": "true",
                "ScriptManager1": f"UpdatePanel1|{btn_id}",
                "txtboxSetTemp": str(int(self._attr_target_temperature)),
                f"{btn_id}.x": "30",
                f"{btn_id}.y": "10",
            }
            if self._hub.send_command(self._url, payload):
                self.update()
        except Exception as e:
            _LOGGER.error("Heater command error: %s", e)

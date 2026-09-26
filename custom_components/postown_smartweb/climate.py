"""Climate platform for Postown SmartWeb integration."""
from __future__ import annotations

import logging

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_HOME,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_WHOLE, UnitOfTemperature
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

    # Links the entity to entity.climate.heater.* in strings.json
    _attr_translation_key = "heater"
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = [PRESET_HOME, PRESET_AWAY]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    # The device only accepts whole degrees
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 1
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
        self._attr_hvac_mode = None
        self._attr_preset_mode = None
        self._attr_target_temperature = None
        # The control page only exposes the set temperature, not the room temperature
        self._attr_current_temperature = None
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_heater_{device_id}"

    def update(self) -> None:
        """Fetch new state data for this heater."""
        soup = self._hub.get_soup(self._url)
        if soup is None:
            self._attr_available = False
            return

        self._attr_available = True
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

        temp = self._read_set_temperature(soup)
        if temp is not None:
            self._attr_target_temperature = temp
            _LOGGER.debug(
                "%s - Target temperature updated: %.1f°C", self._attr_name, temp
            )

    def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.HEAT:
            self._send_command("btnOn")
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
        temp = int(round(temp))
        _LOGGER.debug(
            "%s - Setting target temperature: %s°C -> %d°C",
            self._attr_name,
            self._attr_target_temperature,
            temp,
        )
        if self._send_command("btnTmpSet", temp):
            self._attr_target_temperature = temp

    @staticmethod
    def _read_set_temperature(soup) -> float | None:
        """Return the set temperature shown on the control page."""
        temp_input = soup.find(id="txtboxSetTemp")
        if not temp_input:
            return None
        try:
            return float(temp_input.get("value", ""))
        except (ValueError, TypeError):
            return None

    def _send_command(self, btn_id: str, temperature: int | None = None) -> bool:
        """Send command to the heater.

        Home Assistant refreshes the entity after the service call, so the
        state is not updated here.
        """
        soup = self._hub.get_soup(self._url)
        if soup is None:
            _LOGGER.error("Could not load heater page for device %s", self._device_id)
            return False

        viewstate = soup.find(id="__VIEWSTATE")
        generator = soup.find(id="__VIEWSTATEGENERATOR")
        validation = soup.find(id="__EVENTVALIDATION")

        if not viewstate:
            _LOGGER.error("Could not find form fields for heater control")
            return False

        if temperature is None:
            # Keep the temperature currently set on the server so that
            # on/off/away do not overwrite a change made on the wall panel.
            current = self._read_set_temperature(soup)
            if current is None:
                current = self._attr_target_temperature
            if current is None:
                _LOGGER.error("Could not determine set temperature for heater command")
                return False
            temperature = int(current)

        payload = {
            "__VIEWSTATE": viewstate["value"],
            "__VIEWSTATEGENERATOR": generator["value"] if generator else "",
            "__EVENTVALIDATION": validation["value"] if validation else "",
            "__ASYNCPOST": "true",
            "ScriptManager1": f"UpdatePanel1|{btn_id}",
            "txtboxSetTemp": str(temperature),
            f"{btn_id}.x": "30",
            f"{btn_id}.y": "10",
        }
        return self._hub.send_command(self._url, payload)

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
from homeassistant.exceptions import HomeAssistantError
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

# Buttons that are only rendered while the heater is running. The OFF page
# renders disabled "...D" variants (btnAwayD, btnTmpSetD) instead.
RUNNING_ONLY_BUTTONS = {
    "btnAway": "heater_off_away",
    "btnTmpSet": "heater_off_temperature",
}


def _read_float(element) -> float | None:
    """Return the numeric value of an input or text element."""
    if element is None:
        return None
    raw = element.get("value") if element.name == "input" else element.get_text(strip=True)
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def read_set_temperature(soup) -> float | None:
    """Return the set temperature (희망온도) shown on the heater page."""
    return _read_float(soup.find(id="txtboxSetTemp"))


def read_current_temperature(soup) -> float | None:
    """Return the room temperature (현재온도) shown on the heater page."""
    return _read_float(soup.find(id="lbNowTemp"))


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
    # Range shown on the control page: "희망온도 설정 (18℃~41℃)"
    _attr_min_temp = 18
    _attr_max_temp = 41

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
        self._attr_current_temperature = None
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_heater_{device_id}"

    def update(self) -> None:
        """Fetch new state data for this heater."""
        soup = self._hub.get_soup(self._url)
        if soup is None:
            self._attr_available = False
            return

        self._attr_available = True
        # The state icon is imgDevice: icon_b_boiler_off / icon_b_boiler_away /
        # icon_b_boiler_on1 (the ON icon has a numeric suffix).
        device_icon = soup.find(id="imgDevice")
        page_content = device_icon.get("src", "") if device_icon else str(soup)

        if "icon_b_boiler_away" in page_content:
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = PRESET_AWAY
        elif "icon_b_boiler_on" in page_content:
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = PRESET_HOME
        else:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = PRESET_HOME

        target = read_set_temperature(soup)
        if target is not None:
            self._attr_target_temperature = target
        self._attr_current_temperature = read_current_temperature(soup)
        _LOGGER.debug(
            "%s - Temperature updated: current=%s°C, target=%s°C",
            self._attr_name,
            self._attr_current_temperature,
            self._attr_target_temperature,
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

        # The page only renders the buttons that apply to the current state.
        # Posting a button that is not rendered fails ASP.NET event validation.
        if soup.find(id=btn_id) is None:
            if btn_id in RUNNING_ONLY_BUTTONS:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key=RUNNING_ONLY_BUTTONS[btn_id],
                )
            # btnOn is only shown while off and btnOff only while on
            _LOGGER.debug(
                "%s - %s not shown, heater is already in the requested state",
                self._attr_name,
                btn_id,
            )
            return True

        if temperature is None:
            # Keep the temperature currently set on the server so that
            # on/off/away do not overwrite a change made on the wall panel.
            current = read_set_temperature(soup)
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

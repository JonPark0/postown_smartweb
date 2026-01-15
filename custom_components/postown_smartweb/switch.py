"""Switch platform for Postown SmartWeb integration."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_DEVICE_TYPE,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    DEVICE_TYPE_LIGHT,
)
from .hub import SmartWebHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Postown SmartWeb switches from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    hub: SmartWebHub = data["hub"]
    devices: list[dict] = data["devices"]

    entities = []
    for device in devices:
        if device[CONF_DEVICE_TYPE] == DEVICE_TYPE_LIGHT:
            entities.append(
                SmartWebLight(
                    hub,
                    device[CONF_DEVICE_NAME],
                    device[CONF_DEVICE_ID],
                    entry.entry_id,
                )
            )

    async_add_entities(entities, True)


class SmartWebLight(SwitchEntity):
    """Representation of a Postown SmartWeb light switch."""

    def __init__(
        self,
        hub: SmartWebHub,
        name: str,
        device_id: str,
        entry_id: str,
    ) -> None:
        """Initialize the light switch."""
        self._hub = hub
        self._attr_name = name
        self._device_id = device_id
        self._url = f"{hub.host}/SmartWeb/My_Home/Detail_Control_Light.aspx?device_no={device_id}"
        self._attr_is_on = False
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_light_{device_id}"

    def update(self) -> None:
        """Fetch new state data for this light."""
        soup = self._hub.get_soup(self._url)
        if soup and "icon_b_light_on" in str(soup):
            self._attr_is_on = True
        else:
            self._attr_is_on = False

    def turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        self._operate("on")

    def turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        self._operate("off")

    def _operate(self, action: str) -> None:
        """Perform on/off operation."""
        soup = self._hub.get_soup(self._url)
        if not soup:
            return

        try:
            viewstate = soup.find(id="__VIEWSTATE")
            generator = soup.find(id="__VIEWSTATEGENERATOR")
            validation = soup.find(id="__EVENTVALIDATION")

            if not viewstate:
                _LOGGER.error("Could not find form fields for light control")
                return

            payload = {
                "__VIEWSTATE": viewstate["value"],
                "__VIEWSTATEGENERATOR": generator["value"] if generator else "",
                "__EVENTVALIDATION": validation["value"] if validation else "",
                "__ASYNCPOST": "true",
                "ScriptManager1": f"UpdatePanel1|btn{action.capitalize()}",
                f"btn{action.capitalize()}.x": "30",
                f"btn{action.capitalize()}.y": "10",
            }
            if self._hub.send_command(self._url, payload):
                self._attr_is_on = action == "on"
        except Exception as e:
            _LOGGER.error("Error controlling light: %s", e)

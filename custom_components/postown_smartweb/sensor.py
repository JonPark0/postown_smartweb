"""Sensor platform for Postown SmartWeb integration."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
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
    """Set up Postown SmartWeb sensor entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    hub: SmartWebHub = data["hub"]
    devices: list[dict] = data["devices"]

    entities = []
    for device in devices:
        if device[CONF_DEVICE_TYPE] == DEVICE_TYPE_HEATER:
            # Add current temperature sensor
            entities.append(
                SmartWebTemperatureSensor(
                    hub,
                    device[CONF_DEVICE_NAME],
                    device[CONF_DEVICE_ID],
                    entry.entry_id,
                    "current",
                )
            )
            # Add target temperature sensor
            entities.append(
                SmartWebTemperatureSensor(
                    hub,
                    device[CONF_DEVICE_NAME],
                    device[CONF_DEVICE_ID],
                    entry.entry_id,
                    "target",
                )
            )

    async_add_entities(entities, True)


class SmartWebTemperatureSensor(SensorEntity):
    """Representation of a Postown SmartWeb temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        hub: SmartWebHub,
        device_name: str,
        device_id: str,
        entry_id: str,
        sensor_type: str,  # "current" or "target"
    ) -> None:
        """Initialize the temperature sensor."""
        self._hub = hub
        self._device_id = device_id
        self._device_name = device_name
        self._sensor_type = sensor_type
        self._url = f"{hub.host}/SmartWeb/My_Home/Detail_Control_Heater.aspx?device_no={device_id}"
        self._attr_native_value = None

        # Set name and unique_id based on sensor type
        if sensor_type == "current":
            self._attr_name = f"{device_name} Current Temperature"
            self._attr_unique_id = f"{DOMAIN}_{entry_id}_heater_{device_id}_current_temp"
            self._attr_translation_key = "heater_current_temperature"
        else:  # target
            self._attr_name = f"{device_name} Target Temperature"
            self._attr_unique_id = f"{DOMAIN}_{entry_id}_heater_{device_id}_target_temp"
            self._attr_translation_key = "heater_target_temperature"

    def update(self) -> None:
        """Fetch new temperature data."""
        soup = self._hub.get_soup(self._url)
        if not soup:
            return

        try:
            temp_input = soup.find(id="txtboxSetTemp")
            if temp_input:
                temperature = float(temp_input.get("value", 20))

                # For now, both current and target use the same value from the web page
                # This matches the behavior in climate.py
                self._attr_native_value = temperature

                _LOGGER.debug(
                    "%s - Temperature sensor updated: %s=%.1f°C",
                    self._device_name,
                    self._sensor_type,
                    temperature,
                )
        except (ValueError, TypeError) as e:
            _LOGGER.error("Failed to parse temperature for %s: %s", self._device_name, e)

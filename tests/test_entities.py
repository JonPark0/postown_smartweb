"""Tests for the switch and climate entities with a fake hub."""
from bs4 import BeautifulSoup
from homeassistant.components.climate import HVACMode

from custom_components.postown_smartweb.climate import SmartWebHeater
from custom_components.postown_smartweb.switch import SmartWebLight

FORM = (
    '<input id="__VIEWSTATE" value="vs"/>'
    '<input id="__VIEWSTATEGENERATOR" value="g"/>'
    '<input id="__EVENTVALIDATION" value="ev"/>'
)


class FakeHub:
    """Serves queued pages (None = fetch failure) and records commands."""

    host = "http://h"

    def __init__(self, pages, command_ok=True):
        self.pages = list(pages)
        self.command_ok = command_ok
        self.sent = []

    def get_soup(self, url):
        page = self.pages.pop(0) if self.pages else None
        return None if page is None else BeautifulSoup(page, "html.parser")

    def send_command(self, url, payload):
        self.sent.append(payload)
        return self.command_ok


def heater(pages, command_ok=True):
    hub = FakeHub(pages, command_ok)
    return SmartWebHeater(hub, "n", "31", "e"), hub


def light(pages, command_ok=True):
    hub = FakeHub(pages, command_ok)
    return SmartWebLight(hub, "n", "1", "e"), hub


def test_heater_translation_key():
    entity, _ = heater([])
    assert entity.translation_key == "heater"


def test_heater_update_reads_state():
    entity, _ = heater(
        [FORM + '<img src="icon_b_boiler_on.png"/><input id="txtboxSetTemp" value="23"/>']
    )
    entity.update()
    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.preset_mode == "home"
    assert entity.target_temperature == 23.0
    # The page has no room temperature, so none is reported
    assert entity.current_temperature is None
    assert entity.target_temperature_step == 1


def test_heater_update_away():
    entity, _ = heater([FORM + '<img src="icon_b_boiler_away.png"/>'])
    entity.update()
    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.preset_mode == "away"


def test_heater_unavailable_on_fetch_failure():
    entity, _ = heater([None, FORM])
    entity.update()
    assert entity.available is False
    entity.update()
    assert entity.available is True
    assert entity.hvac_mode == HVACMode.OFF


def test_heater_mode_change_keeps_server_temperature():
    entity, hub = heater([FORM + '<input id="txtboxSetTemp" value="25"/>'])
    entity._attr_target_temperature = 20  # stale local value
    entity.set_hvac_mode(HVACMode.HEAT)
    assert hub.sent[0]["txtboxSetTemp"] == "25"
    assert hub.sent[0]["ScriptManager1"] == "UpdatePanel1|btnOn"


def test_heater_set_temperature_rounds():
    entity, hub = heater([FORM + '<input id="txtboxSetTemp" value="20"/>'])
    entity.set_temperature(temperature=22.6)
    assert hub.sent[0]["txtboxSetTemp"] == "23"
    assert entity.target_temperature == 23


def test_heater_set_temperature_failure_keeps_value():
    entity, _ = heater([FORM], command_ok=False)
    entity._attr_target_temperature = 20
    entity.set_temperature(temperature=26)
    assert entity.target_temperature == 20


def test_heater_preset_away():
    entity, hub = heater([FORM + '<input id="txtboxSetTemp" value="21"/>'])
    entity.set_preset_mode("away")
    assert hub.sent[0]["ScriptManager1"] == "UpdatePanel1|btnAway"


def test_heater_command_does_not_refetch():
    # Home Assistant refreshes polling entities after a service call
    entity, hub = heater([FORM + '<input id="txtboxSetTemp" value="21"/>', "unread"])
    entity.set_hvac_mode(HVACMode.OFF)
    assert hub.pages == ["unread"]


def test_light_unavailable_on_fetch_failure():
    entity, _ = light([FORM + '<img src="icon_b_light_on.png"/>', None])
    entity.update()
    assert entity.is_on is True
    assert entity.available is True
    entity.update()
    assert entity.available is False


def test_light_failed_command_keeps_state():
    entity, _ = light([FORM], command_ok=False)
    entity._attr_is_on = False
    entity.turn_on()
    assert entity.is_on is False


def test_light_turn_on():
    entity, hub = light([FORM])
    entity.turn_on()
    assert entity.is_on is True
    assert hub.sent[0]["ScriptManager1"] == "UpdatePanel1|btnOn"

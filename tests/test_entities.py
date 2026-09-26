"""Tests for the switch, climate and sensor entities with a fake hub.

The page fixtures mirror the real SmartWeb control pages. LIGHT_ON, LIGHT_OFF
and HEATER_OFF were checked against the live server; HEATER_ON and HEATER_AWAY
are reconstructed (no heater was running when the pages were inspected).
"""
import pytest
from bs4 import BeautifulSoup
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.postown_smartweb.climate import SmartWebHeater
from custom_components.postown_smartweb.sensor import SmartWebTemperatureSensor
from custom_components.postown_smartweb.switch import SmartWebLight

FORM = (
    '<input id="__VIEWSTATE" value="vs"/>'
    '<input id="__VIEWSTATEGENERATOR" value="g"/>'
    '<input id="__EVENTVALIDATION" value="ev"/>'
    '<input type="image" id="ibtnRefresh" src="../Images/HomeControl/btn_refresh_N.png"/>'
)

LIGHT_ON = FORM + (
    '<img id="imgDevice" src="../Images/HomeControl/icon_b_light_on.png"/>'
    '<input type="image" id="btnOff" src="../Images/HomeControl/btn_device_off_N.png"/>'
)
LIGHT_OFF = FORM + (
    '<img id="imgDevice" src="../Images/HomeControl/icon_b_light_off.png"/>'
    '<input type="image" id="btnOn" src="../Images/HomeControl/btn_device_on_N.png"/>'
)


def heater_page(icon, buttons, set_temp="23", now_temp="24"):
    return FORM + (
        f'<img id="imgDevice" src="../Images/HomeControl/{icon}.png"/>'
        + "".join(f'<input type="image" id="{b}"/>' for b in buttons)
        + f'<span id="lbNowTemp">{now_temp}</span><span id="Label2">℃</span>'
        + f'<input type="text" id="txtboxSetTemp" value="{set_temp}"/>'
    )


HEATER_OFF = heater_page("icon_b_boiler_off", ["btnAwayD", "btnOn", "btnTmpSetD"])
HEATER_ON = heater_page("icon_b_boiler_on1", ["btnAway", "btnOff", "btnTmpSet"])
HEATER_AWAY = heater_page("icon_b_boiler_away", ["btnOn", "btnOff", "btnTmpSetD"])


class FakeHub:
    """Serves queued pages (None = fetch failure) and records commands."""

    host = "http://h"

    def __init__(self, pages, command_ok=True):
        self.pages = list(pages)
        self.command_ok = command_ok
        self.sent = []

    def get_device_page(self, url):
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


# ---------- climate ----------

def test_heater_translation_key_and_range():
    entity, _ = heater([])
    assert entity.translation_key == "heater"
    assert (entity.min_temp, entity.max_temp) == (18, 41)
    assert entity.target_temperature_step == 1


def test_heater_update_off_page():
    entity, _ = heater([HEATER_OFF])
    entity.update()
    assert entity.hvac_mode == HVACMode.OFF
    assert entity.target_temperature == 23.0
    assert entity.current_temperature == 24.0


def test_heater_update_on_page():
    entity, _ = heater([HEATER_ON])
    entity.update()
    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.preset_mode == "home"


def test_heater_update_away_page():
    entity, _ = heater([HEATER_AWAY])
    entity.update()
    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.preset_mode == "away"


def test_heater_missing_room_temperature():
    entity, _ = heater([heater_page("icon_b_boiler_off", ["btnOn"], now_temp="")])
    entity.update()
    assert entity.current_temperature is None


def test_heater_unavailable_on_fetch_failure():
    entity, _ = heater([None, HEATER_OFF])
    entity.update()
    assert entity.available is False
    entity.update()
    assert entity.available is True


def test_heater_turn_on_keeps_server_temperature():
    entity, hub = heater([heater_page("icon_b_boiler_off", ["btnOn"], set_temp="25")])
    entity._attr_target_temperature = 20  # stale local value
    entity.set_hvac_mode(HVACMode.HEAT)
    assert hub.sent[0]["txtboxSetTemp"] == "25"
    assert hub.sent[0]["ScriptManager1"] == "UpdatePanel1|btnOn"


def test_heater_turn_on_when_already_on_does_not_post():
    entity, hub = heater([HEATER_ON])
    entity.set_hvac_mode(HVACMode.HEAT)
    assert hub.sent == []


def test_heater_turn_off_when_already_off_does_not_post():
    entity, hub = heater([HEATER_OFF])
    entity.set_hvac_mode(HVACMode.OFF)
    assert hub.sent == []


def test_heater_set_temperature_rounds():
    entity, hub = heater([HEATER_ON])
    entity.set_temperature(temperature=22.6)
    assert hub.sent[0]["txtboxSetTemp"] == "23"
    assert hub.sent[0]["ScriptManager1"] == "UpdatePanel1|btnTmpSet"
    assert entity.target_temperature == 23


def test_heater_set_temperature_failure_keeps_value():
    entity, _ = heater([HEATER_ON], command_ok=False)
    entity._attr_target_temperature = 20
    entity.set_temperature(temperature=26)
    assert entity.target_temperature == 20


def test_heater_set_temperature_while_off_raises():
    entity, hub = heater([HEATER_OFF])
    with pytest.raises(HomeAssistantError) as err:
        entity.set_temperature(temperature=25)
    assert err.value.translation_key == "heater_off_temperature"
    assert hub.sent == []


def test_heater_away_while_off_raises():
    entity, hub = heater([HEATER_OFF])
    with pytest.raises(HomeAssistantError) as err:
        entity.set_preset_mode("away")
    assert err.value.translation_key == "heater_off_away"
    assert hub.sent == []


def test_heater_preset_away_while_on():
    entity, hub = heater([HEATER_ON])
    entity.set_preset_mode("away")
    assert hub.sent[0]["ScriptManager1"] == "UpdatePanel1|btnAway"


def test_heater_command_does_not_refetch():
    # Home Assistant refreshes polling entities after a service call
    entity, hub = heater([HEATER_ON, "unread"])
    entity.set_hvac_mode(HVACMode.OFF)
    assert hub.sent[0]["ScriptManager1"] == "UpdatePanel1|btnOff"
    assert hub.pages == ["unread"]


# ---------- sensor ----------

def test_temperature_sensors_read_their_own_values():
    hub = FakeHub([HEATER_OFF, HEATER_OFF])
    current = SmartWebTemperatureSensor(hub, "n", "31", "e", "current")
    target = SmartWebTemperatureSensor(hub, "n", "31", "e", "target")
    current.update()
    target.update()
    assert current.native_value == 24.0
    assert target.native_value == 23.0


def test_temperature_sensor_unavailable_on_fetch_failure():
    hub = FakeHub([HEATER_OFF, None])
    entity = SmartWebTemperatureSensor(hub, "n", "31", "e", "target")
    entity.update()
    assert entity.available is True
    entity.update()
    assert entity.available is False


# ---------- switch ----------

def test_light_state_from_real_pages():
    entity, _ = light([LIGHT_ON, LIGHT_OFF])
    entity.update()
    assert entity.is_on is True
    entity.update()
    assert entity.is_on is False


def test_light_unavailable_on_fetch_failure():
    entity, _ = light([LIGHT_ON, None])
    entity.update()
    assert entity.available is True
    entity.update()
    assert entity.available is False


def test_light_turn_on():
    entity, hub = light([LIGHT_OFF])
    entity.turn_on()
    assert entity.is_on is True
    assert hub.sent[0]["ScriptManager1"] == "UpdatePanel1|btnOn"


def test_light_turn_on_when_already_on_does_not_post():
    entity, hub = light([LIGHT_ON])
    entity._attr_is_on = False
    entity.turn_on()
    assert hub.sent == []
    assert entity.is_on is True


def test_light_failed_command_keeps_state():
    entity, _ = light([LIGHT_OFF], command_ok=False)
    entity._attr_is_on = False
    entity.turn_on()
    assert entity.is_on is False

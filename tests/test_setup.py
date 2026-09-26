"""Tests for entry setup and config flow helpers."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.postown_smartweb import (
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.postown_smartweb import config_flow
from custom_components.postown_smartweb.const import DOMAIN
from custom_components.postown_smartweb.hub import CannotConnect, InvalidAuth, SmartWebHub


def make_hass():
    hass = MagicMock()

    async def run_in_executor(func, *args):
        return func(*args)

    hass.async_add_executor_job = run_in_executor
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_reload = AsyncMock()
    return hass


def make_entry():
    return SimpleNamespace(
        entry_id="e1",
        data={"host": "http://h", "username": "u", "password": "p", "devices": []},
        async_on_unload=MagicMock(),
        add_update_listener=MagicMock(),
    )


def raiser(exc):
    def authenticate(self):
        raise exc
    return authenticate


def test_setup_retries_when_server_unreachable(monkeypatch):
    monkeypatch.setattr(SmartWebHub, "authenticate", raiser(CannotConnect("down")))
    with pytest.raises(ConfigEntryNotReady):
        asyncio.run(async_setup_entry(make_hass(), make_entry()))


def test_setup_fails_on_invalid_auth(monkeypatch):
    monkeypatch.setattr(SmartWebHub, "authenticate", raiser(InvalidAuth("no")))
    assert asyncio.run(async_setup_entry(make_hass(), make_entry())) is False


def test_setup_and_unload(monkeypatch):
    monkeypatch.setattr(SmartWebHub, "authenticate", lambda self: None)
    closed = []
    monkeypatch.setattr(SmartWebHub, "close", lambda self: closed.append(True))
    hass = make_hass()
    entry = make_entry()

    assert asyncio.run(async_setup_entry(hass, entry)) is True
    hass.config_entries.async_forward_entry_setups.assert_awaited_once()
    assert asyncio.run(async_unload_entry(hass, entry)) is True
    assert closed == [True]
    assert entry.entry_id not in hass.data[DOMAIN]


def test_reload_uses_config_entries_reload():
    hass = make_hass()
    asyncio.run(async_reload_entry(hass, make_entry()))
    hass.config_entries.async_reload.assert_awaited_once_with("e1")


@pytest.mark.parametrize(
    ("authenticate", "host", "expected"),
    [
        (lambda self: None, "sdexpo9.postown.net", "invalid_host"),
        (raiser(CannotConnect("x")), "http://h", "cannot_connect"),
        (raiser(InvalidAuth("x")), "http://h", "invalid_auth"),
        (raiser(RuntimeError("x")), "http://h", "unknown"),
        (lambda self: None, "https://h", None),
    ],
)
def test_validate_connection(monkeypatch, authenticate, host, expected):
    monkeypatch.setattr(SmartWebHub, "authenticate", authenticate)
    result = asyncio.run(
        config_flow._async_validate_connection(make_hass(), host, "u", "p")
    )
    assert result == expected


def test_validate_device():
    existing = [{"device_name": "a", "device_type": "light", "device_id": "1"}]

    _, error = config_flow._validate_device(
        {"device_name": "x", "device_type": "light", "device_id": "abc"}, existing
    )
    assert error == "invalid_device_id"

    _, error = config_flow._validate_device(
        {"device_name": "x", "device_type": "light", "device_id": " 1 "}, existing
    )
    assert error == "device_exists"

    # Same ID with a different type is a different device page
    device, error = config_flow._validate_device(
        {"device_name": " x ", "device_type": "heater", "device_id": "1"}, existing
    )
    assert error is None
    assert device["device_name"] == "x"

"""Tests for the SmartWeb hub using a scripted fake HTTP session."""
import threading
import time

import pytest
import requests

from custom_components.postown_smartweb import hub as hub_mod

LOGIN_PAGE = (
    '<input id="__VIEWSTATE" value="vs"/>'
    '<input id="__VIEWSTATEGENERATOR" value="g"/>'
)
PAGE_URL = "http://h/SmartWeb/My_Home/x.aspx"
EXPIRED = "|pageRedirect||/SmartWeb/Default.aspx|"


class Resp:
    """Minimal stand-in for requests.Response."""

    def __init__(self, text="", status=200, url=PAGE_URL, json_data=None):
        self.text = text
        self.status_code = status
        self.url = url
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeSession:
    """Returns scripted responses and tracks concurrent use."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.headers = {}
        self.active = 0
        self.max_active = 0

    def _next(self):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        time.sleep(0.005)
        self.active -= 1
        self.calls += 1
        item = self.script.pop(0) if self.script else Resp()
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, **kwargs):
        return self._next()

    def post(self, url, **kwargs):
        return self._next()

    def close(self):
        pass


def make_hub(script):
    hub = hub_mod.SmartWebHub("http://h/ ", "u", "p")
    hub._session = FakeSession(script)
    return hub


def login_ok():
    return [
        Resp(LOGIN_PAGE, url="http://h/SmartWeb/Default.aspx"),
        Resp(json_data={"d": "token123"}),
        Resp("1|#||4|pageRedirect||/SmartWeb/Main.aspx|"),
    ]


def test_host_is_normalized():
    assert make_hub([]).host == "http://h"


def test_authenticate_succeeds():
    make_hub(login_ok()).authenticate()


@pytest.mark.parametrize(
    ("script", "error"),
    [
        ([requests.ConnectionError("down")], hub_mod.CannotConnect),
        ([Resp("<html>maintenance</html>")], hub_mod.CannotConnect),
        ([Resp(LOGIN_PAGE), Resp("<html>oops</html>")], hub_mod.CannotConnect),
        ([Resp(LOGIN_PAGE), Resp(status=500)], hub_mod.CannotConnect),
        ([Resp(LOGIN_PAGE), Resp(json_data={"d": "<script>alert('x')</script>"})], hub_mod.InvalidAuth),
        ([Resp(LOGIN_PAGE), Resp(json_data={"d": ""})], hub_mod.InvalidAuth),
        ([Resp(LOGIN_PAGE), Resp(json_data={"d": "t"}), Resp("no redirect")], hub_mod.InvalidAuth),
    ],
)
def test_authenticate_errors(script, error):
    with pytest.raises(error):
        make_hub(script).authenticate()


def test_get_soup_network_error_returns_none():
    assert make_hub([requests.Timeout("t")]).get_soup(PAGE_URL) is None


def test_get_soup_relogins_on_redirect():
    hub = make_hub(
        [Resp("login", url="http://h/SmartWeb/Default.aspx")]
        + login_ok()
        + [Resp('<img src="icon_b_light_on.png"/>')]
    )
    soup = hub.get_soup(PAGE_URL)
    assert soup is not None
    assert "icon_b_light_on" in str(soup)


def test_get_soup_returns_none_when_relogin_fails():
    hub = make_hub(
        [Resp("login", url="http://h/SmartWeb/Default.aspx"), requests.ConnectionError("down")]
    )
    assert hub.get_soup(PAGE_URL) is None


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        ([Resp("1|#||4|updatePanel|UpdatePanel1|...|")], True),
        # ASP.NET AJAX reports server errors as HTTP 200 with an error segment
        ([Resp("47|error|500|Invalid postback or callback argument|")], False),
        ([Resp("err", status=500)], False),
        ([requests.ConnectionError("x")], False),
        ([Resp(EXPIRED)] + login_ok() + [Resp("ok")], True),
        ([Resp(EXPIRED)] + login_ok() + [Resp(EXPIRED)], False),
        ([Resp(EXPIRED), requests.ConnectionError("x")], False),
    ],
)
def test_send_command(script, expected):
    assert make_hub(script).send_command("u", {}) is expected


def test_session_is_never_used_concurrently():
    hub = make_hub([Resp("<p/>") for _ in range(40)])
    threads = [
        threading.Thread(target=hub.get_soup, args=(PAGE_URL,)) for _ in range(20)
    ] + [threading.Thread(target=hub.send_command, args=("u", {})) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert hub._session.max_active == 1

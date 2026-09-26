"""Hub for Postown SmartWeb integration."""
import logging
import threading
import time
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

# After a network failure, polling skips the server for this many seconds.
# Without this every entity waits for its own timeout during an outage, and
# because requests are serialized a user command could queue for minutes.
UNREACHABLE_BACKOFF = 60

# Every device control page shows its state icon in this element. A page
# without it is not a device page (e.g. a router's "no internet" page).
DEVICE_ICON_ID = "imgDevice"


class SmartWebError(Exception):
    """Base error for Postown SmartWeb."""


class CannotConnect(SmartWebError):
    """Error to indicate the server could not be reached."""


class InvalidAuth(SmartWebError):
    """Error to indicate the credentials were rejected."""


def normalize_host(host: str) -> str:
    """Return the host URL without surrounding whitespace or trailing slash."""
    return host.strip().rstrip("/")


class SmartWebHub:
    """Handles the connection to the ASP.NET system."""

    def __init__(self, host: str, username: str, password: str) -> None:
        """Initialize the hub."""
        self._host = normalize_host(host)
        self._netloc = urlsplit(self._host).netloc.lower()
        self._auth = {"ID": username, "PW": password}
        # Switch, climate and sensor platforms update in parallel threads and
        # share this session, so login and requests must not interleave.
        self._lock = threading.RLock()
        self._unreachable_until = 0.0
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Accept-Language": "ko,en;q=0.9,en-US;q=0.8",
        })

    @property
    def host(self) -> str:
        """Return the host URL."""
        return self._host

    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()

    def authenticate(self) -> None:
        """Perform full ASP.NET login.

        Raises CannotConnect when the server is unreachable or returns an
        unexpected response, and InvalidAuth when the credentials are rejected.
        """
        with self._lock:
            try:
                self._login()
            except requests.RequestException as e:
                raise CannotConnect(f"Login network error: {e}") from e
            except ValueError as e:
                # Non-JSON response from the login web service
                raise CannotConnect(f"Unexpected login response: {e}") from e

    def _login(self) -> None:
        """Run the login steps. Caller must hold the lock."""
        login_url = f"{self._host}/SmartWeb/Default.aspx"
        r_get = self._session.get(login_url, timeout=10)
        r_get.raise_for_status()
        if not self._is_own_host(r_get):
            raise CannotConnect(f"Login page was redirected to {r_get.url}")

        soup = BeautifulSoup(r_get.text, "html.parser")

        viewstate_tag = soup.find(id="__VIEWSTATE")
        generator_tag = soup.find(id="__VIEWSTATEGENERATOR")
        event_val_tag = soup.find(id="__EVENTVALIDATION")

        if not viewstate_tag:
            raise CannotConnect("Could not find __VIEWSTATE on login page")

        svc_url = f"{self._host}/SmartWeb/_WebService/WizWeb_Svc.asmx/Login"
        svc_headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        svc_payload = {"ID": self._auth["ID"], "PW": self._auth["PW"]}

        r_svc = self._session.post(
            svc_url, json=svc_payload, headers=svc_headers, timeout=10
        )
        if r_svc.status_code != 200:
            raise CannotConnect(f"WebService login check failed: {r_svc.status_code}")

        login_token = r_svc.json().get("d")

        if not login_token or ">" in str(login_token):
            raise InvalidAuth("Login web service rejected the credentials")

        post_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-MicrosoftAjax": "Delta=true",
            "Cache-Control": "no-cache",
            "X-Requested-With": "XMLHttpRequest",
        }

        payload = {
            "scriptmanager1": "UpdatePanel1|btnLogin",
            "__EVENTTARGET": "btnLogin",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": viewstate_tag["value"],
            "__VIEWSTATEGENERATOR": generator_tag["value"] if generator_tag else "",
            "__EVENTVALIDATION": event_val_tag["value"] if event_val_tag else "",
            "txtID": self._auth["ID"],
            "txtPW": self._auth["PW"],
            "Hidden2": "1",
            "Hidden1": login_token,
            "__ASYNCPOST": "true",
        }

        r_post = self._session.post(
            login_url, data=payload, headers=post_headers, timeout=10
        )
        if r_post.status_code != 200:
            raise CannotConnect(f"Login form post failed: {r_post.status_code}")

        if "pageRedirect" not in r_post.text:
            raise InvalidAuth("Login failed: pageRedirect not found")

        _LOGGER.debug("Login successful")

    def _relogin(self) -> bool:
        """Log in again after the session expired. Caller must hold the lock."""
        _LOGGER.info("Session expired, logging in again")
        try:
            self._login()
        except requests.RequestException as e:
            self._mark_unreachable(e)
            return False
        except (SmartWebError, ValueError) as e:
            _LOGGER.error("Re-login failed: %s", e)
            return False
        return True

    def _is_own_host(self, response: requests.Response) -> bool:
        """Return True if the response came from the configured server."""
        return urlsplit(response.url).netloc.lower() == self._netloc

    def _mark_unreachable(self, reason: object) -> None:
        """Pause polling after a network failure. Caller must hold the lock."""
        if self._unreachable_until == 0.0:
            _LOGGER.warning(
                "SmartWeb server is unreachable (%s); pausing status updates for %s seconds",
                reason,
                UNREACHABLE_BACKOFF,
            )
        else:
            _LOGGER.debug("SmartWeb server still unreachable: %s", reason)
        self._unreachable_until = time.monotonic() + UNREACHABLE_BACKOFF

    def _mark_reachable(self) -> None:
        """Clear the backoff after a successful request. Caller must hold the lock."""
        if self._unreachable_until:
            _LOGGER.info("SmartWeb server is reachable again")
            self._unreachable_until = 0.0

    def get_soup(self, url: str) -> BeautifulSoup | None:
        """Get page content with automatic re-login. Returns None on failure."""
        with self._lock:
            if time.monotonic() < self._unreachable_until:
                return None
            try:
                r = self._session.get(url, timeout=10)

                if "Default.aspx" in r.url and "Default.aspx" not in url:
                    if not self._relogin():
                        return None
                    r = self._session.get(url, timeout=10)
                    if "Default.aspx" in r.url:
                        _LOGGER.error("Failed to access page after login")
                        return None

                if not self._is_own_host(r):
                    # e.g. the router redirects to its own page when offline
                    self._mark_unreachable(f"redirected to {r.url}")
                    return None

                if r.status_code != 200:
                    _LOGGER.error("Unexpected status %s accessing %s", r.status_code, url)
                    return None

                self._mark_reachable()
                return BeautifulSoup(r.text, "html.parser")
            except requests.RequestException as e:
                self._mark_unreachable(e)
                return None

    def get_device_page(self, url: str) -> BeautifulSoup | None:
        """Get a device control page, or None if it is missing or not a device page."""
        soup = self.get_soup(url)
        if soup is None:
            return None
        if soup.find(id=DEVICE_ICON_ID) is None:
            _LOGGER.warning("Response from %s is not a device control page", url)
            return None
        return soup

    def send_command(self, url: str, payload: dict) -> bool:
        """Send command to device. Returns True only if the server accepted it.

        Commands are tried even while polling is paused, since they are
        user-initiated and a success means the server is back.
        """
        headers = {
            "X-MicrosoftAjax": "Delta=true",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Cache-Control": "no-cache",
        }
        with self._lock:
            try:
                r = self._session.post(url, data=payload, headers=headers, timeout=10)

                if self._is_redirected(r):
                    if not self._relogin():
                        return False
                    r = self._session.post(url, data=payload, headers=headers, timeout=10)
                    if self._is_redirected(r):
                        _LOGGER.error("Command still redirected after re-login")
                        return False

                if not self._is_own_host(r):
                    self._mark_unreachable(f"redirected to {r.url}")
                    return False

                if r.status_code != 200:
                    _LOGGER.error("Command failed with status %s", r.status_code)
                    return False

                # ASP.NET AJAX reports server errors as HTTP 200 with an
                # "error" segment in the delta response.
                if "|error|" in r.text:
                    _LOGGER.error("Server rejected command: %s", r.text[:200])
                    return False

                self._mark_reachable()
                return True
            except requests.RequestException as e:
                self._mark_unreachable(e)
                _LOGGER.error("Command failed: %s", e)
                return False

    @staticmethod
    def _is_redirected(response: requests.Response) -> bool:
        """Return True if the response sends us back to the login page."""
        return "pageRedirect" in response.text or "Default.aspx" in response.url

"""Hub for Postown SmartWeb integration."""
import logging
import threading

import requests
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)


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
        self._auth = {"ID": username, "PW": password}
        # Switch and climate platforms update in parallel threads and share
        # this session, so login and requests must not interleave.
        self._lock = threading.RLock()
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
        except (SmartWebError, requests.RequestException, ValueError) as e:
            _LOGGER.error("Re-login failed: %s", e)
            return False
        return True

    def get_soup(self, url: str) -> BeautifulSoup | None:
        """Get page content with automatic re-login. Returns None on failure."""
        with self._lock:
            try:
                r = self._session.get(url, timeout=10)

                if "Default.aspx" in r.url and "Default.aspx" not in url:
                    if not self._relogin():
                        return None
                    r = self._session.get(url, timeout=10)
                    if "Default.aspx" in r.url:
                        _LOGGER.error("Failed to access page after login")
                        return None

                if r.status_code != 200:
                    _LOGGER.error("Unexpected status %s accessing %s", r.status_code, url)
                    return None

                return BeautifulSoup(r.text, "html.parser")
            except requests.RequestException as e:
                _LOGGER.error("Network error accessing %s: %s", url, e)
                return None

    def send_command(self, url: str, payload: dict) -> bool:
        """Send command to device. Returns True only if the server accepted it."""
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

                if r.status_code != 200:
                    _LOGGER.error("Command failed with status %s", r.status_code)
                    return False

                # ASP.NET AJAX reports server errors as HTTP 200 with an
                # "error" segment in the delta response.
                if "|error|" in r.text:
                    _LOGGER.error("Server rejected command: %s", r.text[:200])
                    return False

                return True
            except requests.RequestException as e:
                _LOGGER.error("Command failed: %s", e)
                return False

    @staticmethod
    def _is_redirected(response: requests.Response) -> bool:
        """Return True if the response sends us back to the login page."""
        return "pageRedirect" in response.text or "Default.aspx" in response.url

"""Hub for Postown SmartWeb integration."""
import logging
import requests
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)


class SmartWebHub:
    """Handles the connection to the ASP.NET system."""

    def __init__(self, host: str, username: str, password: str) -> None:
        """Initialize the hub."""
        self._host = host.rstrip("/")
        self._auth = {"ID": username, "PW": password}
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Accept-Language": "ko,en;q=0.9,en-US;q=0.8",
        })

    @property
    def host(self) -> str:
        """Return the host URL."""
        return self._host

    def login(self) -> bool:
        """Perform full ASP.NET Login process."""
        try:
            login_url = f"{self._host}/SmartWeb/Default.aspx"
            r_get = self._session.get(login_url, timeout=10)

            soup = BeautifulSoup(r_get.text, "html.parser")

            viewstate_tag = soup.find(id="__VIEWSTATE")
            generator_tag = soup.find(id="__VIEWSTATEGENERATOR")
            event_val_tag = soup.find(id="__EVENTVALIDATION")

            if not viewstate_tag:
                _LOGGER.error("Could not find __VIEWSTATE on login page")
                return False

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
                _LOGGER.error("WebService login check failed: %s", r_svc.status_code)
                return False

            svc_data = r_svc.json()
            login_token = svc_data.get("d")

            if not login_token or ">" in str(login_token):
                _LOGGER.error("Invalid login token received: %s", login_token)
                return False

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

            if r_post.status_code == 200 and "pageRedirect" in r_post.text:
                _LOGGER.info("Login successful")
                return True

            _LOGGER.warning("Login failed: pageRedirect not found")
            return False

        except requests.RequestException as e:
            _LOGGER.error("Login network error: %s", e)
            return False
        except Exception as e:
            _LOGGER.error("Login process error: %s", e)
            return False

    def test_connection(self) -> bool:
        """Test if connection and login work."""
        return self.login()

    def get_soup(self, url: str) -> BeautifulSoup | None:
        """Get page content with automatic re-login."""
        try:
            r = self._session.get(url, timeout=10)

            if "Default.aspx" in r.url and "Default.aspx" not in url:
                _LOGGER.info("Session expired, logging in...")
                if self.login():
                    r = self._session.get(url, timeout=10)
                    if "Default.aspx" in r.url:
                        _LOGGER.error("Failed to access page after login")
                        return None
                else:
                    return None

            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            _LOGGER.error("Network error accessing %s: %s", url, e)
            return None

    def send_command(self, url: str, payload: dict) -> bool:
        """Send command to device."""
        headers = {
            "X-MicrosoftAjax": "Delta=true",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Cache-Control": "no-cache",
        }
        try:
            r = self._session.post(url, data=payload, headers=headers, timeout=10)

            if "pageRedirect" in r.text or "Default.aspx" in r.url:
                _LOGGER.info("Session expired during command, re-logging...")
                if self.login():
                    r = self._session.post(url, data=payload, headers=headers, timeout=10)

            return r.status_code == 200
        except Exception as e:
            _LOGGER.error("Command failed: %s", e)
            return False

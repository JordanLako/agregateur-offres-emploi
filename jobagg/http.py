"""Session HTTP partagée : en-têtes de navigateur, réessais, délai de politesse."""

from __future__ import annotations

import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
    # brotli n'est pas géré nativement par requests
    "Accept-Encoding": "gzip, deflate",
}

TIMEOUT = 20


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


class Throttle:
    """Impose un délai minimal entre deux requêtes d'une même source."""

    def __init__(self, delay: float):
        self.delay = delay
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self._last = time.monotonic()

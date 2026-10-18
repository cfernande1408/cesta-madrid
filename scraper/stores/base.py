"""Piezas comunes de los adaptadores: cliente HTTP, errores y ritmo."""

import time
from collections.abc import Callable
from typing import Protocol

import httpx

from scraper.matching import Item
from scraper.models import Offer

# Versión de Chrome que imitan las cabeceras. Revisar cada pocos meses:
# un navegador desactualizado también delata a un bot.
CHROME_VERSION = "155"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "es-ES,es;q=0.9",
    "sec-ch-ua": (
        f'"Chromium";v="{CHROME_VERSION}", "Google Chrome";v="{CHROME_VERSION}", '
        '"Not.A/Brand";v="99"'
    ),
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


class StoreError(Exception):
    """Fallo al hablar con un súper. Guarda lo justo para diagnosticar."""

    def __init__(self, message: str, *, status: int | None = None, sample: str | None = None):
        super().__init__(message)
        self.status = status
        self.sample = sample[:400] if sample else None


class Store(Protocol):
    id: str
    nombre: str

    def search(self, item: Item) -> list[Offer]:
        """Productos candidatos para un artículo de la cesta."""
        ...


def make_client(headers: dict[str, str] | None = None, **kwargs) -> httpx.Client:
    return httpx.Client(
        headers={**BROWSER_HEADERS, **(headers or {})},
        timeout=httpx.Timeout(30.0, connect=15.0),
        follow_redirects=True,
        http2=False,
        **kwargs,
    )


class Pacer:
    """Espera mínima entre peticiones para no cargar las webs de los súper."""

    def __init__(self, delay: float, sleep: Callable[[float], None] = time.sleep):
        self.delay = delay
        self._sleep = sleep
        self._last = 0.0

    def wait(self) -> None:
        if self.delay <= 0:
            return
        elapsed = time.monotonic() - self._last
        if elapsed < self.delay:
            self._sleep(self.delay - elapsed)
        self._last = time.monotonic()


def get(
    client: httpx.Client,
    url: str,
    *,
    pacer: Pacer,
    params: dict | None = None,
    retries: int = 2,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """GET con reintentos solo ante errores de red y 5xx.

    Un 403 o 429 no se reintenta: suele ser un bloqueo y insistir lo empeora.
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        pacer.wait()
        try:
            resp = client.get(url, params=params)
        except httpx.TransportError as exc:
            last_exc = exc
            sleep(2 * (attempt + 1))
            continue
        if resp.status_code >= 500 and attempt < retries:
            sleep(2 * (attempt + 1))
            continue
        if resp.status_code != 200:
            raise StoreError(
                f"HTTP {resp.status_code} en {resp.request.url.path}",
                status=resp.status_code,
                sample=resp.text,
            )
        return resp
    raise StoreError(f"Error de red en {url}: {last_exc}")


def get_json(client: httpx.Client, url: str, *, pacer: Pacer, **kwargs) -> object:
    resp = get(client, url, pacer=pacer, **kwargs)
    try:
        return resp.json()
    except ValueError as exc:
        raise StoreError(
            f"Respuesta no JSON en {resp.request.url.path}", status=resp.status_code, sample=resp.text
        ) from exc

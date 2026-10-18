"""Ahorramás: página de resultados de búsqueda de www.ahorramas.com (HTML).

La web es Salesforce Commerce Cloud (SFRA): cada resultado es un bloque con
`data-pid`, el precio en `.sales .value[content]` y el precio por medida en
`.unit-price-per-unit` ("2,50€/KG.PESO ESC"). Se prueban varias URLs de
búsqueda y se recuerda la primera que devuelve productos.
"""

from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from scraper.matching import Item
from scraper.models import Offer
from scraper.stores.base import Pacer, StoreError, get, make_client
from scraper.units import parse_price_text, parse_unit_price_text

BASE_URL = "https://www.ahorramas.com"
PAGE_SIZE = 48

SEARCH_URLS = (
    f"{BASE_URL}/on/demandware.store/Sites-Ahorramas-Site/es/Search-Show",
    f"{BASE_URL}/buscador",
    f"{BASE_URL}/search",
)

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": f"{BASE_URL}/",
}

NAME_SELECTORS = (".pdp-link a", ".product-name", ".tile-body a.link", "a.link", ".name a")


def _text(node: Tag | None) -> str:
    return " ".join(node.get_text(" ").split()) if node else ""


def _name_and_url(tile: Tag) -> tuple[str, str | None]:
    for selector in NAME_SELECTORS:
        node = tile.select_one(selector)
        if node and _text(node):
            href = node.get("href") or (node.find_parent("a") or {}).get("href")
            if not href:
                link = tile.select_one('a[href$=".html"]')
                href = link.get("href") if link else None
            return _text(node), href
    img = tile.select_one("img[alt]")
    link = tile.select_one('a[href$=".html"]')
    return (img.get("alt", "").strip() if img else ""), (link.get("href") if link else None)


def _price(tile: Tag) -> tuple[float | None, str]:
    """Precio de venta y el texto en que aparece (puede ser '/kg')."""
    sales = tile.select_one(".sales")
    value = (sales or tile).select_one(".value[content]")
    text = _text(sales)
    if value is not None:
        try:
            return float(value["content"]), text
        except (TypeError, ValueError):
            pass
    return (parse_price_text(text) if text else None), text


def _unit_price(tile: Tag) -> tuple[str | None, float | None, str | None]:
    raw = None
    for node in tile.select(".unit-price-per-unit"):
        if node.find_parent(class_="strike-through") or "strike-through" in (node.get("class") or []):
            continue
        raw = _text(node)
        unit, value = parse_unit_price_text(raw)
        if unit is not None:
            return unit, value, raw
    return None, None, raw


def _image(tile: Tag) -> str | None:
    img = tile.select_one("img")
    if img is None:
        return None
    src = img.get("data-src") or img.get("src")
    return urljoin(BASE_URL, src) if src else None


def parse_results(html: str) -> list[Offer]:
    soup = BeautifulSoup(html, "html.parser")
    offers: dict[str, Offer] = {}
    for tile in soup.select("[data-pid]"):
        pid = tile.get("data-pid")
        if not pid or pid in offers:
            continue
        price, price_text = _price(tile)
        if price is None:
            continue
        name, href = _name_and_url(tile)
        if not name:
            continue
        unit, unit_price, unit_raw = _unit_price(tile)
        if "/" in price_text:
            # Producto al peso: el precio publicado ya es por kilo.
            unit, unit_price = parse_unit_price_text(price_text)
            unit_raw = price_text
        offers[pid] = Offer(
            store="ahorramas",
            product_id=str(pid),
            name=name,
            price=round(price, 2),
            unit=unit,
            unit_price=unit_price,
            url=urljoin(BASE_URL, href) if href else f"{BASE_URL}/{pid}.html",
            image=_image(tile),
            unit_raw=unit_raw,
        )
    return list(offers.values())


class Ahorramas:
    id = "ahorramas"
    nombre = "Ahorramás"

    def __init__(self, client: httpx.Client | None = None, pacer: Pacer | None = None):
        self.client = client or make_client(HEADERS)
        self.pacer = pacer or Pacer(1.5)
        self.search_url: str | None = None

    def search(self, item: Item) -> list[Offer]:
        params = {"q": item.busqueda, "sz": PAGE_SIZE, "start": 0}
        if self.search_url is not None:
            resp = get(self.client, self.search_url, pacer=self.pacer, params=params)
            return parse_results(resp.text)
        last_error: StoreError | None = None
        sample = None
        for url in SEARCH_URLS:
            try:
                resp = get(self.client, url, pacer=self.pacer, params=params, retries=0)
            except StoreError as exc:
                last_error = exc
                if exc.blocked:
                    raise
                continue
            offers = parse_results(resp.text)
            if offers:
                self.search_url = url
                return offers
            sample = resp.text
        if last_error is not None and sample is None:
            raise last_error
        raise StoreError("Ninguna URL de búsqueda de Ahorramás devolvió productos", sample=sample)

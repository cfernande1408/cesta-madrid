"""Aldi: fichas de producto de www.aldi.es.

Aldi no vende alimentación online en España, pero publica su surtido con
precios. No hay buscador accesible sin JavaScript, así que:

1. Se lee el sitemap de productos (una petición): cada URL lleva el nombre
   del producto en el slug, /producto/leche-semidesnatada-123400.html.
2. Para cada artículo de la cesta se filtran en local los slugs con sus
   palabras exigidas y excluidas.
3. Solo se descargan las fichas candidatas. Cada ficha trae, en el JSON de
   Next.js (__NEXT_DATA__), el precio y el precio por kg/L de la península.

robots.txt permite /producto/ y el sitemap.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from scraper.matching import Item, matches_text
from scraper.models import Offer
from scraper.stores.base import Pacer, StoreError, get, make_client
from scraper.units import parse_size, to_base

BASE_URL = "https://www.aldi.es"
SITEMAP_URL = f"{BASE_URL}/sitemaps/.aldi-nord-sitemap-products.xml"
MAX_CANDIDATES = 8  # fichas por artículo, para no descargar de más

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": f"{BASE_URL}/productos.html",
}

_PRODUCT_URL = re.compile(r"<loc>\s*(https://www\.aldi\.es/producto/([a-z0-9-]+?)-(\d+)\.html)\s*</loc>")
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


@dataclass(frozen=True)
class Entry:
    product_id: str
    url: str
    text: str  # el slug como texto: "leche semidesnatada"


def parse_sitemap(xml: str) -> list[Entry]:
    entries = [
        Entry(product_id=pid, url=url, text=slug.replace("-", " "))
        for url, slug, pid in _PRODUCT_URL.findall(xml)
    ]
    if not entries:
        raise StoreError("El sitemap de Aldi no trae productos", sample=xml)
    return entries


def _price_now(current: dict, now: datetime) -> tuple[float, float | None, str | None]:
    """(precio, precio por medida, escala) vigentes ahora.

    `currentPrice` puede anunciar ya una promoción que empieza otro día
    (validFrom en el futuro): entonces vale el precio sin promoción.
    """
    price = float(current["priceValue"])
    base = (current.get("basePrice") or [{}])[0]
    base_value = base.get("basePriceValue")
    scale = base.get("basePriceScale")
    strike = (current.get("strikePrice") or {}).get("strikePriceValue")
    ts = now.timestamp()
    valid_from, valid_until = current.get("validFrom"), current.get("validUntil")
    promo_not_active = (valid_from and ts < valid_from) or (valid_until and ts > valid_until)
    if strike and promo_not_active and price > 0:
        if base_value is not None:
            base_value = float(base_value) * float(strike) / price
        price = float(strike)
    return price, (float(base_value) if base_value is not None else None), scale


def parse_product_page(html: str, url: str, now: datetime | None = None) -> Offer | None:
    m = _NEXT_DATA.search(html)
    if not m:
        raise StoreError("Ficha de Aldi sin __NEXT_DATA__", sample=html)
    data = json.loads(m.group(1))
    api = data.get("props", {}).get("pageProps", {}).get("apiData")
    if isinstance(api, str):
        api = json.loads(api)
    for entry in api or []:
        if isinstance(entry, list) and len(entry) == 2 and entry[0] == "PRODUCT_DETAIL_GET":
            products = ((entry[1] or {}).get("res") or {}).get("products") or []
            if products:
                return parse_product(products[0], url, now or datetime.now(UTC))
    return None


def parse_product(p: dict, url: str, now: datetime) -> Offer | None:
    if not p.get("isAvailable", True) or p.get("isRecall") or not p.get("currentPrice"):
        return None
    try:
        price, base_value, scale = _price_now(p["currentPrice"], now)
    except (KeyError, TypeError, ValueError):
        return None
    unit, unit_price = to_base(base_value, scale)
    if unit is None:
        # Sin precio por medida reconocible (p. ej. por metro): se calcula con el tamaño.
        for text in (p.get("salesUnit"), p.get("name")):
            size_unit, qty = parse_size(text)
            if size_unit is not None:
                unit, unit_price = size_unit, price / qty
                break
    image = next((a.get("url") for a in p.get("assets") or [] if a.get("type") == "primary"), None)
    return Offer(
        store="aldi",
        product_id=str(p.get("objectID")),
        name=p.get("name") or "",
        price=round(price, 2),
        unit=unit,
        unit_price=round(unit_price, 4) if unit_price is not None else None,
        url=url,
        image=image,
        brand=p.get("brandName"),
        format=p.get("salesUnit"),
        unit_raw=scale,
    )


class Aldi:
    id = "aldi"
    nombre = "Aldi"

    def __init__(self, client: httpx.Client | None = None, pacer: Pacer | None = None):
        self.client = client or make_client(HEADERS)
        self.pacer = pacer or Pacer(1.5)
        self._entries: list[Entry] | None = None
        self._offers: dict[str, Offer | None] = {}

    def _catalog(self) -> list[Entry]:
        if self._entries is None:
            self._entries = parse_sitemap(get(self.client, SITEMAP_URL, pacer=self.pacer).text)
        return self._entries

    def _offer(self, entry: Entry) -> Offer | None:
        if entry.product_id not in self._offers:
            resp = get(self.client, entry.url, pacer=self.pacer)
            self._offers[entry.product_id] = parse_product_page(resp.text, entry.url)
        return self._offers[entry.product_id]

    def search(self, item: Item) -> list[Offer]:
        candidates = [e for e in self._catalog() if matches_text(item, e.text)]
        # Los nombres más cortos suelen ser el producto básico ("leche semidesnatada").
        candidates.sort(key=lambda e: len(e.text))
        offers = []
        for entry in candidates[:MAX_CANDIDATES]:
            offer = self._offer(entry)
            if offer is not None:
                offers.append(offer)
        return offers

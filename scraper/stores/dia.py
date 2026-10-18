"""Dia: buscador JSON de www.dia.es.

Endpoint observado en el propio frontend de Dia:
GET /api/v1/search-back/search/reduced?q=<texto>&page=1&page_size=<n>

La sesión anónima busca con el código postal por defecto de Dia (28041,
Madrid), así que no hace falta fijarlo.
"""

import httpx

from scraper.matching import Item
from scraper.models import Offer
from scraper.stores.base import Pacer, StoreError, get_json, make_client
from scraper.units import to_base

BASE_URL = "https://www.dia.es"
SEARCH_PATH = "/api/v1/search-back/search/reduced"
PAGE_SIZE = 50

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Referer": f"{BASE_URL}/",
}


def parse_search(payload: object) -> list[Offer]:
    if not isinstance(payload, dict) or not isinstance(payload.get("search_items"), list):
        raise StoreError("Formato inesperado en la búsqueda de Dia", sample=str(payload))
    offers = []
    for raw in payload["search_items"]:
        offer = _parse_item(raw)
        if offer is not None:
            offers.append(offer)
    return offers


def _parse_item(raw: object) -> Offer | None:
    if not isinstance(raw, dict):
        return None
    prices = raw.get("prices") or {}
    try:
        price = float(prices["price"])
        per_unit = float(prices["price_per_unit"])
    except (KeyError, TypeError, ValueError):
        return None
    # Con precio Club Dia, `price` es el de la tarjeta y `strikethrough_price`
    # el que paga todo el mundo. Comparamos con el precio sin tarjeta.
    strike = prices.get("strikethrough_price")
    if prices.get("is_club_price") and isinstance(strike, (int, float)) and price > 0:
        per_unit = per_unit * strike / price
        price = float(strike)
    unit, unit_price = to_base(per_unit, prices.get("measure_unit"))
    pid = raw.get("object_id") or raw.get("sku_id")
    name = raw.get("display_name")
    if not pid or not name:
        return None
    image = raw.get("image")
    return Offer(
        store="dia",
        product_id=str(pid),
        name=name,
        price=round(price, 2),
        unit=unit,
        unit_price=round(unit_price, 4) if unit_price is not None else None,
        url=BASE_URL + raw.get("url", f"/p/{pid}"),
        image=BASE_URL + image if image else None,
        brand=raw.get("brand"),
    )


class Dia:
    id = "dia"
    nombre = "Dia"

    def __init__(self, client: httpx.Client | None = None, pacer: Pacer | None = None):
        self.client = client or make_client(HEADERS)
        self.pacer = pacer or Pacer(1.5)

    def search(self, item: Item) -> list[Offer]:
        payload = get_json(
            self.client,
            BASE_URL + SEARCH_PATH,
            pacer=self.pacer,
            params={"q": item.busqueda, "page": 1, "page_size": PAGE_SIZE},
        )
        return parse_search(payload)

"""Alcampo: buscador JSON de compraonline.alcampo.es.

Endpoint observado en el propio frontend de Alcampo:
GET /api/webproductpagews/v6/product-pages/search?q=<texto>&tag=web&maxPageSize=50

Los productos llegan en productGroups[].decoratedProducts[].
"""

import re

import httpx

from scraper.matching import Item, normalize
from scraper.models import Offer
from scraper.stores.base import Pacer, StoreError, get, get_json, make_client
from scraper.units import to_base

BASE_URL = "https://www.compraonline.alcampo.es"
SEARCH_PATH = "/api/webproductpagews/v6/product-pages/search"
PAGE_SIZE = 50

HEADERS = {
    "Accept": "application/json",
    "Referer": f"{BASE_URL}/",
    "ecom-request-source": "web",
}


def _slug(name: str) -> str:
    return re.sub(r"\s+", "-", normalize(name)) or "producto"


def _amount(node: object) -> float | None:
    if isinstance(node, dict):
        try:
            return float(node["amount"])
        except (KeyError, TypeError, ValueError):
            return None
    return None


def parse_search(payload: object) -> list[Offer]:
    if not isinstance(payload, dict) or not isinstance(payload.get("productGroups"), list):
        raise StoreError("Formato inesperado en la búsqueda de Alcampo", sample=str(payload))
    offers: dict[str, Offer] = {}
    for group in payload["productGroups"]:
        for raw in (group or {}).get("decoratedProducts") or []:
            offer = _parse_product(raw)
            if offer is not None and offer.product_id not in offers:
                offers[offer.product_id] = offer
    return list(offers.values())


def _parse_product(raw: object) -> Offer | None:
    if not isinstance(raw, dict) or raw.get("available") is False:
        return None
    pid = raw.get("retailerProductId")
    name = raw.get("name")
    price = _amount(raw.get("price"))
    if not pid or not name or price is None:
        return None
    unit_price_node = raw.get("unitPrice") or {}
    unit, unit_price = to_base(_amount(unit_price_node.get("price")), unit_price_node.get("unitName"))
    image = (raw.get("image") or {}).get("src")
    return Offer(
        store="alcampo",
        product_id=str(pid),
        name=name,
        price=round(price, 2),
        unit=unit,
        unit_price=unit_price,
        url=f"{BASE_URL}/products/{_slug(name)}/{pid}",
        image=image,
        brand=raw.get("brand"),
        format=raw.get("packSizeDescription"),
    )


class Alcampo:
    id = "alcampo"
    nombre = "Alcampo"

    def __init__(self, client: httpx.Client | None = None, pacer: Pacer | None = None):
        self.client = client or make_client(HEADERS)
        # El WAF de Alcampo corta las ráfagas: peticiones bien espaciadas.
        self.pacer = pacer or Pacer(6.0)
        self._warmed_up = False

    def _warm_up(self) -> None:
        """Visita la portada una vez para recibir las cookies de sesión."""
        if self._warmed_up:
            return
        self._warmed_up = True
        try:
            get(self.client, BASE_URL + "/", pacer=self.pacer, retries=0)
        except StoreError:
            pass  # Si falla, la búsqueda dirá si de verdad estamos bloqueados.

    def search(self, item: Item) -> list[Offer]:
        self._warm_up()
        payload = get_json(
            self.client,
            BASE_URL + SEARCH_PATH,
            pacer=self.pacer,
            params={
                "q": item.busqueda[:50],
                "tag": "web",
                "maxPageSize": PAGE_SIZE,
                "maxProductsToDecorate": PAGE_SIZE,
            },
        )
        return parse_search(payload)

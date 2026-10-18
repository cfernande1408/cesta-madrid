"""Mercadona: catálogo completo de tienda.mercadona.es por categorías.

La tienda online no expone un buscador propio (usa un servicio externo),
pero sí el catálogo por categorías con precios:
  GET /api/categories/?lang=es&wh=<almacén>          árbol de categorías
  GET /api/categories/<id>/?lang=es&wh=<almacén>     productos de una categoría

Se descarga el catálogo una vez por ejecución (~150 peticiones, pausadas)
y la búsqueda de cada artículo se hace en local. Los precios dependen del
almacén; "mad1" sirve a Madrid.
"""

from collections.abc import Iterator

import httpx

from scraper.matching import Item
from scraper.models import Offer
from scraper.stores.base import Pacer, StoreError, get_json, make_client
from scraper.units import to_base

BASE_URL = "https://tienda.mercadona.es"
API = f"{BASE_URL}/api"
DEFAULT_WAREHOUSE = "mad1"

HEADERS = {"Accept": "application/json", "Referer": f"{BASE_URL}/"}


def iter_second_level_ids(root: object) -> list[int]:
    if not isinstance(root, dict) or not isinstance(root.get("results"), list):
        raise StoreError("Formato inesperado en las categorías de Mercadona", sample=str(root))
    ids = []
    for top in root["results"]:
        for cat in (top or {}).get("categories") or []:
            if isinstance(cat.get("id"), int):
                ids.append(cat["id"])
    return ids


def iter_raw_products(node: object) -> Iterator[dict]:
    """Recorre una categoría (con subcategorías anidadas) y devuelve sus productos."""
    if isinstance(node, dict):
        for product in node.get("products") or []:
            if isinstance(product, dict):
                yield product
        for key, value in node.items():
            if key != "products":
                yield from iter_raw_products(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_raw_products(value)


def _format(raw: dict, pi: dict) -> str | None:
    parts = []
    if raw.get("packaging"):
        parts.append(str(raw["packaging"]))
    size, size_format = pi.get("unit_size"), pi.get("size_format")
    if isinstance(size, (int, float)) and size_format:
        parts.append(f"{size:g} {size_format}")
    return " ".join(parts) or None


def parse_product(raw: dict) -> Offer | None:
    pi = raw.get("price_instructions") or {}
    pid, name = raw.get("id"), raw.get("display_name")
    try:
        price = float(pi["unit_price"])
    except (KeyError, TypeError, ValueError):
        return None
    if not pid or not name:
        return None
    try:
        reference = float(pi.get("reference_price"))
    except (TypeError, ValueError):
        reference = None
    unit, unit_price = to_base(reference, pi.get("reference_format"))
    return Offer(
        store="mercadona",
        product_id=str(pid),
        name=name,
        price=round(price, 2),
        unit=unit,
        unit_price=unit_price,
        url=raw.get("share_url") or f"{BASE_URL}/product/{pid}",
        image=raw.get("thumbnail"),
        brand=raw.get("brand"),
        format=_format(raw, pi),
    )


def parse_category(payload: object) -> list[Offer]:
    return [o for o in map(parse_product, iter_raw_products(payload)) if o is not None]


class Mercadona:
    id = "mercadona"
    nombre = "Mercadona"

    def __init__(
        self,
        client: httpx.Client | None = None,
        pacer: Pacer | None = None,
        warehouse: str = DEFAULT_WAREHOUSE,
    ):
        self.client = client or make_client(HEADERS)
        self.pacer = pacer or Pacer(1.0)
        self.warehouse = warehouse
        self._catalog: list[Offer] | None = None
        self.failed_categories = 0

    def _params(self) -> dict:
        return {"lang": "es", "wh": self.warehouse}

    def load_catalog(self) -> list[Offer]:
        root = get_json(self.client, f"{API}/categories/", pacer=self.pacer, params=self._params())
        ids = iter_second_level_ids(root)
        if not ids:
            raise StoreError("Mercadona no ha devuelto categorías", sample=str(root))
        offers: dict[str, Offer] = {}
        last_error: StoreError | None = None
        for cid in ids:
            try:
                payload = get_json(
                    self.client, f"{API}/categories/{cid}/", pacer=self.pacer, params=self._params()
                )
            except StoreError as exc:
                self.failed_categories += 1
                last_error = exc
                if exc.status in (403, 429):
                    raise  # Bloqueo: mejor parar que insistir.
                continue
            for offer in parse_category(payload):
                offers.setdefault(offer.product_id, offer)
        if self.failed_categories > len(ids) // 2:
            raise StoreError(
                f"Fallaron {self.failed_categories} de {len(ids)} categorías: {last_error}",
                status=last_error.status if last_error else None,
                sample=last_error.sample if last_error else None,
            )
        return list(offers.values())

    def search(self, item: Item) -> list[Offer]:
        if self._catalog is None:
            self._catalog = self.load_catalog()
        return self._catalog

import json
from pathlib import Path

import httpx
import pytest

from scraper.matching import Item, best_offer
from scraper.stores.base import Pacer, StoreError
from scraper.stores.mercadona import Mercadona, iter_second_level_ids, parse_category

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = json.loads((FIXTURES / "mercadona_categories.json").read_text())
CAT_72 = json.loads((FIXTURES / "mercadona_category_72.json").read_text())

LECHE = Item(id="leche", nombre="Leche semidesnatada", busqueda="leche semidesnatada", unidad="l")


def test_second_level_ids():
    assert iter_second_level_ids(ROOT) == [77, 72, 112]


def test_parse_category_walks_nested_levels():
    offers = {o.product_id: o for o in parse_category(CAT_72)}
    assert set(offers) == {"10381", "10380", "10400"}
    pack = offers["10381"]
    assert pack.price == 5.64
    assert (pack.unit, pack.unit_price) == ("l", 0.94)
    assert pack.format == "Pack-6 6 l"
    assert pack.url.endswith("/10381/leche-semidesnatada-hacendado-pack-6")


def make_store(handler) -> Mercadona:
    return Mercadona(client=httpx.Client(transport=httpx.MockTransport(handler)), pacer=Pacer(0))


def test_catalog_is_loaded_once_and_searched_locally():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.url.params["wh"] == "mad1"
        if request.url.path == "/api/categories/":
            return httpx.Response(200, json=ROOT)
        if request.url.path == "/api/categories/72/":
            return httpx.Response(200, json=CAT_72)
        return httpx.Response(200, json={"id": 1, "categories": []})

    store = make_store(handler)
    best = best_offer(LECHE, store.search(LECHE))
    store.search(LECHE)
    assert best.product_id == "10381"
    assert calls.count("/api/categories/") == 1
    assert len(calls) == 4


def test_blocked_category_aborts():
    def handler(request):
        if request.url.path == "/api/categories/":
            return httpx.Response(200, json=ROOT)
        return httpx.Response(403, text="blocked")

    with pytest.raises(StoreError) as exc:
        make_store(handler).search(LECHE)
    assert exc.value.status == 403


def test_some_failed_categories_are_tolerated():
    def handler(request):
        if request.url.path == "/api/categories/":
            return httpx.Response(200, json=ROOT)
        if request.url.path == "/api/categories/72/":
            return httpx.Response(200, json=CAT_72)
        if request.url.path == "/api/categories/77/":
            return httpx.Response(404, json={"detail": "not found"})
        return httpx.Response(200, json={"categories": []})

    store = make_store(handler)
    assert len(store.search(LECHE)) == 3
    assert store.failed_categories == 1

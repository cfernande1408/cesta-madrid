import json
from pathlib import Path

import httpx
import pytest

from scraper.matching import Item
from scraper.stores.alcampo import Alcampo, parse_search
from scraper.stores.base import Pacer, StoreError

FIXTURE = json.loads((Path(__file__).parent / "fixtures/alcampo_search_leche.json").read_text())


def test_parse_search_maps_fields_and_dedupes():
    offers = parse_search(FIXTURE)
    ids = [o.product_id for o in offers]
    assert ids == ["54180", "90610", "88888"]
    pack = offers[0]
    assert pack.price == 5.28
    assert (pack.unit, pack.unit_price) == ("l", 0.88)
    assert pack.format == "6000ml"
    assert pack.url.startswith("https://www.compraonline.alcampo.es/products/auchan-leche-")
    assert pack.url.endswith("/54180")


def test_unavailable_products_are_skipped():
    assert "77777" not in {o.product_id for o in parse_search(FIXTURE)}


def test_product_without_unit_price_has_no_unit():
    sin_unidad = {o.product_id: o for o in parse_search(FIXTURE)}["88888"]
    assert sin_unidad.unit is None and sin_unidad.unit_price is None


def test_unexpected_payload_raises():
    with pytest.raises(StoreError):
        parse_search({"message": "Forbidden"})


def test_search_warms_up_once_then_queries():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        assert request.url.params["tag"] == "web"
        return httpx.Response(200, json=FIXTURE)

    store = Alcampo(client=httpx.Client(transport=httpx.MockTransport(handler)), pacer=Pacer(0))
    item = Item(id="l", nombre="Leche", busqueda="leche semidesnatada", unidad="l")
    store.search(item)
    store.search(item)
    assert paths == [
        "/",
        "/api/webproductpagews/v6/product-pages/search",
        "/api/webproductpagews/v6/product-pages/search",
    ]


def test_waf_challenge_counts_as_block():
    def handler(request):
        if request.url.path == "/":
            return httpx.Response(200, text="ok")
        return httpx.Response(202, headers={"x-amzn-waf-action": "challenge"}, text="")

    store = Alcampo(client=httpx.Client(transport=httpx.MockTransport(handler)), pacer=Pacer(0))
    with pytest.raises(StoreError) as exc:
        store.search(Item(id="l", nombre="Leche", busqueda="leche", unidad="l"))
    assert exc.value.blocked

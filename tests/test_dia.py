import json
from pathlib import Path

import httpx
import pytest

from scraper.matching import Item
from scraper.stores.base import Pacer, StoreError
from scraper.stores.dia import Dia, parse_search

FIXTURE = json.loads((Path(__file__).parent / "fixtures/dia_search_leche.json").read_text())


def test_parse_search_maps_fields():
    offers = {o.product_id: o for o in parse_search(FIXTURE)}
    pack = offers["504P6"]
    assert pack.name == "Leche semidesnatada Dia Láctea pack 6 x 1 L"
    assert pack.price == 4.98
    assert (pack.unit, pack.unit_price) == ("l", 0.83)
    assert pack.url == "https://www.dia.es/huevos-leche-y-mantequilla/leche/p/504P6"
    assert pack.image.startswith("https://www.dia.es/product_images/")


def test_club_price_uses_price_for_everyone():
    asturiana = {o.product_id: o for o in parse_search(FIXTURE)}["16065"]
    assert asturiana.price == 1.25
    assert asturiana.unit_price == pytest.approx(1.25)


def test_hundred_ml_is_converted_to_litre():
    batido = {o.product_id: o for o in parse_search(FIXTURE)}["300"]
    assert (batido.unit, batido.unit_price) == ("l", 2.25)


def test_broken_items_are_skipped():
    assert "999" not in {o.product_id for o in parse_search(FIXTURE)}


def test_unexpected_payload_raises():
    with pytest.raises(StoreError):
        parse_search({"error": "blocked"})


def test_search_sends_query_and_parses():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        return httpx.Response(200, json=FIXTURE)

    store = Dia(client=httpx.Client(transport=httpx.MockTransport(handler)), pacer=Pacer(0))
    item = Item(id="leche", nombre="Leche semidesnatada", busqueda="leche semidesnatada", unidad="l")
    offers = store.search(item)
    assert seen["url"].path == "/api/v1/search-back/search/reduced"
    assert seen["url"].params["q"] == "leche semidesnatada"
    assert len(offers) == 4


def test_search_blocked_raises_with_status():
    def handler(request):
        return httpx.Response(403, text="<html>Access Denied</html>")

    store = Dia(client=httpx.Client(transport=httpx.MockTransport(handler)), pacer=Pacer(0))
    with pytest.raises(StoreError) as exc:
        store.search(Item(id="x", nombre="x", busqueda="x", unidad="l"))
    assert exc.value.status == 403
    assert "Access Denied" in exc.value.sample

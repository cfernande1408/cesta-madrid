from pathlib import Path

import httpx
import pytest

from scraper.matching import Item
from scraper.stores.ahorramas import SEARCH_URLS, Ahorramas, parse_results
from scraper.stores.base import Pacer, StoreError

HTML = (Path(__file__).parent / "fixtures/ahorramas_search_leche.html").read_text()
ITEM = Item(id="leche", nombre="Leche semidesnatada", busqueda="leche semidesnatada", unidad="l")


def offers_by_id():
    return {o.product_id: o for o in parse_results(HTML)}


def test_parses_tiles_with_price():
    assert set(offers_by_id()) == {"2", "44569", "3"}


def test_basic_tile():
    leche = offers_by_id()["2"]
    assert leche.name == "Leche semidesnatada Ahorramás 1L"
    assert leche.price == 0.89
    assert (leche.unit, leche.unit_price) == ("l", 0.89)
    assert leche.url == "https://www.ahorramas.com/leche-semidesnatada-ahorramas-1l-2.html"
    assert leche.image == "https://www.ahorramas.com/dw/image/v2/leche.jpg"


def test_promo_ignores_struck_through_prices():
    pascual = offers_by_id()["44569"]
    assert pascual.price == 1.50
    assert (pascual.unit, pascual.unit_price) == ("l", 1.0)
    assert pascual.url.endswith("-44569.html")


def test_product_sold_by_weight():
    platano = offers_by_id()["3"]
    assert platano.price == 2.49
    assert (platano.unit, platano.unit_price) == ("kg", 2.49)


def store_with(handler) -> Ahorramas:
    return Ahorramas(client=httpx.Client(transport=httpx.MockTransport(handler)), pacer=Pacer(0))


def test_falls_back_to_next_search_url_and_remembers_it():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url).split("?")[0])
        if str(request.url).startswith(SEARCH_URLS[0]):
            return httpx.Response(404, text="not found")
        return httpx.Response(200, text=HTML)

    store = store_with(handler)
    assert len(store.search(ITEM)) == 3
    assert store.search_url == SEARCH_URLS[1]
    store.search(ITEM)
    assert calls == [SEARCH_URLS[0], SEARCH_URLS[1], SEARCH_URLS[1]]


def test_no_results_anywhere_raises_with_sample():
    def handler(request):
        return httpx.Response(200, text="<html><body>Sin resultados</body></html>")

    with pytest.raises(StoreError) as exc:
        store_with(handler).search(ITEM)
    assert "Sin resultados" in exc.value.sample


def test_blocked_stops_immediately():
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(403, text="Forbidden")

    with pytest.raises(StoreError):
        store_with(handler).search(ITEM)
    assert len(calls) == 1

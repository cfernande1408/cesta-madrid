from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from scraper.matching import Item, best_offer
from scraper.stores.aldi import Aldi, parse_product_page, parse_sitemap
from scraper.stores.base import Pacer, StoreError

FIXTURES = Path(__file__).parent / "fixtures"
SITEMAP = (FIXTURES / "aldi_sitemap.xml").read_text()
NARANJA = (FIXTURES / "aldi_producto_naranja.html").read_text()
LECHE = (FIXTURES / "aldi_producto_leche.html").read_text()

# La promo de la naranja va del 19 al 25 de octubre de 2026 (hora de Madrid).
ANTES_DE_LA_PROMO = datetime(2026, 10, 18, 12, tzinfo=UTC)
DURANTE_LA_PROMO = datetime(2026, 10, 20, 12, tzinfo=UTC)


def test_sitemap_entries():
    entries = parse_sitemap(SITEMAP)
    assert [e.product_id for e in entries] == ["994500", "123400", "123500", "555500"]
    assert entries[1].text == "leche semidesnatada"
    assert entries[1].url == "https://www.aldi.es/producto/leche-semidesnatada-123400.html"


def test_empty_sitemap_raises():
    with pytest.raises(StoreError):
        parse_sitemap("<urlset></urlset>")


def test_product_page_regular_price():
    offer = parse_product_page(LECHE, "https://www.aldi.es/producto/leche-semidesnatada-123400.html")
    assert offer.name == "Leche semidesnatada"
    assert offer.price == 0.82
    assert (offer.unit, offer.unit_price) == ("l", 0.82)
    assert offer.format == "1 l"
    assert offer.image.endswith("/leche")


def test_promo_counts_only_while_active():
    url = "https://www.aldi.es/producto/naranja-de-mesa-994500.html"
    antes = parse_product_page(NARANJA, url, now=ANTES_DE_LA_PROMO)
    assert antes.price == 2.45
    assert antes.unit_price == pytest.approx(2.45)
    durante = parse_product_page(NARANJA, url, now=DURANTE_LA_PROMO)
    assert durante.price == 1.69
    assert (durante.unit, durante.unit_price) == ("kg", 1.69)


def test_page_without_next_data_raises():
    with pytest.raises(StoreError):
        parse_product_page("<html></html>", "https://www.aldi.es/producto/x-1.html")


def test_search_downloads_only_matching_candidates_once():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("products.xml"):
            return httpx.Response(200, text=SITEMAP)
        if "leche-semidesnatada-123400" in request.url.path:
            return httpx.Response(200, text=LECHE)
        return httpx.Response(404, text="no")

    store = Aldi(client=httpx.Client(transport=httpx.MockTransport(handler)), pacer=Pacer(0))
    item = Item(id="leche", nombre="Leche semidesnatada", busqueda="leche semidesnatada",
                unidad="l", excluir=("sin lactosa",))
    offers = store.search(item)
    store.search(item)
    assert best_offer(item, offers).product_id == "123400"
    assert calls == ["/sitemaps/.aldi-nord-sitemap-products.xml", "/producto/leche-semidesnatada-123400.html"]

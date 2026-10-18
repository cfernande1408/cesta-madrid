import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scraper.models import Offer
from scraper.run import load_cesta, run
from scraper.stores.base import StoreError

ROOT = Path(__file__).resolve().parent.parent

CESTA = {
    "ajustes": {"supermercados": ["bueno", "bloqueado", "roto"]},
    "articulos": [
        {"id": "leche", "nombre": "Leche semidesnatada", "busqueda": "leche semidesnatada", "unidad": "l", "cantidad": 6},
        {"id": "arroz", "nombre": "Arroz redondo", "busqueda": "arroz redondo", "unidad": "kg"},
    ],
}


def offer(store, name, unit_price, unit):
    return Offer(store=store, product_id=name, name=name, price=unit_price, unit=unit,
                 unit_price=unit_price, url="https://x")


class Bueno:
    id, nombre = "bueno", "Bueno"

    def search(self, item):
        return [offer("bueno", "Leche semidesnatada marca", 0.9, "l"),
                offer("bueno", "Leche semidesnatada barata", 0.8, "l"),
                offer("bueno", "Arroz redondo", 1.1, "kg")]


class Bloqueado:
    id, nombre = "bloqueado", "Bloqueado"

    def __init__(self):
        self.calls = 0

    def search(self, item):
        self.calls += 1
        raise StoreError("HTTP 403", status=403, sample="Access Denied")


class Roto:
    id, nombre = "roto", "Roto"

    def search(self, item):
        raise KeyError("campo")


@pytest.fixture
def cesta(tmp_path):
    path = tmp_path / "cesta.json"
    path.write_text(json.dumps(CESTA))
    return path


def factory(stores):
    return lambda store_id, ajustes: stores[store_id]


def test_run_writes_best_offers_and_status(cesta, tmp_path):
    out = tmp_path / "data"
    bloqueado = Bloqueado()
    stores = {"bueno": Bueno(), "bloqueado": bloqueado, "roto": Roto()}
    estado = run(cesta, out, store_factory=factory(stores), now=datetime(2026, 10, 18, tzinfo=UTC))

    precios = json.loads((out / "precios.json").read_text())
    leche = precios["articulos"][0]
    assert leche["cantidad"] == 6
    assert leche["ofertas"]["bueno"]["name"] == "Leche semidesnatada barata"
    assert "bloqueado" not in leche["ofertas"]

    by_id = {s["id"]: s for s in precios["supermercados"]}
    assert by_id["bueno"]["ok"] and by_id["bueno"]["encontrados"] == 2
    assert not by_id["bloqueado"]["ok"] and by_id["bloqueado"]["actualizado"] is None

    assert bloqueado.calls == 1  # un 403 corta en seco
    assert estado["supermercados"]["bloqueado"]["muestra"] == "Access Denied"
    assert "KeyError" in estado["supermercados"]["roto"]["mensaje"]
    assert estado["articulos"]["leche"]["bueno"]["validos"] == 2


def test_failed_store_keeps_previous_data(cesta, tmp_path):
    out = tmp_path / "data"
    first = {"bueno": Bueno(), "bloqueado": Bueno(), "roto": Roto()}
    first["bloqueado"].id = "bloqueado"
    run(cesta, out, store_factory=factory(first), now=datetime(2026, 10, 17, tzinfo=UTC))

    second = {"bueno": Bueno(), "bloqueado": Bloqueado(), "roto": Roto()}
    run(cesta, out, store_factory=factory(second), now=datetime(2026, 10, 18, tzinfo=UTC))

    precios = json.loads((out / "precios.json").read_text())
    by_id = {s["id"]: s for s in precios["supermercados"]}
    assert by_id["bloqueado"]["actualizado"] == "2026-10-17T00:00:00+00:00"
    assert not by_id["bloqueado"]["ok"]
    assert "bloqueado" in precios["articulos"][0]["ofertas"]


def test_history_is_appended(cesta, tmp_path):
    out = tmp_path / "data"
    stores = {"bueno": Bueno(), "bloqueado": Bloqueado(), "roto": Roto()}
    for day in (17, 18):
        run(cesta, out, store_factory=factory(stores), now=datetime(2026, 10, day, tzinfo=UTC))
    rows = list(csv.DictReader((out / "historial.csv").open()))
    assert len(rows) == 4
    assert rows[0]["fecha"] == "2026-10-17" and rows[-1]["fecha"] == "2026-10-18"


def test_only_flag_skips_other_stores(cesta, tmp_path):
    out = tmp_path / "data"
    bloqueado = Bloqueado()
    stores = {"bueno": Bueno(), "bloqueado": bloqueado, "roto": Roto()}
    run(cesta, out, only=["bueno"], store_factory=factory(stores))
    assert bloqueado.calls == 0


def test_real_cesta_is_valid():
    ajustes, items = load_cesta(ROOT / "cesta.json")
    assert set(ajustes["supermercados"]) <= {"mercadona", "dia", "alcampo", "ahorramas"}
    assert len(items) >= 30
    assert all(i.unidad in {"kg", "l", "ud"} for i in items)
    assert all(i.cantidad > 0 for i in items)

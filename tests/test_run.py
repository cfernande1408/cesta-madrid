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
    assert set(ajustes["supermercados"]) <= {"mercadona", "dia", "aldi", "alcampo", "ahorramas"}
    assert len(items) >= 30
    assert all(i.unidad in {"kg", "l", "ud"} for i in items)
    assert all(i.cantidad > 0 for i in items)


def test_rejected_sample_lists_similar_products():
    from scraper.matching import Item
    from scraper.run import rejected_sample

    item = Item(id="huevos", nombre="Huevos", busqueda="huevos", unidad="ud")
    offers = [offer("m", "Huevo campero L", 3.0, "docena?"), offer("m", "Arroz", 1.0, "kg")]
    sample = rejected_sample(item, offers)
    assert [s["nombre"] for s in sample] == ["Huevo campero L"]


def test_waf_block_stops_store_immediately(cesta, tmp_path):
    class Waf:
        id, nombre = "bloqueado", "Waf"

        def __init__(self):
            self.calls = 0

        def search(self, item):
            self.calls += 1
            raise StoreError("HTTP 202", status=202)

    waf = Waf()
    run(cesta, tmp_path / "d", store_factory=factory({"bueno": Bueno(), "bloqueado": waf, "roto": Roto()}))
    assert waf.calls == 1


class Guion:
    """Súper falso que responde según un guion: item_id -> lista de ofertas o excepción."""

    def __init__(self, store_id, guion):
        self.id, self.nombre, self.guion, self.orden = store_id, store_id.title(), guion, []

    def search(self, item):
        self.orden.append(item.id)
        res = self.guion[item.id]
        if isinstance(res, Exception):
            raise res
        return res


def run_with(cesta, out, stores, day):
    return run(cesta, out, store_factory=factory(stores), now=datetime(2026, 10, day, 6, tzinfo=UTC))


def leche_y_arroz(store_id, leche=0.8, arroz=1.1):
    return {
        "leche": [offer(store_id, "Leche semidesnatada", leche, "l")],
        "arroz": [offer(store_id, "Arroz redondo", arroz, "kg")],
    }


def ofertas(out):
    precios = json.loads((out / "precios.json").read_text())
    return {a["id"]: a["ofertas"] for a in precios["articulos"]}, {s["id"]: s for s in precios["supermercados"]}


def test_partial_block_keeps_older_offers_and_rotates(cesta, tmp_path):
    out = tmp_path / "data"
    stores = {"bueno": Guion("bueno", leche_y_arroz("bueno")),
              "bloqueado": Guion("bloqueado", leche_y_arroz("bloqueado")),
              "roto": Guion("roto", leche_y_arroz("roto"))}
    run_with(cesta, out, stores, 10)

    blocked = StoreError("HTTP 202", status=202)
    guion = {"leche": [offer("bloqueado", "Leche semidesnatada", 0.7, "l")], "arroz": blocked}
    stores["bloqueado"] = Guion("bloqueado", guion)
    run_with(cesta, out, stores, 11)

    of, st = ofertas(out)
    assert of["leche"]["bloqueado"]["unit_price"] == 0.7
    assert of["leche"]["bloqueado"]["fecha"] == "2026-10-11"
    assert of["arroz"]["bloqueado"]["fecha"] == "2026-10-10"  # se conserva el de ayer
    assert st["bloqueado"]["parcial"] and st["bloqueado"]["ok"]

    # Al día siguiente empieza por el artículo con el precio más antiguo.
    stores["bloqueado"] = Guion("bloqueado", leche_y_arroz("bloqueado"))
    run_with(cesta, out, stores, 12)
    assert stores["bloqueado"].orden == ["arroz", "leche"]


def test_searched_and_not_found_drops_offer(cesta, tmp_path):
    out = tmp_path / "data"
    stores = {sid: Guion(sid, leche_y_arroz(sid)) for sid in ("bueno", "bloqueado", "roto")}
    run_with(cesta, out, stores, 10)
    stores["bueno"] = Guion("bueno", {"leche": [], "arroz": leche_y_arroz("bueno")["arroz"]})
    run_with(cesta, out, stores, 11)
    of, _ = ofertas(out)
    assert "bueno" not in of["leche"]


def test_offers_older_than_two_weeks_are_dropped(cesta, tmp_path):
    out = tmp_path / "data"
    stores = {sid: Guion(sid, leche_y_arroz(sid)) for sid in ("bueno", "bloqueado", "roto")}
    run_with(cesta, out, stores, 1)
    caido = StoreError("HTTP 403", status=403)
    stores["bloqueado"] = Guion("bloqueado", {"leche": caido, "arroz": caido})
    run_with(cesta, out, stores, 15)
    of, _ = ofertas(out)
    assert "bloqueado" in of["leche"]
    run_with(cesta, out, stores, 16)
    of, st = ofertas(out)
    assert "bloqueado" not in of["leche"]
    assert st["bloqueado"]["encontrados"] == 0


def test_rejected_sample_explains_reason():
    from scraper.matching import Item
    from scraper.run import rejected_sample

    item = Item(id="huevos", nombre="Huevos", busqueda="huevos", unidad="ud", excluir=("chocolate",))
    offers = [
        offer("m", "Huevos grandes L", 0.25, "kg"),
        offer("m", "Huevos de chocolate", 30.0, "ud"),
        offer("m", "Macarrón al huevo", 2.9, "kg"),
    ]
    sample = rejected_sample(item, offers)
    assert [s["motivo"] for s in sample] == ["unidad kg", "excluido por «chocolate»", "unidad kg"]

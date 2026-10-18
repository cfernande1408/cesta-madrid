"""Descarga precios de todos los súper y genera los datos de la web.

Uso:
    python -m scraper.run                 # todos los súper de cesta.json
    python -m scraper.run --solo dia      # solo uno (para probar)

Escribe en web/data/:
    precios.json    la mejor oferta de cada súper para cada artículo (lo lee la web)
    estado.json     diagnóstico de la última ejecución (errores, muestras)
    historial.csv   un registro por artículo, súper y día
"""

import argparse
import csv
import json
import sys
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from scraper.matching import Item, accepts, best_offer
from scraper.models import Offer
from scraper.stores.base import Store, StoreError

ROOT = Path(__file__).resolve().parent.parent
MAX_CONSECUTIVE_ERRORS = 3
HISTORY_FIELDS = ["fecha", "articulo", "supermercado", "precio_unidad", "unidad", "precio", "producto"]


def build_store(store_id: str, ajustes: dict) -> Store:
    from scraper.stores.ahorramas import Ahorramas
    from scraper.stores.alcampo import Alcampo
    from scraper.stores.dia import Dia
    from scraper.stores.mercadona import Mercadona

    if store_id == "mercadona":
        return Mercadona(warehouse=ajustes.get("almacen_mercadona", "mad1"))
    factories = {"dia": Dia, "alcampo": Alcampo, "ahorramas": Ahorramas}
    if store_id not in factories:
        raise ValueError(f"Supermercado desconocido: {store_id}")
    return factories[store_id]()


def load_cesta(path: Path) -> tuple[dict, list[Item]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = [Item.from_dict(d) for d in data["articulos"]]
    ids = [i.id for i in items]
    duplicated = {i for i in ids if ids.count(i) > 1}
    if duplicated:
        raise ValueError(f"IDs repetidos en la cesta: {sorted(duplicated)}")
    return data.get("ajustes", {}), items


def _offer_json(offer: Offer) -> dict:
    data = offer.to_dict()
    data.pop("store")
    return data


def scrape_store(store: Store, items: list[Item]) -> tuple[dict[str, Offer], dict, dict[str, dict]]:
    """Busca todos los artículos en un súper.

    Devuelve (mejores ofertas por artículo, estado del súper, diagnóstico por artículo).
    """
    best: dict[str, Offer] = {}
    diagnostics: dict[str, dict] = {}
    status = {"id": store.id, "nombre": store.nombre, "errores": 0, "mensaje": None, "muestra": None}
    started = time.monotonic()
    consecutive = 0
    for item in items:
        try:
            offers = store.search(item)
        except StoreError as exc:
            status["errores"] += 1
            consecutive += 1
            status["mensaje"] = str(exc)
            status["http"] = exc.status
            status["muestra"] = exc.sample
            if exc.status in (403, 429) or consecutive >= MAX_CONSECUTIVE_ERRORS:
                status["mensaje"] += " (se deja de consultar este súper en esta ejecución)"
                break
            continue
        except Exception as exc:  # Un fallo de programación no debe tumbar al resto.
            status["errores"] += 1
            status["mensaje"] = f"{type(exc).__name__}: {exc}"
            status["muestra"] = traceback.format_exc()[-400:]
            break
        consecutive = 0
        chosen = best_offer(item, offers)
        diagnostics[item.id] = {
            "resultados": len(offers),
            "validos": sum(1 for o in offers if accepts(item, o)),
            "elegido": chosen.name if chosen else None,
        }
        if chosen is not None:
            best[item.id] = chosen
    status["encontrados"] = len(best)
    status["duracion_s"] = round(time.monotonic() - started, 1)
    return best, status, diagnostics


def _previous(out_dir: Path) -> dict:
    path = out_dir / "precios.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def run(
    cesta_path: Path,
    out_dir: Path,
    *,
    only: list[str] | None = None,
    store_factory: Callable[[str, dict], Store] = build_store,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(UTC)
    stamp = now.isoformat(timespec="seconds")
    ajustes, items = load_cesta(cesta_path)
    store_ids = ajustes.get("supermercados", [])
    previous = _previous(out_dir)
    prev_stores = {s["id"]: s for s in previous.get("supermercados", [])}
    prev_offers = {a["id"]: a.get("ofertas", {}) for a in previous.get("articulos", [])}

    offers: dict[str, dict[str, dict]] = {item.id: {} for item in items}
    stores_out, estado_stores, estado_items, history = [], {}, {}, []

    for store_id in store_ids:
        if only and store_id not in only:
            fresh = False
        else:
            try:
                store = store_factory(store_id, ajustes)
            except Exception as exc:
                best, status, diag = {}, {"id": store_id, "nombre": store_id, "errores": 1,
                                          "mensaje": f"No se pudo crear: {exc}", "encontrados": 0}, {}
            else:
                print(f"→ {store.nombre}…", flush=True)
                best, status, diag = scrape_store(store, items)
                print(f"  {status['encontrados']}/{len(items)} artículos, "
                      f"{status['errores']} errores, {status.get('duracion_s')} s", flush=True)
                if status["mensaje"]:
                    print(f"  último error: {status['mensaje']}", flush=True)
            estado_stores[store_id] = status
            for item_id, d in diag.items():
                estado_items.setdefault(item_id, {})[store_id] = d
            fresh = bool(best)

        if fresh:
            for item_id, offer in best.items():
                offers[item_id][store_id] = _offer_json(offer)
                history.append({
                    "fecha": now.date().isoformat(), "articulo": item_id, "supermercado": store_id,
                    "precio_unidad": offer.unit_price, "unidad": offer.unit, "precio": offer.price,
                    "producto": offer.name,
                })
            actualizado = stamp
        else:
            # Sin datos nuevos: se conservan los de la última vez que funcionó.
            for item_id in offers:
                if store_id in prev_offers.get(item_id, {}):
                    offers[item_id][store_id] = prev_offers[item_id][store_id]
            actualizado = prev_stores.get(store_id, {}).get("actualizado")

        prev_name = prev_stores.get(store_id, {}).get("nombre", store_id)
        stores_out.append({
            "id": store_id,
            "nombre": estado_stores.get(store_id, {}).get("nombre", prev_name),
            "ok": fresh,
            "actualizado": actualizado,
            "encontrados": sum(1 for o in offers.values() if store_id in o),
        })

    precios = {
        "generado": stamp,
        "supermercados": stores_out,
        "articulos": [
            {
                "id": item.id, "nombre": item.nombre, "categoria": item.categoria,
                "unidad": item.unidad, "cantidad": item.cantidad, "ofertas": offers[item.id],
            }
            for item in items
        ],
    }
    estado = {"generado": stamp, "supermercados": estado_stores, "articulos": estado_items}

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "precios.json", precios)
    _write_json(out_dir / "estado.json", estado)
    _append_history(out_dir / "historial.csv", history)
    return estado


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_history(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HISTORY_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--cesta", type=Path, default=ROOT / "cesta.json")
    parser.add_argument("--salida", type=Path, default=ROOT / "web" / "data")
    parser.add_argument("--solo", nargs="*", help="IDs de súper a consultar (por defecto, todos)")
    args = parser.parse_args(argv)
    estado = run(args.cesta, args.salida, only=args.solo)
    # Nunca falla por culpa de un súper: el diagnóstico queda en estado.json.
    total = sum(s.get("encontrados", 0) for s in estado["supermercados"].values())
    print(f"Listo: {total} precios nuevos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Sonda temporal (2): páginas de categoría y búsqueda de aldi.es. Guarda muestras en explorar/salida/."""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper.stores.base import BROWSER_HEADERS  # noqa: E402

import httpx  # noqa: E402

OUT = Path(__file__).parent / "salida"
OUT.mkdir(exist_ok=True)
BASE = "https://www.aldi.es"
client = httpx.Client(
    headers={**BROWSER_HEADERS, "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"},
    timeout=30,
    follow_redirects=True,
)
resumen = {}


def next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def analizar(nombre, url):
    time.sleep(2)
    try:
        r = client.get(url)
    except Exception as exc:
        resumen[nombre] = {"url": url, "error": repr(exc)}
        return None
    info = {"url": url, "final": str(r.url), "status": r.status_code, "bytes": len(r.text)}
    (OUT / f"{nombre}.txt").write_text(r.text[:400_000], encoding="utf-8")
    d = next_data(r.text) if "html" in (r.headers.get("content-type") or "") else None
    if d:
        info["page"] = d.get("page")
        pp = d["props"].get("pageProps", {})
        api = pp.get("apiData")
        if isinstance(api, str):
            try:
                api = json.loads(api)
            except ValueError:
                api = None
        llamadas = []
        for entry in api or []:
            if isinstance(entry, list) and len(entry) == 2 and isinstance(entry[1], dict):
                res = entry[1].get("res")
                llamadas.append({
                    "nombre": entry[0],
                    "req": entry[1].get("req"),
                    "tipo_res": type(res).__name__,
                    "muestra_res": json.dumps(res, ensure_ascii=False)[:2500],
                })
        info["api"] = llamadas
    info["precios_en_html"] = re.findall(r"\d+,\d{2}\s*€", r.text)[:10]
    resumen[nombre] = info
    return r.text


html = (OUT / "producto.txt").read_text(encoding="utf-8") if (OUT / "producto.txt").exists() else ""
home = (OUT / "productos.txt").read_text(encoding="utf-8")
chunks = sorted(set(re.findall(r'src="(/_next/static/[^"]+\.js)"', home + html)))
hallazgos = {}
patron = re.compile(r".{0,160}(algolia|ALGOLIA|x-algolia|/api/[a-zA-Z0-9/_-]+|PRODUCT_[A-Z_]+|searchClient|indexName|appId|apiKey).{0,200}")
for src in chunks:
    time.sleep(1)
    try:
        js = client.get(BASE + src).text
    except Exception as exc:
        hallazgos[src] = repr(exc)
        continue
    trozos = [m.group(0) for m in patron.finditer(js)]
    if trozos:
        hallazgos[src] = trozos[:40]
resumen["js"] = hallazgos

(OUT / "resumen4.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(resumen, ensure_ascii=False, indent=1)[:6000])

"""Sonda temporal: cómo sirve aldi.es su catálogo. Guarda muestras en explorar/salida/."""

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

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


def fetch(nombre, url):
    time.sleep(2)
    try:
        r = client.get(url)
    except Exception as exc:
        resumen[nombre] = {"url": url, "error": repr(exc)}
        return None
    texto = r.text
    resumen[nombre] = {
        "url": url,
        "final": str(r.url),
        "status": r.status_code,
        "tipo": r.headers.get("content-type"),
        "bytes": len(texto),
        "server": r.headers.get("server"),
    }
    (OUT / f"{nombre}.txt").write_text(texto[:300_000], encoding="utf-8")
    return texto


robots = fetch("robots", f"{BASE}/robots.txt")
home = fetch("productos", f"{BASE}/productos.html") or ""

# Enlaces a categorías y pistas de API en la página de productos.
enlaces = sorted(set(re.findall(r'href="(/[^"]*productos[^"]*)"', home)))
apis = sorted(set(re.findall(r'["\'](https?://[^"\']*(?:api|graphql|algolia|search)[^"\']*)["\']', home, re.I)))
scripts = sorted(set(re.findall(r'<script[^>]+src="([^"]+)"', home)))
datos = re.findall(r'data-[a-z-]*(?:product|price|config|api)[a-z-]*="([^"]{0,300})', home, re.I)
precios = re.findall(r"\d+,\d{2}\s*€", home)
resumen["pistas"] = {
    "enlaces_productos": enlaces[:80],
    "apis": apis[:40],
    "scripts": scripts[:40],
    "data_attrs": datos[:20],
    "precios_en_html": precios[:20],
}

# Primera categoría que parezca de alimentación: ¿lleva precios en el HTML?
for i, enlace in enumerate([e for e in enlaces if e.count("/") >= 2][:3]):
    html = fetch(f"categoria_{i}", urljoin(BASE, enlace)) or ""
    resumen[f"categoria_{i}"]["precios_en_html"] = re.findall(r"\d+,\d{2}\s*€", html)[:15]
    resumen[f"categoria_{i}"]["json_ld"] = len(re.findall(r"application/ld\+json", html))

sitemap = fetch("sitemap", f"{BASE}/sitemap.xml") or ""
resumen["pistas"]["sitemaps"] = re.findall(r"<loc>([^<]+)</loc>", sitemap)[:40]

(OUT / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(resumen, ensure_ascii=False, indent=1)[:5000])

"""Normalización de unidades y precios por medida.

Cada supermercado expresa el precio por medida a su manera ("LITRO",
"PER_1KG", "2,50€/KG.PESO ESC"...). Aquí se traduce todo a tres unidades
base: kilo ("kg"), litro ("l") y unidad ("ud"), y a un precio por esa
unidad base.
"""

import re

# Cada entrada: texto de unidad (ya normalizado) -> (unidad base, factor).
# precio_base = precio_publicado * factor
# Ej.: "100 g" a 0,50 €  ->  5,00 €/kg  (factor 10)
#      "docena" a 3,05 € ->  0,254 €/ud (factor 1/12)
_UNIT_TABLE: dict[str, tuple[str, float]] = {
    "kg": ("kg", 1.0),
    "kilo": ("kg", 1.0),
    "kilos": ("kg", 1.0),
    "1kg": ("kg", 1.0),
    "kgpesoesc": ("kg", 1.0),
    "kgpesoescurrido": ("kg", 1.0),
    "100g": ("kg", 10.0),
    "100gr": ("kg", 10.0),
    "g": ("kg", 1000.0),
    "l": ("l", 1.0),
    "lt": ("l", 1.0),
    "litro": ("l", 1.0),
    "litros": ("l", 1.0),
    "litre": ("l", 1.0),
    "100ml": ("l", 10.0),
    "ml": ("l", 1000.0),
    "ud": ("ud", 1.0),
    "u": ("ud", 1.0),
    "unidad": ("ud", 1.0),
    "unidades": ("ud", 1.0),
    "each": ("ud", 1.0),
    "unit": ("ud", 1.0),
    "docena": ("ud", 1 / 12),
    "dozen": ("ud", 1 / 12),
}

# Unidades de Alcampo (campo `unitPrice.unitName`).
_ALCAMPO_UNITS: dict[str, tuple[str, float]] = {
    "PER_LITRE": ("l", 1.0),
    "PER_1KG": ("kg", 1.0),
    "PER_KG": ("kg", 1.0),
    "PER_100G": ("kg", 10.0),
    "PER_100ML": ("l", 10.0),
    "PER_EACH": ("ud", 1.0),
    "PER_UNIT": ("ud", 1.0),
    "PER_DOZEN": ("ud", 1 / 12),
}


def _key(text: str) -> str:
    """'100 GR.' -> '100gr'; 'KG.PESO ESC' -> 'kgpesoesc'."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def normalize_unit(text: str | None) -> tuple[str, float] | None:
    """Traduce un texto de unidad a (unidad base, factor), o None si no se conoce."""
    if not text:
        return None
    key = _key(text)
    if key in _UNIT_TABLE:
        return _UNIT_TABLE[key]
    if text.upper() in _ALCAMPO_UNITS:
        return _ALCAMPO_UNITS[text.upper()]
    # "kgpeso..." y similares: nos quedamos con el prefijo conocido.
    for prefix in ("kg", "litro", "docena", "unidad"):
        if key.startswith(prefix):
            return _UNIT_TABLE[prefix]
    return None


def to_base(price: float | None, unit_text: str | None) -> tuple[str | None, float | None]:
    """Convierte un precio por medida publicado a (unidad base, precio base)."""
    if price is None:
        return None, None
    norm = normalize_unit(unit_text)
    if norm is None:
        return None, None
    unit, factor = norm
    return unit, round(price * factor, 4)


_PRICE_PER_UNIT_RE = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?:€|eur)?\s*/\s*(?P<unit>[a-zA-Z0-9. ]+)",
    re.IGNORECASE,
)


def parse_price_text(text: str) -> float | None:
    """'1,65 €' -> 1.65; '1.234,50€' -> 1234.5."""
    m = re.search(r"\d[\d.]*(?:,\d+)?|\d+(?:\.\d+)?", text.replace("\xa0", " "))
    if not m:
        return None
    raw = m.group(0)
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_unit_price_text(text: str) -> tuple[str | None, float | None]:
    """'2,50€/KG.PESO ESC' -> ('kg', 2.5); '0,99 €/L' -> ('l', 0.99)."""
    m = _PRICE_PER_UNIT_RE.search(text.replace("\xa0", " "))
    if not m:
        return None, None
    value = parse_price_text(m.group("num"))
    return to_base(value, m.group("unit").strip())

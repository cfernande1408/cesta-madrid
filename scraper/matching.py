"""Elegir, para cada artículo de la cesta, la oferta más barata de cada súper.

Un artículo de la cesta es genérico ("leche semidesnatada") y se define en
cesta.json con palabras que deben aparecer (`incluir`), palabras que lo
descartan (`excluir`) y la unidad en la que se compara (`unidad`). Entre los
productos que cumplen, gana el de menor precio por unidad base.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

from scraper.models import Offer

STOPWORDS = frozenset(
    "de del la las el los y e con sin en a al para por un una unos unas".split()
)


def normalize(text: str) -> str:
    """Minúsculas, sin tildes y con espacios simples: 'Plátano  Canarias' -> 'platano canarias'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9ñ]+", " ", text.lower())
    return " ".join(text.split())


def tokens(text: str) -> list[str]:
    """Palabras significativas de un texto, sin stopwords."""
    return [t for t in normalize(text).split() if t not in STOPWORDS]


def contains(haystack: str, phrase: str) -> bool:
    """¿Aparece `phrase` (normalizada) como palabras completas en `haystack`?

    `phrase` admite alternativas separadas por "|": "espagueti|spaghetti".
    """
    for alternative in phrase.split("|"):
        needle = normalize(alternative)
        if not needle:
            return True
        if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack):
            return True
    return False


@dataclass(frozen=True)
class Item:
    """Un artículo genérico de la cesta (una entrada de cesta.json)."""

    id: str
    nombre: str
    busqueda: str
    unidad: str
    cantidad: float = 1.0
    categoria: str = "Otros"
    incluir: tuple[str, ...] = ()
    excluir: tuple[str, ...] = ()
    fijar: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        return cls(
            id=data["id"],
            nombre=data["nombre"],
            busqueda=data.get("busqueda", data["nombre"]),
            unidad=data["unidad"],
            cantidad=float(data.get("cantidad", 1)),
            categoria=data.get("categoria", "Otros"),
            incluir=tuple(data.get("incluir", ())),
            excluir=tuple(data.get("excluir", ())),
            fijar=dict(data.get("fijar", {})),
        )

    def required_phrases(self) -> tuple[str, ...]:
        """Lo que el nombre del producto tiene que contener.

        Si `incluir` está vacío se exigen todas las palabras de la búsqueda.
        """
        if self.incluir:
            return self.incluir
        return tuple(tokens(self.busqueda))


def accepts(item: Item, offer: Offer) -> bool:
    """¿Sirve esta oferta para este artículo?"""
    if offer.unit != item.unidad or offer.unit_price is None or offer.unit_price <= 0:
        return False
    name = normalize(offer.name)
    if not all(contains(name, p) for p in item.required_phrases()):
        return False
    return not any(contains(name, p) for p in item.excluir)


def best_offer(item: Item, offers: Iterable[Offer]) -> Offer | None:
    """La oferta más barata por unidad base que sirve para el artículo.

    Si el artículo fija un producto concreto para este súper (`fijar`), se
    usa ese aunque no sea el más barato, siempre que aparezca y tenga precio.
    """
    offers = list(offers)
    if not offers:
        return None
    pinned = item.fijar.get(offers[0].store)
    if pinned is not None:
        for offer in offers:
            if offer.product_id == pinned and offer.unit_price:
                return offer
    candidates = [o for o in offers if accepts(item, o)]
    if not candidates:
        return None
    return min(candidates, key=lambda o: (o.unit_price, o.price, o.name))

"""Tipos compartidos por los adaptadores y el comparador."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Offer:
    """Un producto concreto de un supermercado, con su precio normalizado.

    `unit` es la unidad base de comparación ("kg", "l" o "ud") y
    `unit_price` el precio por esa unidad base. Si el supermercado no da
    precio por medida, ambos pueden ser None y la oferta no se puede
    comparar por cantidad.
    """

    store: str
    product_id: str
    name: str
    price: float
    unit: str | None
    unit_price: float | None
    url: str
    image: str | None = None
    brand: str | None = None
    format: str | None = None
    unit_raw: str | None = None  # unidad tal como la publica el súper (diagnóstico)

    def to_dict(self) -> dict:
        return asdict(self)

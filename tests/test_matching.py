from scraper.matching import Item, accepts, best_offer, normalize, tokens
from scraper.models import Offer


def offer(name, unit_price, unit="l", pid=None, price=None, store="dia"):
    return Offer(
        store=store,
        product_id=pid or name,
        name=name,
        price=price if price is not None else unit_price,
        unit=unit,
        unit_price=unit_price,
        url="https://example.com",
    )


LECHE = Item(
    id="leche-semi",
    nombre="Leche semidesnatada",
    busqueda="leche semidesnatada",
    unidad="l",
    excluir=("sin lactosa", "batido"),
)


def test_normalize_strips_accents_and_symbols():
    assert normalize("  Plátano de  CANARIAS, I.G.P. ") == "platano de canarias i g p"


def test_tokens_drop_stopwords():
    assert tokens("Aceite de oliva virgen extra") == ["aceite", "oliva", "virgen", "extra"]


def test_accepts_requires_all_search_words():
    assert accepts(LECHE, offer("Leche semidesnatada Hacendado", 0.89))
    assert not accepts(LECHE, offer("Leche entera Hacendado", 0.85))


def test_accepts_respects_exclusions():
    assert not accepts(LECHE, offer("Leche semidesnatada sin lactosa", 0.95))
    assert not accepts(LECHE, offer("Batido de cacao con leche semidesnatada", 1.2))


def test_accepts_needs_same_unit_and_price():
    assert not accepts(LECHE, offer("Leche semidesnatada en polvo", 9.0, unit="kg"))
    assert not accepts(LECHE, offer("Leche semidesnatada", None))


def test_whole_word_match():
    pan = Item(id="pan", nombre="Pan", busqueda="pan", unidad="kg")
    assert accepts(pan, offer("Pan de molde", 2.0, unit="kg"))
    assert not accepts(pan, offer("Panceta curada", 8.0, unit="kg"))


def test_incluir_overrides_search_words():
    huevos = Item(
        id="huevos", nombre="Huevos L", busqueda="huevos", unidad="ud", incluir=("huevos", "l")
    )
    assert accepts(huevos, offer("Huevos grandes L 12 unidades", 0.25, unit="ud"))
    assert not accepts(huevos, offer("Huevos medianos M 12 unidades", 0.2, unit="ud"))


def test_alternatives_with_pipe():
    pasta = Item(
        id="espaguetis",
        nombre="Espaguetis",
        busqueda="espaguetis",
        unidad="kg",
        incluir=("espaguetis|espagueti|spaghetti",),
    )
    assert accepts(pasta, offer("Spaghetti Hacendado", 1.2, unit="kg"))
    assert accepts(pasta, offer("Espaguetis Dia", 1.1, unit="kg"))
    assert not accepts(pasta, offer("Macarrones Dia", 1.0, unit="kg"))


def test_best_offer_picks_lowest_unit_price():
    offers = [
        offer("Leche semidesnatada marca", 1.10),
        offer("Leche semidesnatada pack 6 x 1 L", 0.83, price=4.98),
        offer("Leche entera", 0.70),
    ]
    assert best_offer(LECHE, offers).name == "Leche semidesnatada pack 6 x 1 L"


def test_best_offer_none_when_nothing_matches():
    assert best_offer(LECHE, [offer("Zumo de naranja", 0.9)]) is None
    assert best_offer(LECHE, []) is None


def test_pinned_product_wins():
    item = Item(
        id="leche-semi",
        nombre="Leche semidesnatada",
        busqueda="leche semidesnatada",
        unidad="l",
        fijar={"dia": "marca-favorita"},
    )
    offers = [offer("Leche semidesnatada barata", 0.8), offer("Leche Pascual", 1.3, pid="marca-favorita")]
    assert best_offer(item, offers).product_id == "marca-favorita"


def test_item_from_dict_defaults():
    item = Item.from_dict({"id": "x", "nombre": "Arroz redondo", "unidad": "kg"})
    assert item.busqueda == "Arroz redondo"
    assert item.cantidad == 1.0
    assert item.required_phrases() == ("arroz", "redondo")

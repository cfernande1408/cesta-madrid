import pytest

from scraper.units import normalize_unit, parse_price_text, parse_size, parse_unit_price_text, to_base


@pytest.mark.parametrize(
    "text, expected",
    [
        ("kg", ("kg", 1.0)),
        ("KILO", ("kg", 1.0)),
        ("L", ("l", 1.0)),
        ("LITRO", ("l", 1.0)),
        ("ud", ("ud", 1.0)),
        ("UNIDAD", ("ud", 1.0)),
        ("100 GR.", ("kg", 10.0)),
        ("100 ML.", ("l", 10.0)),
        ("PER_LITRE", ("l", 1.0)),
        ("PER_1KG", ("kg", 1.0)),
        ("KG.PESO ESC", ("kg", 1.0)),
    ],
)
def test_normalize_known_units(text, expected):
    assert normalize_unit(text) == expected


@pytest.mark.parametrize("text", ["DOCENA", "dz", "dc"])
def test_dozen_is_converted_to_units(text):
    unit, factor = normalize_unit(text)
    assert unit == "ud"
    assert factor == pytest.approx(1 / 12)


@pytest.mark.parametrize("text", [None, "", "LAVADO", "PER_METRE"])
def test_unknown_units(text):
    assert normalize_unit(text) is None


def test_to_base_scales_price():
    assert to_base(0.5, "100 GR.") == ("kg", 5.0)
    assert to_base(3.0, "DOCENA") == ("ud", 0.25)
    assert to_base(None, "kg") == (None, None)
    assert to_base(1.0, "LAVADO") == (None, None)


@pytest.mark.parametrize(
    "text, expected",
    [("1,65 €", 1.65), ("1.234,50€", 1234.5), ("0.99", 0.99), ("12", 12.0), ("gratis", None)],
)
def test_parse_price_text(text, expected):
    assert parse_price_text(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2,50€/KG.PESO ESC", ("kg", 2.5)),
        (" 0,99 €/L ", ("l", 0.99)),
        ("1,20€/Kg", ("kg", 1.2)),
        ("0,25 €/UNIDAD", ("ud", 0.25)),
        ("3,25€", (None, None)),
    ],
)
def test_parse_unit_price_text(text, expected):
    assert parse_unit_price_text(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1 l", ("l", 1.0)),
        ("Brik 1,5 l", ("l", 1.5)),
        ("Pack 6 x 1 l", ("l", 6.0)),
        ("6x200 ml", ("l", 1.2)),
        ("500 g", ("kg", 0.5)),
        ("1 kg", ("kg", 1.0)),
        ("12 rollos", ("ud", 12.0)),
        ("una docena", ("ud", 12.0)),
        ("precio kg (a granel)", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_size(text, expected):
    unit, qty = parse_size(text)
    assert unit == expected[0]
    assert qty == (pytest.approx(expected[1]) if expected[1] is not None else None)

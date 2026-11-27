from erarta_scraper.domain.parsing import (
    clean_price,
    clean_year,
    details_from_text_getter,
    normalize_blank,
    parse_size_cm,
)
from erarta_scraper.scraping.selectors import ArtworkLocators


def test_clean_price_strips_currency_and_spaces() -> None:
    assert clean_price("120 000 ₽") == 120000.0
    assert clean_price("1.500.000 руб.") == 1500000.0
    assert clean_price("") is None
    assert clean_price(None) is None
    assert clean_price("цена по запросу") is None


def test_clean_price_parses_decimal_comma() -> None:
    assert clean_price("1 500,50") == 1500.5
    assert clean_price("1 299,99 ₽") == 1299.99
    assert clean_price("1,5") == 1.5
    assert clean_price("0,75") == 0.75
    assert clean_price("1 500,5") == 1500.5
    assert clean_price("1.500,50") == 1500.5


def test_clean_price_keeps_comma_thousands_separator() -> None:
    assert clean_price("1299,999") == 1299999.0
    assert clean_price("1,500") == 1500.0
    assert clean_price("1,299,999") == 1299999.0


def test_clean_price_edge_cases() -> None:
    assert clean_price("1 500,50 и 2 000") == 1500.5
    assert clean_price(",50") is None
    assert clean_price("1500,") == 1500.0
    assert clean_price("цена 1500 руб.") == 1500.0
    assert clean_price("н/д") is None


def test_clean_year_picks_first_century_match() -> None:
    assert clean_year("2019 год") == 2019
    assert clean_year("работа 1998 / печать 2020") == 1998
    assert clean_year("XIX век") is None
    assert clean_year("") is None


def test_parse_size_cm() -> None:
    assert parse_size_cm("70 x 90 см") == (70.0, 90.0)
    assert parse_size_cm("70×90") == (70.0, 90.0)
    assert parse_size_cm("холст") is None


def test_normalize_blank() -> None:
    assert normalize_blank("  масло  ") == "масло"
    assert normalize_blank("   ") is None


def test_details_from_text_getter_uses_price_fallback() -> None:
    texts = {
        ArtworkLocators.TITLE: "Рассвет",
        ArtworkLocators.ARTIST: " Иванов ",
        ArtworkLocators.PRICE_SECONDARY: "",
        ArtworkLocators.PRICE_PRIMARY: "45 000 ₽",
        ArtworkLocators.SIZE: "50 x 60",
        ArtworkLocators.YEAR: "2018",
        ArtworkLocators.ART_TYPE: "живопись",
        ArtworkLocators.GENRE: "пейзаж",
        ArtworkLocators.BAGUETTE: "",
        ArtworkLocators.TECHNIQUE: "масло",
    }
    details = details_from_text_getter(lambda key: texts.get(key, ""))
    assert details.title == "Рассвет"
    assert details.artist_name == " Иванов "
    assert details.price == 45000.0
    assert details.year == 2018
    assert details.baguette is None
    assert details.technique == "масло"

import pytest
from scrapy import Selector

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.maps import parse_map_options
from nthu_scraper.spiders.nthu_maps import MapSpider


def test_map_contract_and_order(fixture_text, html_response):
    page = html_response(
        fixture_text("maps", "locations.html"), meta={"map_type": "MainZH"}
    )
    expected = {
        "圖書館": {"latitude": "24.7950", "longitude": "120.9930"},
        "台積館": {"latitude": "24.791234", "longitude": "120.990000"},
    }
    parsed = parse_map_options(page)
    assert parsed == expected
    assert list(parsed) == list(expected)
    parsed["圖書館"]["latitude"] = "modified"
    assert parse_map_options(page) == expected
    (item,) = MapSpider().parse(page)
    assert dict(item) == {"map_type": "MainZH", "data": expected}


@pytest.mark.parametrize(
    "value",
    ["24", "24,120,1", "x,120", ",120", "NaN,120", "24,inf", "91,120", "24,-181", " "],
)
def test_invalid_coordinates(value):
    with pytest.raises(ParseError):
        parse_map_options(
            Selector(text=f'<select><option value="{value}">Place</option></select>')
        )


@pytest.mark.parametrize(
    "html",
    [
        "<select></select>",
        "<select><option>Select location</option></select>",
        '<select><option value="">Select location</option></select>',
    ],
)
def test_empty_selectors(html):
    assert parse_map_options(Selector(text=html)) == {}


@pytest.mark.parametrize(
    "html",
    [
        "<html>Unavailable</html>",
        '<select><option value="24,120"></option></select>',
    ],
)
def test_missing_structure_or_name(html):
    with pytest.raises(ParseError):
        parse_map_options(Selector(text=html))


def test_partial_parse_does_not_yield_truncated_map(
    fixture_text, html_response, caplog
):
    page = html_response(
        fixture_text("maps", "malformed.html"), meta={"map_type": "MainEN"}
    )
    with pytest.raises(ParseError):
        parse_map_options(page)
    assert list(MapSpider().parse(page)) == []
    assert "retaining MainEN" in caplog.text

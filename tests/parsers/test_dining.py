import pytest

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.dining import parse_dining_html
from nthu_scraper.spiders.nthu_dining import DiningSpider


def test_dining_contract(fixture_text, html_response):
    html = fixture_text("dining", "restaurants.html")
    expected = [
        {"name": "水木餐廳", "restaurants": [{"name": "測試餐廳", "hours": "08:00-20:00"}]},
        {"name": "小吃部", "restaurants": [], "open": True},
    ]
    assert parse_dining_html(html) == expected
    item, = DiningSpider().parse(html_response(html))
    assert dict(item) == {"data": expected}


@pytest.mark.parametrize("literal", ['[]', '[{"name": "A"}]', "[{'name': 'A'}, ]"])
def test_whitespace_and_quotes(literal):
    expected = [] if literal == "[]" else [{"name": "A"}]
    assert parse_dining_html(f"const \n restaurantsData\t=\n{literal}\nrenderTabs()") == expected


@pytest.mark.parametrize("html", [
    "", "<html>Unavailable</html>", "const restaurantsData = []",
    "const restaurantsData = {} renderTabs()",
    "const restaurantsData = [oops] renderTabs()",
    "const restaurantsData = [{'name':'A'},] renderTabs()",
    "const restaurantsData = [{'name':'A',}] renderTabs()",
    "const restaurantsData = []; renderTabs()",
    "const restaurantsData = [{'name':'A'},\r\n ] renderTabs()",
])
def test_missing_or_unsupported_data_is_not_empty(html):
    with pytest.raises(ParseError):
        parse_dining_html(html)


def test_malformed_fixture(fixture_text):
    with pytest.raises(ParseError):
        parse_dining_html(fixture_text("dining", "malformed.html"))


@pytest.mark.parametrize("has_boundary", [False, True])
def test_long_whitespace_before_boundary(has_boundary):
    html = "const restaurantsData = []" + " " * 100_000
    if has_boundary:
        assert parse_dining_html(html + "renderTabs()") == []
    else:
        with pytest.raises(ParseError):
            parse_dining_html(html + "unrecognizedFunction()")


def test_empty_and_broken_callback_do_not_yield(html_response, caplog):
    assert list(DiningSpider().parse(html_response("const restaurantsData = [] renderTabs()"))) == []
    assert list(DiningSpider().parse(html_response("<html>Unavailable</html>"))) == []
    assert "Invalid dining source" in caplog.text

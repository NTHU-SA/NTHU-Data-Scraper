import ast

import pytest

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.buses import (
    extract_js_value,
    parse_info_variable,
    parse_schedule_variable,
    prepare_literal,
)
from nthu_scraper.spiders import nthu_buses


@pytest.mark.parametrize("literal", [
    "{}", "[]", "{a: [{b: [1, 2]}]}", '[{a: "[x] }"}, [1, 2]]',
    r'''{a: 'escaped \' [ }', b: "escaped \" ] {"}''',
    '{a: `brackets [ }`}',
])
def test_extract_balanced_value(literal):
    assert extract_js_value(f"const data = {literal}; const next = [];", "data") == literal


@pytest.mark.parametrize("fragment", [
    "", "const other = [];", "const data =", "const data = 3;",
    "const data = [{];", "const data = [{a: 1}", 'const data = ["unterminated];',
])
def test_missing_or_malformed_extraction(fragment):
    with pytest.raises(ParseError):
        extract_js_value(fragment, "data")


def test_literal_types_and_trailing_commas():
    assert ast.literal_eval(prepare_literal("{yes: true, no: false, value: null, xs: [1,],}")) == {
        "yes": True, "no": False, "value": None, "xs": [1],
    }


def test_legacy_quoted_boolean_normalization_is_preserved():
    assert parse_info_variable("data", "const data = {label: 'true false null'};") == {
        "label": "True False None",
    }


def test_bus_info_contract(fixture_text):
    assert parse_info_variable("towardTSMCBuildingInfo", fixture_text("buses", "schedule.html")) == {
        "route": "校門 台積館", "routeEN": "Main Gate TSMC",
        "enabled": True, "holiday": False, "note": None, "stops": ["校門", "台積館"],
    }


def test_schedule_contract(fixture_text):
    html = fixture_text("buses", "schedule.html")
    assert parse_schedule_variable("weekdayBusScheduleTowardTSMCBuilding", html) == [
        {"time": "08:00", "description": "上課日", "dep_stop": "校門", "route": "校園公車"},
        {"time": "09:00", "description": "", "dep_stop": "台積館", "route": "校園公車"},
    ]
    assert parse_schedule_variable("weekdayBusScheduleTowardNanda", html) == [
        {"time": "10:00", "description": "直達", "line": "1", "dep_stop": "校本部", "route": "南大區間車"},
    ]


@pytest.mark.parametrize("parser,literal", [
    (parse_info_variable, "[]"), (parse_info_variable, "{route: null}"),
    (parse_info_variable, "{a: functionCall()}"),
    (parse_schedule_variable, "{}"), (parse_schedule_variable, "[null]"),
    (parse_schedule_variable, "[{time: ''}]"),
])
def test_invalid_value_shapes(parser, literal):
    with pytest.raises(ParseError):
        parser("data", f"const data = {literal};")


def test_malformed_fixture_rejects_whole_component(fixture_text):
    html = fixture_text("buses", "malformed.html")
    with pytest.raises(ParseError):
        parse_schedule_variable("schedule", html)
    with pytest.raises(ParseError):
        parse_info_variable("info", html)


def test_valid_empty_values():
    assert parse_info_variable("info", "const info = {};") == {}
    assert parse_schedule_variable("schedule", "const schedule = [];") == []


def test_callback_keeps_successful_components_when_others_missing(fixture_text, html_response, caplog):
    spider = nthu_buses.BusesSpider()
    page = html_response(fixture_text("buses", "schedule.html"), meta={"bus_type": "main"})
    items = [dict(item) for item in spider.parse(page)]
    assert items == [
        {"type": "info", "route_type": "main", "item_name": "towardTSMCBuildingInfo",
         "data": parse_info_variable("towardTSMCBuildingInfo", page.text)},
        {"type": "schedule", "route_type": "main", "item_name": "weekdayBusScheduleTowardTSMCBuilding",
         "data": parse_schedule_variable("weekdayBusScheduleTowardTSMCBuilding", page.text)},
    ]
    assert "retaining towardMainGateInfo" in caplog.text

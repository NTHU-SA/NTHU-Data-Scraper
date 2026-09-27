"""Parse the embedded dining JSON-like array using the existing source rules."""

import json
import re

from nthu_scraper.parsers import ParseError


DINING_DECLARATION = re.compile(r"const\s+restaurantsData\s*=\s*")
RENDER_TABS_BOUNDARY = re.compile(r"\srenderTabs")


def parse_dining_html(html: str) -> list:
    match = DINING_DECLARATION.search(html)
    if match is None or html[match.end():match.end() + 1] != "[":
        raise ParseError("Missing restaurantsData array")
    boundary = RENDER_TABS_BOUNDARY.search(html, match.end())
    if boundary is None:
        raise ParseError("Missing restaurantsData or renderTabs boundary")
    literal = html[match.end():boundary.start()].replace("'", '"').replace("\n", "")
    literal = re.sub(r",[ ]+?\]", "]", literal)
    try:
        data = json.loads(literal)
    except json.JSONDecodeError as error:
        raise ParseError(f"Invalid restaurantsData: {error}") from error
    if not isinstance(data, list):
        raise ParseError("restaurantsData must be an array")
    return data

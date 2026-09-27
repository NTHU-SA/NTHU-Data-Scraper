"""Parse the embedded dining JSON-like array using the existing source rules."""

import json
import re

from nthu_scraper.parsers import ParseError


DINING_REGEX = re.compile(r"const\s+restaurantsData\s*=\s*(\[.*?)(?:\s+renderTabs)", re.S)


def parse_dining_html(html: str) -> list:
    match = DINING_REGEX.search(html)
    if match is None:
        raise ParseError("Missing restaurantsData or renderTabs boundary")
    literal = match.group(1).replace("'", '"').replace("\n", "")
    literal = re.sub(r",[ ]+?\]", "]", literal)
    try:
        data = json.loads(literal)
    except json.JSONDecodeError as error:
        raise ParseError(f"Invalid restaurantsData: {error}") from error
    if not isinstance(data, list):
        raise ParseError("restaurantsData must be an array")
    return data

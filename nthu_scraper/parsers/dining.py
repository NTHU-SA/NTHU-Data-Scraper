"""Parse the embedded dining JSON-like array using the existing source rules."""

import json
import logging
import re

from nthu_scraper.parsers import ParseError
from nthu_scraper.utils.url_utils import normalize_optional_http_url

logger = logging.getLogger(__name__)
DINING_DECLARATION = re.compile(r"const\s+restaurantsData\s*=\s*")
RENDER_TABS_BOUNDARY = re.compile(r"\srenderTabs")


def parse_dining_html(
    html: str, base_url: str = "https://ddfm.site.nthu.edu.tw/"
) -> list:
    match = DINING_DECLARATION.search(html)
    if match is None or html[match.end() : match.end() + 1] != "[":
        raise ParseError("Missing restaurantsData array")
    boundary = RENDER_TABS_BOUNDARY.search(html, match.end())
    if boundary is None:
        raise ParseError("Missing restaurantsData or renderTabs boundary")
    literal = html[match.end() : boundary.start()].replace("'", '"').replace("\n", "")
    literal = re.sub(r",[ ]+?\]", "]", literal)
    try:
        data = json.loads(literal)
    except json.JSONDecodeError as error:
        raise ParseError(f"Invalid restaurantsData: {error}") from error
    if not isinstance(data, list):
        raise ParseError("restaurantsData must be an array")
    for building in data:
        if not isinstance(building, dict):
            raise ParseError("Dining building must be an object")
        restaurants = building.get("restaurants", [])
        if not isinstance(restaurants, list):
            raise ParseError("Dining restaurants must be an array")
        for restaurant in restaurants:
            if not isinstance(restaurant, dict):
                raise ParseError("Dining restaurant must be an object")
            if "image" in restaurant:
                restaurant["image"] = normalize_optional_http_url(
                    restaurant["image"],
                    base_url=base_url,
                    logger=logger,
                    context=f"dining image for {restaurant.get('name')!r}",
                )
    return data

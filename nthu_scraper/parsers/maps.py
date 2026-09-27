"""Campus map option parsing; coordinates remain strings in published output."""

import math

from nthu_scraper.parsers import ParseError


def parse_map_options(page) -> dict[str, dict[str, str]]:
    options = page.css("option")
    if not options and not page.css("select"):
        raise ParseError("Map page has no location selector")
    result = {}
    for option in options:
        value = option.xpath("@value").get()
        if not value:
            continue
        coords = [coord.strip() for coord in value.split(",")]
        if len(coords) != 2:
            raise ParseError(f"Invalid map coordinate pair: {value!r}")
        try:
            latitude, longitude = map(float, coords)
        except ValueError as error:
            raise ParseError(f"Invalid map coordinates: {value!r}") from error
        if not (
            math.isfinite(latitude)
            and math.isfinite(longitude)
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            raise ParseError(f"Map coordinates out of range: {value!r}")
        name = option.xpath("normalize-space(text())").get()
        if not name:
            raise ParseError("Map location has no name")
        result[name] = {"latitude": coords[0], "longitude": coords[1]}
    return result

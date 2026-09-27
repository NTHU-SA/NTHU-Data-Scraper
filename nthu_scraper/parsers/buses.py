"""Parse the limited JavaScript literals used by the bus pages, without eval."""

import ast
import re

from scrapy import Selector

from nthu_scraper.parsers import ParseError


def extract_js_value(page_text: str, var_name: str) -> str:
    match = re.search(rf"\bconst\s+{re.escape(var_name)}\s*=\s*", page_text)
    if not match:
        raise ParseError(f"Missing bus variable: {var_name}")
    start = match.end()
    if start == len(page_text) or page_text[start] not in "{[":
        raise ParseError(f"Unsupported value for bus variable: {var_name}")

    stack = []
    closing = {"{": "}", "[": "]"}
    quote = ""
    escape = False
    for index in range(start, len(page_text)):
        char = page_text[index]
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = ""
        elif char in "\"'`":
            quote = char
        elif char in closing:
            stack.append(closing[char])
        elif char in "}]":
            if not stack or stack.pop() != char:
                raise ParseError(f"Mismatched brackets in bus variable: {var_name}")
            if not stack:
                return page_text[start:index + 1]
    raise ParseError(f"Unterminated bus variable: {var_name}")


def prepare_literal(js_value: str) -> str:
    """Preserve the crawler's existing literal normalization (not general JS)."""
    literal = js_value.strip().rstrip(";")
    literal = literal.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    literal = re.sub(r'(?<!["\'])\b([A-Za-z_]\w*)\b\s*:', r'"\1":', literal)
    literal = re.sub(r'""(\w+)"":', r'"\1":', literal)
    literal = re.sub(r",\s*]", "]", literal)
    literal = re.sub(r",\s*}", "}", literal)
    literal = re.sub(r"\btrue\b", "True", literal, flags=re.IGNORECASE)
    literal = re.sub(r"\bfalse\b", "False", literal, flags=re.IGNORECASE)
    return re.sub(r"\bnull\b", "None", literal, flags=re.IGNORECASE)


def _parse_variable(var_name: str, page_text: str):
    literal = prepare_literal(extract_js_value(page_text, var_name))
    try:
        return ast.literal_eval(literal)
    except (SyntaxError, ValueError) as error:
        raise ParseError(f"Invalid bus literal {var_name}: {error}") from error


def parse_info_variable(var_name: str, page_text: str) -> dict:
    data = _parse_variable(var_name, page_text)
    if not isinstance(data, dict):
        raise ParseError(f"Bus info must be an object: {var_name}")
    for key in ("route", "routeEN"):
        if key in data:
            if not isinstance(data[key], str):
                raise ParseError(f"Bus {var_name}.{key} must be text")
            data[key] = " ".join(Selector(text=data[key]).xpath("//text()").getall())
    return data


def parse_schedule_variable(var_name: str, page_text: str) -> list[dict]:
    data = _parse_variable(var_name, page_text)
    if not isinstance(data, list) or any(
        not isinstance(item, dict) or not item.get("time") for item in data
    ):
        raise ParseError(f"Invalid or incomplete bus schedule: {var_name}")
    normalized = []
    for item in data:
        record = {"time": item.get("time", ""), "description": item.get("description", "")}
        if "line" in item:
            record["line"] = item["line"]
        if "depStop" in item or "dep_stop" in item:
            record["dep_stop"] = item.get("depStop", item.get("dep_stop", ""))
        record["route"] = "南大區間車" if "line" in record else "校園公車"
        normalized.append(record)
    return normalized

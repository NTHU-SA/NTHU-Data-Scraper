"""Parse newsletter entries and archives without requests or spider state."""

import re
from datetime import date

from nthu_scraper.parsers import ParseError

URL_PREFIX = "https://newsletter.cc.nthu.edu.tw"
MONTHS = (
    ("一月", "Jan"),
    ("二月", "Feb"),
    ("三月", "Mar"),
    ("四月", "Apr"),
    ("五月", "May"),
    ("六月", "Jun"),
    ("七月", "Jul"),
    ("八月", "Aug"),
    ("九月", "Sep"),
    ("十月", "Oct"),
    ("十一月", "Nov"),
    ("十二月", "Dec"),
)


def parse_metadata_table(table) -> dict:
    details = {}
    for row in table.css("tr"):
        cells = row.css("td, th")
        if len(cells) != 2:
            raise ParseError("Newsletter metadata row must have two cells")
        key = (cells[0].css("::text").get() or "").strip()
        value = (cells[1].css("::text").get() or "").strip()
        if key and value:
            details[key] = value
    return details


def parse_newsletter_entry(entry) -> dict:
    anchor = entry.css("h3 a")
    name = (anchor.css("::text").get() or "").strip()
    link = (anchor.css("::attr(href)").get() or "").strip()
    if not name or not link:
        raise ParseError("Newsletter gallery entry has no usable link or name")
    return {
        "name": name,
        "link": link,
        "details": parse_metadata_table(entry.css("table")),
        "articles": [],
    }


def newsletter_entries(page):
    gallery = page.css("div.gallery")
    if not gallery:
        raise ParseError("Newsletter root contained no gallery")
    entries = gallery.css("li")
    if not entries and (gallery.xpath("normalize-space(.)").get() or ""):
        raise ParseError("Newsletter gallery has an unexpected structure")
    return entries


def parse_newsletter_list(page) -> list[dict]:
    return [parse_newsletter_entry(entry) for entry in newsletter_entries(page)]


def convert_chinese_month_to_english(date_str: str) -> str:
    for chinese, english in MONTHS:
        date_str = date_str.replace(f" {chinese} ", f" {english} ")
    return date_str


def parse_newsletter_date(date_str: str) -> str:
    normalized = convert_chinese_month_to_english(
        date_str.strip().replace("Sent on ", "")
    )
    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", normalized)
    if not match:
        raise ParseError(f"Invalid newsletter date: {normalized}")
    day, month, year = match.groups()
    try:
        # The source's English month names must not depend on the host locale.
        month_number = [english.lower() for _, english in MONTHS].index(
            month.lower()
        ) + 1
        return date(int(year), month_number, int(day)).isoformat()
    except ValueError as error:
        raise ParseError(f"Invalid newsletter date: {normalized}") from error


def parse_popup_url(onclick: str) -> str:
    match = re.search(r"openpopup\('(.*?)',", onclick)
    if not match or not match.group(1):
        raise ParseError("Newsletter article has an invalid popup URL")
    return f"{URL_PREFIX}{match.group(1)}"


def parse_archive_articles(page) -> list[dict]:
    content = page.css("div#acyarchivelisting")
    if not content:
        raise ParseError("Missing newsletter content")
    table = content.css("table.contentpane")
    if not table:
        raise ParseError("Missing newsletter article table")
    articles = []
    for row in table.css("div.archiveRow"):
        anchor = row.css("a")
        title = (anchor.css("::text").get() or "").strip()
        if not title:
            raise ParseError("Unusable newsletter article title")
        article = {}
        onclick = anchor.css("::attr(onclick)").get()
        if onclick:
            article["link"] = parse_popup_url(onclick)
        article["title"] = title
        date = row.css("span.sentondate::text").get()
        if date and date.strip():
            article["date"] = parse_newsletter_date(date)
        articles.append(article)
    if not articles and (table.xpath("normalize-space(.)").get() or ""):
        raise ParseError("Newsletter article table has an unexpected structure")
    return articles

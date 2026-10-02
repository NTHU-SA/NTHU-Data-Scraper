"""Parse newsletter entries and archives without requests or spider state."""

import re
from datetime import date
from urllib.parse import urlsplit

from nthu_scraper.parsers import ParseError
from nthu_scraper.utils.url_utils import InvalidHttpUrl, normalize_http_url

URL_PREFIX = normalize_http_url("https://newsletter.cc.nthu.edu.tw").rstrip("/")
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
        key = cells[0].xpath("normalize-space(.)").get() or ""
        value = cells[1].xpath("normalize-space(.)").get() or ""
        if key and value:
            details[key] = value
    return details


def _newsletter_url(value: str, base_url: str) -> str:
    try:
        return normalize_http_url(value, base_url=base_url)
    except InvalidHttpUrl as error:
        raise ParseError(f"Invalid newsletter URL {value!r}: {error}") from error


def parse_newsletter_entry(entry, base_url: str = URL_PREFIX + "/") -> dict:
    anchor = entry.css("h3 a, .list_name a")
    return _parse_newsletter_anchor(
        anchor, parse_metadata_table(entry.css("table")), base_url
    )


def _parse_newsletter_anchor(anchor, details: dict, base_url: str) -> dict:
    name = (anchor.xpath("normalize-space(.)").get() or "").strip()
    link = (anchor.css("::attr(href)").get() or "").strip()
    if not name or not link:
        raise ParseError("Newsletter gallery entry has no usable link or name")
    return {
        "name": name,
        "link": _newsletter_url(link, base_url),
        "details": details.copy(),
        "articles": [],
    }


def newsletter_entries(page):
    listing = page.css("#acylistslisting")
    if listing:
        entries = listing.css(".acymailing_list")
        if not entries:
            raise ParseError("Newsletter list contained no entries")
        return entries
    gallery = page.css("div.gallery")
    if not gallery:
        raise ParseError("Newsletter root contained no gallery")
    entries = gallery.css("li")
    if not entries and (gallery.xpath("normalize-space(.)").get() or ""):
        raise ParseError("Newsletter gallery has an unexpected structure")
    return entries


def parse_newsletter_list(page, base_url: str = URL_PREFIX + "/") -> list[dict]:
    return [
        newsletter
        for entry in newsletter_entries(page)
        for newsletter in parse_newsletter_group(entry, base_url)
    ]


def parse_newsletter_group(entry, base_url: str) -> list[dict]:
    if "acymailing_list" in (entry.attrib.get("class") or "").split():
        if len(entry.css(".list_name a")) != 1:
            raise ParseError("Newsletter list entry must have one archive link")
        newsletter = parse_newsletter_entry(entry, base_url)
        if newsletter_list_id(newsletter["link"]) is None:
            raise ParseError("Newsletter list entry has no official list ID")
        return [newsletter]
    anchors = entry.css("h3 a")
    if not anchors:
        raise ParseError("Newsletter gallery entry has no usable link or name")
    details = parse_metadata_table(entry.css("table"))
    return [_parse_newsletter_anchor(anchor, details, base_url) for anchor in anchors]


def newsletter_list_id(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.hostname != urlsplit(URL_PREFIX).hostname:
        return None
    match = re.search(r"/listid-(\d+)(?:-|/|$)", parsed.path)
    return match.group(1) if match else None


def parse_newsletter_sources(page, base_url: str) -> tuple[str, str]:
    gallery = page.css("iframe#blockrandom::attr(src)").get()
    listing = page.css('a[href$="/list/lists/listing"]::attr(href)').get()
    if not gallery or not listing:
        raise ParseError("Newsletter wrapper is missing its gallery or official list")
    urls = tuple(_newsletter_url(value, base_url) for value in (gallery, listing))
    if any(urlsplit(url).hostname != urlsplit(URL_PREFIX).hostname for url in urls):
        raise ParseError("Newsletter sources must remain on the official host")
    return urls


def parse_gallery_metadata(page, base_url: str) -> dict[str, dict]:
    if not page.css("div.gallery"):
        raise ParseError("Missing newsletter metadata gallery")
    newsletters = parse_newsletter_list(page, base_url)
    if not newsletters:
        raise ParseError("Newsletter metadata gallery contained no entries")
    metadata = {}
    for newsletter in newsletters:
        if list_id := newsletter_list_id(newsletter["link"]):
            if list_id in metadata and metadata[list_id] != newsletter["details"]:
                raise ParseError(f"Conflicting newsletter metadata for list {list_id}")
            metadata[list_id] = newsletter["details"]
    if not metadata:
        raise ParseError("Newsletter metadata gallery contained no official list IDs")
    return metadata


def convert_chinese_month_to_english(date_str: str) -> str:
    for chinese, english in MONTHS:
        date_str = date_str.replace(f" {chinese} ", f" {english} ")
    return date_str


def parse_newsletter_date(date_str: str) -> str:
    normalized = convert_chinese_month_to_english(
        date_str.strip().replace("Sent on ", "")
    )
    localized = re.fullmatch(
        r"(\d{4})年(?:(\d{1,2})月|([一二三四五六七八九十]{1,3})月?)(\d{1,2})日",
        normalized,
    )
    if localized:
        year, numeric_month, chinese_month, day = localized.groups()
        try:
            month_number = (
                int(numeric_month)
                if numeric_month
                else [chinese.removesuffix("月") for chinese, _ in MONTHS].index(
                    chinese_month
                )
                + 1
            )
            return date(int(year), month_number, int(day)).isoformat()
        except ValueError as error:
            raise ParseError(f"Invalid newsletter date: {normalized}") from error
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
    return _newsletter_url(match.group(1), URL_PREFIX + "/")


def parse_archive_articles(page, base_url: str = URL_PREFIX + "/") -> list[dict]:
    content = page.css("div#acyarchivelisting")
    if not content:
        raise ParseError("Missing newsletter content")
    table = content.css("table.contentpane")
    if not table:
        raise ParseError("Missing newsletter article table")
    articles = []
    for row in table.css("div.archiveRow"):
        anchor = row.css("a")
        title = (anchor.xpath("normalize-space(.)").get() or "").strip()
        if not title:
            raise ParseError("Unusable newsletter article title")
        article = {}
        onclick = anchor.css("::attr(onclick)").get()
        if onclick:
            article["link"] = parse_popup_url(onclick)
        elif href := anchor.css("::attr(href)").get():
            article["link"] = _newsletter_url(href, base_url)
        article["title"] = title
        date = row.css("span.sentondate::text").get()
        if date and date.strip():
            article["date"] = parse_newsletter_date(date)
        articles.append(article)
    if not articles:
        counter = (
            content.css(".acypagination_counter").xpath("normalize-space(.)").get()
        )
        if counter != "No results":
            raise ParseError(
                "Newsletter archive has no articles or explicit empty result"
            )
    return articles

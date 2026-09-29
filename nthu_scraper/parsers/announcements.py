"""Deterministic parsing of RPage announcement pages."""

import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from nthu_scraper.parsers import ParseError
from nthu_scraper.utils.constants import RPAGE_DOMAIN_SUFFIX
from nthu_scraper.utils.url_utils import (
    check_domain_suffix,
    force_https,
    http_url_error,
    update_url_query_param,
)

logger = logging.getLogger(__name__)


@dataclass
class ParsedArticles:
    articles: list[dict]
    rejected_count: int = 0


class InvalidArticleUrl(ValueError):
    def __init__(self, title: str, link: str, reason: str):
        super().__init__(f"title={title!r} link={link!r}: {reason}")


def parse_article(item, base_url: str) -> dict:
    link_elem = item.css(".mtitle a")
    title = link_elem.css("::text").get()
    if title:
        title = title.strip().replace('"', "")
    href = link_elem.css("::attr(href)").get()
    if not title or not href:
        raise ParseError("Announcement entry has no usable title or link")
    raw_link = href.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_link):
        raise InvalidArticleUrl(title, href, "URL contains control characters")
    try:
        if urlsplit(raw_link).scheme:
            link = raw_link
        elif raw_link.startswith("//"):
            link = f"{urlsplit(base_url).scheme}:{raw_link}"
        else:
            link = urljoin(base_url, raw_link)
    except ValueError as error:
        raise InvalidArticleUrl(title, href, str(error)) from error
    reason = http_url_error(link) if raw_link else "URL is blank"
    if reason:
        raise InvalidArticleUrl(title, href, reason)
    date = item.css(".mdate::text").get() or item.css(".d-txt::text").get()
    return {
        "title": title,
        "link": link,
        "date": date.strip() if date else date,
    }


def _article_rows(page):
    container = page.css("#pageptlist")
    if not container:
        raise ParseError("Announcement page has no #pageptlist container")
    rows = container.css(".row.listBS") or container.css("tr")
    if not rows and (
        container.xpath(".//*[not(self::table or self::tbody or self::thead)]")
        or (container.xpath("normalize-space(.)").get() or "")
    ):
        raise ParseError("Announcement container has an unexpected structure")
    return rows


def parse_articles(page, base_url: str) -> ParsedArticles:
    result = ParsedArticles([])
    for index, row in enumerate(_article_rows(page)):
        if row.css("th") and not row.css(".mtitle a"):
            continue
        try:
            result.articles.append(parse_article(row, base_url))
        except InvalidArticleUrl as error:
            result.rejected_count += 1
            logger.warning(
                "Skipping invalid announcement URL: source=%s article=%s %s",
                base_url,
                index,
                error,
            )
    return result


def parse_more_links(page, base_url: str, language: str) -> list[str]:
    # A department homepage need not expose any announcement lists.
    return [
        update_url_query_param(urljoin(base_url, link), "Lang", language)
        for link in page.css("p.more a::attr(href)").getall()
    ]


def parse_list_page(page) -> dict:
    title = page.css("[class*='title']::text").get()
    if not title or not title.strip():
        title = page.css("title::text").get()
    return {
        "title": title.strip() if title else title,
        "has_content": bool(_article_rows(page)),
    }


def normalize_list_url(url: str) -> str | None:
    normalized = force_https(url)
    if not normalized or not check_domain_suffix(normalized, RPAGE_DOMAIN_SUFFIX):
        return None
    return normalized

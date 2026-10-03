"""Deterministic parsing of RPage announcement pages."""

import logging
from dataclasses import dataclass

from nthu_scraper.parsers import ParseError
from nthu_scraper.utils.constants import RPAGE_DOMAIN_SUFFIX
from nthu_scraper.utils.text_utils import normalize_single_line_text
from nthu_scraper.utils.url_utils import (
    InvalidHttpUrl,
    check_domain_suffix,
    force_https,
    normalize_http_url,
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


def normalize_announcement_text(text: str) -> str:
    return normalize_single_line_text(text)


def parse_article(item, base_url: str) -> dict:
    link_elem = item.css(".mtitle a")
    title = link_elem.xpath("string(.)").get()
    if title:
        title = normalize_announcement_text(title.replace('"', ""))
    href = link_elem.css("::attr(href)").get()
    if not title or not href:
        raise ParseError("Announcement entry has no usable title or link")
    try:
        link = normalize_http_url(href, base_url=base_url)
    except InvalidHttpUrl as error:
        raise InvalidArticleUrl(title, href, str(error)) from error
    date = item.css(".mdate::text").get() or item.css(".d-txt::text").get()
    return {
        "title": title,
        "link": link,
        "date": normalize_announcement_text(date) if date else date,
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
    links = []
    for link in page.css("p.more a::attr(href)").getall():
        try:
            url = normalize_http_url(link, base_url=base_url)
            links.append(update_url_query_param(url, "Lang", language))
        except InvalidHttpUrl as error:
            logger.warning(
                "Skipping invalid announcement list URL: source=%s link=%r: %s",
                base_url,
                link,
                error,
            )
    return links


def parse_list_title(page) -> str | None:
    module = page.css("#pageptlist").xpath(
        "ancestor::*[contains(concat(' ', normalize-space(@class), ' '), "
        "' module ')][1]"
    )
    for candidates in (
        module.css("header .mt-title"),
        page.css("h1.section-title, h2.section-title").xpath(
            "self::*[not(ancestor::*[@id='pageptlist' or "
            "contains(concat(' ', normalize-space(@class), ' '), ' module ')])]"
        ),
        page.css(
            ".module-path .breadcrumb > li.active, "
            ".module-path .breadcrumb [aria-current='page']"
        ),
        page.css("title"),
    ):
        for candidate in candidates:
            title = normalize_announcement_text(
                candidate.xpath("string(.)").get() or ""
            )
            if title:
                return title
    return None


def parse_list_page(page) -> dict:
    rows = _article_rows(page)
    title = parse_list_title(page)
    if not title:
        raise ParseError("Announcement page has no usable list title")
    return {
        "title": title,
        "has_content": bool(rows),
    }


def normalize_list_url(url: str) -> str | None:
    try:
        normalized = force_https(url)
    except InvalidHttpUrl as error:
        logger.warning("Skipping invalid announcement source URL %r: %s", url, error)
        return None
    if not normalized or not check_domain_suffix(normalized, RPAGE_DOMAIN_SUFFIX):
        return None
    return normalized

"""URL processing utility functions."""

import logging
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from pydantic import HttpUrl, TypeAdapter, ValidationError

_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)
_URL_LIST_SEPARATOR = re.compile(r",\s*(?:https?:)?//", re.IGNORECASE)


class InvalidHttpUrl(ValueError):
    """A value cannot be safely normalized into a single HTTP(S) URL."""


def normalize_http_url(
    value: object, *, base_url: str | None = None, force_https: bool = False
) -> str:
    """Resolve links, encode spaces, and return a strictly validated canonical URL."""
    if not isinstance(value, str):
        raise InvalidHttpUrl("URL must be a string")
    url = value.strip()
    if not url:
        raise InvalidHttpUrl("URL is blank")
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        raise InvalidHttpUrl("URL contains control characters")
    if "\\" in url:
        raise InvalidHttpUrl("URL contains backslashes")
    try:
        parts = urlsplit(url)
    except ValueError as error:
        raise InvalidHttpUrl(str(error)) from error
    if _URL_LIST_SEPARATOR.search(parts.path):
        raise InvalidHttpUrl("Expected one URL, not a comma-separated URL list")
    if parts.scheme:
        if parts.scheme.lower() not in {"http", "https"}:
            raise InvalidHttpUrl("URL scheme must be HTTP(S)")
        if not parts.netloc:
            raise InvalidHttpUrl("Absolute HTTP(S) URL has no host")
    elif url.startswith("//"):
        parts = parts._replace(scheme="https")
    elif base_url is not None:
        base = normalize_http_url(base_url)
        try:
            parts = urlsplit(urljoin(base, url))
        except ValueError as error:
            raise InvalidHttpUrl(str(error)) from error
    else:
        raise InvalidHttpUrl("Relative URL requires a base URL")

    url = urlunsplit(
        parts._replace(
            scheme="https" if force_https else parts.scheme,
            path=parts.path.replace(" ", "%20"),
            query=parts.query.replace(" ", "%20"),
            fragment=parts.fragment.replace(" ", "%20"),
        )
    )

    try:
        return str(_HTTP_URL_ADAPTER.validate_python(url, strict=True))
    except ValidationError as error:
        detail = error.errors(include_url=False)[0]
        raise InvalidHttpUrl(f"{detail['type']}: {detail['msg']}") from error


def normalize_optional_http_url(
    value: object,
    *,
    logger: logging.Logger | logging.LoggerAdapter,
    context: str,
    base_url: str | None = None,
) -> str | None:
    """Normalize an optional URL; log unrecoverable values before using null."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return normalize_http_url(value, base_url=base_url)
    except InvalidHttpUrl as error:
        logger.warning("Invalid %s URL %r; using null: %s", context, value, error)
        return None


def http_url_error(value: object) -> str | None:
    """Check HTTP URL syntax without normalizing the stored representation."""
    try:
        _HTTP_URL_ADAPTER.validate_python(value, strict=True)
    except ValidationError as error:
        detail = error.errors(include_url=False)[0]
        return f"{detail['type']}: {detail['msg']}"
    return None


def force_https(url: str) -> str:
    """Normalize an HTTP(S) URL and require HTTPS."""
    if not url:
        return url
    return normalize_http_url(url, force_https=True)


def update_url_query_param(
    url: str, param_name: str, param_value: str, force_https: bool = True
) -> str:
    """
    更新網址的查詢參數。可選地強制將 scheme 設為 https。

    Args:
        url: 網址字串。
        param_name: 參數名稱。
        param_value: 參數值。
        force_https: 若為 True，會把 scheme 強制改為 https；否則保留 HTTP(S) scheme。
    Returns:
        更新參數後的網址字串。
    """
    parsed_url = urlsplit(normalize_http_url(url, force_https=force_https))
    query_params = parse_qs(parsed_url.query)
    query_params[param_name] = [param_value]
    new_query = urlencode(query_params, doseq=True)

    return normalize_http_url(urlunsplit(parsed_url._replace(query=new_query)))


def build_multi_lang_urls(
    original_url: str, languages: list[str], lang_param: str = "Lang"
) -> dict[str, str] | None:
    """
    為給定的原始 URL 建立包含不同語言版本的 URL 字典。

    Args:
        original_url: 原始網址字串。
        languages: 語言代碼列表。
        lang_param: 語言參數名稱。

    Returns:
        一個字典，鍵為語言代碼，值為對應語言版本的 URL。
    """
    lang_urls = {}
    for lang in languages:
        lang_urls[lang] = update_url_query_param(original_url, lang_param, lang)
    return lang_urls


def check_domain_suffix(url: str, suffix: str) -> bool:
    """
    檢查 URL 是否屬於指定的網域後綴。

    Args:
        url: 要檢查的 URL。
        suffix: 網域後綴。

    Returns:
        若 URL 屬於該網域後綴則返回 True，否則返回 False。
    """
    hostname = urlsplit(url).hostname
    suffix = suffix.lower().lstrip(".")
    return bool(hostname and (hostname == suffix or hostname.endswith("." + suffix)))

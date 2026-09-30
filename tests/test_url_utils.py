import logging

import pytest

from nthu_scraper.utils.url_utils import (
    InvalidHttpUrl,
    build_multi_lang_urls,
    check_domain_suffix,
    force_https,
    http_url_error,
    normalize_http_url,
    normalize_optional_http_url,
    update_url_query_param,
)


@pytest.mark.parametrize(
    "value,base_url,expected",
    [
        (" https://example.test/a \n", None, "https://example.test/a"),
        ("http://example.test/a", None, "http://example.test/a"),
        ("//example.test/a", None, "https://example.test/a"),
        (
            "/cover image.jpg",
            "https://example.test/news/",
            "https://example.test/cover%20image.jpg",
        ),
        (
            "../cover image.jpg",
            "https://example.test/news/",
            "https://example.test/cover%20image.jpg",
        ),
        (
            "https://example.test/cover%2Fone image.jpg?q=a b&escaped=a%20b#part one",
            None,
            "https://example.test/cover%2Fone%20image.jpg?q=a%20b&escaped=a%20b#part%20one",
        ),
        (
            "https://example.test/\u516c\u544a.jpg",
            None,
            "https://example.test/%E5%85%AC%E5%91%8A.jpg",
        ),
        ("https://\u4f8b\u5b50.test/a", None, "https://xn--fsqu00a.test/a"),
        ("https://example.test:443", None, "https://example.test/"),
        (
            "https://example.test/a(b)?next=https://other.test/a&value=a+b",
            None,
            "https://example.test/a(b)?next=https://other.test/a&value=a+b",
        ),
        (
            "https://example.test/search?urls=https://one.test/, https://two.test/",
            None,
            "https://example.test/search?urls=https://one.test/,%20https://two.test/",
        ),
    ],
)
def test_normalization_is_valid_and_idempotent(value, base_url, expected):
    actual = normalize_http_url(value, base_url=base_url)
    assert actual == expected
    assert http_url_error(actual) is None
    assert normalize_http_url(actual) == actual


@pytest.mark.parametrize(
    "value",
    [
        None,
        42,
        [],
        "",
        " \n",
        "/relative",
        "https://",
        "https:relative",
        "https://invalid host.test/image.jpg",
        "https://example.test:99999/a",
        "https://example.test:not-a-port/a",
        "https://[broken",
        "https://example.test/a\nb",
        "https://example.test/a\tb",
        "https://example.test/a\x7fb",
        r"https://example.test\a",
        "javascript:alert(1)",
        "mailto:office@example.test",
        "ftp://example.test/a",
        "https://example.test/one, https://other.test/two",
        "https://example.test/one,https://other.test/two",
        "https://example.test/?value=bad](https://other.test/",
    ],
)
def test_unrecoverable_values_are_rejected(value):
    with pytest.raises(InvalidHttpUrl):
        normalize_http_url(value)


@pytest.mark.parametrize(
    "value", ["javascript:alert(1)", "https:relative", "//[broken", "/a\nb"]
)
def test_base_url_cannot_hide_invalid_input(value):
    with pytest.raises(InvalidHttpUrl):
        normalize_http_url(value, base_url="https://example.test/")


def test_invalid_base_is_not_used_for_relative_urls():
    with pytest.raises(InvalidHttpUrl):
        normalize_http_url("/image.jpg", base_url="https://invalid host.test/")


def test_https_is_an_explicit_policy():
    assert normalize_http_url("http://example.test/a") == "http://example.test/a"
    assert (
        normalize_http_url("http://example.test/a", force_https=True)
        == "https://example.test/a"
    )
    assert force_https(" http://example.test/a b ") == "https://example.test/a%20b"


def test_optional_urls_log_context_before_using_null(caplog):
    logger = logging.getLogger(__name__)
    assert (
        normalize_optional_http_url(
            "https://invalid host.test/image.jpg",
            logger=logger,
            context="cover for News",
        )
        is None
    )
    assert "cover for News" in caplog.text
    assert "https://invalid host.test/image.jpg" in caplog.text
    assert "using null" in caplog.text


@pytest.mark.parametrize("value", [None, "", " \n"])
def test_missing_optional_url_is_null(value, caplog):
    assert (
        normalize_optional_http_url(
            value, logger=logging.getLogger(__name__), context="missing image"
        )
        is None
    )
    assert not caplog.records


def test_query_helpers_use_the_same_normalization():
    url = "http://dept.site.nthu.edu.tw/cover image?Lang=zh-tw&name=a%20b#part one"
    assert update_url_query_param(url, "Lang", "en") == (
        "https://dept.site.nthu.edu.tw/cover%20image?Lang=en&name=a+b#part%20one"
    )
    assert update_url_query_param(url, "Lang", "en", force_https=False).startswith(
        "http://"
    )
    assert build_multi_lang_urls(url, ["en", "zh-tw"]) == {
        language: update_url_query_param(url, "Lang", language)
        for language in ["en", "zh-tw"]
    }


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://dept.site.nthu.edu.tw/", True),
        ("https://site.nthu.edu.tw/", True),
        ("https://evilsite.nthu.edu.tw/", False),
        ("https://site.nthu.edu.tw.example.test/", False),
    ],
)
def test_domain_suffix_matches_host_boundaries(url, expected):
    assert check_domain_suffix(url, "site.nthu.edu.tw") is expected

"""Offline tests for the NTHU Library spider parsers and pipeline."""

import json
import logging
from copy import deepcopy
from datetime import date
from html import escape
from pathlib import Path

import pytest

from nthu_scraper.spiders import nthu_libraries
from nthu_scraper.spiders.nthu_libraries import (
    CALENDARS,
    LibrariesPipeline,
    _make_event_id,
    get_calendar_window,
    normalize_rss_items,
    parse_calendar,
    parse_rss,
)
from nthu_scraper.utils.url_utils import http_url_error

RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>國立清華大學圖書館</title>
<item>
<guid>2024</guid>
<category>展覽與活動</category>
<title>【活動快訊】週三響時光</title>
<link></link>
<pubDate>Tue, 22 Sep 2026 14:38:27 +0800</pubDate>
<description><![CDATA[第一行<br />
第二行]]></description>
<author>ref@my.nthu.edu.tw (NTHU Library 服務推廣組)</author>
<image><url>//www.lib.nthu.edu.tw/image/news/2/music.jpg</url>
<title>【活動快訊】週三響時光</title>
<link>/</link>
</image>
</item>
<item>
<guid>2025</guid>
<category>最新消息</category>
<title>招募</title>
<link>recruit</link>
<pubDate>Wed, 23 Sep 2026 09:00:00 +0800</pubDate>
<description><![CDATA[內容]]></description>
<author>lib@lib.nthu.edu.tw</author>
</item>
</channel>
</rss>
"""

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
X-WR-CALNAME:總圖書館開館行事曆
X-WR-TIMEZONE:Asia/Taipei
X-WR-CALDESC:測試日曆
BEGIN:VEVENT
UID:single@test
DTSTART;VALUE=DATE:20260925
DTEND;VALUE=DATE:20260926
SUMMARY:中秋節閉館 Closed
DESCRIPTION:星期五
END:VEVENT
BEGIN:VEVENT
UID:weekly@test
DTSTART;VALUE=DATE:20260906
DTEND;VALUE=DATE:20260907
RRULE:FREQ=WEEKLY;BYDAY=SU
SUMMARY:總圖 10:00-18:00
END:VEVENT
BEGIN:VEVENT
UID:timed@test
DTSTART;TZID=Asia/Taipei:20260928T080000
DTEND;TZID=Asia/Taipei:20260928T220000
SUMMARY:總圖 08:00-22:00
END:VEVENT
BEGIN:VEVENT
UID:old@test
DTSTART;VALUE=DATE:20200101
DTEND;VALUE=DATE:20200102
SUMMARY:Out of window
END:VEVENT
END:VCALENDAR
"""


def rss_article(title):
    return {
        "guid": None,
        "category": None,
        "title": title,
        "link": None,
        "pubDate": None,
        "description": "",
        "author": None,
        "image": None,
    }


@pytest.fixture
def published_items():
    xml = Path(__file__).parent / "fixtures" / "libraries" / "published_urls.xml"
    return parse_rss(xml.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "start,expected",
    [
        ("2026-09-25", "36c05c1cf357ffe2"),
        ("2026-09-28T22:00:00+08:00", "ad548bfa249d7b68"),
    ],
)
def test_public_event_id_contract(start, expected):
    assert _make_event_id("event@example.test", start) == expected


class TestParseRss:
    def test_parses_all_items(self):
        items = parse_rss(RSS_XML)
        assert [item["guid"] for item in items] == ["2024", "2025"]

    def test_normalizes_urls_and_description(self):
        first, second = parse_rss(RSS_XML)
        assert first["link"] is None
        assert first["description"] == "第一行\n第二行"
        assert (
            first["image"]["url"]
            == "https://www.lib.nthu.edu.tw/image/news/2/music.jpg"
        )
        assert first["image"]["link"] == "https://www.lib.nthu.edu.tw/"
        assert second["link"] == "https://www.lib.nthu.edu.tw/recruit"
        assert second["image"] is None

    @pytest.mark.parametrize(
        "link,expected",
        [
            ("recruit", "https://www.lib.nthu.edu.tw/recruit"),
            ("//www.lib.nthu.edu.tw/", "https://www.lib.nthu.edu.tw/"),
            (
                " https://example.test/one, https://example.test/two ",
                "https://example.test/one",
            ),
            (
                "https://example.test/one,https://example.test/two",
                "https://example.test/one",
            ),
            (
                "https://example.test/form?usp=header, https://example.test/two",
                "https://example.test/form?usp=header",
            ),
            ("//example.test/one,\n//example.test/two", "https://example.test/one"),
            (
                "https://example.test/one, HTTPS://example.test/two",
                "https://example.test/one",
            ),
            (
                "https://example.test/one, //example.test/two",
                "https://example.test/one",
            ),
            (
                "https://example.test/one,//example.test/two",
                "https://example.test/one",
            ),
            (
                "https://www.emerald.com/insight/,https://forms.gle/65YaF7R1z52VU9S19",
                "https://www.emerald.com/insight/",
            ),
            (
                "/one, /two",
                "https://www.lib.nthu.edu.tw/one",
            ),
            (
                "https://example.test/one, javascript:alert(1)",
                "https://example.test/one",
            ),
            (
                "/article with space",
                "https://www.lib.nthu.edu.tw/article%20with%20space",
            ),
            (
                "https://example.test/one,two?values=a,b#one,two",
                "https://example.test/one,two?values=a,b#one,two",
            ),
            (
                "https://example.test/search?paths=/one,/two",
                "https://example.test/search?paths=/one,/two",
            ),
            (
                "https://example.test/one,/two",
                "https://example.test/one,/two",
            ),
        ],
    )
    def test_article_links_are_single_valid_urls(self, link, expected):
        (item,) = parse_rss(
            "<rss><channel><item><title>News</title>"
            f"<link>{escape(link)}</link></item></channel></rss>"
        )
        assert item["link"] == expected
        assert (
            normalize_rss_items([{**rss_article("News"), "link": link}])[0]["link"]
            == expected
        )
        assert normalize_rss_items([item]) == [item]
        assert http_url_error(item["link"]) is None

    @pytest.mark.parametrize(
        "link",
        [
            "https://",
            "https://invalid host.test/article",
            "javascript:alert(1)",
            "javascript:alert(1), https://example.test/valid",
            "https://example.test/one\ntwo",
            "https://, https://example.test/valid",
        ],
    )
    def test_invalid_article_link_is_null_without_losing_article(self, link, caplog):
        items = parse_rss(
            "<rss><channel><item><guid>Bad link</guid><title>News</title>"
            f"<link>{escape(link)}</link></item>"
            "<item><title>Sibling</title></item></channel></rss>"
        )
        assert [item["title"] for item in items] == ["News", "Sibling"]
        assert items[0]["link"] is None
        assert (
            normalize_rss_items([{**rss_article("News"), "link": link}])[0]["link"]
            is None
        )
        assert "Bad link" in caplog.text
        assert "using null" in caplog.text

    @pytest.mark.parametrize("link", [42, [], {}])
    def test_invalid_article_link_value_is_null(self, link, caplog):
        assert normalize_rss_items([{**rss_article("News"), "link": link}]) == [
            rss_article("News")
        ]
        assert "using null" in caplog.text

    def test_clean_text_for_fresh_and_retained_articles(self):
        xml = (
            "<rss><channel><item><guid>123</guid>"
            "<title>  News\n\t Items\u3000 </title>"
            "<category> New\r\n Resources </category>"
            "<author> Library\t Staff </author>"
            "<pubDate> Fri, 02 Oct 2026\n15:54:21 +0800 </pubDate>"
            "<description><![CDATA[ First<br>Second<BR/>Third<br />\n"
            "Fourth\t  & fifth ]]></description>"
            "<image><url>/cover.jpg</url><title> Cover\n Title </title></image>"
            "</item></channel></rss>"
        )
        (item,) = parse_rss(xml)
        assert item["title"] == "News Items"
        assert item["category"] == "New Resources"
        assert item["author"] == "Library Staff"
        assert item["pubDate"] == "Fri, 02 Oct 2026 15:54:21 +0800"
        assert item["description"] == "First\nSecond\nThird\nFourth & fifth"
        assert item["image"]["title"] == "Cover Title"
        retained = {
            **item,
            "title": "  News\n\t Items\u3000 ",
            "category": " New\r\n Resources ",
            "author": " Library\t Staff ",
            "pubDate": " Fri, 02 Oct 2026\n15:54:21 +0800 ",
            "description": " First<br>Second<BR/>Third<br />\nFourth\t  & fifth ",
            "image": {**item["image"], "title": " Cover\n Title "},
        }
        original = deepcopy(retained)
        assert normalize_rss_items([retained]) == [item]
        assert retained == original
        assert normalize_rss_items([item]) == [item]

    @pytest.mark.parametrize(
        "description",
        [
            "  First\n\n\n Second\t Line  \n",
            "\r\n First\r\n \t\r\n Second  Line \r\n",
            " First\r\rSecond Line ",
            " First<br><BR/><br /> Second Line ",
            " First<br />\n\n\u3000\n Second Line ",
        ],
    )
    def test_description_keeps_only_one_consecutive_newline(self, description):
        (item,) = parse_rss(
            "<rss><channel><item><title>News</title>"
            f"<description><![CDATA[{description}]]></description>"
            "</item></channel></rss>"
        )
        expected = {**rss_article("News"), "description": "First\nSecond Line"}
        assert item == expected
        assert normalize_rss_items(
            [{**rss_article("News"), "description": description}]
        ) == [expected]

    def test_blank_optional_text_is_null(self):
        article = {
            **rss_article("News"),
            "category": " \t",
            "author": "\n",
            "pubDate": "\u3000",
            "description": " \r\n<br/> ",
        }
        assert normalize_rss_items([article]) == [rss_article("News")]

    @pytest.mark.parametrize(
        "url,expected",
        [
            (
                "//www.lib.nthu.edu.tw/image/cover image.jpg",
                "https://www.lib.nthu.edu.tw/image/cover%20image.jpg",
            ),
            (
                "https://example.test/cover%2Fone image.jpg?name=a%20b#cover",
                "https://example.test/cover%2Fone%20image.jpg?name=a%20b#cover",
            ),
            (
                "https://example.test/cover%20image.jpg",
                "https://example.test/cover%20image.jpg",
            ),
            (
                "/image/週三.jpg",
                "https://www.lib.nthu.edu.tw/image/%E9%80%B1%E4%B8%89.jpg",
            ),
        ],
    )
    def test_image_urls_share_normalization(self, url, expected):
        (item,) = parse_rss(
            "<rss><channel><item><title>News</title>"
            f"<image><url>{escape(url)}</url></image></item></channel></rss>"
        )
        assert item["image"] == {"url": expected, "title": None, "link": None}
        assert normalize_rss_items([item]) == [item]

    @pytest.mark.parametrize(
        "url",
        [
            "https://",
            "https://invalid host.test/image.jpg",
            "https://example.test/co\tver.jpg",
            "javascript:alert(1)",
        ],
    )
    def test_invalid_image_is_null_without_losing_article(self, url, caplog):
        items = parse_rss(
            "<rss><channel><item><guid>Bad image</guid><title>News</title>"
            f"<image><url>{escape(url)}</url></image></item>"
            "<item><title>Sibling</title></item></channel></rss>"
        )
        assert [item["title"] for item in items] == ["News", "Sibling"]
        assert items[0]["image"] is None
        assert "Bad image" in caplog.text
        assert repr(url) in caplog.text
        assert "using null" in caplog.text

    def test_invalid_image_link_does_not_discard_a_valid_image(self, caplog):
        items = [
            {
                **rss_article("News"),
                "image": {
                    "url": "//example.test/cover image.jpg",
                    "link": "javascript:alert(1)",
                    "title": "Cover",
                    "publisher_metadata": {"retain": True},
                },
                "publisher_metadata": {"retain": True},
            }
        ]
        original = deepcopy(items)
        normalized = normalize_rss_items(items)
        assert items == original
        assert normalized[0]["image"] == {
            "url": "https://example.test/cover%20image.jpg",
            "link": None,
            "title": "Cover",
            "publisher_metadata": {"retain": True},
        }
        assert normalized[0]["publisher_metadata"] == {"retain": True}
        assert "image" in caplog.text

    @pytest.mark.parametrize("url", [42, [], {}])
    def test_invalid_image_value_is_null(self, url, caplog):
        normalized = normalize_rss_items(
            [{**rss_article("News"), "image": {"url": url}}]
        )
        assert normalized == [rss_article("News")]
        assert "using null" in caplog.text

    @pytest.mark.parametrize("link", ["", " \n"])
    def test_blank_retained_links_match_fresh_output(self, link):
        assert normalize_rss_items([{**rss_article("News"), "link": link}]) == [
            rss_article("News")
        ]

    @pytest.mark.parametrize("title", ["", " ", "\t\n", "\u3000", "\u00a0", "\x1c"])
    def test_nonblank_title_is_required_for_fresh_and_retained_feeds(self, title):
        with pytest.raises(nthu_libraries.InvalidLibrarySource):
            parse_rss(
                "<rss><channel><item>"
                f"<title>{escape(title)}</title>"
                "</item></channel></rss>"
            )
        with pytest.raises(nthu_libraries.InvalidLibrarySource):
            normalize_rss_items([rss_article(title)])

    def test_valid_retained_title_text_is_cleaned(self):
        title = " \tMeaningful title\u3000"
        assert normalize_rss_items([rss_article(title)])[0]["title"] == (
            "Meaningful title"
        )

    def test_published_url_cases_preserve_all_articles(self, published_items):
        assert len(published_items) == 5
        assert published_items[0]["link"] == (
            "https://www.proquest.com/centralpremium/index"
        )
        assert published_items[1]["link"] == "https://hyread.cc/2026Ericdata"
        assert published_items[2]["link"].endswith("/viewform?usp=header")
        assert published_items[3]["link"] == "https://oversea.cnki.net/tra"
        assert published_items[3]["image"]["url"].endswith("CNKI%20Trial.jpg")
        assert published_items[4]["image"]["url"].endswith("Wiley%20UBCM.jpg")
        assert normalize_rss_items(published_items) == published_items
        for item in published_items:
            assert http_url_error(item["link"]) is None
            if item["image"]:
                assert http_url_error(item["image"]["url"]) is None
                assert http_url_error(item["image"]["link"]) is None


class TestParseCalendar:
    @pytest.fixture
    def calendar(self):
        return parse_calendar(ICS, date(2026, 9, 1), date(2026, 10, 1))

    def test_metadata(self, calendar):
        assert calendar["name"] == "總圖書館開館行事曆"
        assert calendar["description"] == "測試日曆"
        assert calendar["timezone"] == "Asia/Taipei"

    def test_expands_recurring_events_within_window(self, calendar):
        sundays = [
            e["start"] for e in calendar["events"] if e["title"] == "總圖 10:00-18:00"
        ]
        assert sundays == ["2026-09-06", "2026-09-13", "2026-09-20", "2026-09-27"]

    def test_excludes_events_outside_window(self, calendar):
        assert all(e["title"] != "Out of window" for e in calendar["events"])

    def test_all_day_event(self, calendar):
        event = next(e for e in calendar["events"] if e["start"] == "2026-09-25")
        assert event["all_day"] is True
        assert event["end"] == "2026-09-26"
        assert event["description"] == "星期五"

    def test_timed_event_uses_taipei_offset(self, calendar):
        event = next(e for e in calendar["events"] if not e["all_day"])
        assert event["start"] == "2026-09-28T08:00:00+08:00"
        assert event["end"] == "2026-09-28T22:00:00+08:00"

    def test_ids_are_unique_and_stable(self, calendar):
        ids = [e["id"] for e in calendar["events"]]
        assert len(ids) == len(set(ids))
        again = parse_calendar(ICS, date(2026, 9, 1), date(2026, 10, 1))
        assert ids == [e["id"] for e in again["events"]]

    def test_events_are_sorted(self, calendar):
        starts = [e["start"] for e in calendar["events"]]
        assert starts == sorted(starts)


def test_calendar_window_is_year_aligned():
    assert get_calendar_window(date(2026, 9, 25)) == (
        date(2025, 1, 1),
        date(2028, 1, 1),
    )


class TestLibrariesPipeline:
    @pytest.fixture
    def paths(self, tmp_path, monkeypatch):
        rss_path = tmp_path / "rss.json"
        calendars_path = tmp_path / "calendars.json"
        monkeypatch.setattr(nthu_libraries, "LIBRARIES_RSS_JSON_PATH", rss_path)
        monkeypatch.setattr(
            nthu_libraries, "LIBRARIES_CALENDARS_JSON_PATH", calendars_path
        )
        return rss_path, calendars_path

    @staticmethod
    def _run(items):
        class FakeSpider:
            logger = logging.getLogger(__name__)

        pipeline = LibrariesPipeline()
        pipeline.open_spider(FakeSpider)
        for item in items:
            pipeline.process_item(item, FakeSpider)
        pipeline.close_spider(FakeSpider)

    def test_keeps_previous_data_for_failed_sources(self, paths):
        rss_path, calendars_path = paths
        rss_path.write_text(
            json.dumps({"news": [rss_article("Old")], "exhibit": [rss_article("Old")]}),
            encoding="utf-8",
        )
        calendars_path.write_text(
            json.dumps(
                [{"id": "main", "events": ["old"]}, {"id": "hss", "events": ["old"]}]
            ),
            encoding="utf-8",
        )

        self._run(
            [
                {"kind": "rss", "key": "news", "data": [rss_article("New")]},
                {
                    "kind": "calendar",
                    "key": "hss",
                    "data": {"id": "hss", "events": ["new"]},
                },
            ]
        )

        assert json.loads(rss_path.read_text(encoding="utf-8")) == {
            "news": [rss_article("New")],
            "exhibit": [rss_article("Old")],
        }
        assert json.loads(calendars_path.read_text(encoding="utf-8")) == [
            {"id": "main", "events": ["old"]},
            {"id": "hss", "events": ["new"]},
        ]

    def test_does_not_write_when_everything_failed(self, paths):
        rss_path, calendars_path = paths
        self._run([])
        assert not rss_path.exists()
        assert not calendars_path.exists()

    def test_calendars_follow_configured_order(self, paths):
        _, calendars_path = paths
        self._run(
            [
                {"kind": "calendar", "key": key, "data": {"id": key, "events": []}}
                for key in reversed(list(CALENDARS))
            ]
        )
        saved = json.loads(calendars_path.read_text(encoding="utf-8"))
        assert [c["id"] for c in saved] == list(CALENDARS)

    def test_empty_refresh_preserves_nonempty_sources(self, paths):
        rss_path, calendars_path = paths
        rss_path.write_text(
            json.dumps({"news": [rss_article("Old")]}), encoding="utf-8"
        )
        calendars_path.write_text(
            json.dumps([{"id": "main", "events": ["old"]}]), encoding="utf-8"
        )
        self._run(
            [
                {"kind": "rss", "key": "news", "data": []},
                {
                    "kind": "calendar",
                    "key": "main",
                    "data": {"id": "main", "events": []},
                },
            ]
        )
        assert json.loads(rss_path.read_text(encoding="utf-8")) == {
            "news": [rss_article("Old")]
        }
        assert json.loads(calendars_path.read_text(encoding="utf-8")) == [
            {"id": "main", "events": ["old"]}
        ]

    @pytest.mark.parametrize("refresh", [False, True])
    def test_repairs_retained_rss_even_when_refresh_fails(self, paths, refresh, caplog):
        rss_path, _ = paths
        old = {
            **rss_article(" Old\n Title "),
            "description": " First<br />\n Second\t Line ",
            "link": "https://example.test/one, https://example.test/two",
            "image": {"url": "//example.test/cover image.jpg"},
            "publisher_metadata": {"retain": True},
        }
        broken = {
            **rss_article("Broken image"),
            "image": {"url": "https://invalid host.test/cover.jpg"},
        }
        rss_path.write_text(json.dumps({"news": [old, broken]}), encoding="utf-8")
        self._run(
            [{"kind": "rss", "key": "exhibit", "data": [rss_article("New")]}]
            if refresh
            else []
        )
        expected = {
            "news": [
                {
                    **old,
                    "title": "Old Title",
                    "description": "First\nSecond Line",
                    "link": "https://example.test/one",
                    "image": {
                        "url": "https://example.test/cover%20image.jpg",
                        "title": None,
                        "link": None,
                    },
                },
                {**broken, "image": None},
            ]
        }
        if refresh:
            expected["exhibit"] = [rss_article("New")]
        assert json.loads(rss_path.read_text(encoding="utf-8")) == expected
        assert "Normalized retained library RSS data" in caplog.text
        assert "source=news" in caplog.text
        before = rss_path.read_bytes()
        self._run([])
        assert rss_path.read_bytes() == before

    def test_healthy_failed_refresh_keeps_exact_bytes(self, paths):
        rss_path, _ = paths
        original = json.dumps({"news": [rss_article("Old")]}).encode()
        rss_path.write_bytes(original)
        self._run([])
        assert rss_path.read_bytes() == original

    def test_published_url_cases_are_saved_for_every_feed(self, paths, published_items):
        rss_path, _ = paths
        self._run(
            [
                {"kind": "rss", "key": key, "data": deepcopy(published_items)}
                for key in nthu_libraries.RSS_TYPES
            ]
        )
        assert json.loads(rss_path.read_text(encoding="utf-8")) == {
            key: published_items for key in nthu_libraries.RSS_TYPES
        }

    @pytest.mark.parametrize(
        "articles",
        [
            ["invalid"],
            [{}],
            [{"title": "News"}],
            [{"title": 42, "description": ""}],
            [{"title": "", "description": ""}],
            [{"title": " ", "description": ""}],
            [{"title": "\t\n", "description": ""}],
            [{"title": "\u3000", "description": ""}],
            [{"title": "\u00a0", "description": ""}],
            [{"title": "News", "description": "", "image": []}],
        ],
    )
    def test_invalid_baseline_does_not_get_overwritten(self, paths, articles):
        rss_path, _ = paths
        original = json.dumps({"news": articles}).encode()
        rss_path.write_bytes(original)
        with pytest.raises(nthu_libraries.InvalidLibrarySource):
            self._run([])
        assert rss_path.read_bytes() == original

    @pytest.mark.parametrize(
        "article",
        [{"title": 42}, rss_article(" "), rss_article("\u3000")],
    )
    def test_invalid_fresh_item_does_not_get_published(self, paths, article):
        rss_path, _ = paths
        original = json.dumps({"news": [rss_article("Old")]}).encode()
        rss_path.write_bytes(original)
        with pytest.raises(nthu_libraries.InvalidLibrarySource):
            self._run([{"kind": "rss", "key": "news", "data": [article]}])
        assert rss_path.read_bytes() == original

    def test_storage_error_is_not_hidden(self, paths, monkeypatch):
        def fail_save(*args):
            raise OSError("disk full")

        monkeypatch.setattr(nthu_libraries, "save_json", fail_save)
        with pytest.raises(OSError, match="disk full"):
            self._run([{"kind": "rss", "key": "news", "data": [rss_article("New")]}])


@pytest.mark.parametrize("error_type", [AttributeError, ValueError])
def test_library_implementation_error_is_not_treated_as_upstream_failure(
    monkeypatch, error_type
):
    def broken_parser(text):
        raise error_type("implementation regression")

    monkeypatch.setattr(nthu_libraries, "parse_rss", broken_parser)
    from scrapy.http import TextResponse

    response = TextResponse("https://example.test", body=b"test", encoding="utf-8")
    spider = nthu_libraries.LibrariesSpider()
    items = spider.parse_rss_feed(response, "news")
    with pytest.raises(error_type):
        list(items)


def test_library_errback_does_not_swallow_implementation_errors():
    from twisted.python.failure import Failure

    spider = nthu_libraries.LibrariesSpider()
    failure = Failure(AttributeError("regression"))
    with pytest.raises(AttributeError):
        spider.handle_error(failure)


@pytest.mark.parametrize(
    "xml",
    [
        "",
        "<html>Unavailable</html>",
        "<rss><channel>",
        "<error><channel></channel></error>",
        "<rss><channel></channel><channel></channel></rss>",
        "<rss><channel><item><link>/no-title</link></item></channel></rss>",
    ],
)
def test_invalid_rss_is_not_an_empty_feed(xml):
    with pytest.raises(nthu_libraries.InvalidLibrarySource):
        parse_rss(xml)


def test_valid_empty_rss_and_optional_fields():
    assert parse_rss("<rss><channel></channel></rss>") == []
    assert parse_rss(
        "<rss><channel><item><title>Only title</title></item></channel></rss>"
    ) == [
        {
            "guid": None,
            "category": None,
            "title": "Only title",
            "link": None,
            "pubDate": None,
            "description": "",
            "author": None,
            "image": None,
        }
    ]


@pytest.mark.parametrize(
    "ics",
    [
        "",
        "not a calendar",
        "BEGIN:VCALENDAR\nVERSION:2.0\n",
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:missing-start\nEND:VEVENT\nEND:VCALENDAR",
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:invalid\nEND:VEVENT\nEND:VCALENDAR",
    ],
)
def test_invalid_calendar_is_not_an_empty_calendar(ics):
    with pytest.raises(nthu_libraries.InvalidLibrarySource):
        parse_calendar(ics, date(2026, 1, 1), date(2027, 1, 1))


def test_empty_calendar():
    assert parse_calendar(
        b"BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR",
        date(2026, 1, 1),
        date(2027, 1, 1),
    ) == {"name": None, "description": None, "timezone": None, "events": []}


def test_calendar_missing_end_uses_existing_defaults():
    calendar = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:all-day
DTSTART;VALUE=DATE:20260901
SUMMARY:All day
END:VEVENT
BEGIN:VEVENT
UID:utc
DTSTART:20260902T010000Z
SUMMARY:UTC
END:VEVENT
END:VCALENDAR"""
    events = parse_calendar(calendar, date(2026, 9, 1), date(2026, 9, 3))["events"]
    assert events[0]["end"] == "2026-09-02"
    assert events[1]["start"] == events[1]["end"] == "2026-09-02T09:00:00+08:00"


@pytest.mark.parametrize(
    "boundaries",
    [
        "DTSTART;VALUE=DATE:20260902\nDTEND;VALUE=DATE:20260901",
        "DTSTART:20260902T100000Z\nDTEND:20260902T090000Z",
        "DTSTART;VALUE=DATE:20260902\nDTEND:20260903T000000Z",
        "DTSTART:20260902T100000Z\nDTEND;VALUE=DATE:20260903",
    ],
)
def test_invalid_event_boundaries_are_rejected_at_scraper_layer(boundaries):
    ics = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:broken@test\n"
        f"{boundaries}\nEND:VEVENT\nEND:VCALENDAR"
    )
    with pytest.raises(nthu_libraries.InvalidLibrarySource):
        parse_calendar(ics, date(2026, 1, 1), date(2027, 1, 1))


def test_calendar_duration_and_timezone_boundaries_remain_supported():
    ics = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:duration@test
DTSTART;VALUE=DATE:20260901
DURATION:P2D
END:VEVENT
BEGIN:VEVENT
UID:timezone@test
DTSTART:20260902T010000Z
DTEND;TZID=Asia/Taipei:20260902T100000
END:VEVENT
END:VCALENDAR"""
    events = parse_calendar(ics, date(2026, 1, 1), date(2027, 1, 1))["events"]
    assert events[0]["end"] == "2026-09-03"
    assert events[1]["start"] == "2026-09-02T09:00:00+08:00"
    assert events[1]["end"] == "2026-09-02T10:00:00+08:00"

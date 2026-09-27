import pytest
from scrapy import Request, Selector

from nthu_scraper.parsers import ParseError
from nthu_scraper.parsers.directory import (
    URL_PREFIX,
    parse_contact_table,
    parse_department_details,
    parse_department_index,
    parse_department_link,
    parse_people_table,
    translate_key,
)
from nthu_scraper.spiders.nthu_directory import DepartmentItem, DirectorySpider


def test_department_links(fixture_text):
    page = Selector(text=fixture_text("directory", "index.html"))
    assert [parse_department_link(entry.css("a")) for entry in page.css("li")] == [
        {"name": "計算機與通訊中心", "url": URL_PREFIX + "dept.php?dd=1"},
        {"name": "圖書館", "url": URL_PREFIX + "dept.php?dd=2"},
    ]


def test_tables_and_details_contract(fixture_text, capsys):
    page = Selector(text=fixture_text("directory", "department.html"))
    departments = [parse_department_link(link) for link in page.css(".story_left a")]
    expected = {
        "departments": [{"name": "網路組", "url": URL_PREFIX + "dept.php?dd=11"}],
        "contact": {
            "extension": "31000", "website": "https://example.test/",
            "email": "office@example.test", "note": "N/A", "服務時間": "09:00-17:00",
        },
        "people": [
            {"name": "測試姓名", "title": "管理員", "email": "person@example.test", "note": None},
            {"name": "另一姓名", "title": "助理"},
        ],
    }
    assert parse_contact_table(page.css("table")[0]) == expected["contact"]
    assert parse_people_table(page.css("table")[1]) == expected["people"]
    assert parse_department_details(page, departments) == expected
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("key,expected", [
    (" 分　機 ", "extension"), ("直撥電話", "phone"), ("傳真電話", "fax"),
    ("姓名", "name"), ("職稱/職責", "title"), ("Email", "email"),
    ("網頁", "website"), ("備註", "note"), (" 新欄位 ", "新欄位"),
])
def test_translated_and_unknown_keys(key, expected):
    assert translate_key(key) == expected


@pytest.mark.parametrize("html", ["<a>No href</a>", '<a href="dept.php"></a>', "<li>No link</li>"])
def test_invalid_department_links(html):
    with pytest.raises(ParseError):
        parse_department_link(Selector(text=html).css("a"))


def test_empty_structures():
    assert parse_contact_table(Selector(text="<table></table>")) == {}
    assert parse_people_table(Selector(text="<table></table>")) == []
    assert parse_people_table(Selector(text="<table><tr><td>姓名</td></tr></table>")) == []
    assert parse_department_details(Selector(text='<div class="story_max"></div>'), []) == {
        "departments": [], "contact": {}, "people": [],
    }


@pytest.mark.parametrize("parser,html", [
    (parse_contact_table, "<table><tr><td>分機</td></tr></table>"),
    (parse_people_table, "<table><tr><th>Redesigned header</th></tr></table>"),
    (parse_people_table, "<table><tr><td>姓名</td></tr><tr></tr></table>"),
])
def test_malformed_tables(parser, html):
    with pytest.raises(ParseError):
        parser(Selector(text=html))


def test_missing_department_containers():
    with pytest.raises(ParseError):
        parse_department_details(Selector(text="<p>Unavailable</p>"), [])


def test_unknown_header_and_optional_cells():
    page = Selector(text="<table><tr><td></td><td>未知</td></tr><tr><td>X</td><td></td><td>extra</td></tr></table>")
    assert parse_people_table(page) == [{"header_0": "X", "未知": None}]


@pytest.mark.parametrize("url,index", [
    (URL_PREFIX + "dept.php?dd=11&lang=en", "11"),
    (URL_PREFIX + "dept.php?lang=en&dd=2", "2"), (URL_PREFIX, None),
])
def test_department_index(url, index):
    assert parse_department_index(url) == index


def test_parent_child_callback_contract(fixture_text, html_response):
    spider = DirectorySpider()
    requests = list(spider.parse(html_response(fixture_text("directory", "index.html"))))
    assert len(requests) == 2
    parent_request = requests[0]
    parent_page = html_response(fixture_text("directory", "department.html"),
                                url=parent_request.url, meta=parent_request.meta)
    outputs = list(spider.parse_dept_page(parent_page))
    child_request = next(item for item in outputs if isinstance(item, Request))
    parent = next(item for item in outputs if isinstance(item, DepartmentItem))
    assert dict(parent) == {
        "index": "1", "name": "計算機與通訊中心", "parent_name": None,
        "url": parent_request.url,
        "details": parse_department_details(parent_page, [{"name": "網路組", "url": child_request.url}]),
    }
    child, = spider.parse_dept_page(html_response(
        fixture_text("directory", "child.html"), url=child_request.url, meta=child_request.meta,
    ))
    assert dict(child) == {
        "index": "11", "name": "網路組", "parent_name": "計算機與通訊中心",
        "url": child_request.url,
        "details": {"departments": [], "contact": {"phone": "03-0000000", "fax": "N/A"}, "people": []},
    }
    assert child_request.errback == spider.handle_request_error
    assert not spider.crawl_incomplete


def test_malformed_table_marks_whole_crawl_incomplete(html_response):
    spider = DirectorySpider()
    page = html_response('<div class="story_max"><table><tr><td>分機</td></tr></table></div>',
                         meta={"dept_name": "Dept"})
    assert list(spider.parse_dept_page(page)) == []
    assert spider.crawl_incomplete

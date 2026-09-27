import json
from dataclasses import asdict

import pytest

from nthu_scraper.spiders.nthu_courses import (
    CoursesData,
    _split_classroom_time,
    _strip_data_str,
    group_courses,
)


def test_course_fixture_contract(fixture_text):
    source = json.loads(fixture_text("courses", "courses.json"))
    expected = dict.fromkeys([
        "id", "chinese_title", "english_title", "credit", "size_limit", "student_count",
        "lecturer", "language", "class_room_and_time", "classroom", "time", "note",
        "suspend", "limit_note", "freshman_reservation", "object", "ge_type",
        "ge_category", "prerequisite", "expertise", "program", "no_extra_selection",
        "required_optional_note",
    ], "")
    expected.update(
        id="11510CS101", chinese_title="程式設計 實習", english_title="Programming Lab",
        credit="3", lecturer="測試教師", class_room_and_time="資電館101 M1M2",
        classroom="資電館101", time="M1M2", note="限本系", object="大一",
        ge_category="自然科學", required_optional_note="必修",
    )
    assert asdict(CoursesData.from_dict(source[0])) == expected
    grouped = group_courses(source)
    assert list(grouped) == ["11510", "11520"]
    assert [course["id"] for course in grouped["11510"]] == ["11510CS101", "11510CS103"]
    assert grouped["11510"][0] == expected
    assert grouped["11520"] == [asdict(CoursesData.from_dict(source[1]))]
    assert source == json.loads(fixture_text("courses", "courses.json"))


@pytest.mark.parametrize("field,aliases", [
    ("chinese_title", ["課程中文名稱", "中文課名"]),
    ("english_title", ["課程英文名稱", "英文課名"]),
    ("credit", ["學分數", "學分"]),
    ("lecturer", ["授課教師", "教師姓名", "教師"]),
    ("note", ["備註", "備註欄"]),
    ("object", ["開課對象", "選課限制條件"]),
    ("ge_category", ["通識分類", "通識類別"]),
    ("required_optional_note", ["必選修說明", "此課程已列入之系所班別"]),
])
def test_legacy_aliases_and_precedence(field, aliases):
    for alias in aliases:
        assert getattr(CoursesData.from_dict({alias: "value"}), field) == "value"
    assert getattr(CoursesData.from_dict({alias: str(i) for i, alias in enumerate(aliases)}), field) == "0"


@pytest.mark.parametrize("field,alias", [
    ("id", "科號"), ("size_limit", "人限"), ("student_count", "總人數"),
    ("language", "授課語言"), ("suspend", "停開註記"),
    ("limit_note", "課程限制說明"), ("freshman_reservation", "新生保留人數"),
    ("ge_type", "通識對象"), ("prerequisite", "擋修說明"),
    ("expertise", "第一二專長對應"), ("program", "學分學程對應"),
    ("no_extra_selection", "不可加簽說明"),
])
def test_remaining_fields(field, alias):
    assert getattr(CoursesData.from_dict({alias: "value"}), field) == "value"


@pytest.mark.parametrize("raw,expected", [
    ("Room\tM1\n", {"classroom": "Room", "time": "M1\n"}),
    ("Room", {"classroom": "Room", "time": ""}),
    ("Room\tM1\textra", {"classroom": "Room", "time": "M1"}),
    ("", {"classroom": "", "time": ""}),
])
def test_classroom_time_split(raw, expected):
    assert _split_classroom_time(raw) == expected


def test_separate_fields_override_combined():
    course = CoursesData.from_dict({
        "教室與上課時間": "Old\tM1", "教室": "New", "上課時間": "T2\n",
    })
    assert (course.classroom, course.time, course.class_room_and_time) == ("New", "T2", "Old M1")


def test_existing_text_normalization_and_missing_fields():
    assert _strip_data_str(" a<BR>b<br>c\td\ne ") == "a b c d e"
    assert _strip_data_str("<b>Title</b><br/>") == "<b>Title</b><br/>"
    assert all(value == "" for value in asdict(CoursesData.from_dict({})).values())
    assert CoursesData.from_dict({"學分": None}).credit == "None"
    assert CoursesData.from_dict({"unknown": "ignored"}).id == ""


@pytest.mark.parametrize("course_id", ["", "1151", "11510", "11510   ", "../xxCS101", "１１５１０CS101", "abcdeCS101"])
def test_malformed_course_identity_rejected_at_collection_boundary(course_id):
    # from_dict remains permissive; validation belongs to whole-response grouping.
    assert CoursesData.from_dict({"科號": course_id}).id == course_id.strip()
    with pytest.raises(ValueError, match="identity"):
        group_courses([{"科號": course_id, "中文課名": "Title"}])


@pytest.mark.parametrize("data", [[], {}, None, [None], [{}], [{"科號": "11510CS101"}]])
def test_invalid_collection(data):
    with pytest.raises(ValueError):
        group_courses(data)


def test_mixed_collection_is_not_truncated():
    with pytest.raises(ValueError):
        group_courses([{"科號": "11510CS101", "中文課名": "Title"}, {}])

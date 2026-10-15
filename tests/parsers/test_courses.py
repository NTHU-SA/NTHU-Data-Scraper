import json

import pytest

from nthu_scraper.course_data import (
    FIELD_MAPPING,
    PUBLIC_TEXT_FIELDS,
    canonical_fields,
    group_courses,
    normalize_course,
    validate_standard_course,
)

STANDARD_KEYS = {
    *PUBLIC_TEXT_FIELDS,
    "semester_code",
    "department_code",
    "course_number",
    "department_name",
    "college_name",
    "course_level_code",
    "course_level",
    "remote_teaching",
    "credits",
    "capacity",
    "capacity_unlimited",
    "enrolled_count",
    "enrollment_after_selection",
    "enrollment_after_withdrawal",
    "reserved_for_freshmen",
    "is_cancelled",
    "language_code",
    "lecturers",
    "meetings",
    "expertises",
    "programs",
    "curriculum_requirements",
    "prerequisite_text",
    "parsing_issues",
}


def test_course_fixture_contract(fixture_text):
    source = json.loads(fixture_text("courses", "courses.json"))
    grouped = group_courses(source)
    assert list(grouped) == ["11510", "11520"]
    assert [course["id"] for course in grouped["11510"]] == ["11510CS101", "11510CS103"]
    course = grouped["11510"][0]
    assert set(course) == STANDARD_KEYS
    assert course["chinese_title"] == "程式設計 實習"
    assert course["english_title"] == "Programming Lab"
    assert course["credits"] == 3
    assert course["lecturers"] == [{"label": "測試教師"}]
    assert course["meetings"] == [
        {"classroom": "資電館101", "time": "M1M2", "time_codes": ["M1", "M2"]}
    ]
    for rows in grouped.values():
        for row in rows:
            assert set(row) == STANDARD_KEYS
            validate_standard_course(row)
    assert source == json.loads(fixture_text("courses", "courses.json"))


@pytest.mark.parametrize("field,aliases", list(FIELD_MAPPING.items()))
def test_aliases_and_precedence(field, aliases):
    for alias in aliases:
        assert canonical_fields({alias: "value"})[field] == "value"
    assert (
        canonical_fields({alias: str(i) for i, alias in enumerate(aliases)})[field]
        == "0"
    )


def test_separate_fields_override_combined():
    course = normalize_course(
        canonical_fields(
            {
                "科號": "11510AES 450100",
                "中文課名": "Title",
                "教室與上課時間": "Old\tM1",
                "教室": "New",
                "上課時間": "T2\n",
            }
        )
    )
    assert course["meetings"] == [
        {"classroom": "New", "time": "T2", "time_codes": ["T2"]}
    ]
    assert "classroom" not in course
    assert "class_room_and_time" not in course


@pytest.mark.parametrize(
    "course_id",
    ["", "1151", "11510", "11510   ", "../xxCS101", "１１５１０CS101", "abcdeCS101"],
)
def test_malformed_course_identity_rejected_at_collection_boundary(course_id):
    with pytest.raises(ValueError, match="identity"):
        group_courses([{"科號": course_id, "中文課名": "Title"}])


@pytest.mark.parametrize("data", [[], {}, None, [None], [{}], [{"科號": "11510CS101"}]])
def test_invalid_collection(data):
    with pytest.raises(ValueError):
        group_courses(data)


def test_mixed_collection_is_not_truncated():
    with pytest.raises(ValueError):
        group_courses([{"科號": "11510CS101", "中文課名": "Title"}, {}])


def test_unknown_values_stay_nullable_and_raw_fields_do_not_leak():
    result = group_courses([{"科號": "11510AES 450100", "中文課名": "Title"}])["11510"][
        0
    ]
    assert set(result) == STANDARD_KEYS
    assert result["capacity"] is None
    assert result["capacity_unlimited"] is None
    assert result["department_name"] is None
    assert result["lecturers"] == []
    assert result["meetings"] == []


def test_id_spelling_preserved_and_source_semester_only_reported():
    result = normalize_course(
        {
            "id": "11510AES   450100",
            "chinese_title": "Title",
            "source_semester": "11420",
        }
    )
    assert result["id"] == "11510AES   450100"
    assert "source_semester" not in result
    assert result["parsing_issues"] == ["Source semester disagrees with course ID"]

import json

import pytest

from validate_data import (
    SnapshotValidationError,
    iter_dataset_json_files,
    validate_snapshot,
)


def _snapshot(tmp_path):
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    (data_folder / "buses.json").write_text("[]", encoding="utf-8")
    return data_folder


def test_valid_snapshot_passes(tmp_path):
    data_folder = _snapshot(tmp_path)
    assert validate_snapshot(data_folder, ("buses.json",)) == 1


def test_malformed_json_fails(tmp_path):
    data_folder = _snapshot(tmp_path)
    (data_folder / "buses.json").write_text("{", encoding="utf-8")
    with pytest.raises(SnapshotValidationError, match="Invalid JSON"):
        validate_snapshot(data_folder, ("buses.json",))


def test_zero_byte_json_fails(tmp_path):
    data_folder = _snapshot(tmp_path)
    (data_folder / "buses.json").write_bytes(b"")
    with pytest.raises(SnapshotValidationError, match="empty"):
        validate_snapshot(data_folder, ("buses.json",))


def test_missing_critical_dataset_fails(tmp_path):
    data_folder = _snapshot(tmp_path)
    with pytest.raises(SnapshotValidationError, match="courses.json"):
        validate_snapshot(data_folder, ("buses.json", "courses.json"))


def test_publishing_metadata_is_not_a_dataset(tmp_path):
    data_folder = _snapshot(tmp_path)
    (data_folder / "file_details.json").write_text(
        json.dumps({"last_updated": "now", "file_details": {}}),
        encoding="utf-8",
    )
    assert [path.name for path in iter_dataset_json_files(data_folder)] == [
        "buses.json"
    ]
    assert validate_snapshot(data_folder, ("buses.json",)) == 1


@pytest.mark.parametrize(
    "relative_path",
    [
        "courses.json",
        "courses/latest.json",
        "courses/semesters/11510.json",
        "courses/sources.json",
        "file_details.json",
        "courses/raw/unlisted.json",
        "courses/raw/latest-invalid.json",
        "courses/semesters/latest-11510.json",
    ],
)
def test_non_source_json_stays_strict_utf8(tmp_path, relative_path):
    data_folder = _snapshot(tmp_path)
    path = data_folder / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xef\xbb\xbf[]")
    with pytest.raises(SnapshotValidationError, match="Invalid JSON"):
        validate_snapshot(data_folder, ("buses.json",))


@pytest.mark.parametrize("body", [b"{", b"\xff\xff{", b""])
@pytest.mark.parametrize("filename", ["latest.json", "latest-11510.json"])
def test_raw_course_json_must_still_be_valid(tmp_path, body, filename):
    data_folder = _snapshot(tmp_path)
    path = data_folder / "courses" / "raw" / filename
    path.parent.mkdir(parents=True)
    path.write_bytes(body)
    with pytest.raises(SnapshotValidationError, match="Invalid JSON|empty"):
        validate_snapshot(data_folder, ("buses.json",))

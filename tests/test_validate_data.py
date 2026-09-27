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

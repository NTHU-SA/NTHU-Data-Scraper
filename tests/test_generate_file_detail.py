import argparse
import datetime
import json

import pytest

from generate_file_detail import (
    calculate_sha256,
    generate_file_detail_json,
    workspace_path,
)

FIRST_RUN = datetime.datetime(2026, 9, 27, 12, 0, tzinfo=datetime.timezone.utc)
SECOND_RUN = datetime.datetime(2026, 9, 27, 14, 0, tzinfo=datetime.timezone.utc)


def _entry(metadata, folder="/", index=0):
    return metadata["file_details"][folder][index]


def test_cli_paths_must_remain_in_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert workspace_path("data/file_details.json").is_relative_to(tmp_path)
    with pytest.raises(argparse.ArgumentTypeError, match="must remain within"):
        workspace_path("../file_details.json")


def test_sha256_uses_exact_file_bytes(tmp_path):
    path = tmp_path / "sample.json"
    path.write_bytes(b'{"value":1}\n')
    first = calculate_sha256(path)

    path.write_bytes(b'{"value":1}')
    second = calculate_sha256(path)

    assert first != second
    assert first == "3a37782e8974c48eebf2a0517c866ad15641c53b3d31993188796b56aeb79624"


def test_unchanged_files_preserve_versions_and_timestamps(tmp_path):
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    (data_folder / "buses.json").write_text("[]\n", encoding="utf-8")
    metadata_path = data_folder / "file_details.json"

    first = generate_file_detail_json(data_folder, metadata_path, generated_at=FIRST_RUN)
    second = generate_file_detail_json(
        data_folder, metadata_path, generated_at=SECOND_RUN
    )

    first_entry = _entry(first)
    second_entry = _entry(second)
    assert second_entry == first_entry
    assert second["last_updated"] == first["last_updated"]
    assert (
        second_entry["last_commit"]
        == second_entry["version"]
        == second_entry["sha256"]
    )


def test_changed_and_new_files_get_current_timestamp(tmp_path):
    data_folder = tmp_path / "data"
    nested = data_folder / "libraries"
    nested.mkdir(parents=True)
    (data_folder / "buses.json").write_text("[]", encoding="utf-8")
    metadata_path = data_folder / "file_details.json"
    first = generate_file_detail_json(data_folder, metadata_path, generated_at=FIRST_RUN)

    (data_folder / "buses.json").write_text("[1]", encoding="utf-8")
    (nested / "rss.json").write_text("{}", encoding="utf-8")
    second = generate_file_detail_json(
        data_folder, metadata_path, generated_at=SECOND_RUN
    )

    assert _entry(first)["sha256"] != _entry(second)["sha256"]
    assert _entry(second)["last_updated"] == "2026-09-27T22:00:00+08:00"
    assert _entry(second, "libraries")["last_updated"] == "2026-09-27T22:00:00+08:00"
    assert second["last_updated"] == "2026-09-27T22:00:00+08:00"


def test_missing_malformed_and_pre_sha_metadata_are_safe(tmp_path):
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    (data_folder / "buses.json").write_text("[]", encoding="utf-8")
    metadata_path = data_folder / "file_details.json"

    missing = generate_file_detail_json(
        data_folder, metadata_path, generated_at=FIRST_RUN
    )
    assert _entry(missing)["last_updated"] == "2026-09-27T20:00:00+08:00"

    metadata_path.write_text("{invalid", encoding="utf-8")
    malformed = generate_file_detail_json(
        data_folder, metadata_path, generated_at=SECOND_RUN
    )
    assert _entry(malformed)["last_updated"] == "2026-09-27T22:00:00+08:00"

    metadata_path.write_text(
        json.dumps(
            {
                "last_updated": "2025-01-01T00:00:00+08:00",
                "file_details": {
                    "/": [
                        {
                            "name": "buses.json",
                            "last_updated": "2025-01-01T00:00:00+08:00",
                            "last_commit": "a" * 40,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    legacy = generate_file_detail_json(
        data_folder, metadata_path, generated_at=SECOND_RUN
    )
    assert _entry(legacy)["last_updated"] == "2026-09-27T22:00:00+08:00"


def test_nested_structure_and_publishing_files_are_handled(tmp_path):
    data_folder = tmp_path / "data"
    nested = data_folder / "courses" / "semesters"
    nested.mkdir(parents=True)
    (nested / "11510.json").write_text("{}", encoding="utf-8")
    (data_folder / "index.html").write_text("<html></html>", encoding="utf-8")
    (data_folder / ".nojekyll").touch()
    (data_folder / "CNAME").write_text("data.example.test", encoding="utf-8")
    (data_folder / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
    metadata_path = data_folder / "file_details.json"

    result = generate_file_detail_json(data_folder, metadata_path, generated_at=FIRST_RUN)

    assert list(result["file_details"]) == ["courses/semesters"]
    assert _entry(result, "courses/semesters")["name"] == "11510.json"

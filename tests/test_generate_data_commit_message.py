import subprocess

import pytest

from generate_data_commit_message import (
    NoDatasetChangesError,
    StagedChange,
    generate_commit_message,
    parse_name_status_z,
    read_staged_changes,
)


def change(status, *paths):
    return StagedChange(status, paths)


def test_single_dataset():
    message = generate_commit_message([change("M", "announcements.json")])
    assert message.startswith("data(announcements): update published snapshot\n")


def test_multiple_files_in_same_dataset_do_not_duplicate_scope():
    message = generate_commit_message(
        [
            change("M", "announcements.json"),
            change("M", "announcements/foo.json"),
        ]
    )
    assert message.startswith("data(announcements): update published snapshot\n")


def test_multiple_scopes_are_sorted():
    message = generate_commit_message(
        [
            change("M", "courses.json"),
            change("M", "buses/timetable.json"),
            change("M", "announcements/foo.json"),
        ]
    )
    assert message.startswith(
        "data(announcements,buses,courses): update published snapshot\n"
    )


def test_generated_files_are_separate_and_do_not_affect_scope():
    message = generate_commit_message(
        [
            change("M", "announcements.json"),
            change("M", "file_details.json"),
            change("M", "index.html"),
        ]
    )
    assert message == (
        "data(announcements): update published snapshot\n"
        "\n"
        "Changed files:\n"
        "- M announcements.json\n"
        "\n"
        "Generated files:\n"
        "- M file_details.json\n"
        "- M index.html\n"
    )


def test_unicode_and_spaces_are_preserved():
    path = "announcements/教務處註冊組/Search results (中文).json"
    message = generate_commit_message([change("M", path)])
    assert f"- M {path}" in message


def test_added_deleted_and_renamed_files():
    message = generate_commit_message(
        [
            change("A", "buses/new.json"),
            change("D", "courses/old.json"),
            change("R100", "maps/old map.json", "maps/new map.json"),
        ]
    )
    assert "- A buses/new.json" in message
    assert "- D courses/old.json" in message
    assert "- R maps/old map.json -> maps/new map.json" in message


def test_unknown_dataset_uses_deterministic_top_level_scope():
    message = generate_commit_message([change("M", "research-data.json")])
    assert message.startswith("data(research-data): update published snapshot\n")


def test_generated_only_changes_are_rejected():
    with pytest.raises(NoDatasetChangesError, match="No real dataset changes"):
        generate_commit_message(
            [change("M", "file_details.json"), change("M", "index.html")]
        )


def test_parse_name_status_z_handles_renames_and_unicode():
    raw = (
        b"M\0announcements.json\0"
        b"R100\0announcements/old name.json\0"
        + "announcements/教務處 new.json".encode()
        + b"\0"
    )
    assert parse_name_status_z(raw) == [
        change("M", "announcements.json"),
        change(
            "R100",
            "announcements/old name.json",
            "announcements/教務處 new.json",
        ),
    ]


def test_reads_actual_staged_diff_with_unicode_and_rename(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    folder = tmp_path / "announcements"
    folder.mkdir()
    original = folder / "old name.json"
    original.write_text("{}", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=tmp_path, check=True)
    original.rename(folder / "教務處 new.json")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)

    monkeypatch.chdir(tmp_path)
    changes = read_staged_changes()

    assert changes == [
        change(
            "R100",
            "announcements/old name.json",
            "announcements/教務處 new.json",
        )
    ]

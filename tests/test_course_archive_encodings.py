import json

import pytest

from nthu_scraper.course_data import publish_sources
from validate_data import SnapshotValidationError, validate_snapshot


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "utf-16-be", "utf-16-le"])
def test_encoded_course_archive_survives_publication_and_validation(tmp_path, encoding):
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    source = [{"科號": "11510AES 450100", "中文課名": "測試"}]
    body = json.dumps(source, ensure_ascii=False).encode(encoding)
    publish_sources(
        {"latest": body},
        data_folder / "courses",
    )

    archive = data_folder / "courses" / "raw" / "latest.json"
    assert archive.read_bytes() == body
    assert (
        json.loads(
            (data_folder / "courses" / "latest.json").read_text(encoding="utf-8")
        )[0]["id"]
        == source[0]["科號"]
    )
    assert not (data_folder / "courses.json").exists()
    assert validate_snapshot(data_folder, ("courses/latest.json",)) == 5

    archive.write_bytes(b"\xff\xff{")
    with pytest.raises(SnapshotValidationError, match="Invalid JSON"):
        validate_snapshot(data_folder, ("courses/latest.json",))


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "utf-16-be", "utf-16-le"])
def test_encoded_rollover_archive_survives_snapshot_validation(tmp_path, encoding):
    data_folder = tmp_path / "data"
    folder = data_folder / "courses"
    original = json.dumps(
        [{"科號": "11510AES 450100", "中文課名": "測試"}], ensure_ascii=False
    ).encode(encoding)
    publish_sources({"latest": original}, folder)
    incoming = json.dumps([{"科號": "11520AES 450100", "中文課名": "New term"}]).encode(
        "utf-8"
    )
    publish_sources({"latest": incoming}, folder)

    assert (folder / "raw" / "latest-11510.json").read_bytes() == original
    assert validate_snapshot(data_folder, ("courses/latest.json",)) == 8

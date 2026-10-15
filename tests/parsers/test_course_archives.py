import hashlib
import json
import shutil

import pytest

from nthu_scraper.course_data import (
    load_archives,
    normalize_retained_snapshot,
    publish_sources,
)


def response(*rows):
    return json.dumps(list(rows), ensure_ascii=False).encode("utf-8")


def course(semester, suffix, title):
    return {"科號": f"{semester}AES {suffix}", "中文課名": title}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_rollover_archives_published_latest_before_replacing_it(tmp_path, encoding):
    folder = tmp_path / "courses"
    original = (
        response(course("11420", "450100", "Published snapshot"))
        .decode("utf-8")
        .encode(encoding)
    )
    folder.joinpath("raw").mkdir(parents=True)
    folder.joinpath("raw", "latest.json").write_bytes(original)
    # Rollout may start with legacy-schema semester files and no manifest.
    folder.joinpath("semesters").mkdir()
    folder.joinpath("semesters", "11420.json").write_text(
        '[{"id":"11420AES 450100","chinese_title":"Old schema"}]',
        encoding="utf-8",
    )

    incoming = response(course("11510", "450100", "New term"))
    manifest = publish_sources({"latest": incoming}, folder)
    assert manifest["path_base"] == "courses"
    archived = folder / "raw" / "latest-11420.json"
    assert archived.read_bytes() == original
    assert read_json(folder / "semesters" / "11420.json")[0]["chinese_title"] == (
        "Published snapshot"
    )
    assert {entry["id"]: entry["semesters"] for entry in manifest["sources"]} == {
        "latest": ["11510"],
        "latest-11420": ["11420"],
    }
    assert manifest["normalized_records"] == 2
    assert "field_sources" not in read_json(folder / "semesters" / "11420.json")[0]
    assert (
        next(entry for entry in manifest["sources"] if entry["id"] == "latest-11420")[
            "sha256"
        ]
        == hashlib.sha256(original).hexdigest()
    )
    for entry in manifest["sources"]:
        assert (tmp_path / manifest["path_base"] / entry["path"]).is_file()

    clean = tmp_path / "clean"
    shutil.copytree(folder / "raw", clean / "raw")
    rebuild = publish_sources(load_archives(clean), clean)
    assert rebuild == manifest
    for semester in ("11420", "11510"):
        assert read_json(clean / "semesters" / f"{semester}.json") == read_json(
            folder / "semesters" / f"{semester}.json"
        )


def test_overlapping_latest_archives_only_disappearing_semester(tmp_path):
    folder = tmp_path / "courses"
    root = folder / "latest.json"
    previous = response(
        course("11510", "450100", "Term one"),
        course("11520", "450100", "Removed course"),
    )
    publish_sources({"latest": previous}, folder)
    incoming = response(course("11520", "450200", "Current course"))
    manifest = publish_sources({"latest": incoming}, folder)
    assert (folder / "raw" / "latest-11510.json").read_bytes() == previous
    assert [row["id"] for row in read_json(folder / "semesters" / "11520.json")] == [
        "11520AES 450200"
    ]
    assert manifest["normalized_records"] == 2
    assert {entry["id"]: entry["semesters"] for entry in manifest["sources"]} == {
        "latest": ["11520"],
        "latest-11510": ["11510"],
    }
    assert (
        next(entry for entry in manifest["sources"] if entry["id"] == "latest-11510")[
            "records"
        ]
        == 1
    )
    before = {path: path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    publish_sources(load_archives(folder), folder)
    assert before == {path: path.read_bytes() for path in before}
    assert "field_sources" not in read_json(folder / "semesters" / "11510.json")[0]
    original_root = root.read_bytes()
    archived = folder / "raw" / "latest-11510.json"
    archived.write_bytes(b"corrupt archive")
    with pytest.raises(ValueError, match="checksum mismatch"):
        publish_sources(
            {"latest": response(course("11610", "450300", "Next term"))},
            folder,
        )
    assert root.read_bytes() == original_root


def test_published_semester_without_raw_source_is_retained_and_rebuildable(tmp_path):
    folder = tmp_path / "courses"
    latest = response(course("11510", "450100", "Current"))
    publish_sources({"latest": latest}, folder)
    legacy = folder / "semesters" / "11420.json"
    legacy.write_text(
        '[{"id":"11420AES 450100","chinese_title":"Published only"}]',
        encoding="utf-8",
    )
    original = legacy.read_bytes()
    manifest = publish_sources({"latest": latest}, folder)
    assert read_json(legacy) == normalize_retained_snapshot(original, "11420")
    assert (folder / "raw" / "retained-11420.json").read_bytes() == original
    assert manifest["semesters"] == ["11420", "11510"]
    assert manifest["normalized_records"] == 1
    assert manifest["retained_records"] == 1
    assert manifest["published_records"] == 2
    assert manifest["retained_published_snapshots"] == [
        {
            "id": "retained-11420",
            "semester": "11420",
            "path": "raw/retained-11420.json",
            "sha256": hashlib.sha256(original).hexdigest(),
            "records": 1,
        }
    ]
    assert {entry["id"] for entry in manifest["sources"]} == {"latest"}
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in folder.rglob("*")
        if path.is_file()
    }
    publish_sources(load_archives(folder), folder)
    assert before == {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before
    }
    clean = tmp_path / "clean"
    shutil.copytree(folder / "raw", clean / "raw")
    rebuilt = publish_sources(load_archives(clean), clean)
    assert rebuilt == manifest
    assert read_json(clean / "semesters" / "11420.json") == read_json(legacy)
    legacy.write_text(
        '[{"id":"11420AES 450100","chinese_title":"Unexpected edit"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="differs from retained snapshot"):
        publish_sources({"latest": latest}, folder)
    assert (folder / "raw" / "retained-11420.json").read_bytes() == original


@pytest.mark.parametrize(
    "invalid",
    [
        b"not json",
        b"[]",
        b'[{"id":"11510AES 450100","chinese_title":"Wrong"}]',
        '[{"id":"11420AES 450100","chinese_title":"BOM"}]'.encode("utf-8-sig"),
        '[{"id":"11420AES 450100","chinese_title":"UTF16"}]'.encode("utf-16"),
    ],
)
def test_malformed_retained_snapshot_blocks_publication(tmp_path, invalid):
    folder = tmp_path / "courses"
    legacy = folder / "semesters" / "11420.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(invalid)
    with pytest.raises(ValueError, match="Malformed retained published snapshot"):
        publish_sources(
            {"latest": response(course("11510", "450100", "Current"))},
            folder,
        )
    assert legacy.read_bytes() == invalid
    assert not (folder / "raw").exists()


def test_official_source_supersedes_but_does_not_delete_retained_snapshot(tmp_path):
    folder = tmp_path / "courses"
    legacy = folder / "semesters" / "11420.json"
    legacy.parent.mkdir(parents=True)
    original = b'[{"id":"11420AES 450100","chinese_title":"Published only"}]'
    legacy.write_bytes(original)
    latest = response(course("11510", "450100", "Current"))
    publish_sources({"latest": latest}, folder)

    incoming = response(
        course("11420", "450100", "Recovered official course"),
        course("11510", "450100", "Current"),
    )
    manifest = publish_sources({"latest": incoming}, folder)
    assert read_json(legacy)[0]["chinese_title"] == "Recovered official course"
    assert (folder / "raw" / "retained-11420.json").read_bytes() == original
    assert manifest["retained_published_snapshots"][0]["superseded"] is True
    assert manifest["normalized_records"] == manifest["published_records"] == 2
    assert manifest["retained_records"] == 0
    assert publish_sources(load_archives(folder), folder) == manifest

    clean = tmp_path / "clean"
    shutil.copytree(folder / "raw", clean / "raw")
    assert publish_sources(load_archives(clean), clean) == manifest
    assert (clean / "semesters" / "11420.json").read_bytes() == legacy.read_bytes()


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_corrupt_retained_archive_blocks_before_writes(tmp_path, missing):
    folder = tmp_path / "courses"
    root = folder / "latest.json"
    legacy = folder / "semesters" / "11420.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b'[{"id":"11420AES 450100","chinese_title":"Published only"}]')
    latest = response(course("11510", "450100", "Current"))
    publish_sources({"latest": latest}, folder)
    original_root = root.read_bytes()
    archived = folder / "raw" / "retained-11420.json"
    if missing:
        archived.unlink()
    else:
        archived.write_bytes(b"changed")
    before = {path: path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    with pytest.raises((FileNotFoundError, ValueError), match="snapshot"):
        publish_sources(
            {"latest": response(course("11520", "450100", "New term"))},
            folder,
        )
    assert before == {path: path.read_bytes() for path in before}
    assert root.read_bytes() == original_root


def test_import_can_restore_a_corrupt_configured_source(tmp_path):
    folder = tmp_path / "courses"
    latest = response(course("11510", "450100", "Current"))
    historical = response(course("10820", "450100", "Old title"))
    publish_sources({"latest": latest, "10820": historical}, folder)
    (folder / "raw" / "10820.json").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum mismatch"):
        publish_sources({"latest": latest}, folder)

    repaired = response(course("10820", "450100", "Restored title"))
    publish_sources({"latest": latest, "10820": repaired}, folder)
    assert load_archives(folder)["10820"] == repaired
    assert read_json(folder / "semesters" / "10820.json")[0]["chinese_title"] == (
        "Restored title"
    )

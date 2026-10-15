import hashlib
import json
import socket
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from nthu_scraper import course_data
from nthu_scraper.course_data import (
    SOURCE_BY_ID,
    convert_source,
    converted_records,
    publish_sources,
    validate_standard_course,
)
from nthu_scraper.course_tool import main
from nthu_scraper.storage import read_json
from validate_data import SnapshotValidationError, validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


def source_bytes(semester="11510", title="Latest"):
    return json.dumps(
        [{"科號": f"{semester}AES 450100", "中文課名": title, "學分": "0.5"}],
        ensure_ascii=False,
    ).encode("utf-16")


def snapshot(folder):
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in folder.rglob("*")
        if path.is_file()
    }


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Course import and rebuild must not use the network")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def test_import_excel_preserves_latest_and_rebuilds_from_converted(
    tmp_path, monkeypatch
):
    feed = tmp_path / "official.json"
    feed.write_bytes(source_bytes())
    data = tmp_path / "data"
    folder = data / "courses"
    assert (
        main(
            [
                "import",
                "--source",
                "latest",
                "--input",
                str(feed),
                "--data-folder",
                str(data),
            ]
        )
        == 0
    )
    latest = (folder / "latest.json").read_bytes()
    workbook = Workbook()
    workbook.active.title = "108-110"
    workbook.active.append(["科號", "中文課名", "學分", "Unknown"])
    workbook.active.append(["11020AES 450100", "History", 3, "Preserved"])
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    excel = tmp_path / "history.xlsx"
    excel.write_bytes(buffer.getvalue())
    assert (
        main(
            [
                "import",
                "--source",
                "108-110",
                "--input",
                str(excel),
                "--data-folder",
                str(data),
            ]
        )
        == 0
    )
    assert (folder / "raw" / "108-110.xlsx").read_bytes() == excel.read_bytes()
    assert (folder / "raw" / "latest.json").read_bytes() == feed.read_bytes()
    assert (folder / "latest.json").read_bytes() == latest
    assert not (data / "courses.json").exists()
    converted = read_json(folder / "raw" / "converted" / "108-110.json")
    assert converted["records"][0]["values"]["Unknown"] == "Preserved"
    assert read_json(folder / "semesters" / "11020.json")[0]["credits"] == 3
    latest_course = read_json(folder / "latest.json")[0]
    assert latest_course["credits"] == 0.5
    assert set(latest_course) == set(read_json(folder / "semesters" / "11020.json")[0])
    validate_standard_course(latest_course)
    manifest = read_json(folder / "sources.json")
    for entry in manifest["sources"]:
        converted_path = folder / entry["converted"]["path"]
        assert (
            hashlib.sha256(converted_path.read_bytes()).hexdigest()
            == (entry["converted"]["sha256"])
        )

    def forbidden_conversion(*args, **kwargs):
        raise AssertionError("Validated first-stage records must be reusable")

    monkeypatch.setattr(course_data, "read_source", forbidden_conversion)
    before = snapshot(data)
    assert main(["rebuild", "--data-folder", str(data)]) == 0
    assert snapshot(data) == before


def test_cli_entrypoint_latest_rollover_and_offline_rebuild(tmp_path):
    data = tmp_path / "data"
    incoming = tmp_path / "latest.json"
    for semester in ("11510", "11520"):
        incoming.write_bytes(source_bytes(semester))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "nthu_scraper.course_tool",
                "import",
                "--source",
                "latest",
                "--input",
                str(incoming),
                "--data-folder",
                str(data),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
    folder = data / "courses"
    assert (folder / "raw" / "latest-11510.json").read_bytes() == source_bytes("11510")
    assert read_json(folder / "latest.json")[0]["semester_code"] == "11520"
    assert read_json(folder / "semesters" / "11510.json")[0]["semester_code"] == "11510"
    before = snapshot(data)
    assert main(["rebuild", "--data-folder", str(data)]) == 0
    assert snapshot(data) == before


@pytest.mark.parametrize(
    "case", ["empty", "missing", "unknown", "wrong-format", "bad-json", "bad-excel"]
)
def test_cli_failures_exit_nonzero_without_output(tmp_path, case):
    data = tmp_path / "data"
    path = tmp_path / "source.json"
    path.write_bytes(b"{")
    args = [
        "import",
        "--source",
        "latest",
        "--input",
        str(path),
        "--data-folder",
        str(data),
    ]
    if case == "empty":
        args = ["rebuild", "--data-folder", str(data)]
    elif case == "missing":
        path.unlink()
    elif case == "unknown":
        args[2] = "unknown"
    elif case == "wrong-format":
        args[2] = "108-110"
    elif case == "bad-excel":
        args[2] = "108-110"
        excel = path.with_suffix(".xlsx")
        excel.write_bytes(b"not a workbook")
        args[4] = str(excel)
    result = subprocess.run(
        [sys.executable, "-m", "nthu_scraper.course_tool", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert result.stderr
    if case == "bad-excel":
        assert "Course processing failed" in result.stderr
        assert "Traceback" not in result.stderr
    assert not data.exists()


@pytest.mark.parametrize(
    "mutation", ["version", "identity", "checksum", "row", "records"]
)
def test_converted_document_validation(mutation):
    source = SOURCE_BY_ID["latest"]
    document = convert_source(source_bytes(), source)
    if mutation == "version":
        document["schema_version"] = 2
    elif mutation == "identity":
        document["source_id"] = "10820"
    elif mutation == "checksum":
        document["sha256"] = "bad"
    elif mutation == "row":
        document["records"][0]["origin"]["row"] = True
    else:
        document["records"] = []
    with pytest.raises(ValueError, match="invalid converted"):
        converted_records(document, source)


def test_schema_invalid_converted_json_is_not_a_valid_snapshot(tmp_path):
    folder = tmp_path / "courses"
    publish_sources({"latest": source_bytes()}, folder)
    path = folder / "raw" / "converted" / "latest.json"
    document = read_json(path)
    document["schema_version"] = 2
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SnapshotValidationError, match="Invalid converted"):
        validate_snapshot(tmp_path, ("courses/latest.json",))


@pytest.mark.parametrize("body", [b"null", b"[]", b"{}", b'{"schema_version":1}'])
def test_untracked_invalid_intermediate_cannot_be_silently_replaced(tmp_path, body):
    folder = tmp_path / "courses"
    path = folder / "raw" / "converted" / "latest.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(body)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="invalid converted"):
        publish_sources({"latest": source_bytes()}, folder)
    assert snapshot(tmp_path) == before


def test_retained_structured_values_survive_schema_cleanup(tmp_path):
    folder = tmp_path / "courses"
    body = source_bytes("11420", "Retained")
    publish_sources({"latest": body}, folder)
    row = read_json(folder / "latest.json")[0]
    row["lecturers"] = [{"name_zh": "Teacher", "name_en": "English name"}]
    row["credits"] = 2.5
    row["sources"] = [{"source_id": "old"}]
    retained = folder / "raw" / "retained-11420.json"
    original = json.dumps([row]).encode("utf-8")
    retained.write_bytes(original)
    # Simulate a published-only semester with no reconstructable official source.
    (folder / "semesters" / "11420.json").write_bytes(original)
    (folder / "raw" / "latest.json").unlink()
    (folder / "raw" / "converted" / "latest.json").unlink()
    (folder / "sources.json").unlink()
    publish_sources({"latest": source_bytes()}, folder)
    actual = read_json(folder / "semesters" / "11420.json")[0]
    assert actual["lecturers"] == row["lecturers"]
    assert actual["credits"] == 2.5
    assert "sources" not in actual
    assert retained.read_bytes() == original
    before = snapshot(tmp_path)
    publish_sources({}, folder)
    assert snapshot(tmp_path) == before


def test_retained_diagnostics_preserve_old_and_new_issues():
    from nthu_scraper.course_data import normalize_retained_snapshot

    original = json.dumps(
        [
            {
                "id": "11420AES 450100",
                "chinese_title": "Title",
                "source_semester": "11410",
                "parsing_issues": ["Existing issue"],
            }
        ]
    ).encode("utf-8")
    result = normalize_retained_snapshot(original, "11420")[0]
    assert result["parsing_issues"] == [
        "Existing issue",
        "Source semester disagrees with course ID",
    ]

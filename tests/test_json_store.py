import json
from pathlib import Path

import pytest

from nthu_scraper.storage import read_json, read_json_optional, write_json_atomic
from nthu_scraper.storage import json_store
from nthu_scraper.utils.file_utils import load_json, save_json


def test_atomic_writer_preserves_unicode_and_format(tmp_path):
    path = tmp_path / "nested" / "data.json"
    value = {"z": "\u6e05\u83ef", "a": [1]}
    write_json_atomic(value, path)
    assert read_json(path) == value
    assert path.read_text(encoding="utf-8") == json.dumps(value, ensure_ascii=False, indent=4)
    write_json_atomic(value, path, indent=2, sort_keys=True, trailing_newline=True)
    assert path.read_text(encoding="utf-8") == (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def test_missing_optional_is_distinct_from_malformed(tmp_path):
    path = tmp_path / "data.json"
    assert read_json_optional(path) is None
    assert read_json_optional(path, []) == []
    with pytest.raises(FileNotFoundError):
        read_json(path)
    path.write_text("{broken", encoding="utf-8")
    for reader in (read_json, read_json_optional, load_json):
        with pytest.raises(json.JSONDecodeError):
            reader(path)
    with pytest.raises(json.JSONDecodeError):
        write_json_atomic({}, path)
    assert path.read_text(encoding="utf-8") == "{broken"


def test_optional_reader_propagates_io_errors(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(PermissionError):
        read_json_optional(tmp_path / "data.json")


@pytest.mark.parametrize("failure", ["serialize", "write", "fsync", "replace"])
def test_failed_atomic_write_keeps_old_bytes_and_cleans_temp(tmp_path, monkeypatch, failure):
    path = tmp_path / "data.json"
    path.write_bytes(b'{"old":true}\n')
    original = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("injected failure")

    data = {"new": object()} if failure == "serialize" else {"new": True}
    if failure == "write":
        def partial_write(data, file, **kwargs):
            file.write('{"partial":')
            raise OSError("injected write failure")
        monkeypatch.setattr(json_store.json, "dump", partial_write)
    elif failure in ("fsync", "replace"):
        monkeypatch.setattr(json_store.os, failure, fail)

    with pytest.raises((TypeError, OSError)):
        save_json(data, path)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_temp_is_in_destination_directory_and_destination_stays_readable(tmp_path, monkeypatch):
    path = tmp_path / "data.json"
    save_json({"old": True}, path)
    replace = json_store.os.replace

    def inspect_replace(source, destination):
        assert Path(source).parent == path.parent
        assert read_json(destination) == {"old": True}
        assert read_json(Path(source)) == {"new": True}
        replace(source, destination)

    monkeypatch.setattr(json_store.os, "replace", inspect_replace)
    save_json({"new": True}, path)
    assert read_json(path) == {"new": True}

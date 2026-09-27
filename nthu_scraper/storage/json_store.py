"""Preserve existing JSON on serialization, write, or replacement failure."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def read_json_optional(path: Path, default: Any = None) -> Any:
    """Only a missing file is optional; malformed JSON and I/O errors propagate."""
    try:
        return read_json(path)
    except FileNotFoundError:
        return default


def write_json_atomic(
    data: Any,
    path: Path,
    *,
    ensure_ascii: bool = False,
    indent: int | None = 4,
    sort_keys: bool = False,
    ensure_dir: bool = True,
    trailing_newline: bool = False,
) -> None:
    # Standalone crawls must not overwrite a corrupt baseline either.
    read_json_optional(path)
    if ensure_dir:
        path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(
                data,
                file,
                ensure_ascii=ensure_ascii,
                indent=indent,
                sort_keys=sort_keys,
            )
            if trailing_newline:
                file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

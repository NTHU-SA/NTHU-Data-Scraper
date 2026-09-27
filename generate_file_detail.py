import argparse
import datetime
import hashlib
import json
from pathlib import Path
from typing import Iterable, Optional

TAIPEI_TIMEZONE = datetime.timezone(datetime.timedelta(hours=8))
PUBLISHING_FILES = {
    ".git",
    ".nojekyll",
    "CNAME",
    "file_details.json",
    "index.html",
}


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _generation_time(generated_at: Optional[datetime.datetime]) -> datetime.datetime:
    if generated_at is None:
        generated_at = datetime.datetime.now(datetime.timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return generated_at.astimezone(TAIPEI_TIMEZONE)


def _load_previous_details(path: Path) -> dict[tuple[str, str], dict]:
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as error:
        print(f"Warning: ignoring malformed previous metadata at {path}: {error}")
        return {}

    if not isinstance(data, dict):
        print(f"Warning: ignoring invalid previous metadata structure at {path}")
        return {}

    sections = data.get("file_details")
    if not isinstance(sections, dict):
        print(f"Warning: ignoring invalid previous metadata structure at {path}")
        return {}

    previous = {}
    for folder, entries in sections.items():
        if not isinstance(folder, str) or not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                previous[(folder, entry["name"])] = entry
    return previous


def _valid_previous_timestamp(entry: dict) -> Optional[str]:
    value = entry.get("last_updated")
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return None
    return value


def _previous_sha256(entry: dict) -> Optional[str]:
    for key in ("sha256", "version", "last_commit"):
        value = entry.get(key)
        if (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdefABCDEF" for character in value)
        ):
            return value.lower()
    return None


def _iter_published_files(data_folder: Path) -> Iterable[Path]:
    for path in sorted(data_folder.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(data_folder).as_posix()
        if relative_path in PUBLISHING_FILES:
            continue
        yield path


def generate_file_detail_json(
    data_folder: Path,
    file_detail_json_path: Path,
    include_folders: Optional[list[str]] = None,
    exclude_folders: Optional[list[str]] = None,
    generated_at: Optional[datetime.datetime] = None,
) -> dict:
    current_time = _generation_time(generated_at)
    current_time_iso = current_time.isoformat()
    previous_details = _load_previous_details(file_detail_json_path)
    file_details: dict[str, list[dict[str, str]]] = {}
    meaningful_timestamps: list[datetime.datetime] = []

    for path in _iter_published_files(data_folder):
        relative_path = path.relative_to(data_folder)
        folder_key = "/".join(relative_path.parts[:-1]) or "/"

        if exclude_folders and folder_key in exclude_folders:
            continue
        if include_folders and folder_key not in include_folders:
            continue

        sha256 = calculate_sha256(path)
        previous = previous_details.get((folder_key, path.name), {})
        previous_timestamp = _valid_previous_timestamp(previous)
        if _previous_sha256(previous) == sha256 and previous_timestamp is not None:
            last_updated = previous_timestamp
        else:
            last_updated = current_time_iso

        timestamp = datetime.datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        meaningful_timestamps.append(timestamp)
        file_details.setdefault(folder_key, []).append(
            {
                "name": path.name,
                "last_updated": last_updated,
                "last_commit": sha256,
                "version": sha256,
                "sha256": sha256,
            }
        )

    for entries in file_details.values():
        entries.sort(key=lambda entry: entry["name"])

    last_updated = (
        max(meaningful_timestamps).isoformat()
        if meaningful_timestamps
        else current_time_iso
    )
    detail_data = {"last_updated": last_updated, "file_details": file_details}

    file_detail_json_path.parent.mkdir(parents=True, exist_ok=True)
    with file_detail_json_path.open("w", encoding="utf-8") as file:
        json.dump(detail_data, file, indent=2, ensure_ascii=False, sort_keys=True)
        file.write("\n")

    print(f"{file_detail_json_path} generated.")
    return detail_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate file_details.json with exact-byte SHA-256 versions."
    )
    parser.add_argument("--include", nargs="+", help="Only include these folder keys")
    parser.add_argument("--exclude", nargs="+", help="Exclude these folder keys")
    args = parser.parse_args()
    data_folder = (Path.cwd() / "data").resolve()
    generate_file_detail_json(
        data_folder,
        data_folder / "file_details.json",
        args.include,
        args.exclude,
    )

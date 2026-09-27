import argparse
import json
from pathlib import Path

PUBLISHING_JSON_FILES = {"file_details.json"}
DEFAULT_CRITICAL_FILES = (
    "announcements.json",
    "announcements_list.json",
    "buses.json",
    "courses.json",
    "dining.json",
    "directory.json",
    "maps.json",
    "newsletters.json",
)


class SnapshotValidationError(ValueError):
    pass


def iter_dataset_json_files(data_folder: Path):
    for path in sorted(data_folder.rglob("*.json")):
        if path.relative_to(data_folder).as_posix() not in PUBLISHING_JSON_FILES:
            yield path


def _validate_json_file(path: Path) -> None:
    if path.stat().st_size == 0:
        raise SnapshotValidationError(f"JSON file is empty: {path}")
    try:
        with path.open(encoding="utf-8") as file:
            json.load(file)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SnapshotValidationError(f"Invalid JSON file {path}: {error}") from error


def validate_snapshot(
    data_folder: Path,
    critical_files: tuple[str, ...] = DEFAULT_CRITICAL_FILES,
) -> int:
    if not data_folder.is_dir():
        raise SnapshotValidationError(
            f"Published snapshot directory does not exist: {data_folder}"
        )

    missing = [name for name in critical_files if not (data_folder / name).is_file()]
    if missing:
        raise SnapshotValidationError(
            f"Missing critical dataset(s): {', '.join(missing)}"
        )

    dataset_files = list(iter_dataset_json_files(data_folder))
    if not dataset_files:
        raise SnapshotValidationError("No dataset JSON files found")
    for path in dataset_files:
        _validate_json_file(path)

    metadata_path = data_folder / "file_details.json"
    if metadata_path.exists():
        _validate_json_file(metadata_path)

    return len(dataset_files)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate a candidate data snapshot.")
    parser.add_argument(
        "--data-folder",
        type=Path,
        default=Path("data"),
        help="Candidate snapshot directory (default: data)",
    )
    args = parser.parse_args()
    try:
        count = validate_snapshot(args.data_folder)
    except SnapshotValidationError as error:
        parser.exit(1, f"Snapshot validation failed: {error}\n")
    print(f"Validated {count} dataset JSON files.")

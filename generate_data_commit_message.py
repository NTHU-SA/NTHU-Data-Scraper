import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath

GENERATED_PATHS = {"file_details.json", "index.html", ".nojekyll", "CNAME"}
DATASET_SCOPES = {
    "announcements": "announcements",
    "announcements.json": "announcements",
    "announcements_list.json": "announcements",
    "buses": "buses",
    "buses.json": "buses",
    "calendars": "calendars",
    "courses": "courses",
    "courses.json": "courses",
    "dining": "dining",
    "dining.json": "dining",
    "directory": "directory",
    "directories": "directory",
    "directories.json": "directory",
    "directory.json": "directory",
    "libraries": "libraries",
    "maps": "maps",
    "maps.json": "maps",
    "newsletters": "newsletters",
    "newsletters.json": "newsletters",
}


class NoDatasetChangesError(ValueError):
    pass


@dataclass(frozen=True)
class StagedChange:
    status: str
    paths: tuple[str, ...]

    @property
    def indicator(self) -> str:
        return self.status[0]

    @property
    def display_path(self) -> str:
        if self.indicator == "R":
            return f"{self.paths[0]} -> {self.paths[1]}"
        return self.paths[-1]

    @property
    def sort_path(self) -> str:
        return self.paths[-1]


def parse_name_status_z(raw: bytes) -> list[StagedChange]:
    fields = raw.split(b"\0")
    changes = []
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index].decode("ascii")
        index += 1
        path_count = 2 if status.startswith(("R", "C")) else 1
        if index + path_count > len(fields):
            raise ValueError("Incomplete NUL-delimited Git diff")
        paths = tuple(
            fields[index + offset].decode("utf-8") for offset in range(path_count)
        )
        index += path_count
        changes.append(StagedChange(status, paths))
    return changes


def read_staged_changes() -> list[StagedChange]:
    raw = subprocess.check_output(
        [
            "git",
            "diff",
            "--cached",
            "--name-status",
            "--find-renames",
            "-z",
        ]
    )
    return parse_name_status_z(raw)


def is_generated_path(path: str) -> bool:
    return path in GENERATED_PATHS


def dataset_scope(path: str) -> str:
    top_level = PurePosixPath(path).parts[0]
    if top_level in DATASET_SCOPES:
        return DATASET_SCOPES[top_level]

    candidate = PurePosixPath(top_level).stem.lower()
    scope = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in candidate
    ).strip("-")
    return scope or "dataset"


def generate_commit_message(changes: list[StagedChange]) -> str:
    dataset_changes = [
        change
        for change in changes
        if not all(is_generated_path(path) for path in change.paths)
    ]
    generated_changes = [
        change
        for change in changes
        if all(is_generated_path(path) for path in change.paths)
    ]

    scopes = sorted(
        {
            dataset_scope(path)
            for change in dataset_changes
            for path in change.paths
            if not is_generated_path(path)
        }
    )
    if not scopes:
        raise NoDatasetChangesError(
            "No real dataset changes are staged; refusing a generated-only snapshot."
        )

    lines = [f"data({','.join(scopes)}): update published snapshot", ""]
    lines.append("Changed files:")
    for change in sorted(dataset_changes, key=lambda item: item.sort_path):
        lines.append(f"- {change.indicator} {change.display_path}")

    if generated_changes:
        lines.extend(["", "Generated files:"])
        for change in sorted(generated_changes, key=lambda item: item.sort_path):
            lines.append(f"- {change.indicator} {change.display_path}")

    return "\n".join(lines) + "\n"


def main() -> int:
    changes = read_staged_changes()
    if not changes:
        print("No staged published data changes.", file=sys.stderr)
        return 1
    try:
        message = generate_commit_message(changes)
    except NoDatasetChangesError as error:
        print(error, file=sys.stderr)
        return 2
    sys.stdout.write(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

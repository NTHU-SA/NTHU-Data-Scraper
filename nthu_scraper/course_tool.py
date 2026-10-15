"""Import manually downloaded official course files or rebuild them offline."""

import argparse
import logging
from pathlib import Path
from zipfile import BadZipFile

from nthu_scraper.course_data import SOURCE_BY_ID, load_archives, publish_sources
from nthu_scraper.utils.constants import DATA_FOLDER


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import", help="Import a local official source")
    importer.add_argument("--source", required=True, choices=sorted(SOURCE_BY_ID))
    importer.add_argument("--input", required=True, type=Path)
    importer.add_argument("--data-folder", type=Path, default=DATA_FOLDER)
    rebuild = commands.add_parser("rebuild", help="Rebuild available local sources")
    rebuild.add_argument("--data-folder", type=Path, default=DATA_FOLDER)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    folder = args.data_folder / "courses"
    try:
        if args.command == "import":
            expected = f".{SOURCE_BY_ID[args.source].format}"
            if args.input.suffix.lower() != expected:
                raise ValueError(f"Source {args.source} requires a {expected} file")
            inputs = {args.source: args.input.read_bytes()}
        else:
            inputs = load_archives(folder)
            if not inputs:
                raise ValueError("No local course sources; import a source first")
        manifest = publish_sources(inputs, folder)
    except (ValueError, OSError, TypeError, BadZipFile) as error:
        parser.exit(1, f"Course processing failed: {error}\n")
    print(f"Published {manifest['published_records']} courses from local sources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

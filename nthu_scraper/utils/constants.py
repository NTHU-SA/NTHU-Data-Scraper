"""Constants used across the project."""

import os
from pathlib import Path

# Data folder configuration
DATA_FOLDER = Path(os.getenv("DATA_FOLDER", "data"))

# Language settings
LANGUAGES = ["zh-tw", "en"]
LANGUAGE_QUERY_PARAM = "Lang"

# Domain settings
RPAGE_DOMAIN_SUFFIX = "site.nthu.edu.tw"

# File paths
DIRECTORY_PATH = DATA_FOLDER / "directory.json"
ANNOUNCEMENTS_FOLDER = DATA_FOLDER / "announcements"
ANNOUNCEMENTS_LIST_PATH = DATA_FOLDER / "announcements_list.json"
ANNOUNCEMENTS_JSON_PATH = DATA_FOLDER / "announcements.json"
BUSES_JSON_PATH = DATA_FOLDER / "buses.json"
BUSES_FOLDER = DATA_FOLDER / "buses"

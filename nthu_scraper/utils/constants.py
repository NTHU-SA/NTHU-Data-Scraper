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
DIRECTORY_JSON_PATH = DATA_FOLDER / "directory.json"
ANNOUNCEMENTS_FOLDER = DATA_FOLDER / "announcements"
ANNOUNCEMENTS_LIST_PATH = DATA_FOLDER / "announcements_list.json"
ANNOUNCEMENTS_JSON_PATH = DATA_FOLDER / "announcements.json"
BUSES_JSON_PATH = DATA_FOLDER / "buses.json"
BUSES_FOLDER = DATA_FOLDER / "buses"
COURSES_FOLDER = DATA_FOLDER / "courses"
COURSES_JSON_PATH = DATA_FOLDER / "courses.json"
DINING_JSON_PATH = DATA_FOLDER / "dining.json"
MAPS_FOLDER = DATA_FOLDER / "maps"
MAPS_JSON_PATH = DATA_FOLDER / "maps.json"
NEWSLETTERS_JSON_PATH = DATA_FOLDER / "newsletters.json"
LIBRARIES_FOLDER = DATA_FOLDER / "libraries"
LIBRARIES_RSS_JSON_PATH = LIBRARIES_FOLDER / "rss.json"
LIBRARIES_CALENDARS_JSON_PATH = LIBRARIES_FOLDER / "calendars.json"

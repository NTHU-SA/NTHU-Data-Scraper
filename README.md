# NTHU-Data-Scraper
<p align="center">
    <em>NTHU-Data-Scraper is a project designed for NTHU developers.</em>
    <br>
    <em>We scrape data from NTHU official website with GitHub Action and deliver it with our website.</em>
</p>
<p align="center">
<a href="https://github.com/psf/black" target="_blank">
    <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
</a>
<a href="https://github.com/NTHU-SA/NTHU-Data-Scraper/actions/workflows/update_data.yml" target="_blank">
    <img src="https://github.com/NTHU-SA/NTHU-Data-Scraper/actions/workflows/update_data.yml/badge.svg" alt="Crawl and update data">
<br>
<a href="https://sonarcloud.io/summary/new_code?id=NTHU-SA_NTHU-Data-Scraper" target="_blank">
    <img src="https://sonarcloud.io/api/project_badges/measure?project=NTHU-SA_NTHU-Data-Scraper&metric=sqale_rating" alt="
Maintainability Rating">
</a>
<a href="https://sonarcloud.io/summary/new_code?id=NTHU-SA_NTHU-Data-Scraper" target="_blank">
    <img src="https://sonarcloud.io/api/project_badges/measure?project=NTHU-SA_NTHU-Data-Scraper&metric=ncloc" alt="Lines of Code">
</a>
<a href="https://sonarcloud.io/summary/new_code?id=NTHU-SA_NTHU-Data-Scraper" target="_blank">
    <img src="https://sonarcloud.io/api/project_badges/measure?project=NTHU-SA_NTHU-Data-Scraper&metric=sqale_index" alt="Technical Debt">
</a>
</p>

## Features

### Available Spiders
- **nthu_announcements_list**: Crawls and maintains a list of announcement pages
- **nthu_announcements_item**: Updates content from the announcement list
- **nthu_buses**: Scrapes campus bus schedules (supports new Nanda bus routes)
- **nthu_courses**: Fetches course information
- **nthu_dining**: Retrieves dining hall data
- **nthu_directory**: Downloads department directory
- **nthu_maps**: Gets campus map data
- **nthu_newsletters**: Collects newsletter information

### Recent Improvements
- ✅ Refactored project structure with common utility modules
- ✅ Split announcements spider into list and item crawlers
- ✅ Added support for new Nanda bus route format
- ✅ Unified JSON file operations across all spiders
- ✅ Improved error handling and logging
- ✅ Self-hosted runners now require manual trigger

## Usage

### Running Spiders Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run a single spider
python -m scrapy crawl nthu_buses

# For announcements, run list spider first, then item spider
python -m scrapy crawl nthu_announcements_list
python -m scrapy crawl nthu_announcements_item
```

### GitHub Actions

The workflow runs automatically on:
- Push to main branch
- Scheduled every 2 hours
- Manual trigger via workflow_dispatch

Self-hosted crawlers (directory, maps, newsletters) only run when manually triggered with `run_self_hosted` set to true.

## Project Structure

```
NTHU-Data-Scraper/
├── nthu_scraper/
│   ├── spiders/          # Spider implementations
│   ├── utils/            # Common utilities
│   │   ├── constants.py  # Global constants
│   │   ├── file_utils.py # JSON file operations
│   │   └── url_utils.py  # URL processing utilities
│   ├── items.py
│   ├── middlewares.py
│   ├── pipelines.py
│   └── settings.py
├── data/                 # Scraped data output
├── .github/
│   └── workflows/
│       └── update_data.yml
└── requirements.txt
```

## Credit
This project is maintained by NTHUSA 32nd.

## License
This project is licensed under the [MIT License](https://choosealicense.com/licenses/mit/).

## Acknowledgements
Thanks to SonarCloud for providing code quality metrics:

[![SonarCloud](https://sonarcloud.io/images/project_badges/sonarcloud-white.svg)](https://sonarcloud.io/summary/new_code?id=NTHU-SA_NTHU-Data-API)
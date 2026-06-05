# Total Promote Filter Extraction

This project provides tools to extract filter data (features and colors) from the Total Promote website.

## Prerequisites

- Python 3.7+
- Playwright (install via `pip install playwright`)

## Installation

1. Install dependencies:
   ```bash
   pip install playwright
   playwright install
   ```

## Usage

Run the script to extract data:

```bash
python faster-extraction.py
```

Or:

```bash
python total-promote-extraction.py
```

The scripts will:
- Load existing results from `totalpromote_filters.json`
- Process links from `links_map.json` (or fetch from homepage if not present)
- Save results to `totalpromote_filters.json`

## Configuration

- `links_map.json`: Contains URLs to process, organized by category.
- `totalpromote_filters.json`: Output file with extracted filter data.

## Features

- Parallel processing with up to 7 concurrent tabs
- Resumes from existing results if interrupted
- Handles existing data to avoid reprocessing

## Notes

- The website uses iframes, so the scripts wait for the iframe to load before scraping.
- Results are saved atomically to prevent data loss on interruption.
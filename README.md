# MangaDex Exporter

A Python tool to export your manga follows from MangaDex to AniList.

## Features

- Exports manga follows from MangaDex to AniList
- Saves progress to resume interrupted exports
- Tracks non-matched manga for manual review

## Installation

### Local Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/mangadex-exporter.git
cd mangadex-exporter
```

2. Create a virtual environment and activate it:
```bash
uv venv
```

3. Install the package in development mode:
```bash
uv pip install -e .
```

## Configuration

1. Create a `.env` file in the project root with the following variables:
```env
# MangaDex credentials
MANGADEX_USERNAME=your_username
MANGADEX_PASSWORD=your_password
MANGADEX_CLIENT_ID=your_client_id
MANGADEX_CLIENT_SECRET=your_client_secret

# AniList credentials
ANILIST_CLIENT_ID=your_client_id
ANILIST_REDIRECT_URI=http://localhost:8080  # Optional, defaults to http://localhost:8080

# Optional: Debug mode and log level
DEBUG=false  # Set to true for debug output
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

2. Get your MangaDex API credentials:
   - Go to https://mangadex.org/settings/client
   - Create a new client
   - Copy the client ID and secret

3. Get your AniList API credentials:
   - Go to https://anilist.co/settings/developer
   - Create a new client
   - Copy the client ID
   - Set the redirect URI to `http://localhost:8080`

## Usage

### Local Usage

Run the exporter:
```bash
uv run python -m mangadex_exporter
```

### Command-line Arguments

The exporter supports the following command-line arguments:

- `--force-refresh`: Force a fresh fetch of manga statuses from MangaDex, ignoring any cached data


## Data Files

The exporter creates and manages several files in the `data` directory:

- `manga_statuses.json`: Cached manga statuses from MangaDex
- `sync_progress.json`: Progress for the current sync

## License

This project is licensed under the MIT License - see the LICENSE file for details. 
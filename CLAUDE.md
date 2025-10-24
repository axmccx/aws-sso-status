# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AWS SSO Status is a macOS menu bar application built with Python 3.11 that displays the expiry time of AWS SSO sessions. It monitors the default AWS profile and provides visual indicators (✓, ⚠, ✕) for session status in the macOS menu bar.

## Architecture

This is a single-file Python application (`aws_sso_status.py`) with the following key components:

- **Main application class**: `AWSSSOStatusApp` (extends `rumps.App`) manages the menu bar UI and periodic status checks
- **Cache monitoring**: Reads AWS SSO credentials from `~/.aws/cli/cache/*.json` to extract expiration timestamps
- **Status verification**: Uses `aws sts get-caller-identity` to confirm active session validity
- **Refresh mechanism**: Triggers `aws sso login` and temporarily increases polling frequency (1s) until login completes
- **Timer system**: Runs on 60-second intervals normally, switches to 1-second intervals during login flows

The app uses `rumps` (Ridiculously Uncomplicated macOS Python Statusbar apps) for the menu bar interface and `py2app` to build a standalone macOS application bundle.

## Development Commands

### Environment setup
```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Build the macOS app
```bash
python setup.py py2app
```

The built app will be in `dist/AWS SSO Status.app`

### Run directly during development
```bash
python aws_sso_status.py
```

Note: Running directly will show the menu bar app immediately. Use Cmd+Q to quit or use the Quit menu item.

## Configuration Constants

Located in `aws_sso_status.py`:
- `CHECK_INTERVAL_SECONDS = 60`: Normal polling interval for status checks
- `EXPIRY_WARNING_MINUTES = 10`: Threshold for warning icon display
- `LOCAL_TZ = zoneinfo.ZoneInfo("America/Toronto")`: Timezone for display formatting
- `CACHE_DIR = Path("~/.aws/sso/cache").expanduser()`: Legacy location (note: code actually reads from `~/.aws/cli/cache`)

## Key Dependencies

- `rumps`: Menu bar app framework
- `py2app`: macOS app bundler
- `AppKit`: Used to hide Dock icon via `NSApplicationActivationPolicyProhibited`
- AWS CLI: Must be installed and accessible (via `which aws` or `/usr/local/bin/aws`)

## Testing Considerations

This project currently has no automated tests. When adding tests:
- Mock file system operations for cache reading
- Mock subprocess calls to AWS CLI
- Test timezone conversion logic
- Test the timer switching between fast/slow modes

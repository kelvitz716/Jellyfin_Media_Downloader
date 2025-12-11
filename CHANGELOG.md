# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] - 2024-12-11

### Added
- **Modular Architecture**: Split `main.py` (986 lines) into modular handlers
  - `src/handlers/user.py` - User commands (/start, /stats, /queue)
  - `src/handlers/admin.py` - Admin commands (/propagate, /history, /shutdown)
  - `src/handlers/organize.py` - File organization FSM
  - `src/handlers/media.py` - Media file handling
- **Session Manager**: TTL-based session management (30-min expiry) replaces `defaultdict`
- **Rate Limiting**: Token bucket rate limiter to prevent command spam
- **Structured Logging**: JSON-formatted logs with context support
- **Config Validation**: Pydantic-based configuration with fail-fast validation
- **Test Suite**: Comprehensive test coverage (157 tests)
  - Unit tests for all modules
  - Performance benchmarks
  - Test runner with completion chime

### Changed
- `main.py` reduced from 986 to ~150 lines
- `stats.py` uses bounded `deque(maxlen=1000)` instead of unbounded lists
- `media_processor.py` now supports async context manager pattern
- Improved `.gitignore` with testing and IDE entries
- Enhanced `README.md` with architecture and development docs

### Fixed
- Memory leak from unbounded session storage
- Memory growth from unbounded stats lists
- Proper session lifecycle management in MediaProcessor

## [1.0.0] - Initial Release

- Telegram bot for downloading media files
- Auto-organization using GuessIt and TMDb
- Interactive `/organize` command with inline buttons
- Bulk propagation with `/propagate`
- Download queue management
- Persistent statistics with TinyDB
- Docker deployment support

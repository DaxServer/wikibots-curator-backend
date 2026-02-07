# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

**Note:** Generic coding standards apply across all projects.

## Project Overview

Curator Backend is a FastAPI service that manages CuratorBot jobs for uploading media to Wikimedia Commons. It provides a REST API and WebSocket endpoint for the frontend, with Celery workers handling background upload tasks.

**Tech Stack:** Python 3.13, FastAPI, SQLModel, Redis, Celery, Pywikibot | **Deployment:** Wikimedia Toolforge

## Development Commands

```bash
poetry run web       # FastAPI server (port 8000) - DO NOT RUN
poetry run worker    # Celery worker - DO NOT RUN
poetry run pytest -q # Run tests
poetry run ty check  # Type check (excludes asyncapi/)
poetry run isort .   # Sort imports
poetry run ruff format  # Format code
poetry run ruff check  # Run linter
poetry run alembic upgrade head  # Apply migrations
```

**Project-Specific Development Workflow:**
After completing backend tasks, always run in order:
```bash
poetry run pytest -q && poetry run ruff check && poetry run ty check && poetry run isort . && poetry run ruff format
```

## Architecture

### Layered Architecture
```
main.py (Routes) → handler.py (Business Logic) → dal.py (Database) → models.py (SQLModel)
```

1. **Routes** (`main.py`) → validate request, get user session
2. **Handlers** (`handler*.py`) → business logic, orchestration
3. **DAL** (`dal*.py`) → database queries and persistence
4. **Models** (`models.py`) → SQLModel definitions

All database access must go through DAL functions. Use `get_session()` dependency for database sessions.

### Directory Structure
```
src/curator/
├── main.py              # FastAPI application entry point
├── auth.py              # OAuth1 authentication with Wikimedia
├── ws.py                # WebSocket endpoint
├── protocol.py          # AsyncAPI WebSocket protocol (union types)
├── admin.py             # Admin endpoints
├── frontend_utils.py    # Frontend asset management
├── app/                 # Core application logic
│   ├── config.py        # Configuration from environment
│   ├── db.py           # Database engine
│   ├── models.py        # SQLModel models
│   ├── dal.py          # Data Access Layer
│   ├── dal_optimized.py # Optimized DAL (type errors known, ignore)
│   ├── handler.py      # Business logic
│   ├── handler_optimized.py # Optimized handlers
│   ├── auth.py, crypto.py, wcqs.py, sdc_v2.py, commons.py
│   ├── rate_limiter.py  # Upload rate limiting with privileged user handling
│   └── image_models.py # Image-related models
├── handlers/            # Image source handlers
│   ├── interfaces.py   # Abstract Handler class
│   ├── mapillary_handler.py
│   └── flickr_handler.py
├── asyncapi/            # Auto-generated AsyncAPI models (do not edit)
└── workers/             # Celery workers
    ├── tasks.py        # Background tasks
    ├── celery.py       # Celery config
    └── ingest.py       # Ingestion worker
```

## Project-Specific Patterns

### Image Handler Interface
Abstract `Handler` class in `handlers/interfaces.py` defines the contract for image sources:
- `fetch_collection()` - Get all images from a collection
- `fetch_image_metadata()` - Get single image metadata
- `fetch_existing_pages()` - Check which images already exist on Commons
- `fetch_collection_ids()` - Get all image IDs in a collection
- `fetch_images_batch()` - Batch fetch images by ID

Implementations: `MapillaryHandler`, `FlickrHandler`. Used by both WebSocket handler and ingestion worker.

### Rate Limiting with Privileged Users
- Rate limiting checks user groups (`patroller`, `sysop`) using `site.has_group()` - privileged users get effectively no limit
- Uses Redis to track next available upload slot per user with key `ratelimit:{userid}:next_available`
- Celery tasks are spaced out to match allowed rate, preventing API throttling
- Pywikibot global state is protected by threading lock (`_pywikibot_lock`) due to race conditions
- When removing Redis caching functionality, remove both the usage code AND the key constant

### SDC Key Mapping Pattern
- Auto-generated AsyncAPI models use kebab-case aliases (e.g., `entity-type`, `numeric-id`)
- DAL's `_fix_sdc_keys()` function recursively maps snake_case to kebab-case for database storage
- Mapping is defined in `dal.py` and must be updated when AsyncAPI schema changes

### AsyncAPI WebSocket Protocol
- Union types `ClientMessage` and `ServerMessage` defined in `protocol.py`
- 50+ auto-generated message types in `asyncapi/`
- Two-phase upload process: creation phase (slices via `UPLOAD_SLICE`) → subscription phase (`SUBSCRIBE_BATCH`)
- `UploadSliceAck` provides immediate item status updates to client

## AsyncAPI Schema Updates

Backend models are auto-generated from `frontend/asyncapi.json`. When updating schema:

1. Update `frontend/asyncapi.json` with schema changes
2. Run `bun generate` from frontend directory
   - Generates Python models to `src/curator/asyncapi/`
   - Auto-formats generated code
3. Update all code that constructs or accesses the modified models
4. Run tests: `poetry run pytest -q`

**Design Patterns:**
- Group related fields into nested objects (e.g., `MediaImage.urls`, `MediaImage.camera`)
- Use short names without redundant prefixes (e.g., `original` not `url_original`)
- Boolean flags should be required with defaults, not Optional

## Database Migrations

Use Alembic CLI auto-generator:
```bash
poetry run alembic revision --autogenerate -m "description"
poetry run alembic upgrade head
```

## Testing

- `pytest` with tests in `tests/`
- BDD tests in `tests/bdd/`, async tests with pytest-asyncio
- **pytest timeout:** Configured to `0` (disabled) in `pytest.ini` - tests have no timeout limit
- **Mock Structure:** Mock objects must match actual return type structure (e.g., `UploadRequest` needs `id`, `key`, `status` attributes)
- **AsyncMock Assertions:** Use `assert_called_once_with()` for keyword arguments

## Configuration

All configuration via environment variables:
- `CURATOR_OAUTH1_KEY`, `CURATOR_OAUTH1_SECRET` - Wikimedia OAuth1 credentials
- `TOKEN_ENCRYPTION_KEY` - Fernet key for encrypting access tokens
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` - Redis connection
- `CELERY_CONCURRENCY`, `CELERY_MAXIMUM_WAIT_TIME`, `CELERY_TASKS_PER_WORKER` - Celery settings
- `RATE_LIMIT_DEFAULT_NORMAL`, `RATE_LIMIT_DEFAULT_PERIOD` - Upload rate limits

## Important Notes

- **Type errors in `dal_optimized.py` are known and should be ignored**
- **AsyncAPI models are auto-generated - do not edit manually**
- Use `get_session()` dependency for database sessions, don't create sessions directly
- Follow layered architecture: routes → handlers → DAL → models

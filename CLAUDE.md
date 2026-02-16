# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

**Note:** Generic coding standards apply across all projects.

## Project Overview

Curator Backend is a FastAPI service that manages CuratorBot jobs for uploading media to Wikimedia Commons. It provides a REST API and WebSocket endpoint for the frontend, with Celery workers handling background upload tasks.

**Tech Stack:** Python 3.13, FastAPI, SQLModel, Redis, Celery, MediaWikiClient (requests + mwoauth) | **Deployment:** Wikimedia Toolforge

## Development Commands

```bash
poetry run web       # FastAPI server (port 8000) - DO NOT RUN
poetry run worker    # Celery worker - DO NOT RUN
poetry run pytest -q # Run tests
poetry run ty check --exclude src/curator/app/dal_optimized.py --exclude alembic  # Type check (excludes asyncapi/)
poetry run isort .   # Sort imports
poetry run ruff format  # Format code
poetry run ruff check  # Run linter
poetry run alembic upgrade head  # Apply migrations
```

**Project-Specific Development Workflow:**
After completing backend tasks, always run in order:
```bash
poetry run isort . && poetry run ruff format && poetry run ruff check && poetry run pytest -q && poetry run ty check --exclude src/curator/app/dal_optimized.py --exclude alembic
```
Note: Type errors in `dal_optimized.py` and `alembic/` are known and should be ignored. The command above intentionally excludes them to prevent false positives.

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
│   ├── mediawiki_client.py # MediaWiki API client
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

### Image Handler Interface
Abstract `Handler` class in `handlers/interfaces.py` defines the contract for image sources:
- `fetch_collection()` - Get all images from a collection
- `fetch_image_metadata()` - Get single image metadata
- `fetch_existing_pages()` - Check which images already exist on Commons
- `fetch_collection_ids()` - Get all image IDs in a collection
- `fetch_images_batch()` - Batch fetch images by ID

Implementations: `MapillaryHandler`, `FlickrHandler`. Used by both WebSocket handler and ingestion worker.

### Rate Limiting with Privileged Users
- Rate limiting checks user groups (`patroller`, `sysop`) using `MediaWikiClient.get_user_groups()` - privileged users get effectively no limit
- Uses separate queues: `uploads-privileged` for privileged users, `uploads-normal` for regular users
- Uses Redis to track next available upload slot per user with key `ratelimit:{userid}:next_available`
- Celery tasks are spaced out to match allowed rate, preventing API throttling
- Tasks dispatched using `process_upload.apply_async(args=[upload_id, edit_group_id], queue=QUEUE_...)` based on `rate_limit.is_privileged`
- Queue constants defined in `src/curator/workers/celery.py`: `QUEUE_PRIVILEGED`, `QUEUE_NORMAL`

### MediaWiki Client Patterns
- **Use `MediaWikiClient`** - All Wikimedia Commons operations must use the `MediaWikiClient` class.
- **Use `create_mediawiki_client()`** - Helper function in `mediawiki_client.py` to create authenticated clients.
- **No Global State** - Pass `MediaWikiClient` instances where needed, or create them.
- **Async/Await** - Prefer async methods where available (or `asyncio.to_thread` for synchronous calls if needed).
- **Close Resources** - Always ensure `client.close()` is called (e.g. using `try...finally`).
- **File Uploads** - `upload_file()` accepts `file_path: str` (not `file_content: bytes`) for memory efficiency. Use `NamedTemporaryFile()` for large files.
- **Upload Orchestration** - Use `commons.py:upload_file_chunked()` for complete upload workflow (download, hash, duplicate check, upload, SDC). `MediaWikiClient.upload_file()` is a low-level method that only performs chunked upload.
- **SDC fetching by title**: Use `sites=commonswiki&titles=File:Example.jpg` instead of `ids=M12345` to avoid extra API call to fetch page ID
- **wbgetentities response when using sites/titles**: Entity is keyed by entity ID, not title - extract first entity with `next(iter(entities))`
- **Distinguish "missing" cases**: Entity ID "-1" with site/title keys = non-existent file (raise error); positive entity ID with "missing" key = file exists but no SDC (return None)

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
- **Import placement:** All imports must be at the top of test files, never inline in test functions
- BDD tests in `tests/bdd/`, async tests with pytest-asyncio
- **pytest timeout:** Configured to `0` (disabled) in `pytest.ini` - tests have no timeout limit
- **Mock Structure:** Mock objects must match actual return type structure (e.g., `UploadRequest` needs `id`, `key`, `status` attributes)
- **Celery task mocks:** When mocking `process_upload.apply_async()`, check `call[1]["queue"]` and `call[1]["args"]` for kwargs
- **AsyncMock Assertions:** Use `assert_called_once_with()` for keyword arguments

## Configuration

All configuration via environment variables:
- `CURATOR_OAUTH1_KEY`, `CURATOR_OAUTH1_SECRET` - Wikimedia OAuth1 credentials
- `TOKEN_ENCRYPTION_KEY` - Fernet key for encrypting access tokens
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` - Redis connection
- `CELERY_CONCURRENCY`, `CELERY_MAXIMUM_WAIT_TIME`, `CELERY_TASKS_PER_WORKER` - Celery settings
- `RATE_LIMIT_DEFAULT_NORMAL`, `RATE_LIMIT_DEFAULT_PERIOD` - Upload rate limits

### Pull Request Review Workflow
- Use `gh api repos/{owner}/{repo}/pulls/{number}/comments` to get line-by-line review comments with file paths and line numbers
- `gh pr view --json reviews` only shows high-level review summaries, not specific line comments

## Important Notes

- **Type errors in `dal_optimized.py` are known and should be ignored**
- **Type errors in `alembic/` are known and should be ignored**
- **AsyncAPI models are auto-generated - do not edit manually**
- **Large file uploads** - Use `NamedTemporaryFile()` with streaming downloads (see `commons.py`) to avoid OOM on large files
- Use `get_session()` dependency for database sessions, don't create sessions directly
- Follow layered architecture: routes → handlers → DAL → models
- **WebSocket cleanup pattern**: Handler's `cleanup()` method should ensure resources are released (now simpler without thread-local Pywikibot)

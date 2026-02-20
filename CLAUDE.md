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
All other files must pass type check. Even pre-existing errors in modified files should be fixed before committing.
To type-check specific files only: `poetry run ty check path/to/file.py`

## Architecture

### Layered Architecture
```
main.py (Routes) → handler.py (Business Logic) → dal.py (Database) → models.py (SQLModel)
```

1. **Routes** (`main.py`) → validate request, get user session
2. **Handlers** (`handler*.py`) → business logic, orchestration
3. **DAL** (`dal*.py`) → database queries and persistence
4. **Models** (`models.py`) → SQLModel definitions

Database access goes through DAL functions using the `get_session()` dependency.

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

### Retry Functionality

Retry functionality allows users and admins to retry failed uploads. The current implementation creates new `UploadRequest` objects (copies) in a new batch rather than modifying the originals. This preserves the original failed uploads in the original batch for history/audit purposes.

- `dal.reset_failed_uploads_to_new_batch()` - User retry, creates copies of failed uploads in new batch
- `dal.retry_selected_uploads_to_new_batch()` - Admin retry, same pattern
- After enqueueing Celery tasks, `update_celery_task_id()` is called to enable cancellation

### Rate Limiting with Privileged Users
- Rate limiting checks user groups (`patroller`, `sysop`) using `MediaWikiClient.get_user_groups()` - privileged users get effectively no limit
- Uses separate queues: `uploads-privileged` for privileged users, `uploads-normal` for regular users
- Uses Redis to track next available upload slot per user with key `ratelimit:{userid}:next_available`
- Celery tasks are spaced out to match allowed rate, preventing API throttling
- Tasks are dispatched using `process_upload.apply_async(args=[upload_id, edit_group_id], queue=QUEUE_...)` based on `rate_limit.is_privileged`
- Queue constants are defined in `src/curator/workers/celery.py`: `QUEUE_PRIVILEGED`, `QUEUE_NORMAL`

### MediaWiki Client
- `MediaWikiClient` class handles all Wikimedia Commons operations
- `create_mediawiki_client()` in `mediawiki_client.py` creates authenticated clients
- `_api_request()` supports optional retry with exponential backoff via `retry=True` parameter (3 attempts: 0s, 1s, 3s delays)
- Only `requests.exceptions.RequestException` triggers retries; other exceptions propagate immediately
- `apply_sdc()` uses `retry=True` for SDC operations which are prone to transient API errors
- Client instances are passed where needed (no global state)
- Async methods are used where available, or `asyncio.to_thread` for synchronous calls
- Clients are closed after use (e.g., using `try...finally`)
- `upload_file()` accepts `file_path: str` (not `file_content: bytes`) for memory efficiency
- `commons.py:upload_file_chunked()` provides the complete upload workflow (download, hash, duplicate check, upload, SDC). `MediaWikiClient.upload_file()` is a low-level method that only performs chunked upload.
- **Chunked upload flow**: Chunks are uploaded with `stash=1`, then a final commit publishes the file
- **Duplicate detection**: Duplicate warnings appear on the final chunk response during stash phase (with `stash=1`), NOT during final commit. The code checks for `warnings.duplicate` in chunk upload response and raises `DuplicateUploadError` before final commit.
- When fetching SDC by title, the code uses `sites=commonswiki&titles=File:Example.jpg` instead of `ids=M12345` to avoid an extra API call to fetch page ID
- When using `sites`/`titles` in wbgetentities, the entity is keyed by entity ID, not title - extracted with `next(iter(entities))`
- Entity ID "-1" with site/title keys means non-existent file (raises error); positive entity ID with "missing" key means file exists but has no SDC (returns None)

### SDC Key Mapping Pattern
- Auto-generated AsyncAPI models use kebab-case aliases (e.g., `entity-type`, `numeric-id`)
- DAL's `_fix_sdc_keys()` function recursively maps snake_case to kebab-case for database storage
- Mapping is defined in `dal.py` and is updated when AsyncAPI schema changes

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
- All imports must be at the top of test files (no inline imports)
- NO nested function definitions in tests - avoid `def func(): def inner():` pattern
- For complex mock behavior, use module-level helper functions (prefix with `_`) passed to `side_effect`
- BDD tests in `tests/bdd/`, async tests with pytest-asyncio
- pytest timeout is configured to `0` (disabled) in `pytest.ini`
- Mock objects match actual return type structure (e.g., `UploadRequest` needs `id`, `key`, `status` attributes)
- When mocking `process_upload.apply_async()`, the queue is checked via `call[1]["queue"]` and args via `call[1]["args"]`
- AsyncMock assertions use `assert_called_once_with()` for keyword arguments

### Writing Tests with Patches

When mocking file operations or other builtins, use a single `with` statement with comma-separated patches:

```python
# Wrong (nested with statements)
with patch("os.path.getsize", return_value=1000):
    with patch("builtins.open", mock_open(read_data=b"data")):
        result = func()

# Correct (single with statement)
with patch("os.path.getsize", return_value=1000), patch(
    "builtins.open", mock_open(read_data=b"data")
):
    result = func()
```

### Pull Request Review Workflow
- Use `gh api repos/{owner}/{repo}/pulls/{number}/comments` to get line-by-line review comments with file paths and line numbers
- `gh pr view --json reviews` only shows high-level review summaries, not specific line comments

### SQLModel vs SQLAlchemy Behavior
- `session.exec(select(col(Table.column))).all()` returns `list[value]`, not `list[Row]` (SQLModel-specific)
- Raw SQLAlchemy's `session.execute()` returns `list[Row]` and needs `.scalars()` to extract values
- SQLModel's `session.exec()` is a simplified wrapper that automatically unwraps scalar values
- When using `session.execute()` (not `exec`), you need `.scalars().all()` to get plain values

## Important Notes

- Type errors in `dal_optimized.py` are known and ignored
- Type errors in `alembic/` are known and ignored
- Functions that always return or raise an exception use `raise AssertionError("Unreachable")` to satisfy the type checker
- AsyncAPI models are auto-generated from `frontend/asyncapi.json`
- Large file uploads use `NamedTemporaryFile()` with streaming downloads (see `commons.py`)
- Database sessions use the `get_session()` dependency
- Code follows the layered architecture: routes → handlers → DAL → models

## Common Pitfalls and Troubleshooting

### Test Fixture Issues

The `tests/fixtures.py` file contains an autouse fixture `mock_external_calls` that patches many external dependencies. This fixture is designed for BDD tests but can cause issues with other tests. If tests fail with strange errors:

- Check if the test needs to be isolated from the autouse fixture
- The fixture patches `curator.app.handler.encrypt_access_token` and other common dependencies
- Some tests may need to run without this fixture or use `@pytest.mark.usefixtures("mock_external_calls")` explicitly

### Circular Imports

When adding imports between core modules (`commons.py`, `mediawiki_client.py`, etc.), be aware of circular dependencies:

- `commons.py` imports from `mediawiki_client.py`
- `mediawiki_client.py` should NOT import from `commons.py` directly
- For shared exceptions like `DuplicateUploadError`, use a dedicated `errors.py` module that only imports from `asyncapi` (which has no dependencies on other app modules)
- Import exceptions inside functions if needed to avoid circular imports: `from curator.app.errors import DuplicateUploadError`

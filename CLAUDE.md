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
poetry run ty check  # Type check
poetry run isort .   # Sort imports
poetry run ruff format  # Format code
poetry run ruff check  # Run linter
poetry run alembic upgrade head  # Apply migrations
```

**Project-Specific Development Workflow:**
After completing backend tasks, always run in order:
```bash
poetry run isort . && poetry run ruff format && poetry run ruff check && poetry run pytest -q && poetry run ty check
```
To type-check specific files only: `poetry run ty check path/to/file.py`

## Architecture

### Layered Architecture
```
main.py (Routes) → handler.py (Business Logic) → dal.py (Database) → models.py (SQLModel)
```

1. **Routes** (`main.py`) → validate request, get user session
2. **Handlers** (`handler*.py`) → business logic, orchestration
3. **DAL** (`dal.py`) → database queries and persistence
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
├── core/                # Business logic and application services
│   ├── config.py        # Configuration from environment
│   ├── handler.py       # WebSocket business logic
│   ├── auth.py, crypto.py, wcqs.py
│   ├── errors.py        # DuplicateUploadError, HashLockError
│   ├── geocoding.py     # Reverse geocoding for location enrichment
│   ├── task_enqueuer.py # Upload task enqueueing with rate limiting
│   ├── rate_limiter.py  # Upload rate limiting with privileged user handling
│   └── recovery.py      # Startup recovery for uploads stuck in queued state
├── db/                  # Database layer
│   ├── engine.py        # SQLAlchemy engine and get_session()
│   ├── commons_engine.py # Wikimedia Commons replica DB connection
│   ├── models.py        # SQLModel models
│   ├── dal_batches.py   # Batch queries
│   ├── dal_uploads.py   # Upload request queries
│   ├── dal_presets.py   # Preset queries
│   └── dal_users.py     # User queries
├── mediawiki/           # Wikimedia Commons integration
│   ├── client.py        # MediaWiki API client
│   ├── commons.py       # Upload workflow (download, hash, upload, SDC)
│   ├── sdc_v2.py, sdc_merge.py
├── handlers/            # Image source handlers
│   ├── interfaces.py    # Abstract Handler class
│   ├── mapillary_handler.py
│   └── flickr_handler.py
├── asyncapi/            # Auto-generated AsyncAPI models (do not edit)
└── workers/             # Celery workers
    ├── tasks.py         # Background tasks
    ├── celery.py        # Celery config
    └── ingest.py        # Ingestion worker
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

### Startup Recovery
`recovery.py` handles uploads stuck in `queued` state after a Redis restart. Uses a sentinel key (`curator:started`) written to Redis on successful startup — missing key means Redis was restarted and recovery is needed. On recovery, queued uploads are grouped by `(userid, edit_group_id)`, the OAuth token validated against MediaWiki, then re-enqueued via `enqueue_uploads()`. Invalid tokens mark the group's uploads as failed with a session-expired message in a single DB call. Called from `main.py` lifespan after Alembic migrations.
- The sentinel key is set atomically using `redis_client.set(SENTINEL_KEY, "1", nx=True)` — if it returns `None`, another instance already claimed recovery and the function returns immediately. This prevents double-enqueuing on concurrent startups.

### Retry Functionality

Retry functionality allows users and admins to retry failed uploads. The current implementation creates new `UploadRequest` objects (copies) in a new batch rather than modifying the originals. This preserves the original failed uploads in the original batch for history/audit purposes.

- `dal.reset_failed_uploads_to_new_batch()` - User retry, creates copies of failed uploads in new batch
- `dal.retry_selected_uploads_to_new_batch()` - Admin retry, same pattern
- After enqueueing Celery tasks, `update_celery_task_id()` is called to enable cancellation
- `admin_retry_uploads` in `admin.py` calls `process_upload.apply_async()` directly, bypassing `enqueue_uploads()` and rate limiting — admin retries are not rate limited

### Redis Role
Redis serves as both the Celery **broker** (task queue) and **result backend**. A Redis restart destroys all in-flight task data — tasks sitting in the broker queue are gone, but the database retains `status="queued"` records. The startup recovery system (`recovery.py`) reconciles this.

### Rate Limiting
- Rate limits are fetched from `action=query&meta=userinfo&uiprop=ratelimits|rights` via `MediaWikiClient.get_user_rate_limits()` which returns `(ratelimits, rights)`
- Each upload costs 2 edit API calls (SDC apply + null edit), so the edit limit is halved before comparing against the upload limit — the more restrictive of the two is used
- Users with the `noratelimit` right are exempt and receive `_NO_RATE_LIMIT`; MediaWiki returns `"ratelimits": {}` for exempt users (sysops, bots) — this is expected, not an error
- Uses Redis to track next available upload slot per user with key `ratelimit:{userid}:next_available`
- Rate limit keys have no TTL — stale past-timestamp values are handled correctly by `max(0.0, next_available - current_time)`, and a TTL would incorrectly reset the slot for large batches
- All uploads go to `QUEUE_NORMAL`
- `get_user_groups()` in `recovery.py` is used only to validate OAuth tokens on startup recovery — the returned groups are not used

### commons.py (Upload Workflow)
`commons.py` contains both the upload-to-Commons workflow (`upload_file_chunked`) and the image download function (`download_file`) which fetches from external CDNs (e.g., Mapillary/Facebook). Both download and upload chunk retries use `config.HTTP_RETRY_DELAYS` for escalating backoff but have separate retry loops — they differ in error handling and response processing.

### MediaWiki Client
- `MediaWikiClient` class handles all Wikimedia Commons operations
- Instantiate directly: `MediaWikiClient(access_token=access_token)`
- `_api_request()` always retries with exponential backoff (3 attempts: 0s, 1s, 3s delays)
- `requests.exceptions.RequestException`, `badtoken` CSRF errors, and OAuth "Nonce already used" errors trigger retries; other exceptions propagate immediately
- API-level error responses (e.g. `{"error": {"code": "..."}}`) are returned as-is — `_api_request` does not raise on them; callers must check for expected keys (e.g. `"query"`) before indexing
- Client instances are passed where needed (no global state)
- Async methods are used where available, or `asyncio.to_thread` for synchronous calls
- Clients are closed after use (e.g., using `try...finally`)
- `_client` is the underlying `requests.Session` — close it explicitly with `client._client.close()` in a `finally` block when the client is short-lived (not managed by a context manager)
- `upload_file()` accepts `file_path: str` (not `file_content: bytes`) for memory efficiency
- `commons.py:upload_file_chunked()` provides the complete upload workflow (download, hash, duplicate check, upload, SDC). `MediaWikiClient.upload_file()` is a low-level method that only performs chunked upload.
- **Chunked upload flow**: Chunks are uploaded with `stash=1`, then a final commit publishes the file
- **Per-chunk retryable errors**: substring match on `error.code` for `UploadStashFileException`, `uploadstash-exception` (bare variant from `handleStashException` default case — also covers `UploadChunkFileException` falling through), `UploadChunkFileException`, `JobQueueError`; also matches `backend-fail-internal` in `error.info` (handles `stashfailed` code with Swift storage errors) — transient infrastructure errors that retry up to 4 attempts with 3/5/10s delays
- **Final commit retryable errors** (substring match on `error.code`): `backend-fail-internal`, `JobQueueError` — retried with the same 4-attempt / 3/5/10s logic. The final commit has its own separate retry loop in `upload_file()`.
- **`uploadstash-file-not-found`, `uploadstash-bad-path`, and `stashfailed` (with "No chunked upload session with this key") are NOT retried inside `_upload_chunk`** — all mean the entire stash is gone, so retrying the same chunk is useless. Instead, they surface as `UploadResult(success=False)` and `_upload_with_retry` in `ingest.py` restarts the full upload from scratch (re-download + re-upload all chunks). `MAX_UPLOADSTASH_TRIES` controls how many full-restart attempts are allowed. All three are detected by `_is_uploadstash_gone_error`.
- **Chunk `UploadResult.error` format**: always `f"{error_code}: {error_info}"` — omitting the error code means any code path that checks for a specific error code string (e.g. `_is_uploadstash_gone_error`) will silently fail to match.
- **Duplicate detection**: `warnings.duplicate` and `warnings.exists` are handled during the stash phase (chunk responses with `stash=1`). `warnings.exists` (same filename, content may differ) fetches remote SHA1 and raises `DuplicateUploadError` only if hashes match; otherwise falls through to a generic warning failure. The final commit can also return a `Warning` result — `warnings.nochange` (content identical, confirmed by MediaWiki) raises `DuplicateUploadError` using the `warnings.exists` title if present. `upload_file()` accepts `file_sha1` to enable the exists comparison; `upload_file_chunked()` in `commons.py` passes the hash computed during download.
- When fetching SDC by title, the code uses `sites=commonswiki&titles=File:Example.jpg` instead of `ids=M12345` to avoid an extra API call to fetch page ID
- When using `sites`/`titles` in wbgetentities, the entity is keyed by entity ID, not title - extracted with `next(iter(entities))`
- Entity ID "-1" with site/title keys means non-existent file (raises error); positive entity ID with "missing" key means file exists but has no SDC (returns None)
- `commons.py:upload_file_chunked` acquires a Redis hash lock (keyed by file hash) after duplicate check; always released in `try/finally` — the TTL is a safety net, not the primary release mechanism
- `upload_file` in `mediawiki_client.py`: all result processing (`if "upload" in data`, error logging) lives inside the `if file_key:` block — `data` is only assigned there

### SDC Key Mapping Pattern
- Auto-generated AsyncAPI models use kebab-case aliases (e.g., `entity-type`, `numeric-id`)
- DAL's `_fix_sdc_keys()` function recursively maps snake_case to kebab-case for database storage
- Mapping is defined in `dal.py` and is updated when AsyncAPI schema changes

### Commons Replica Database

`db/commons_engine.py` provides a read-only connection to the Wikimedia Commons replica database, available from Toolforge. Uses the same `TOOL_TOOLSDB_USER`/`TOOL_TOOLSDB_PASSWORD` credentials as the app's own DB, but connects to `commonswiki.analytics.db.svc.wikimedia.cloud` / `commonswiki_p`. Falls back to `COMMONS_DB_URL` env var for local development.

**Local development:** When `TOOL_TOOLSDB_USER` is absent, the engine auto-starts an SSH tunnel through `login.toolforge.org` (override with `TOOLFORGE_SSH_HOST` env var) on the first request. Credentials are read from the Toolforge bastion via `ssh login.toolforge.org cat ~/replica.my.cnf` — no local `.cnf` file needed. The tunnel uses `start_new_session=True` so it survives poetry file-watch restarts. PyMySQL reads `.cnf` files natively via `connect_args={"read_default_file": path}` — no manual parsing needed.

The replica schema uses `linktarget` as a normalised title store — `cl_to`, `pl_title`, `tl_title` columns were removed in MediaWiki 1.43–1.45 and replaced with `cl_target_id`/`pl_target_id`/`tl_target_id` foreign keys to `linktarget(lt_id, lt_namespace, lt_title)`.

**Commons replica query patterns (benchmarked against the live replica):**

- `NOT EXISTS` subqueries are catastrophically slow on large tables like `categorylinks` (~4.5 min for 100 rows) — the optimizer cannot short-circuit them. Always use `LEFT JOIN ... WHERE p_target.page_id IS NULL` instead.
- `EXPLAIN` is not available on replica (insufficient privileges) — benchmark with `time sql commonswiki`.
- `categorylinks` does not have a `cl_to` column (removed in 1.43–1.45) — join via `cl_target_id` → `linktarget(lt_id, lt_namespace, lt_title)`.
- For categorylinks-based wanted-categories queries (discarded approach), filtering `p_from.page_namespace IN (0, 6, 14)` halves query time (3.7s → 1.7s). Not applicable to the accepted `category` table query, which has no `p_from`.
- `DISTINCT` with `LIMIT` does not allow early termination — the DB must find all distinct rows before applying the limit. Avoid `DISTINCT` on high-cardinality scans where possible; use narrow filters instead to reduce the working set.

**`category` table for wanted-categories counts:**

The `category` table stores pre-computed per-category statistics maintained by MediaWiki in real time — including for categories that don't have a page yet. Columns: `cat_title`, `cat_pages` (total members), `cat_subcats`, `cat_files`. Use `cat_pages - cat_subcats - cat_files` to get regular pages (galleries/templates). This is how `SpecialWantedCategories.php` fetches live counts in `preprocessResults()`.

Query: `SELECT c.cat_title, c.cat_subcats, c.cat_files, (c.cat_pages - c.cat_subcats - c.cat_files) AS pages, c.cat_pages AS total FROM category c LEFT JOIN page p ON p.page_namespace = 14 AND p.page_title = c.cat_title WHERE p.page_id IS NULL ORDER BY c.cat_pages DESC LIMIT 100`

Performance findings:
- `querypage=WantedCategories` MediaWiki API is disabled on Commons — cannot use the pre-computed cache via API.
- No index on `cat_pages` — `ORDER BY cat_pages DESC` always requires a full table sort (~7–16s).
- Threshold filters (`cat_pages >= N`) do not help — full scan cost is fixed regardless.
- Removing `ORDER BY` brings LIMIT 20 to 0.22s but results are unsorted and the full-scan cost returns with larger LIMITs.
- Multiple-query approach ruled out: top 10,000 categories by `cat_pages` contain only 1 missing one — missing categories are NOT correlated with the largest categories, so no indexed shortcut exists.
- GROUP BY aggregation directly on `categorylinks` takes several minutes — do not use.
- **Accepted approach**: run the ~7s query directly (admin-only, infrequent use, loading state shown). Redis caching with a Celery periodic task is the known improvement path if latency becomes a problem.

### Database Query Performance
**Only search indexed columns** - When implementing text search/filter functionality, only include columns that have database indexes. Searching unindexed columns (especially JSONB fields) will be very slow on large datasets. Check model definitions for `index=True` before adding search.

### Type Conversion Patterns
- **TypedDict for query return types** — when a query returns rows with mixed key types (e.g., `str` title + `int` counts), define a private `TypedDict` (prefix `_`) in the DAL file. `dict[str, int | str]` is too broad — ty flags callers that expect a specific type per key
- `ImageHandler` enum - use `str(handler)` when passing to functions expecting `str` type
- Pydantic objects (e.g., `Label`) - use `model_dump(mode="json")` to convert to dict for database storage
- Optional asyncapi booleans - add `or False`/`or True` when passing to functions expecting non-optional `bool`
- When AsyncAPI fields become required with defaults (e.g., `Field(default=False)`), remove the fallback pattern

### AsyncAPI WebSocket Protocol
- Union types `ClientMessage` and `ServerMessage` defined in `protocol.py`
- 50+ auto-generated message types in `asyncapi/`
- Two-phase upload process: creation phase (slices via `UPLOAD_SLICE`) → subscription phase (`SUBSCRIBE_BATCH`)
- `UploadSliceAck` provides immediate item status updates to client

## AsyncAPI Schema Updates

Backend models are auto-generated from `../frontend/asyncapi.json`. When updating schema:

1. Update `../frontend/asyncapi.json` with schema changes
2. Run `cd ../frontend && bun generate` from frontend directory
   - Generates Python models to `src/curator/asyncapi/`
   - Auto-formats generated code
3. Update all code that constructs or accesses the modified models
4. Run tests: `poetry run pytest -q`

**Design Patterns:**
- Group related fields into nested objects (e.g., `MediaImage.urls`, `MediaImage.camera`)
- Use short names without redundant prefixes (e.g., `original` not `url_original`)
- Boolean flags should be required with defaults, not Optional
- Required boolean fields generate as `Field(default=False)` in Python models

**When adding new server messages, update all 4 locations in `asyncapi.json` (alphabetical order):**
1. `components/messages/` - Message definition (`"RetryUploadsResponse": {"payload": {...}}`)
2. `components/schemas/` - Schema definition with type, data, nonce properties
3. `channels/wsChannel/messages/` - Channel message reference
4. `operations/ServerMessage/messages/` - Server operation reference (alphabetical order)

## Database Migrations

Use Alembic CLI auto-generator:
```bash
poetry run alembic revision --autogenerate -m "description"
poetry run alembic upgrade head
```

When dropping a column that has both a foreign key and an index, the autogenerated migration drops the index first — MySQL requires the FK to be dropped first. Always verify the order: `drop_constraint` (FK) → `drop_index` → `drop_column`.

## Testing

- `pytest` with tests in `tests/`
- All imports must be at the top of test files (no inline imports)
- Use `patch()` from `unittest.mock`, not `pytest.mock.patch`
- NO nested function definitions in tests - avoid `def func(): def inner():` pattern
- For complex mock behavior, use module-level helper functions (prefix with `_`) passed to `side_effect`
- BDD tests in `tests/bdd/`, async tests with pytest-asyncio
- pytest timeout is configured to `0.25` seconds in `pytest.ini`
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

**When adding new async send methods to `protocol.py`:**
- Add `sender.send_new_method = AsyncMock()` to `mock_sender` fixture in `tests/fixtures.py`
- This is required for tests that use WebSocket handlers (mock_sender is autouse for BDD tests)

### Test Fixture Issues

The `tests/fixtures.py` file contains an autouse fixture `mock_external_calls` that patches many external dependencies. This fixture is designed for BDD tests but can cause issues with other tests. If tests fail with strange errors:

- Check if the test needs to be isolated from the autouse fixture
- The fixture patches `curator.app.handler.encrypt_access_token` and other common dependencies
- Some tests may need to run without this fixture or use `@pytest.mark.usefixtures("mock_external_calls")` explicitly
- The fixture skips for modules with "mediawiki", "geocoding", or "test_download" in the name, avoiding a slow Celery import chain that causes timeouts. New test files that don't need BDD mocks should be added to this skip list in `fixtures.py`.

### BDD Testing Patterns (pytest-bdd)

- Use `@given(..., target_fixture="fixture_name")` to make fixture values available to other steps
- Use `global` variables to track state across BDD step definitions (e.g., `_use_default_mock` flag)
- Mock `time.sleep` in tests involving retry logic to avoid pytest-timeout (default 0.25s)
- Use `@when(..., target_fixture="result")` to make return values available to `@then` steps
- Handle expected exceptions in `@when` steps, return them in result dict for `@then` verification

### TDD Red Phase — Patching Non-Existent Imports

When writing a failing test before the implementation exists, `mocker.patch("module.symbol")` raises `AttributeError` if the symbol doesn't exist yet. Use `create=True` to allow patching symbols that don't exist in the target module:

```python
mocker.patch("curator.core.handler.get_redlinks", return_value=[...], create=True)
```

This lets the test fail for the right reason (missing method on Handler) rather than a patching error.

### Mock Patterns for Instance Methods

- When patching instance methods, use `side_effect` with functions accepting `*args, **kwargs`
- This avoids "got multiple values for argument" errors when method is called with keyword arguments
- Example: `mocker.patch("path.to.Class.method", side_effect=lambda *args, **kwargs: {...})`

### Testing Celery Bound Tasks

- `@app.task(bind=True)` with `autoretry_for` stores the pre-autoretry function as `task._orig_run` (a bound method)
- To call with a mock `self`: `process_upload._orig_run.__func__(mock_self, upload_id, edit_group_id)` — `__func__` gives the unbound function
- Calling `process_upload(mock_self, ...)` or `process_upload._orig_run(mock_self, ...)` both fail: the former because Celery's task machinery conflicts with keyword args, the latter because `_orig_run` is already bound to the task instance
- When using `MagicMock()` as task `self`, set integer attributes explicitly: `mock_self.max_retries = 3` — MagicMock attributes default to MagicMock instances, causing `TypeError` on numeric comparisons

### pytest-timeout Quirks

- pytest-timeout may enforce 0.25s default even with `timeout = 0` in pytest.ini
- Tests with `time.sleep()` must mock `time` module to avoid timeouts: `mocker.patch("time.sleep")`

### Asserting Eager Loading in DAL Tests

To verify `selectinload` is applied to a query, inspect `_with_options` on the captured query:
`option_keys = [opt.path.path[1].key for opt in query._with_options]` — `path[0]` is the Mapper, `path[1]` is the RelationshipProperty (has `.key`).

### selectinload and SQLModel Relationship Attributes

Passing `Model.relationship` directly to `selectinload` causes a ty type error — the attribute resolves as the related model type, not `QueryableAttribute`. Use `class_mapper` instead: `class_mapper(Model).relationships["name"].class_attribute`.

## Pull Request Conventions
- Phabricator tasks must be linked by full URL in PR descriptions: `https://phabricator.wikimedia.org/T123456`

## Pull Request Review Workflow
- Use `gh api repos/{owner}/{repo}/pulls/{number}/comments` to get line-by-line review comments with file paths and line numbers
- `gh pr view --json reviews` only shows high-level review summaries, not specific line comments

## Common Pitfalls and Troubleshooting

### Important Notes

- Functions that always return or raise an exception use `raise AssertionError("Unreachable")` to satisfy the type checker
- AsyncAPI models are auto-generated from `frontend/asyncapi.json`
- Large file uploads use `NamedTemporaryFile()` with streaming downloads (see `commons.py`)
- Database sessions use the `get_session()` dependency
- Code follows the layered architecture: routes → handlers → DAL → models

### Circular Imports

When adding imports between core modules (`commons.py`, `mediawiki_client.py`, etc.), be aware of circular dependencies:

- `commons.py` imports from `mediawiki_client.py`
- `mediawiki_client.py` should NOT import from `commons.py` directly
- For shared exceptions like `DuplicateUploadError`, use a dedicated `errors.py` module that only imports from `asyncapi` (which has no dependencies on other app modules)
- Import exceptions inside functions if needed to avoid circular imports: `from curator.app.errors import DuplicateUploadError`

### FastAPI List Query Parameters
- `list[str] | None = None` without `Query()` always resolves to `None` — repeated URL params like `?status=queued&status=failed` are silently ignored
- Use `Query(default=None)` for any list-typed query parameter: `status: list[str] | None = Query(default=None)`
- Tests that call endpoint functions directly bypass HTTP query string parsing, so list param issues won't be caught — use `TestClient` to verify HTTP-level behavior

### SQLModel vs SQLAlchemy Behavior
- `session.exec(select(col(Table.column))).all()` returns `list[value]`, not `list[Row]` (SQLModel-specific)
- Use `session.exec()` for all queries; `session.execute()` is deprecated in SQLModel
- Multi-column queries (e.g. GROUP BY with `sa_select`): `session.exec()` returns rows that unpack as tuples — `bid, count = row`
- `sa_select(...)` (raw SQLAlchemy multi-column select) doesn't match SQLModel's `session.exec()` overloads — use `# type: ignore` on those lines (known SQLModel limitation: fastapi/sqlmodel#909)

### ty Type Checker Quirks
- `# type: ignore[error-code]` does NOT suppress errors — ty only honors bare `# type: ignore`
- When a DAL function calls `session.exec()` multiple times, tests must use `mock_session.exec.side_effect = [result1, result2]` — a single `return_value` only handles one call

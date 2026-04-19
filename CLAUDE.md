# CLAUDE.md

Generic coding standards apply across all projects.

## Project Overview

Curator Backend = FastAPI service managing CuratorBot jobs for uploading media to Wikimedia Commons. Provides REST API + WebSocket endpoint for frontend; Celery workers handle background upload tasks.

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
After backend tasks, run in order:
```bash
poetry run isort . && poetry run ruff format && poetry run ruff check && poetry run pytest -q && poetry run ty check
```
Type-check specific files: `poetry run ty check path/to/file.py`

## Architecture

### Layered Architecture
```
main.py (Routes) → handler.py (Business Logic) → dal.py (Database) → models.py (SQLModel)
```

1. **Routes** (`main.py`) → validate request, get user session
2. **Handlers** (`handler*.py`) → business logic, orchestration
3. **DAL** (`dal.py`) → database queries and persistence
4. **Models** (`models.py`) → SQLModel definitions

DB access via DAL functions using `get_session()` dependency.

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
│   ├── errors.py        # DuplicateUploadError, HashLockError, StorageError, SourceCdnError
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
Abstract `Handler` class in `handlers/interfaces.py` defines contract for image sources:
- `fetch_collection()` - Get all images from collection
- `fetch_image_metadata()` - Get single image metadata
- `fetch_existing_pages()` - Check which images exist on Commons
- `fetch_collection_ids()` - Get all image IDs in collection
- `fetch_images_batch()` - Batch fetch images by ID

Implementations: `MapillaryHandler`, `FlickrHandler`. Used by WebSocket handler + ingestion worker.

### Startup Recovery
`recovery.py` handles uploads stuck in `queued` state after Redis restart. Uses sentinel key (`curator:started`) written to Redis on successful startup — missing key means Redis restarted, recovery needed. On recovery, queued uploads grouped by `(userid, edit_group_id)`, OAuth token validated against MediaWiki, then re-enqueued via `enqueue_uploads()`. Invalid tokens mark group uploads as failed with session-expired message in single DB call. Called from `main.py` lifespan after Alembic migrations.
- Sentinel key set atomically via `redis_client.set(SENTINEL_KEY, "1", nx=True)` — `None` return means another instance claimed recovery, function returns immediately. Prevents double-enqueuing on concurrent startups.

### Retry Functionality

Retry lets users + admins retry failed uploads. Creates new `UploadRequest` objects (copies) in new batch rather than modifying originals. Preserves original failed uploads for history/audit.

- `dal.reset_failed_uploads_to_new_batch()` - User retry, creates copies in new batch
- `dal.retry_selected_uploads_to_new_batch()` - Admin retry, same pattern
- After enqueueing Celery tasks, `update_celery_task_id()` called to enable cancellation
- `admin_retry_uploads` in `admin.py` calls `process_upload.apply_async()` directly, bypassing `enqueue_uploads()` + rate limiting — admin retries not rate limited

### Redis Role
Redis = Celery **broker** (task queue) + **result backend**. Redis restart destroys in-flight task data — tasks in broker queue gone, DB retains `status="queued"` records. Startup recovery (`recovery.py`) reconciles this.

### Worker Requeue Pattern
`tasks.py` uses `_requeue_or_fail(self, upload_id, worker_id, DELAYS, exc)` to requeue or permanently fail on exhaustion. Each error type has own delay list: `STORAGE_ERROR_DELAYS = [300, 600, 900]`, `HASH_LOCK_DELAYS = [60, 60, 60]`, `SOURCE_CDN_DELAYS = [600]`. To add new requeue type: add constant, add `except NewError` handler in `process_one` (reset to `QUEUED`, re-raise), add matching handler in `process_upload` calling `_requeue_or_fail`.

### Rate Limiting
- Rate limits fetched from `action=query&meta=userinfo&uiprop=ratelimits|rights` via `MediaWikiClient.get_user_rate_limits()` returning `(ratelimits, rights)`
- Each upload costs 2 edit API calls (SDC apply + null edit), so edit limit halved before comparing against upload limit — more restrictive used
- Users with `noratelimit` right exempt, receive `_NO_RATE_LIMIT`; MediaWiki returns `"ratelimits": {}` for exempt users (sysops, bots) — expected, not error
- Redis tracks next available upload slot per user with key `ratelimit:{userid}:next_available`
- Rate limit keys have no TTL — stale past-timestamp values handled by `max(0.0, next_available - current_time)`, TTL would incorrectly reset slot for large batches
- All uploads go to `QUEUE_NORMAL`
- `get_user_groups()` in `recovery.py` used only to validate OAuth tokens on startup recovery — returned groups not used

### commons.py (Upload Workflow)
`commons.py` contains upload-to-Commons workflow (`upload_file_chunked`) + image download (`download_file`) fetching from external CDNs (e.g., Mapillary/Facebook). Both use `config.HTTP_RETRY_DELAYS` for escalating backoff but have separate retry loops — differ in error handling + response processing.
- `download_file` raises `SourceCdnError` (not `HTTPError`) when all retries exhausted on 5xx — triggers task-level requeue. 4xx errors raise `HTTPError` directly, treated as permanent failures.

### MediaWiki Client
- `MediaWikiClient` handles all Wikimedia Commons operations
- Instantiate directly: `MediaWikiClient(access_token=access_token)`
- `_api_request()` always retries with exponential backoff (3 attempts: 0s, 1s, 3s delays)
- `requests.exceptions.RequestException`, `badtoken` CSRF errors, + OAuth "Nonce already used" errors trigger retries; other exceptions propagate immediately
- API-level error responses (e.g. `{"error": {"code": "..."}}`) returned as-is — `_api_request` does not raise on them; callers must check for expected keys (e.g. `"query"`) before indexing
- Client instances passed where needed (no global state)
- Async methods used where available, or `asyncio.to_thread` for synchronous calls
- Clients closed after use (e.g., `try...finally`)
- `_client` = underlying `requests.Session` — close explicitly with `client._client.close()` in `finally` block for short-lived clients (not managed by context manager)
- **Category name normalization**: MediaWiki treats `_` + ` ` as equivalent in titles. Category names from API/frontend often have underscores, but wikitext always uses spaces (`[[Category:Foo bar]]` not `[[Category:Foo_bar]]`). Normalize with `source.replace("_", " ")` before regex-matching wikitext.
- **Fetching page wikitext for editing**: Use `action=query&prop=revisions&rvprop=content&rvslots=main&titles=<title>` — content at `pages[id].revisions[0].slots.main["*"]`
- `upload_file()` accepts `file_path: str` (not `file_content: bytes`) for memory efficiency
- `commons.py:upload_file_chunked()` = complete upload workflow (download, hash, duplicate check, upload, SDC). `MediaWikiClient.upload_file()` = low-level chunked upload only.
- **Chunked upload flow**: Chunks uploaded with `stash=1`, then final commit publishes file
- **Per-chunk retryable errors**: substring match on `error.code` for `UploadStashFileException`, `uploadstash-exception` (bare variant from `handleStashException` default — also covers `UploadChunkFileException` fallthrough), `UploadChunkFileException`, `JobQueueError`, `internal_api_error_` (prefix, covers `DBQueryError` + similar transient MW DB errors); also matches `backend-fail-internal` in `error.info` (handles `stashfailed` with Swift storage errors) — transient infra errors, retry up to 4 attempts with 3/5/10s delays
- **Final commit retryable errors** (substring match on `error.code`): `backend-fail-internal`, `JobQueueError`, `internal_api_error_` (prefix) — retried with same 4-attempt / 3/5/10s logic. Final commit has own separate retry loop in `upload_file()`.
- **`uploadstash-file-not-found`, `uploadstash-bad-path`, `stashfailed` (with "No chunked upload session with this key") NOT retried inside `_upload_chunk`** — all mean stash gone, retrying same chunk useless. Surface as `UploadResult(success=False)`; `_upload_with_retry` in `ingest.py` restarts full upload from scratch (re-download + re-upload all chunks). `MAX_UPLOADSTASH_TRIES` controls full-restart attempt count. All three detected by `_is_uploadstash_gone_error`.
- **`stashfailed: Chunked upload is already completed`** handled in `upload_file()` (not `_upload_chunk`) — when chunk retry gets this error + valid `file_key` exists, chunk loop breaks, proceeds to final commit; stash was already complete despite transient error on prior attempt
- **Chunk `UploadResult.error` format**: always `f"{error_code}: {error_info}"` — omitting error code means code paths checking specific error code strings (e.g. `_is_uploadstash_gone_error`) silently fail to match.
- **Duplicate detection**: `warnings.duplicate` + `warnings.exists` handled during stash phase (chunk responses with `stash=1`). `warnings.exists` (same filename, content may differ) fetches remote SHA1, raises `DuplicateUploadError` only if hashes match; if SHA1 differs, returns `UploadResult(success=False)` with `"File already exists with different content: <title>"` — NOT `DuplicateUploadError`, naming conflict not true duplicate. Final commit can also return `Warning` — `warnings.nochange` (content identical, confirmed by MediaWiki) raises `DuplicateUploadError` using `warnings.exists` title if present. `upload_file()` accepts `file_sha1` for exists comparison; `upload_file_chunked()` in `commons.py` passes hash computed during download.
- Fetching SDC by title uses `sites=commonswiki&titles=File:Example.jpg` not `ids=M12345` — avoids extra API call to fetch page ID
- With `sites`/`titles` in wbgetentities, entity keyed by entity ID, not title — extract with `next(iter(entities))`
- Entity ID "-1" with site/title keys = non-existent file (raises error); positive entity ID with "missing" key = file exists but no SDC (returns None)
- `commons.py:upload_file_chunked` acquires Redis hash lock (keyed by file hash) after duplicate check; always released in `try/finally` — TTL is safety net, not primary release
- `upload_file` in `mediawiki_client.py`: all result processing (`if "upload" in data`, error logging) lives inside `if file_key:` block — `data` only assigned there

### SDC Key Mapping Pattern
- Auto-generated AsyncAPI models use kebab-case aliases (e.g., `entity-type`, `numeric-id`)
- DAL's `_fix_sdc_keys()` recursively maps snake_case to kebab-case for DB storage
- Mapping defined in `dal.py`, updated when AsyncAPI schema changes

### Commons Replica Database

`db/commons_engine.py` = read-only connection to Wikimedia Commons replica DB, available from Toolforge. Uses same `TOOL_TOOLSDB_USER`/`TOOL_TOOLSDB_PASSWORD` credentials as app DB, but connects to `commonswiki.analytics.db.svc.wikimedia.cloud` / `commonswiki_p`. Falls back to `COMMONS_DB_URL` env var for local dev.

**Local development:** When `TOOL_TOOLSDB_USER` absent, engine auto-starts SSH tunnel through `login.toolforge.org` (override with `TOOLFORGE_SSH_HOST` env var) on first request. Credentials read from Toolforge bastion via `ssh login.toolforge.org cat ~/replica.my.cnf` — no local `.cnf` needed. Tunnel uses `start_new_session=True` so it survives poetry file-watch restarts. PyMySQL reads `.cnf` files natively via `connect_args={"read_default_file": path}` — no manual parsing needed.

Replica schema uses `linktarget` as normalised title store — `cl_to`, `pl_title`, `tl_title` columns removed in MediaWiki 1.43–1.45, replaced with `cl_target_id`/`pl_target_id`/`tl_target_id` foreign keys to `linktarget(lt_id, lt_namespace, lt_title)`.

**Commons replica query patterns (benchmarked against live replica):**

- `NOT EXISTS` subqueries catastrophically slow on large tables like `categorylinks` (~4.5 min for 100 rows) — optimizer cannot short-circuit. Always use `LEFT JOIN ... WHERE p_target.page_id IS NULL` instead.
- `EXPLAIN` unavailable on replica (insufficient privileges) — benchmark with `time sql commonswiki`.
- `categorylinks` has no `cl_to` column (removed in 1.43–1.45) — join via `cl_target_id` → `linktarget(lt_id, lt_namespace, lt_title)`.
- For categorylinks-based wanted-categories queries (discarded), filtering `p_from.page_namespace IN (0, 6, 14)` halves query time (3.7s → 1.7s). Not applicable to accepted `category` table query (no `p_from`).
- `DISTINCT` with `LIMIT` does not allow early termination — DB must find all distinct rows before applying limit. Avoid `DISTINCT` on high-cardinality scans; use narrow filters to reduce working set.

**`category` table for wanted-categories counts:**

`category` table stores pre-computed per-category statistics maintained by MediaWiki in real time — including categories without a page. Columns: `cat_title`, `cat_pages` (total members), `cat_subcats`, `cat_files`. Use `cat_pages - cat_subcats - cat_files` for regular pages (galleries/templates). How `SpecialWantedCategories.php` fetches live counts in `preprocessResults()`.

Query: `SELECT c.cat_title, c.cat_subcats, c.cat_files, (c.cat_pages - c.cat_subcats - c.cat_files) AS pages, c.cat_pages AS total FROM category c LEFT JOIN page p ON p.page_namespace = 14 AND p.page_title = c.cat_title WHERE p.page_id IS NULL ORDER BY c.cat_pages DESC LIMIT 100`

Performance findings:
- `querypage=WantedCategories` MediaWiki API disabled on Commons — cannot use pre-computed cache via API.
- No index on `cat_pages` — `ORDER BY cat_pages DESC` always requires full table sort (~7–16s).
- Threshold filters (`cat_pages >= N`) don't help — full scan cost fixed regardless.
- Removing `ORDER BY` brings LIMIT 20 to 0.22s but results unsorted + full-scan cost returns with larger LIMITs.
- Multiple-query approach ruled out: top 10,000 categories by `cat_pages` contain only 1 missing — missing categories NOT correlated with largest categories, no indexed shortcut.
- GROUP BY aggregation directly on `categorylinks` takes several minutes — do not use.
- **Accepted approach**: run ~7s query directly (admin-only, infrequent use, loading state shown). Redis caching with Celery periodic task = known improvement path if latency becomes problem.

**DuckDB text filter pattern:** To add case-insensitive text search alongside exclusion conditions in `wanted_categories_cache.py`, append `lower(title) LIKE '%{filter_text.lower()}%'` to `conditions` list before building `WHERE` clause. Use `filter_text.lower()` to normalize input.

**`filter` field naming:** AsyncAPI may generate Python model field named `filter` (Python built-in). Use `filter_text` as parameter name in cache/handler functions to avoid shadowing built-in.

**`test_wanted_categories_cache.py` import pattern:** Cache tests import module functions *inside* `with patch("curator.db.wanted_categories_cache._get_duck_conn", ...)` blocks so mock active on call. New tests must follow same inline-import pattern.

**DuckDB concurrency pattern:** `_duck_conn` opens in write mode (not `read_only=True`) so reads + writes share one connection. `threading.Lock` (`_duck_lock`) serialises all access — DuckDB connections not thread-safe, `asyncio.gather` runs `count`/`query` concurrently in threads. Write mutations (e.g., `mark_created`) acquire `_duck_lock`, use `_get_duck_conn()` directly. Tests mock `_get_duck_conn` (not `duckdb.connect`) for both read + write operations.

**Title format in wanted categories:** DuckDB stores `cat_title` with underscores (`March_1924_in_Boston`). Backend sends titles as-is — no `replace("_", " ")`. Display transformation (`replaceAll('_', ' ')`) in Vue template only. Exception: `CATEGORY_CREATED_RESPONSE` title comes from MediaWiki API with spaces — normalize to underscores in handler before sending (`created_title.replace(" ", "_")`).

### Database Query Performance
**Search indexed columns only** — when implementing text search/filter, only include columns with DB indexes. Unindexed columns (especially JSONB fields) very slow on large datasets. Check model definitions for `index=True` before adding search.

### Type Conversion Patterns
- **TypedDict for query return types** — when query returns rows with mixed key types (e.g., `str` title + `int` counts), define private `TypedDict` (prefix `_`) in DAL file. `dict[str, int | str]` too broad — ty flags callers expecting specific type per key
- `ImageHandler` enum - use `handler.value` when passing to functions expecting `str` (`str(handler)` returns `'ImageHandler.MAPILLARY'`, not value)
- Pydantic objects (e.g., `Label`) - use `model_dump(mode="json")` to convert to dict for DB storage
- Optional asyncapi booleans - add `or False`/`or True` when passing to functions expecting non-optional `bool`
- When AsyncAPI fields become required with defaults (e.g., `Field(default=False)`), remove fallback pattern

### AsyncAPI WebSocket Protocol
- Union types `ClientMessage` + `ServerMessage` defined in `protocol.py`
- Background streaming tasks sending on closing WebSocket receive `AssertionError` (from `websockets.legacy.protocol._drain_helper`), not `WebSocketDisconnect` — detect clean shutdown via `socket.client_state == WebSocketState.DISCONNECTED` (import from `starlette.websockets`)
- 50+ auto-generated message types in `asyncapi/`
- Two-phase upload: creation phase (slices via `UPLOAD_SLICE`) → subscription phase (`SUBSCRIBE_BATCH`)
- `UploadSliceAck` provides immediate item status updates to client

## AsyncAPI Schema Updates

Backend models auto-generated from `../frontend/asyncapi.json`. When updating schema:

1. Update `../frontend/asyncapi.json` with schema changes
2. Run `cd ../frontend && bun generate` from frontend directory
   - Generates Python models to `src/curator/asyncapi/`
   - Auto-formats generated code
3. Update all code constructing or accessing modified models
4. Run tests: `poetry run pytest -q`

**Design Patterns:**
- Group related fields into nested objects (e.g., `MediaImage.urls`, `MediaImage.camera`)
- Use short names without redundant prefixes (e.g., `original` not `url_original`)
- Boolean flags required with defaults, not Optional
- Required boolean fields generate as `Field(default=False)` in Python models
- Use `$ref: "#/components/schemas/ImageHandler"` (not `type: string`) for enum fields — produces typed `ImageHandler` enum in both Python + TypeScript

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

When dropping column with both FK + index, autogenerated migration drops index first — MySQL requires FK dropped first. Verify order: `drop_constraint` (FK) → `drop_index` → `drop_column`.

## Testing

- `pytest` with tests in `tests/`
- All imports at top of test files (no inline imports)
- Use `patch()` from `unittest.mock`, not `pytest.mock.patch`
- NO nested function definitions in tests — avoid `def func(): def inner():` pattern
- For complex mock behavior, use module-level helper functions (prefix `_`) passed to `side_effect`; for stateful mocks (e.g. call-count tracking), pass mutable dict via `functools.partial(helper, state_dict)`
- BDD tests in `tests/bdd/`, async tests with pytest-asyncio
- pytest timeout configured to `0.25` seconds in `pytest.ini`
- Mock objects match actual return type structure (e.g., `UploadRequest` needs `id`, `key`, `status` attributes)
- When mocking `process_upload.apply_async()`, queue checked via `call[1]["queue"]`, args via `call[1]["args"]`
- AsyncMock assertions use `assert_called_once_with()` for keyword arguments

### Writing Tests with Patches

When mocking file operations or other builtins, use single `with` statement with comma-separated patches:

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
- Required for tests using WebSocket handlers (mock_sender is autouse for BDD tests)

### Test Fixture Issues

`tests/fixtures.py` contains autouse fixture `mock_external_calls` patching many external dependencies. Designed for BDD tests, can cause issues elsewhere. If tests fail with strange errors:

- Check if test needs isolation from autouse fixture
- Fixture patches `curator.app.handler.encrypt_access_token` + other common dependencies
- Some tests may need to run without fixture or use `@pytest.mark.usefixtures("mock_external_calls")` explicitly
- Fixture skips for modules with "mediawiki", "geocoding", or "test_download" in name — avoids slow Celery import chain causing timeouts. New test files not needing BDD mocks should be added to skip list in `fixtures.py`.

### BDD Testing Patterns (pytest-bdd)

- Use `@given(..., target_fixture="fixture_name")` to make fixture values available to other steps
- Use `global` variables to track state across BDD step definitions (e.g., `_use_default_mock` flag)
- Mock `time.sleep` in tests involving retry logic to avoid pytest-timeout (default 0.25s)
- Use `@when(..., target_fixture="result")` to make return values available to `@then` steps
- Handle expected exceptions in `@when` steps, return in result dict for `@then` verification

### TDD Red Phase — Patching Non-Existent Imports

When writing failing test before implementation exists, `mocker.patch("module.symbol")` raises `AttributeError` if symbol doesn't exist. Use `create=True` to patch non-existent symbols:

```python
mocker.patch("curator.core.handler.get_redlinks", return_value=[...], create=True)
```

Test fails for right reason (missing method on Handler), not patching error.

### Mock Patterns for Instance Methods

- When patching instance methods, use `side_effect` with functions accepting `*args, **kwargs`
- Avoids "got multiple values for argument" errors when method called with keyword arguments
- Example: `mocker.patch("path.to.Class.method", side_effect=lambda *args, **kwargs: {...})`

### Testing Celery Bound Tasks

- `@app.task(bind=True)` with `autoretry_for` stores pre-autoretry function as `task._orig_run` (bound method)
- To call with mock `self`: `process_upload._orig_run.__func__(mock_self, upload_id, edit_group_id)` — `__func__` gives unbound function
- Calling `process_upload(mock_self, ...)` or `process_upload._orig_run(mock_self, ...)` both fail: former because Celery task machinery conflicts with keyword args, latter because `_orig_run` already bound to task instance
- When using `MagicMock()` as task `self`, set integer attributes explicitly: `mock_self.max_retries = 3` — MagicMock attributes default to MagicMock instances, causing `TypeError` on numeric comparisons

### pytest-timeout Quirks

- pytest-timeout may enforce 0.25s default even with `timeout = 0` in pytest.ini
- Tests with `time.sleep()` must mock `time` module: `mocker.patch("time.sleep")`

### Asserting Eager Loading in DAL Tests

To verify `selectinload` applied to query, inspect `_with_options` on captured query:
`option_keys = [opt.path.path[1].key for opt in query._with_options]` — `path[0]` is Mapper, `path[1]` is RelationshipProperty (has `.key`).

### selectinload and SQLModel Relationship Attributes

Passing `Model.relationship` directly to `selectinload` causes ty type error — attribute resolves as related model type, not `QueryableAttribute`. Use `class_mapper` instead: `class_mapper(Model).relationships["name"].class_attribute`.

## Pull Request Conventions
- Phabricator tasks linked by full URL in PR descriptions: `https://phabricator.wikimedia.org/T123456`

## Pull Request Review Workflow
- Use `gh api repos/{owner}/{repo}/pulls/{number}/comments` to get line-by-line review comments with file paths + line numbers
- `gh pr view --json reviews` shows high-level review summaries only, not specific line comments

## Common Pitfalls and Troubleshooting

### Important Notes

- Functions always returning or raising use `raise AssertionError("Unreachable")` to satisfy type checker
- AsyncAPI models auto-generated from `frontend/asyncapi.json`
- Large file uploads use `NamedTemporaryFile()` with streaming downloads (see `commons.py`)
- DB sessions use `get_session()` dependency
- Code follows layered architecture: routes → handlers → DAL → models

### Circular Imports

When adding imports between core modules (`commons.py`, `mediawiki_client.py`, etc.), watch for circular dependencies:

- `commons.py` imports from `mediawiki_client.py`
- `mediawiki_client.py` should NOT import from `commons.py` directly
- For shared exceptions like `DuplicateUploadError`, use dedicated `errors.py` module that only imports from `asyncapi` (no dependencies on other app modules)
- Import exceptions inside functions if needed to avoid circular imports: `from curator.app.errors import DuplicateUploadError`

### FastAPI List Query Parameters
- `list[str] | None = None` without `Query()` always resolves to `None` — repeated URL params like `?status=queued&status=failed` silently ignored
- Use `Query(default=None)` for any list-typed query parameter: `status: list[str] | None = Query(default=None)`
- Tests calling endpoint functions directly bypass HTTP query string parsing — use `TestClient` to verify HTTP-level behavior

### SQLModel vs SQLAlchemy Behavior
- `session.exec(select(col(Table.column))).all()` returns `list[value]`, not `list[Row]` (SQLModel-specific)
- Use `session.exec()` for all queries; `session.execute()` deprecated in SQLModel
- Multi-column queries (e.g. GROUP BY with `sa_select`): `session.exec()` returns rows unpacking as tuples — `bid, count = row`
- `sa_select(...)` (raw SQLAlchemy multi-column select) doesn't match SQLModel's `session.exec()` overloads — use `# type: ignore` on those lines (known SQLModel limitation: fastapi/sqlmodel#909)

### ty Type Checker Quirks
- `# type: ignore[error-code]` does NOT suppress errors — ty only honors bare `# type: ignore`
- When DAL function calls `session.exec()` multiple times, tests must use `mock_session.exec.side_effect = [result1, result2]` — single `return_value` handles only one call
# CLAUDE.md

Generic coding standards apply across all projects.

## Project Overview

Curator Backend = FastAPI service managing CuratorBot jobs for uploading media to Wikimedia Commons. REST API + WebSocket endpoint for frontend; Celery workers handle background upload tasks.

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

Layered: `main.py (Routes) → handler*.py (Business Logic) → dal.py (Database) → models.py (SQLModel)`

DB access via DAL functions using `get_session()` dependency.

## Project-Specific Patterns

### Startup Recovery
`recovery.py` handles uploads stuck in `queued` state after Redis restart. Uses sentinel key (`curator:started`) — missing means Redis restarted. Queued uploads grouped by `(userid, edit_group_id)`, OAuth token validated, then re-enqueued via `enqueue_uploads()`. Invalid tokens mark group uploads failed with session-expired message in single DB call. Called from `main.py` lifespan after Alembic migrations.
- Sentinel set atomically via `redis_client.set(SENTINEL_KEY, "1", nx=True)` — `None` return means another instance claimed recovery, return immediately. Prevents double-enqueuing on concurrent startups.

### Retry Functionality

Retry lets users + admins retry failed uploads. Creates new `UploadRequest` copies in new batch rather than modifying originals. Preserves original failed uploads for history/audit.

- `dal.reset_failed_uploads_to_new_batch()` — user retry
- `dal.retry_selected_uploads_to_new_batch()` — admin retry
- After enqueueing, `update_celery_task_id()` called to enable cancellation
- `admin_retry_uploads` in `admin.py` calls `process_upload.apply_async()` directly, bypassing `enqueue_uploads()` + rate limiting — admin retries not rate limited

### Redis Role
Redis = Celery **broker** + **result backend**. Redis restart destroys in-flight tasks — DB retains `status="queued"` records. Startup recovery (`recovery.py`) reconciles this.

### Worker Requeue Pattern
`tasks.py` uses `_requeue_or_fail(self, upload_id, worker_id, DELAYS, exc)`. Delay lists: `STORAGE_ERROR_DELAYS = [300, 600, 900]`, `HASH_LOCK_DELAYS = [60, 60, 60]`, `SOURCE_CDN_DELAYS = [600]`. To add new requeue type: add constant, add `except NewError` handler in `process_one` (reset to `QUEUED`, re-raise), add matching handler in `process_upload` calling `_requeue_or_fail`.

### Rate Limiting
- Rate limits fetched from `action=query&meta=userinfo&uiprop=ratelimits|rights` via `MediaWikiClient.get_user_rate_limits()` returning `(ratelimits, rights)`
- Each upload costs 2 edit API calls (SDC apply + null edit), so edit limit halved before comparing against upload limit — more restrictive used
- Users with `noratelimit` right exempt, receive `_NO_RATE_LIMIT`; MediaWiki returns `"ratelimits": {}` for exempt users (sysops, bots) — expected, not error
- Redis tracks next available slot per user: `ratelimit:{userid}:next_available`
- Rate limit keys have no TTL — stale past-timestamp values handled by `max(0.0, next_available - current_time)`, TTL would incorrectly reset slot for large batches
- `get_user_groups()` in `recovery.py` used only to validate OAuth tokens on startup recovery — returned groups not used

### commons.py (Upload Workflow)
`upload_file_chunked` = complete workflow (download, hash, duplicate check, upload, SDC). `download_file` fetches from external CDNs. Both use `config.HTTP_RETRY_DELAYS` but have separate retry loops — differ in error handling + response processing.
- `download_file` raises `SourceCdnError` (not `HTTPError`) when all retries exhausted on 5xx — triggers task-level requeue. 4xx errors raise `HTTPError` directly, permanent failures.

### MediaWiki Client
- `_api_request()` retries with exponential backoff (3 attempts: 0s, 1s, 3s delays)
- `requests.exceptions.RequestException`, `badtoken` CSRF errors, + OAuth "Nonce already used" errors trigger retries; other exceptions propagate immediately
- API-level error responses (e.g. `{"error": {"code": "..."}}`) returned as-is — `_api_request` does not raise on them; callers must check for expected keys (e.g. `"query"`) before indexing. Helpers called from inside `_api_request` (e.g. `get_csrf_token`) must raise `requests.exceptions.RequestException` on missing keys — `KeyError` propagates past the retry loop.
- `_client` = underlying `requests.Session` — close explicitly with `client._client.close()` in `finally` block for short-lived clients
- **Category name normalization**: MediaWiki treats `_` + ` ` as equivalent. Category names from API/frontend often have underscores, wikitext always uses spaces. Normalize with `source.replace("_", " ")` before regex-matching wikitext.
- **Fetching page wikitext**: `action=query&prop=revisions&rvprop=content&rvslots=main&titles=<title>` — content at `pages[id].revisions[0].slots.main["*"]`
- `upload_file()` accepts `file_path: str` (not `file_content: bytes`) for memory efficiency
- **Chunked upload flow**: chunks uploaded with `stash=1`, then final commit publishes file
- **Per-chunk retryable errors**: substring match on `error.code` for `UploadStashFileException`, `uploadstash-exception`, `UploadChunkFileException`, `JobQueueError`, `internal_api_error_` (prefix); also `backend-fail-internal` in `error.info` — retry up to 4 attempts with 3/5/10s delays
- **Final commit retryable errors**: `backend-fail-internal`, `JobQueueError`, `internal_api_error_` (prefix) — same 4-attempt / 3/5/10s logic. Final commit has own separate retry loop in `upload_file()`.
- **`uploadstash-file-not-found`, `uploadstash-bad-path`, `stashfailed` (with "No chunked upload session with this key") NOT retried inside `_upload_chunk`** — stash gone, retrying useless. Surface as `UploadResult(success=False)`; `_upload_with_retry` in `ingest.py` restarts full upload from scratch. `MAX_UPLOADSTASH_TRIES` controls restart count. All three detected by `_is_uploadstash_gone_error`.
- **`stashfailed: Chunked upload is already completed`** handled in `upload_file()` — when chunk retry gets this + valid `file_key` exists, break chunk loop and proceed to final commit
- **Chunk `UploadResult.error` format**: always `f"{error_code}: {error_info}"` — omitting error code means `_is_uploadstash_gone_error` checks silently fail to match
- **Duplicate detection**: `warnings.duplicate` + `warnings.exists` handled during stash phase. `warnings.exists` fetches remote SHA1, raises `DuplicateUploadError` only if hashes match; SHA1 differs → `UploadResult(success=False)` with `"File already exists with different content"`. `warnings.nochange` on final commit raises `DuplicateUploadError`.
- SDC by title: use `sites=commonswiki&titles=File:Example.jpg` not `ids=M12345`
- With `sites`/`titles` in wbgetentities, entity keyed by entity ID — extract with `next(iter(entities))`
- Entity ID "-1" = non-existent file (raise); positive ID with "missing" key = file exists but no SDC (return None)
- `upload_file_chunked` acquires Redis hash lock after duplicate check; released in `try/finally`
- All result processing in `upload_file()` lives inside `if file_key:` block

### SDC Key Mapping Pattern
- Auto-generated AsyncAPI models use kebab-case aliases (e.g., `entity-type`, `numeric-id`)
- DAL's `_fix_sdc_keys()` recursively maps snake_case to kebab-case for DB storage

### Commons Replica Database

`db/commons_engine.py` = read-only connection to Wikimedia Commons replica DB. Uses `TOOL_TOOLSDB_USER`/`TOOL_TOOLSDB_PASSWORD` credentials, connects to `commonswiki.analytics.db.svc.wikimedia.cloud` / `commonswiki_p`. Falls back to `COMMONS_DB_URL` env var for local dev.

**Local dev:** When `TOOL_TOOLSDB_USER` absent, auto-starts SSH tunnel through `login.toolforge.org`. Credentials read from bastion via `ssh login.toolforge.org cat ~/replica.my.cnf`. Tunnel uses `start_new_session=True` so it survives poetry file-watch restarts.

Replica schema: `cl_to`, `pl_title`, `tl_title` removed in MW 1.43–1.45, replaced with `cl_target_id`/`pl_target_id`/`tl_target_id` → `linktarget(lt_id, lt_namespace, lt_title)`.

**Commons replica query patterns (benchmarked against live replica):**

- `NOT EXISTS` catastrophically slow on large tables like `categorylinks` (~4.5 min for 100 rows). Use `LEFT JOIN ... WHERE p_target.page_id IS NULL` instead.
- `EXPLAIN` unavailable on replica — benchmark with `time sql commonswiki`.
- `categorylinks` has no `cl_to` — join via `cl_target_id` → `linktarget`.
- `DISTINCT` with `LIMIT` does not allow early termination. Avoid on high-cardinality scans.

**`category` table for wanted-categories counts:**

`category` table = pre-computed per-category stats. Use `cat_pages - cat_subcats - cat_files` for regular pages. Query:

`SELECT c.cat_title, c.cat_subcats, c.cat_files, (c.cat_pages - c.cat_subcats - c.cat_files) AS pages, c.cat_pages AS total FROM category c LEFT JOIN page p ON p.page_namespace = 14 AND p.page_title = c.cat_title WHERE p.page_id IS NULL ORDER BY c.cat_pages DESC LIMIT 100`

Performance:
- `querypage=WantedCategories` API disabled on Commons.
- No index on `cat_pages` — `ORDER BY cat_pages DESC` requires full table sort (~7–16s).
- Missing categories NOT correlated with largest categories — no indexed shortcut.
- **Accepted approach**: run ~7s query directly (admin-only, infrequent). Redis caching with Celery periodic task = known improvement path.

**DuckDB text filter:** Append `lower(title) LIKE '%{filter_text.lower()}%'` to `conditions` list. Use `filter_text` param name (not `filter` — shadows built-in).

**`test_wanted_categories_cache.py`:** Cache tests import module functions *inside* `with patch("curator.db.wanted_categories_cache._get_duck_conn", ...)` blocks. New tests must follow same inline-import pattern.

**DuckDB concurrency:** `_duck_conn` opens in write mode. `threading.Lock` (`_duck_lock`) serialises all access — DuckDB not thread-safe. Tests mock `_get_duck_conn` (not `duckdb.connect`) for both read + write.

**Title format in wanted categories:** DuckDB stores `cat_title` with underscores. Backend sends as-is. Display transformation in Vue template only. Exception: `CATEGORY_CREATED_RESPONSE` title from MediaWiki API uses spaces — normalize to underscores before sending (`created_title.replace(" ", "_")`).

### Database Query Performance
Search indexed columns only — unindexed columns (especially JSONB fields) very slow on large datasets. Check model definitions for `index=True`.

### Type Conversion Patterns
- **TypedDict for query return types** — define private `TypedDict` (prefix `_`) in DAL file when query returns mixed key types. `dict[str, int | str]` too broad.
- `ImageHandler` enum — use `handler.value` when passing to `str`-typed params (`str(handler)` returns `'ImageHandler.MAPILLARY'`)
- Pydantic objects — use `model_dump(mode="json")` to convert to dict for DB storage
- Optional asyncapi booleans — add `or False`/`or True` when passing to non-optional `bool` params

### AsyncAPI WebSocket Protocol
- Background streaming tasks sending on closing WebSocket receive `AssertionError` (from `websockets.legacy.protocol._drain_helper`), not `WebSocketDisconnect` — detect via `socket.client_state == WebSocketState.DISCONNECTED`
- Two-phase upload: creation phase (slices via `UPLOAD_SLICE`) → subscription phase (`SUBSCRIBE_BATCH`)

## AsyncAPI Schema Updates

Backend models auto-generated from `../frontend/asyncapi.json`. When updating schema:

1. Update `../frontend/asyncapi.json`
2. Run `cd ../frontend && bun generate`
3. Update all code constructing or accessing modified models
4. Run tests: `poetry run pytest -q`

**Design Patterns:**
- Group related fields into nested objects
- Boolean flags required with defaults, not Optional
- Required boolean fields generate as `Field(default=False)` in Python models
- Use `$ref: "#/components/schemas/ImageHandler"` (not `type: string`) for enum fields — produces typed `ImageHandler` enum in both Python + TypeScript

**When adding new server messages, update all 4 locations in `asyncapi.json` (alphabetical order):**
1. `components/messages/` — message definition
2. `components/schemas/` — schema with type, data, nonce properties
3. `channels/wsChannel/messages/` — channel message reference
4. `operations/ServerMessage/messages/` — server operation reference

## Database Migrations

```bash
poetry run alembic revision --autogenerate -m "description"
poetry run alembic upgrade head
```

When dropping column with both FK + index, autogenerated migration drops index first — MySQL requires FK dropped first. Verify order: `drop_constraint` (FK) → `drop_index` → `drop_column`.

## Testing

- Tests in `tests/`, BDD tests in `tests/bdd/`
- All imports at top of test files (no inline imports)
- Use `patch()` from `unittest.mock`, not `pytest.mock.patch`
- No nested function definitions in tests
- Complex mock behavior: module-level helper functions (prefix `_`) passed to `side_effect`; stateful mocks: `functools.partial(helper, state_dict)`
- pytest timeout: `0.25s` — mock `time.sleep` in any test using retry logic
- When mocking `process_upload.apply_async()`, queue via `call[1]["queue"]`, args via `call[1]["args"]`

### Writing Tests with Patches

Use single `with` statement with comma-separated patches:

```python
# Wrong
with patch("os.path.getsize", return_value=1000):
    with patch("builtins.open", mock_open(read_data=b"data")):
        result = func()

# Correct
with patch("os.path.getsize", return_value=1000), patch(
    "builtins.open", mock_open(read_data=b"data")
):
    result = func()
```

**When adding new async send methods to `protocol.py`:** add `sender.send_new_method = AsyncMock()` to `mock_sender` fixture in `tests/fixtures.py`.

### Test Fixture Issues

`tests/fixtures.py` autouse fixture `mock_external_calls` patches many external deps. Designed for BDD. If tests fail with strange errors, check if file needs adding to skip list in `fixtures.py` — fixture skips modules with "mediawiki", "geocoding", or "test_download" in name.

### BDD Testing Patterns (pytest-bdd)

- `@given(..., target_fixture="fixture_name")` to make fixture values available to other steps
- `@when(..., target_fixture="result")` to make return values available to `@then` steps
- `global` variables for state across BDD step definitions
- Handle expected exceptions in `@when` steps, return in result dict for `@then` verification

### TDD Red Phase — Patching Non-Existent Imports

`mocker.patch("module.symbol")` raises `AttributeError` if symbol doesn't exist. Use `create=True`:

```python
mocker.patch("curator.core.handler.get_redlinks", return_value=[...], create=True)
```

### Mock Patterns for Instance Methods

Patch instance methods with `side_effect=lambda *args, **kwargs: {...}` — avoids "got multiple values for argument" errors.

### Testing Celery Bound Tasks

- `@app.task(bind=True)` with `autoretry_for` stores pre-autoretry function as `task._orig_run`
- Call with mock `self`: `process_upload._orig_run.__func__(mock_self, upload_id, edit_group_id)`
- When using `MagicMock()` as task `self`, set integer attributes explicitly: `mock_self.max_retries = 3`

### Asserting Eager Loading in DAL Tests

Inspect `_with_options` on captured query: `option_keys = [opt.path.path[1].key for opt in query._with_options]`

### selectinload and SQLModel Relationship Attributes

Passing `Model.relationship` to `selectinload` causes ty error. Use `class_mapper` instead: `class_mapper(Model).relationships["name"].class_attribute`.

## Pull Request Conventions
- Phabricator tasks linked by full URL: `https://phabricator.wikimedia.org/T123456`
- Line-by-line review comments: `gh api repos/{owner}/{repo}/pulls/{number}/comments`

## Common Pitfalls

### Misc
- Functions always returning or raising: use `raise AssertionError("Unreachable")` to satisfy type checker
- AsyncAPI models auto-generated from `frontend/asyncapi.json` — do not edit directly

### Circular Imports
- `commons.py` imports from `mediawiki_client.py`; never reverse
- Shared exceptions go in `errors.py` (no deps on other app modules)

### FastAPI List Query Parameters
- `list[str] | None = None` without `Query()` always resolves to `None`
- Use `Query(default=None)`: `status: list[str] | None = Query(default=None)`
- Tests calling endpoint functions directly bypass HTTP parsing — use `TestClient` to verify

### SQLModel vs SQLAlchemy Behavior
- `session.exec(select(col(Table.column))).all()` returns `list[value]`, not `list[Row]`
- Use `session.exec()` for all queries; `session.execute()` deprecated in SQLModel
- `sa_select(...)` doesn't match SQLModel's `session.exec()` overloads — use `# type: ignore` on those lines
- When DAL calls `session.exec()` multiple times, tests must use `mock_session.exec.side_effect = [result1, result2]`

### ty Type Checker Quirks
- `# type: ignore[error-code]` does NOT suppress errors — ty only honors bare `# type: ignore`

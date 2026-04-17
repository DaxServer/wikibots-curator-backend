# Wanted Categories Server-Side Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add server-side pagination to the wanted categories WebSocket endpoint so the client can page through results using an offset, and the server returns the total row count for rendering a paginator.

**Architecture:** `FetchWantedCategories` gains a required `data.offset` field (integer, default 0). `WantedCategoriesResponseData` gains a `total` integer. The DuckDB cache gets a `count()` function and the `query()` function gains an `offset` parameter. The handler calls both, and the frontend composable stores `total` and passes `offset` per page.

**Tech Stack:** Python 3.13, FastAPI WebSocket, DuckDB, AsyncAPI/modelina code generation, Vue 3 + PrimeVue Paginator, Bun test

---

## File Map

| File | Change |
|------|--------|
| `frontend/asyncapi.json` | Add `FetchWantedCategoriesData` schema, update `FetchWantedCategories` to include `data`, add `total` to `WantedCategoriesResponseData` |
| `src/curator/asyncapi/FetchWantedCategories.py` | **Auto-generated** — gains `data: FetchWantedCategoriesData` |
| `src/curator/asyncapi/FetchWantedCategoriesData.py` | **Auto-generated** — new file with `offset: int = Field(default=0)` |
| `src/curator/asyncapi/WantedCategoriesResponseData.py` | **Auto-generated** — gains `total: int` |
| `src/curator/asyncapi/__init__.py` | **Auto-generated** — gains import for `FetchWantedCategoriesData` |
| `src/curator/db/wanted_categories_cache.py` | Add `count()` function; add `offset: int = 0` param to `query()` |
| `src/curator/core/handler.py` | `fetch_wanted_categories` accepts `offset`, calls `count()`, passes `total` in response |
| `src/curator/ws.py` | Pass `message.data.offset` to `handler.fetch_wanted_categories(offset)` |
| `tests/bdd/test_fetch_wanted_categories.py` | Update existing scenario to assert `total`; add offset scenario |
| `tests/bdd/features/fetch_wanted_categories.feature` | Add offset scenario |
| `frontend/src/composables/useWantedCategories.ts` | Add `total` ref, pass `offset` in request, store `total` from response |
| `frontend/src/composables/__tests__/useWantedCategories.test.ts` | Update existing tests; add offset + total tests |
| `frontend/src/components/views/WantedCategoriesView.vue` | Add `Paginator`, wire up page change to `fetchWantedCategories(offset)` |

---

## Task 1: Update AsyncAPI schema and regenerate models

**Files:**
- Modify: `frontend/asyncapi.json:2140-2215`

- [ ] **Step 1: Update `FetchWantedCategories` schema**

In `frontend/asyncapi.json`, replace lines 2140–2151:

```json
      "FetchWantedCategories": {
        "type": "object",
        "required": [
          "type",
          "data"
        ],
        "properties": {
          "type": {
            "const": "FETCH_WANTED_CATEGORIES"
          },
          "data": {
            "$ref": "#/components/schemas/FetchWantedCategoriesData"
          }
        },
        "additionalProperties": false
      },
      "FetchWantedCategoriesData": {
        "type": "object",
        "required": [
          "offset"
        ],
        "properties": {
          "offset": {
            "type": "integer",
            "default": 0
          }
        },
        "additionalProperties": false
      },
```

- [ ] **Step 2: Add `total` to `WantedCategoriesResponseData` schema**

In `frontend/asyncapi.json`, replace the `WantedCategoriesResponseData` schema (lines 2201–2215):

```json
      "WantedCategoriesResponseData": {
        "type": "object",
        "required": [
          "items",
          "total"
        ],
        "properties": {
          "items": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/WantedCategoryItem"
            }
          },
          "total": {
            "type": "integer"
          }
        },
        "additionalProperties": false
      }
```

- [ ] **Step 3: Regenerate Python and TypeScript models**

Run from repo root:
```bash
cd /Users/daxserver/projects/wikimedia/curator-app/frontend && bun generate
```

Expected: new file `src/curator/asyncapi/FetchWantedCategoriesData.py` created, `FetchWantedCategories.py` now has `data: FetchWantedCategoriesData`, `WantedCategoriesResponseData.py` now has `total: int`.

- [ ] **Step 4: Verify generated models compile**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/backend && poetry run ty check src/curator/asyncapi/
```

Expected: no errors.

---

## Task 2: Add `count()` and `offset` param to DuckDB cache (TDD)

**Files:**
- Modify: `src/curator/db/wanted_categories_cache.py`

- [ ] **Step 1: Write the failing tests**

Add to a new temporary test file `tests/test_wanted_categories_cache.py`:

```python
"""Unit tests for wanted_categories_cache."""

from unittest.mock import MagicMock, patch

import pytest


def _make_cursor(fetchone_value=None, fetchall_value=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_value
    cursor.fetchall.return_value = fetchall_value or []
    return cursor


def _make_conn(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def test_count_returns_total_rows():
    cursor = _make_cursor(fetchone_value=(42,))
    with patch("curator.db.wanted_categories_cache._get_duck_conn", return_value=_make_conn(cursor)):
        from curator.db.wanted_categories_cache import count
        result = count()
    assert result == 42
    sql = cursor.execute.call_args[0][0]
    assert "COUNT(*)" in sql
    assert "NOT contains" in sql


def test_query_passes_offset_to_sql():
    cursor = _make_cursor(fetchall_value=[])
    with patch("curator.db.wanted_categories_cache._get_duck_conn", return_value=_make_conn(cursor)):
        from curator.db.wanted_categories_cache import query
        query(offset=200)
    sql = cursor.execute.call_args[0][0]
    assert "OFFSET 200" in sql


def test_query_default_offset_is_zero():
    cursor = _make_cursor(fetchall_value=[])
    with patch("curator.db.wanted_categories_cache._get_duck_conn", return_value=_make_conn(cursor)):
        from curator.db.wanted_categories_cache import query
        query()
    sql = cursor.execute.call_args[0][0]
    assert "OFFSET 0" in sql
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/backend && poetry run pytest tests/test_wanted_categories_cache.py -v
```

Expected: 3 failures — `count` does not exist, `OFFSET` not in query SQL.

- [ ] **Step 3: Add `count()` and `offset` parameter to `wanted_categories_cache.py`**

In `src/curator/db/wanted_categories_cache.py`, add `count()` after line 121 (after `query()`):

```python
def count(
    excluded: set[str] = EXCLUDED_WANTED_CATEGORIES,
) -> int:
    """Return total wanted category rows after applying exclusion filter."""
    exclusions = " AND ".join(f"NOT contains(title, '{term}')" for term in excluded)
    where = f"WHERE {exclusions}" if exclusions else ""
    cursor = _get_duck_conn().cursor()
    row = cursor.execute(
        f"SELECT COUNT(*) FROM wanted_categories {where}"
    ).fetchone()
    cursor.close()
    return row[0] if row else 0
```

Update the signature of `query()` at line 102:

```python
def query(
    excluded: set[str] = EXCLUDED_WANTED_CATEGORIES,
    limit: int = _QUERY_LIMIT,
    offset: int = 0,
) -> list[WantedCategoryRow]:
```

Update the SQL inside `query()` to append `OFFSET {offset}`:

```python
    rows = cursor.execute(
        f"SELECT title, subcats, files, pages, total FROM wanted_categories {where} ORDER BY total DESC LIMIT {limit} OFFSET {offset}"
    ).fetchall()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/backend && poetry run pytest tests/test_wanted_categories_cache.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Export `count` in handler imports**

In `src/curator/core/handler.py` line 67–72, add `count` to the import:

```python
from curator.db.wanted_categories_cache import (
    EXCLUDED_WANTED_CATEGORIES,
    count,
    is_ready,
    populate_with_lock,
    query,
)
```

- [ ] **Step 6: Type-check and lint**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/backend && poetry run ty check src/curator/db/wanted_categories_cache.py src/curator/core/handler.py && poetry run ruff check src/curator/db/wanted_categories_cache.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

Use the gitbutler skill to commit with message: `feat: add count() and offset param to DuckDB wanted_categories_cache`

---

## Task 3: Update handler and ws.py (TDD)

**Files:**
- Modify: `src/curator/core/handler.py:686-713`
- Modify: `src/curator/ws.py:128-130`
- Modify: `tests/bdd/features/fetch_wanted_categories.feature`
- Modify: `tests/bdd/test_fetch_wanted_categories.py`

- [ ] **Step 1: Write failing BDD scenario asserting `total` in response**

Update `tests/bdd/features/fetch_wanted_categories.feature` to add `total` to the existing scenario and a new offset scenario:

```gherkin
Feature: Fetch Wanted Categories
  As a curator admin
  I want to fetch wanted categories from Wikimedia Commons
  So that I can identify missing category pages that are referenced but don't exist

  Scenario: Fetching wanted categories returns items and total from Commons replica
    Given I am a logged-in user with id "12345"
    When I fetch wanted categories at offset 0
    Then I should receive a wanted categories response with 2 items and total 50

  Scenario: Fetching wanted categories at an offset passes offset to the query
    Given I am a logged-in user with id "12345"
    When I fetch wanted categories at offset 100
    Then the DuckDB query should have been called with offset 100
```

- [ ] **Step 2: Update the BDD test file**

Replace `tests/bdd/test_fetch_wanted_categories.py` with:

```python
"""BDD tests for fetch_wanted_categories.feature"""

from unittest.mock import MagicMock

from mwoauth import AccessToken
from pytest_bdd import scenario, then, when

from curator.core.handler import Handler

from .conftest_steps import run_sync

_last_query_offset: int | None = None


@scenario(
    "features/fetch_wanted_categories.feature",
    "Fetching wanted categories returns items and total from Commons replica",
)
def test_fetch_wanted_categories():
    pass


@scenario(
    "features/fetch_wanted_categories.feature",
    "Fetching wanted categories at an offset passes offset to the query",
)
def test_fetch_wanted_categories_offset():
    pass


def _mock_query(*args, offset: int = 0, **kwargs):
    global _last_query_offset
    _last_query_offset = offset
    return [
        {"title": "Foo_in_Germany", "subcats": 1, "files": 121, "pages": 2, "total": 124},
        {"title": "Bar_in_Germany", "subcats": 0, "files": 5, "pages": 10, "total": 15},
    ]


@when("I fetch wanted categories at offset 0")
def when_fetch_wanted_categories_offset_0(mock_sender, event_loop, mocker):
    mocker.patch("curator.core.handler.is_ready", return_value=True)
    mocker.patch("curator.core.handler.query", side_effect=_mock_query)
    mocker.patch("curator.core.handler.count", return_value=50)
    h = Handler(
        {"username": "testuser", "userid": "12345", "access_token": AccessToken("v", "s")},
        mock_sender,
        MagicMock(),
    )
    run_sync(h.fetch_wanted_categories(0), event_loop)


@when("I fetch wanted categories at offset 100")
def when_fetch_wanted_categories_offset_100(mock_sender, event_loop, mocker):
    mocker.patch("curator.core.handler.is_ready", return_value=True)
    mocker.patch("curator.core.handler.query", side_effect=_mock_query)
    mocker.patch("curator.core.handler.count", return_value=50)
    h = Handler(
        {"username": "testuser", "userid": "12345", "access_token": AccessToken("v", "s")},
        mock_sender,
        MagicMock(),
    )
    run_sync(h.fetch_wanted_categories(100), event_loop)


@then("I should receive a wanted categories response with 2 items and total 50")
def then_wanted_categories_received(mock_sender):
    mock_sender.send_wanted_categories_response.assert_called_once()
    call_args = mock_sender.send_wanted_categories_response.call_args[0][0]
    assert len(call_args.items) == 2
    assert call_args.total == 50
    assert call_args.items[0].title == "Foo in Germany"
    assert call_args.items[0].subcats == 1
    assert call_args.items[0].files == 121
    assert call_args.items[0].pages == 2
    assert call_args.items[0].total == 124


@then("the DuckDB query should have been called with offset 100")
def then_query_called_with_offset(mock_sender):
    assert _last_query_offset == 100
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/backend && poetry run pytest tests/bdd/test_fetch_wanted_categories.py -v
```

Expected: failures — `fetch_wanted_categories` does not accept offset, `WantedCategoriesResponseData` has no `total`.

- [ ] **Step 4: Update `handler.py` — `fetch_wanted_categories` method**

Replace the `fetch_wanted_categories` method body at lines 686–713:

```python
    @handle_exceptions
    async def fetch_wanted_categories(self, offset: int = 0) -> None:
        """Fetch wanted categories from DuckDB cache or fall back to MySQL top-N query."""
        if await asyncio.to_thread(is_ready):
            total, rows = await asyncio.gather(
                asyncio.to_thread(count),
                asyncio.to_thread(query, offset=offset),
            )
        else:
            rows = await asyncio.to_thread(get_wanted_categories)
            asyncio.create_task(populate_with_lock())
            rows = [
                r
                for r in rows
                if not any(term in r["title"] for term in EXCLUDED_WANTED_CATEGORIES)
            ]
            total = len(rows)
        items = [
            WantedCategoryItem(
                title=r["title"].replace("_", " "),
                subcats=r["subcats"],
                files=r["files"],
                pages=r["pages"],
                total=r["total"],
            )
            for r in rows
        ]
        logger.info(
            f"[ws] [resp] Sending {len(items)} wanted categories (offset={offset}, total={total}) to {self.username}"
        )
        await self.socket.send_wanted_categories_response(
            WantedCategoriesResponseData(items=items, total=total)
        )
```

- [ ] **Step 5: Update `ws.py` to pass `message.data.offset`**

Replace lines 128–130 in `src/curator/ws.py`:

```python
            if isinstance(message, FetchWantedCategories):
                await handler.fetch_wanted_categories(message.data.offset)
                continue
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/backend && poetry run pytest tests/bdd/test_fetch_wanted_categories.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Run full test suite + type check**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/backend && poetry run isort . && poetry run ruff format && poetry run ruff check && poetry run pytest -q && poetry run ty check src/curator/core/handler.py src/curator/ws.py
```

Expected: all pass.

- [ ] **Step 8: Commit**

Use the gitbutler skill to commit with message: `feat: add offset and total to fetch_wanted_categories handler`

---

## Task 4: Update frontend composable (TDD)

**Files:**
- Modify: `frontend/src/composables/__tests__/useWantedCategories.test.ts`
- Modify: `frontend/src/composables/useWantedCategories.ts`

- [ ] **Step 1: Write failing tests**

Replace `frontend/src/composables/__tests__/useWantedCategories.test.ts` with:

```typescript
import type { WantedCategoryItem } from '@/types/asyncapi'
import { type Mock, beforeEach, describe, expect, it, mock } from 'bun:test'
import { resolve } from 'node:path'
import { ref } from 'vue'

export const mockSocketData = ref<string | null>(null)
export const mockSend = mock(() => {})

const mockSocketImpl = () => ({
  useSocket: {
    data: mockSocketData,
    send: mockSend,
  },
})

mock.module('@/composables/useSocket', mockSocketImpl)
mock.module('../useSocket', mockSocketImpl)
mock.module(resolve(__dirname, '../useSocket.ts'), mockSocketImpl)

import { useWantedCategories } from '../useWantedCategories'

describe('useWantedCategories', () => {
  beforeEach(() => {
    mockSocketData.value = null
    ;(mockSend as Mock<typeof mockSend>).mockClear()
    const { wantedCategories, loading, total } = useWantedCategories()
    wantedCategories.value = []
    loading.value = false
    total.value = 0
  })

  it('sends FETCH_WANTED_CATEGORIES with offset 0 by default', () => {
    const { fetchWantedCategories } = useWantedCategories()

    fetchWantedCategories()

    expect(mockSend).toHaveBeenCalledWith(
      JSON.stringify({ type: 'FETCH_WANTED_CATEGORIES', data: { offset: 0 } }),
    )
  })

  it('sends FETCH_WANTED_CATEGORIES with provided offset', () => {
    const { fetchWantedCategories } = useWantedCategories()

    fetchWantedCategories(100)

    expect(mockSend).toHaveBeenCalledWith(
      JSON.stringify({ type: 'FETCH_WANTED_CATEGORIES', data: { offset: 100 } }),
    )
  })

  it('sets loading to true when fetchWantedCategories is called', () => {
    const { loading, fetchWantedCategories } = useWantedCategories()

    fetchWantedCategories()

    expect(loading.value).toBe(true)
  })

  it('updates wantedCategories, total, and clears loading when WANTED_CATEGORIES_RESPONSE is received', () => {
    const { wantedCategories, loading, total, fetchWantedCategories } = useWantedCategories()
    fetchWantedCategories()

    const items: WantedCategoryItem[] = [
      { title: 'Foo_in_Germany', subcats: 1, files: 121, pages: 2, total: 124 },
      { title: 'Bar_in_Germany', subcats: 0, files: 5, pages: 10, total: 15 },
    ]
    mockSocketData.value = JSON.stringify({
      type: 'WANTED_CATEGORIES_RESPONSE',
      data: { items, total: 843 },
      nonce: 'x',
    })

    expect(wantedCategories.value).toEqual(items)
    expect(total.value).toBe(843)
    expect(loading.value).toBe(false)
  })

  it('ignores unrelated server messages', () => {
    const { wantedCategories } = useWantedCategories()

    mockSocketData.value = JSON.stringify({ type: 'BATCHES_LIST', data: {}, nonce: 'x' })

    expect(wantedCategories.value).toEqual([])
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/frontend && bun test src/composables/__tests__/useWantedCategories.test.ts
```

Expected: failures — `total` not exported, `fetchWantedCategories` doesn't accept offset, message doesn't include `data.offset`.

- [ ] **Step 3: Update `useWantedCategories.ts`**

Replace `frontend/src/composables/useWantedCategories.ts` with:

```typescript
import { useSocket } from '@/composables/useSocket'
import type { ServerMessage, WantedCategoryItem } from '@/types/asyncapi'
import { ref, watch } from 'vue'

const wantedCategories = ref<WantedCategoryItem[]>([])
const loading = ref(false)
const total = ref(0)

export const useWantedCategories = () => {
  const { data, send } = useSocket

  watch(
    data,
    (raw) => {
      if (!raw) return
      const msg = JSON.parse(raw as string) as ServerMessage
      if (msg.type === 'WANTED_CATEGORIES_RESPONSE') {
        wantedCategories.value = msg.data.items
        total.value = msg.data.total
        loading.value = false
      }
    },
    { flush: 'sync' },
  )

  const fetchWantedCategories = (offset = 0) => {
    loading.value = true
    send(JSON.stringify({ type: 'FETCH_WANTED_CATEGORIES', data: { offset } }))
  }

  return { wantedCategories, loading, total, fetchWantedCategories }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/frontend && bun test src/composables/__tests__/useWantedCategories.test.ts
```

Expected: all passed.

- [ ] **Step 5: Commit**

Use the gitbutler skill to commit with message: `feat: add offset and total to useWantedCategories composable`

---

## Task 5: Add Paginator to WantedCategoriesView

**Files:**
- Modify: `frontend/src/components/views/WantedCategoriesView.vue`

- [ ] **Step 1: Update the view**

Replace `frontend/src/components/views/WantedCategoriesView.vue` with:

```vue
<script setup lang="ts">
const { wantedCategories, loading, total, fetchWantedCategories } = useWantedCategories()
const { getStatus, createCategory, getCategoryText } = useCreateCategory()

const filterText = ref('')
const offset = ref(0)
const PAGE_SIZE = 100

const filteredCategories = computed(() =>
  wantedCategories.value
    .filter((c) => c.title.toLowerCase().includes(filterText.value.toLowerCase()))
    .map((c) => ({ ...c, status: getStatus(c.title) })),
)

const skeletonRows = Array<WantedCategoryItem>(10).fill({} as WantedCategoryItem)

const onPageChange = (event: { first: number }) => {
  offset.value = event.first
  fetchWantedCategories(event.first)
}

onMounted(() => {
  fetchWantedCategories(0)
})
</script>

<template>
  <div class="flex justify-between items-center mb-4 max-w-7xl mx-auto">
    <h1 class="text-2xl font-bold">Wanted Categories</h1>
    <div class="flex gap-2 items-center">
      <Button
        label="Refresh"
        :loading="loading"
        @click="fetchWantedCategories(offset)"
      />
    </div>
  </div>

  <InputText
    v-model="filterText"
    placeholder="Filter..."
    class="w-full mb-3 max-w-7xl mx-auto block"
  />

  <DataView
    :value="loading && wantedCategories.length === 0 ? skeletonRows : filteredCategories"
    data-key="title"
    layout="list"
    class="max-w-7xl mx-auto"
  >
    <template #empty>
      <span class="py-4 text-center text-surface-500 block">No wanted categories found.</span>
    </template>

    <template #list="slotProps">
      <div class="flex flex-col">
        <div
          v-for="(cat, index) in slotProps.items"
          :key="index"
          class="flex items-center justify-between py-2 px-3 rounded odd:bg-surface-50 hover:bg-surface-100"
        >
          <template v-if="loading && wantedCategories.length === 0">
            <Skeleton />
          </template>
          <template v-else>
            <span class="text-xs text-surface-400 w-8 shrink-0">{{ offset + Number(index) + 1 }}</span>
            <span class="flex items-center gap-2 flex-wrap min-w-0 flex-1">
              <ExternalLink
                :href="`https://commons.wikimedia.org/wiki/Category:${encodeURIComponent(cat.title)}`"
                :show-icon="false"
                class="hover:underline"
              >
                {{ cat.title }}
              </ExternalLink>

              <template v-if="cat.status.type === 'idle'">
                <Button
                  label="Create"
                  size="small"
                  severity="secondary"
                  text
                  @click="createCategory(cat.title, getCategoryText(cat.title))"
                />
                <Button
                  label="Create WI"
                  size="small"
                  severity="secondary"
                  text
                  @click="createCategory(cat.title, '{{WI}}')"
                />
              </template>

              <span
                v-if="cat.status.type === 'deleted'"
                class="text-xs text-red-900 cursor-help shrink-0"
                title="This category was previously deleted"
              >
                Deleted
              </span>

              <span
                v-else-if="cat.status.type === 'creating'"
                class="text-xs cursor-wait shrink-0"
              >
                Creating...
              </span>

              <template v-else-if="cat.status.type === 'created'">
                <span class="text-xs shrink-0 text-green-500">
                  Created
                  <ExternalLink
                    :href="`https://commons.wikimedia.org/wiki/${encodeURIComponent(cat.status.createdTitle)}`"
                    class="ml-1 hover:underline"
                  >
                    {{ cat.status.createdTitle }}
                  </ExternalLink>
                </span>
              </template>

              <span
                v-else-if="cat.status.type === 'error'"
                class="text-xs text-red-500 shrink-0"
              >
                {{ cat.status.message }}
              </span>
            </span>

            <span class="flex gap-3 text-xs text-surface-500 shrink-0 ml-4">
              <span title="Subcategories">{{ cat.subcats }}c</span>
              <span title="Files">{{ cat.files }}f</span>
              <span title="Pages">{{ cat.pages }}p</span>
              <span
                title="Total"
                class="font-medium text-surface-700"
              >
                {{ cat.total }}
              </span>
            </span>
          </template>
        </div>
      </div>
    </template>
  </DataView>

  <Paginator
    v-if="total > PAGE_SIZE"
    :rows="PAGE_SIZE"
    :total-records="total"
    :first="offset"
    class="max-w-7xl mx-auto mt-3"
    @page="onPageChange"
  />
</template>
```

- [ ] **Step 2: Run lint and type check**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/frontend && bun run lint && bun run typecheck
```

Expected: no errors.

- [ ] **Step 3: Commit**

Use the gitbutler skill to commit with message: `feat: add server-side pagination to WantedCategoriesView`

---

## Task 6: Run full verification

- [ ] **Step 1: Run full backend suite**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/backend && poetry run isort . && poetry run ruff format && poetry run ruff check && poetry run pytest -q && poetry run ty check
```

Expected: all pass.

- [ ] **Step 2: Run full frontend suite**

```bash
cd /Users/daxserver/projects/wikimedia/curator-app/frontend && bun test && bun run lint && bun run typecheck
```

Expected: all pass.

- [ ] **Step 3: Final commit**

Use the gitbutler skill to commit with message: `feat: wanted categories server-side pagination`

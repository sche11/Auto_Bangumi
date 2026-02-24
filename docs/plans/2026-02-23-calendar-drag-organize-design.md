# Calendar Drag-to-Organize Unknown Bangumi — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to drag bangumi cards from the "Unknown" section into weekday columns in the calendar view, with a locked flag to prevent calendar refresh from overwriting manual assignments.

**Architecture:** Add a `weekday_locked` boolean field to the Bangumi model. A new API endpoint sets weekday + locks it. The `refresh_calendar()` method skips locked items. Frontend uses vuedraggable for smooth drag-and-drop from Unknown to weekday columns, with a reset/unlock button on manually-pinned cards.

**Tech Stack:** Python/FastAPI (backend), SQLModel/SQLite (data), Vue 3 + TypeScript + vuedraggable (frontend)

---

### Task 1: Add `weekday_locked` field to data model + migration

**Files:**
- Modify: `backend/src/module/models/bangumi.py:36-38`
- Modify: `backend/src/module/database/combine.py:26,99-105`

**Step 1: Add `weekday_locked` field to `Bangumi` model**

In `backend/src/module/models/bangumi.py`, after the `air_weekday` field (line 38), add:

```python
weekday_locked: bool = Field(
    default=False, alias="weekday_locked", title="放送星期锁定"
)
```

**Step 2: Add `weekday_locked` to `BangumiUpdate` model**

In the same file, after `air_weekday` in `BangumiUpdate` (line 79), add:

```python
weekday_locked: bool = Field(
    default=False, alias="weekday_locked", title="放送星期锁定"
)
```

**Step 3: Add database migration**

In `backend/src/module/database/combine.py`:

1. Increment `CURRENT_SCHEMA_VERSION` from `8` to `9`
2. Add migration entry after the existing migration 8:

```python
(
    9,
    "add weekday_locked column to bangumi",
    [
        "ALTER TABLE bangumi ADD COLUMN weekday_locked BOOLEAN DEFAULT 0",
    ],
),
```

3. Add skip-check in `run_migrations()` after the version 8 check:

```python
if "bangumi" in tables and version == 9:
    columns = [col["name"] for col in inspector.get_columns("bangumi")]
    if "weekday_locked" in columns:
        needs_run = False
```

**Step 4: Run backend tests to verify migration**

Run: `cd backend && uv run pytest src/test/ -v -k "not test_mcp"`
Expected: All pass (new column has default, so no breaking changes)

**Step 5: Commit**

```bash
git add backend/src/module/models/bangumi.py backend/src/module/database/combine.py
git commit -m "feat(model): add weekday_locked field to bangumi for manual calendar assignment"
```

---

### Task 2: Add backend API endpoint for setting weekday

**Files:**
- Modify: `backend/src/module/api/bangumi.py`
- Modify: `backend/src/module/database/bangumi.py`

**Step 1: Add `set_weekday` database method**

In `backend/src/module/database/bangumi.py`, add method to `BangumiDatabase`:

```python
def set_weekday(self, _id: int, weekday: int | None) -> bool:
    """Set air_weekday and weekday_locked for manual calendar assignment."""
    bangumi = self.session.get(Bangumi, _id)
    if not bangumi:
        return False
    if weekday is not None:
        bangumi.air_weekday = weekday
        bangumi.weekday_locked = True
    else:
        bangumi.air_weekday = None
        bangumi.weekday_locked = False
    self.session.add(bangumi)
    self.session.commit()
    _invalidate_bangumi_cache()
    logger.debug(
        "[Database] Set weekday=%s, locked=%s for bangumi id %s",
        weekday,
        bangumi.weekday_locked,
        _id,
    )
    return True
```

**Step 2: Add API endpoint**

In `backend/src/module/api/bangumi.py`, add request model and endpoint:

```python
class SetWeekdayRequest(BaseModel):
    weekday: Optional[int] = None  # 0-6 for Mon-Sun, None to reset

@router.patch(
    path="/{bangumi_id}/weekday",
    response_model=APIResponse,
    dependencies=[Depends(get_current_user)],
)
async def set_weekday(bangumi_id: int, request: SetWeekdayRequest):
    """Manually set the broadcast weekday for a bangumi."""
    if request.weekday is not None and not (0 <= request.weekday <= 6):
        return JSONResponse(
            status_code=400,
            content={
                "status": False,
                "msg_en": "Weekday must be 0-6 (Mon-Sun) or null.",
                "msg_zh": "星期必须是 0-6（周一至周日）或空。",
            },
        )
    with Database() as db:
        success = db.bangumi.set_weekday(bangumi_id, request.weekday)
    if success:
        action = f"weekday {request.weekday}" if request.weekday is not None else "unknown"
        return JSONResponse(
            status_code=200,
            content={
                "status": True,
                "msg_en": f"Set bangumi to {action}.",
                "msg_zh": f"已设置放送日为 {action}。",
            },
        )
    return JSONResponse(
        status_code=404,
        content={
            "status": False,
            "msg_en": f"Bangumi {bangumi_id} not found.",
            "msg_zh": f"未找到番剧 {bangumi_id}。",
        },
    )
```

**Step 3: Modify `refresh_calendar()` to skip locked items**

In `backend/src/module/manager/torrent.py`, in `refresh_calendar()` method (line 212-213), change:

```python
# Before:
if bangumi.deleted:
    continue

# After:
if bangumi.deleted or bangumi.weekday_locked:
    continue
```

**Step 4: Run tests**

Run: `cd backend && uv run pytest src/test/ -v -k "not test_mcp"`
Expected: All pass

**Step 5: Commit**

```bash
git add backend/src/module/api/bangumi.py backend/src/module/database/bangumi.py backend/src/module/manager/torrent.py
git commit -m "feat(api): add PATCH /bangumi/{id}/weekday endpoint and skip locked items in calendar refresh"
```

---

### Task 3: Add frontend TypeScript types and API client

**Files:**
- Modify: `webui/types/bangumi.ts`
- Modify: `webui/src/api/bangumi.ts`

**Step 1: Add `weekday_locked` to TypeScript types**

In `webui/types/bangumi.ts`, add to `BangumiRule` interface (after `air_weekday` line 26):

```typescript
weekday_locked: boolean;
```

Add to `ruleTemplate` (after `air_weekday: null` line 65):

```typescript
weekday_locked: false,
```

**Step 2: Add API method for setting weekday**

In `webui/src/api/bangumi.ts`, add method to `apiBangumi`:

```typescript
/**
 * 手动设置番剧的放送星期
 * @param bangumiId - bangumi 的 id
 * @param weekday - 0-6 for Mon-Sun, null to reset
 */
async setWeekday(bangumiId: number, weekday: number | null) {
  const { data } = await axios.patch<ApiSuccess>(
    `api/v1/bangumi/${bangumiId}/weekday`,
    { weekday }
  );
  return data;
},
```

**Step 3: Commit**

```bash
git add webui/types/bangumi.ts webui/src/api/bangumi.ts
git commit -m "feat(webui): add weekday_locked type and setWeekday API client"
```

---

### Task 4: Install vuedraggable

**Files:**
- Modify: `webui/package.json`

**Step 1: Install vuedraggable**

```bash
cd webui && pnpm add vuedraggable@next
```

**Step 2: Commit**

```bash
git add webui/package.json webui/pnpm-lock.yaml
git commit -m "chore(webui): add vuedraggable dependency for calendar drag-and-drop"
```

---

### Task 5: Add i18n strings for drag-and-drop

**Files:**
- Modify: `webui/src/i18n/en.json`
- Modify: `webui/src/i18n/zh-CN.json`

**Step 1: Add English i18n strings**

In `webui/src/i18n/en.json`, inside the `"calendar"` object (before the closing `}`), add:

```json
"drag_hint": "Drag to assign weekday",
"pinned": "Manually assigned",
"unpin": "Reset to unknown",
"drop_here": "Drop here"
```

**Step 2: Add Chinese i18n strings**

In `webui/src/i18n/zh-CN.json`, inside the `"calendar"` object, add:

```json
"drag_hint": "拖拽以设置放送日",
"pinned": "手动设置",
"unpin": "重置为未知",
"drop_here": "拖放到此处"
```

**Step 3: Commit**

```bash
git add webui/src/i18n/en.json webui/src/i18n/zh-CN.json
git commit -m "feat(i18n): add calendar drag-and-drop strings"
```

---

### Task 6: Implement drag-and-drop in calendar.vue (Desktop)

**Files:**
- Modify: `webui/src/pages/index/calendar.vue`

This is the main implementation task. The calendar.vue file needs:

1. **Import vuedraggable** and add drag-and-drop functionality
2. **Wrap Unknown section cards** in a `<draggable>` component as the drag source
3. **Wrap each weekday column** in a `<draggable>` component as drop targets
4. **Handle the `onChange` event** to call the API when a card is dropped
5. **Add reset/unpin button** on cards with `weekday_locked === true`
6. **Add visual pin indicator** on locked cards
7. **Add drop-zone highlighting** CSS for when dragging over a weekday column

Key implementation details:

- vuedraggable uses `group` option to allow cross-list dragging
- Unknown list: `group: { name: 'calendar', pull: true, put: false }` (can pull from, cannot put into)
- Weekday lists: `group: { name: 'calendar', pull: false, put: true }` (can put into, cannot pull from)
- On `change` event with `added` property, extract the bangumi group's primary ID and target day index, then call `apiBangumi.setWeekday(id, dayIndex)`
- After API success, update the local bangumi store to reflect the change
- The reset button calls `apiBangumi.setWeekday(id, null)` and refreshes store

CSS additions:
- `.calendar-column--drop-active`: highlight border when dragging over
- `.calendar-card--pinned`: pin icon overlay
- `.calendar-unpin-btn`: reset button style
- `.sortable-ghost`: semi-transparent placeholder during drag
- `.sortable-drag`: shadow on the card being dragged

**Step 1: Implement the full calendar.vue changes**

(See implementation — this is a substantial template + script change)

**Step 2: Test manually in dev server**

```bash
cd webui && pnpm dev
```

Verify:
- Unknown cards can be dragged to weekday columns
- Weekday column highlights on dragover
- Dropped cards show pin icon
- Pin icon has working reset button
- Cards with weekday_locked show pin in weekday columns
- Mobile view still works (no drag on mobile — touch has different UX)

**Step 3: Commit**

```bash
git add webui/src/pages/index/calendar.vue
git commit -m "feat(calendar): add drag-and-drop from Unknown to weekday columns with pin/reset"
```

---

### Task 7: Update bangumi store to handle weekday_locked

**Files:**
- Modify: `webui/src/store/bangumi.ts` (if needed for reactive updates after setWeekday)

**Step 1: Add `setWeekday` action to store**

Add a store action that calls the API and updates the local bangumi array reactively:

```typescript
async function setWeekday(bangumiId: number, weekday: number | null) {
  await apiBangumi.setWeekday(bangumiId, weekday);
  // Update local state
  const item = bangumi.value?.find((b) => b.id === bangumiId);
  if (item) {
    item.air_weekday = weekday;
    item.weekday_locked = weekday !== null;
  }
}
```

**Step 2: Commit**

```bash
git add webui/src/store/bangumi.ts
git commit -m "feat(store): add setWeekday action for calendar drag-and-drop"
```

---

### Task 8: Final integration test and type check

**Step 1: Run type check**

```bash
cd webui && pnpm test:build
```

**Step 2: Run backend tests**

```bash
cd backend && uv run pytest src/test/ -v -k "not test_mcp"
```

**Step 3: Run lint**

```bash
cd webui && pnpm lint
cd backend && uv run ruff check src
```

**Step 4: Fix any issues and commit**

```bash
git add -A
git commit -m "fix: resolve type and lint issues from calendar drag-and-drop feature"
```

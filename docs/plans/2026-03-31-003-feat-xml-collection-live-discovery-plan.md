---
title: "feat: XML collection strategy with live discovery"
type: feat
status: completed
date: 2026-03-31
origin: docs/brainstorms/2026-03-31-xml-collection-strategy-requirements.md
---

# feat: XML Collection Strategy with Live Discovery

## Overview

Replace `collect_all_chats()` internals with `driver.page_source` XML parsing (33% faster in exploration, richer metadata), add a `ChatMetadata` type to carry per-chat metadata alongside names, and combine this with the live discovery TUI feature (streaming chat list, refresh button, manual continue). All callers updated from `List[str]` to `List[ChatMetadata]`.

## Problem Frame

The current `collect_all_chats()` uses individual `find_elements` calls per scroll screen, hardcoded pixel coordinates, and returns only chat names. An exploration spike validated that XML parsing is faster and captures timestamps, message previews, mute/group indicators. Separately, the live discovery plan (now superseded) adds TUI streaming during collection. Both changes modify `collect_all_chats` internals — combining them avoids conflicts and delivers both improvements atomically. (see origin: `docs/brainstorms/2026-03-31-xml-collection-strategy-requirements.md`)

## Requirements Trace

- R1. XML parsing replaces find_elements for chat collection; find_elements retained for settle detection
- R2. Proportional scroll coordinates from `get_window_size()`
- R3. find_elements count stabilization for settle detection
- R4. Capture all parseable metadata fields; missing fields → None
- R5. Return `List[ChatMetadata]` with `.name` field
- R6. No dedup changes — duplicates preserved in list
- R7. Update all callers to handle `List[ChatMetadata]`
- R8. Combined with live-discovery: `on_chat_found(ChatMetadata)` callback, TUI streaming, refresh, manual continue
- R9. `limit` and `sort_alphabetical` continue to work

## Scope Boundaries

- No export pipeline, transcription, or Google Drive changes
- No changes to `_find_chat_with_scrolling()` (export-phase scroll path)
- Strategies C/D not pursued (both broken in exploration)
- No dedup logic changes
- `whatsapp_export.py`'s parallel `collect_all_chats` marked deprecated, not rewritten

## Context & Research

### Relevant Code and Patterns

- **`collect_all_chats()`**: `whatsapp_driver.py` line 1501 — the method being replaced. Uses `all_chats_dict` for dedup, `driver.swipe(500,1500,500,500)` for scrolling, smart-wait settle loop at line 1576
- **Connection setup**: `headless.py` lines 141-183 — canonical flow using `WhatsAppDriver`
- **`get_page_source()`**: `whatsapp_driver.py` line 1470 — existing XML dump helper
- **State models**: `state/models.py` — all Pydantic `BaseModel`. `ChatState` has `name`, `status`, `metadata: Dict[str, Any]`
- **`SessionState.add_chat()`**: `state/models.py` line 190 — keys by name, silently drops duplicates
- **TUI app**: `textual_app.py` — `_discovered_chats: List[str]`, `transition_to_selection(chats: List[str])`
- **Discovery screen**: `discovery_screen.py` — `_collect_chats()` wraps `collect_all_chats` in `asyncio.to_thread`
- **Selection screen**: `selection_screen.py` — reads `app.discovered_chats`, passes to `ChatListWidget`
- **ChatListWidget**: `chat_list.py` — `_chats: List[str]`, `selected_chats: Set[str]` reactive
- **Caller sites**: `headless.py:183`, `discovery_screen.py:604`, `interactive.py:160/163/258`, `chat_exporter.py` (`export_chats(chat_names=...)`), `state_manager.py:150` (`add_chats`), `legacy/cli/commands/export.py:264`, `legacy/cli/commands/wizard.py:294/335/339`, `whatsapp_export.py:2705/2708/2786`
- **Exploration XML**: `exploration_output/page_source_default.xml` — confirmed resource IDs per chat row
- **Live discovery plan (superseded)**: `docs/plans/2026-03-31-001-feat-live-discovery-inventory-plan.md` — Units 1-4 describe callback, TUI widgets, streaming wiring, and refresh

### Institutional Learnings

- **Discovery speed baseline** (PR #12): Smart waits replaced hardcoded sleeps. 200+ chats in ~18-23s. `restart_app_to_top()` costs 4-6s per call.
- **`verify_whatsapp_is_open()` is heavyweight**: ~10 Appium calls. Benchmarks should account for this.
- **Appium driver is not thread-safe**: All UI automation on main thread; TUI callbacks use `call_from_thread`.
- **`_fire_progress` pattern**: Used in `chat_exporter.py` — wraps callback calls in try/except so callback errors don't crash the main loop.

## Key Technical Decisions

- **ChatMetadata as dataclass in `export/models.py`**: Avoids layering inversion (driver layer importing from state layer). State layer uses Pydantic throughout, but `ChatMetadata` is a lightweight transport type that doesn't need serialization. New file `export/models.py` keeps the driver layer independent. (Resolves deferred question from origin)
- **Legacy `whatsapp_export.py` marked deprecated**: Its parallel `collect_all_chats` implementation is not rewritten. Call sites in that file extract `.name` from `ChatMetadata` items. A deprecation comment points to `WhatsAppDriver.collect_all_chats`. (Resolves deferred question from origin)
- **Caller boundary strategy**: Callers that need `List[str]` (e.g., `export_chats(chat_names=...)`, `state_manager.add_chats()`, `click_chat()`) receive `[c.name for c in chats]` at the call boundary. The ChatMetadata objects don't propagate past the collection/discovery layer into the export pipeline.
- **`state_manager.add_chat()` dedup-by-name preserved**: It silently drops duplicate names. This is documented as the expected behavior — the export loop iterates the raw `List[ChatMetadata]` and is the authoritative source for duplicate handling. (Resolves deferred question from origin)
- **`ChatListWidget.selected_chats` stays `Set[str]`**: Widget internals key on `.name` strings. Duplicate names collapse to one checkbox — documented as a known TUI limitation. (Resolves deferred question from origin)
- **`page_source` ParseError handling**: Wrap in try/except, skip iteration on failure, don't increment `no_new_chats_count`. (Resolves deferred question from origin)
- **Settings tuning deferred to implementation**: Test `waitForIdleTimeout=0` and `scrollAcknowledgmentTimeout=100` during development; apply if beneficial.
- **Build parent_map once per page_source call**: Not per-element. Avoids O(rows_per_screen × elements) overhead per scroll.

## Open Questions

### Resolved During Planning

- **ChatMetadata shape?** → Dataclass in `export/models.py`. Lightweight, no Pydantic dependency at the driver layer.
- **Legacy whatsapp_export.py disposition?** → Mark deprecated, update call sites to extract `.name`.
- **state_manager dedup?** → Preserved. Export loop is authoritative for duplicate handling.
- **ChatListWidget Set[str]?** → Kept. Documented limitation for duplicate names.
- **Combined plan structure?** → 6 units: model, collection core, TUI discovery, caller updates, tests, legacy cleanup.

### Deferred to Implementation

- **Exact resource ID extraction validation**: Grep `exploration_output/page_source_default.xml` during implementation to confirm correct attribute names for each metadata field.
- **Settings tuning values**: Test `waitForIdleTimeout=0` / `scrollAcknowledgmentTimeout=100` on Strategy B during implementation.
- **Dry-run mock format**: Update the 10-item mock in `discovery_screen.py` to `List[ChatMetadata]` — exact field values determined during implementation.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
┌─────────────────────────────────────────────────────┐
│  collect_all_chats(limit, sort_alphabetical,        │
│                    on_chat_found)                    │
│                                                     │
│  1. restart_app_to_top()                            │
│  2. window_size = driver.get_window_size()          │
│     compute proportional scroll coords              │
│  3. Loop (max_scrolls=50):                          │
│     a. xml = driver.page_source                     │
│        (try/except ParseError → continue)           │
│     b. Parse XML: build parent_map once             │
│     c. For each chat row in XML:                    │
│        - Extract name, timestamp, preview, etc.     │
│        - Create ChatMetadata                        │
│        - Append to results list                     │
│        - Fire on_chat_found(metadata) if set        │
│     d. Check limit / no-new-chats (3 consecutive)   │
│     e. Scroll (proportional coords, 300ms)          │
│     f. Smart-wait: find_elements count stability    │
│  4. restart_app_to_top()                            │
│  5. Sort by .name if sort_alphabetical              │
│  6. Return List[ChatMetadata]                       │
│                                                     │
│  TUI Integration (DiscoveryScreen):                 │
│  - on_chat_found callback → call_from_thread        │
│  - _add_discovered_chat appends to ListView         │
│  - Running count in status label                    │
│  - Refresh clears list, reruns with exclusive=True  │
│  - Continue button → transition_to_selection        │
└─────────────────────────────────────────────────────┘
```

## Implementation Units

### Phase 1: Core Data Model

- [x] **Unit 1: ChatMetadata dataclass**

**Goal:** Define the `ChatMetadata` type that carries per-chat metadata through the collection layer.

**Requirements:** R4, R5

**Dependencies:** None

**Files:**
- Create: `whatsapp_chat_autoexport/export/models.py`
- Test: `tests/unit/test_export_models.py`

**Approach:**
- Define `ChatMetadata` as a Python `dataclass` with fields: `name: str`, `timestamp: Optional[str]`, `message_preview: Optional[str]`, `is_muted: bool`, `is_group: bool`, `group_sender: Optional[str]`, `has_type_indicator: bool`, `photo_description: Optional[str]`
- All fields except `name` default to `None` / `False`
- Add a `__str__` that returns `self.name` for convenient string coercion in callers

**Patterns to follow:**
- `state/models.py` for field naming conventions (but use dataclass, not Pydantic)
- `core/interfaces.py` for existing dataclass usage in the project

**Test scenarios:**
- Happy path: Create ChatMetadata with all fields populated → all attributes accessible
- Happy path: Create ChatMetadata with only name → all optional fields are None/False
- Edge case: `str(ChatMetadata(name="John"))` returns `"John"`
- Edge case: ChatMetadata with empty string name → should be allowed (WhatsApp may have empty-named chats)

**Verification:**
- `ChatMetadata` importable from `whatsapp_chat_autoexport.export.models`
- `str()` coercion returns `.name`

---

### Phase 2: Collection Core

- [x] **Unit 2: Replace collect_all_chats internals with XML parsing**

**Goal:** Rewrite the scroll-and-collect loop to use `page_source` XML parsing with proportional coordinates and `on_chat_found` callback.

**Requirements:** R1, R2, R3, R4, R5, R6, R8, R9

**Dependencies:** Unit 1

**Files:**
- Modify: `whatsapp_chat_autoexport/export/whatsapp_driver.py`
- Test: `tests/unit/test_xml_collection.py`
- Modify: `tests/unit/test_discovery_speed.py` (settle-wait tests reference old find_elements loop — need `page_source` PropertyMock alongside find_elements mock for settle detection)

**Approach:**
- Add `on_chat_found: Optional[Callable] = None` parameter to `collect_all_chats()`
- Replace the inner loop: instead of `find_elements` → position sort → dict insert, use `driver.page_source` → `ET.fromstring()` → walk XML for chat rows → create `ChatMetadata` per row → append to results list
- **Termination detection**: Maintain a separate `seen_names: Set[str]` used only for end-of-list detection (not for deduplication of results). After parsing each screen's XML, count how many names are not in `seen_names`. If none are new, increment `no_new_chats_count`; otherwise reset it and add names to `seen_names`. Append all rows to results regardless (preserving R6's no-dedup behavior). Without this, the loop would never terminate early because duplicate names always grow the results list.
- Wrap `page_source` + `ET.fromstring()` in try/except for `ET.ParseError` and empty string — on failure, `continue` (don't increment `no_new_chats_count`)
- Compute scroll coords from `driver.get_window_size()` at loop start — scroll from 75% to 25% height, centered horizontally
- Retain the existing smart-wait settle loop (find_elements count stability at 50ms intervals)
- Fire `on_chat_found(metadata)` for each new chat, wrapped in try/except (matching `_fire_progress` error-handling pattern)
- Build `parent_map` once per `page_source` call, not per element
- Extract metadata by finding `contact_row_container` elements, then walking children for known resource IDs. For `contact_photo`, read `content-desc` attribute
- Return `List[ChatMetadata]` instead of `List[str]`
- `sort_alphabetical` sorts by `ChatMetadata.name` using `sorted(results, key=lambda c: c.name)`
- `limit` truncates the results list

**Patterns to follow:**
- Existing smart-wait pattern at `whatsapp_driver.py` line 1576
- `_fire_progress` error handling in `chat_exporter.py`
- `explore_chat_collection.py` Strategy B implementation (directional reference, not copy)

**Test scenarios:**
- Happy path: Mock `page_source` returning XML with 3 chat rows → returns `List[ChatMetadata]` with 3 items, correct names and metadata
- Happy path: `on_chat_found` callback fires for each chat with correct `ChatMetadata`
- Happy path: `limit=2` with 5 chats available → returns 2 items, stops scrolling
- Happy path: `sort_alphabetical=True` → results sorted by `.name`
- Edge case: `page_source` returns empty string → ParseError caught, loop continues, no increment to `no_new_chats_count`
- Edge case: `page_source` returns XML with no chat rows → treated as no-new-chats scroll
- Edge case: Chat row missing timestamp/preview elements → `ChatMetadata` has None for those fields
- Edge case: Duplicate chat names in XML → both appear in results list (no dedup)
- Error path: `on_chat_found` callback raises exception → caught and logged, collection continues
- Error path: `page_source` raises exception mid-scroll → caught, skip iteration, continue
- Integration: Proportional scroll coordinates computed from mocked `get_window_size()` — verify scroll uses correct coordinates, not hardcoded `(500, 1500)`

**Verification:**
- `collect_all_chats()` returns `List[ChatMetadata]`
- No hardcoded scroll coordinates in the method
- `on_chat_found` fires per chat with `ChatMetadata` argument
- ParseError handling does not truncate collection

---

### Phase 3: TUI Live Discovery

- [x] **Unit 3: Discovery screen TUI — streaming inventory, refresh, and continue**

**Goal:** Add live chat inventory to DiscoveryScreen showing chats as they're discovered, with Refresh and Continue buttons. Replace auto-transition with manual continue.

**Requirements:** R8 (live discovery plan's R1-R9)

**Dependencies:** Unit 2

**Files:**
- Modify: `whatsapp_chat_autoexport/tui/textual_screens/discovery_screen.py`
- Modify: `whatsapp_chat_autoexport/tui/styles.tcss`
- Test: `tests/unit/test_discovery_screen.py`

**Approach:**
- Add discovery UI widgets to `compose()`: status label (`Static`), chat inventory (`ListView`), action row with Refresh and Continue buttons. Section hidden until device connected.
- Add screen state: `_connected_driver`, `_discovered_chats: List[ChatMetadata]`, `_discovery_generation: int`
- Pass `on_chat_found` callback to `collect_all_chats` in `_collect_chats()`. Callback uses `call_from_thread(self._add_discovered_chat, metadata, generation)` with generation counter to drop stale callbacks from cancelled workers. **Important**: capture generation by value into the closure (`gen = self._discovery_generation` before creating the callback), not by reference to `self._discovery_generation`, so old workers' callbacks carry the snapshot value and are correctly detected as stale.
- `_add_discovered_chat`: append to `_discovered_chats`, add `ListItem(Label(metadata.name))` to inventory `ListView`, update count in status label
- `_handle_chat_collection`: on success enable Refresh + Continue; on failure enable Refresh only; zero chats shows warning
- Remove auto-transition. Add `action_continue` that calls `transition_to_selection(driver, _discovered_chats)`
- `action_refresh_chats`: clear inventory, reset list, disable buttons, re-run worker with `exclusive=True`
- Guard refresh: no-op if scanning or no driver
- Update dry-run mock from `List[str]` to `List[ChatMetadata]` objects (populate `.name` from existing string list, set all other fields to None/False defaults — exact field values are deferred to implementation)
- Style following the DeviceList CSS block pattern

**Patterns to follow:**
- Superseded live-discovery plan Units 2-4 (directional, adapted for ChatMetadata)
- Existing `_scan_devices` worker pattern in `discovery_screen.py`
- `exclusive=True` worker pattern

**Test scenarios:**
- Happy path: Device connected → discovery runs → chats appear one by one in inventory list → count updates → both buttons enabled
- Happy path: Continue button → `transition_to_selection` called with `List[ChatMetadata]` and driver
- Happy path: Refresh → inventory cleared, discovery re-runs, new chats appear
- Edge case: Discovery returns 0 chats → warning shown, only Refresh enabled, Continue disabled
- Edge case: Discovery fails → error shown, Refresh enabled, Continue disabled
- Edge case: Refresh during active scan → no-op (guarded)
- Edge case: Dry-run mode → mock `ChatMetadata` objects injected, no driver needed
- Integration: `on_chat_found` callback fires from background thread → `call_from_thread` safely updates TUI

**Verification:**
- Chats stream into ListView during collection
- Refresh clears and re-runs
- Continue passes `List[ChatMetadata]` to SelectionScreen
- No auto-transition on discovery completion

---

### Phase 4: Caller Updates

- [x] **Unit 4: Update all callers from List[str] to List[ChatMetadata]**

**Goal:** Update every caller of `collect_all_chats()` and downstream consumers to handle `List[ChatMetadata]`.

**Requirements:** R7, R9

**Dependencies:** Unit 1, Unit 2

**Files:**
- Modify: `whatsapp_chat_autoexport/headless.py`
- Modify: `whatsapp_chat_autoexport/tui/textual_app.py`
- Modify: `whatsapp_chat_autoexport/tui/textual_screens/selection_screen.py`
- Modify: `whatsapp_chat_autoexport/tui/textual_widgets/chat_list.py`
- Modify: `whatsapp_chat_autoexport/export/interactive.py`
- Modify: `whatsapp_chat_autoexport/export/chat_exporter.py`
- Modify: `whatsapp_chat_autoexport/state/state_manager.py`
- Test: `tests/unit/test_headless.py` (update mocks)
- Test: `tests/unit/test_selection_screen_export.py` (update mocks)

**Approach:**
- **`headless.py`**: `all_chats = driver.collect_all_chats(...)` now returns `List[ChatMetadata]`. Extract names at the export boundary: `exporter.export_chats(chat_names=[c.name for c in all_chats], ...)`
- **`textual_app.py`**: Change `_discovered_chats: List[str]` → `List[ChatMetadata]`, `transition_to_selection(chats: List[ChatMetadata])`, `discovered_chats` property → `List[ChatMetadata]`. Note: `_selected_chats` stays `List[str]` — it is populated from selection (ChatListWidget outputs strings), not from collection
- **`selection_screen.py`**: `app.discovered_chats` now returns `List[ChatMetadata]`. In `compose()`, change `chats=self.app.discovered_chats` to `chats=[c.name for c in self.app.discovered_chats]` — ChatListWidget stays string-based internally. `len(self.app.discovered_chats)` calls elsewhere still work (type-agnostic)
- **`ChatListWidget`**: No internal changes needed — receives `List[str]` from selection_screen extraction. `selected_chats: Set[str]` unchanged.
- **`interactive.py`**: Integer-indexed selections (`all_chats[idx - 1]`) now return `ChatMetadata` objects. Extract `.name` when passing to export: `chats_to_export = [c.name for c in selected]`
- **`chat_exporter.py`**: `export_chats(chat_names: List[str])` signature unchanged — it receives extracted names
- **`state_manager.py`**: `add_chats(chat_names: List[str])` signature unchanged — receives extracted names
- **Test mocks**: Update `collect_all_chats.return_value` from `["Chat A", "Chat B"]` to `[ChatMetadata(name="Chat A"), ChatMetadata(name="Chat B")]` in all test files

**Patterns to follow:**
- Existing caller patterns in each file
- `[c.name for c in chats]` extraction at boundaries

**Test scenarios:**
- Happy path: `headless.py` receives `List[ChatMetadata]` → passes name list to `export_chats` → export succeeds
- Happy path: TUI `transition_to_selection` receives `List[ChatMetadata]` → `SelectionScreen` displays chat names correctly
- Happy path: `interactive.py` integer selection → extracts `.name` from `ChatMetadata` item → passes to export
- Edge case: Empty chat list `[]` → all callers handle gracefully (same as before)
- Edge case: `sort_alphabetical=True` in `interactive.py` → sorted by `.name`

**Verification:**
- All callers compile without type errors
- Headless export completes with `List[ChatMetadata]` from `collect_all_chats`
- TUI displays chat names correctly in selection screen
- No caller passes raw `ChatMetadata` objects where strings are expected

---

### Phase 5: Test Coverage

- [x] **Unit 5: Existing test updates and new integration tests**

**Goal:** Update all existing tests that mock `collect_all_chats` and add integration tests for the XML parsing + callback chain.

**Requirements:** Success criteria (tests updated, new tests added)

**Dependencies:** Units 1-4

**Files:**
- Modify: `tests/unit/test_headless.py`
- Modify: `tests/unit/test_discovery_screen.py`
- Modify: `tests/unit/test_discovery_speed.py`
- Modify: `tests/unit/test_selection_screen_export.py`
- Modify: `tests/unit/test_selection_screen_processing.py`
- Test: `tests/unit/test_xml_collection.py` (created in Unit 2)
- Test: `tests/unit/test_export_models.py` (created in Unit 1)

**Approach:**
- Update every test that mocks `collect_all_chats.return_value` as `List[str]` → `List[ChatMetadata]`
- Update `test_discovery_speed.py` — the smart-wait and scroll tests reference the old find_elements loop; update to match XML parsing behavior
- Add integration test: mock `page_source` → XML parsing → `on_chat_found` fires → `ChatMetadata` returned — end-to-end within `collect_all_chats`

**Test scenarios:**
- Integration: Full `collect_all_chats` with mocked `page_source` returning multi-row XML → verifies XML parsing, metadata extraction, callback firing, and `List[ChatMetadata]` return in one test
- Happy path: `test_discovery_speed.py` settle-wait tests still pass with XML-based collection loop

**Verification:**
- `poetry run pytest` passes with 0 failures
- No test uses `collect_all_chats.return_value = ["string", ...]` (grep verification)

---

### Phase 6: Legacy Cleanup

- [x] **Unit 6: Legacy caller updates and deprecation**

**Goal:** Update legacy callers and mark the duplicate `collect_all_chats` in `whatsapp_export.py` as deprecated.

**Requirements:** R7

**Dependencies:** Unit 1, Unit 2

**Files:**
- Modify: `whatsapp_chat_autoexport/whatsapp_export.py`
- Modify: `whatsapp_chat_autoexport/legacy/cli/commands/export.py`
- Modify: `whatsapp_chat_autoexport/legacy/cli/commands/wizard.py`

**Approach:**
- `whatsapp_export.py` line ~1209: Add deprecation docstring to its own `collect_all_chats`. Do not rewrite the method itself.
- `whatsapp_export.py` call sites (lines 2705, 2708, 2786): These call the legacy class's own `collect_all_chats` which still returns `List[str]`. Add a comment noting the method is deprecated. If these paths are exercised by users, the legacy behavior is preserved.
- `legacy/cli/commands/export.py:264`: If this calls `WhatsAppDriver.collect_all_chats`, extract `.name` from results. If it calls the legacy class, no change needed.
- `legacy/cli/commands/wizard.py:294, 335, 339`: Same pattern — extract `.name` when indexing/slicing if using `WhatsAppDriver`.

**Test expectation:** None — legacy paths have no dedicated tests and are not actively maintained.

**Verification:**
- Legacy callers do not crash when receiving `List[ChatMetadata]` (if using WhatsAppDriver) or continue working with `List[str]` (if using legacy class)
- Deprecation comment present on `whatsapp_export.py`'s `collect_all_chats`

## System-Wide Impact

- **Interaction graph:** `collect_all_chats` → `on_chat_found` callback → `DiscoveryScreen._add_discovered_chat` → `call_from_thread` → TUI ListView update. The callback chain crosses thread boundaries (Appium thread → TUI main thread).
- **Error propagation:** `on_chat_found` callback errors are caught and logged (matching `_fire_progress` pattern). `page_source` ParseError caught per-iteration, does not crash loop. Missing metadata fields degrade to None.
- **State lifecycle risks:** `state_manager.add_chat()` deduplicates by name — silently drops duplicate ChatMetadata items. This is documented and accepted. The export loop (not state_manager) is the authoritative source for what gets exported.
- **API surface parity:** `List[ChatMetadata]` replaces `List[str]` at the collection layer. Export pipeline, chat_exporter, and state_manager continue to receive `List[str]` via `.name` extraction at the boundary.
- **Integration coverage:** The `on_chat_found` → `call_from_thread` → ListView chain is the most cross-layer interaction. Unit tests with mocked page_source + callback assertions cover this. Textual pilot tests verify the TUI wiring.
- **Unchanged invariants:** `export_chats(chat_names: List[str])` signature unchanged. `state_manager.add_chats(List[str])` unchanged. `click_chat(chat_name: str)` unchanged. `_find_chat_with_scrolling()` unchanged. All export and pipeline flows receive string names, not ChatMetadata.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| WhatsApp changes resource IDs | Missing metadata fields degrade to None. Only `conversations_row_contact_name` is critical — if that breaks, the old method would break equally. |
| `page_source` XML structure varies across chat types (groups, communities, broadcasts) | R4 specifies None for missing fields. Parser is resilient. Validate against exploration XML during implementation. |
| `on_chat_found` callback slows collection | Callback is lightweight (append to list + `call_from_thread`). Same pattern as `_fire_progress` which is proven fast. |
| Thread safety of `call_from_thread` | Textual's `call_from_thread` is the documented thread-safe mechanism. Already used for device scanning in DiscoveryScreen. |
| Test mock updates are incomplete | Grep for `collect_all_chats.return_value` after Unit 5 to verify no stale `List[str]` mocks remain. |
| Legacy paths crash with new return type | Legacy `whatsapp_export.py` has its own `collect_all_chats` returning `List[str]` — those paths are unaffected. Only `WhatsAppDriver` callers get `List[ChatMetadata]`. |

## Sources & References

- **Origin document:** [docs/brainstorms/2026-03-31-xml-collection-strategy-requirements.md](docs/brainstorms/2026-03-31-xml-collection-strategy-requirements.md)
- **Superseded plan:** [docs/plans/2026-03-31-001-feat-live-discovery-inventory-plan.md](docs/plans/2026-03-31-001-feat-live-discovery-inventory-plan.md) (status: superseded-merged)
- **Exploration findings:** `exploration_output/findings_report.md`, `exploration_output/page_source_default.xml`
- **Exploration plan:** `docs/plans/2026-03-31-002-feat-chat-collection-exploration-plan.md`
- Related code: `whatsapp_chat_autoexport/export/whatsapp_driver.py` (collect_all_chats, get_page_source)
- Related code: `whatsapp_chat_autoexport/tui/textual_screens/discovery_screen.py` (TUI discovery)
- Related code: `whatsapp_chat_autoexport/tui/textual_app.py` (app state, transition)

---
title: "feat: Optimize chat discovery speed with smart waits"
type: feat
status: completed
date: 2026-03-29
origin: docs/brainstorms/2026-03-29-discovery-speed-optimization-requirements.md
---

# feat: Optimize chat discovery speed with smart waits

## Overview

Replace hardcoded `time.sleep()` calls in the chat discovery phase (`collect_all_chats()` and `restart_app_to_top()`) with condition-based waits using `TimeoutConfig` ceilings. Same pattern as PR #11 (export step optimization), applied to the discovery methods that were out of scope there.

## Problem Frame

The discovery phase has three categories of hardcoded sleeps totaling 18-23s for heavy users (200+ chats). Most of this time is unconditional sleeping — the UI is typically ready much sooner.

(see origin: docs/brainstorms/2026-03-29-discovery-speed-optimization-requirements.md)

## Requirements Trace

- R1. Replace 0.5s scroll settle sleep with condition-based wait
- R2. Smart wait must use `TimeoutConfig` ceiling
- R3. Replace 3-5s app restart sleep with polling for chat list element
- R4. Wireless vs USB as timeout ceiling, not sleep duration
- R5. Reduce post-force-stop delay to 0.2s

## Scope Boundaries

- Only `whatsapp_driver.py` discovery methods (`collect_all_chats`, `restart_app_to_top`)
- No changes to export steps (already optimized in PR #11)
- No changes to `_find_chat_with_scrolling` (separate method, used during export)
- No new CLI flags

## Context & Research

### Relevant Code and Patterns

- **`TimeoutConfig`** in `config/timeouts.py` — already has `scroll_settle_time: 0.5` (NORMAL), `0.3` (FAST), `1.0` (SLOW) and `app_launch_timeout: 30.0`. These are the exact ceiling fields needed.
- **PR #11 pattern** — export steps import `get_timeout_config()` and use fields like `screen_transition_wait` as ceilings for element waits. The discovery code should follow the same import pattern.
- **`verify_whatsapp_is_open()`** at line 1127 — already checks for `conversations_row_contact_name` (line 1189), toolbar, action bar, and menu button. Returns True/False. Can be polled directly for R3.
- **Existing element finding** — `self.driver.find_elements("id", ...)` is the standard Appium call used throughout. No custom `ElementFinder` in `whatsapp_driver.py`.

## Key Technical Decisions

- **Scroll-settled condition: compare element count before/after** — Of the three options in the deferred question (count comparison, element presence, position stabilization), count comparison is simplest and most reliable. Element presence doesn't work because elements exist from previous scrolls. Position stabilization is expensive and race-prone. The existing code already counts elements at lines 1458-1468; the smart wait just polls until count stabilizes or ceiling is reached. (see origin: Outstanding Questions, Deferred to Planning)
- **R3: Poll `verify_whatsapp_is_open()` directly** — Rather than writing a new element wait, reuse the existing multi-check method at short intervals. Use `app_launch_timeout` as ceiling (30s default), with `is_wireless` scaling the poll frequency (see origin: Resolved question).
- **Wire `TimeoutConfig` via `get_timeout_config()` import** — Import `get_timeout_config` at module level in `whatsapp_driver.py` and call it inline where ceiling values are needed. No constructor changes or instance attribute needed — the global config singleton is sufficient (see origin: Key Decisions).

## Open Questions

### Resolved During Planning

- **Scroll-settled condition**: Use element count comparison — simplest, most reliable, already partially implemented in the collection loop.
- **`verify_whatsapp_is_open()` reuse for R3**: Yes — it already checks for chat list elements. Poll it with short intervals instead of sleeping.

### Deferred to Implementation

- Exact poll interval for `verify_whatsapp_is_open()` retry loop — start with 0.5s, tune if needed.

## Implementation Units

- [x] **Unit 1: Smart waits in `restart_app_to_top()` and `collect_all_chats()`**

**Goal:** Replace all three categories of hardcoded sleeps with condition-based waits.

**Requirements:** R1, R2, R3, R4, R5

**Files:**
- Modify: `whatsapp_chat_autoexport/export/whatsapp_driver.py`
- Test: `tests/unit/test_discovery_speed.py` (new)

**Approach:**

*Post-force-stop (R5):* Change `sleep(0.5)` at line 1311 to `sleep(0.2)`.

*App restart wait (R3, R4):* Replace both the `sleep(wait_time)` at line 1327 AND the subsequent `verify_whatsapp_is_open()` call at line 1330 with a single polling loop that calls `verify_whatsapp_is_open()` at ~0.5s intervals. Use `get_timeout_config().app_launch_timeout` as the ceiling (30s NORMAL), scaled by 1.5x when `self.is_wireless` is True. On timeout, return False with an error message indicating the app did not become ready within the timeout period (matching current failure behavior).

Note: `verify_whatsapp_is_open()` is heavier than "4 find_elements calls" — it also checks `current_package`, `current_activity`, and calls `check_if_phone_locked()`. At 0.5s poll intervals on USB this is fine. On wireless where each Appium call has higher latency, the effective interval will be longer (the method itself may take 1-2s), which is acceptable — the key improvement is eliminating the unconditional 5s sleep.

*Scroll settle (R1, R2):* Replace `sleep(0.5)` at line 1472 (after the swipe) with a smart wait that:
1. Records element count immediately after the swipe
2. Polls `find_elements("id", "com.whatsapp:id/conversations_row_contact_name")` at short intervals (~0.05s)
3. Requires element count to stabilize for 2 consecutive polls (~100ms stability window) before declaring settled — this prevents returning during mid-animation element count fluctuations
4. Exits when either: count stabilizes (new elements queryable) or `get_timeout_config().scroll_settle_time` ceiling is reached
5. Always returns control to the collection loop — if ceiling is reached without change, the existing `no_new_chats_count` logic (lines 1464-1468) handles end-of-list detection

Import `get_timeout_config` from `config.timeouts` at module level.

**Patterns to follow:**
- PR #11 export steps: import `get_timeout_config()`, use config fields as ceilings
- `verify_whatsapp_is_open()` — existing multi-check method to reuse for R3

**Test scenarios:**
- Happy path: `restart_app_to_top` completes in < 1s when `verify_whatsapp_is_open()` returns True immediately on first poll
- Happy path: `restart_app_to_top` succeeds after 3 polls (1.5s) when `verify_whatsapp_is_open()` fails twice then succeeds
- Happy path: Scroll settle returns early when element count changes within 0.1s
- Happy path: Scroll settle uses full ceiling when element count doesn't change (end of list)
- Edge case: Post-force-stop uses exactly 0.2s delay (assert `time.sleep` called with 0.2)
- Edge case: Wireless connection uses same poll interval but higher timeout ceiling
- Edge case: FAST profile uses shorter scroll_settle_time ceiling (0.3s)
- Error path: `verify_whatsapp_is_open()` never returns True — `restart_app_to_top` returns False after `app_launch_timeout`
- Error path: `find_elements` raises during scroll settle — falls through gracefully, doesn't hang

**Verification:**
- No `time.sleep(0.5)` or `time.sleep(3)` or `time.sleep(5)` remains in `restart_app_to_top()` or `collect_all_chats()`
- Only `time.sleep(0.2)` (post-force-stop) and short poll intervals remain
- All existing tests pass (mocked calls in `test_headless.py` unaffected)
- New tests validate polling behavior with mocked driver

---

- [x] **Unit 2: Integration test for discovery speed**

**Goal:** Validate that the smart waits produce measurably faster discovery.

**Requirements:** All (R1-R5)

**Dependencies:** Unit 1

**Files:**
- Modify: `tests/unit/test_discovery_speed.py` (add integration-style tests)

**Approach:**
- Mock the Appium driver and `verify_whatsapp_is_open()` to return immediately
- Simulate a 10-chat collection with mocked `find_elements` returning elements after short delays
- Assert wall-clock time is significantly less than the old hardcoded delays would produce (old: ~10s for 10 scrolls + 2 restarts; new: < 3s)
- Assert timing is consistent across FAST and NORMAL profiles (just different ceilings)

**Patterns to follow:**
- `tests/integration/test_parallel_export.py` — timing-based assertions with mocked driver

**Test scenarios:**
- Happy path: 10-chat discovery with fast-responding mocks completes in < 3s (vs ~10s with old sleeps)
- Happy path: Timing varies correctly between FAST and NORMAL profiles
- Edge case: Slow-responding verify (simulated wireless) still completes within ceiling

**Verification:**
- Integration test demonstrates measurable speedup
- All tests pass

## System-Wide Impact

- **Interaction graph:** `collect_all_chats()` is called from `headless.py` and the TUI's discovery screen. Neither caller is affected — the method signature and return value are unchanged.
- **Unchanged invariants:** `verify_whatsapp_is_open()` behavior unchanged — it's only called more frequently. `_find_chat_with_scrolling` not touched. Export step optimizations from PR #11 not affected.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Scroll settle too aggressive — elements not yet queryable | `scroll_settle_time` ceiling ensures minimum wait; SLOW profile available |
| `verify_whatsapp_is_open()` too slow for frequent polling | Method makes ~10 Appium calls (package, activity, 4 find_elements, lock check). On USB at 0.5s intervals this is fine. On wireless the method itself may take 1-2s, making effective interval longer — but still far better than unconditional 5s sleep. |
| 0.2s post-force-stop insufficient on some devices | R3 polling loop provides safety net — if app isn't stopped, launch fails and retry kicks in |

## Sources & References

- **Origin document:** [docs/brainstorms/2026-03-29-discovery-speed-optimization-requirements.md](docs/brainstorms/2026-03-29-discovery-speed-optimization-requirements.md)
- PR #11: Export speed optimization (merged) — established the smart wait pattern
- TimeoutConfig: `whatsapp_chat_autoexport/config/timeouts.py`
- Discovery code: `whatsapp_chat_autoexport/export/whatsapp_driver.py` lines 1270-1492

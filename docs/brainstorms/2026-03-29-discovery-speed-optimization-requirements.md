---
date: 2026-03-29
topic: discovery-speed-optimization
---

# Optimize Chat Discovery Speed

## Problem Frame

The chat discovery phase (`collect_all_chats()`) has three categories of hardcoded `time.sleep()` calls that add significant delay before any export work begins. For a user with 200+ chats, discovery takes 18-23s — most of it sleeping. This directly follows the pattern addressed in PR #11 (export step speed optimization), but the discovery phase was out of scope there.

## Requirements

**Scroll settle delays**
- R1. Replace the 0.5s `time.sleep()` after each scroll (line 1472) with a condition-based wait that detects when the scroll animation has completed and new elements are queryable. The existing element-count comparison loop (lines 1458-1468) stays as end-of-list detection — the smart wait replaces only the fixed sleep.
- R2. The smart wait must have a timeout ceiling from `TimeoutConfig` to prevent infinite hangs

**App restart delays**
- R3. Replace the 3-5s hardcoded `time.sleep()` in `restart_app_to_top()` (line 1327) with a condition-based wait that polls for the chat list element (`com.whatsapp:id/conversations_row_contact_name`) to appear
- R4. Keep the wireless vs USB distinction as a timeout ceiling (wireless gets a higher ceiling), not as the sleep duration

**Post-force-stop delay**
- R5. Reduce the 0.5s `time.sleep()` after `force-stop` (line 1311) to a fixed 0.2s delay. ADB `force-stop` is synchronous and completes before returning; 0.5s is overly conservative.

## Success Criteria

- Discovery phase completes measurably faster on both USB and wireless connections
- No increase in flakiness — smart waits use timeout ceilings, not aggressive polling
- All existing unit and integration tests pass

## Scope Boundaries

- Only `whatsapp_driver.py` discovery methods (`collect_all_chats`, `restart_app_to_top`)
- No changes to export steps (already optimized in PR #11)
- No changes to `_find_chat_with_scrolling` (used during export, not discovery)
- No new CLI flags

## Key Decisions

- **Same pattern as PR #11**: Use `TimeoutConfig` ceilings + element presence checks, not new waiting mechanisms. Wire `TimeoutConfig` into `whatsapp_driver.py` by importing `get_timeout_config()` directly (the file currently has no `TimeoutConfig` reference — it uses `self.default_wait_timeout`).
- **Reduce post-force-stop to 0.2s**: ADB `force-stop` is synchronous; 0.5s was overly conservative. The subsequent app launch and R3 polling loop provide a safety net if 0.2s proves insufficient on any device.

## Outstanding Questions

### Resolved

- [Affects R3] `verify_whatsapp_is_open()` already checks for `conversations_row_contact_name` (line 1189). Replace the sleep+verify sequence with a polling loop that retries `verify_whatsapp_is_open()` at short intervals up to a TimeoutConfig ceiling.

### Deferred to Planning

- [Affects R1][Needs research] What's the right condition for "scroll settled"? Options: (a) compare element count before/after, (b) wait for any `conversations_row_contact_name` element to be present, (c) check that element positions have stabilized

## Next Steps

→ `/ce:plan` for structured implementation planning

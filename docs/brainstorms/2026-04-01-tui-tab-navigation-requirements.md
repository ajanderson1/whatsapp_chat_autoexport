---
date: 2026-04-01
topic: tui-tab-navigation
---

# TUI Tab Navigation

## Problem Frame

The current TUI uses a linear screen-stack model: `DiscoveryScreen` handles connect + chat discovery, then transitions to `SelectionScreen` which manages 4 internal modes (select/export/processing/complete) via a single reactive `_mode` property. The `PipelineHeader` widget shows 4 stages but they're cosmetic indicators, not navigable sections. Users can't jump between workflow phases, can't review earlier stages, and the "Discover Messages" / "Select Messages" stages are artificially split when they're really one activity. The result is a rigid forward-only flow that doesn't match how users actually want to interact with a multi-phase tool.

```
Current Architecture (2 screens, 4 cosmetic stages):

┌─────────────────────┐      ┌─────────────────────────────────────┐
│   DiscoveryScreen   │─────▶│          SelectionScreen            │
│                     │      │  _mode: select → export →           │
│ • Device scan       │      │          processing → complete      │
│ • Wireless ADB      │      │                                     │
│ • Chat discovery    │      │  (no back navigation once in        │
│                     │      │   export/processing/complete)       │
└─────────────────────┘      └─────────────────────────────────────┘

Proposed Architecture (1 screen, 4 navigable tabs):

┌──────────────────────────────────────────────────────────┐
│  [1 Connect]  [2 Discover & Select]  [3 Export]  [4 Summary]  │
│   ●  active     ○  locked             ○  locked   ○  locked   │
├──────────────────────────────────────────────────────────┤
│                                                          │
│              Tab content area                             │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## Requirements

**Tab Structure & Navigation**

- R1. The TUI has exactly four tabs: **Connect**, **Discover & Select**, **Export**, **Summary**. These replace the current `PipelineHeader` stages and the two-screen model.
- R2. Tabs are navigable by mouse click and by number hotkeys `1`-`4`. Locked tabs ignore input (click and hotkey both no-op).
- R3. Tabs unlock progressively: Connect is always available. Discover & Select unlocks after successful device connection. Export unlocks after at least one chat is selected. Summary unlocks after export completes (success or partial failure).

**Tab Behavior & State**

- R4. After successful device connection, the TUI auto-advances to the Discover & Select tab.
- R5. Background work continues regardless of which tab is focused. Navigating away from the Export tab does not pause or interrupt the export. Navigating back shows current progress.
- R6. Each tab retains its state when navigated away from and back to. The Connect tab shows connection status, Discover & Select shows current selections, Export shows live or completed progress, Summary shows results.

**Visual States & Indicators**

- R7. Tabs display three visual states: **active** (currently focused), **unlocked** (reachable but not focused), **locked** (not yet available, visually dimmed, non-interactive).
- R8. *(Nice-to-have)* A tab that has background activity (e.g., Export running) shows a subtle indicator (e.g., spinner or dot) even when not focused, so the user knows work is happening. Lower priority than R1-R7 and R9-R12; defer if implementation budget is tight.

**Content Migration (Screen -> Tab)**

- R9. The Connect tab contains the current `DiscoveryScreen` device scan, wireless ADB pairing, and connection UI — but NOT chat discovery. Chat discovery moves to the Discover & Select tab.
- R10. The Discover & Select tab combines chat discovery (currently part of `DiscoveryScreen`) with chat selection and settings (currently `SelectionScreen` in "select" mode). Discovery runs automatically when the tab is first reached.
- R11. The Export tab contains the per-chat export progress display (currently `SelectionScreen` in "export" mode), including pause/resume and cancel controls.
- R12. The Summary tab contains processing progress (download, extract, transcribe, organize) and completion results (currently `SelectionScreen` in "processing" and "complete" modes).

## Success Criteria

- Users can navigate between unlocked tabs freely using mouse or hotkeys 1-4
- Auto-advance to Discover & Select tab works after connection
- Export continues running when user navigates to a different tab
- All current TUI functionality is preserved (no feature regression)
- Existing unit and integration tests pass or are updated to match new structure

## Scope Boundaries

- Not changing the underlying export/pipeline logic — only the TUI navigation model
- Not adding new export features or pipeline capabilities
- Not redesigning individual tab content (widget layout within each tab stays similar to current)
- Not changing headless mode or CLI flags — this is TUI-only
- Not changing the modal overlays (help, cancel, secret settings) — they continue to work as overlays on top of whatever tab is active

## Key Decisions

- **Tabs over screens**: Textual's `TabbedContent` (or custom tab bar + `ContentSwitcher`) replaces the screen-stack model. All tabs live in a single screen, avoiding push/pop overhead and enabling persistent state.
- **Number hotkeys 1-4**: Simple, positional, no conflicts with existing bindings (A/N/I for selection, P for pause, etc.).
- **Merge Discover + Select**: These are one logical activity ("figure out what to export"). Splitting them created an unnecessary stage boundary.
- **Background export with free navigation**: Users shouldn't be locked to the Export tab while waiting. This matches expectations from modern multi-tab interfaces.

## Dependencies / Assumptions

- Textual's `TabbedContent` or `ContentSwitcher` widget supports the locking/unlocking behavior, or it can be implemented with a custom tab bar widget
- The current `Worker` pattern for background export/processing is compatible with tab switching (workers run on the app, not on a specific screen)

## Outstanding Questions

### Deferred to Planning

- [Affects R1][Technical] Should we use Textual's built-in `TabbedContent` widget or build a custom tab bar + `ContentSwitcher`? `TabbedContent` may not support locked/dimmed tabs natively.
- [Affects R9-R12][Needs research] What is the cleanest refactoring path from 2 screens → 1 screen with 4 tab panes? Can the existing screen classes be converted to container widgets, or do they need rewriting?
- [Affects R5][Technical] Verify that Textual workers attached to the app (not a screen) continue running when tab content is hidden. This is expected but should be confirmed.
- [Affects R8][Technical] Best approach for the background-activity indicator on unfocused tabs — CSS animation, reactive property watcher, or timer-based update?

## Next Steps

-> `/ce:plan` for structured implementation planning

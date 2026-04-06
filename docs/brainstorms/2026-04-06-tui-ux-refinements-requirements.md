---
date: 2026-04-06
topic: tui-ux-refinements
---

# TUI UX Refinements

## Problem Frame

After the tab navigation refactor (PR #15), the TUI has 4 tabs but the workflow timing is off. Chat discovery lives entirely in Tab 2 and only starts when the user navigates there — but discovery should be auto-triggered by connection and its results should stream into the selection list in real time. Additionally, the "Discover & Select" tab name is now misleading since discovery will be auto-triggered, and the Summary tab lacks a cancel button for the processing pipeline.

## Requirements

**Discovery & Connection Flow**

- R1. On successful device connection (Tab 1), chat discovery starts automatically in the background and the TUI immediately advances to Tab 2.
- R2. Discovered chat names stream into Tab 2's chat list in real time as they are found. The list is interactive during discovery — the user can select/deselect chats while discovery is still running.
- R3. The "Refresh Chats" button remains on Tab 2 (Select) for re-running discovery after the initial auto-scan.

**Export Initiation**

- R4. When the user clicks "Start Export" on Tab 2, the discovery worker is cancelled if still running. Chats already discovered and visible in the list are preserved; only the currently selected subset is exported.
- R5. Export starts and the TUI advances to Tab 3 (Export). Export continues running in the background regardless of which tab the user navigates to (existing behavior, no change).

**Auto-Advance**

- R6. On export completion (success or partial failure, not cancellation), the TUI auto-advances to Tab 4 (Summary) and pipeline processing begins automatically (existing behavior, no change needed).
- R7. If the user cancels mid-export, the TUI returns to Tab 2 (Select) for re-selection (existing behavior, no change needed).

**Summary Cancel**

- R8. Tab 4 (Summary) has a visible Cancel button that stops the processing pipeline (download/extract/transcribe/organize).
- R9. After cancellation, the user stays on Tab 4 and sees partial results for whatever pipeline phases completed before cancellation.

**Tab Renaming**

- R10. Tab labels change from "1 Connect / 2 Discover & Select / 3 Export / 4 Summary" to "1 Connect / 2 Select / 3 Export / 4 Summary". Hotkeys 1-4 remain unchanged.

## Success Criteria

- Discovery begins automatically on connection without user action
- Chat names appear one-by-one in Tab 2 as they are discovered
- User can start export before discovery finishes
- Summary tab has a working cancel button that stops pipeline processing
- All existing functionality preserved (no regression)

## Scope Boundaries

- Not changing the 4-tab structure or navigation model
- Not changing export logic, pipeline logic, or Appium automation
- Not changing headless mode or CLI flags
- Not redesigning widget layouts within tabs (minimal UI changes)

## Key Decisions

- **Discovery triggered from Tab 1, results shown in Tab 2**: Separates the "trigger" (connection event) from the "display" (streaming list). Discovery is a side-effect of connecting, not a separate user action.
- **Stop discovery on export start**: Avoids confusion about new chats appearing after export begins. Clean cut-off point.
- **Cancel on Summary stays on Summary**: User wants to see partial results, not be bounced to another tab.
- **Tab rename "Discover & Select" → "Select"**: Since discovery is auto-triggered, the tab's primary purpose is selection.

## Dependencies / Assumptions

- The existing `_collect_chats` worker and live callback pattern in DiscoverSelectPane can be triggered from ConnectPane's connection handler via message passing
- Textual workers attached to the app continue running across tab switches (already verified in PR #15)

## Outstanding Questions

### Deferred to Planning

- [Affects R1, R2][Technical] Best approach for triggering discovery from ConnectPane while streaming results into the Select pane — message-based handoff, shared app-level state, or worker ownership change?
- [Affects R8][Technical] How to cleanly cancel a running pipeline worker and capture partial results for display.

## Next Steps

-> `/ce:plan` for structured implementation planning

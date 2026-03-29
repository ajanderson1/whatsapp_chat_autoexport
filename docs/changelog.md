# Changelog

## [Unreleased]

### Changed - Google Drive Selection Flow

Modified the Google Drive upload flow to select "Drive" instead of "My Drive" directly, and added support for clicking the "Upload" button in the subsequent Google Drive window.

**Changes:**

1. **Drive Selection**: Changed primary search target from "My Drive" to "Drive" with swipe-up functionality if not immediately visible. Kept "My Drive" as fallback.
2. **Window Transition Detection**: Added logic to detect when Google Drive window appears after clicking "Drive".
3. **Upload Button Selection**: Added new step to find and click the "Upload" button using multiple search strategies.

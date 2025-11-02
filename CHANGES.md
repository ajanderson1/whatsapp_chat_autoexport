# Changelog

## [Unreleased]

### Changed - Google Drive Selection Flow

**Date**: Current implementation

**Summary**: Modified the Google Drive upload flow to select "Drive" instead of "My Drive" directly, and added support for clicking the "Upload" button in the subsequent Google Drive window.

**Changes**:

1. **STEP 5 - Drive Selection** (`whatsapp_export.py`):
   - Changed primary search target from "My Drive" to "Drive"
   - Added swipe-up functionality: If "Drive" option is not immediately visible, the script will swipe up from the bottom of the screen (up to 3 attempts) to make it visible
   - Swipe pattern: Swipes from 85% of screen height to 35% of screen height
   - Kept "My Drive" as a fallback option for backward compatibility
   - Updated logging messages to reflect "Drive" selection

2. **Window Transition Detection** (`whatsapp_export.py`):
   - Added logic to detect when Google Drive window appears after clicking "Drive"
   - Checks for package/activity changes to confirm transition to Google Drive app
   - Includes debug logging for troubleshooting window transitions

3. **STEP 6 - Upload Button Selection** (`whatsapp_export.py`):
   - Added new step to find and click the "Upload" button in the top right of the Google Drive window
   - Implemented multiple search strategies:
     - **Strategy 1**: Search by resource ID `com.google.android.apps.docs:id/save_button` (most reliable)
     - **Strategy 2**: Search Button elements by text "Upload" in top right area
     - **Strategy 3**: Search TextView elements in top right area and find parent Button
     - **Strategy 4**: Search clickable containers for "Upload" text
     - **Strategy 5**: Fallback - find any Button with "Upload" text regardless of position
   - Updated verification logic to check Button's own text attribute first (not just TextView children)
   - Added trust mechanism for buttons found by resource ID

**Technical Details**:
- Top right area definition: rightmost 30% of screen width, top 15% of screen height
- Swipe duration: 300ms
- Maximum swipe attempts: 3
- Error handling includes debug XML dumps for troubleshooting

**Known Limitations**:
- ⚠️ **UNTESTED**: The swipe-up functionality to reveal "Drive" when it's initially not visible has not been tested. The implementation follows the same swipe patterns used elsewhere in the codebase, but should be verified in scenarios where:
  - "Drive" option is below the visible area of the share dialog
  - Multiple swipes are required to reveal "Drive"
  - Different screen sizes/resolutions affect swipe behavior

**Related Files**:
- `whatsapp_export.py` - Main export automation script

**Testing Recommendations**:
- Test with "Drive" option visible without swiping
- Test with "Drive" option requiring 1 swipe
- Test with "Drive" option requiring 2-3 swipes
- Test on different Android device screen sizes
- Verify Upload button detection in Google Drive window
- Test error handling when Upload button cannot be found


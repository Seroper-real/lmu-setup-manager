
# Project Tasks: Settings Workflow Fixes

- [x]  **Fix: Settings State Persistence & Dirty Checking**

  - **Description:** Resolve issues in the settings save/discard workflow.
  - **Tasks:**
    - **Fix Revert Logic:** Ensure that clicking "Discard Changes" correctly fetches and restores the previous values stored in the DB.
    - **Fix Dirty Checking:** Prevent the "unsaved changes" confirmation dialog from appearing if the user has already saved the changes and no further edits have been made.
    - **UX Layout:** Reposition the "Discard" (Annulla) button to the far left; keep the "Save" and other confirmation buttons on the right side.
- [x]  **UI Update: Visibility Toggle Placement**

  - **Description:** Reorganize the "Show/Hide" value buttons in the settings interface.
  - **Tasks:**
    - **Remove:** Delete the global visibility button currently located at the top.
    - **Add:** Place a specific visibility toggle button to the left of the "Token TrackTitan" field.
    - **Add:** Place a specific visibility toggle button to the left of the "Credenziali Dropbox" field.

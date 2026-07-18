
# Project Tasks: Settings & UI Workflow

- [ ]  **Rename Application Modes (GUI & Documentation)**

  - **Description:** Update all occurrences of the application's primary modes in the user interface and documentation (README.md).
  - **Mapping:**
    - `Full` → **"Diretta"**
    - `Master` → **"Solo Upload"**
    - `Slave` → **"Solo installazione"**
  - **Scope:** Ensure consistency across menus, settings, tooltips, and documentation.
- [ ]  **UI Update: Refine Help Label**

  - **Description:** Rename the label `"non sai come recuperarli? Guarda qui."` to **"Guida alla compilazione"** for a more professional tone.
- [ ]  **UI Update: Default Settings Configuration**

  - **Description:** Set the following settings to be checked (flagged) by default:
    - "Elimina la versione precedente del setup"
    - "Elimina file scaricati dopo la copia"
- [ ]  **UI Update: Tooltip Styling & Consistency**

  - **Description:** Fix visual issues in tooltip components.
  - **Tasks:**
    - Resolve text overflow issues in advanced settings tooltips to ensure text stays within the box.
    - Standardize the "delete" tooltip for installed setups to match the design and format of the other application tooltips.
- [ ]  **UI Extension: Universal Copy Button**

  - **Description:** Add a "Copy" button to every input field within the settings menu for standardized access.
- [ ]  **Refactor Settings Save Workflow**

  - **Description:** Optimize the settings saving process to improve UX.
  - **Task:**
    - Remove the manual "Save" button from the settings page.
    - **Auto-save:** Trigger automatic saving specifically after the automatic token retrieval process.
    - **Unsaved Changes Prompt:** Implement a confirmation dialog that triggers when the user attempts to navigate away from the settings screen or close the application, asking if they wish to save pending changes.

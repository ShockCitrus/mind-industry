# Detection View Refactoring Implementation Guide

## Overview

This guide provides a complete specification for refactoring the detection page and its JavaScript logic. The page currently has two distinct states (topic selection and results display) packed unstructurally into a single `detection.html` (659 lines) backed by a single `detection.js` (1,483 lines), causing visual bugs, functional complexity, and excessive coupling between the D3 scatterplot, the DataTables library, the Docs pagination module, and the pipeline control flow.

**Core philosophy: Simplicity, clarity, both in design and code.**

### What is being REPLACED

| Current Element | Problem | Replacement |
| :--- | :--- | :--- |
| D3.js SVG scatter plot ("Visual" mode, L184-185 in `detection.html`) | External dependency, complex coordinate math, buggy interactions | Removed entirely |
| "Visual / Text / Docs" 3-mode toggle button group (L37-46) | Confusing multi-mode navigation, inconsistent UX | Removed entirely |
| Docs lang1/lang2 paginated panels (L187-221) | Rarely used, adds > 800 lines of JS, Chart.js dependency | Removed entirely |
| D3.js CDN script (L649) | No longer needed | Removed |
| Chart.js CDN script (L646) | No longer needed | Removed |
| `drawTopicVis()` (detection.js L238-368) | ~130 lines of D3 code | Deleted |
| `initTopicViewToggle()` (detection.js L370-454) | ~85 lines of view-switching logic | Deleted |
| `DocsPagination` module (detection.js L28-236) | ~200 lines of pagination, per-doc charts | Deleted |

### What is being KEPT (logic is preserved, not rewritten from scratch)

| Current Element | Notes |
| :--- | :--- |
| Dataset + TM selection accordion (state 1) | Good structure, keep as-is |
| Topic list accordion with checkboxes (text-mode, L226-264) | **This becomes the only/primary topic view** |
| Pipeline action bar (Sample Size + Analyze + Check Status, L440-473) | Keep, with minor simplification |
| Config Pipeline modal (LLM type/model/method/weighting, L475-580) | Keep as-is |
| Log/Status modal (L584-600) | Keep as-is |
| Results DataTable with column filter + label filter bar | Keep as-is |
| XLSX export | Keep as-is |
| `MINDInterface` class and its `handleInstruction()` / `handleDatasetSelection()` | Keep, simplify topic collection |
| Backend routes in `views.py` & `backend/detection.py` | **No backend changes required** |

---

## Implementation Steps

| Step | Description | Target Files | Completed |
| :--- | :--- | :--- | :---: |
| **1. Template Restructure** | Remove the 3-mode toggle, D3 container, and Docs panels from `detection.html`. Promote text-mode topic list to be the sole topic view. | `detection.html` | [ ] |
| **2. Add "Select All" Topics Toggle** | Add a "Select All / Deselect All" button above the topic accordion. | `detection.html` | [ ] |
| **3. Add Inline Help Text** | Add a concise description banner at the top of the topic view to guide the user. Replace the `#infoModal` with simpler inline copy. | `detection.html` | [ ] |
| **4. JS Modularization** | Split `detection.js` into two focused files: `detection-config.js` (pipeline control) and `detection-table.js` (results DataTable). Remove D3, Chart.js, and Docs-related code. | `detection.js` → 2 new files | [ ] |
| **5. Update Topic Selection Logic** | In the refactored JS, topic selection always reads from checkboxes (removing the `window.currentView` branch). Adjust the "Analyze" button handler accordingly. | new `detection-config.js` | [ ] |
| **6. Update `detection.html` Script Tags** | Replace the single `detection.js` `<script>` tag with the two new file references. Remove D3, Chart.js CDN tags. | `detection.html` | [ ] |
| **7. Apply Sister-View Visual Styling** | Align spacing, card styles, and typography with `datasets.html` and `detection_results.html`. Remove the `height: 60vh; overflow: hidden` jumbotron tricks. | `detection.html`, `detection.css` | [ ] |
| **8. Functional Smoke Test** | Manually run through both the topic selection flow and the results display in the browser. | Browser | [ ] |

---

## Detailed Implementation Steps

### Step 1: Template Restructure (`detection.html`)

#### Current 3-State Structure

The template switches between three states based on Jinja template context variables:

```
State A: dataset_detection is truthy  → Show Dataset + TM accordion selector
State B: topic_keys is truthy         → Show topic picker + action bar
State C: status == 'completed'        → Show results DataTable
```

This structure is correct and must be **preserved**. The refactoring only touches **State B**.

#### Deletions

Inside the `{% elif topic_keys %}` block (lines 182-264 in current `detection.html`):

1. **Delete** the entire Visual container:
   ```html
   <!-- DELETE THIS BLOCK: Option 1: Visual -->
   <div id="topicVis" style="..."></div>
   ```

2. **Delete** both Docs panels:
   ```html
   <!-- DELETE THIS BLOCK: Option 3: Docs lang1 -->
   <div id="topicDocs1" ...> ... </div>
   <!-- DELETE THIS BLOCK: Option 4: Docs lang2 -->
   <div id="topicDocs2" ...> ... </div>
   ```

3. **Delete** the Visual/Text/Docs toggle button group (lines 37-46):
   ```html
   <!-- DELETE THIS BLOCK -->
   <div class="btn-group" role="group" aria-label="Visual/Text toggle">
       <button ... id="btn-visual">Visual</button>
       <button ... id="btn-text">Text</button>
       {% if docs_data_1 %}<button ... id="btn-docs1">Docs {{ lang_1 }}</button>{% endif %}
       {% if docs_data_2 %}<button ... id="btn-docs2">Docs {{ lang_2 }}</button>{% endif %}
   </div>
   ```

4. **Delete** the `#infoModal` (lines 49-113). It references the removed modes and adds confusion.

5. **Remove** the `display: none;` inline style from the topic accordion div (line 224, `style="display: none; ..."`):
   ```html
   <!-- BEFORE (currently hidden because text mode was non-default) -->
   <div class="topic-accordion" style="display: none; height: 100%; ...">

   <!-- AFTER: Make it visible and remove the fixed-height jumbotron constraint -->
   <div class="topic-accordion" style="overflow-y: auto;">
   ```

6. **Delete** the data bridge blocks for Docs data (lines 612-615), as they are no longer needed:
   ```html
   <!-- DELETE these two data bridge blocks -->
   {% if docs_data_1 %}<script ... id="__data_docsData1">...</script>{% endif %}
   {% if docs_data_2 %}<script ... id="__data_docsData2">...</script>{% endif %}
   ```
   Also remove the corresponding `docsData1` and `docsData2` keys from `window.__DETECTION_DATA` (lines 633-634).

#### Simplify the Header

The header for the topic view (lines 23-35) can be simplified. Keep the h3 title with the TM name and the CSRF attribute, but remove the circular info button that opened the deleted modal.

```html
<!-- SIMPLIFIED HEADER for State B -->
<div class="d-flex justify-content-between align-items-center mb-3">
    <div>
        <h3 class="mb-0" id="TopicModel-h3" TM-name="{{ topic_keys['topics'][0]['TM_name'] }}">
            Topic Model: "{{ topic_keys['topics'][0]['TM_name'] }}"
        </h3>
        <p class="text-muted mb-0 small">Select one or more topics below, then configure and run the discrepancy analysis.</p>
    </div>
</div>
```

---

### Step 2: Add "Select All" Topics Toggle

Immediately **above** the `<div class="topic-accordion">`, insert a simple button bar:

```html
<!-- INSERT ABOVE the topic-accordion div -->
<div class="d-flex align-items-center gap-3 mb-3 pb-2 border-bottom">
    <button type="button" class="btn btn-sm btn-outline-secondary" id="selectAllTopicsBtn">
        <i class="ph ph-check-square me-1"></i> Select All
    </button>
    <button type="button" class="btn btn-sm btn-outline-secondary" id="deselectAllTopicsBtn">
        <i class="ph ph-square me-1"></i> Deselect All
    </button>
    <span class="text-muted small ms-auto" id="topicSelectionCount">0 topics selected</span>
</div>
```

This replaces the complexity of the D3 click-selection-region drag behavior with a single, understandable UI pattern.

---

### Step 3: Add Inline Help Text (Replace Info Modal)

Add a compact `alert` or styled card at the top of **State B** (below the header, above the select-all bar) to give context. This replaces the old `#infoModal` popup:

```html
<!-- INSERT between the header and the select-all bar -->
<div class="alert alert-info d-flex align-items-start gap-2 py-2 px-3 mb-3" role="alert" style="font-size: 0.875rem;">
    <i class="ph ph-info fs-5 mt-1 flex-shrink-0"></i>
    <div>
        <strong>How to use:</strong> Select the topics you want to analyze using the checkboxes below.
        Use <em>Configure Pipeline</em> to review LLM and method settings, then click <em>Analyze Discrepancies</em>.
        Results open automatically when the analysis completes.
        <strong class="text-danger">Do not leave this page while the analysis is running.</strong>
    </div>
</div>
```

> [!NOTE]
> The `<i class="ph ph-info">` icon uses the Phosphor icon set, which is already available in `base.html` via the existing CDN import. No new dependencies are needed.

---

### Step 4: JS Modularization

The current `detection.js` (1,483 lines) must be split into two focused files:

#### New file: `detection-config.js`

**Responsibilities:** Topic selection control, "Select All"/"Deselect All", pipeline submission, LLM config toggle, model selector, pipeline polling, exit warning, SSE log streaming, accordion toggle.

**Sections to MOVE from `detection.js`:**

| Section | Lines in current `detection.js` | Destination |
| :--- | :--- | :--- |
| `showOverlay()`, `hideOverlay()` | L8-17 | `detection-config.js` |
| `initExitWarning()` | L459-500 | `detection-config.js` |
| `initLLMConfigToggle()` | L1048-1082 | `detection-config.js` |
| `initModelSelector()` | L1084-1108 | `detection-config.js` |
| `initLogStreaming()` | L1110-1132 | `detection-config.js` |
| `initAccordionToggle()` | L1134-1162 | `detection-config.js` |
| `startPipelinePolling()` | L1164-1192 | `detection-config.js` |
| `MINDInterface` class | L1194-1401 | `detection-config.js` |
| `DOMContentLoaded` init block | L1424-1482 | Split between both files |

**New functions to ADD to `detection-config.js`:**

```javascript
/* ---------- Select All / Deselect All ---------- */
function initTopicSelectionControls() {
    const selectAllBtn = document.getElementById('selectAllTopicsBtn');
    const deselectAllBtn = document.getElementById('deselectAllTopicsBtn');
    const countEl = document.getElementById('topicSelectionCount');

    function updateCount() {
        const checked = document.querySelectorAll('.topic-checkbox:checked').length;
        if (countEl) countEl.textContent = `${checked} topic${checked !== 1 ? 's' : ''} selected`;
    }

    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', () => {
            document.querySelectorAll('.topic-checkbox').forEach(cb => cb.checked = true);
            updateCount();
        });
    }
    if (deselectAllBtn) {
        deselectAllBtn.addEventListener('click', () => {
            document.querySelectorAll('.topic-checkbox').forEach(cb => cb.checked = false);
            updateCount();
        });
    }

    // Keep count in sync when individual checkboxes are clicked
    document.querySelectorAll('.topic-checkbox').forEach(cb => {
        cb.addEventListener('change', updateCount);
    });
    updateCount(); // Initialize count on load
}
```

#### New file: `detection-table.js`

**Responsibilities:** Results DataTable initialization, label filter bar, column visibility, XLSX export, range selector, chunk loading.

**Sections to MOVE from `detection.js`:**

| Section | Lines in current `detection.js` | Destination |
| :--- | :--- | :--- |
| `generateColors()` | L19-27 | `detection-table.js` |
| `updateColors()` | L502-533 | `detection-table.js` |
| `initDefaultColumnVisibility()` | L535-547 | `detection-table.js` |
| `initResultsDataTable()` | L549-755 | `detection-table.js` |
| `initLabelFilterBar()` | L757-822 | `detection-table.js` |
| `loadChunk()` | L824-875 | `detection-table.js` |
| `initRangeSelector()` | L877-884 | `detection-table.js` |
| `initDatatableLayout()` | L886-923 | `detection-table.js` |
| `initXlsxExport()` | L925-1046 | `detection-table.js` |

**Sections to DELETE entirely (do not move):**

| Section | Lines | Reason |
| :--- | :--- | :--- |
| `drawTopicVis()` | L238-368 | Replaces D3 visualization — removed |
| `initTopicViewToggle()` | L370-454 | Removed with the 3-mode toggle |
| `DocsPagination` module | L28-236 | Docs panels removed |
| `initDocModal()` | L1403-1422 | Doc modal was only used by Docs panels |

#### `DOMContentLoaded` init in each new file

**`detection-config.js` init block** (runs when topic view is active):
```javascript
document.addEventListener("DOMContentLoaded", function () {
    const DATA = window.__DETECTION_DATA || {};

    initExitWarning();
    initAccordionToggle();
    initTopicSelectionControls(); // NEW

    if (DATA.availableModels) {
        initModelSelector();
        initLLMConfigToggle();
        initLogStreaming();
    }

    if (DATA.csrfToken) {
        document.cookie = "csrf_token=" + DATA.csrfToken;
    }

    const mindInterface = new MINDInterface();
});
```

**`detection-table.js` init block** (runs when results view is active):
```javascript
document.addEventListener("DOMContentLoaded", function () {
    const DATA = window.__DETECTION_DATA || {};

    initExitWarning(); // Keep here too, in case user navigates from results back

    if (DATA.columnsJson) {
        initDefaultColumnVisibility();
        initResultsDataTable();
        initDatatableLayout();
        initXlsxExport();
        initRangeSelector();

        const rangeSelector = document.getElementById("rangeSelector");
        if (rangeSelector) {
            hideOverlay();
            loadChunk(rangeSelector.value);
        }
    }
});
```

> [!IMPORTANT]
> `showOverlay()` / `hideOverlay()` are used in both files. Either: (a) define them in both files independently (they are short, 5 lines each), or (b) create a tiny shared `detection-utils.js` with only those two functions and `generateColors()`. Option (a) is simpler and avoids an additional HTTP request.

---

### Step 5: Update Topic Selection Logic in `MINDInterface`

The current `MINDInterface.initEventListeners()` in `detection.js` (L1238-1311) branches on `window.currentView`:

```javascript
// CURRENT CODE — reading view state to decide where to get topics
if (window.currentView === "visual") {
    selected = window.currentVisibleTopics;  // D3 reference
} else if (window.currentView === "text") {
    const checkboxes = document.querySelectorAll('.topic-checkbox');
    selected = Array.from(checkboxes).filter(cb => cb.checked).map(cb => cb.value);
} else {
    showToast("Choose Topics in Option Visual or Text.");
    return;
}
```

In the refactored `detection-config.js`, replace this block with the simple, direct version:

```javascript
// NEW CODE — always read from checkboxes (only view after refactor)
const checkboxes = document.querySelectorAll('.topic-checkbox');
const selected = Array.from(checkboxes).filter(cb => cb.checked).map(cb => cb.value);

if (selected.length < 1) {
    showToast('Select at least 1 topic.');
    return;
}
```

Everything else in `MINDInterface` (CSRF, config payload assembly, `handleInstruction()`, polling) stays exactly the same.

---

### Step 6: Update `detection.html` Script Tags

Replace the current CDN scripts block and the single `detection.js` `<script>` tag (lines 644-656 in current `detection.html`):

```html
<!-- BEFORE -->
{% if docs_data_1 or docs_data_2 %}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
{% endif %}
{% if topic_keys %}
<script src="https://d3js.org/d3.v7.min.js"></script>
{% endif %}
{% if result_mind and result_columns %}
<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
{% endif %}

<script src="{{ url_for('static', filename='js/detection.js') }}"></script>
```

```html
<!-- AFTER -->
{% if result_mind and result_columns %}
<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
{% endif %}

{% if topic_keys %}
<script src="{{ url_for('static', filename='js/detection-config.js') }}"></script>
{% endif %}
{% if result_mind and result_columns %}
<script src="{{ url_for('static', filename='js/detection-table.js') }}"></script>
{% endif %}
```

Load `detection-table.js` only when results are present (State C). Load `detection-config.js` only when the topic view is present (State B). This avoids loading unused code.

> [!NOTE]
> D3 and Chart.js CDN imports are **fully removed**. Neither is needed after the refactor.

---

### Step 7: Apply Sister-View Visual Styling

#### Remove the Jumbotron Height Hack

The current `detection.html` uses:
```html
<div class="jumbotron" id='jumbotron-detection' style="height: 60vh; overflow: hidden; padding: 2rem;">
```

This forces the topic list into a fixed-height scrollable box, which causes visual glitches. Remove the fixed height and overflow constraints:

```html
<!-- SIMPLIFIED: let the page expand naturally -->
<div id="detection-main-content" style="padding: 0;">
```

The JS in `initDatatableLayout()` also manually adjusts `jumbotron-detection` styles. Remove the `jumbotron` ID from that too.

#### Card Styling Reference (from `datasets.html`)

The sister view `datasets.html` uses Bootstrap 5 cards cleanly:
- Wrapper: `<div class="card">` with no extra styles
- Header: `<div class="card-header d-flex align-items-center justify-content-between">`
- Body: `<div class="card-body">`

The topic accordion cards in `detection.html` already use `class="topic-group mb-3 card border-0 shadow-sm"` which closely matches. **Keep these classes, only remove the `border-0` if you want a visible border like in `datasets.html`.**

#### Typography and Spacing Reference

From `datasets.html`:
- Page title: `<h1 class="mt-4">` 
- Lead paragraph: `<p>Check below...</p>` (no `class="lead"`, just a plain `<p>`)
- Section headers: `<h2 class="mt-4">`

The detection page currently uses `<h1>` only in State A. In State B, use `<h3>` for the TM name (already done). Ensure the help text paragraph uses `class="text-muted small"` or similar.

#### `detection.css` — Rules to Remove

After removing D3 and the Docs panels, search `detection.css` for and remove any rules targeting selectors that no longer exist:
- `#topicVis` — the D3 SVG container
- `#topicDocs1`, `#topicDocs2` — Docs panel containers
- `#btn-visual`, `#btn-text`, `#btn-docs1`, `#btn-docs2` — the removed toggle buttons
- Any `.node`, `.link`, or other D3-specific selectors

---

### Step 8: Functional Smoke Test (Manual)

No automated tests exist for the frontend. Manual verification is the required approach.

#### Test Flow A: Topic Selection → Pipeline Run

1. Log in and navigate to `/detection`.
2. Click on a Dataset to expand it, click on a Topic Model.
3. **Verify:** Page reloads showing only the topic accordion list (no D3 canvas, no Visual/Text buttons).
4. **Verify:** A help text banner with instructions is visible above the topic list.
5. Click "Select All". **Verify:** All topic checkboxes become checked; count badge updates.
6. Click "Deselect All". **Verify:** All checkboxes uncheck; count shows `0 topics selected`.
7. Manually check 2 topics using checkboxes.
8. Click "Configure Pipeline" and change the LLM type to Gemini; verify the LLM model dropdown appears. Close modal.
9. Set Sample Size to 3. Click "Analyze Discrepancies".
10. **Verify:** Button shows spinner and becomes disabled.
11. **Verify:** No console errors referencing D3, `drawTopicVis`, or `currentView`.
12. Click "Check Status". **Verify:** Log modal opens and shows streaming log output.
13. Wait for completion. **Verify:** Page redirects to `/detection_results?TM=...&topics=...`.

#### Test Flow B: Results Display

1. Navigate to a completed detection result via `/detection_results?TM=...&topics=...`.
2. **Verify:** Results DataTable loads correctly with pagination.
3. **Verify:** Label filter bar (CONTRADICTION, NO_DISCREPANCY, etc.) is visible and functional.
4. **Verify:** Column filter dropdown works.
5. Click "Save & Download XLSX". **Verify:** File downloads correctly.
6. Change the range selector. **Verify:** New chunk of results loads.

#### Test Flow C: Regression — State A (Dataset Selection)

1. Navigate to `/detection` (no TM selected).
2. **Verify:** Dataset accordion list renders correctly.
3. **Verify:** No JS errors in the console on page load.

---

## Data Flow Reference (Unchanged by Refactor)

The backend APIs are **not changed**. The refactor only touches the frontend presentation layer.

```
[1] GET /detection
      → views.detection_page() → getTMDatasets()
      → render detection.html (State A: dataset_detection context)

[2] User clicks a TM → POST /detection_topickeys
      → views.detection_page_topickeys_post()
      → getTMkeys() → getModels() → getDocProportion()
      → stores results in Flask session
      → returns { redirect: /detection_topickeys }
      → GET /detection_topickeys → render detection.html (State B: topic_keys context)

[3] User clicks "Analyze Discrepancies" → JS collects:
      topics: "1,3,5"  (comma-separated topic IDs from checkboxes)
      sample_size: 5 or null (if "All" is toggled)
      config: { llm_type, llm, gpt_api, ollama_server, method, do_weighting }
      → POST /mode_selection (views.mode_selection)
      → analyseContradiction(user_id, TM, topics, sample_size, config)
      → POST to backend /detection/analyse_contradiction
      → starts a Python Process (detection.run_pipeline_process)
      → returns { message: "Started" } → 200

[4] JS polls GET /pipeline_status?TM=...&topics=...
      → backend checks if mind_results.parquet exists
      → returns { status: "running" | "finished" | "error" }
      → on "finished": JS redirects to /detection_results?TM=...&topics=...

[5] GET /detection_results → views.detection_results_page()
      → get_result_mind() → GET /detection/result_mind
      → reads mind_results.parquet, returns paginated rows
      → render detection.html (State C: result_mind context)
```

### `config` Payload Schema (Frontend → Backend)

```json
{
  "llm_type": "gemini | ollama | GPT",
  "llm": "<model name string>",
  "gpt_api": "<api key string or empty>",
  "ollama_server": "<server name string or empty>",
  "method": "ENN | ANN | TB-ENN | TB-ANN",
  "do_weighting": true
}
```

Backend handler: `backend/detection.py` `analyse_contradiction()` (L429-563).

---

## File Change Summary

| File | Action | Description |
| :--- | :--- | :--- |
| `app/frontend/templates/detection.html` | Modify | Remove D3 container, Docs panels, 3-mode toggle, info modal. Update script tags. |
| `app/frontend/static/js/detection.js` | Delete | Replaced by two focused files. |
| `app/frontend/static/js/detection-config.js` | Create (NEW) | Pipeline control: topic selection, LLM config, polling, exit warning. |
| `app/frontend/static/js/detection-table.js` | Create (NEW) | Results table: DataTables, filters, XLSX export, chunk loading. |
| `app/frontend/static/css/detection.css` | Modify | Remove D3 and Docs-related CSS rules. |

> [!IMPORTANT]
> **No backend files are changed.** `app/backend/detection.py`, `app/frontend/views.py`, and `app/frontend/detection.py` are all left untouched.

---

## Compatibility with Upcoming Features

This refactoring is designed to be forward-compatible with the planned features documented in their respective implementation guides:

- **Custom Categories** (`custom_categories_implementation_guide.md`): Step 6 of that guide requires replacing the hardcoded label filter buttons in the results DataTable with dynamically generated ones. The refactored `detection-table.js` isolates this logic in `initLabelFilterBar()`, making it straightforward to update.
- **Monolingual Support** (`monolingual_support_implementation_guide.md`): The removal of the `btn-docs2` and `lang_2` references simplifies the conditional rendering already needed for monolingual datasets.
- **Data Erasure** (`data_erasure_implementation_guide.md`): Unaffected — targets the datasets and results list pages, not the detection flow itself.
- **Data Ingestion Abstraction** (`data_ingestion_abstraction_guide.md`): Unaffected — targets the profile upload flow.

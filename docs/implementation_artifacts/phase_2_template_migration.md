# Phase 2: Template Migration

> **Goal**: Update all templates to use Bootstrap 5 / Halfmoon v2 classes while preserving complex custom JavaScript logic.
> **Critical**: Do not break the existing redirect logic or jQuery-dependent plugins (DataTables).

---

## 1. Global Find & Replace

Run these commands in `app/frontend/templates/`:

```bash
# Spacing
sed -i 's/ml-/ms-/g' *.html
sed -i 's/mr-/me-/g' *.html
sed -i 's/pl-/ps-/g' *.html
sed -i 's/pr-/pe-/g' *.html

# Text Alignment
sed -i 's/text-left/text-start/g' *.html
sed -i 's/text-right/text-end/g' *.html

# Bootstrap 5 Attributes
sed -i 's/data-toggle="modal"/data-bs-toggle="modal"/g' *.html
sed -i 's/data-target="#/data-bs-target="#/g' *.html
sed -i 's/data-dismiss="modal"/data-bs-dismiss="modal"/g' *.html
```

> [!WARNING]
> **Check `preprocessing.html` Manually**: The `.details-toggle` elements use a custom `data-target` attribute (not Bootstrap). Verify these were not incorrectly changed to `data-bs-target`. If they were, revert them.

---

## 2. Refactor `detection.html`

### 2.1 Modals
- Ensure all modal triggers use `data-bs-toggle` and `data-bs-target`.
- Update close buttons: `<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>`.

### 2.2 DataTables
- Update CSS link to BS5 version: `<link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/dataTables.bootstrap5.min.css">`
- **Keep jQuery**: DataTables requires it.

### 2.3 Visualizations (D3.js)
- Inspect `#topicVis` container. Ensure it has a defined height (e.g., `height: 600px;`) as BS5 flexbox behavior might differ from BS4.

### 2.4 JavaScript Updates
- **Preserve**: `startPipelinePolling` logic. It uses `window.location.href` for redirects. **Do not change this to HTMX yet.**
- **Update**: Modal events.
  ```javascript
  // Old (BS4/jQuery) - Still works with jQuery, but better to modernize if possible
  $('#logModal').on('shown.bs.modal', function () { ... });
  
  // New (BS5 Vanilla)
  document.getElementById('logModal').addEventListener('shown.bs.modal', function () { ... });
  ```

---

## 3. Refactor `preprocessing.html`

### 3.1 Step Wizard
- **Preserve**: The custom `step-slide` navigation logic (`nextBtn`, `prevBtn`, `showSlide`). This relies on standard DOM manipulation (`style.display`), so it is safe.
- **Update**: Modal attributes for the wrapping `#stepModal`.

### 3.2 Collapse Toggles
- The code uses `$(collapseEl).collapse('show')`.
- **Update**:
  ```javascript
  // Bootstrap 5 API
  const bsCollapse = new bootstrap.Collapse(collapseEl, { toggle: false });
  bsCollapse.show(); // or .hide()
  ```

---

## 4. Refactor `profile.html`

### 4.1 File Upload
- **Preserve**: The `dropZone` drag-and-drop logic. It is standard JS.
- **Update**: Form styling.
  - `form-group` -> `mb-3`
  - `custom-file` -> `form-control` (BS5 file input is simpler).

---

## 5. Refactor `login.html` & `sign_up.html`

- Simple form updates: `form-group` -> `mb-3`, add labels.
- Center the card using Halfmoon/BS5 utilities: `d-flex justify-content-center align-items-center vh-100`.

---

## 6. Verification

- [ ] **Detection**: Config modal opens, pipeline runs, redirects to results.
- [ ] **Preprocessing**: Wizard steps navigate correctly, "Details" toggles work.
- [ ] **Profile**: File drag-and-drop works, form submits.
- [ ] **Visual**: No broken layout due to missing `jumbotron` (replace with `bg-light p-5 rounded`).

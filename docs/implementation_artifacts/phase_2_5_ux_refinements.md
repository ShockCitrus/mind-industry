# Phase 2.5: UX Refinements (Detection Page)

> **Goal**: Fix dark mode visibility issues for cards and improve the ergonomics of the pipeline configuration menu in `detection.html`.
> **Context**: User reported cards are hard to see in dark mode, and the "Sample Size" menu is too small/cramped.

---

## 1. Fix Card Visibility (Dark Mode)

The cards in `detection.html` likely rely on default Bootstrap background transparency or white backgrounds that clash in dark mode.

**Action**: Add `bg-body-secondary` or `bs-card-bg` (from our Design System) to all card containers.

### 1.1 Topic Group Cards (`.topic-group`)
Currently:
```html
<div class="topic-group mb-3 border rounded-2 shadow-sm">
```
Change to:
```html
<div class="topic-group mb-3 card border-0 shadow-sm">
```
*Note: `card` class in Halfmoon/BS5 usually handles dark mode backgrounds better than raw `div`s.*

### 1.2 List Group Items (`.list-group-item`)
The header has `bg-light`:
```html
<div class="dataset-header ... bg-light ...">
```
Change to:
```html
<div class="dataset-header ... bg-body-tertiary ...">
```
*Rationale: `bg-light` is often too bright in dark mode. `bg-body-tertiary` adapts.*

### 1.3 Topic Content List
```html
<ul ... style="background-color: #f8f9fa; ...">
```
**Remove the inline style**. Let the class handle it:
```html
<ul ... class="list-group list-group-flush bg-body-tertiary">
```

---

## 2. Improve Menu Ergonomics

The "Config Pipeline" and "Run Pipeline" menu is currently a `<ul>` with cramped inputs.

**Current State**:
```html
<li class="nav-item d-flex align-items-center">
    <label ...>Sample Size: </label>
    <input ... style="width: 100px;">
    <a ...>Analyze Discrepancies</a>
    <a ...>Check Status</a>
</li>
```

**Refactoring Plan**: Convert this into a **Toolbar** using `btn-group` and `input-group` for a cohesive, larger control surface.

### New Markup (Replace the entire `<ul>` block):

```html
<div class="d-flex flex-wrap align-items-center justify-content-between p-3 mb-4 bg-body-tertiary rounded-3 shadow-sm gap-3">
    
    <!-- Config Trigger -->
    <button type="button" class="btn btn-outline-secondary d-flex align-items-center gap-2" data-bs-toggle="modal" data-bs-target="#configPipelineModalLabel">
        <i class="ph ph-gear"></i>
        <span>Configure Pipeline</span>
    </button>

    <!-- Run Controls -->
    <div class="d-flex align-items-center gap-2">
        <div class="input-group">
            <span class="input-group-text bg-body-secondary border-secondary-subtle">Sample Size</span>
            <input type="number" class="form-control border-secondary-subtle" id="sampleSizeInput" name="n_samples" placeholder="5" value="5" min="1" style="max-width: 80px;">
        </div>

        <button class="btn btn-primary d-flex align-items-center gap-2 mode-selectors" id="analyze_contradictions" data-bs-toggle="tab" data-no-warning>
            <i class="ph ph-play"></i>
            <span>Analyze Discrepancies</span>
        </button>

        <button class="btn btn-outline-info d-flex align-items-center gap-2" data-bs-toggle="modal" data-bs-target="#logModal" data-no-warning>
             <i class="ph ph-terminal-window"></i>
             <span>Check Status</span>
        </button>
    </div>
</div>
```

**Key Improvements**:
1.  **Container**: Wrapped in `bg-body-tertiary rounded-3` (Panel style) instead of a loose tab list.
2.  **Buttons**: Replaced text links (`<a>`) with distinct `<button>` classes (`btn-primary` for action, `btn-outline` for secondary).
3.  **Icons**: Added Phosphor icons (`gear`, `play`, `terminal-window`) for instant recognition.
4.  **Input Group**: "Sample Size" label is now part of the input unit, removing whitespace issues.
5.  **Spacing**: Used `gap-3` and `gap-2` for consistent separation.

---

## 3. Verification

- [x] **Dark Mode**: Cards (topic list) have a dark background (Slate-800 from design system) and readable text.
- [x] **Menu**: The new toolbar renders correctly, buttons are clickable, and the "Sample Size" input works.
- [ ] **Functionality**: Clicking "Analyze" still triggers the JS handler (ensure `#analyze_contradictions` ID is preserved).

# Phase 3: HTMX Cleanup

> **Goal**: Replace manual JavaScript polling and complex `fetch` logic with declarative HTMX attributes.
> **Prerequisite**: Phase 1 and 2 must be complete and stable.

---

## 1. Progress Bar Polling (`base.html`)

**Remove**: The custom `updateProgressBar` function and `setInterval`.
**Add**: HTMX polling to the progress container.

```html
<div id="dynamic-progress-bars"
     hx-get="/progress"
     hx-trigger="every 2s"
     hx-swap="innerHTML">
  <!-- Server returns updated progress bar HTML -->
</div>
```

> **Backend Note**: The `/progress` endpoint currently returns JSON. For HTMX, modify it to return an HTML snippet (e.g., `render_template('partials/progress_toast.html', tasks=tasks)`). If backend changes are out of scope, keep the JS polling for now.

---

## 2. Pipeline Status Polling (`detection.html`)

**Remove**: `startPipelinePolling` and `setInterval`.
**Add**: HTMX polling to the status indicator.

```html
<div id="pipeline-status"
     hx-get="/pipeline_status?TM={{ TM }}&topics={{ topics }}"
     hx-trigger="every 2s"
     hx-swap="outerHTML">
  <span class="badge bg-warning">Processing...</span>
</div>
```

---

## 3. Log Streaming (`detection.html`)

**Convert**: SSE (Server-Sent Events) to HTMX.
The current implementation uses `new EventSource("/stream_detection")`.
HTMX supports this via the SSE extension.

1.  **Add Extension**: `<script src="https://unpkg.com/htmx.org/dist/ext/sse.js"></script>`
2.  **Markup**:
    ```html
    <div hx-ext="sse" sse-connect="/stream_detection" sse-swap="message">
      <!-- Logs append here -->
    </div>
    ```

---

## 4. Verification

- [ ] Progress bars appear/update without page reload.
- [ ] Pipeline completion redirects correctly (if handled by HTMX response header `HX-Redirect`).
- [ ] Logs stream into the modal.
- [ ] No console errors from HTMX.

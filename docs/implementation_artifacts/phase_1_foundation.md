# Phase 1: Foundation Upgrade

> **Goal**: Establish the Halfmoon v2 (Bootstrap 5) foundation, configure the "Deep Cipher" design system, and update the global layout (`base.html`).
> **Critical**: Do not tackle individual page templates yet. Focus on the shell.

---

## 1. Create CSS Variable Overrides

Create a new file: `app/frontend/static/css/app.css`
Copy the "Deep Cipher" CSS variables from `docs/implementation_artifacts/frontend_design_system.md` into this file.

---

## 2. Refactor `base.html`

### 2.1 CDN Swap
**Remove** all Bootstrap 4, Popper.js 1.x, and Bootstrap Icons links.
**Add** the following in `<head>`:

```html
<!-- Fonts -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">

<!-- Halfmoon v2 (Bootstrap 5 compatible) -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/halfmoon@2.0.2/css/halfmoon.min.css">

<!-- Custom Branding -->
<link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">

<!-- DataTables (BS5 Styling) -->
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/dataTables.bootstrap5.min.css">

<!-- Icons -->
<script src="https://unpkg.com/@phosphor-icons/web"></script>
```

**Add** the following before `</body>`:

```html
<!-- HTMX (for future use) -->
<script src="https://unpkg.com/htmx.org@1.9.12"></script>

<!-- Bootstrap 5 Bundle (includes Popper 2) -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>

<!-- Keep jQuery for DataTables (Legacy) -->
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
```

### 2.2 Global Layout Updates

1. **Root Variables**: Ensure `app.css` is loaded *after* Halfmoon.
2. **Navbar**:
   - Change `ml-auto` to `ms-auto`.
   - Update `data-toggle="collapse"` to `data-bs-toggle="collapse"`.
   - Update `data-target` to `data-bs-target`.
   - Add Dark Mode toggle button (see Design System).
3. **Alerts**:
   - Update dismiss buttons: `<button class="btn-close" data-bs-dismiss="alert"></button>` (remove `<span>&times;</span>`).
4. **Icons**:
   - Replace `bi bi-house` with `<i class="ph ph-house"></i>`.
   - Replace `bi bi-gear` with `<i class="ph ph-gear"></i>`.
   - Replace `bi bi-box-arrow-right` with `<i class="ph ph-sign-out"></i>`.

---

## 3. Dark Mode Toggle Implementation

Add this script to `base.html` (before `</body>`):

```html
<script>
  // Theme Toggle Logic
  const toggleTheme = () => {
    const current = document.documentElement.getAttribute('data-bs-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-bs-theme', next);
    localStorage.setItem('theme', next);
  };

  // Initialize
  const saved = localStorage.getItem('theme') || 'dark'; // Default to Dark/Sci-Fi
  document.documentElement.setAttribute('data-bs-theme', saved);
</script>
```

And add the toggle button to the Navbar:
```html
<li class="nav-item">
  <button class="nav-link btn btn-link" onclick="toggleTheme()">
    <i class="ph ph-moon"></i>
  </button>
</li>
```

---

## 4. Verification

- [ ] Page loads without 404s for CSS/JS.
- [ ] Fonts are Inter (check computed styles).
- [ ] Navbar collapses/expands on mobile.
- [ ] Dark mode toggle works and persists refresh.
- [ ] DataTables (on other pages) might look broken – ignore for Phase 1.

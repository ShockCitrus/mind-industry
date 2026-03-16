# Frontend Design System — MIND "Deep Cipher"

> **Purpose**: Define the visual language for the MIND application modernization.
> **Theme**: "Deep Cipher" — A professional, technical aesthetic using deep slate backgrounds and precise cyan/teal accents. Geared towards data-intensive interfaces.

---

## 1. Color Palette

We override Halfmoon's default CSS variables to achieve the "Deep Cipher" look.

### Dark Mode (Default for "Sci-Fi" feel)

| Variable | Value | Description |
|---|---|---|
| `--bs-body-bg` | `#0f172a` | **Slate-900**. Deep, rich background. Not pitch black. |
| `--bs-body-color` | `#f8fafc` | **Slate-50**. High contrast text. |
| `--bs-card-bg` | `#1e293b` | **Slate-800**. Slightly lighter for cards/surfaces. |
| `--bs-border-color` | `#334155` | **Slate-700**. Subtle borders. |

### Brand Colors

| Role | Variable | Value | Description |
|---|---|---|---|
| **Primary** | `--bs-primary` | `#06b6d4` | **Cyan-500**. The core "energy" color. Precise, technical. |
| **Secondary** | `--bs-secondary` | `#64748b` | **Slate-500**. For neutral actions/metadata. |
| **Success** | `--bs-success` | `#10b981` | **Emerald-500**. Secure, positive data states. |
| **Info** | `--bs-info` | `#3b82f6` | **Blue-500**. For standard information. |
| **Warning** | `--bs-warning` | `#f59e0b` | **Amber-500**. Attention required. |
| **Danger** | `--bs-danger` | `#ef4444` | **Red-500**. Critical errors/deletions. |

### Gradient Accents (Optional utilities)

- **Technical Gradient**: `linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)`
  - Use for: Hero headers, active states, special buttons.

---

## 2. Typography

**Font Family**: [Inter](https://fonts.google.com/specimen/Inter)
- **CSS**: `font-family: 'Inter', system-ui, -apple-system, sans-serif;`
- **Rationale**: Highly legible interface font, supports tabular figures (great for data).

**Weights**:
- **300 (Light)**: Captions, metadata.
- **400 (Regular)**: Body text.
- **500 (Medium)**: Buttons, navigation.
- **600 (SemiBold)**: Card headers, section titles.

---

## 3. Iconography

**Library**: [Phosphor Icons](https://phosphoricons.com/)
- **Style**: Regular (default) or Thin (for a more precise, wireframe look).
- **Usage**:
  ```html
  <i class="ph ph-house"></i> <!-- Home -->
  <i class="ph ph-chart-bar"></i> <!-- Analysis -->
  <i class="ph ph-gear"></i> <!-- Settings -->
  ```

---

## 4. Component Styles

### Cards
- **Background**: `--bs-card-bg` (#1e293b)
- **Border**: 1px solid `--bs-border-color` (#334155)
- **Radius**: `0.5rem` (rounded-2)
- **Shadow**: `0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)`

### Modals
- **Backdrop**: `rgba(15, 23, 42, 0.8)` (Slate-900 at 80%)
- **Blur**: `backdrop-filter: blur(4px)` (Glassmorphism effect)

### Buttons
- **Primary**: Cyan background, white text. Hover: slightly lighter Cyan.
- **Outline**: Cyan border, Cyan text. Hover: Cyan background.

---

## 5. CSS Implementation Snippet

Add this to `app/frontend/static/css/app.css`:

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

:root {
  --font-family-base: 'Inter', system-ui, -apple-system, sans-serif;
}

[data-bs-theme="dark"] {
  --bs-body-bg: #0f172a;
  --bs-body-color: #f8fafc;
  --bs-card-bg: #1e293b;
  --bs-border-color: #334155;
  
  --bs-primary: #06b6d4;
  --bs-primary-rgb: 6, 182, 212;
  
  --bs-secondary: #64748b;
  --bs-secondary-rgb: 100, 116, 139;
  
  --bs-success: #10b981;
  --bs-success-rgb: 16, 185, 129;
  
  --bs-warning: #f59e0b;
  --bs-warning-rgb: 245, 158, 11;
  
  --bs-danger: #ef4444;
  --bs-danger-rgb: 239, 68, 68;
  
  --bs-info: #3b82f6;
  --bs-info-rgb: 59, 130, 246;
}

[data-bs-theme="light"] {
  --bs-body-bg: #f8fafc;
  --bs-body-color: #0f172a;
  --bs-card-bg: #ffffff;
  --bs-border-color: #e2e8f0;
  
  /* Keep brand colors consistent or slightly darker for contrast if needed */
  --bs-primary: #0891b2; /* Cyan-600 for better contrast on light */
  --bs-primary-rgb: 8, 145, 178;
}

body {
  font-family: var(--font-family-base);
}
```

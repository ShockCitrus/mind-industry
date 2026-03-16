# Custom Categories & Category Selection Implementation Guide

## Overview

This document provides a complete implementation plan for enhancing the Natural Language Inference (NLI) discrepancy detection system with **user-managed categories** and **runtime category selection**.

**Current State:** The system hardcodes four detection categories: `NOT_ENOUGH_INFO`, `CONTRADICTION`, `NO_DISCREPANCY`, and `CULTURAL_DISCREPANCY`. These are embedded in:

- **NLI Prompt Template:** [discrepancy_detection.txt](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/prompts/discrepancy_detection.txt) — defines the four categories with descriptions and few-shot examples; uses `{question}`, `{answer_1}`, `{answer_2}` placeholders.
- **Pipeline Label Parsing:** [pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py) `MIND._check_contradiction()` (L769–803) — parses `DISCREPANCY_TYPE:` and `REASON:` from LLM output; `_clean_contradiction()` (L805–812) applies typo corrections for known labels only.
- **Frontend Filter Buttons:** [detection.html](file:///home/alonso/Projects/Mind-Industry/app/frontend/templates/detection.html) — hardcoded `label_options` list at L318–319 and quick-filter buttons at L416–424 with hardcoded color mapping.
- **Console Color Map:** `MIND._print_result()` (L642–660) — maps `CONTRADICTION` → Red, `CULTURAL_DISCREPANCY` → Magenta, `NOT_ENOUGH_INFO` → Yellow, `AGREEMENT` → Green.

**New Capabilities (2 features):**

1. **Category Preselection** — Users select which categories (max 5) to detect per pipeline run. Fewer categories = better LLM precision. Defaults are preselected but can be deselected; `CULTURAL_DISCREPANCY` is **not** preselected by default (outside core software scope); `NOT_ENOUGH_INFO` is always visible in the menu but not necessarily preselected.
2. **Custom Categories** — Users can define up to 20 personal detection categories with custom prompts and few-shot examples. These have their own complete management system (CRUD) in the user profile, independent from dataset management.

> [!NOTE]
> **Data Erasure** (deleting user datasets, pipeline runs, etc.) is documented in a **separate guide**: [data_erasure_implementation_guide.md](file:///home/alonso/Projects/Mind-Industry/docs/implementation_artifacts/data_erasure_implementation_guide.md). These are distinct functionalities with different scopes — category management is about detection configuration, data erasure is about storage/privacy management.

---

## Implementation Steps

| Step | Description | Target Areas | Completed |
|------|-------------|--------------|-----------|
| **1. Database Updates** | Add `CustomCategory` model linked to `User` for persistent category storage. | Auth Service / DB | [ ] |
| **2. API Updates** | Create CRUD endpoints for categories, update pipeline submission to accept selected categories. | Backend API | [ ] |
| **3. UI: Category Management** | Add category CRUD section to User Profile page. | Frontend | [ ] |
| **4. UI: Pipeline Category Selection** | Expose category selection (max 5) in pipeline configuration modal with smart defaults. | Frontend | [ ] |
| **5. Prompt Engineering** | Refactor NLI prompt into a dynamic template that injects only the selected categories. | Backend / LLM Prompts | [ ] |
| **6. Dynamic Frontend Visualization** | Make detection results UI extract labels dynamically from result data. | Frontend | [ ] |
| **7. Color Coding Adaptation** | Adapt color logic: original 4 colors for defaults + 1 extra for custom categories. | Frontend | [ ] |

---

## Detailed Implementation Steps

### Step 1: Database Updates

> [!IMPORTANT]
> The auth service uses **Flask-SQLAlchemy** with a simple `User` model. The `CustomCategory` model must be added in the same database.

#### Codebase References
- **Auth DB init:** [database.py](file:///home/alonso/Projects/Mind-Industry/app/auth/app/database.py) — `SQLAlchemy()` instance, reads `DATABASE_URL` env var.
- **User model:** [models.py](file:///home/alonso/Projects/Mind-Industry/app/auth/app/models.py) — `User(id, email, password, username)`.
- **Auth routes:** [routes.py](file:///home/alonso/Projects/Mind-Industry/app/auth/app/routes.py) — existing user CRUD endpoints.

#### Tasks
1. **Add `CustomCategory` model** to `app/auth/app/models.py`:
   ```python
   class CustomCategory(db.Model):
       id = db.Column(db.Integer, primary_key=True)
       user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
       name = db.Column(db.String(100), nullable=False)           # e.g., "POLICY_DISCREPANCY"
       prompt_instruction = db.Column(db.Text, nullable=False)    # How to detect this category
       examples = db.Column(db.Text, nullable=True)               # Few-shot examples (JSON string)
       created_at = db.Column(db.DateTime, default=db.func.now())
       
       user = db.relationship('User', backref=db.backref('custom_categories', lazy=True))
       
       __table_args__ = (
           db.UniqueConstraint('user_id', 'name', name='uq_user_category_name'),
       )
   ```
2. **Add relationship backref** to `User` model (handled by the backref above).
3. **Enforce 20-category limit** at the API level (not in the DB schema, to keep the model simple).
4. **Run migration**: `flask db migrate` / `flask db upgrade` (or add `db.create_all()` in the init script if not using Alembic).

#### Best Practices
- Use **JSON string** for the `examples` field to store structured few-shot examples (list of dicts with `question`, `answer_1`, `answer_2`, `expected_label`, `reason`). This avoids needing a separate table.
- Keep `name` as `SCREAMING_SNAKE_CASE` to match existing label conventions (`CONTRADICTION`, `NO_DISCREPANCY`, etc.).

---

### Step 2: API Updates

#### 2a. Category CRUD Endpoints (Auth Service)

Add to [routes.py](file:///home/alonso/Projects/Mind-Industry/app/auth/app/routes.py):

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/auth/user/<user_id>/categories` | List all custom categories for a user |
| `POST` | `/auth/user/<user_id>/categories` | Create a new category (enforce max 20) |
| `PUT` | `/auth/user/<user_id>/categories/<cat_id>` | Update an existing category |
| `DELETE` | `/auth/user/<user_id>/categories/<cat_id>` | Delete a category |

**Validation rules:**
- `name`: required, max 100 chars, must match `^[A-Z][A-Z0-9_]*$` pattern.
- `prompt_instruction`: required, non-empty, max 2000 chars.
- `examples`: optional, valid JSON array if provided.
- **20-category hard limit**: return HTTP 409 if user tries to exceed.
- **Name uniqueness per user**: return HTTP 409 on duplicate name.

> [!IMPORTANT]
> Category management is completely independent from dataset/pipeline data management. Deleting a category from the profile does NOT affect any existing pipeline results — those results already have labels stored as strings in `mind_results.parquet`.

#### 2b. Pipeline Submission Update (Backend)

File: [detection.py](file:///home/alonso/Projects/Mind-Industry/app/backend/detection.py) `analyse_contradiction()` (L429–563)

The frontend already sends a `config` dict to this endpoint. Extend it:

```python
# In the request payload, add:
config = {
    ...existing fields...,
    "selected_categories": [
        {
            "name": "CONTRADICTION",
            "prompt_instruction": "The answers provide directly opposing factual information...",
            "examples": "..."
        },
        # up to 5 items
    ]
}
```

**Logic changes inside `analyse_contradiction()`:**
1. Extract `selected_categories` from `config`.
2. Pass them into the `cfg` dict that feeds into the `MIND` constructor (new parameter).
3. The `MIND` class will forward them to the prompt engineering system (Step 5).

> [!TIP]
> Send the full category objects (name + prompt + examples) rather than IDs. This makes the pipeline self-contained and avoids cross-service calls from the backend to the auth service. The frontend already has the category data when the user selects them.

---

### Step 3: UI – Category Management (Profile Section)

#### Codebase References
- **Profile template:** [profile.html](file:///home/alonso/Projects/Mind-Industry/app/frontend/templates/profile.html) — currently shows user info form and dataset upload.
- **Profile route:** [profile.py](file:///home/alonso/Projects/Mind-Industry/app/frontend/profile.py) `profile()` (L18–58).
- **Design system:** Uses Bootstrap 5 + Phosphor Icons, dark/light mode support via CSS variables.

#### Tasks
1. **Add a "Custom Categories" section** below the profile form in `profile.html`, visually separated (e.g., a dedicated card or panel).
2. **Display existing categories** in a card list showing: name, prompt instruction (truncated), count badge (e.g., `3 / 20 used`).
3. **Add "Create Category" button** opening a modal form with:
   - Category Name (validated to SCREAMING_SNAKE_CASE, with helper text)
   - Prompt Instruction (textarea, max 2000 chars) — explain: *"Describe how the LLM should recognize this category. Be specific and concise."*
   - Examples (textarea, JSON format, with a helper tooltip showing the expected structure)
4. **Add edit/delete buttons** per category card.
5. **Show remaining slots** badge: `✦ 3 / 20 categories used`.

#### Data Flow
```
profile.html → JS fetch() → profile.py → auth service API → DB
```

The profile route (`profile.py`) must be extended to:
- Fetch categories from auth service on `GET /profile`
- Pass them to the template as `categories` context variable

---

### Step 4: UI – Pipeline Category Selection

#### Codebase References
- **Pipeline config modal:** [detection.html](file:///home/alonso/Projects/Mind-Industry/app/frontend/templates/detection.html) L476–580 — modal `#configPipelineModalLabel` with LLM type, method, and weighting selectors.
- **Frontend API helper:** [detection.py](file:///home/alonso/Projects/Mind-Industry/app/frontend/detection.py) `analyseContradiction()` (L73–87) — sends `config` dict to backend.
- **Backend handler:** [detection.py](file:///home/alonso/Projects/Mind-Industry/app/backend/detection.py) `analyse_contradiction()` (L429–563).

#### Tasks

1. **Add a "Category Selection" section** inside the pipeline config modal (before the Method selector at L554).
2. **Display all available categories** as checkboxes, organized into two groups:

##### Default categories (always visible):

| Category | Pre-checked | Rationale |
|----------|-------------|-----------|
| `CONTRADICTION` | ✅ Yes | Core detection target |
| `NO_DISCREPANCY` | ✅ Yes | Essential for balanced classification |
| `NOT_ENOUGH_INFO` | ❌ No (always visible) | Important but optional — increases noise if enabled |
| `CULTURAL_DISCREPANCY` | ❌ No | Outside the core scope of the software; opt-in only |

##### User custom categories:
- Displayed below the defaults, unchecked by default.
- Fetched from the auth service (same data that populates the profile page).

3. **Enforce max 5 selection** via JS:
   - When 5 are checked, disable all remaining unchecked checkboxes.
   - Show a visible warning text: `⚠️ Selecting more categories may reduce detection accuracy due to LLM context limitations.`
   - When the user unchecks one, re-enable the remaining.

4. **Pass selected categories** in the `config` payload when the "Analyze Discrepancies" button (L461) is clicked. The payload must include the full category objects (name, prompt_instruction, examples), not just names.

5. **Validation before submission:** At least 1 category must be selected. If zero are selected, show an error and block submission.

> [!WARNING]
> The entire pipeline — backend, prompt engineering, and frontend visualization — **must** support runtime-selected categories. This means:
> - The backend `analyse_contradiction()` must accept and forward the `selected_categories` list.
> - The MIND pipeline must dynamically build the NLI prompt from whatever categories are provided.
> - The frontend results page must render labels dynamically, not from a hardcoded list.
> All three layers must be updated as part of this feature.

#### Data Flow: Categories Through the Full Stack
```
detection.html (user selects categories)
  → config.selected_categories (JS payload)
  → analyseContradiction() (frontend/detection.py)
  → analyse_contradiction() (backend/detection.py)
  → cfg["selected_categories"] → MIND.__init__()
  → _build_category_prompt_sections() → dynamic NLI prompt
  → LLM response → _check_contradiction() → parsed label
  → results.append({"label": label}) → mind_results.parquet
  → get_results_mind() → unique_labels extracted from data
  → detection.html (dynamic filter buttons rendered from data)
```

---

### Step 5: Prompt Engineering Modifications

This is the most critical step. The NLI system prompt must become a dynamic template.

#### Current Prompt Architecture

```
config.yaml → mind.prompts.contradiction_checking → discrepancy_detection.txt
         ↓ (loaded at MIND.__init__)
self.prompts["contradiction_checking"] = load_prompt(path)
         ↓ (used in _check_contradiction)
template_formatted = self.prompts["contradiction_checking"].format(
    question=question, answer_1=answer_s, answer_2=answer_t
)
```

#### Refactoring Plan

##### 5a. Create a new dynamic prompt template

Create a new file: `src/mind/pipeline/prompts/discrepancy_detection_dynamic.txt`

The template should have additional `{categories_block}` and `{examples_block}` placeholders:

```
You will be given a QUESTION along with two responses (ANSWER_1 and ANSWER_2). Your task is to classify the relationship between the two answers, given the question, into one of the following categories:

{categories_block}

Response Format:
- REASON: [Briefly explain why you selected this category]
- DISCREPANCY_TYPE: [Choose ONLY one of the categories listed above]

{examples_block}

#### YOUR TASK ####

QUESTION: {question}
ANSWER_1: {answer_1}
ANSWER_2: {answer_2}

You MUST choose exactly one of the categories listed above. Do not invent new categories.
Before answering, carefully consider the definitions and examples for each category.
```

##### 5b. Build `categories_block` and `examples_block` dynamically

In the `MIND` class, add a method to build these blocks from the selected categories:

```python
def _build_category_prompt_sections(self, selected_categories: list) -> tuple[str, str]:
    """Build the categories_block and examples_block for the NLI prompt."""
    categories_block_lines = []
    examples_block_lines = ["#### EXAMPLES ####", ""]
    
    for i, cat in enumerate(selected_categories, 1):
        # Category definition
        categories_block_lines.append(
            f"{i}. {cat['name']}: {cat['prompt_instruction']}"
        )
        categories_block_lines.append("")
        
        # Few-shot examples (if any)
        if cat.get('examples'):
            examples = json.loads(cat['examples']) if isinstance(cat['examples'], str) else cat['examples']
            for ex in examples:
                examples_block_lines.append(f"QUESTION: {ex['question']}")
                examples_block_lines.append(f"ANSWER_1: {ex['answer_1']}")
                examples_block_lines.append(f"ANSWER_2: {ex['answer_2']}")
                examples_block_lines.append(f"REASON: {ex['reason']}")
                examples_block_lines.append(f"DISCREPANCY_TYPE: {ex['expected_label']}")
                examples_block_lines.append("")
    
    return "\n".join(categories_block_lines), "\n".join(examples_block_lines)
```

##### 5c. Update `MIND.__init__()` to accept selected categories

File: [pipeline.py](file:///home/alonso/Projects/Mind-Industry/src/mind/pipeline/pipeline.py) `MIND.__init__()` (L142–262)

Add a new parameter `selected_categories: list = None`. If provided:
1. Load the dynamic template instead of the static one.
2. Build the categories/examples blocks.
3. Pre-format the template with the category/example blocks (the `{question}`, `{answer_1}`, `{answer_2}` placeholders remain for per-call formatting).

If `selected_categories` is `None`, fall back to the original static `discrepancy_detection.txt` (backward compatibility for CLI usage).

##### 5d. Update `_clean_contradiction()`

Currently only corrects `NO_ DISCREPANCY` and `CULTURAL_ DISCREPANCY`. For custom categories, apply a generic normalization instead of a hardcoded corrections dict:
```python
def _clean_contradiction(self, discrepancy_label):
    label = discrepancy_label.strip().upper()
    label = re.sub(r'\s+', '_', label)  # "NOT ENOUGH INFO" → "NOT_ENOUGH_INFO"
    return label
```

##### 5e. `_evaluate_pair()` fallback labels

At lines 565–570, there are hardcoded `"NOT_ENOUGH_INFO"` labels for "cannot answer" responses. These should remain as-is — `NOT_ENOUGH_INFO` is always a valid fallback regardless of selected categories (the LLM may not be able to answer, and that's an intrinsic pipeline behavior, not a user-selected category).

---

### Step 6: Dynamic Frontend Visualization & History Handling

#### Codebase References

- **Results table rendering:** [detection.html](file:///home/alonso/Projects/Mind-Industry/app/frontend/templates/detection.html) L298–337.
- **Hardcoded label filter (dropdown):** L318–324 — `label_options = ['CONTRADICTION', 'CULTURAL_DISCREPANCY', 'NOT_ENOUGH_INFO', 'NO_DISCREPANCY']`.
- **Hardcoded label filter (quick-filter bar):** L412–425 — buttons with hardcoded labels and colors.
- **Backend results endpoint:** [detection.py](file:///home/alonso/Projects/Mind-Industry/app/backend/detection.py) `get_results_mind()` (L565–599).

#### Tasks

##### 6a. Backend: Extract unique labels

In `get_results_mind()`, add a `unique_labels` field to the JSON response:
```python
unique_labels = df['label'].dropna().unique().tolist()
if 'final_label' in df.columns:
    unique_labels = list(set(unique_labels + df['final_label'].dropna().unique().tolist()))

return jsonify({
    ...existing fields...,
    "unique_labels": unique_labels
})
```

##### 6b. Frontend: Dynamic filter buttons

Replace the hardcoded `label_options` list (L318–319) and quick-filter bar (L412–425) with dynamically generated elements:

```javascript
// In detection.js, after loading results:
const labels = window.__DETECTION_DATA.uniqueLabels || [];
const filterBar = document.getElementById('label-filter-bar');
filterBar.innerHTML = '';  // Clear hardcoded buttons
// Dynamically generate one button per unique label with color logic
```

##### 6c. Historical Data Integrity

> [!IMPORTANT]
> Old pipeline runs must NOT be altered. If a custom category was detected in the past and then deleted from the user's profile, the results still display it correctly. The dynamic label extraction from `mind_results.parquet` guarantees this — the labels live in the parquet file itself, never resolved from the DB at display time.

---

### Step 7: Color Coding Adaptation

#### Current Color Mapping

| Category | Console (pipeline.py) | Frontend (detection.html) |
|----------|----------------------|--------------------------|
| `CONTRADICTION` | `Fore.RED` | `#dc3545` (red) |
| `CULTURAL_DISCREPANCY` | `Fore.MAGENTA` | `#ffc107` (amber) |
| `NOT_ENOUGH_INFO` | `Fore.YELLOW` | `#17a2b8` (teal) |
| `NO_DISCREPANCY` | `Fore.GREEN` (as AGREEMENT) | `#28a745` (green) |

#### Tasks

1. **Keep all 4 default colors** unchanged.
2. **Add 1 extra color** for custom categories: suggest `#6f42c1` (purple, Bootstrap's `--bs-purple`) — contrasts well in both light/dark modes.
3. **Frontend logic**: In `detection.js`, build the color map dynamically:
   ```javascript
   const DEFAULT_COLORS = {
       'CONTRADICTION': '#dc3545',
       'CULTURAL_DISCREPANCY': '#ffc107',
       'NOT_ENOUGH_INFO': '#17a2b8',
       'NO_DISCREPANCY': '#28a745'
   };
   const CUSTOM_COLOR = '#6f42c1';
   
   function getColorForLabel(label) {
       return DEFAULT_COLORS[label] || CUSTOM_COLOR;
   }
   ```
4. **Console colors** in `_print_result()` (pipeline.py L642–660): apply same logic — use `Fore.CYAN` (already the default fallback) for custom categories.

---

## Verification Plan

### Automated Tests
1. **DB Model Tests**: Create/read/update/delete `CustomCategory` records. Verify 20-limit enforcement.
2. **API Tests**: Test all CRUD endpoints for categories. Test error codes for limit exceeded and duplicates.
3. **Prompt Generation Tests**: Unit test `_build_category_prompt_sections()` with various category configurations (0 custom, 5 custom, mix of default + custom).
4. **Label Parsing Tests**: Verify `_clean_contradiction()` handles custom labels with spaces, mixed case, etc.

### Manual Verification
1. **Full flow**: Create custom categories via profile → select them in pipeline config → run detection → verify results display correctly with dynamic labels.
2. **Default behavior**: Run with only `CONTRADICTION` + `NO_DISCREPANCY` selected → verify only those labels appear in results.
3. **Historical compatibility**: Run detection with default categories, then add custom categories and run again. Verify old results still display correctly.
4. **Edge cases**: 0 categories selected (blocked), 1 category, 5 categories (max), deselecting all defaults.

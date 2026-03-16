# Data Erasure Implementation Guide

## Overview

This guide details the implementation of data management features allowing users to delete their data at varying levels of granularity. This is a distinct feature from detection category management or pipeline configuration — it concerns **storage and privacy management**.

**Current data layout** on disk per user:
```
/data/<email>/
├── 1_Segmenter/          # Segmented datasets
├── 2_Translator/         # Translated datasets  
├── 3_TopicModel/         # Topic model outputs (.mallet files, thetas, keys)
├── 4_Detection/          # Detection results (mind_results.parquet, checkpoints)
├── .env                  # GPT API keys (if any)
└── pipeline-mind.log     # Pipeline logs
```

**Dataset registry:** A global parquet file at `DATASETS_STAGE` env var, with schema: `Usermail`, `Dataset`, `OriginalDataset`, `Stage`, `Path`, `textColumn`.

---

## Implementation Steps

| Step | Description | Target Areas | Completed |
|------|-------------|--------------|-----------|
| **1. Granular Deletion API** | Create endpoints for deleting individual datasets, pipeline runs, and topic models. | Backend API | [x] |
| **2. Full Data Erasure API** | Create a "nuke" endpoint that deletes ALL user data from disk. | Backend API | [x] |
| **3. UI: Granular Deletion** | Add delete buttons per-dataset and per-pipeline-run in existing UI. | Frontend | [x] |
| **4. UI: Full Data Erasure** | Add a "Danger Zone" section in profile with destructive confirmation. | Frontend | [x] |

---

## Detailed Steps

### Step 1: Granular Deletion API

File: [dataset.py](file:///home/alonso/Projects/Mind-Industry/app/backend/dataset.py)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `DELETE` | `/dataset/<email>/<stage>/<dataset_name>` | Delete a specific dataset at a given stage |
| `DELETE` | `/detection/<email>/<TM>/<topics_slug>` | Delete a specific pipeline run result |

**Implementation notes:**
- Remove the directory from disk (`shutil.rmtree`)
- Remove the corresponding row from `DATASETS_STAGE` parquet
- Return 404 if the resource doesn't exist

### Step 2: Full Data Erasure API ("Nuke" Option)

File: [dataset.py](file:///home/alonso/Projects/Mind-Industry/app/backend/dataset.py)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `DELETE` | `/user_data/erase` | Delete ALL user data |

```python
@datasets_bp.route('/user_data/erase', methods=['DELETE'])
def erase_user_data():
    email = request.args.get('email')
    if not email:
        return jsonify({'error': 'Missing email'}), 400
    
    user_dir = f"/data/{email}"
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)
    
    # Remove all rows from DATASETS_STAGE parquet
    df = pd.read_parquet(DATASETS_STAGE)
    df = df[df['Usermail'] != email]
    df.to_parquet(DATASETS_STAGE)
    
    return jsonify({'message': 'All data erased'}), 200
```

Frontend route in [profile.py](file:///home/alonso/Projects/Mind-Industry/app/frontend/profile.py):
```python
@profile_bp.route('/erase_data', methods=['DELETE'])
@login_required_custom
def erase_data():
    email = session.get("user_id")
    resp = requests.delete(f"{MIND_WORKER_URL}/user_data/erase", params={"email": email})
    return jsonify(resp.json()), resp.status_code
```

### Step 3: UI – Granular Deletion

Add delete buttons (with confirmation) to:
- Dataset cards in [datasets.html](file:///home/alonso/Projects/Mind-Industry/app/frontend/templates/datasets.html)
- Detection result entries in [detection_results.html](file:///home/alonso/Projects/Mind-Industry/app/frontend/templates/detection_results.html)

### Step 4: UI – Full Data Erasure (Profile Danger Zone)

Add to [profile.html](file:///home/alonso/Projects/Mind-Industry/app/frontend/templates/profile.html):

1. **"Danger Zone" section** at the bottom with red-bordered card and `<hr>` separator.
2. **"Delete All My Data" button** styled as `btn-outline-danger`.
3. **Confirmation modal** requiring the user to type the word `DELETE` before proceeding.
4. **On success**, redirect to profile with flash message: *"All data has been permanently deleted."*

> [!CAUTION]
> This is a destructive, non-reversible operation. The confirmation modal must keep the "Confirm" button disabled until `input.value === 'DELETE'`.

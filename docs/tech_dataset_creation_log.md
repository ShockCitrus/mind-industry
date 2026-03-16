# Tech Contradictions Dataset Generation Log

## Purpose
Created a synthetic `TechContradictions_EN_ES` dataset to measure the performance of the Mind Industry application in detecting cross-lingual contradictions on tech-related themes.

## Dataset Structure
- **Size**: 20 total passages (10 in English, 10 in Spanish).
- **Matching Content**: 5 pairs (10 passages) are direct, non-contradictory translations.
- **Contradicting Content**: 5 pairs (10 passages) contain explicit, factual contradictions about the same topic.
- **Location**: Installed inside the active Docker volume `mind-industry_backend_data` at `/data/all/1_RawData/TechContradictions_EN_ES/dataset` as a Parquet file. Any newly created users automatically inherit this dataset.

## Embedded Contradictions
1. **Blockchain Consensus**: Employs Proof of Work (EN) vs. Proof of Stake (ES).
2. **Cyber Security**: Firewall updated yesterday (EN) vs. Firewall not updated in a year (ES).
3. **Autonomous Vehicles**: Tesla uses vision-based cameras only (EN) vs. Tesla uses LiDAR mapping (ES).
4. **Semiconductors (Moore's Law)**: Moore's Law is dead (EN) vs. Moore's Law is accelerating (ES).
5. **Space Tech (Starship)**: Reached orbit seamlessly (EN) vs. Exploded shortly after liftoff (ES).

## Deployment Procedure
1. Created via a Python script (`generate_tech_dataset.py`) using `pandas` and `pyarrow` to build the required `.parquet` structure.
2. Migrated into the Docker volume using `docker cp`.
3. Registered the new dataset into the application's global state (`datasets_stage_preprocess.parquet`) for existing test users (e.g., `alonsomadronal@gmail.com`) using a one-off Python patching script to assure visibility in the UI.

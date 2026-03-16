import os
import pandas as pd
import sys

DATA_DIR = "/data"
ALL_DIR = os.path.join(DATA_DIR, "all")
PARQUET_FILE = "datasets_stage_preprocess.parquet"

def init_data():
    print(f"Checking data initialization in {DATA_DIR}...")
    
    # Ensure /data exists
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 1. Initialize /data/datasets_stage_preprocess.parquet if missing
    root_parquet = os.path.join(DATA_DIR, PARQUET_FILE)
    if not os.path.exists(root_parquet):
        print(f"Creating empty {root_parquet}...")
        df = pd.DataFrame(columns=["Usermail", "Dataset", "OriginalDataset", "Stage", "Path", "textColumn"])
        df.to_parquet(root_parquet, engine='pyarrow', index=False)
    
    # 2. Initialize /data/all if missing
    if not os.path.exists(ALL_DIR):
        print(f"Creating {ALL_DIR}...")
        os.makedirs(ALL_DIR, exist_ok=True)
        
        # Create minimal subfolders that are expected to be copied
        for folder in ["1_RawData", "2_PreprocessData", "3_TopicModel", "4_Detection"]:
            os.makedirs(os.path.join(ALL_DIR, folder), exist_ok=True)
            
        # Create base parquet for 'all' template
        all_parquet = os.path.join(ALL_DIR, PARQUET_FILE)
        if not os.path.exists(all_parquet):
            print(f"Creating empty {all_parquet}...")
            # This is the template that gets copied/modified for new users
            # Since we don't have default datasets, we create an empty one
            df = pd.DataFrame(columns=["Usermail", "Dataset", "OriginalDataset", "Stage", "Path", "textColumn"])
            df.to_parquet(all_parquet, engine='pyarrow', index=False)

    print("Data initialization complete.")

if __name__ == "__main__":
    try:
        init_data()
    except Exception as e:
        print(f"Error initializing data: {e}")
        sys.exit(1)

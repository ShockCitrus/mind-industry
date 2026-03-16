import os
import re
import glob
import shutil
import zipfile
import pandas as pd

from flask import jsonify


def validate_and_get_dataset(email: str, dataset: str, output: str, phase: str):
    try:
        parquet_path = "/data/datasets_stage_preprocess.parquet"
        if not os.path.exists(parquet_path):
            print('No paths found')
            return f"Parquet file not found at {parquet_path}"

        df = pd.read_parquet(parquet_path)

        row = df[
            (df["Usermail"] == email) &
            (df["Dataset"] == dataset) &
            (df["Stage"] == 1)
        ]

        if row.empty:
            print('No dataset found')
            return f"No dataset found for user '{email}', dataset '{dataset}', stage 1."

        if phase == '1_Segmenter':
            dataset_path = f"/data/{email}/1_RawData/{dataset}/dataset"
            output_dir = f"/data/{email}/1_RawData/{dataset}/{phase}/{output}"
        
        elif phase == '2_Translator':
            dataset_path = f"/data/{email}/1_RawData/{dataset}/1_Segmenter/{output}/dataset"
            output_dir = f"/data/{email}/1_RawData/{dataset}/{phase}/{output}"
            
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                return dataset_path, output_dir
            
            content_dir = os.listdir(output_dir)
            files = [f for f in content_dir if os.path.isfile(os.path.join(output_dir, f))]
            if len(files) >= 2:
                return f"Output already exists at {output_dir}. Please choose another output name."
            
            return dataset_path, output_dir
        
        elif phase == '3_Preparer':
            dataset_path = f"/data/{email}/1_RawData/{dataset}/2_Translator/{output}"
            output_dir = f"/data/{email}/2_PreprocessData/{output}"
        
        else:
            print('No phase found')
            return f"No dataset found for user '{email}', dataset '{dataset}', stage 1."
        
        if os.path.exists(f"{output_dir}/dataset"):
            return f"Output already exists at {output_dir}. Please choose another output name."

        os.makedirs(output_dir)

        return dataset_path, output_dir

    except Exception as e:
        return f"Validation error: {e}"
    
def validate_and_get_datasetTM(email: str, dataset: str, output: str):
    try:
        parquet_path = "/data/datasets_stage_preprocess.parquet"
        if not os.path.exists(parquet_path):
            print('No paths found')
            return f"Parquet file not found at {parquet_path}"

        df = pd.read_parquet(parquet_path)

        row = df[
            (df["Usermail"] == email) &
            (df["Dataset"] == dataset) &
            (df["Stage"] == 2)
        ]

        if row.empty:
            print('No dataset found')
            return f"No dataset found for user '{email}', dataset '{dataset}', stage 1."

        dataset_path = f"/data/{email}/2_PreprocessData/{dataset}/dataset"
        output_dir = f"/data/{email}/3_TopicModel/{output}"
        
        if os.path.exists(f"{output_dir}"):
            return f"Output already exists at {output_dir}. Please choose another output name."
        os.makedirs(output_dir)

        return dataset_path, output_dir

    except Exception as e:
        return f"Validation error: {e}"
    
def cleanup_output_dir(email: str, dataset: str, output: str):
    phases = ["1_Segmenter", "2_Translator", "3_Preparer"]
    
    for phase in phases:
        try:
            if phase == "3_Preparer": output_dir = f"/data/{email}/2_PreprocessData/{output}/"
            else: output_dir = f"/data/{email}/1_RawData/{dataset}/{phase}/"
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)
                print(f"[CLEANUP] Removed incomplete dataset at: {output_dir}")
        except Exception as e:
            print(f"[CLEANUP ERROR] Could not remove {output_dir}: {e}")

def aggregate_row(email: str, dataset: str, og_dataset: str, stage: int, output: str, textCol: str = None):
    try:
        parquet_path = "/data/datasets_stage_preprocess.parquet"
        if not os.path.exists(parquet_path):
            print('No paths found')
            return jsonify({
                "status": "error",
                "message": f"Parquet file not found at {parquet_path}"
            }), 404

        df = pd.read_parquet(parquet_path)

        new_row_data = {
            "Usermail": email,
            "Dataset": dataset,
            "OriginalDataset": og_dataset,
            "Stage": stage,
            "textColumn": textCol if stage == 2 else None,
            "Path": output
        }

        if ((df['Usermail'] == new_row_data['Usermail']) &
            (df['Dataset'] == new_row_data['Dataset']) & 
            (df['Stage'] == new_row_data['Stage'])
            ).any():
            print('Existing that dataset for that stage for that user')
            return jsonify({'error': 'Existing that dataset in that stage'}), 450
    
        new_row_df = pd.DataFrame([new_row_data])
        df = pd.concat([df, new_row_df], ignore_index=True)

        df.to_parquet(parquet_path)

    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({
                "status": "error",
                "message": str(e)
            }), 404
    
def obtainTextColumn(email: str, dataset: str):
    try:
        parquet_path = "/data/datasets_stage_preprocess.parquet"
        if not os.path.exists(parquet_path):
            print('No paths found')
            return None

        df = pd.read_parquet(parquet_path)

        row = df[
            (df["Usermail"] == email) &
            (df["Dataset"] == dataset) &
            (df["Stage"] == 2)
        ]

        if row.empty:
            print('No textCol found')
            return None
                
        return row.iloc[0]["textColumn"]
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return None
    
def get_TM_detection(email: str, TM: str):
    try:
        parquet_path = "/data/datasets_stage_preprocess.parquet"
        if not os.path.exists(parquet_path):
            print('No paths found')
            return jsonify({
                "status": "error",
                "message": f"Parquet file not found at {parquet_path}"
            }), 404

        df = pd.read_parquet(parquet_path)

        row = df[
            (df["Usermail"] == email) &
            (df["Dataset"] == TM) &
            (df["Stage"] == 3)
        ]

        if row.empty:
            print('No dataset found')
            return jsonify({
                "status": "error",
                "message": f"No dataset found for user '{email}', topic model '{TM}', stage 3."
            }), 404
                
        return row.iloc[0]["Path"], f"/data/{email}/2_PreprocessData/{row.iloc[0]["OriginalDataset"]}/dataset"
    
    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({
                "status": "error",
                "message": str(e)
            }), 404
    
def obtain_langs_TM(pathTM: str):
    corpus_lang = f'{pathTM}/train_data/corpus_*.txt'
    lang = []
    for file in glob.glob(corpus_lang):
        if not os.path.isfile(file):
            continue
        lang.append(file.split('corpus_')[-1].replace('.txt', ''))
    return lang

def process_mind_results(topics: list[int], directory: str):
    topics_regex = "|".join(str(t) for t in topics)
    # Also matches the final-flush file: results_topic_final_0.parquet
    pattern = re.compile(rf"results_topic_(?:({topics_regex})|final)_(\d+)\.parquet$")

    mapping = {
        'source_chunk': 'anchor_passage',
        'source_chunk_id': 'anchor_passage_id',
        'a_s': 'anchor_answer',
        'target_chunk': 'comparison_passage',
        'target_chunk_id': 'comparison_passage_id',
        'a_t': 'comparison_answer'
    }
    order = [
        'topic', 'question_id', 'question', 'anchor_passage_id', 'anchor_passage', 
        'anchor_answer', 'comparison_passage_id', 'comparison_passage',
        'comparison_answer', 'label', 'final_label', 'reason', 
        'Notes', 'secondary_label'
    ]

    dataframes = []
    matched_files = []
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)

        if not os.path.isfile(filepath):
            continue

        if pattern.match(filename):
            matched_files.append(filename)
            df = pd.read_parquet(filepath)
            df['final_label'] = df['label']
            df = df.rename(columns=mapping)
            top = [col for col in order if col in df.columns]
            bottom = [col for col in df.columns if col not in order]
            final_order = top + bottom
            df = df[final_order]
            dataframes.append(df)

    output_path = os.path.join(directory, "mind_results.parquet")
    if dataframes:
        result = pd.concat(dataframes, ignore_index=True)
        result.to_parquet(output_path)

    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)

        if not os.path.isfile(filepath):
            continue

        if filename != "mind_results.parquet":
            os.remove(filepath)
    
def get_download_dataset(stage: int, email: str, dataset: str, format_file : str):
    try:
        parquet_path = "/data/datasets_stage_preprocess.parquet"
        if not os.path.exists(parquet_path):
            print('No paths found')
            return jsonify({
                "status": "error",
                "message": f"Parquet file not found at {parquet_path}"
            }), 404

        df = pd.read_parquet(parquet_path)

        row = df[
            (df["Usermail"] == email) &
            (df["Dataset"] == dataset) &
            (df["Stage"] == stage)
        ]

        if row.empty:
            print('No dataset found')
            return jsonify({
                "status": "error",
                "message": f"No dataset found for user '{email}', dataset '{dataset}', stage {stage}."
            }), 404

        if stage == 1:
            stage_str = "1_RawData"
            dataset_path = f"/data/{email}/{stage_str}/{dataset}/dataset"
            if format_file == 'xlsx':
                df = pd.read_parquet(dataset_path, engine='pyarrow')
                dataset_path = f'{dataset_path}.xlsx'
                df.to_excel(dataset_path)

        elif stage == 2:
            stage_str = "2_PreprocessData"
            dataset_path = f"/data/{email}/{stage_str}/{dataset}/dataset"
            if format_file == 'xlsx':
                df = pd.read_parquet(dataset_path, engine='pyarrow')
                dataset_path = f'{dataset_path}.xlsx'
                df.to_excel(dataset_path)

        elif stage == 3:
            stage_str = "3_TopicModel"
            dataset_path = f"/data/{email}/{stage_str}/{dataset}"
            zip_path = f"{dataset_path}.zip"
            allowed_dirs = {"train_data", "mallet_input", "mallet_output"}

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(dataset_path):
                    rel_dir = os.path.relpath(root, start=dataset_path)
                    first_level_dir = rel_dir.split(os.sep)[0]
                    if first_level_dir not in allowed_dirs:
                        continue

                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, start=dataset_path)
                        zipf.write(file_path, arcname)
            dataset_path = zip_path

        return dataset_path

    except Exception as e:
        print(e)
        return jsonify({
            "status": "error",
            "message": f"Validation error: {e}"
        }), 500
    
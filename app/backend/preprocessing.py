import os
import json
import uuid
import shutil
import logging
import pandas as pd

from pathlib import Path
from utils import cleanup_output_dir, aggregate_row
from flask import Blueprint, request, jsonify, current_app, send_file, after_this_request


import yaml

preprocessing_bp = Blueprint('preprocessing', __name__, url_prefix='/preprocessing')

# ---------------------------------------------------------------------------
# LLM Server configuration — loaded from config file, NOT hardcoded.
# To add or change servers, edit the 'llm.ollama.servers' section of
# /src/config/config.yaml.
# ---------------------------------------------------------------------------
def _load_ollama_servers(config_path: str = "/src/config/config.yaml") -> dict:
    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        return raw.get("llm", {}).get("ollama", {}).get("servers", {})
    except Exception as e:
        print(f"[WARNING] Could not load Ollama servers from {config_path}: {e}")
        return {}

OLLAMA_SERVER: dict = _load_ollama_servers()

TASKS = {}


def run_step(step_name, func, app, *args, **kwargs):
    step_id = str(uuid.uuid4())
    
    def target():
        with app.app_context():
            TASKS[step_id] = {'status': 'running', 'message': f"{step_name} in progress", 'name': step_name}
            try:
                func(*args, **kwargs)
                TASKS[step_id]['status'] = 'completed'
                TASKS[step_id]['message'] = f"{step_name} completed successfully!"
            except Exception as e:
                TASKS[step_id]['status'] = 'error'
                TASKS[step_id]['message'] = str(e)
    
    from threading import Thread
    Thread(target=target).start()
    
    TASKS[step_id] = {'status': 'pending', 'message': f"{step_name} task created", 'name': step_name}
    return step_id

@preprocessing_bp.route('/status/<step_id>', methods=['GET'])
def status(step_id):
    log = logging.getLogger('werkzeug')
    original_level = log.level
    log.setLevel(logging.ERROR)
    
    try:
        task = TASKS.get(step_id)
        if not task:
            return jsonify({"status": "not_found", "message": "Step ID not found"}), 404
        return jsonify(task), 200
    finally:
        log.setLevel(original_level)

@preprocessing_bp.route('/file_exists', methods=['GET'])
def file_exists():
    """Check if a file exists and optionally return its content (for small marker files)."""
    path = request.args.get('path', '')
    if not path or not path.startswith('/data/'):
        return jsonify({"exists": False}), 200
    exists = os.path.isfile(path)
    content = ""
    if exists:
        try:
            with open(path, 'r') as f:
                content = f.read(256)  # Read small marker files only
        except Exception:
            pass
    return jsonify({"exists": exists, "content": content}), 200

@preprocessing_bp.route('/segmenter', methods=['POST'])
def segmenter():
    try:
        data = request.get_json()
        email = data.get("email")
        dataset = data.get("dataset")
        segmenter_data = data.get("segmenter_data")

        def do_segment():
            import traceback
            from utils import validate_and_get_dataset
            from mind.corpus_building.segmenter import Segmenter
            
            validation = validate_and_get_dataset(
                email=email,
                dataset=dataset,
                output=segmenter_data['output'],
                phase="1_Segmenter"
            )
            if isinstance(validation, tuple):
                dataset_path, output_dir = validation
            else:
                raise Exception(validation)

            print(f'[Segmenter] dataset_path={dataset_path!r}, output_dir={output_dir!r}')
            print(f'[Segmenter] segmenter_data={segmenter_data!r}')

            try:
                seg = Segmenter(config_path="/src/config/config.yaml")
                seg.segment(
                    path_df=dataset_path,
                    path_save=f'{output_dir}/dataset',
                    text_col=segmenter_data['text_col'],
                    id_col=segmenter_data['id_col'],
                    min_length=segmenter_data['min_length'],
                    sep=segmenter_data['sep']
                )

                print('[Segmenter] All data segmented. Splitting by lang...')
                
                df_segmented = pd.read_parquet(f'{output_dir}/dataset', engine='pyarrow')
                df_segmented['lang'] = df_segmented['lang'].astype(str).str.upper()

                # Detect unique languages in the dataset
                detected_langs = df_segmented['lang'].unique().tolist()
                print(f'[Segmenter] Total rows={len(df_segmented)}, detected_langs={detected_langs!r}')
                is_monolingual = len(detected_langs) == 1

                if is_monolingual:
                    # Monolingual dataset: save a marker file and skip bilingual split
                    mono_lang = detected_langs[0]
                    print(f'[Segmenter] Monolingual dataset detected (lang={mono_lang!r}). Skipping bilingual split.')
                    df_segmented.to_parquet(f'{output_dir}/dataset_{mono_lang.lower()}', engine='pyarrow')
                    print(f'[Segmenter] Written monolingual parquet: {output_dir}/dataset_{mono_lang.lower()}')
                    with open(f'{output_dir}/.monolingual', 'w') as f:
                        f.write(mono_lang)
                    print(f'[Segmenter] Written .monolingual marker with lang={mono_lang!r}')
                else:
                    src_lang_upper = str(segmenter_data['src_lang']).upper()
                    tgt_lang_upper = str(segmenter_data['tgt_lang']).upper()
                    df_lang1 = df_segmented[df_segmented['lang'] == src_lang_upper]
                    df_lang2 = df_segmented[df_segmented['lang'] == tgt_lang_upper]
                    print(f'[Segmenter] Bilingual split: {src_lang_upper}={len(df_lang1)} rows, {tgt_lang_upper}={len(df_lang2)} rows')

                    if df_lang1.empty or df_lang2.empty:
                        raise ValueError(f"ERROR: DataFrame has no {segmenter_data['src_lang']} or {segmenter_data['tgt_lang']} language.")

                    df_lang1.to_parquet(f'{output_dir}/dataset_{segmenter_data["src_lang"]}', engine='pyarrow')
                    df_lang2.to_parquet(f'{output_dir}/dataset_{segmenter_data["tgt_lang"]}', engine='pyarrow')
                    print(f'[Segmenter] Written bilingual parquets for {segmenter_data["src_lang"]} and {segmenter_data["tgt_lang"]}')
                
                print(f'[Segmenter] Finalized segmenting dataset {output_dir}')

            except Exception as e:
                tb = traceback.format_exc()
                print(f'[Segmenter] ERROR: {e}\n{tb}')
                cleanup_output_dir(email, dataset, segmenter_data['output'])
                raise e

        step_id = run_step("Segmenting", do_segment, app=current_app._get_current_object())
        # segmenter_output_dir is the real path where .monolingual is written
        segmenter_output_dir = f'/data/{email}/1_RawData/{dataset}/1_Segmenter/{segmenter_data["output"]}'
        return jsonify({
            "step_id": step_id,
            "message": "Segmenter task started",
            "output_dir": f'/data/{email}/2_PreprocessData/{segmenter_data["output"]}',
            "segmenter_output_dir": segmenter_output_dir,
        }), 200

    except Exception as e:
        print(str(e))
        cleanup_output_dir(email, dataset, segmenter_data['output'])
        return jsonify({"status": "error", "message": str(e)}), 500

@preprocessing_bp.route('/translator', methods=['POST'])
def translator():
    try:
        data = request.get_json()
        email = data.get("email")
        dataset = data.get("dataset")
        translator_data = data.get("translator_data")

        def do_translate():
            from utils import validate_and_get_dataset
            from mind.corpus_building.translator import Translator
            
            validation = validate_and_get_dataset(
                email=email,
                dataset=dataset,
                output=translator_data['output'],
                phase="2_Translator"
            )
            if isinstance(validation, tuple):
                dataset_path, output_dir = validation
            else:
                raise Exception(validation)

            # Creating new ID
            df = pd.read_parquet(f'{dataset_path}_{translator_data['src_lang']}', engine='pyarrow')
            df['lang'] = df['lang'].str.lower()
            # df["id_preproc"] = translator_data['src_lang'] + df["id_preproc"].astype(str)
            df.to_parquet(f'{dataset_path}_{translator_data['src_lang']}_temp', engine='pyarrow')

            # Translator
            print(f"Translating dataset {dataset}...")

            try:
                trans = Translator(config_path="/src/config/config.yaml")
                
                # src -> tgt
                trans.translate(
                    path_df=f'{dataset_path}_{translator_data['src_lang']}_temp',
                    save_path=f'{output_dir}/dataset_{translator_data["src_lang"]}2{translator_data["tgt_lang"]}',
                    src_lang=translator_data['src_lang'],
                    tgt_lang=translator_data['tgt_lang'],
                    text_col=translator_data['text_col'],
                    lang_col=translator_data['lang_col'],
                )

                print(f'Finalize translating dataset {output_dir}')
            
            except Exception as e:
                print(str(e))
                cleanup_output_dir(email, dataset, translator_data['output'])
                raise e

        step_id = run_step("Translating", do_translate, app=current_app._get_current_object())
        return jsonify({"step_id": step_id, "message": "Translator task started"}), 200

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f'[Translator endpoint] ERROR: {e}\n{tb}')
        output_key = translator_data['output'] if translator_data else '(unknown)'
        cleanup_output_dir(email, dataset, output_key)
        return jsonify({"status": "error", "message": str(e)}), 500


@preprocessing_bp.route('/preparer', methods=['POST'])
def preparer():
    try:
        data = request.get_json()
        email = data.get("email")
        dataset = data.get("dataset")
        preparer_data = data.get("preparer_data")

        def do_preparer():
            from utils import validate_and_get_dataset
            from mind.corpus_building.data_preparer import DataPreparer
            
            validation = validate_and_get_dataset(
                email=email,
                dataset=dataset,
                output=preparer_data['output'],
                phase="3_Preparer"
            )
            if isinstance(validation, tuple):
                dataset_path, output_dir = validation
            else:
                raise Exception(validation)

            # Data Preparer
            is_monolingual = preparer_data.get('is_monolingual', False)
            print(f"[Preparer] dataset={dataset!r}, is_monolingual={is_monolingual}, dataset_path={dataset_path!r}, output_dir={output_dir!r}")

            # For monolingual, the segmenter wrote the parquet directly to the 1_Segmenter phase.
            # validate_and_get_dataset(phase='3_Preparer') returns dataset_path pointing to 2_Translator
            # which doesn't exist. We override it to read from 1_Segmenter instead.
            if is_monolingual:
                mono_lang = preparer_data.get('src_lang', '').lower()
                segmenter_output = preparer_data.get('output', '')
                monolingual_dataset_path = f"/data/{email}/1_RawData/{dataset}/1_Segmenter/{segmenter_output}"
                print(f"[Preparer] Monolingual: overriding dataset_path to: {monolingual_dataset_path!r}")
                print(f"[Preparer] Will read parquet from: {monolingual_dataset_path}/dataset_{mono_lang}")
                dataset_path = monolingual_dataset_path

            try:
                nlpipe_json = {
                        "id": preparer_data["schema"]["chunk_id"],
                        "raw_text": preparer_data["schema"]["text"],
                        "title": ""
                    }

                with open("/backend/NLPipe/config.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                data['mind'] = nlpipe_json

                with open("/backend/NLPipe/config.json", 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)

                prep = DataPreparer(
                    preproc_script="/backend/NLPipe/src/nlpipe/cli.py",
                    config_path="/backend/NLPipe/config.json",
                    config_logger_path="/src/config/config.yaml",
                    stw_path="/backend/NLPipe/src/nlpipe/stw_lists",
                    spacy_models={
                        "en": "en_core_web_sm",
                        "de": "de_core_news_sm",
                        "es": "es_core_news_sm"},
                    schema=preparer_data['schema'],
                )

                if is_monolingual:
                    mono_lang = preparer_data.get('src_lang', '').lower()
                    res = prep.format_monolingual(
                        input_path=f'{dataset_path}/dataset_{mono_lang}',
                        path_save=f'{output_dir}/dataset'
                    )
                else:
                    res = prep.format_dataframes(
                        anchor_path=f'{dataset_path}/dataset_{preparer_data["src_lang"]}2{preparer_data["tgt_lang"]}',
                        comparison_path=f'{dataset_path}/dataset_{preparer_data["tgt_lang"]}2{preparer_data["src_lang"]}',
                        path_save=f'{output_dir}/dataset'
                    )

                if res is None: return jsonify({"status": "error", "message": "Data Preparer result is None"}), 400

                if os.path.isdir(f"{output_dir}/_tmp_preproc"):
                    shutil.rmtree(f"{output_dir}/_tmp_preproc")

                aggregate_row(email, preparer_data['output'], dataset, 2, f'{output_dir}/dataset', preparer_data["schema"]["text"])

                with open(f'{output_dir}/schema.json', 'w') as f:
                    json.dump(preparer_data['schema'], f, ensure_ascii=False, indent=4)

                print(f'Finalize preparing dataset {output_dir}')
            
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                print(f'[Preparer] ERROR during prepare: {e}\n{tb}')
                cleanup_output_dir(email, dataset, preparer_data['output'])
                # _tmp_preproc may not exist for monolingual, use ignore_errors
                shutil.rmtree(f"{output_dir}/_tmp_preproc", ignore_errors=True)
                raise e

        step_id = run_step("Data Preparer", do_preparer, app=current_app._get_current_object())
        print(f'[Preparer endpoint] step_id={step_id!r}')
        return jsonify({"step_id": step_id, "message": "Data Preparer task started"}), 200

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f'[Preparer endpoint] ERROR: {e}\n{tb}')
        cleanup_output_dir(email, dataset, preparer_data['output'])
        return jsonify({"status": "error", "message": str(e)}), 500
    
@preprocessing_bp.route('/topicmodeling', methods=['POST'])
def topicmodelling():
    try:
        data = request.get_json()
        email = data.get("email")
        dataset = data.get("dataset")
        output = data.get('output')
        lang1 = data.get('lang1')
        lang2 = data.get('lang2')  # None / empty for monolingual
        k = data.get('k')
        is_monolingual = not lang2  # True when lang2 is None or empty string

        def train_topicmodel():
            from utils import validate_and_get_datasetTM
            
            validation = validate_and_get_datasetTM(
                email=email,
                dataset=dataset,
                output=output
            )
            if isinstance(validation, tuple):
                dataset_path, output_dir = validation
            else:
                raise Exception(validation)

            print(f'Training model (k = {k}, monolingual={is_monolingual}) for dataset {dataset_path}...')

            try:
                if is_monolingual:
                    from mind.topic_modeling.lda_tm import LDATM
                    import pathlib
                    model = LDATM(
                        langs=[lang1],
                        model_folder=pathlib.Path(output_dir),
                        num_topics=int(k),
                        mallet_path="/backend/Mallet/bin/mallet",
                    )
                    res = model.train(pathlib.Path(dataset_path))
                    # LDATM.train() returns the mallet_out_folder on success, None on failure
                    if res is None:
                        raise Exception("LDATM training failed.")
                else:
                    from mind.topic_modeling.polylingual_tm import PolylingualTM
                    model = PolylingualTM(
                        lang1=lang1,
                        lang2=lang2,
                        model_folder=Path(output_dir),
                        num_topics=int(k),
                        mallet_path="/backend/Mallet/bin/mallet",
                        add_stops_path="/src/mind/topic_modeling/stops",
                        is_second_level=False
                    )
                    res = model.train(dataset_path)
                    if res != 2:
                        shutil.rmtree(output_dir, ignore_errors=True)
                        shutil.rmtree(f'{output_dir}_old', ignore_errors=True)
                        raise Exception("Model couldn't be trained.")
                
                try:
                    shutil.rmtree(f'{output_dir}_old', ignore_errors=True)
                except:
                    pass
                
                aggregate_row(email, output, dataset, 3, output_dir)
                print('Finalize train model')

            except Exception as e:
                print(str(e))
                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir, ignore_errors=True)
                raise e

        step_id = run_step("TopicModeling", train_topicmodel, app=current_app._get_current_object())
        return jsonify({"step_id": step_id, "message": "Training Topic Model task started"}), 200

    except Exception as e:
        print(str(e))
        return jsonify({"status": "error", "message": str(e)}), 500
    
@preprocessing_bp.route('/labeltopic', methods=['POST'])
def labeltopic():
    try:
        data = request.get_json()
        email = data.get("email")
        output = data.get('output')
        lang1 = data.get('lang1')
        lang2 = data.get('lang2')  # None / empty for monolingual
        k = data.get('k')
        labelTopic = data.get('labelTopic')

        def labeling_topic():
            from mind.topic_modeling.topic_label import TopicLabel
            
            output_dir = f'/data/{email}/3_TopicModel/{output}'

            print(f'Labeling Topic model (k = {k}) {output}...')

            try:
                llm_type = labelTopic.get('llm_type', 'default')

                if llm_type == 'GPT':
                    llm_model = labelTopic.get('llm')
                    llm_server = ''
                    with open(f'/data/{email}/.env', 'w') as f:
                        f.write(f'OPEN_API_KEY={labelTopic["gpt_api"]}')

                elif llm_type == 'gemini' or llm_type == 'default':
                    # Use the llm.default block from config.yaml — no model or server needed.
                    llm_model = None
                    llm_server = None

                else:  # Ollama
                    server_name = labelTopic.get('ollama_server')
                    if not server_name or server_name not in OLLAMA_SERVER:
                        raise ValueError(f"Unknown Ollama server '{server_name}'. Check llm.ollama.servers in config.yaml.")
                    llm_model = labelTopic.get('llm')
                    llm_server = OLLAMA_SERVER[server_name]

                tl = TopicLabel(
                    lang1=lang1,
                    lang2=lang2 or lang1,  # For monolingual, use lang1 as lang2 to satisfy TopicLabel API
                    model_folder=Path(output_dir),
                    llm_model=llm_model,   # None → TopicLabel uses Prompter.from_config()
                    llm_server=llm_server,
                    config_path='/src/config/config.yaml',
                    env_path=f'/data/{email}/.env' if llm_type == 'GPT' else None
                )

                tl.label_topic()

                if os.path.exists(f'/data/{email}/.env'):
                    os.remove(f'/data/{email}/.env')
                
                print('Finalize label TM')

            except Exception as e:
                print(str(e))
                
                if os.path.exists(f'/data/{email}/.env'):
                    os.remove(f'/data/{email}/.env')

                raise e

        step_id = run_step("TopicModeling", labeling_topic, app=current_app._get_current_object())
        return jsonify({"step_id": step_id, "message": "Labeling Topic Model task started"}), 200

    except Exception as e:
        print(str(e))
        return jsonify({"status": "error", "message": str(e)}), 500
    

@preprocessing_bp.route("/download", methods=["POST"])
def download_data():
    data = request.get_json()
    stage = data.get("stage")
    email = data.get("email")
    dataset = data.get("dataset")
    format_file = data.get("format")

    if not dataset:
        return jsonify({"message": "Data missing"}), 400

    try:
        from utils import get_download_dataset
        dataset_path = get_download_dataset(int(stage), email, dataset, format_file)

        if not dataset_path or not os.path.exists(dataset_path):
            return jsonify({"message": "Failed to generate data"}), 500
        
        if dataset_path.endswith(".zip") or dataset_path.endswith(".xlsx"):
            @after_this_request
            def remove_file(response):
                try:
                    os.remove(dataset_path)
                except Exception as e:
                    preprocessing_bp.logger.error(f"Error removing temporary file: {e}")
                return response

        return send_file(
            dataset_path,
            as_attachment=True,
            download_name=os.path.basename(dataset_path),
            mimetype='application/octet-stream'
        )

    except Exception as e:
        return jsonify({"message": f"Error generating data for download: {str(e)}"}), 500

import io
import os
import re
import sys
import glob
import json
import yaml
import string
import requests
import warnings
import threading
import numpy as np
import pandas as pd

from sklearn.manifold import MDS
from collections import defaultdict
from mind.cli import comma_separated_ints
from multiprocessing import Process, Queue
from flask import Blueprint, jsonify, request, send_file
from utils import get_TM_detection, obtain_langs_TM, obtainTextColumn, process_mind_results


detection_bp = Blueprint("detection", __name__)
MIND_FRONTEND_URL = os.getenv('MIND_FRONTEND_URL', 'http://frontend:5000')

OLLAMA_SERVER = {
    "kumo01": "http://kumo01.tsc.uc3m.es:11434",
    "kumo02": "http://kumo02.tsc.uc3m.es:11434",
    "yiyuan": "https://yiyuan.tsc.uc3m.es"
}
ACTIVE_OLLAMA_SERVERS = []

active_processes = {}
lock = threading.Lock()
MAX_USERS = int(os.getenv('MAX_USERS', '2'))
OUTPUT_QUEUE = Queue()

ROWS_PER_PAGE = 15000

class StreamForwarder:
    """
    Stream log to HTML terminal
    """
    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def __init__(self, endpoint_url=None, log_file="/data/pipeline.log"):
        self.endpoint_url = endpoint_url
        self.log_file = log_file
        warnings.simplefilter('default')

        with open(self.log_file, "w") as f:
            f.write("")

    def clean_line(self, line: str) -> str:
        line = self.ANSI_ESCAPE.sub('', line)
        printable = set(string.printable)
        return ''.join([c for c in line if c in printable]).strip()

    def write(self, message: str):
        if not message.strip():
            return

        clean_msg = self.clean_line(message)

        if clean_msg:
            if "Warning" not in clean_msg and self.endpoint_url:
                try:
                    requests.post(self.endpoint_url, json={"log": clean_msg}, timeout=0.5)
                except Exception:
                    pass

            self._save_local(clean_msg)

        sys.__stdout__.write(message + "\n")
        sys.__stdout__.flush()

    def _save_local(self, message: str):
        try:
            with open(self.log_file, "a") as f:
                f.write(message + "\n")
        except Exception:
            pass

    def flush(self):
        pass

    def __enter__(self):
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        sys.stdout = self
        sys.stderr = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self._stdout
        sys.stderr = self._stderr


@detection_bp.route('/detection/topickeys', methods=['GET'])
def getTopicKeys():
    try:
        data = request.get_json()
        email = data.get("email")
        dataset_name = data.get("dataset_name")
        topic_model = data.get("topic_model")

        if not email or not dataset_name or not topic_model:
            return jsonify({"error": "Missing one of the mandatory arguments"}), 400

        path = f'/data/{email}/3_TopicModel/{topic_model}'

        if not os.path.exists(path):
            return jsonify({"error": f'Not existing Topic Model "{topic_model}"'}), 500

        topic_keys = {"TM_name": topic_model, "lang": []}
        all_keywords = {}  # {lang: {topic_id: [words]}}

        mallet_topic_keys = f'{path}/mallet_output/keys_*.txt'
        for file in glob.glob(mallet_topic_keys):
            if not os.path.isfile(file):
                continue

            lang = file.split('keys_')[-1].replace('.txt', '')
            topic_keys["lang"].append(lang)

            keys = {}
            with open(file, 'r') as f:
                for i, line in enumerate(f):
                    keys[i] = line.strip().split(' ')
            all_keywords[lang] = keys

        num_topics = len(next(iter(all_keywords.values())))

        doc_topics_file = f"{path}/mallet_output/doc-topics.txt"
        with open(doc_topics_file, 'r') as f:
            lines = [line.strip() for line in f if not line.startswith("#")]

        num_docs = len(lines)
        max_topic_id = 0
        for line in lines:
            parts = line.split()[2:]
            topic_ids = [int(parts[i]) for i in range(1, len(parts), 2)]
            max_topic_id = max(max_topic_id, max(topic_ids))
        num_topics_file = max_topic_id + 1
        num_topics = max(num_topics, num_topics_file)

        topic_matrix = np.zeros((num_docs, num_topics))

        for doc_idx, line in enumerate(lines):
            parts = line.split()[2:]
            for i in range(1, len(parts), 2):
                topic_id = int(parts[i])
                proportion = float(parts[i - 1])
                topic_matrix[doc_idx, topic_id] = proportion

        mds = MDS(n_components=2, random_state=1234)
        topic_matrix = np.nan_to_num(topic_matrix)
        coords = mds.fit_transform(topic_matrix.T)
        topic_sizes = topic_matrix.mean(axis=0)

        # Read data labels lang
        labels = {}
        try:
            for lang in topic_keys["lang"]:
                with open(f"{path}/mallet_output/labels_{lang}.txt", 'r', encoding='utf-8') as f:
                    labels[lang] = f.readlines()
        except:
            labels = None

        topics_data = []
        for topic_id in range(num_topics):
            entry = {
                "id": topic_id + 1,
                "x": float(coords[topic_id, 0]),
                "y": float(coords[topic_id, 1]),
                "size": float(topic_sizes[topic_id]),
                "TM_name": topic_model
            }

            label = []
            for lang in topic_keys["lang"]:
                entry[f"keywords_{lang}"] = all_keywords.get(lang, {}).get(topic_id, [])
            
                # Get Topic label
                if labels: label.append(f'{lang}: {labels[lang][topic_id].strip()}')

            if labels: entry["label"] = f'({" || ".join(label)})'
            else: entry["label"] = ''
            
            topics_data.append(entry)

        return jsonify({"topics": topics_data}), 200

    except Exception as e:
        print(str(e))
        return jsonify({"error": f"ERROR: {str(e)}"}), 500
    
@detection_bp.route('/detection/models', methods=['GET'])
def getModels():
    """gemma3:4b"""
    try:
        # models_detection = ["qwen2.5:72b", "llama3.2", "llama3.1:8b-instruct-q8_0", "qwen:32b", "llama3.3:70b", "qwen2.5:7b-instruct", "qwen3:32b", "llama3.3:70b-instruct-q5_K_M", "llama3:8b"]
        models_detection = ["gemma3:4b",
                            "mistral:7b",
                            "mixtral:8x22b",
                            "gemma2:9b",
                            "llama3.1:8b",
                            "llama4:16x17b",
                            "qwen3:8b",
                            "qwen3:32b",
                            "falcon3:10b"
                            ]
        avaible_models = {}
        for server in OLLAMA_SERVER.keys():
            if server == "yiyuan":
                response = requests.get(f"{OLLAMA_SERVER[server]}/v1/models", headers={'X-API-KEY': os.getenv('YIYUAN_API_KEY')})
            else:
                response = requests.get(f"{OLLAMA_SERVER[server]}/v1/models")
            if response.status_code == 200:
                data = response.json()
                models_server = [m['id'] for m in data['data']]  
                
                avaible_models[server] = []
                for model in models_detection:
                    if model in models_server:
                        avaible_models[server].append(model)
        
        return jsonify({"models": avaible_models}), 200
    
    except Exception as e:
        print(str(e))
        return jsonify({"error": f"ERROR: {str(e)}"}), 500
    
@detection_bp.route('/detection/doc_representation', methods=['GET'])
def doc_representation():
    try:
        data = request.get_json()
        email = data.get("email")
        TM = data.get("TM")

        paths = get_TM_detection(email, TM)

        if isinstance(paths, tuple):
            pathTM, pathCorpus = paths[0], paths[1]
        else:
            raise Exception("Path TM failed")
        
        lang = obtain_langs_TM(pathTM)
        textCol = obtainTextColumn(email, pathCorpus.replace('/dataset', '').split('/')[-1])

        df = pd.read_parquet(pathCorpus, engine='pyarrow')
        df1 = df[df["lang"] == lang[0]].copy()
        df2 = df[df["lang"] == lang[1]].copy()

        ids_1 = df1['doc_id'].astype(str).tolist()
        texts_1 = [
            " ".join(text.split()[:80]) + "..." if len(text.split()) > 10 else text
            for text in df1[textCol].astype(str)
        ]

        ids_2 = df2['doc_id'].astype(str).tolist()
        texts_2 = [
            " ".join(text.split()[:80]) + "..." if len(text.split()) > 10 else text
            for text in df2[textCol].astype(str)
        ]
        
        topic_docs = defaultdict(list)

        with open(f'/data/{email}/3_TopicModel/{TM}/mallet_output/doc-topics.txt', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                parts = line.split()
                doc_id = int(parts[0])
                topic_props = parts[1:]
                for i in range(0, len(topic_props), 2):
                    topic = int(topic_props[i])
                    prop = float(topic_props[i+1])
                    topic_docs[topic].append([doc_id, prop, str(topic)])

        if os.path.exists(f'/data/{email}/3_TopicModel/{TM}/mallet_output/labels_{lang[0]}.txt'):
            with open(f'/data/{email}/3_TopicModel/{TM}/mallet_output/labels_{lang[0]}.txt', 'r', encoding='utf-8') as f:
                labels1 = f.readlines()

            with open(f'/data/{email}/3_TopicModel/{TM}/mallet_output/labels_{lang[1]}.txt', 'r', encoding='utf-8') as f:
                labels2 = f.readlines()

            for k in range(len(topic_docs)):
                for doc in range(len(topic_docs[k])):
                    topic_docs[k][doc][2] += f' ({lang[0].upper()}: {labels1[k].strip()} || {lang[1].upper()}: {labels2[k].strip()})'

        docs_data_1 = [
            {
                "id": ids_1[i],
                "text": texts_1[i],
                "topics": {}
            }
            for i in range(len(ids_1))
        ]

        for k, doc_list in topic_docs.items():
            for doc_id, prop, topic_name in doc_list:
                try:
                    docs_data_1[doc_id]["topics"][topic_name] = prop
                except:
                    continue

        docs_data_2 = [
            {
                "id": ids_2[i],
                "text": texts_2[i],
                "topics": {}
            }
            for i in range(len(ids_2))
        ]

        for k, doc_list in topic_docs.items():
            for doc_id, prop, topic_name in doc_list:
                try:
                    docs_data_2[doc_id]["topics"][topic_name] = prop
                except:
                    continue

        return jsonify({
            "docs_data_1": docs_data_1,
            "lang_1": lang[0],
            "docs_data_2": docs_data_2,
            "lang_2": lang[1]
        }), 200
    
    except Exception as e:
        print(str(e))
        return jsonify({"error": f"ERROR: {str(e)}"}), 500
    
@detection_bp.route('/detection/pipeline_status', methods=['GET'])
def pipeline_status():
    try:
        data = request.get_json()
        global lock, active_processes
        with lock:
            if data['email'] in active_processes:
                if active_processes[data['email']]['process'].is_alive():
                    return jsonify({"status": "running"}), 200
                elif os.path.exists(f'/data/{data['email']}/4_Detection/{data['TM']}_contradiction/{data['topics']}/mind_results.parquet'):
                    return jsonify({"status": "finished"}), 200
                return jsonify({"status": "error"}), 500
            else:
                if os.path.exists(f'/data/{data['email']}/4_Detection/{data['TM']}_contradiction/{data['topics']}/mind_results.parquet'):
                    return jsonify({"status": "finished"}), 200
                return jsonify({"status": "error"}), 500
            
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

def run_pipeline_process(cfg, run_kwargs, log_file, email):
    from mind.pipeline.pipeline import MIND
    global OUTPUT_QUEUE
    try:
        with StreamForwarder(f'{MIND_FRONTEND_URL}/log_detection', log_file):
            mind = MIND(**cfg)
            if cfg["env_path"] != None: os.remove(cfg["env_path"])

            print("MIND class created. Running pipeline...", file=sys.__stdout__)
            mind.run_pipeline(**run_kwargs)

            print('MIND Pipeline Finish. Preparing results...')
            global ACTIVE_OLLAMA_SERVERS
            try:
                ACTIVE_OLLAMA_SERVERS.remove(cfg['llm_model'])
            except:
                pass
            process_mind_results(run_kwargs['topics'], run_kwargs['path_save'])
        
        OUTPUT_QUEUE.put(0)
    except Exception as e:
        if cfg["env_path"] != None:
            if os.path.exists(cfg["env_path"]):
                os.remove(cfg["env_path"])

        global lock, active_processes
        with lock:
            if email in active_processes:
                del active_processes[email]
        
        try:
            ACTIVE_OLLAMA_SERVERS.remove(cfg['llm_model'])
        except:
            pass
        
        with StreamForwarder(f'{MIND_FRONTEND_URL}/log_detection', log_file):
            print(f"[PIPELINE ERROR] {e}")
        OUTPUT_QUEUE.put(-1)

@detection_bp.route('/detection/analyse_contradiction', methods=['POST'])
def analyse_contradiction():
    try:
        data = request.get_json()
        print(data)
        email = data.get("email")
        TM = data.get("TM")
        topics = data.get("topics")
        sample_size = data.get("sample_size")
        config = data.get("config")

        # First check if was analyse before
        path_results = f'/data/{email}/4_Detection/{TM}_contradiction/{topics}/'
        if os.path.exists(path_results):
            print('Results were done before.')
            return jsonify({"message": "Pipeline done correctly"}), 200
        
        print('Analysing...')
        paths = get_TM_detection(email, TM)

        if isinstance(paths, tuple):
            pathTM, pathCorpus = paths[0], paths[1]
        else:
            raise Exception("Path TM failed")
        
        lang = obtain_langs_TM(pathTM)
        textCol = obtainTextColumn(email, pathCorpus.replace('/dataset', '').split('/')[-1])

        if config['llm_type'] == 'GPT':
            llm_server = ''
            with open(f'/data/{email}/.env', 'w') as f:
                f.write(f'OPEN_API_KEY={config['gpt_api']}')
        
        else:
            llm_server = OLLAMA_SERVER[config['ollama_server']]
            global ACTIVE_OLLAMA_SERVERS
            if config['llm'] in ACTIVE_OLLAMA_SERVERS:
                return jsonify({"error": f"{config['llm']} is in use. Please, choose another ollama LLM."}), 500
            else: ACTIVE_OLLAMA_SERVERS.append(config['llm'])
        
        # =========================
        # =      CONFIG PART      =
        # =========================

        source_corpus = {
            "corpus_path": pathCorpus,
            "thetas_path": f'{pathTM}/mallet_output/thetas_{lang[0]}.npz',
            "id_col": 'doc_id',
            "passage_col": textCol,
            "full_doc_col": 'full_doc',
            "language_filter": lang[0],
            "filter_ids": None,
            "load_thetas": True,
            "method": config['method'],
        }

        target_corpus = {
            "corpus_path": pathCorpus,
            "thetas_path": f'{pathTM}/mallet_output/thetas_{lang[1]}.npz',
            "id_col": 'doc_id',
            "passage_col": textCol,
            "full_doc_col": 'full_doc',
            "language_filter": lang[1],
            "filter_ids": None,
            "load_thetas": True,
            "method": config['method'],
            'index_path': f'/data/{email}/3_TopicModel/{TM}/'
        }

        cfg = {
            "llm_model": config['llm'],
            "llm_server": llm_server,
            "source_corpus": source_corpus,
            "target_corpus": target_corpus,
            "retrieval_method": config['method'],
            "config_path": '/src/config/config.yaml',
            "env_path": f'/data/{email}/.env' if config["llm_type"] == 'GPT' else None
        }

        run_kwargs = {
            "topics": [x - 1 for x in comma_separated_ints(topics)],
            "sample_size": int(sample_size),
            "path_save": path_results
        }

        # weight yaml
        with open('/src/config/config.yaml', 'r') as f:
            data = yaml.safe_load(f)

        data['mind']['method'] = config['method']
        data['mind']['do_weighting'] = config['do_weighting']

        with open('/src/config/config.yaml', 'w') as f:
            yaml.safe_dump(data, f, sort_keys=False)

        log_file = f'/data/{email}/pipeline-mind.log'
        global lock, active_processes
        with lock:
            if email not in active_processes and len(active_processes) >= MAX_USERS:
                if cfg["env_path"] == None: ACTIVE_OLLAMA_SERVERS.remove(cfg['llm_model'])
                return jsonify({"error": "Max users reached"}), 429

            # Cancel on the other session
            if email in active_processes:
                prev_proc = active_processes[email]["process"]
                if prev_proc.is_alive():
                    print(f"Cancelling previous pipeline for {email}", file=sys.__stdout__)
                    prev_proc.terminate()
                if cfg["env_path"] == None: ACTIVE_OLLAMA_SERVERS.remove(cfg['llm_model'])
                del active_processes[email]

        p = Process(target=run_pipeline_process, args=(cfg, run_kwargs, log_file, email))
        p.start()

        active_processes[email] = {"process": p, "llm": cfg['llm_model']}

        return jsonify({"message": "Started"}), 200
    
    except Exception as e:
        print(e)
        return jsonify({"error": f"ERROR: {str(e)}"}), 500
    
@detection_bp.route('/detection/result_mind', methods=['GET'])
def get_results_mind():
    try:
        data = request.get_json()
        print(data)
        email = data.get("email")
        TM = data.get("TM")
        topics = data.get("topics")
        start = int(data.get("start", 0))
        end = start + ROWS_PER_PAGE

        df = pd.read_parquet(f'/data/{email}/4_Detection/{TM}_contradiction/{topics}/mind_results.parquet', engine='pyarrow')
        df_rows = df.iloc[start:end]
        result_mind = df_rows.to_dict(orient='records')
        result_columns = df.columns.tolist()

        columns_json = json.dumps([{"name": col} for col in df.columns])
        non_orderable_indices = json.dumps([i for i, col in enumerate(df.columns) if col in ['label', 'final_label']])

        pagination_ranges = [
            [i, min(i + ROWS_PER_PAGE, len(df))] 
            for i in range(0, len(df), ROWS_PER_PAGE)
        ]

        return jsonify({"message": f"Results from MIND obtained correctly",
                        "result_mind": result_mind,
                        "result_columns": result_columns,
                        "columns_json": columns_json,
                        "non_orderable_indices": non_orderable_indices,
                        "ranges": pagination_ranges}), 200

    except Exception as e:
        print(e)
        return jsonify({"error": f"ERROR: {str(e)}"}), 500
    
@detection_bp.route('/detection/update_results', methods=['POST'])
def update_result_mind():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file uploaded"}), 400
        
        TM = request.form.get("TM")
        topics = request.form.get("topics")
        email = request.form.get("email")
        start = int(request.form.get("start"))

        if not TM or not topics or not email:
            return jsonify({"error": "Missing parameters"}), 400
        
        end = start + ROWS_PER_PAGE

        df_xlsx = pd.read_excel(file, engine='openpyxl')
        keys = []
        for key in df_xlsx.keys():
            values = key.replace('\n', '').split(' ')
            if 'label' in values:
                keys.append('label')
            elif 'final_label' in values:
                keys.append('final_label')
            else:
                keys.append(values[0])

        df_xlsx.columns = keys

        df = pd.read_parquet(f'/data/{email}/4_Detection/{TM}_contradiction/{topics}/mind_results.parquet', engine='pyarrow')
        df = df.astype(str)
        df_xlsx = df_xlsx.astype(str)
        df.iloc[start:end, :] = df_xlsx.values
        df.to_parquet(f'/data/{email}/4_Detection/{TM}_contradiction/{topics}/mind_results.parquet', engine='pyarrow')

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name='mind_results_updated.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        print(e)
        return jsonify({"error": f"ERROR: {str(e)}"}), 500

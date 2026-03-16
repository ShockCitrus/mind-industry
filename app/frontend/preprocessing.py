import os
import time
import uuid
import dotenv
import requests
import threading

from io import BytesIO
from detection import getModels
from collections import defaultdict
from views import login_required_custom
from flask import Blueprint, render_template, request, flash, jsonify, session, send_file


preprocess = Blueprint('preprocess', __name__)
dotenv.load_dotenv()
MIND_WORKER_URL = os.environ.get('MIND_WORKER_URL')

MAX_CONCURRENT_TASKS = int(os.getenv('MAX_CONCURRENT_TASKS', '20')) - 1
MAX_CONCURRENT_TASKS_PER_USER = int(os.getenv('MAX_CONCURRENT_TASKS_PER_USER', '4'))
RUNNING_TASKS = defaultdict(list)
TASK_COUNTER = 0

tasks_lock = threading.Lock()


@preprocess.route('/api/preprocess_status', methods=['GET'])
def get_preprocess_status():
    global RUNNING_TASKS, tasks_lock
    user_id = session.get('user_id')

    with tasks_lock:
        tasks_list = []
        for task in RUNNING_TASKS[user_id]:
            percent = task.get('percent', 0)
            message = task.get('message', '')
            name = task.get('name', 'Unknown')

            tasks_list.append({
                'id': task['id'],
                'name': name,
                'percent': percent,
                'message': message
            })

    return jsonify({
        'tasks': tasks_list,
        'running_count': len(tasks_list),
        'max_limit': MAX_CONCURRENT_TASKS_PER_USER
    })

@preprocess.route('/preprocessing', methods=['GET'])
@login_required_custom
def preprocessing():
    user_id = session.get('user_id')

    models = getModels()
    try:
        response = requests.get(f"{MIND_WORKER_URL}/datasets", params={"email": user_id})
        if response.status_code == 200:
            data = response.json()
            datasets = data.get("datasets", [])
            names = data.get("names", [])
            stages = data.get("stages", [])
        else:
            flash("Error loading datasets from backend.", "danger")
            datasets, names = [], []
    except requests.exceptions.RequestException:
        flash("Backend service unavailable.", "danger")
        datasets, names = [], []

    return render_template('preprocessing.html', user_id=user_id, datasets=datasets, names=names, stages=stages, zip=zip, models=models)

def wait_for_step_completion(step_id, step_name, timeout=600000, interval=5):
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{MIND_WORKER_URL}/status/{step_id}")
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "").lower()
            message = data.get("message", "")
            
            print(f"[{step_name}] Status: {status} - {message}")
            
            if status == "completed":
                print(f"[{step_name}] Completed.")
                return True
            elif status == "error":
                raise Exception(f"Backend error: {message}")
            
            time.sleep(interval)
        except requests.RequestException as e:
            print(f"[{step_name}] Error checking status: {e}")
            time.sleep(interval)
    raise TimeoutError(f"Timeout waiting for {step_name} to complete.")

def preprocess_stage1(task_id, task_name, email, dataset, segmenter_data, translator_data, preparer_data):
    global RUNNING_TASKS

    with tasks_lock:
        task_state = next((t for t in RUNNING_TASKS[email] if t['id'] == task_id), None)

    if not task_state:
        print(f"ERROR: Task {task_id} not found or was deleted")
        return

    print(f"[{task_name}] Task started.")
    print(f"[{task_name}] dataset={dataset!r}")
    print(f"[{task_name}] segmenter_data={segmenter_data!r}")
    print(f"[{task_name}] translator_data={translator_data!r}")
    print(f"[{task_name}] preparer_data={preparer_data!r}")

    try:
        # ── Step 1: Segmenter ──
        task_state['percent'] = 20
        step_name = "Segmenting"
        task_state['message'] = f"Step 1: {step_name} {dataset}..."
        print(f"[{task_name}] → Sending segmenter request for dataset={dataset!r}, output={segmenter_data.get('output')!r}")
        response = requests.post(
            f"{MIND_WORKER_URL}/segmenter",
            json={"email": email, "dataset": dataset, "segmenter_data": segmenter_data}
        )
        response.raise_for_status()
        seg_data = response.json()
        print(f"[{task_name}] Segmenter response: {seg_data}")
        step_id = seg_data.get("step_id")
        output_dir = seg_data.get("output_dir", "")
        # segmenter_output_dir is the actual 1_RawData path where the .monolingual marker is written
        segmenter_output_dir = seg_data.get("segmenter_output_dir", "")
        print(f"[{task_name}] Segmenter step_id={step_id!r}, output_dir={output_dir!r}, segmenter_output_dir={segmenter_output_dir!r}")
        if step_id:
            wait_for_step_completion(step_id, step_name)

        # ── Check if monolingual ──
        mono_marker = f"{segmenter_output_dir}/.monolingual"
        is_monolingual = False
        mono_lang = None
        print(f"[{task_name}] Checking for monolingual marker at: {mono_marker!r}")
        try:
            check_resp = requests.get(f"{MIND_WORKER_URL}/file_exists", params={"path": mono_marker})
            check_data = check_resp.json()
            print(f"[{task_name}] file_exists response: {check_data}")
            if check_resp.status_code == 200 and check_data.get("exists"):
                is_monolingual = True
                mono_lang = check_data.get("content", "").strip().upper()
                print(f"[{task_name}] Monolingual dataset detected (lang={mono_lang!r}). Translation will be skipped.")
            else:
                print(f"[{task_name}] No monolingual marker found — bilingual path will be used.")
        except Exception as e:
            print(f"[{task_name}] WARNING: Could not check monolingual marker: {e}. Defaulting to bilingual.")

        if is_monolingual:
            # ── Monolingual path: skip translation, go directly to preparer ──
            task_state['percent'] = 60
            task_state['message'] = f"Step 2/2: Data-Preparing (monolingual) {dataset}..."
            preparer_data['is_monolingual'] = True
            preparer_data['src_lang'] = mono_lang.lower()
            print(f"[{task_name}] → Sending preparer request (monolingual). preparer_data={preparer_data!r}")
            response = requests.post(
                f"{MIND_WORKER_URL}/preparer",
                json={"email": email, "dataset": dataset, "preparer_data": preparer_data}
            )
            response.raise_for_status()
            data = response.json()
            print(f"[{task_name}] Preparer (monolingual) response: {data}")
            step_id = data.get("step_id")
            if step_id:
                wait_for_step_completion(step_id, "Data-Preparing (monolingual)")
        else:
            # ── Bilingual path: translate both directions, then prepare ──
            if translator_data is None:
                raise ValueError(
                    "translator_data is None but dataset is bilingual. "
                    "Please provide source and target language details."
                )

            # Step 2: Translate src → tgt
            task_state['percent'] = 35
            step_name = f"Translating ({translator_data['src_lang']} → {translator_data['tgt_lang']})"
            task_state['message'] = f"Step 2/4: {step_name} {dataset}..."
            print(f"[{task_name}] → Sending translator request (src→tgt). translator_data={translator_data!r}")
            response = requests.post(
                f"{MIND_WORKER_URL}/translator",
                json={"email": email, "dataset": dataset, "translator_data": translator_data}
            )
            response.raise_for_status()
            data = response.json()
            print(f"[{task_name}] Translator (→tgt) response: {data}")
            step_id = data.get("step_id")
            if step_id:
                wait_for_step_completion(step_id, step_name)

            # Step 3: Translate tgt → src
            task_state['percent'] = 55
            step_name = f"Translating ({translator_data['tgt_lang']} → {translator_data['src_lang']})"
            tgt_lang = translator_data['tgt_lang']
            translator_data['tgt_lang'] = translator_data['src_lang']
            translator_data['src_lang'] = tgt_lang
            task_state['message'] = f"Step 3/4: {step_name} {dataset}..."
            print(f"[{task_name}] → Sending translator request (tgt→src). translator_data={translator_data!r}")
            response = requests.post(
                f"{MIND_WORKER_URL}/translator",
                json={"email": email, "dataset": dataset, "translator_data": translator_data}
            )
            response.raise_for_status()
            data = response.json()
            print(f"[{task_name}] Translator (→src) response: {data}")
            step_id = data.get("step_id")
            if step_id:
                wait_for_step_completion(step_id, step_name)

            # Step 4: Data Preparer
            task_state['percent'] = 75
            step_name = "Data-Preparing"
            task_state['message'] = f"Step 4/4: {step_name} {dataset}..."
            print(f"[{task_name}] → Sending preparer request (bilingual). preparer_data={preparer_data!r}")
            response = requests.post(
                f"{MIND_WORKER_URL}/preparer",
                json={"email": email, "dataset": dataset, "preparer_data": preparer_data}
            )
            response.raise_for_status()
            data = response.json()
            print(f"[{task_name}] Preparer (bilingual) response: {data}")
            step_id = data.get("step_id")
            if step_id:
                wait_for_step_completion(step_id, step_name)

        task_state['message'] = f"{task_name} completed! Results saved."
        task_state['percent'] = 100
        print(f"[{task_name}] Task completed successfully.")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[{task_name}] FATAL ERROR: {e}\n{tb}")
        task_state['message'] = f"FATAL ERROR in {task_name}: {e}"
        task_state['percent'] = -1

    finally:
        time.sleep(5)
        with tasks_lock:
            RUNNING_TASKS[email] = [t for t in RUNNING_TASKS[email] if t['id'] != task_id]
        print(f"[{task_name}] Task removed from active tasks.")



@preprocess.route('/preprocess/Stage1', methods=['POST'])
def start_preprocess():
    global RUNNING_TASKS, TASK_COUNTER

    data = request.get_json()
    dataset = data.get('dataset')
    segmentor_data = data.get('segmentor_data')
    translator_data = data.get('translator_data')
    preparer_data = data.get('preparer_data')
    user_id = session.get('user_id')

    with tasks_lock:
        total_tasks = sum(len(user_processes) for user_processes in RUNNING_TASKS.values())
        if total_tasks > MAX_CONCURRENT_TASKS:
            return jsonify({
                'success': False,
                'message': f'Limit {MAX_CONCURRENT_TASKS} of global processes achieved.'
            }), 409
        
        if len(RUNNING_TASKS[user_id]) >= MAX_CONCURRENT_TASKS_PER_USER:
            return jsonify({
                'success': False,
                'message': f'Limit {MAX_CONCURRENT_TASKS_PER_USER} of processes per user achieved.'
            }), 409

        TASK_COUNTER += 1
        new_task_id = str(uuid.uuid4())
        new_task_name = f"Preprocessing {dataset} to {segmentor_data['output']}"

        new_task_state = {
            'id': new_task_id,
            'name': new_task_name,
            'percent': 0,
            'message': "Preprocessing data...",
            'thread': None
        }
        RUNNING_TASKS[user_id].append(new_task_state)

    thread = threading.Thread(
        target=preprocess_stage1, 
        args=(new_task_id, new_task_name, session['user_id'], dataset, segmentor_data, translator_data, preparer_data)
    )
    thread.start()
    
    return jsonify({
        'success': True, 
        'message': f"Process preprocessing dataset '{dataset}' iniciado correctamente.",
        'task_id': new_task_id
    }), 202

def preprocess_stage2(task_id, task_name, email, dataset, output, lang1, lang2, k, labelTopic):
    global RUNNING_TASKS

    with tasks_lock:
        task_state = next((t for t in RUNNING_TASKS[email] if t['id'] == task_id), None)

    if not task_state:
        print(f"ERROR: Task {task_id} not found or was deleted")
        return

    print(f"Starting task: {task_name}")

    TOTAL_STEPS = 1
    if labelTopic != {}: TOTAL_STEPS = 2

    try:
        for step in range(TOTAL_STEPS):
            if step == 0:
                percent = 50
                task_state['percent'] = percent

                step_name = "Topic Modeling"
                task_state['message'] = f"Topic Modeling {dataset}..."
                response = requests.post(
                    f"{MIND_WORKER_URL}/topicmodeling",
                    json={
                        "email": email,
                        "dataset": dataset,
                        "output": output,
                        "lang1": lang1,
                        "lang2": lang2,
                        "k": k
                    }
                )
                response.raise_for_status()
                data = response.json()
                step_id = data.get("step_id")
                if step_id:
                    wait_for_step_completion(step_id, step_name)
            
            elif step == 1:
                percent = 80
                task_state['percent'] = percent

                step_name = "Labeling Topics"
                task_state['message'] = f"Labeling Topics {output}..."
                response = requests.post(
                    f"{MIND_WORKER_URL}/labeltopic",
                    json={
                        "email": email,
                        "output": output,
                        "lang1": lang1,
                        "lang2": lang2,
                        "k": k,
                        "labelTopic": labelTopic,
                    }
                )
                response.raise_for_status()
                data = response.json()
                step_id = data.get("step_id")
                if step_id:
                    wait_for_step_completion(step_id, step_name)

        
        task_state['message'] = f"{task_name} completed! Results saved."
        task_state['percent'] = 100
        print(f"Completed task: {task_name}")

    except Exception as e:
        task_state['message'] = f"FATAL ERROR in {task_name}: {e}"
        task_state['percent'] = -1

    finally:
        time.sleep(5)
        with tasks_lock:
            RUNNING_TASKS[email] = [t for t in RUNNING_TASKS[email] if t['id'] != task_id]
        print(f"Task: {task_name} removed from the active tasks")


@preprocess.route('/preprocess/Stage2', methods=['POST'])
def start_topicModelling():
    global RUNNING_TASKS, TASK_COUNTER

    data = request.get_json()
    dataset = data.get('dataset')
    output = data.get('output')
    lang1 = data.get('lang1')
    lang2 = data.get('lang2')  # None / empty string for monolingual
    k = data.get('k')
    labelTopic = data.get('labelTopic')
    user_id = session.get('user_id')

    with tasks_lock:
        total_tasks = sum(len(user_processes) for user_processes in RUNNING_TASKS.values())
        if total_tasks > MAX_CONCURRENT_TASKS:
            return jsonify({
                'success': False,
                'message': f'Limit {MAX_CONCURRENT_TASKS} of global processes achieved.'
            }), 409
        
        if len(RUNNING_TASKS[user_id]) >= MAX_CONCURRENT_TASKS_PER_USER:
            return jsonify({
                'success': False,
                'message': f'Limit {MAX_CONCURRENT_TASKS_PER_USER} of processes per user achieved.'
            }), 409

        TASK_COUNTER += 1
        new_task_id = str(uuid.uuid4())
        new_task_name = f"Training Topic Model ({k} topics) of {dataset}"

        new_task_state = {
            'id': new_task_id,
            'name': new_task_name,
            'percent': 0,
            'message': "Training Topic Model...",
            'thread': None
        }
        RUNNING_TASKS[user_id].append(new_task_state)

    thread = threading.Thread(
        target=preprocess_stage2, 
        args=(new_task_id, new_task_name, session['user_id'], dataset, output, lang1, lang2, k, labelTopic)
    )
    thread.start()
    
    return jsonify({
        'success': True, 
        'message': f"Process Topic Modelling dataset '{dataset}' started.",
        'task_id': new_task_id
    }), 202

@preprocess.route("/preprocess/download", methods=["POST"])
def download_file():
    data = request.get_json()
    stage = data.get("stage")
    dataset = data.get("dataset")
    output = data.get("output")
    format_file = data.get("format")

    if not dataset or not output:
        return jsonify({"message": "Missing fields"}), 400

    response = requests.post(f"{MIND_WORKER_URL}/download", json={"stage": stage, "dataset": dataset, "email": session['user_id'], "format": format_file})

    if response.status_code != 200:
        return jsonify({"message": "Error from backend"}), 500

    file_content = response.content
    file_io = BytesIO(file_content)
    file_io.seek(0)

    return send_file(
        file_io,
        as_attachment=True,
        download_name=output,
        mimetype="application/octet-stream"
    )
    
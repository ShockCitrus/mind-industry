import os
import json
import queue
import dotenv
import requests

from detection import *
from functools import wraps
from flask import Blueprint, Response, render_template, request, flash, jsonify, session, url_for


views = Blueprint('views', __name__)
dotenv.load_dotenv()

MIND_WORKER_URL = os.environ.get('MIND_WORKER_URL')
AUTH_API_URL = f"{os.environ.get('AUTH_API_URL')}/auth"
log_queue = queue.Queue() 


def login_required_custom(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return render_template("home.html")
        return f(*args, **kwargs)
    return decorated_function

@views.route('/')
def home():
    user_id = session.get('user_id')
    try:
        requests.get(f"{MIND_WORKER_URL}/cancel_detection", params={"email": user_id})
    except:
        pass
    return render_template("home.html", user_id=user_id)

@views.route('/detectionAllResults')
@login_required_custom
def detection_AllResults_page():
    user_id = session.get('user_id')
    dataset_detection = {}
    try:
        response = requests.get(f"{MIND_WORKER_URL}/datasets", params={"email": user_id})
        if response.status_code == 200:
            data = response.json()
            datasets = data.get("datasets", [])
            names = data.get("names", [])
            shapes = data.get("shapes", [])
            stages = data.get("stages", [])
        else:
            flash(f"Error loading datasets: {response.text}", "danger")
            datasets, names, shapes, stages = [], [], [], []
        
        dataset_detection = getTMDatasets(user_id)

    except requests.exceptions.RequestException:
        flash("Backend service unavailable.", "danger")
        datasets, names, shapes, stages = [], [], [], []

    return render_template("detection_results.html", user_id=user_id, datasets=datasets, names=names, shape=shapes, stages=stages, dataset_detection=dataset_detection, zip=zip)

@views.route('/dataset_selection', methods=['POST'])
@login_required_custom
def dataset_selection():
    data = request.get_json()
    dataset = data.get('dataset')

    if not dataset:
        flash('No dataset provided', 'danger')
        return jsonify({'error': 'No dataset provided'}), 400

    print("Received dataset:", dataset)
    session['dataset'] = dataset
    
    return jsonify({'message': 'Dataset received', 'dataset': dataset})

@views.route('/mode_selection', methods=['GET', 'POST'])
@login_required_custom
def mode_selection():
    data = request.get_json()
    mode = data.get('instruction')
    print("Received mode:", mode)

    user_id = session['user_id']

    if not mode:
        flash('No mode provided', 'danger')
        return jsonify({'error': 'No mode provided'}), 400

    if request.method == 'POST':
        if mode == "Analyze contradictions":
            topics = data.get('topics')
            config = data.get('config')
            
            # Call backend
            result = analyseContradiction(user_id, session.get('TM'), topics, data.get('sample_size'), config)
            
            if result is None:
                return jsonify({'error': 'LLM in use'}), 400
            return result
        
        else:
            flash('Invalid mode selected', 'danger')
            return jsonify({'error': 'Invalid mode selected'}), 400
    else:
        flash(f"Select a dataset before exploring!", "warning")
        return jsonify({'error': f'MIND is not initialized.'}), 400
    
@views.route("/log_detection", methods=["POST"])
def receive_log():
    data = request.get_json()
    log_line = data.get("log")
    if log_line:
        log_queue.put(log_line)
    return {"status": "ok"}

@views.route("/stream_detection")
@login_required_custom
def stream():
    def event_stream():
        while True:
            try:
                line = log_queue.get(timeout=1)
                yield f"data: {json.dumps({'log': line})}\n\n"
            except queue.Empty:
                continue
    return Response(event_stream(), mimetype="text/event-stream")

@views.route('/pipeline_status', methods=['GET'])
def pipeline_status():
    email = session['user_id']
    TM = request.args.get("TM")
    topics = request.args.get("topics")

    try:
        response = requests.get(f"{MIND_WORKER_URL}/pipeline_status", json={"email": email, "TM": TM, "topics": topics})
        data = response.json()
        return data

    except requests.exceptions.RequestException:
        flash("Backend service unavailable.", "danger")
        return {}
    
@views.route('/detection_results')
@login_required_custom
def detection_results_page():
    result_mind = None
    result_columns = None
    
    try:
        user_id = session['user_id']
        TM = request.args.get('TM')
        topics = request.args.get('topics')
        start = 0

        result = get_result_mind(user_id, TM, topics, start)
        if result is None:
            flash('Error loading results from backend.', 'warning')
            return render_template("detection.html", user_id=user_id, status="completed",
                                   result_mind=None, result_columns=None,
                                   columns_json=None, non_orderable_indices=None, ranges=None)

        result_mind = result.get('result_mind')
        result_columns = result.get('result_columns')
        columns_json = result.get('columns_json')
        non_orderable_indices = result.get('non_orderable_indices')
        ranges = result.get('ranges')
        unique_labels = result.get('unique_labels', [])

        return render_template("detection.html", user_id=user_id, status="completed", result_mind=result_mind, result_columns=result_columns, columns_json=columns_json, non_orderable_indices=non_orderable_indices, ranges=ranges, unique_labels=unique_labels)

    except Exception as e:
        print(e)
        return render_template("detection.html", user_id=user_id, status="completed",
                               result_mind=None, result_columns=None,
                               columns_json=None, non_orderable_indices=None, ranges=None)

@views.route('/results_chunk', methods=['GET'])
@login_required_custom
def results_chunk():
    result_mind = None
    result_columns = None
    
    try:
        user_id = session['user_id']
        TM = request.args.get('TM')
        topics = request.args.get('topics')
        start = int(request.args.get('start', 0))

        result = get_result_mind(user_id, TM, topics, start)
        if result is None:
            flash('Error in Backend', 'warning')
            return result
        
        result_mind = result.get('result_mind')
        result_columns = result.get('result_columns')
        unique_labels = result.get('unique_labels', [])

        columns = [
            {"name": col, "data": col} for col in result_columns
        ]

        return {
            "rows": result_mind,
            "columns": columns,
            "unique_labels": unique_labels
        }
    
    except Exception as e:
        print(e)
        return {
            "rows": None,
            "columns": None
        }
    
@views.route('/update_results', methods=['POST'])
@login_required_custom
def update_mind_results():
    try:
        user_id = session['user_id']

        file = request.files.get('file')
        if not file:
            return jsonify({"error": "No file uploaded"}), 400

        TM = request.form.get('TM')
        topics = request.form.get('topics')
        start = request.form.get('start')

        if not TM or not topics or not start:
            return jsonify({"message": "Missing fields"}), 400

        files = {"file": (file.filename, file.stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        data = {
            "TM": TM,
            "topics": topics,
            "start": start,
            "email": user_id
        }

        response = requests.post(f"{MIND_WORKER_URL}/detection/update_results", files=files, data=data, timeout=300)

        if response.status_code != 200:
            print(response.text)
            return jsonify({"message": "Error from backend"}), 500

        return Response(
            response.iter_content(chunk_size=1024),
            status=response.status_code,
            mimetype=response.headers['Content-Type'],
            headers={
                "Content-Disposition": response.headers.get('Content-Disposition')
            }
        )
    
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

@views.route('/detection', methods=['GET', 'POST'])
@login_required_custom
def detection_page():
    user_id = session.get('user_id')

    status = "idle"
    mind_info = {}
    dataset_detection = {}
    topic_keys = {}
    avaible_models = []
    doc_proportion = {"lang_1": "", "lang_2": "", "docs_data_1": [], "docs_data_2": []}

    if request.method == 'GET':
        dataset_detection = getTMDatasets(user_id)

    elif request.method == 'POST':
        try:
            data = request.get_json()
            print(f'Found: {data}')
            data = json.loads(data)
            session["TM"] = data['topic_model']

        except Exception as e:
            flash("Couldn't get correctly data or communicate to the backend.", "danger")
            dataset_detection = getTMDatasets(user_id)

        if data:
            # Get the topic keys from that model
            topic_keys = getTMkeys(user_id, data)
            avaible_models = getModels()
            doc_proportion = getDocProportion(user_id, session["TM"])

    # Fetch user's custom categories for the config modal
    user_categories = []
    try:
        cat_resp = requests.get(f"{AUTH_API_URL}/user/{user_id}/categories", timeout=5)
        if cat_resp.status_code == 200:
            user_categories = cat_resp.json().get('categories', [])
    except requests.exceptions.RequestException:
        pass

    is_monolingual = not doc_proportion.get("lang_2", "")

    return render_template("detection.html",
                           user_id=user_id,
                           status=status,
                           dataset_detection=dataset_detection,
                           topic_keys=topic_keys,
                           mind_info=mind_info,
                           avaible_models=avaible_models,
                           lang_1=doc_proportion["lang_1"],
                           docs_data_1=doc_proportion["docs_data_1"],
                           lang_2=doc_proportion["lang_2"],
                           docs_data_2=doc_proportion["docs_data_2"],
                           is_monolingual=is_monolingual,
                           user_categories=user_categories
                           )

@views.route('/detection_topickeys', methods=['POST'])
@login_required_custom
def detection_page_topickeys_post():
    user_id = session.get('user_id')
    
    status = "idle"
    mind_info = {}
    session['mind_info'] = mind_info
    dataset_detection = ""
    session['dataset_detection'] = None
    topic_keys = {}

    try:
        data = request.get_json()
        print(f'Found: {data}')
        data = json.loads(data)
        session["TM"] = data['topic_model']

    except Exception as e:
        flash("Couldn't get correctly data or communicate to the backend.", "danger")
        dataset_detection = getTMDatasets(user_id)
        session['dataset_detection'] = dataset_detection

    if data:
        # Get the topic keys from that model
        topic_keys = getTMkeys(user_id, data)
        avaible_models = getModels()
        doc_proportion = getDocProportion(user_id, session["TM"])
        session['topic_keys'] = topic_keys
        session['avaible_models'] = avaible_models
        session['doc_proportion'] = doc_proportion

    return jsonify({
        'redirect': url_for('views.detection_page_topickeys_get',
                            status=status)
    })

@views.route('/detection_topickeys', methods=['GET'])
@login_required_custom
def detection_page_topickeys_get():
    user_id = session.get('user_id')
    status = request.args.get('status')
    dataset_detection = session.get('dataset_detection')
    topic_keys = session.get('topic_keys')
    avaible_models = session.get('avaible_models')
    doc_proportion = session.get('doc_proportion')
    mind_info = session.get('mind_info')

    return render_template(
        "detection.html",
        user_id=user_id,
        status=status,
        dataset_detection=dataset_detection,
        topic_keys=topic_keys,
        avaible_models=avaible_models,
        lang_1=doc_proportion["lang_1"],
        docs_data_1=doc_proportion["docs_data_1"],
        lang_2=doc_proportion["lang_2"],
        docs_data_2=doc_proportion["docs_data_2"],
        mind_info=mind_info
    )

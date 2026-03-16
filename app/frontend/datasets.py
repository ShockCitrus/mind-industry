import os
import dotenv
import requests

from views import login_required_custom
from flask import Blueprint, render_template, flash, session, request, jsonify


dataset_bp = Blueprint('dataset', __name__)
dotenv.load_dotenv()
MIND_WORKER_URL = os.environ.get('MIND_WORKER_URL')


@dataset_bp.route('/datasets')
@login_required_custom
def datasets():
    user_id = session.get('user_id')

    try:
        response = requests.get(f"{MIND_WORKER_URL}/datasets", params={"email": user_id})
        if response.status_code == 200:
            data = response.json()
            datasets = data.get("datasets", [])
            names = data.get("names", [])
            shapes = data.get("shapes", [])
            stages = data.get("stages", [])
            # flash(f"Datasets loaded successfully!", "success")
        else:
            flash(f"Error loading datasets: {response.text}", "danger")
            datasets, names, shapes, stages = [], [], [], []
    except requests.exceptions.RequestException:
        flash("Backend service unavailable.", "danger")
        datasets, names, shapes, stages = [], [], [], []

    return render_template("datasets.html", user_id=user_id, datasets=datasets, names=names, shape=shapes, stages=stages, zip=zip)


@dataset_bp.route('/delete_dataset', methods=['DELETE'])
@login_required_custom
def delete_dataset():
    email = session.get('user_id')
    stage = request.args.get('stage')
    dataset_name = request.args.get('dataset_name')

    if not stage or not dataset_name:
        return jsonify({'error': 'Missing stage or dataset_name'}), 400

    try:
        resp = requests.delete(f"{MIND_WORKER_URL}/dataset/{email}/{stage}/{dataset_name}")
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.RequestException:
        return jsonify({'error': 'Backend service unavailable'}), 503


@dataset_bp.route('/delete_detection', methods=['DELETE'])
@login_required_custom
def delete_detection():
    email = session.get('user_id')
    tm = request.args.get('TM')
    topics_slug = request.args.get('topics_slug')

    if not tm or not topics_slug:
        return jsonify({'error': 'Missing TM or topics_slug'}), 400

    try:
        resp = requests.delete(f"{MIND_WORKER_URL}/detection/{email}/{tm}/{topics_slug}")
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.RequestException:
        return jsonify({'error': 'Backend service unavailable'}), 503

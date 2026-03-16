import os
import dotenv
import requests

from auth import validate_password
from views import login_required_custom
from flask import Blueprint, render_template, request, flash, jsonify, session


profile_bp = Blueprint('profile', __name__)
dotenv.load_dotenv()
MIND_WORKER_URL = os.environ.get('MIND_WORKER_URL')
AUTH_API_URL = f"{os.environ.get('AUTH_API_URL', 'http://auth:5002/')}/auth"

MAX_MB = 10


@profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required_custom
def profile():
    user_id = session.get('user_id')
    username = session.get('username')

    # Fetch custom categories from auth service
    categories_data = {"categories": [], "count": 0, "max": 20}
    try:
        cat_resp = requests.get(f"{AUTH_API_URL}/user/{user_id}/categories", timeout=5)
        if cat_resp.status_code == 200:
            categories_data = cat_resp.json()
    except requests.exceptions.RequestException:
        pass  # Non-critical — show empty list

    if request.method == 'POST':

        new_email = request.form.get('email')
        new_username = request.form.get('username')
        new_password = request.form.get('password')
        new_password_rep = request.form.get('password_rep')
        
        update_payload = {}
        if new_email and new_email != session.get('email'):
            update_payload['email'] = new_email
        if new_username and new_username != session.get('username'):
            update_payload['username'] = new_username
        if new_password == new_password_rep and new_password != '' and new_password_rep != '':
            if validate_password(new_password, new_password_rep)[0]:
                update_payload['password'] = new_password
                update_payload['password_rep'] = new_password_rep

        if update_payload:
            try:
                response = requests.put(f"{AUTH_API_URL}/user/{session['user_id']}", json=update_payload)
                if response.status_code == 200:
                    if 'email' in update_payload:
                        session['user_id'] = update_payload['email']
                        user_id = update_payload['email']
                    if 'username' in update_payload:
                        session['username'] = update_payload['username']
                        username = update_payload['username']
                    flash("Profile updated successfully!", "success")
                else:
                    flash(response.json().get('error', 'Error updating profile'), "danger")
            except requests.exceptions.RequestException:
                flash("Authentication service unavailable", "danger")
        else:
            flash("No changes made.", "info")
    return render_template("profile.html", user_id=user_id, username=username,
                           categories=categories_data.get("categories", []),
                           categories_count=categories_data.get("count", 0),
                           categories_max=categories_data.get("max", 20))

@profile_bp.route('/upload_dataset', methods=['POST'])
def upload_dataset():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)

    if file_size > (MAX_MB * 1024 * 1024):
        return jsonify({'error': 'File too large (Max 10MB)'}), 400

    stage = request.form.get('stage')
    if not stage:
        return jsonify({'error': 'No stage selected'}), 400

    sep = request.form.get('sep')
    textColumn = request.form.get('textColumn')

    filename = file.filename
    temp_path = f"temp_{filename}"
    file.save(temp_path)

    email = session.get("user_id") 
    output_dir = f'{email}/{stage}'
    output_file_path = os.path.join(output_dir, filename.split(".")[0])

    try:
        with open(temp_path, 'rb') as f:
            files = {'file': (filename, f)}
            data = {
                'path': output_file_path,
                'email': email,
                'stage': int(stage.split('_')[0]),
                'dataset_name': "".join(filename.split('.')[:-1]),
                'extension': filename.split('.')[-1],
                'sep': sep,
                'textColumn': textColumn
            }
            resp = requests.post(f"{MIND_WORKER_URL}/upload_dataset", files=files, params=data)

            if not resp.ok:
                backend_error_message = resp.json().get('error', 'Backend error message not found')
                return jsonify({'error': backend_error_message}), resp.status_code

            backend_response = resp.json().get('message', 'Success')
    
    except requests.RequestException as e:
        return jsonify({'error': f'Backend request failed: {e}'}), 500
    
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return jsonify({'message': backend_response}), 200


@profile_bp.route('/erase_data', methods=['DELETE'])
@login_required_custom
def erase_data():
    email = session.get("user_id")
    try:
        resp = requests.delete(f"{MIND_WORKER_URL}/user_data/erase", params={"email": email})
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Backend service unavailable"}), 503


# ---------------------------------------------------------------------------
# Custom Category proxy routes
# ---------------------------------------------------------------------------

@profile_bp.route('/categories', methods=['GET'])
@login_required_custom
def list_categories():
    user_id = session.get('user_id')
    try:
        resp = requests.get(f"{AUTH_API_URL}/user/{user_id}/categories", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Auth service unavailable"}), 503


@profile_bp.route('/categories', methods=['POST'])
@login_required_custom
def create_category():
    user_id = session.get('user_id')
    data = request.get_json()
    try:
        resp = requests.post(f"{AUTH_API_URL}/user/{user_id}/categories", json=data, timeout=5)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Auth service unavailable"}), 503


@profile_bp.route('/categories/<int:cat_id>', methods=['PUT'])
@login_required_custom
def update_category(cat_id):
    user_id = session.get('user_id')
    data = request.get_json()
    try:
        resp = requests.put(f"{AUTH_API_URL}/user/{user_id}/categories/{cat_id}", json=data, timeout=5)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Auth service unavailable"}), 503


@profile_bp.route('/categories/<int:cat_id>', methods=['DELETE'])
@login_required_custom
def delete_category(cat_id):
    user_id = session.get('user_id')
    try:
        resp = requests.delete(f"{AUTH_API_URL}/user/{user_id}/categories/{cat_id}", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Auth service unavailable"}), 503

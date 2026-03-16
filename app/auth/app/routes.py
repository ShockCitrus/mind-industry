import os
import re
import json
import dotenv
import requests

from database import db
from models import User, CustomCategory
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash


dotenv.load_dotenv()
auth_bp = Blueprint("auth", __name__)
MIND_WORKER_URL = os.getenv("MIND_WORKER_URL")

MAX_CATEGORIES_PER_USER = 20
CATEGORY_NAME_RE = re.compile(r'^[A-Z][A-Z0-9_]*$')


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    email = data.get("email")
    username = data.get("username")
    password = data.get("password")
    password_rep = data.get("password_rep")

    if not email or not password:
        return jsonify({"error": "Missing fields"}), 400
    if password != password_rep:
        return jsonify({"error": "Passwords do not match"}), 400

    hashed_pw = generate_password_hash(password)
    new_user = User(email=email, username=username, password=hashed_pw)
    
    try:
        db.session.add(new_user)
        db.session.commit()
    except Exception as e:
        print(str(e))
        return jsonify({"error": "Failed to insert user: User already exists"}), 500        

    try:
        response = requests.post(
            f"{MIND_WORKER_URL}/create_user_folders",
            json={"email": email},
            timeout=10
        )
        if response.status_code != 200:
            raise Exception(f"Error from backend: {response.text}")

    except Exception as e:
        db.session.delete(new_user)
        db.session.commit()
        return jsonify({"error": f"Failed to create user folders: {str(e)}"}), 500

    return jsonify({"message": "User created successfully"}), 201

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({"message": "Login successful", "user_id": user.email, "username": user.username}), 200

@auth_bp.route("/user/<user_id>", methods=["PUT"])
def update_user(user_id):
    """
    Update User
    """
    data = request.get_json()
    email = data.get("email")
    username = data.get("username")
    password = data.get("password")
    password_rep = data.get("password_rep")

    user = User.query.filter_by(email=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    updated = False

    if email and email != user.email:
        old_email = user.email
        user.email = email
        updated = True
        try:
            response = requests.post(
                f"{MIND_WORKER_URL}/update_user_folders",
                json={"old_email": old_email, "new_email": email},
                timeout=10
            )
            if response.status_code != 200:
                raise Exception(response.text)
        except Exception as e:
            user.email = old_email
            db.session.commit()
            return jsonify({"error": f"Failed to update backend: {str(e)}"}), 500

    if username and username != user.username:
        user.username = username
        updated = True

    if password or password_rep:
        if not password or not password_rep:
            return jsonify({"error": "Both password and password_rep are required"}), 400
        if password != password_rep:
            return jsonify({"error": "Passwords do not match"}), 400
        user.password = generate_password_hash(password)
        updated = True

    if updated:
        db.session.commit()
        return jsonify({"message": "User updated successfully"}), 200
    else:
        return jsonify({"message": "No changes made"}), 200


# ---------------------------------------------------------------------------
# Custom Category CRUD
# ---------------------------------------------------------------------------

@auth_bp.route("/user/<user_id>/categories", methods=["GET"])
def list_categories(user_id):
    """List all custom categories for a user."""
    user = User.query.filter_by(email=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    categories = CustomCategory.query.filter_by(user_id=user.id).order_by(CustomCategory.created_at).all()
    return jsonify({
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "prompt_instruction": c.prompt_instruction,
                "examples": c.examples,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in categories
        ],
        "count": len(categories),
        "max": MAX_CATEGORIES_PER_USER,
    }), 200


@auth_bp.route("/user/<user_id>/categories", methods=["POST"])
def create_category(user_id):
    """Create a new custom category (max 20 per user)."""
    user = User.query.filter_by(email=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    name = (data.get("name") or "").strip()
    prompt_instruction = (data.get("prompt_instruction") or "").strip()
    examples = data.get("examples")

    # --- validation ---
    if not name:
        return jsonify({"error": "Name is required"}), 400
    if len(name) > 40:
        return jsonify({"error": "Name must be at most 40 characters"}), 400
    if not CATEGORY_NAME_RE.match(name):
        return jsonify({"error": "Name must be SCREAMING_SNAKE_CASE (e.g. MY_CATEGORY)"}), 400

    if not prompt_instruction:
        return jsonify({"error": "Prompt instruction is required"}), 400
    if len(prompt_instruction) > 2000:
        return jsonify({"error": "Prompt instruction must be at most 2000 characters"}), 400

    if examples is not None:
        if isinstance(examples, str):
            try:
                json.loads(examples)
            except json.JSONDecodeError:
                return jsonify({"error": "Examples must be a valid JSON array"}), 400
        else:
            # Accept list/dict directly — serialize for storage
            examples = json.dumps(examples)

    # --- limits ---
    current_count = CustomCategory.query.filter_by(user_id=user.id).count()
    if current_count >= MAX_CATEGORIES_PER_USER:
        return jsonify({"error": f"Maximum of {MAX_CATEGORIES_PER_USER} categories reached"}), 409

    # --- uniqueness ---
    existing = CustomCategory.query.filter_by(user_id=user.id, name=name).first()
    if existing:
        return jsonify({"error": f"Category '{name}' already exists"}), 409

    category = CustomCategory(
        user_id=user.id,
        name=name,
        prompt_instruction=prompt_instruction,
        examples=examples,
    )
    db.session.add(category)
    db.session.commit()

    return jsonify({
        "message": "Category created",
        "category": {
            "id": category.id,
            "name": category.name,
            "prompt_instruction": category.prompt_instruction,
            "examples": category.examples,
            "created_at": category.created_at.isoformat() if category.created_at else None,
        }
    }), 201


@auth_bp.route("/user/<user_id>/categories/<int:cat_id>", methods=["PUT"])
def update_category(user_id, cat_id):
    """Update an existing custom category."""
    user = User.query.filter_by(email=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    category = CustomCategory.query.filter_by(id=cat_id, user_id=user.id).first()
    if not category:
        return jsonify({"error": "Category not found"}), 404

    data = request.get_json()
    name = (data.get("name") or "").strip()
    prompt_instruction = (data.get("prompt_instruction") or "").strip()
    examples = data.get("examples")

    if name:
        if len(name) > 40:
            return jsonify({"error": "Name must be at most 40 characters"}), 400
        if not CATEGORY_NAME_RE.match(name):
            return jsonify({"error": "Name must be SCREAMING_SNAKE_CASE"}), 400
        if name != category.name:
            dup = CustomCategory.query.filter_by(user_id=user.id, name=name).first()
            if dup:
                return jsonify({"error": f"Category '{name}' already exists"}), 409
        category.name = name

    if prompt_instruction:
        if len(prompt_instruction) > 2000:
            return jsonify({"error": "Prompt instruction must be at most 2000 characters"}), 400
        category.prompt_instruction = prompt_instruction

    if examples is not None:
        if isinstance(examples, str):
            try:
                json.loads(examples)
            except json.JSONDecodeError:
                return jsonify({"error": "Examples must be a valid JSON array"}), 400
        else:
            examples = json.dumps(examples)
        category.examples = examples

    db.session.commit()
    return jsonify({
        "message": "Category updated",
        "category": {
            "id": category.id,
            "name": category.name,
            "prompt_instruction": category.prompt_instruction,
            "examples": category.examples,
            "created_at": category.created_at.isoformat() if category.created_at else None,
        }
    }), 200


@auth_bp.route("/user/<user_id>/categories/<int:cat_id>", methods=["DELETE"])
def delete_category(user_id, cat_id):
    """Delete a custom category."""
    user = User.query.filter_by(email=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    category = CustomCategory.query.filter_by(id=cat_id, user_id=user.id).first()
    if not category:
        return jsonify({"error": "Category not found"}), 404

    db.session.delete(category)
    db.session.commit()
    return jsonify({"message": "Category deleted"}), 200

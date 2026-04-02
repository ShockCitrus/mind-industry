import os
import dotenv
import requests

from flask import Blueprint, render_template, request, flash, redirect, url_for, session


auth = Blueprint('auth', __name__)
dotenv.load_dotenv()

AUTH_API_URL = f"{os.environ.get('AUTH_API_URL', 'http://auth:5002/')}/auth"
MIND_WORKER_URL = os.environ.get('MIND_WORKER_URL')


def validate_password(password, password_rep):
    """Validate account strength."""
    veredict = (True, "Valid account.")

    if len(password) < 8:
        flash("Password must be at least 8 characters", "danger")
        veredict = (False, "Invalid password length.")
    elif password != password_rep:
        flash("Passwords do not match", "danger")
        veredict = (False, "Passwords do not match.")
    elif not any(c in '!@#$%^&*(),.?":{}|<>_+=-[]\\;/~`' for c in password):
        flash("Password must contain at least one special character", "danger")
        veredict = (False, "Password must contain a special character.")
    return veredict

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # send login auth
        try:
            print(f"{AUTH_API_URL}/login")
            response = requests.post(f"{AUTH_API_URL}/login", json={
                "email": email,
                "password": password
            })
        except requests.exceptions.RequestException:
            flash("Authentication service unavailable.", "danger")
            return render_template('login.html')

        if response.status_code == 200:
            data = response.json()
            session['user_id'] = data.get('user_id')
            session['username'] = data.get('username')
            # flash("Login successful", "success")
            return redirect(url_for('views.home'))
        else:
            flash(response.json().get('error', 'Login failed'), "danger")

    return render_template('login.html')


@auth.route('/logout', methods=['GET'])
def logout():
    try:
        requests.get(f"{MIND_WORKER_URL}/cancel_detection", params={"email": session['user_id']})
    except:
        pass
    session.pop('user_id', None)
    flash("You have been logged out", "success")
    return redirect(url_for('auth.login'))


@auth.route('/sign-up', methods=['GET', 'POST'])
def sign_up():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        password_rep = request.form.get('password_rep')

        if not validate_password(password, password_rep)[0]:
            return render_template('sign_up.html', email=email, username=username)

        try:
            response = requests.post(f"{AUTH_API_URL}/register", json={
                "email": email,
                "username": username,
                "password": password,
                "password_rep": password_rep
            })
        except requests.exceptions.RequestException:
            flash("Authentication service unavailable.", "danger")
            return render_template('sign_up.html', email=email, username=username)

        if response.status_code == 201:
            # flash("Account created successfully", "success")
            login_response = requests.post(f"{AUTH_API_URL}/login", json={
                "email": email,
                "password": password
            })
            if login_response.status_code == 200:
                session['user_id'] = login_response.json().get('user_id')
                session['username'] = login_response.json().get('username')
            return redirect(url_for('views.home'))
        else:
            flash(response.json().get("error", "Error in server."), "danger")
            return render_template('sign_up.html', email=email, username=username)

    return render_template('sign_up.html')

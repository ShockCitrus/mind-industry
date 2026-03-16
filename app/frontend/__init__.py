import os

from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from flask_session import Session


load_dotenv()  # Load environment variables from .env file


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config['SECRET_KEY'] = os.getenv("WEB_APP_KEY")
    app.config['SESSION_TYPE'] = 'filesystem'

    Session(app)

    CORS(app, resources={r"/*": {"origins": "*"}})  # Enable CORS for all routes

    # Throttle noisy health-check log lines
    import logging
    import time

    class ThrottleHealthCheckFilter(logging.Filter):
        """Only log /api/preprocess_status once every `interval` seconds."""
        def __init__(self, interval=30):
            super().__init__()
            self._interval = interval
            self._last_logged = 0

        def filter(self, record):
            msg = record.getMessage()
            if "/api/preprocess_status" in msg:
                now = time.monotonic()
                if now - self._last_logged < self._interval:
                    return False
                self._last_logged = now
            return True

    logging.getLogger("werkzeug").addFilter(ThrottleHealthCheckFilter(30))

    from auth import auth
    from views import views
    from profile import profile_bp
    from datasets import dataset_bp
    from preprocessing import preprocess

    app.register_blueprint(preprocess, url_prefix='/')
    app.register_blueprint(profile_bp, url_prefix='/')
    app.register_blueprint(dataset_bp, url_prefix='/')
    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')

    @app.after_request
    def add_cache_control(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    
    return app

import os
import sys
import time
import logging
import dotenv
import shutil

from flask import Flask, request, jsonify


app = Flask(__name__)
PORT = 5001
dotenv.load_dotenv()


# Throttle noisy polling log lines (/status/<step_id>)
class ThrottleStatusFilter(logging.Filter):
    """Only log /status/ polling requests once every `interval` seconds."""
    def __init__(self, interval=30):
        super().__init__()
        self._interval = interval
        self._last_logged = 0

    def filter(self, record):
        msg = record.getMessage()
        if "/status/" in msg:
            now = time.monotonic()
            if now - self._last_logged < self._interval:
                return False
            self._last_logged = now
        return True

logging.getLogger("werkzeug").addFilter(ThrottleStatusFilter(30))

@app.before_request
def cancel_active_pipeline():
    # These endpoints are safe to call while the pipeline is running and must
    # NOT cancel it. All result-fetching and status-polling paths go here.
    SAFE_PATHS = {
        "/log_detection",
        "/pipeline_status",
        "/detection/pipeline_status",
        "/detection/result_mind",
        "/detection/update_results",
        "/cancel_detection",
        "/stream_detection",
    }
    if request.path in SAFE_PATHS:
        return

    email = request.args.get("email") or request.args.get("user_id")
    if not email and request.is_json:
        data = request.get_json()
        email = data.get("email") or data.get("user_id")
    if not email:
        return
    
    from detection import active_processes, ACTIVE_OLLAMA_SERVERS, lock
    with lock:
        if email in active_processes:
            proc_info = active_processes[email]
            proc = proc_info["process"]
            print(f"Cancelling active pipeline for {email} due to request {request.path}", file=sys.__stdout__)

            if proc.is_alive():
                proc.terminate()

            if proc_info['llm'] is not None:
                ACTIVE_OLLAMA_SERVERS.remove(proc_info['llm'])

            del active_processes[email]
            print(active_processes)

@app.route('/pipeline_status', methods=['GET'])
def pipeline_status():
    data = request.get_json()
    print(data)
    email = data.get("email")
    TM = data.get("TM")
    topics = data.get("topics")
    if not email or not TM or not topics:
        return jsonify({"error": "No email nor TM nor topics provided"}), 400
    
    from detection import active_processes, lock, OUTPUT_QUEUE
    with lock:
        if email in active_processes:
            proc = active_processes[email]["process"]
            if proc.is_alive():
                return jsonify({"status": "running"}), 200
        try:
            result = OUTPUT_QUEUE.get_nowait()
        except:
            result = -1

        if result == 0:
            return jsonify({"status": "finished"}), 200
        else:
            try:
                from detection import _topics_to_path_slug
                topics_slug = _topics_to_path_slug(topics)
                shutil.rmtree(f'/data/{email}/4_Detection/{TM}_contradiction/{topics_slug}/')
            except: pass
            return jsonify({"status": "error"}), 500

@app.route('/cancel_detection', methods=['GET'])
def route_cancel_detection():
    return {}, 200

if __name__ == '__main__':
    from dataset import datasets_bp
    from detection import detection_bp
    from preprocessing import preprocessing_bp
    
    app.register_blueprint(datasets_bp, url_prefix='/')
    app.register_blueprint(detection_bp, url_prefix='/')
    app.register_blueprint(preprocessing_bp, url_prefix='/')
    
    app.run(host='0.0.0.0', port=PORT, threaded=True)

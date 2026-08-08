from flask import Flask, request, jsonify
import threading
import app as scraper_app

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    return "MITS scraper ready", 200


@app.route("/start", methods=["POST"])
def start():
    data = request.get_json(silent=True) or request.form
    roll = data.get("roll_no") if data else None
    password = data.get("password") if data else None
    if not roll or not password:
        return jsonify(error="missing roll_no or password"), 400

    # Pre-fill credentials and signal the existing HTTP handler to proceed
    scraper_app.CredentialsHandler.credentials = {"roll_no": roll, "password": password}
    scraper_app.CredentialsHandler.processing = True
    scraper_app.CredentialsHandler.event.set()

    def run_scraper():
        try:
            scraper_app.run_attendance_scraper()
        except Exception as e:
            scraper_app.add_log(f"Scraper error: {e}")

    threading.Thread(target=run_scraper, daemon=True).start()
    return jsonify(status="started"), 202

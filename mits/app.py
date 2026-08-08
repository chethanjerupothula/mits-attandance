from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import urllib.parse
import webbrowser
import socket
import json
import re
from pathlib import Path
import time
from flask import Flask, request, jsonify, redirect
import os


# ---------------------------
# Web UI login form and results page
# ---------------------------
LOGIN_FORM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Enter MITS credentials</title>
    <style>
        body { font-family: Inter, Arial, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .card { width: min(460px, calc(100% - 32px)); background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(148, 163, 184, 0.15); border-radius: 24px; box-shadow: 0 24px 60px rgba(15, 23, 42, 0.45); padding: 28px; backdrop-filter: blur(14px); }
        h1 { margin: 0 0 12px; font-size: 1.85rem; color: #f8fafc; }
        p { margin: 0 0 24px; color: #94a3b8; line-height: 1.6; }
        label { display: block; margin-bottom: 10px; font-size: 0.95rem; color: #cbd5e1; }
        input { width: 100%; padding: 14px 14px; border-radius: 14px; border: 1px solid rgba(148, 163, 184, 0.28); background: #0f172a; color: #f8fafc; font-size: 1rem; outline: none; transition: all 0.25s ease; }
        input:focus { border-color: #60a5fa; box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.12); }
        button { width: 100%; padding: 14px 16px; border: none; border-radius: 14px; background: linear-gradient(135deg, #3b82f6 0%, #0ea5e9 100%); color: white; font-size: 1rem; font-weight: 600; cursor: pointer; transition: transform 0.2s ease, box-shadow 0.2s ease; }
        button:hover { transform: translateY(-1px); box-shadow: 0 14px 30px rgba(14, 165, 233, 0.25); }
        .footer { margin-top: 16px; text-align: center; color: #94a3b8; font-size: 0.92rem; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Student Login</h1>
        <p>Enter your MITS roll number and password. The attendance summary will appear here after login.</p>
        <form method="POST">
            <label for="roll_no">Roll number</label>
            <input id="roll_no" name="roll_no" required autofocus>
            <label for="password">Password</label>
            <input id="password" name="password" type="password" required>
            <button type="submit">Continue</button>
        </form>
        <div class="footer">Secure local page — data stays on your machine.</div>
    </div>
</body>
</html>
"""

PROCESSING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Processing Attendance</title>
    <style>
        body { font-family: Inter, Arial, sans-serif; background: #020617; color: #e2e8f0; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .sheet { width: min(580px, calc(100% - 36px)); background: rgba(15, 23, 42, 0.93); border: 1px solid rgba(148, 163, 184, 0.14); border-radius: 28px; padding: 34px; text-align: center; backdrop-filter: blur(16px); }
        .spinner { width: 72px; height: 72px; margin: 0 auto 26px; border: 7px solid rgba(148, 163, 184, 0.25); border-top-color: #38bdf8; border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        h1 { margin: 0 0 18px; font-size: 1.9rem; color: #f8fafc; }
        p { margin: 0 0 18px; color: #cbd5e1; line-height: 1.7; }
        .log-box { margin-top: 18px; max-height: 220px; overflow-y: auto; text-align: left; border-radius: 16px; background: rgba(15, 23, 42, 0.85); padding: 18px; border: 1px solid rgba(148, 163, 184, 0.12); color: #cbd5e1; font-size: 0.92rem; }
        .log-entry { margin-bottom: 10px; }
        .log-entry:last-child { margin-bottom: 0; }
    </style>
</head>
<body>
    <div class="sheet">
        <div class="spinner"></div>
        <h1>Getting your attendance</h1>
        <p>The browser page will show logs and results as the script runs.</p>
        <div class="log-box" id="logBox"></div>
    </div>
    <script>
        async function refreshStatus() {
            try {
                const res = await fetch('/status');
                const data = await res.json();
                const logBox = document.getElementById('logBox');
                logBox.innerHTML = data.logs.map(line => `<div class='log-entry'>${line}</div>`).join('');
                if (data.results_ready) {
                    window.location.href = '/results';
                    return;
                }
            } catch (err) {
                console.error(err);
            }
            setTimeout(refreshStatus, 1200);
        }
        refreshStatus();
    </script>
</body>
</html>
"""

RESULTS_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>MITS Attendance Results</title>
    <style>
        body {{ font-family: Inter, Arial, sans-serif; background: #0b1120; color: #e2e8f0; margin: 0; min-height: 100vh; }}
        .page {{ max-width: 1100px; margin: 0 auto; padding: 28px 24px 40px; }}
        .hero {{ display: grid; gap: 22px; margin-bottom: 28px; }}
        .hero h1 {{ margin: 0; font-size: clamp(2rem, 3vw, 3.25rem); }}
        .badge {{ display: inline-flex; gap: 10px; flex-wrap: wrap; align-items: center; padding: 14px 18px; border-radius: 18px; background: rgba(14, 165, 233, 0.14); color: #dbeafe; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 18px; margin: 24px 0 32px; }}
        .card {{ background: rgba(15, 23, 42, 0.98); border: 1px solid rgba(148, 163, 184, 0.16); border-radius: 22px; padding: 20px 22px; box-shadow: 0 28px 70px rgba(15, 23, 42, 0.26); }}
        .card strong {{ display: block; font-size: 0.95rem; color: #94a3b8; margin-bottom: 8px; }}
        .card span {{ display: block; font-size: 1.65rem; font-weight: 700; color: #f8fafc; }}
        .table-wrap {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; background: rgba(15, 23, 42, 0.96); border: 1px solid rgba(148, 163, 184, 0.12); }}
        th, td {{ padding: 14px 16px; border-bottom: 1px solid rgba(148, 163, 184, 0.12); }}
        th {{ text-align: left; background: rgba(15, 23, 42, 0.95); color: #cbd5e1; font-size: 0.97rem; }}
        td {{ color: #f8fafc; font-size: 0.98rem; }}
        tr:hover {{ background: rgba(59, 130, 246, 0.08); }}
        .center {{ text-align: center; }}
        .status {{ display: inline-flex; align-items: center; gap: 8px; font-size: 0.95rem; color: #38bdf8; }}
        .percent-green {{ color: #22c55e; font-weight: 700; }}
        .percent-blue {{ color: #38bdf8; font-weight: 700; }}
        .percent-orange {{ color: #f97316; font-weight: 700; }}
        .percent-red {{ color: #ef4444; font-weight: 700; }}
        .legend {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; margin-bottom: 20px; }}
        .legend-item {{ padding: 12px 14px; border-radius: 16px; background: rgba(15, 23, 42, 0.92); border: 1px solid rgba(148, 163, 184, 0.14); color: #cbd5e1; }}
        .legend-item span {{ display: inline-block; width: 12px; height: 12px; border-radius: 9999px; margin-right: 10px; vertical-align: middle; }}
        .legend-item.green span {{ background: #22c55e; }}
        .legend-item.blue span {{ background: #38bdf8; }}
        .legend-item.orange span {{ background: #f97316; }}
        .legend-item.red span {{ background: #ef4444; }}
        .footer {{ margin-top: 30px; color: #94a3b8; font-size: 0.94rem; }}
    </style>
</head>
<body>
    <div class="page">
        <div class="hero">
            <div>
                <span class="badge">MITS Attendance Summary</span>
                <h1>Attendance results for {student_name}</h1>
                <p class="status">Roll number: {roll_no} · Last login: {last_login}</p>
            </div>
        </div>

        <div class="cards">
            <div class="card"><strong>Total subjects</strong><span>{subject_count}</span></div>
            <div class="card"><strong>Total attended</strong><span>{total_attended_classes}</span></div>
            <div class="card"><strong>Total conducted</strong><span>{total_conducted_classes}</span></div>
            <div class="card"><strong>Average attendance</strong><span>{average_attendance:.2f}%</span></div>
            <div class="card"><strong>Overall attendance</strong><span>{overall_attendance:.2f}%</span></div>
        </div>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th class="center">S.NO</th>
                        <th>Subject Code</th>
                        <th class="center">Classes Attended</th>
                        <th class="center">Total Conducted</th>
                        <th class="center">Attendance %</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>

        <div class="footer">Refresh the page after a moment if the summary is still loading.</div>
    </div>
</body>
</html>
"""

LOG_MESSAGES = []

# Flask app to host the UI/API when running `python app.py`
app = Flask(__name__)

def add_log(message: str):
    timestamp = time.strftime("%H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    LOG_MESSAGES.append(log_line)

class CredentialsHandler(BaseHTTPRequestHandler):
    credentials = {}
    event = threading.Event()
    results_html = ""
    results_ready = threading.Event()
    processing = False

    def log_message(self, format, *args):
        return

    def send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def send_json(self, obj):
        body = json.dumps(obj)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        if self.path.startswith('/status'):
            self.send_json({
                'processing': CredentialsHandler.processing,
                'results_ready': CredentialsHandler.results_ready.is_set(),
                'logs': LOG_MESSAGES,
            })
            return

        if self.path.startswith('/results') and CredentialsHandler.results_ready.is_set():
            self.send_html(CredentialsHandler.results_html)
            return

        if CredentialsHandler.results_ready.is_set():
            self.send_html(CredentialsHandler.results_html)
            return

        if CredentialsHandler.processing:
            self.send_html(PROCESSING_HTML)
            return

        self.send_html(LOGIN_FORM_HTML)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        data = urllib.parse.parse_qs(body)
        roll_no = data.get("roll_no", [""])[0].strip()
        password = data.get("password", [""])[0]

        if not roll_no or not password:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing roll number or password")
            return

        CredentialsHandler.credentials = {"roll_no": roll_no, "password": password}
        CredentialsHandler.processing = True
        LOG_MESSAGES.clear()
        add_log("Credentials received")
        CredentialsHandler.event.set()
        self.send_html(PROCESSING_HTML)


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get_credentials_via_web():
    # If a PORT env var is set (Render / production), bind to 0.0.0.0 on that port
    if os.environ.get("PORT"):
        try:
            port = int(os.environ.get("PORT"))
        except Exception:
            port = find_free_port()
        host = "0.0.0.0"
    else:
        port = find_free_port()
        host = "127.0.0.1"

    server = HTTPServer((host, port), CredentialsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Prefer a public URL when available (platform-provided), otherwise show localhost
    public_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("PUBLIC_URL")
    if public_url:
        url = f"{public_url.rstrip('/')}/"
    else:
        # Use 127.0.0.1 for local runs, or the container bind address for deployed runs
        display_host = "127.0.0.1" if host == "127.0.0.1" else "<your-service-domain>"
        url = f"http://{display_host}:{port}/"

    add_log(f"Open this page to enter credentials: {url}")
    # Don't attempt to open a browser when running in a container/platform
    if host == "127.0.0.1":
        try:
            webbrowser.open(url)
        except Exception:
            pass

    if not CredentialsHandler.event.wait(timeout=600):
        server.shutdown()
        raise RuntimeError("Timed out waiting for credentials")

    return url, CredentialsHandler.credentials["roll_no"], CredentialsHandler.credentials["password"]


def dump_page_source(driver, name="attendance"):
    html_path = Path(f"{name}.html")
    text_path = Path(f"{name}.txt")
    html_path.write_text(driver.page_source, encoding="utf-8")
    body_text = driver.find_element(By.TAG_NAME, "body").text
    text_path.write_text(body_text, encoding="utf-8")
    add_log(f"Saved full page HTML to {html_path}")
    add_log(f"Saved full page text to {text_path}")
    print("\n=== PAGE TEXT DUMP START ===")
    for line in body_text.splitlines():
        if line.strip():
            print(line)
    print("=== PAGE TEXT DUMP END ===\n")


def switch_to_attendance_iframe(driver, wait):
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    add_log(f"Found {len(iframes)} iframe(s)")
    for i, iframe in enumerate(iframes):
        fid = iframe.get_attribute("id") or ""
        fname = iframe.get_attribute("name") or ""
        add_log(f"iframe[{i}] id={fid} name={fname}")

    if not iframes:
        return False

    for i, iframe in enumerate(iframes):
        driver.switch_to.default_content()
        driver.switch_to.frame(iframe)
        try:
            wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//table[.//th[contains(translate(normalize-space(text()), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'SUBJECT')]] | //table[.//th[contains(translate(normalize-space(text()), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'ATTENDANCE')]] | //table"
                    )
                )
            )
            add_log(f"Found attendance content inside iframe[{i}]")
            return True
        except TimeoutException:
            add_log(f"No attendance content in iframe[{i}]")
            continue

    driver.switch_to.default_content()
    return False


def wait_for_attendance_table(driver, wait):
    try:
        wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//table[.//th[contains(translate(normalize-space(text()), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'SUBJECT')]] | //table[.//th[contains(translate(normalize-space(text()), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'ATTENDANCE')]] | //table"
                )
            )
        )
        return True
    except TimeoutException:
        return False


def parse_attendance_text(text):
    cleaned = text.replace("|", " ").replace("\t", " ")
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]

    # Find the header section for the attendance grid.
    header_end = None
    for idx, line in enumerate(lines):
        uline = line.upper()
        if "ATTENDANCE %" in uline or "TOTAL CONDUCTED" in uline:
            header_end = idx + 1
        if header_end is not None and "ATTENDANCE %" in uline:
            break

    if header_end is None:
        for idx, line in enumerate(lines):
            if line.upper().startswith("SUBJECT CODE"):
                header_end = idx + 1
                break

    rows = []
    if header_end is not None:
        for i in range(header_end, len(lines), 5):
            chunk = lines[i:i + 5]
            if len(chunk) < 5:
                break
            if not chunk[0].isdigit():
                continue
            subject_code = chunk[1]
            attended = chunk[2]
            conducted = chunk[3]
            attendance_pct = chunk[4]
            if not attended.replace('.', '', 1).isdigit() or not conducted.replace('.', '', 1).isdigit() or not attendance_pct.replace('.', '', 1).isdigit():
                continue
            if "CHANGE PASSWORD" in subject_code.upper() or "LOGOUT" in subject_code.upper():
                continue
            rows.append((subject_code, attended, conducted, attendance_pct))

        if rows:
            return rows

    # Fallback: search for inline rows grouped by 5 values.
    for i in range(0, len(lines) - 4):
        if not lines[i].isdigit():
            continue
        subject_code = lines[i + 1]
        attended = lines[i + 2]
        conducted = lines[i + 3]
        attendance_pct = lines[i + 4]
        if not attended.replace('.', '', 1).isdigit() or not conducted.replace('.', '', 1).isdigit() or not attendance_pct.replace('.', '', 1).isdigit():
            continue
        if "CHANGE PASSWORD" in subject_code.upper() or "LOGOUT" in subject_code.upper():
            continue
        rows.append((subject_code, attended, conducted, attendance_pct))
        i += 4

    return rows


def extract_attendance_rows(driver, wait):
    add_log("Extracting attendance rows from page")
    tables = driver.find_elements(By.XPATH, "//table")
    add_log(f"Found {len(tables)} table(s)")
    rows = []

    for idx, table in enumerate(tables):
        table_html = table.get_attribute("outerHTML") or ""
        upper_html = table_html.upper()
        add_log(f"Inspecting table[{idx}] length={len(table_html)}")
        if "SUBJECT CODE" not in upper_html and "ATTENDANCE" not in upper_html and "CLASSES ATTENDED" not in upper_html:
            add_log(f"Skipping table[{idx}] because it does not look like attendance")
            continue

        table_rows = table.find_elements(By.XPATH, ".//tr")
        add_log(f"Examining {len(table_rows)} rows in table[{idx}]")
        for row in table_rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 5:
                subject_code = cols[1].text.strip()
                attended = cols[2].text.strip()
                conducted = cols[3].text.strip()
                attendance_pct = cols[4].text.strip()
            elif len(cols) == 4:
                subject_code = cols[0].text.strip()
                attended = cols[1].text.strip()
                conducted = cols[2].text.strip()
                attendance_pct = cols[3].text.strip()
            else:
                continue

            if not attendance_pct.replace('.', '', 1).isdigit():
                add_log(f"Skipping row with invalid percent: {[c.text for c in cols]}")
                continue
            if "CHANGE PASSWORD" in subject_code.upper() or "LOGOUT" in subject_code.upper():
                continue

            rows.append((subject_code, attended, conducted, attendance_pct))
            add_log(f"Found attendance row: {subject_code}, {attended}, {conducted}, {attendance_pct}")

        if rows:
            break

    if rows:
        add_log(f"Extracted {len(rows)} attendance row(s) from table")
        return rows

    add_log("No attendance rows found in tables, falling back to text parse")
    body_text = driver.execute_script("return document.documentElement.innerText")
    rows = parse_attendance_text(body_text)
    add_log(f"Fallback text parser found {len(rows)} rows")
    if not rows:
        dump_page_source(driver, "attendance_debug")
    return rows


def attendance_css_class(attendance_pct: str) -> str:
    try:
        pct = float(attendance_pct)
    except ValueError:
        return "percent-red"

    if pct >= 85:
        return "percent-green"
    if pct >= 70:
        return "percent-blue"
    if pct >= 59:
        return "percent-orange"
    return "percent-red"


def run_attendance_scraper(roll_no=None, password=None):
    # Allow passing credentials directly to avoid the internal web UI flow.
    if roll_no and password:
        BASE_URL = None
        ROLL_NO = roll_no
        PASSWORD = password
    else:
        BASE_URL, ROLL_NO, PASSWORD = get_credentials_via_web()
    add_log("Starting browser login flow")

    # ---------------------------
    # Chrome Setup
    # ---------------------------
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 30)

        # ---------------------------
        # Open Login Page
        # ---------------------------
        driver.get("http://mitsims.in/studentLogin.jsp?personType=student")

        # ---------------------------
        # Login
        # ---------------------------
        wait.until(
            EC.presence_of_element_located((By.ID, "userId"))
        ).send_keys(ROLL_NO)

        driver.find_element(By.ID, "password").send_keys(PASSWORD)
        driver.find_element(By.ID, "loginBtn").click()

        # Wait for dashboard
        time.sleep(8)

        add_log("Logged in")
        add_log(f"Dashboard URL: {driver.current_url}")

        # ---------------------------
        # Print dashboard menu items
        # ---------------------------
        print("\nAvailable menu items:")

        links = driver.find_elements(By.TAG_NAME, "a")
        for i, link in enumerate(links):
            txt = link.text.strip()
            if txt:
                print(i, txt)

        # ---------------------------
        # Click Attendance
        # ---------------------------
        attendance = None
        try:
            attendance = wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//*[contains(translate(normalize-space(text()), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'ATTENDANCE')]"
                    )
                )
            )
        except TimeoutException:
            add_log("Attendance button not clickable by text search")

        if attendance is None:
            possible_buttons = driver.find_elements(By.XPATH, "//a|//button|//div[@role='button']")
            for btn in possible_buttons:
                txt = btn.text.strip().upper()
                if 'ATTENDANCE' in txt:
                    attendance = btn
                    add_log(f"Found attendance element by fallback text: {txt}")
                    break

        if attendance is None:
            dashboard_html = driver.find_element(By.TAG_NAME, 'body').get_attribute('innerHTML')
            with open('dashboard_dump.html', 'w', encoding='utf-8') as f:
                f.write(dashboard_html)
            add_log('Saved dashboard HTML to dashboard_dump.html for debugging')
            raise RuntimeError('Attendance button not found; dumped dashboard HTML to dashboard_dump.html')

        attendance.click()
        add_log("Attendance page opened")

        if not wait_for_attendance_table(driver, wait):
            add_log("Attendance table not found in main document after click")
            if switch_to_attendance_iframe(driver, wait):
                add_log("Switched to iframe for attendance content")
            else:
                add_log("No attendance table found after iframe check")
                dump_page_source(driver, "attendance_debug")

        # ---------------------------
        # Extract page text
        # ---------------------------
        add_log("Extracting page body text")
        body_text = driver.find_element(By.TAG_NAME, "body").text
        add_log("Page body text extracted")

        # ---------------------------
        # Extract attendance table from page text
        # ---------------------------
        attendance_rows = extract_attendance_rows(driver, wait)
        student_name = links[1].text.strip() if len(links) > 1 else ""
        last_login = ""

        total_attended_classes = 0
        total_conducted_classes = 0
        total_attendance_pct = 0
        attendance_count = 0

        last_login_match = re.search(r"Last Login[:\s]+([0-9A-Za-z/]+)", body_text)
        if last_login_match:
            last_login = last_login_match.group(1)

        if not attendance_rows:
            add_log("No rows found with table extraction, falling back to text parsing")

            lines = [line.strip() for line in body_text.splitlines() if line.strip()]
            start_idx = None
            for idx, line in enumerate(lines):
                if line.upper() == "S.NO":
                    start_idx = idx + 1
                    break

            add_log(f"Found attendance table start at line {start_idx}")

            if start_idx is None:
                start_idx = 0

            end_idx = len(lines)
            for idx in range(start_idx, len(lines)):
                if lines[idx].startswith("Note") or lines[idx].startswith("@"):
                    end_idx = idx
                    break

            attendance_lines = lines[start_idx:end_idx]

            for i in range(0, len(attendance_lines), 5):
                chunk = attendance_lines[i:i + 5]
                if len(chunk) < 5:
                    break
                if not chunk[0].isdigit():
                    break

                subject_code = chunk[1]
                attended = chunk[2]
                conducted = chunk[3]
                attendance_pct = chunk[4]

                try:
                    total_attended_classes += float(attended)
                    total_conducted_classes += float(conducted)
                    total_attendance_pct += float(attendance_pct)
                    attendance_count += 1
                except ValueError:
                    pass

                attendance_rows.append((subject_code, attended, conducted, attendance_pct))
        else:
            add_log("Attendance rows extracted from table")
            for subject_code, attended, conducted, attendance_pct in attendance_rows:
                try:
                    total_attended_classes += float(attended)
                    total_conducted_classes += float(conducted)
                    total_attendance_pct += float(attendance_pct)
                    attendance_count += 1
                except ValueError:
                    pass

        for row in attendance_rows:
            print("Subject:", row[0], "Attended:", row[1], "Conducted:", row[2], "Percent:", row[3])

        rows_html = ""
        for index, row in enumerate(attendance_rows, start=1):
            subject_code, attended, conducted, attendance_pct = row
            percent_class = attendance_css_class(attendance_pct)
            rows_html += (
                f"<tr>"
                f"<td class=\"center\">{index}</td>"
                f"<td>{subject_code}</td>"
                f"<td class=\"center\">{attended}</td>"
                f"<td class=\"center\">{conducted}</td>"
                f"<td class=\"center {percent_class}\">{attendance_pct}%</td>"
                f"</tr>\n"
            )

        subject_count = attendance_count
        average_attendance = total_attendance_pct / attendance_count if attendance_count else 0
        overall_attendance = (
            total_attended_classes / total_conducted_classes * 100
            if total_conducted_classes else 0
        )

        results_html = RESULTS_HTML_TEMPLATE.format(
            student_name=student_name,
            roll_no=ROLL_NO,
            last_login=last_login,
            subject_count=subject_count,
            total_attended_classes=int(total_attended_classes),
            total_conducted_classes=int(total_conducted_classes),
            average_attendance=average_attendance,
            overall_attendance=overall_attendance,
            rows_html=rows_html,
        )

        CredentialsHandler.results_html = results_html
        CredentialsHandler.results_ready.set()
        add_log("Attendance results are ready")
    finally:
        if driver is not None:
            driver.quit()


@app.route("/", methods=["GET"])
def index():
    if CredentialsHandler.results_ready.is_set():
        return CredentialsHandler.results_html
    if CredentialsHandler.processing:
        return PROCESSING_HTML
    return LOGIN_FORM_HTML


@app.route("/start", methods=["POST"])
def start():
    data = request.form.to_dict() or request.get_json(silent=True) or {}
    roll = data.get("roll_no")
    password = data.get("password")
    if not roll or not password:
        return "Missing roll_no or password", 400

    CredentialsHandler.credentials = {"roll_no": roll, "password": password}
    CredentialsHandler.processing = True
    CredentialsHandler.results_ready.clear()
    LOG_MESSAGES.clear()
    add_log("Credentials received via /start")

    # Dry-run mode: return instant fake results for quick testing
    if request.args.get("dry") == "1" or roll == "dry":
        fake_rows = [
            ("MATH101", "28", "30", "93.33"),
            ("PHY102", "24", "30", "80.00"),
        ]
        rows_html = ""
        for index, row in enumerate(fake_rows, start=1):
            subject_code, attended, conducted, attendance_pct = row
            percent_class = attendance_css_class(attendance_pct)
            rows_html += (
                f"<tr>"
                f"<td class=\"center\">{index}</td>"
                f"<td>{subject_code}</td>"
                f"<td class=\"center\">{attended}</td>"
                f"<td class=\"center\">{conducted}</td>"
                f"<td class=\"center {percent_class}\">{attendance_pct}%</td>"
                f"</tr>\n"
            )

        results_html = RESULTS_HTML_TEMPLATE.format(
            student_name="Test Student",
            roll_no=roll,
            last_login=time.strftime("%Y-%m-%d"),
            subject_count=len(fake_rows),
            total_attended_classes=52,
            total_conducted_classes=60,
            average_attendance=86.66,
            overall_attendance=86.66,
            rows_html=rows_html,
        )
        CredentialsHandler.results_html = results_html
        CredentialsHandler.results_ready.set()
        add_log("Dry-run results ready")
        return results_html, 200

    thread = threading.Thread(target=run_attendance_scraper, args=(roll, password), daemon=True)
    thread.start()
    return PROCESSING_HTML, 202


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        'processing': CredentialsHandler.processing,
        'results_ready': CredentialsHandler.results_ready.is_set(),
        'logs': LOG_MESSAGES,
    })


@app.route("/results", methods=["GET"])
def results():
    if CredentialsHandler.results_ready.is_set():
        return CredentialsHandler.results_html
    return "Results not ready", 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

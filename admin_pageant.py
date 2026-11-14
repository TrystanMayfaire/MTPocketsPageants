import os
import sys
import subprocess
from dotenv import load_dotenv
from update_event import sync_current_pageant
from flask import Flask, request, render_template_string, Response, stream_with_context

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load environment variables
possible_env_paths = [
    os.path.join(BASE_DIR, "secrets", ".env"),
    os.path.join(BASE_DIR, ".env"),
    "/home/mtpocketstheatre/secrets/.env",
    os.path.expanduser("~/secrets/.env")
]
for env_path in possible_env_paths:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break

IS_PRODUCTION = (
    os.environ.get("PYTHONANYWHERE_SITE") is not None
    or os.environ.get("APP_ENV") == "production"
)

# Separate password variable dedicated to pageant administration
PAGEANT_ADMIN_PASSWORD = os.environ.get("PAGEANT_ADMIN_PASSWORD") or os.environ.get("PAGEANT_PASSWORD", "mtpockets2026")
RETURN_URL = "/pageants/" if IS_PRODUCTION else "http://127.0.0.1:8050/"

admin_app = Flask(__name__)

ADMIN_HTML = '''
<!doctype html>
<html lang="en">
<head>
    <title>Pageant Admin Sync</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light d-flex align-items-center justify-content-center" style="min-height: 100vh;">
    <div class="card shadow p-4" style="max-width: 480px; width: 100%;">
        <h3 class="mb-2 text-center fw-bold">Pageant Site Sync</h3>
        <p class="text-muted small text-center mb-4">
            Enter the pageant admin password to pull the latest Google Form, flyer, and expiration date from Google Drive.
        </p>
        
        <div class="mb-3">
            <label class="form-label fw-bold small">Pageant Admin Password</label>
            <input type="password" id="adminPassword" class="form-control" required autofocus>
        </div>
        
        <button type="button" id="syncButton" onclick="startSync()" class="btn btn-primary w-100 fw-bold">Sync with Google Drive</button>
        
        <!-- Live Status Console Box -->
        <div id="logConsole" style="display: none; margin-top: 15px; background: #1e1e1e; color: #00ff00; padding: 12px; font-family: monospace; font-size: 0.85rem; border-radius: 4px; height: 160px; overflow-y: auto;">
            <div id="logContent">Initializing sync...<br></div>
        </div>

        <a href="{{ return_url }}" class="btn btn-link btn-sm w-100 mt-3 text-decoration-none">← Return to Pageant Registration</a>
    </div>

<script>
function startSync() {
    const password = document.getElementById('adminPassword').value;
    const btn = document.getElementById('syncButton');
    const consoleBox = document.getElementById('logConsole');
    const logContent = document.getElementById('logContent');
    
    if (!password) {
        alert("Please enter the admin password.");
        return;
    }
    
    // Force the console box to become visible immediately
    consoleBox.style.display = "block";
    btn.disabled = true;
    btn.innerText = "Syncing...";
    logContent.innerHTML = "Connecting to sync stream...<br>";

    // Connect to the Flask Server-Sent Events stream
    const eventSource = new EventSource("/admin/sync-progress?password=" + encodeURIComponent(password));

    eventSource.onmessage = function(event) {
        logContent.innerHTML += event.data + "<br>";
        consoleBox.scrollTop = consoleBox.scrollHeight;

        if (event.data.includes("[COMPLETE]") || event.data.includes("[FAILED]")) {
            eventSource.close();
            btn.disabled = false;
            btn.innerText = "Run Google Drive Sync Again";
        }
    };

    eventSource.onerror = function(err) {
        logContent.innerHTML += "<span style='color: orange;'>Stream closed. Check if sync completed.</span><br>";
        eventSource.close();
        btn.disabled = false;
        btn.innerText = "Run Google Drive Sync";
    };
}
</script>
</body>
</html>
'''

@admin_app.route('/', methods=['GET'])
@admin_app.route('/admin', methods=['GET'])
def pageant_admin():
    return render_template_string(ADMIN_HTML, return_url=RETURN_URL)

@admin_app.route('/admin/sync-progress')
def sync_progress():
    password = request.args.get('password', '')

    @stream_with_context
    def generate():
        if password != PAGEANT_ADMIN_PASSWORD:
            yield "data: ERROR: Incorrect password provided.<br>\n\n"
            yield "data: [FAILED]\n\n"
            return

        yield "data: Starting Google Drive synchronization...\n\n"

        # Run sync_current_pageant() in an unbuffered subprocess (-u)
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", "from update_event import sync_current_pageant; sync_current_pageant()"],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Stream each print() line from update_event.py as it happens
        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                yield f"data: {clean_line}<br>\n\n"

        process.wait()

        if process.returncode == 0:
            yield "data: <span style='color: #00ffff;'>[COMPLETE]</span><br>\n\n"
        else:
            yield "data: <span style='color: red;'>[FAILED]</span><br>\n\n"

    return Response(generate(), mimetype='text/event-stream', headers={'X-Accel-Buffering': 'no'})

server = admin_app

if __name__ == "__main__":
    admin_app.run(debug=True, port=5001)
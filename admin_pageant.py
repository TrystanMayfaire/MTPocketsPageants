import os
import json
from flask import Flask, request, render_template_string
from dotenv import load_dotenv
from update_event import sync_current_pageant

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
    <div class="card shadow p-4" style="max-width: 420px; width: 100%;">
        <h3 class="mb-2 text-center fw-bold">Pageant Site Sync</h3>
        <p class="text-muted small text-center mb-4">
            Enter the pageant admin password to pull the latest Google Form, flyer, and expiration date from Google Drive.
        </p>
        {% if message %}
            <div class="alert {{ 'alert-success' if success else 'alert-danger' }} small" role="alert">
                {{ message }}
            </div>
        {% endif %}
        <form method="post">
            <div class="mb-3">
                <label class="form-label fw-bold small">Pageant Admin Password</label>
                <input type="password" name="password" class="form-control" required autofocus>
            </div>
            <button type="submit" class="btn btn-primary w-100 fw-bold">Sync with Google Drive</button>
        </form>
        <a href="{{ return_url }}" class="btn btn-link btn-sm w-100 mt-3 text-decoration-none">← Return to Pageant Registration</a>
    </div>
</body>
</html>
'''

# Handle root '/' (when mounted at /pageants/admin via WSGI) as well as '/admin'
@admin_app.route('/', methods=['GET', 'POST'])
@admin_app.route('/admin', methods=['GET', 'POST'])
def pageant_admin():
    message = ""
    success = False

    if request.method == 'POST':
        if request.form.get('password') == PAGEANT_ADMIN_PASSWORD:
            try:
                sync_current_pageant()
                message = "Success! Pageant site synced with Google Drive. Refresh the registration page to view updates."
                success = True
            except Exception as e:
                message = f"Sync failed: {e}"
        else:
            message = "Incorrect password. Please try again."

    return render_template_string(ADMIN_HTML, message=message, success=success, return_url=RETURN_URL)

# Expose server for WSGI
server = admin_app

if __name__ == "__main__":
    # Run locally on port 5001 so it doesn't collide with Dash on port 8050
    admin_app.run(debug=True, port=5001)
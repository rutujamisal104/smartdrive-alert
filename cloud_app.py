```python
import os
import time
import secrets
from threading import Lock
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

API_TOKEN = os.environ.get("SMARTDRIVE_API_TOKEN", "")
lock = Lock()

latest_status = {
    "monitoring": False,
    "ear": 0.0,
    "mar": 0.0,
    "head_direction": "Unknown",
    "warning": "Waiting for laptop",
    "last_update": None
}

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SmartDrive Alert</title>
    <style>
        body {
            margin: 0;
            padding: 25px;
            background: #0b1220;
            color: white;
            font-family: Arial, sans-serif;
        }
        h1 { color: #60a5fa; }
        .card {
            background: #172033;
            padding: 20px;
            margin: 15px 0;
            border-radius: 12px;
        }
        .value { font-size: 28px; font-weight: bold; }
        .muted { color: #aab7cc; }
    </style>
</head>
<body>
    <h1>SmartDrive Alert</h1>
    <p class="muted">Live Driver Monitoring Dashboard</p>

    <div class="card">
        <h3>Connection Status</h3>
        <div class="value" id="connection">Connecting...</div>
        <p id="updated" class="muted">Waiting for data</p>
    </div>

    <div class="card">
        <h3>Eye Aspect Ratio (EAR)</h3>
        <div class="value" id="ear">--</div>
    </div>

    <div class="card">
        <h3>Mouth Aspect Ratio (MAR)</h3>
        <div class="value" id="mar">--</div>
    </div>

    <div class="card">
        <h3>Head Direction</h3>
        <div class="value" id="head">Unknown</div>
    </div>

    <div class="card">
        <h3>Monitoring Warning</h3>
        <div class="value" id="warning">Waiting for laptop</div>
    </div>

    <script>
        async function refreshDashboard() {
            try {
                const response = await fetch('/status');
                if (!response.ok) throw new Error('Status unavailable');

                const data = await response.json();

                document.getElementById('ear').textContent =
                    Number(data.ear).toFixed(3);
                document.getElementById('mar').textContent =
                    Number(data.mar).toFixed(3);
                document.getElementById('head').textContent =
                    data.head_direction;
                document.getElementById('warning').textContent =
                    data.warning;

                const lastUpdate = data.last_update
                    ? Date.parse(data.last_update)
                    : 0;

                const fresh = lastUpdate &&
                    (Date.now() - lastUpdate < 10000);

                document.getElementById('connection').textContent =
                    fresh && data.monitoring ? 'LIVE' : 'OFFLINE';

                document.getElementById('updated').textContent =
                    fresh ? 'Latest data received' :
                    'Waiting for a fresh update from your laptop';
            } catch (error) {
                document.getElementById('connection').textContent =
                    'OFFLINE';
            }
        }

        refreshDashboard();
        setInterval(refreshDashboard, 1000);
    </script>
</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(DASHBOARD_HTML)


@app.route("/status")
def status():
    with lock:
        data = latest_status.copy()

    # Mark the laptop offline if updates stop arriving.
    if not data["last_update"]:
        data["monitoring"] = False
    else:
        from datetime import datetime, timezone
        updated = datetime.fromisoformat(
            data["last_update"].replace("Z", "+00:00")
        )
        age = (datetime.now(timezone.utc) - updated).total_seconds()
        if age > 10:
            data["monitoring"] = False

    return jsonify(data)


@app.route("/api/update", methods=["POST"])
def receive_update():
    if not API_TOKEN:
        return jsonify({"error": "Server token is not configured"}), 503

    supplied_token = request.headers.get("X-API-Token", "")
    if not secrets.compare_digest(supplied_token, API_TOKEN):
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body required"}), 400

    try:
        ear = float(payload.get("ear", 0))
        mar = float(payload.get("mar", 0))
        if not (0 <= ear <= 2 and 0 <= mar <= 5):
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid EAR or MAR"}), 400

    head = str(payload.get("head_direction", "Unknown"))[:40]
    warning = str(payload.get("warning", "Normal"))[:120]
    monitoring = payload.get("monitoring") is True

    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).isoformat()

    with lock:
        latest_status.update({
            "monitoring": monitoring,
            "ear": ear,
            "mar": mar,
            "head_direction": head,
            "warning": warning,
            "last_update": timestamp
        })

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        debug=False
    )

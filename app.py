from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

latest_data = {}

@app.route("/")
def home():
    if not latest_data:
        return "<h1>Pi Cloud Test</h1><p>No data received yet.</p>"

    return f"""
    <html>
    <head>
        <title>Pi Cloud Test</title>
        <meta http-equiv="refresh" content="5">
    </head>
    <body>
        <h1>Pi Cloud Test</h1>
        <h2>Latest Data</h2>
        <p><b>Device:</b> {latest_data.get("device", "N/A")}</p>
        <p><b>Temperature:</b> {latest_data.get("temperature_C", "N/A")} °C</p>
        <p><b>Status:</b> {latest_data.get("status", "N/A")}</p>
        <p><b>Received:</b> {latest_data.get("timestamp", "N/A")}</p>
    </body>
    </html>
    """

@app.route("/data", methods=["POST"])
def receive_data():
    global latest_data

    data = request.get_json()

    data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    latest_data = data

    print("Received:", data)

    return jsonify({
        "status": "received",
        "data": data
    }), 200

from flask import Flask, request, jsonify
from datetime import datetime
import time

app = Flask(__name__)

# Temporary memory for testing
data_history = []
last_received_time = 0


@app.route("/")
def dashboard():
    global last_received_time

    # Check whether data was received in the last 5 seconds
    current_time = time.time()

    if last_received_time != 0 and (current_time - last_received_time) <= 5:
        system_status = "● SYSTEM ONLINE"
        status_class = "online"
    else:
        system_status = "● SYSTEM OFFLINE"
        status_class = "offline"

    rows = ""

    for data in reversed(data_history):
        rows += f"""
        <tr>
            <td>{data.get("timestamp", "")}</td>
            <td>{data.get("device", "")}</td>
            <td>{data.get("temperature_C", "")} °C</td>
            <td>
                <span class="data-status">
                    {data.get("status", "")}
                </span>
            </td>
        </tr>
        """

    if not rows:
        rows = """
        <tr>
            <td colspan="4">No data received yet</td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>

    <head>
        <title>Industrial Data Monitoring</title>

        <meta http-equiv="refresh" content="1">

        <style>

            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f2f4f7;
                color: #222;
            }}

            .header {{
                background: #1f2937;
                color: white;
                padding: 25px;
                text-align: center;
            }}

            .header h1 {{
                margin: 0;
                font-size: 28px;
            }}

            .system-status {{
                margin-top: 10px;
                font-size: 15px;
                font-weight: bold;
            }}

            .online {{
                color: #4ade80;
            }}

            .offline {{
                color: #f87171;
            }}

            .container {{
                width: 90%;
                max-width: 1100px;
                margin: 30px auto;
            }}

            .card {{
                background: white;
                padding: 25px;
                border-radius: 12px;
                box-shadow: 0 3px 12px rgba(0,0,0,0.08);
            }}

            .card h2 {{
                text-align: center;
                margin-top: 0;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }}

            th {{
                background: #374151;
                color: white;
                padding: 14px;
                text-align: center;
            }}

            td {{
                padding: 12px;
                text-align: center;
                border-bottom: 1px solid #ddd;
            }}

            tr:hover {{
                background: #f5f5f5;
            }}

            .data-status {{
                background: #dcfce7;
                color: #166534;
                padding: 5px 12px;
                border-radius: 20px;
                font-size: 13px;
            }}

            .count {{
                text-align: center;
                margin-top: 15px;
                color: #666;
            }}

        </style>

    </head>

    <body>

        <div class="header">

            <h1>Industrial Data Monitoring</h1>

            <div class="system-status {status_class}">
                {system_status}
            </div>

        </div>


        <div class="container">

            <div class="card">

                <h2>Live Data</h2>

                <table>

                    <tr>
                        <th>Time</th>
                        <th>Device</th>
                        <th>Temperature</th>
                        <th>Status</th>
                    </tr>

                    {rows}

                </table>

                <div class="count">
                    Total readings received: {len(data_history)}
                </div>

            </div>

        </div>

    </body>

    </html>
    """


@app.route("/data", methods=["POST"])
def receive_data():

    global last_received_time

    data = request.get_json()

    # Add current time
    data["timestamp"] = datetime.now().strftime("%H:%M:%S")

    # Store data
    data_history.append(data)

    # Record the time of the latest data
    last_received_time = time.time()

    # Keep maximum 500 readings
    if len(data_history) > 500:
        data_history.pop(0)

    print("Received:", data)

    return jsonify({
        "status": "received",
        "data": data
    }), 200

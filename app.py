from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# Temporary memory for testing
data_history = []

@app.route("/")
def dashboard():
    rows = ""

    for data in reversed(data_history):
        rows += f"""
        <tr>
            <td>{data.get("timestamp", "")}</td>
            <td>{data.get("device", "")}</td>
            <td>{data.get("temperature_C", "")} °C</td>
            <td><span class="status">{data.get("status", "")}</span></td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Industrial Data Dashboard</title>

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
                padding: 20px;
                text-align: center;
            }}

            .header h1 {{
                margin: 0;
                font-size: 28px;
            }}

            .online {{
                margin-top: 8px;
                color: #4ade80;
                font-size: 14px;
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

            .status {{
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
            <div class="online">● SYSTEM ONLINE</div>
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

    data = request.get_json()

    data["timestamp"] = datetime.now().strftime("%H:%M:%S")

    data_history.append(data)

    # Keep maximum 500 readings for this test
    if len(data_history) > 500:
        data_history.pop(0)

    print("Received:", data)

    return jsonify({
        "status": "received",
        "data": data
    }), 200

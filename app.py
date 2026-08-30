from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return "Pi Cloud Test Server is running!"

@app.route("/data", methods=["POST"])
def receive_data():
    data = request.get_json()

    print("Received:", data)

    return jsonify({
        "status": "received",
        "data": data
    }), 200

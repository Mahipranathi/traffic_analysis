from flask import Flask, request, jsonify, send_from_directory
import cv2
import numpy as np
import time
import pywhatkit as kit
from flask_cors import CORS
import random
import os
from pymongo import MongoClient
from bson import ObjectId
import bcrypt
import jwt
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

# Enable CORS for all routes and all origins
CORS(app, resources={r"/*": {"origins": "*"}})

# Configuration
app.config["SECRET_KEY"] = "your-secret-key-change-this-in-production"
app.config["MONGODB_URI"] = "mongodb://localhost:27017/traffic_analysis"

# MongoDB setup
client = MongoClient(app.config["MONGODB_URI"])
db = client.traffic_analysis
users_collection = db.users


# JWT token decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        try:
            # Check if token has Bearer prefix
            if token.startswith("Bearer "):
                token = token.split(" ")[1]  # Remove 'Bearer ' prefix

            # Decode token
            data = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            current_user = users_collection.find_one({"_id": ObjectId(data["user_id"])})

            if not current_user:
                return jsonify({"error": "Invalid token"}), 401

        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        except Exception as e:
            return jsonify({"error": "Token authentication failed"}), 401

        return f(current_user, *args, **kwargs)

    return decorated


# Authentication routes
@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json
    name = data.get("name")
    phone = data.get("phone")
    password = data.get("password")

    if not all([name, phone, password]):
        return jsonify({"error": "Missing required fields"}), 400

    # Check if user already exists
    if users_collection.find_one({"phone": phone}):
        return jsonify({"error": "Phone number already registered"}), 400

    # Hash password
    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    # Create user
    user = {
        "name": name,
        "phone": phone,
        "password": hashed_password,
        "created_at": datetime.utcnow(),
    }

    result = users_collection.insert_one(user)

    return (
        jsonify(
            {"message": "User created successfully", "user_id": str(result.inserted_id)}
        ),
        201,
    )


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    phone = data.get("phone")
    password = data.get("password")

    if not all([phone, password]):
        return jsonify({"error": "Missing credentials"}), 400

    # Find user
    user = users_collection.find_one({"phone": phone})

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    # Check password
    if not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
        return jsonify({"error": "Invalid credentials"}), 401

    # Generate token
    token = jwt.encode(
        {"user_id": str(user["_id"]), "exp": datetime.utcnow() + timedelta(days=30)},
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )

    print(f"Generated token for user {user['phone']}: {token[:20]}...")  # Debug print

    return (
        jsonify(
            {
                "token": token,
                "user": {
                    "id": str(user["_id"]),
                    "name": user["name"],
                    "phone": user["phone"],
                },
            }
        ),
        200,
    )


# Serve static files
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/login")
def login_page():
    return send_from_directory(".", "index.html")


@app.route("/map.html")
def map_page():
    # Don't protect this route - let the JavaScript handle authentication check
    return send_from_directory(".", "map.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(".", filename)


def get_max_vehicle_count(video_path, duration=3):
    yolo_config = "models\yolov8.cfg"
    yolo_weights = "models\yolov8.weights"
    yolo_classes = "models\yolov8.cfg"

    with open(yolo_classes, "r") as f:
        classes = f.read().strip().split("\n")

    VEHICLE_CLASSES = ["car", "motorbike", "bus", "truck"]

    print("Loading YOLO model...")
    net = cv2.dnn.readNet(yolo_weights, yolo_config)
    print("Model loaded successfully!")

    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Could not open video file.")
        return 0

    layer_names = net.getLayerNames()
    output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

    start_time = time.time()
    max_vehicle_count = 0

    while time.time() - start_time < duration:
        ret, frame = cap.read()
        if not ret:
            print("End of video.")
            break

        height, width = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame, 1 / 255.0, (416, 416), swapRB=True, crop=False
        )
        net.setInput(blob)
        detections = net.forward(output_layers)

        vehicle_count = 0
        boxes, confidences, class_ids = [], [], []

        for output in detections:
            for detection in output:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]

                if confidence > 0.4 and classes[class_id] in VEHICLE_CLASSES:
                    vehicle_count += 1
                    center_x, center_y, w, h = (
                        detection[:4] * np.array([width, height, width, height])
                    ).astype("int")
                    x = int(center_x - w / 2)
                    y = int(center_y - h / 2)

                    boxes.append([x, y, int(w), int(h)])
                    confidences.append(float(confidence))
                    class_ids.append(class_id)

        indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.4, 0.3)
        vehicle_count = len(indices) if indices is not None else 0

        max_vehicle_count = max(max_vehicle_count, vehicle_count)

    cap.release()
    return max_vehicle_count


@app.route("/get_vehicle_count", methods=["POST", "OPTIONS"])
@token_required
def get_vehicle_count(current_user):
    # Handle OPTIONS request for CORS preflight
    if request.method == "OPTIONS":
        response = jsonify({})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add(
            "Access-Control-Allow-Headers", "Content-Type,Authorization"
        )
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response

    print(f"Authenticated user: {current_user['phone']}")  # Debug print

    data = request.json
    source = data.get("source")  # [longitude, latitude]
    destination = data.get("destination")  # [longitude, latitude]

    # Get user's phone number from database
    phone_number = current_user["phone"]

    videos = ["videos/1.mp4", "videos/3.mp4", "videos/2.mp4"]
    video_path = random.choice(videos)  # Path to your video

    # Get the vehicle count
    vehicle_count = get_max_vehicle_count(video_path)

    # Generate alternative route if traffic is high
    needs_reroute = vehicle_count > 100

    # If traffic is high, create an alternative route
    alternative_route = None
    if needs_reroute:
        alternative_route = {
            "source": source,
            "destination": destination,
            "waypoints": [
                # Add slight offset to create an "alternative" route
                [source[0] + 0.01, source[1] - 0.005],
                [destination[0] - 0.008, destination[1] + 0.003],
            ],
            "estimated_vehicle_count": max(30, vehicle_count - random.randint(40, 70)),
        }

    # Send WhatsApp message
    try:
        message = f"Traffic Analysis Results:\nVehicle count: {vehicle_count}"

        if needs_reroute:
            message += f"\nHIGH TRAFFIC ALERT! An alternative route with estimated {alternative_route['estimated_vehicle_count']} vehicles is available."

        print(vehicle_count)
        time.sleep(10)

        if vehicle_count > 100:
            print("High Traffic")
            kit.sendwhatmsg_instantly(
                phone_no=phone_number,
                message="High Traffic",
                wait_time=10,
            )
        elif vehicle_count > 50:
            print("Medium Traffic")
            kit.sendwhatmsg_instantly(
                phone_no=phone_number,
                message="Medium Traffic",
                wait_time=10,
            )
        else:
            print("Low Traffic")
            kit.sendwhatmsg_instantly(
                phone_no=phone_number,
                message="Low Traffic",
                wait_time=30,
            )

        print("WhatsApp message sent successfully!")

        # Log the traffic analysis in MongoDB
        log_entry = {
            "user_id": current_user["_id"],
            "vehicle_count": vehicle_count,
            "needs_reroute": needs_reroute,
            "alternative_route": alternative_route,
            "timestamp": datetime.utcnow(),
        }
        db.traffic_logs.insert_one(log_entry)

    except Exception as e:
        print(f"Failed to send WhatsApp message: {e}")

    return jsonify(
        {
            "vehicle_count": vehicle_count,
            "needs_reroute": needs_reroute,
            "alternative_route": alternative_route,
        }
    )


# Debug route to test authentication
@app.route("/api/test-auth", methods=["GET"])
@token_required
def test_auth(current_user):
    return (
        jsonify(
            {
                "message": "Authentication successful",
                "user": {
                    "id": str(current_user["_id"]),
                    "name": current_user["name"],
                    "phone": current_user["phone"],
                },
            }
        ),
        200,
    )


# Debug route to check current login state
@app.route("/api/debug", methods=["GET"])
def debug():
    token = request.headers.get("Authorization")
    return (
        jsonify(
            {
                "headers": dict(request.headers),
                "has_token": token is not None,
                "local_storage": request.headers.get("Local-Storage-Data"),
            }
        ),
        200,
    )


if __name__ == "__main__":
    app.run(debug=True)

from flask import Flask, request, jsonify
import cv2
import numpy as np
import time
import pywhatkit as kit
from flask_cors import CORS  
import random
app = Flask(__name__)

# Enable CORS for all routes and all origins
CORS(app, resources={r"/*": {"origins": "*"}})


def get_max_vehicle_count(video_path, duration=3):
    yolo_config = "yolov8.cfg"
    yolo_weights = "yolov8.weights"
    yolo_classes = "coco.names"

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
def get_vehicle_count():
    # Handle OPTIONS request for CORS preflight
    if request.method == "OPTIONS":
        response = jsonify({})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response

    data = request.json
    source = data.get("source")  # [longitude, latitude]
    destination = data.get("destination")  # [longitude, latitude]
    phone_number = "+919182436683"  # User's phone number
    videos = ["1.mp4", "3.mp4", "2.mp4"]
    video_path = random.choice(videos)  # Path to your video

    # Get the vehicle count
    vehicle_count = get_max_vehicle_count(video_path)

    # Generate alternative route if traffic is high
    needs_reroute = vehicle_count > 100

    # If traffic is high, create an alternative route
    # In a real system, you would use another API or algorithm to find alternatives
    alternative_route = None
    if needs_reroute:
        # This is a simplified version that just creates a slight variation
        # In reality, you would use a proper routing algorithm
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
        import time
        print(vehicle_count)
        time.sleep(10)
        if vehicle_count > 100:
            print("High Traffic")
            kit.sendwhatmsg_instantly(
                phone_no=phone_number,
                message="High Traffic",
                wait_time=10,
            )
        elif vehicle_count>50:
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
    except Exception as e:
        print(f"Failed to send WhatsApp message: {e}")

    return jsonify(
        {
            "vehicle_count": vehicle_count,
            "needs_reroute": needs_reroute,
            "alternative_route": alternative_route,
        }
    )


if __name__ == "__main__":
    app.run(debug=True)

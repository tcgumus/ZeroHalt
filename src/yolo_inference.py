from ultralytics import YOLO
from pathlib import Path

CLASS_NAMES = ["alternator", "brake_disc", "engine_control",
               "hydraulic_filter", "piston"]

model = YOLO("runs/zerohalt_yolo11n/weights/best.pt")

def detect_parts(image_path: str, conf: float = 0.25) -> list[dict]:
    """Görsel üzerinde parça tespiti yapar."""
    results = model.predict(source=image_path, conf=conf, verbose=False)[0]
    detections = []
    for box in results.boxes:
        x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
        detections.append({
            "class_id":   int(box.cls[0]),
            "class_name": CLASS_NAMES[int(box.cls[0])],
            "confidence": round(float(box.conf[0]), 4),
            "bbox":       [x1, y1, x2, y2],
        })
    return detections

# Kullanım:
# detections = detect_parts("parcalar/piston/images.jpeg")
# print(detections)
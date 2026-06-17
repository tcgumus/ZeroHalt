"""YOLOv11 tabanlı parça tespit modülü.

Fine-tune edilmiş modeli kullanarak resim ve video üzerinde
parça tespiti yapar. Girdinin orijinal boyutunda analiz yapar.

Sınıflar: alternator, brake_disc, engine_control, hydraulic_filter, piston
"""
from __future__ import annotations

import base64
import io
import tempfile
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

# Model yolu
MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "runs" / "zerohalt_yolo11n" / "weights" / "best.pt"

# Sınıf isimleri -> Türkçe etiketler
CLASS_LABELS_TR = {
    "alternator": "Alternatör",
    "brake_disc": "Fren Diski",
    "engine_control": "Motor Kontrol Ünitesi",
    "hydraulic_filter": "Hidrolik Filtre",
    "piston": "Piston",
}

# Sınıf -> muhtemel parça kodu eşlemesi
CLASS_TO_PART = {
    "alternator": None,
    "brake_disc": None,
    "engine_control": None,
    "hydraulic_filter": "FLT-2210",
    "piston": "HYD-4520-B",
}

_model = None


def _get_model():
    """Lazy model yükleme (ilk çağrıda yükler, sonra cache'ten döner)."""
    global _model
    if _model is None:
        from ultralytics import YOLO
        _model = YOLO(str(MODEL_PATH))
    return _model


def detect_image(
    image_bytes: Optional[bytes] = None,
    image_b64: Optional[str] = None,
    image_path: Optional[str] = None,
) -> dict[str, Any]:
    """Resim üzerinde YOLO tespiti yapar.

    Girdinin orijinal boyutunda analiz yapar (imgsz parametresi verilmez).

    Returns:
        {
            "detections": [...],
            "annotated_b64": "...",  # bbox çizilmiş resim (base64)
            "summary": "...",
            "original_size": [w, h]
        }
    """
    # Girdiyi numpy array'e çevir
    if image_b64 and image_bytes is None:
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception:
            return {"error": True, "message": "Geçersiz base64 verisi."}

    if image_bytes:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    elif image_path:
        img = cv2.imread(image_path)
    else:
        return {"error": True, "message": "Resim verisi gerekli (image_b64, image_bytes veya image_path)."}

    if img is None:
        return {"error": True, "message": "Resim okunamadı."}

    h, w = img.shape[:2]

    # Orijinal boyutta inference
    model = _get_model()
    results = model.predict(source=img, imgsz=max(h, w), conf=0.25, verbose=False)

    detections = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = r.names[cls_id]
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            detections.append({
                "class": cls_name,
                "label_tr": CLASS_LABELS_TR.get(cls_name, cls_name),
                "confidence": round(conf, 3),
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "part_code": CLASS_TO_PART.get(cls_name),
            })

    # Annotated image oluştur
    annotated = results[0].plot() if results else img
    _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
    annotated_b64 = base64.b64encode(buf).decode("utf-8")

    # Özet
    if detections:
        summary_parts = []
        for d in detections:
            summary_parts.append(f"{d['label_tr']} (%{int(d['confidence']*100)})")
        summary = f"{len(detections)} parça tespit edildi: " + ", ".join(summary_parts)
    else:
        summary = "Herhangi bir parça tespit edilemedi."

    return {
        "detections": detections,
        "annotated_b64": annotated_b64,
        "summary": summary,
        "original_size": [w, h],
    }


def detect_video(
    video_bytes: Optional[bytes] = None,
    video_b64: Optional[str] = None,
    video_path: Optional[str] = None,
    frame_interval: int = 10,
    max_frames: int = 30,
) -> dict[str, Any]:
    """Video üzerinde YOLO tespiti yapar.

    Her frame_interval karede bir analiz yapar, max_frames'e kadar.
    Orijinal frame boyutunda analiz yapar.

    Returns:
        {
            "frames_analyzed": int,
            "total_frames": int,
            "detections_per_frame": [...],
            "unique_detections": [...],
            "summary": "...",
            "best_frame_b64": "...",  # en çok tespit yapılan frame
            "original_size": [w, h],
            "fps": float,
        }
    """
    # Video dosyasını geçici dosyaya yaz
    tmp_path = None
    if video_b64 and video_bytes is None:
        try:
            video_bytes = base64.b64decode(video_b64)
        except Exception:
            return {"error": True, "message": "Geçersiz base64 video verisi."}

    if video_bytes:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.write(video_bytes)
        tmp.close()
        tmp_path = tmp.name
        cap = cv2.VideoCapture(tmp_path)
    elif video_path:
        cap = cv2.VideoCapture(video_path)
    else:
        return {"error": True, "message": "Video verisi gerekli (video_b64, video_bytes veya video_path)."}

    if not cap.isOpened():
        return {"error": True, "message": "Video açılamadı."}

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    model = _get_model()
    detections_per_frame = []
    all_detections = {}  # class -> max confidence
    best_frame = None
    best_frame_count = 0
    frames_analyzed = 0

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0 and frames_analyzed < max_frames:
            # Orijinal boyutta inference
            results = model.predict(source=frame, imgsz=max(h, w), conf=0.25, verbose=False)

            frame_dets = []
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = r.names[cls_id]
                    conf = float(box.conf[0])
                    frame_dets.append({
                        "class": cls_name,
                        "label_tr": CLASS_LABELS_TR.get(cls_name, cls_name),
                        "confidence": round(conf, 3),
                    })
                    # En yüksek confidence'ı tut
                    if cls_name not in all_detections or conf > all_detections[cls_name]:
                        all_detections[cls_name] = conf

            detections_per_frame.append({
                "frame_idx": frame_idx,
                "time_sec": round(frame_idx / fps, 2) if fps > 0 else 0,
                "count": len(frame_dets),
                "detections": frame_dets,
            })

            # En çok tespit yapılan frame'i sakla
            if len(frame_dets) > best_frame_count:
                best_frame_count = len(frame_dets)
                annotated = results[0].plot() if results else frame
                best_frame = annotated

            frames_analyzed += 1

        frame_idx += 1

    cap.release()

    # Geçici dosyayı temizle
    if tmp_path:
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass

    # Best frame encode
    best_frame_b64 = None
    if best_frame is not None:
        _, buf = cv2.imencode(".jpg", best_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        best_frame_b64 = base64.b64encode(buf).decode("utf-8")

    # Unique detections
    unique_detections = [
        {
            "class": cls,
            "label_tr": CLASS_LABELS_TR.get(cls, cls),
            "max_confidence": round(conf, 3),
            "part_code": CLASS_TO_PART.get(cls),
        }
        for cls, conf in sorted(all_detections.items(), key=lambda x: -x[1])
    ]

    # Özet
    if unique_detections:
        parts = [f"{d['label_tr']} (%{int(d['max_confidence']*100)})" for d in unique_detections]
        summary = f"{frames_analyzed} frame analiz edildi, {len(unique_detections)} farklı parça tespit edildi: " + ", ".join(parts)
    else:
        summary = f"{frames_analyzed} frame analiz edildi, parça tespit edilemedi."

    return {
        "frames_analyzed": frames_analyzed,
        "total_frames": total_frames,
        "detections_per_frame": detections_per_frame,
        "unique_detections": unique_detections,
        "summary": summary,
        "best_frame_b64": best_frame_b64,
        "original_size": [w, h],
        "fps": round(fps, 2),
    }

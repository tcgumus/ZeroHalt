"""Flask web sunucusu — FNSS Otonom Bakım Paneli.

Statik panel `web/templates/index.html` + `web/static/*` üzerinden sunulur;
JSON API'leri gerçek ajan/araç/datasource katmanına bağlanır.

Çalıştırma:
    python -m web.server      veya      python app.py --web
"""
from __future__ import annotations

import sys
from pathlib import Path

# Windows konsolunda Türkçe karakterler için UTF-8 (cp1252 UnicodeEncodeError'ı önler).
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

# proje kökünü import yoluna ekle (python -m web.server için).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

import config  # noqa: E402
import datasource  # noqa: E402
from src import agent, policy  # noqa: E402

BASE = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(BASE / "static"), template_folder=str(BASE / "templates"))


# ---------------------------------------------------------------------------
# Sayfa
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(BASE / "templates", "index.html")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/overview")
def overview():
    # KPI'lar ve haftalık duruş artık gerçek veriden hesaplanır (UC-07).
    kpis = datasource.compute_kpis()
    downtime = datasource.weekly_downtime()
    return jsonify({
        "kpis": kpis,
        "incidents": datasource.list_incidents(),
        "low_stock": datasource.list_low_stock(),
        "downtime": downtime,
        "config": config.summary(),
    })


@app.post("/api/diagnose")
def diagnose():
    body = request.get_json(force=True) or {}
    fault_code = body.get("fault_code")
    incident_id = body.get("incident_id")
    if incident_id and not fault_code:
        inc = datasource.get_incident(incident_id)
        if inc:
            fault_code = inc["fault_code"]
            body.setdefault("machine_id", inc["machine_id"])
            body.setdefault("title", inc["title"])
    if not fault_code:
        return jsonify({"error": "fault_code gerekli"}), 400
    inc = datasource.get_incident_by_fault(fault_code, body.get("machine_id"))
    machine = body.get("machine_id") or (inc["machine_id"] if inc else "Bilinmeyen")
    title = body.get("title") or (inc["title"] if inc else "")
    result = agent.run_diagnosis(
        fault_code, machine, title,
        technician=body.get("technician"),
        image_b64=body.get("image_b64"),
    )
    return jsonify(result)


@app.post("/api/order/<draft_id>/decide")
def decide(draft_id: str):
    body = request.get_json(force=True) or {}
    approved = bool(body.get("approved"))
    approver = body.get("approver", "Elif Demirtaş")
    order = policy.decide(draft_id, approved, approver)
    if order is None:
        return jsonify({"error": "Taslak bulunamadı"}), 404
    return jsonify(order)


@app.get("/api/orders")
def orders():
    return jsonify(datasource.list_orders())


@app.get("/api/work_orders")
def work_orders():
    return jsonify(datasource.list_work_orders())


@app.get("/api/parts")
def parts():
    # Parça tanıma galerisi için kod + isim listesi.
    return jsonify(datasource.list_parts())


@app.post("/api/identify")
def identify():
    body = request.get_json(force=True) or {}
    from src.tools.parts import identify_part
    result = identify_part(image_b64=body.get("image_b64"), hint=body.get("hint"))
    if result.get("part_code"):
        result["part_info"] = datasource.get_part(result["part_code"])
    return jsonify(result)


@app.get("/api/preventive")
def preventive():
    from src.tools.insights import preventive_insights
    return jsonify(preventive_insights())


@app.post("/api/chat")
def chat():
    body = request.get_json(force=True) or {}
    q = (body.get("question") or "").strip()
    if not q:
        return jsonify({"answer": "Lütfen bir soru yazın."})
    return jsonify({"answer": agent.chat(q)})


def main() -> None:
    # DB hazır mı garanti et.
    datasource.list_incidents()
    port = int(config.__dict__.get("WEB_PORT", 5000))
    print(f"FNSS Otonom Bakım Paneli — http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()

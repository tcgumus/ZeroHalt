"""SQLite veritabanını `data/*.csv` dosyalarından tohumlar.

Doğrudan çalıştırılabilir:
    python seed_db.py            # DB'yi (yeniden) oluştur ve doldur

datasource.py, DB boşsa `seed(conn)` fonksiyonunu otomatik çağırır.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

import config

# Windows konsolunda Türkçe karakterler için UTF-8 (cp1252 UnicodeEncodeError'ı önler).
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

DATA_DIR = config.DATA_DIR


def _read_csv(name: str) -> list[dict[str, str]]:
    path = DATA_DIR / name
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _as_bool(val: str) -> int:
    return 1 if str(val).strip().lower() in {"1", "true", "yes", "evet"} else 0


def seed(conn: sqlite3.Connection) -> None:
    """Şemayı kurar ve CSV verilerini yükler (mevcut tabloları temizleyerek)."""
    import datasource

    datasource.init_schema(conn)

    # Temizle (idempotent yeniden tohumlama).
    for tbl in (
        "parts",
        "substitutes",
        "maintenance_history",
        "incidents",
    ):
        conn.execute(f"DELETE FROM {tbl}")

    for r in _read_csv("parts.csv"):
        conn.execute(
            "INSERT INTO parts VALUES (?,?,?,?,?,?,?,?,?)",
            (
                r["part_code"],
                r["name"],
                r["category"],
                r["specs"],
                int(r["on_hand"]),
                int(r["safety_stock"]),
                float(r["unit_cost"]),
                int(r["lead_time_days"]),
                r["used_in_variants"],
            ),
        )

    for r in _read_csv("substitutes.csv"):
        conn.execute(
            "INSERT INTO substitutes VALUES (?,?,?,?)",
            (
                r["part_code"],
                r["substitute_code"],
                r["compatibility_note"],
                _as_bool(r["approved"]),
            ),
        )

    for r in _read_csv("maintenance_history.csv"):
        conn.execute(
            "INSERT INTO maintenance_history VALUES (?,?,?,?,?,?,?)",
            (
                r["record_id"],
                r["machine_id"],
                r["date"],
                r["fault_code"],
                r["root_cause"],
                r["part_used"],
                r["resolution"],
            ),
        )

    for r in _read_csv("incidents.csv"):
        conn.execute(
            "INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?)",
            (
                r["incident_id"],
                r["machine_id"],
                r["fault_code"],
                r["title"],
                r["reported_at"],
                r["status"],
                r.get("resolved_at") or None,
                float(r["downtime_hours"]) if r.get("downtime_hours") else None,
            ),
        )

    conn.commit()


def main() -> None:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Sıfırdan kurmak için mevcut DB'yi sil.
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
    conn = sqlite3.connect(config.DB_PATH)
    try:
        seed(conn)
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("parts", "substitutes", "maintenance_history", "incidents")
        }
        print(f"Veritabanı oluşturuldu: {config.DB_PATH}")
        for t, c in counts.items():
            print(f"  {t}: {c} kayıt")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

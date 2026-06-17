"""Mock veri katmanı — TEK erişim noktası.

Tüm tool'lar veriye DOĞRUDAN değil yalnızca bu modül üzerinden erişir.
Böylece ileride mock CSV/SQLite → gerçek MES/ERP/CMMS bağlantısına geçiş
tek noktadan yapılır.

Şu an arkada SQLite vardır (`config.DB_PATH`). Veritabanı yoksa `data/*.csv`
dosyalarından otomatik tohumlanır (bkz. `seed_db.py`).
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

import config

# Yazma işlemleri için basit kilit (SQLite + çoklu istek güvenliği).
_lock = threading.Lock()
_seed_checked = False


# ---------------------------------------------------------------------------
# Bağlantı / şema
# ---------------------------------------------------------------------------
def _connect() -> sqlite3.Connection:
    """DB bağlantısı döndürür; ilk çağrıda şema + tohum garanti edilir."""
    global _seed_checked
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not _seed_checked:
        _ensure_seeded(conn)
        _seed_checked = True
    return conn


def _ensure_seeded(conn: sqlite3.Connection) -> None:
    """parts tablosu boşsa CSV'lerden tohumla."""
    try:
        cur = conn.execute("SELECT COUNT(*) FROM parts")
        if cur.fetchone()[0] > 0:
            return
    except sqlite3.OperationalError:
        pass  # tablo henüz yok
    import seed_db

    seed_db.seed(conn)


def init_schema(conn: sqlite3.Connection) -> None:
    """Tabloları oluşturur (idempotent)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS parts (
            part_code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            specs TEXT,
            on_hand INTEGER NOT NULL,
            safety_stock INTEGER NOT NULL,
            unit_cost REAL NOT NULL,
            lead_time_days INTEGER NOT NULL,
            used_in_variants TEXT
        );

        CREATE TABLE IF NOT EXISTS substitutes (
            part_code TEXT NOT NULL,
            substitute_code TEXT NOT NULL,
            compatibility_note TEXT,
            approved INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (part_code, substitute_code)
        );

        CREATE TABLE IF NOT EXISTS maintenance_history (
            record_id TEXT PRIMARY KEY,
            machine_id TEXT,
            date TEXT,
            fault_code TEXT,
            root_cause TEXT,
            part_used TEXT,
            resolution TEXT
        );

        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            machine_id TEXT,
            fault_code TEXT,
            title TEXT,
            reported_at TEXT,
            status TEXT,
            resolved_at TEXT,
            downtime_hours REAL
        );

        CREATE TABLE IF NOT EXISTS orders (
            draft_id TEXT PRIMARY KEY,
            part_code TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            est_cost REAL NOT NULL,
            status TEXT NOT NULL,
            requires_manager_approval INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            approved_by TEXT,
            decided_at TEXT
        );

        CREATE TABLE IF NOT EXISTS work_orders (
            work_order_id TEXT PRIMARY KEY,
            fault_id TEXT,
            root_cause TEXT,
            steps TEXT,
            part_code TEXT,
            technician TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _row_to_part(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "part_code": row["part_code"],
        "name": row["name"],
        "category": row["category"],
        "specs": row["specs"],
        "on_hand": row["on_hand"],
        "safety_stock": row["safety_stock"],
        "unit_cost": row["unit_cost"],
        "lead_time_days": row["lead_time_days"],
        "used_in_variants": [
            v for v in (row["used_in_variants"] or "").split(";") if v
        ],
    }


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_date(value: str) -> datetime:
    """CSV/DB tarih metnini datetime'a çevirir (birkaç formatı dener)."""
    text = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Tarih ayrıştırılamadı: {value!r}")


# ---------------------------------------------------------------------------
# Okuma API'si (tool'lar bunları kullanır)
# ---------------------------------------------------------------------------
def get_part(part_code: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM parts WHERE part_code = ?", (part_code,)
        ).fetchone()
        return _row_to_part(row) if row else None


def get_substitutes(part_code: str) -> list[dict[str, Any]]:
    """part_code için muadiller; her biri kendi stok/isim bilgisiyle zenginleştirilir."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM substitutes WHERE part_code = ?", (part_code,)
        ).fetchall()
        results = []
        for r in rows:
            sub = conn.execute(
                "SELECT name, on_hand, safety_stock FROM parts WHERE part_code = ?",
                (r["substitute_code"],),
            ).fetchone()
            results.append(
                {
                    "substitute_code": r["substitute_code"],
                    "name": sub["name"] if sub else r["substitute_code"],
                    "on_hand": sub["on_hand"] if sub else None,
                    "safety_stock": sub["safety_stock"] if sub else None,
                    "compatibility_note": r["compatibility_note"],
                    "approved": bool(r["approved"]),
                }
            )
        # Önce onaylılar, sonra stoğu yüksek olanlar.
        results.sort(key=lambda s: (not s["approved"], -(s["on_hand"] or 0)))
        return results


def get_maintenance_history(
    fault_code: Optional[str] = None, machine_id: Optional[str] = None
) -> list[dict[str, Any]]:
    query = "SELECT * FROM maintenance_history WHERE 1=1"
    params: list[Any] = []
    if fault_code:
        query += " AND fault_code = ?"
        params.append(fault_code)
    if machine_id:
        query += " AND machine_id = ?"
        params.append(machine_id)
    query += " ORDER BY date DESC"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def list_incidents(status: Optional[str] = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM incidents"
    params: list[Any] = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY reported_at DESC"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_incident(incident_id: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
        ).fetchone()
        return dict(row) if row else None


def get_incident_by_fault(
    fault_code: str, machine_id: Optional[str] = None
) -> Optional[dict[str, Any]]:
    query = "SELECT * FROM incidents WHERE fault_code = ?"
    params: list[Any] = [fault_code]
    if machine_id:
        query += " AND machine_id = ?"
        params.append(machine_id)
    query += " ORDER BY reported_at DESC LIMIT 1"
    with _connect() as conn:
        row = conn.execute(query, params).fetchone()
        if row is None and machine_id:
            # makine eşleşmezse yalnızca arıza koduyla dene
            row = conn.execute(
                "SELECT * FROM incidents WHERE fault_code = ? ORDER BY reported_at DESC LIMIT 1",
                (fault_code,),
            ).fetchone()
        return dict(row) if row else None


def list_parts() -> list[dict[str, Any]]:
    """Tüm parçalar (kod + isim) — parça tanıma vb. için."""
    with _connect() as conn:
        rows = conn.execute("SELECT part_code, name FROM parts").fetchall()
        return [{"part_code": r["part_code"], "name": r["name"]} for r in rows]


def list_low_stock() -> list[dict[str, Any]]:
    """on_hand < safety_stock olan parçalar (KPI/panel için)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM parts WHERE on_hand < safety_stock ORDER BY "
            "(CAST(on_hand AS REAL) / safety_stock) ASC"
        ).fetchall()
        return [_row_to_part(r) for r in rows]


def get_part_usage_rate(part_code: str) -> dict[str, Any]:
    """maintenance_history'den parçanın günlük tüketim hızını türetir.

    Tek (veya hiç) kayıt varsa hız 0 kabul edilir (güvenilir trend yok).

    Returns:
        {part_code, total_used, first_date, last_date, span_days, daily_usage}
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT date FROM maintenance_history WHERE part_used = ? ORDER BY date ASC",
            (part_code,),
        ).fetchall()
    dates = [r["date"] for r in rows if r["date"]]
    total = len(dates)
    if total < 2:
        return {
            "part_code": part_code,
            "total_used": total,
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
            "span_days": 0,
            "daily_usage": 0.0,
        }
    span = max(1, (_parse_date(dates[-1]) - _parse_date(dates[0])).days)
    return {
        "part_code": part_code,
        "total_used": total,
        "first_date": dates[0],
        "last_date": dates[-1],
        "span_days": span,
        "daily_usage": round(total / span, 5),
    }


def count_open_demand(part_code: str) -> int:
    """Bu parçayla ilişkili açık talep göstergesi.

    Parçanın geçmişte bağlandığı arıza kodları için açık (çözülmemiş) olaylar
    + bu parçaya ait açık iş emirleri sayılır. Kaba bir "bekleyen talep" sinyali.
    """
    with _connect() as conn:
        fault_codes = [
            r["fault_code"]
            for r in conn.execute(
                "SELECT DISTINCT fault_code FROM maintenance_history WHERE part_used = ?",
                (part_code,),
            ).fetchall()
            if r["fault_code"]
        ]
        open_incidents = 0
        if fault_codes:
            placeholders = ",".join("?" * len(fault_codes))
            open_incidents = conn.execute(
                f"SELECT COUNT(*) FROM incidents WHERE status != 'cozuldu' "
                f"AND fault_code IN ({placeholders})",
                fault_codes,
            ).fetchone()[0]
        open_wos = conn.execute(
            "SELECT COUNT(*) FROM work_orders WHERE part_code = ? AND status != 'kapandi'",
            (part_code,),
        ).fetchone()[0]
    return int(open_incidents + open_wos)


def get_all_maintenance_history() -> list[dict[str, Any]]:
    """Tüm bakım geçmişi (date ASC) — trend/önleyici analiz için."""
    with _connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM maintenance_history ORDER BY date ASC"
            ).fetchall()
        ]


def get_fault_frequency() -> list[dict[str, Any]]:
    """fault_code bazında özet (tekrar sayısı, makineler, tarihler, parçalar).

    Returns (occurrences DESC):
        [{fault_code, occurrences, machines[], dates[], parts[], root_causes[]}]
    """
    groups: dict[str, dict[str, Any]] = {}
    for r in get_all_maintenance_history():
        g = groups.setdefault(
            r["fault_code"],
            {
                "fault_code": r["fault_code"],
                "occurrences": 0,
                "machines": [],
                "dates": [],
                "parts": [],
                "root_causes": [],
            },
        )
        g["occurrences"] += 1
        g["machines"].append(r["machine_id"])
        g["dates"].append(r["date"])
        if r["part_used"]:
            g["parts"].append(r["part_used"])
        g["root_causes"].append(r["root_cause"])
    return sorted(groups.values(), key=lambda x: x["occurrences"], reverse=True)


def list_all_parts() -> list[dict[str, Any]]:
    """Tüm parçalar tam alanlarla (used_in_variants parse edilmiş) — açık tahmini için."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM parts").fetchall()
        return [_row_to_part(r) for r in rows]


# Türkçe kısa gün adları (datetime.weekday(): Pazartesi=0 ... Pazar=6).
_WEEKDAYS_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


def _overall_mtbf_days() -> Optional[float]:
    """maintenance_history'den genel MTBF (arızalar arası ortalama gün)."""
    intervals: list[int] = []
    for g in get_fault_frequency():
        dates = sorted(_parse_date(d) for d in g["dates"] if d)
        intervals += [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    if not intervals:
        return None
    return round(sum(intervals) / len(intervals), 1)


def weekly_downtime() -> list[list[Any]]:
    """Son 7 günün gerçek duruş dağılımı [['Pzt', saat], ...].

    Sistem saatinden bağımsız: en güncel olay tarihinden geriye 7 günlük pencere;
    duruş saatleri haftanın gününe göre toplanır.
    """
    dated = [
        (_parse_date(i["reported_at"]), i.get("downtime_hours") or 0)
        for i in list_incidents()
        if i.get("reported_at")
    ]
    buckets = {d: 0.0 for d in _WEEKDAYS_TR}
    if dated:
        latest = max(d for d, _ in dated)
        window_start = (latest - timedelta(days=6)).date()
        for dt, hours in dated:
            if window_start <= dt.date() <= latest.date():
                buckets[_WEEKDAYS_TR[dt.weekday()]] += hours
    return [[d, round(buckets[d], 1)] for d in _WEEKDAYS_TR]


def compute_kpis() -> dict[str, Any]:
    """incidents + work_orders + maintenance_history'den gerçek KPI'lar.

    Returns:
        {aktif_ariza, cozulen_ariza, kritik_stok, bekleyen_siparis, mtbf_gun,
         mttr_saat, toplam_durus_saat, cozum_orani, haftalik_durus}
    """
    incidents = list_incidents()
    cozulen = [i for i in incidents if i["status"] == "cozuldu"]
    acik = [i for i in incidents if i["status"] != "cozuldu"]
    pending = [o for o in list_orders() if o["status"] == "pending_approval"]

    resolved_dt = [
        i["downtime_hours"] for i in cozulen if i.get("downtime_hours") is not None
    ]
    mttr = round(sum(resolved_dt) / len(resolved_dt), 1) if resolved_dt else 0.0
    toplam_durus = round(sum((i.get("downtime_hours") or 0) for i in incidents), 1)
    cozum_orani = round(100 * len(cozulen) / len(incidents)) if incidents else 0

    return {
        "aktif_ariza": len(acik),
        "cozulen_ariza": len(cozulen),
        "kritik_stok": len(list_low_stock()),
        "bekleyen_siparis": len(pending),
        "mtbf_gun": _overall_mtbf_days(),
        "mttr_saat": mttr,
        "toplam_durus_saat": toplam_durus,
        "cozum_orani": cozum_orani,
        "haftalik_durus": round(sum(d[1] for d in weekly_downtime()), 1),
    }


# ---------------------------------------------------------------------------
# Yazma API'si (sipariş / iş emri)
# ---------------------------------------------------------------------------
def _next_id(conn: sqlite3.Connection, table: str, id_col: str, prefix: str) -> str:
    year = datetime.now().year
    cur = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return f"{prefix}-{year}-{cur + 1:04d}"


def save_order_draft(
    part_code: str,
    quantity: int,
    est_cost: float,
    requires_manager_approval: bool,
) -> dict[str, Any]:
    with _lock, _connect() as conn:
        draft_id = _next_id(conn, "orders", "draft_id", "PO-TASLAK")
        created = _now()
        conn.execute(
            "INSERT INTO orders (draft_id, part_code, quantity, est_cost, status, "
            "requires_manager_approval, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                draft_id,
                part_code,
                quantity,
                est_cost,
                "pending_approval",
                int(requires_manager_approval),
                created,
            ),
        )
        conn.commit()
    return get_order(draft_id)  # type: ignore[return-value]


def get_order(draft_id: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE draft_id = ?", (draft_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["requires_manager_approval"] = bool(d["requires_manager_approval"])
        return d


def decide_order(draft_id: str, approved: bool, approver: str) -> Optional[dict[str, Any]]:
    """İnsan onayı/reddi — koddan ayrı bir adımda çağrılır (policy/CLI/web)."""
    with _lock, _connect() as conn:
        status = "approved" if approved else "rejected"
        conn.execute(
            "UPDATE orders SET status = ?, approved_by = ?, decided_at = ? "
            "WHERE draft_id = ?",
            (status, approver, _now(), draft_id),
        )
        conn.commit()
    return get_order(draft_id)


def list_orders() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["requires_manager_approval"] = bool(d["requires_manager_approval"])
            out.append(d)
        return out


def save_work_order(
    fault_id: str,
    root_cause: str,
    steps: list[str],
    part_code: str,
    technician: str,
) -> dict[str, Any]:
    import json

    with _lock, _connect() as conn:
        wo_id = _next_id(conn, "work_orders", "work_order_id", "WO")
        conn.execute(
            "INSERT INTO work_orders (work_order_id, fault_id, root_cause, steps, "
            "part_code, technician, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                wo_id,
                fault_id,
                root_cause,
                json.dumps(steps, ensure_ascii=False),
                part_code,
                technician,
                "olusturuldu",
                _now(),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM work_orders WHERE work_order_id = ?", (wo_id,)
        ).fetchone()
    d = dict(row)
    d["steps"] = json.loads(d["steps"])
    return d


def list_work_orders() -> list[dict[str, Any]]:
    import json

    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM work_orders ORDER BY created_at DESC"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["steps"] = json.loads(d["steps"]) if d["steps"] else []
            out.append(d)
        return out

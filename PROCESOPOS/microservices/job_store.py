import sqlite3
import os
import json
import time

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage")
DB_PATH = os.path.join(DB_DIR, "pos_jobs.db")

class JobStore:
    def __init__(self):
        os.makedirs(DB_DIR, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    pos_key TEXT,
                    pos_num INTEGER,
                    target_ip TEXT,
                    business_unit TEXT,
                    status TEXT,
                    current_phase INTEGER,
                    phases_status TEXT,
                    config_json TEXT,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    pos_key TEXT,
                    timestamp TEXT,
                    level TEXT,
                    message TEXT
                );
            """)
            conn.commit()

    def create_or_update_job(self, job_id, pos_key, pos_num, target_ip, business_unit, status, current_phase, phases_status, config, error=None):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, pos_key, pos_num, target_ip, business_unit, status, current_phase, phases_status, config_json, error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(job_id) DO UPDATE SET
                    status=excluded.status,
                    current_phase=excluded.current_phase,
                    phases_status=excluded.phases_status,
                    error=excluded.error,
                    updated_at=CURRENT_TIMESTAMP;
            """, (
                job_id, pos_key, pos_num, target_ip, business_unit, status,
                current_phase, json.dumps(phases_status), json.dumps(config), error
            ))
            conn.commit()

    def add_log(self, job_id, pos_key, message, level="INFO"):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO job_logs (job_id, pos_key, timestamp, level, message)
                VALUES (?, ?, ?, ?, ?);
            """, (job_id, pos_key, ts, level, message))
            conn.commit()

    def get_job(self, job_id):
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not row:
                return None
            return {
                "job_id": row["job_id"],
                "pos_key": row["pos_key"],
                "pos_num": row["pos_num"],
                "target_ip": row["target_ip"],
                "business_unit": row["business_unit"],
                "status": row["status"],
                "current_phase": row["current_phase"],
                "phases_status": json.loads(row["phases_status"] or "{}"),
                "config": json.loads(row["config_json"] or "{}"),
                "error": row["error"],
                "updated_at": row["updated_at"]
            }

    def list_recent_jobs(self, limit=20):
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            return [
                {
                    "job_id": r["job_id"],
                    "pos_key": r["pos_key"],
                    "pos_num": r["pos_num"],
                    "target_ip": r["target_ip"],
                    "business_unit": r["business_unit"],
                    "status": r["status"],
                    "current_phase": r["current_phase"],
                    "phases_status": json.loads(r["phases_status"] or "{}"),
                    "error": r["error"],
                    "updated_at": r["updated_at"]
                }
                for r in rows
            ]

    def get_logs(self, job_id=None, limit=50):
        with self._get_connection() as conn:
            if job_id:
                rows = conn.execute("SELECT * FROM job_logs WHERE job_id = ? ORDER BY id DESC LIMIT ?", (job_id, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM job_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [
                {
                    "id": r["id"],
                    "job_id": r["job_id"],
                    "pos_key": r["pos_key"],
                    "timestamp": r["timestamp"],
                    "level": r["level"],
                    "message": r["message"]
                }
                for r in reversed(rows)
            ]

job_store_instance = JobStore()

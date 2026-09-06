"""Durable job snapshots; SQLite transactions survive an interrupted write."""
import json
import sqlite3
from pathlib import Path


def job_record(job):
    return {"id": job.id, "name": job.params.get("display_name", job.id),
            "type": job.job_type.value, "state": job.state.value,
            "progress": job.progress, "status": job.params.get("stage", job.progress_text),
            "error": job.error_message, "output": str(job.output_path) if job.output_path else None,
            "download": job.params.get("download_dir"), "outputs": job.params.get("outputs", []),
            "steps": job.params.get("steps", []), "warning": job.params.get("cleanup_warning", ""),
            "created": job.created_at.isoformat(),
            "awaiting_copy_medium": job.params.get("awaiting_copy_medium", False)}


class JobHistory:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created TEXT, payload TEXT)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def save(self, job):
        row = job_record(job)
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?, ?)",
                       (row["id"], row["created"], json.dumps(row, ensure_ascii=False)))

    def recent(self, limit=100):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM jobs ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for (payload,) in rows:
            row = json.loads(payload)
            # These are snapshots from an earlier session; live jobs override them.
            if row["state"] in ("pending", "running"):
                row.update(state="interrupted", status="Unterbrochen", error="Anwendung beendet. Bitte Auftrag erneut starten; vorhandene Downloads bleiben erhalten.")
            result.append(row)
        return result

    def clear_completed(self):
        with self.connect() as db:
            db.execute("DELETE FROM jobs")

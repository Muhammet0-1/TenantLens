"""Small local SQLite store with private permissions and immutable run snapshots."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time


class Storage:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "tenantlens.sqlite3"
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL)")
        os.chmod(self.path, 0o600)
        # A server restart cannot truthfully claim an interrupted run completed.
        with self.connection() as db:
            for rid, payload in db.execute("SELECT id, data FROM runs").fetchall():
                data = json.loads(payload)
                if data.get("status") == "running":
                    data["status"] = "interrupted"
                    data["error"] = "server_restarted"
                    db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), rid))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_project(self, project):
        with self.connection() as db:
            db.execute("INSERT INTO projects VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated=excluded.updated", (project["id"], json.dumps(project, ensure_ascii=False), time.time()))

    def project(self, pid):
        with self.connection() as db:
            row = db.execute("SELECT data FROM projects WHERE id=?", (pid,)).fetchone()
        return json.loads(row[0]) if row else None

    def projects(self):
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM projects ORDER BY updated DESC")]

    def delete_project(self, pid):
        with self.connection() as db:
            db.execute("DELETE FROM projects WHERE id=?", (pid,))

    def save_run(self, run):
        with self.connection() as db:
            existing = db.execute("SELECT data FROM runs WHERE id=?", (run["id"],)).fetchone()
            if existing and json.loads(existing[0]).get("status") != "running":
                raise ValueError("Finished run snapshots are immutable.")
            db.execute("INSERT INTO runs VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (run["id"], run["project_id"], json.dumps(run, ensure_ascii=False), time.time()))

    def run(self, rid):
        with self.connection() as db:
            row = db.execute("SELECT data FROM runs WHERE id=?", (rid,)).fetchone()
        return json.loads(row[0]) if row else None

    def runs(self):
        with self.connection() as db:
            values = [json.loads(row[0]) for row in db.execute("SELECT data FROM runs ORDER BY created DESC LIMIT 200")]
        fields = ("id", "project_id", "project_name", "started_at", "finished_at", "status", "total", "completed", "counts", "request_count")
        return [{key: run.get(key) for key in fields} for run in values]

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, paths):
        self.paths = paths
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
                INSERT OR IGNORE INTO meta VALUES ('library_revision',0);
                CREATE TABLE IF NOT EXISTS tracks (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL,
                    source TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT UNIQUE NOT NULL,
                    duration REAL NOT NULL, license_json TEXT NOT NULL,
                    hashes BLOB NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL, video_path TEXT NOT NULL,
                    duration REAL NOT NULL DEFAULT 0, engines TEXT NOT NULL, purpose TEXT NOT NULL,
                    settings_json TEXT NOT NULL, state TEXT NOT NULL, status TEXT NOT NULL,
                    errors_json TEXT NOT NULL DEFAULT '[]', detections_json TEXT NOT NULL DEFAULT '[]',
                    note TEXT NOT NULL DEFAULT '', conclusion TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS tasks_created ON tasks(created_at DESC);
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    note TEXT NOT NULL, conclusion TEXT NOT NULL, created_at TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL DEFAULT '{}'
                );
            """)
            if "snapshot_json" not in {r[1] for r in db.execute("PRAGMA table_info(reviews)")}:
                db.execute("ALTER TABLE reviews ADD COLUMN snapshot_json TEXT NOT NULL DEFAULT '{}'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.paths.db, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def revision(self):
        with self.connect() as db:
            return db.execute("SELECT value FROM meta WHERE key='library_revision'").fetchone()[0]

    def tracks(self, include_hashes=False):
        with self.connect() as db:
            columns = "*" if include_hashes else "id,title,artist,source,path,sha256,duration,license_json,created_at,updated_at"
            rows = db.execute(f"SELECT {columns} FROM tracks ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["license"] = json.loads(item.pop("license_json"))
            result.append(item)
        return result

    def add_track(self, track, hashes):
        stamp = now()
        with self.connect() as db:
            db.execute("INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                track["id"], track["title"], track["artist"], track["source"], str(track["path"]),
                track["sha256"], track["duration"], json.dumps(track["license"], ensure_ascii=False),
                hashes, stamp, stamp))
            db.execute("UPDATE meta SET value=value+1 WHERE key='library_revision'")

    def update_track(self, track_id, title, artist, source, license_info):
        with self.connect() as db:
            db.execute("UPDATE tracks SET title=?,artist=?,source=?,license_json=?,updated_at=? WHERE id=?",
                       (title, artist, source, json.dumps(license_info, ensure_ascii=False), now(), track_id))

    def replace_track_audio(self, track_id, path, sha256, duration, hashes, license_info):
        with self.connect() as db:
            db.execute("UPDATE tracks SET path=?,sha256=?,duration=?,hashes=?,license_json=?,updated_at=? WHERE id=?",
                       (str(path), sha256, duration, hashes, json.dumps(license_info, ensure_ascii=False), now(), track_id))
            db.execute("UPDATE meta SET value=value+1 WHERE key='library_revision'")

    def remove_track(self, track_id):
        with self.connect() as db:
            row = db.execute("SELECT path FROM tracks WHERE id=?", (track_id,)).fetchone()
            db.execute("DELETE FROM tracks WHERE id=?", (track_id,))
            db.execute("UPDATE meta SET value=value+1 WHERE key='library_revision'")
        if row:
            path = Path(row[0]).resolve()
            if path.is_relative_to(self.paths.library):
                path.unlink(missing_ok=True)

    def create_task(self, filename, video_path, engines, purpose, settings):
        task_id = uuid.uuid4().hex
        stamp = now()
        with self.connect() as db:
            db.execute("""INSERT INTO tasks
                (id,filename,video_path,engines,purpose,settings_json,state,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,'running','审核中',?,?)""",
                       (task_id, filename, str(video_path), json.dumps(engines), purpose,
                        json.dumps(settings), stamp, stamp))
        return task_id

    def finish_task(self, task_id, duration, detections, errors, status, state="completed"):
        with self.connect() as db:
            db.execute("""UPDATE tasks SET duration=?,detections_json=?,errors_json=?,status=?,state=?,updated_at=?
                          WHERE id=?""", (duration, json.dumps(detections, ensure_ascii=False),
                        json.dumps(errors, ensure_ascii=False), status, state, now(), task_id))

    def get_task(self, task_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            reviews = db.execute("SELECT note,conclusion,created_at,snapshot_json FROM reviews WHERE task_id=? ORDER BY id",
                                 (task_id,)).fetchall()
        if not row:
            return None
        item = dict(row)
        for column, name in (("engines", "engines"), ("settings_json", "settings"),
                             ("errors_json", "errors"), ("detections_json", "detections")):
            item[name] = json.loads(item.pop(column))
        item["reviews"] = []
        for row in reviews:
            review = dict(row)
            review["snapshot"] = json.loads(review.pop("snapshot_json"))
            item["reviews"].append(review)
        return item

    def tasks(self, query=""):
        with self.connect() as db:
            rows = db.execute("""SELECT id,filename,duration,state,status,purpose,created_at,note,conclusion
                                FROM tasks WHERE filename LIKE ? OR detections_json LIKE ? OR note LIKE ?
                                ORDER BY created_at DESC""", (f"%{query}%",)*3).fetchall()
        return [dict(r) for r in rows]

    def review(self, task_id, note, conclusion):
        with self.connect() as db:
            task = db.execute("SELECT status,detections_json,errors_json FROM tasks WHERE id=?", (task_id,)).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            snapshot = dict(status=task["status"], detections=json.loads(task["detections_json"]),
                            errors=json.loads(task["errors_json"]))
            db.execute("UPDATE tasks SET note=?,conclusion=?,updated_at=? WHERE id=?",
                       (note, conclusion, now(), task_id))
            db.execute("INSERT INTO reviews(task_id,note,conclusion,created_at,snapshot_json) VALUES (?,?,?,?,?)",
                       (task_id, note, conclusion, now(), json.dumps(snapshot, ensure_ascii=False)))

    def delete_task(self, task_id):
        task = self.get_task(task_id)
        if not task:
            return
        with self.connect() as db:
            db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        path = Path(task["video_path"]).resolve()
        if path.is_relative_to(self.paths.videos):
            path.unlink(missing_ok=True)
        for path in self.paths.previews.glob(f"{task_id}_*.mp4"):
            path.unlink(missing_ok=True)

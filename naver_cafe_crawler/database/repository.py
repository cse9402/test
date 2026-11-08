"""SQLite 저장소."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from crawler.types import Board, CafeInfo, Comment
from database.models import ARTICLE_COLUMNS, SCHEMA


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Repository:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn = sqlite3.connect(":memory:") if self.db_path == ":memory:" else None
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = self._memory_conn or sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            if self._memory_conn is None:
                conn.execute("PRAGMA journal_mode=WAL")  # 앱(읽기)과 크롤러(쓰기) 동시 접근
            yield conn
            conn.commit()
        finally:
            if self._memory_conn is None:
                conn.close()

    # ---------- cafes / boards ----------
    def upsert_cafe(self, info: CafeInfo) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO cafes (cafe_name, club_id, title, url, updated_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(cafe_name) DO UPDATE SET
                     club_id=COALESCE(excluded.club_id, cafes.club_id),
                     title=COALESCE(excluded.title, cafes.title),
                     url=excluded.url, updated_at=excluded.updated_at""",
                (info.cafe_name, info.club_id, info.title, info.url, now_iso()))

    def get_cafe(self, cafe_name: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM cafes WHERE cafe_name=?", (cafe_name,)).fetchone()
        return dict(row) if row else None

    def upsert_boards(self, cafe_name: str, boards: list[Board]) -> None:
        with self._conn() as c:
            c.executemany(
                """INSERT INTO boards (cafe_name, menu_id, name, url, updated_at) VALUES (?,?,?,?,?)
                   ON CONFLICT(cafe_name, menu_id) DO UPDATE SET
                     name=excluded.name, url=excluded.url, updated_at=excluded.updated_at""",
                [(cafe_name, b.menu_id, b.name, b.url, now_iso()) for b in boards])

    def list_boards(self, cafe_name: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM boards WHERE cafe_name=? ORDER BY menu_id",
                             (cafe_name,)).fetchall()
        return [dict(r) for r in rows]

    # ---------- articles ----------
    def get_article_status(self, cafe_name: str, article_id: int) -> str | None:
        with self._conn() as c:
            row = c.execute("SELECT access_status FROM articles WHERE cafe_name=? AND article_id=?",
                            (cafe_name, article_id)).fetchone()
        return row["access_status"] if row else None

    def max_article_id(self, cafe_name: str, menu_id: int | None = None) -> int | None:
        sql = "SELECT MAX(article_id) AS m FROM articles WHERE cafe_name=?"
        args: list = [cafe_name]
        if menu_id is not None:
            sql += " AND menu_id=?"
            args.append(menu_id)
        with self._conn() as c:
            row = c.execute(sql, args).fetchone()
        return row["m"] if row and row["m"] is not None else None

    def save_article(self, record: dict) -> str:
        """
        (cafe_name, article_id) 기준 upsert. 반환: 'inserted' | 'updated' | 'kept'
        이미 'ok'로 저장된 글을 접근제한/실패 결과로 덮어쓰지 않음(본문 보존).
        """
        data = {k: record.get(k) for k in ARTICLE_COLUMNS}
        for key in ("image_urls", "attachments"):
            if isinstance(data[key], (list, dict)):
                data[key] = json.dumps(data[key], ensure_ascii=False)
        ts = now_iso()
        data["updated_at"] = ts
        data["collected_at"] = data.get("collected_at") or ts
        existing = self.get_article_status(data["cafe_name"], data["article_id"])
        with self._conn() as c:
            if existing is None:
                cols = ",".join(ARTICLE_COLUMNS)
                marks = ",".join("?" for _ in ARTICLE_COLUMNS)
                c.execute(f"INSERT INTO articles ({cols}) VALUES ({marks})",
                          [data[k] for k in ARTICLE_COLUMNS])
                return "inserted"
            if existing == "ok" and data["access_status"] != "ok":
                c.execute("UPDATE articles SET error_message=?, updated_at=? "
                          "WHERE cafe_name=? AND article_id=?",
                          (f"재확인 시 {data['access_status']}", ts,
                           data["cafe_name"], data["article_id"]))
                return "kept"
            sets = ",".join(f"{k}=COALESCE(?, {k})" if k not in ("access_status", "error_message")
                            else f"{k}=?" for k in ARTICLE_COLUMNS if k != "collected_at")
            values = [data[k] for k in ARTICLE_COLUMNS if k != "collected_at"]
            c.execute(f"UPDATE articles SET {sets} WHERE cafe_name=? AND article_id=?",
                      values + [data["cafe_name"], data["article_id"]])
            return "updated"

    def save_comments(self, cafe_name: str, article_id: int, comments: list[Comment]) -> int:
        ts = now_iso()
        with self._conn() as c:
            c.executemany(
                """INSERT INTO comments (cafe_name, article_id, comment_key, author, content,
                                         written_at, is_reply, collected_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(cafe_name, article_id, comment_key) DO UPDATE SET
                     author=excluded.author, content=excluded.content,
                     written_at=excluded.written_at, is_reply=excluded.is_reply""",
                [(cafe_name, article_id, cm.comment_key, cm.author, cm.content, cm.written_at,
                  int(cm.is_reply), ts) for cm in comments])
        return len(comments)

    def query_articles(self, cafe_name: str | None = None, keyword: str = "",
                       menu_ids: list[int] | None = None, statuses: list[str] | None = None,
                       date_from: str | None = None, date_to: str | None = None,
                       limit: int | None = None) -> list[dict]:
        sql = "SELECT * FROM articles WHERE 1=1"
        args: list = []
        if cafe_name:
            sql += " AND cafe_name=?"
            args.append(cafe_name)
        if keyword:
            sql += " AND (title LIKE ? OR content_text LIKE ?)"
            args += [f"%{keyword}%", f"%{keyword}%"]
        if menu_ids:
            sql += f" AND menu_id IN ({','.join('?' for _ in menu_ids)})"
            args += list(menu_ids)
        if statuses:
            sql += f" AND access_status IN ({','.join('?' for _ in statuses)})"
            args += list(statuses)
        if date_from:
            sql += " AND written_at >= ?"
            args.append(date_from)
        if date_to:
            sql += " AND written_at < ?"
            args.append(date_to + "T99")  # 해당 일자 끝까지 포함
        sql += " ORDER BY article_id DESC"
        if limit:
            sql += " LIMIT ?"
            args.append(int(limit))
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def query_comments(self, cafe_name: str, article_id: int) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM comments WHERE cafe_name=? AND article_id=? ORDER BY id",
                             (cafe_name, article_id)).fetchall()
        return [dict(r) for r in rows]

    def article_stats(self, cafe_name: str) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute("SELECT access_status, COUNT(*) n FROM articles WHERE cafe_name=? "
                             "GROUP BY access_status", (cafe_name,)).fetchall()
        return {r["access_status"]: r["n"] for r in rows}

    # ---------- jobs ----------
    def create_job(self, cafe_name: str, params: dict, status: str = "pending") -> int:
        with self._conn() as c:
            cur = c.execute("INSERT INTO crawl_jobs (cafe_name, params, status, started_at) "
                            "VALUES (?,?,?,?)",
                            (cafe_name, json.dumps(params, ensure_ascii=False), status, now_iso()))
            return int(cur.lastrowid)

    def get_job(self, job_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM crawl_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        job = dict(row)
        job["params"] = json.loads(job["params"] or "{}")
        return job

    def list_jobs(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM crawl_jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    _JOB_FIELDS = {"status", "current_menu_id", "current_page", "success_count",
                   "restricted_count", "failed_count", "skipped_count", "message", "pid",
                   "finished_at", "stop_requested", "started_at"}

    def update_job(self, job_id: int, **fields) -> None:
        fields = {k: v for k, v in fields.items() if k in self._JOB_FIELDS}
        if not fields:
            return
        sets = ",".join(f"{k}=?" for k in fields)
        with self._conn() as c:
            c.execute(f"UPDATE crawl_jobs SET {sets} WHERE id=?", [*fields.values(), job_id])

    def request_stop(self, job_id: int) -> None:
        self.update_job(job_id, stop_requested=1)

    def is_stop_requested(self, job_id: int) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT stop_requested FROM crawl_jobs WHERE id=?", (job_id,)).fetchone()
        return bool(row and row["stop_requested"])

    def add_log(self, job_id: int | None, level: str, message: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO crawl_logs (job_id, level, message, created_at) VALUES (?,?,?,?)",
                      (job_id, level, message[:2000], now_iso()))

    def list_logs(self, job_id: int | None = None, limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM crawl_logs"
        args: list = []
        if job_id is not None:
            sql += " WHERE job_id=?"
            args.append(job_id)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

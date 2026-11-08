"""SQLite 스키마."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS cafes (
    cafe_name   TEXT PRIMARY KEY,
    club_id     TEXT,
    title       TEXT,
    url         TEXT,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS boards (
    cafe_name   TEXT NOT NULL,
    menu_id     INTEGER NOT NULL,
    name        TEXT,
    url         TEXT,
    updated_at  TEXT,
    PRIMARY KEY (cafe_name, menu_id)
);

CREATE TABLE IF NOT EXISTS articles (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    cafe_name      TEXT NOT NULL,
    club_id        TEXT,
    menu_id        INTEGER,
    board_name     TEXT,
    article_id     INTEGER NOT NULL,
    url            TEXT,
    title          TEXT,
    content_text   TEXT,
    content_html   TEXT,
    author         TEXT,
    written_at     TEXT,
    view_count     INTEGER,
    comment_count  INTEGER,
    image_urls     TEXT,       -- JSON 배열
    attachments    TEXT,       -- JSON 배열
    access_status  TEXT NOT NULL,
    error_message  TEXT,
    collected_at   TEXT,
    updated_at     TEXT,
    job_id         INTEGER,
    UNIQUE (cafe_name, article_id)
);
CREATE INDEX IF NOT EXISTS idx_articles_board ON articles (cafe_name, menu_id, article_id);
CREATE INDEX IF NOT EXISTS idx_articles_written ON articles (written_at);

CREATE TABLE IF NOT EXISTS comments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cafe_name    TEXT NOT NULL,
    article_id   INTEGER NOT NULL,
    comment_key  TEXT NOT NULL,
    author       TEXT,
    content      TEXT,
    written_at   TEXT,
    is_reply     INTEGER DEFAULT 0,
    collected_at TEXT,
    UNIQUE (cafe_name, article_id, comment_key)
);

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    cafe_name        TEXT NOT NULL,
    params           TEXT,          -- JSON (CrawlOptions)
    status           TEXT NOT NULL, -- pending/running/completed/stopped/failed/blocked/captcha/session_expired
    stop_requested   INTEGER DEFAULT 0,
    current_menu_id  INTEGER,
    current_page     INTEGER,
    success_count    INTEGER DEFAULT 0,
    restricted_count INTEGER DEFAULT 0,
    failed_count     INTEGER DEFAULT 0,
    skipped_count    INTEGER DEFAULT 0,
    message          TEXT,
    pid              INTEGER,
    started_at       TEXT,
    finished_at      TEXT
);

CREATE TABLE IF NOT EXISTS crawl_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER,
    level       TEXT,
    message     TEXT,
    created_at  TEXT
);
"""

ARTICLE_COLUMNS = [
    "cafe_name", "club_id", "menu_id", "board_name", "article_id", "url", "title",
    "content_text", "content_html", "author", "written_at", "view_count", "comment_count",
    "image_urls", "attachments", "access_status", "error_message", "collected_at",
    "updated_at", "job_id",
]

FINAL_JOB_STATUSES = {"completed", "stopped", "failed", "blocked", "captcha", "session_expired"}

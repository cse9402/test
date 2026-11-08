"""환경 설정 로더 (.env → Settings)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _path(name: str, default: str) -> Path:
    p = Path(_env_str(name, default))
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


def cafe_name_from_url(url: str) -> str:
    """https://cafe.naver.com/adoutdoor -> adoutdoor"""
    path = urlparse(url).path.strip("/")
    if not path:
        raise ValueError(f"카페 주소에서 카페 이름을 찾을 수 없습니다: {url}")
    return path.split("/")[0]


@dataclass(frozen=True)
class Settings:
    cafe_url: str
    profile_dir: Path
    db_path: Path
    log_dir: Path
    export_dir: Path
    media_dir: Path
    diagnostics_dir: Path
    headless: bool
    browser_channel: str
    browser_executable_path: str
    page_timeout_ms: int
    delay_min: float
    delay_max: float
    max_retries: int
    retry_backoff_seconds: float
    default_max_articles: int
    media_download_policy_confirmed: bool
    list_url_template: str
    article_url_template: str
    search_url_template: str
    search_query_encoding: str

    @property
    def cafe_name(self) -> str:
        return cafe_name_from_url(self.cafe_url)

    def with_cafe_url(self, url: str) -> "Settings":
        from dataclasses import replace
        cafe_name_from_url(url)  # 검증
        return replace(self, cafe_url=url.rstrip("/"))

    def ensure_dirs(self) -> None:
        for d in (self.db_path.parent, self.log_dir, self.export_dir, self.media_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings(env_file: str | os.PathLike | None = None) -> Settings:
    load_dotenv(env_file or BASE_DIR / ".env", override=False)
    delay_min = max(1.0, _env_float("REQUEST_DELAY_MIN", 3.0))  # 1초 미만 금지
    delay_max = max(delay_min, _env_float("REQUEST_DELAY_MAX", 6.0))
    return Settings(
        cafe_url=_env_str("CAFE_URL", "https://cafe.naver.com/adoutdoor").rstrip("/"),
        profile_dir=_path("BROWSER_PROFILE_DIR", "./browser_profile"),
        db_path=_path("DB_PATH", "./data/cafe.db"),
        log_dir=_path("LOG_DIR", "./logs"),
        export_dir=_path("EXPORT_DIR", "./exports"),
        media_dir=_path("MEDIA_DIR", "./data/media"),
        diagnostics_dir=_path("DIAGNOSTICS_DIR", "./diagnostics"),
        headless=_env_bool("HEADLESS", False),
        browser_channel=_env_str("BROWSER_CHANNEL", ""),
        browser_executable_path=_env_str("BROWSER_EXECUTABLE_PATH", ""),
        page_timeout_ms=_env_int("PAGE_TIMEOUT_MS", 30000),
        delay_min=delay_min,
        delay_max=delay_max,
        max_retries=max(0, min(5, _env_int("MAX_RETRIES", 2))),
        retry_backoff_seconds=max(1.0, _env_float("RETRY_BACKOFF_SECONDS", 10.0)),
        default_max_articles=max(1, _env_int("DEFAULT_MAX_ARTICLES", 100)),
        media_download_policy_confirmed=_env_bool("MEDIA_DOWNLOAD_POLICY_CONFIRMED", False),
        list_url_template=_env_str(
            "LIST_URL_TEMPLATE",
            "https://cafe.naver.com/ArticleList.nhn?search.clubid={club_id}"
            "&search.menuid={menu_id}&search.boardtype=L&search.page={page}",
        ),
        article_url_template=_env_str(
            "ARTICLE_URL_TEMPLATE", "https://cafe.naver.com/{cafe_name}/{article_id}"
        ),
        search_url_template=_env_str(
            "SEARCH_URL_TEMPLATE",
            "https://cafe.naver.com/ArticleSearchList.nhn?search.clubid={club_id}"
            "&search.menuid={menu_id}&search.searchBy=0&search.query={query}&search.page={page}",
        ),
        search_query_encoding=_env_str("SEARCH_QUERY_ENCODING", "utf-8"),
    )

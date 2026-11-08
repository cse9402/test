"""URL 생성·해석 (템플릿은 .env 에서 변경 가능)."""
from __future__ import annotations

import re
from urllib.parse import quote, urlparse

from config import Settings

_ARTICLE_URL_PATTERNS = [
    re.compile(r"[?&]articleid=(\d+)", re.I),
    re.compile(r"/articles/(\d+)"),
]
_CLUB_PATTERNS = [re.compile(r"[?&](?:search\.)?clubid=(\d+)", re.I), re.compile(r"/cafes/(\d+)")]


def build_list_url(settings: Settings, club_id: str, menu_id: int, page: int) -> str:
    return settings.list_url_template.format(
        cafe_name=settings.cafe_name, club_id=club_id, menu_id=menu_id, page=page)


def build_article_url(settings: Settings, article_id: int, club_id: str | None = None) -> str:
    return settings.article_url_template.format(
        cafe_name=settings.cafe_name, club_id=club_id or "", article_id=article_id)


def build_search_url(settings: Settings, club_id: str, menu_id: int, query: str, page: int) -> str:
    encoded = quote(query, encoding=settings.search_query_encoding or "utf-8")
    return settings.search_url_template.format(
        cafe_name=settings.cafe_name, club_id=club_id, menu_id=menu_id, query=encoded, page=page)


def parse_article_url(url: str, cafe_name: str | None = None) -> dict:
    """게시글 URL에서 article_id / club_id / cafe_name 추출. 실패 시 article_id=None."""
    result = {"article_id": None, "club_id": None, "cafe_name": None}
    url = url.strip()
    for pat in _ARTICLE_URL_PATTERNS:
        m = pat.search(url)
        if m:
            result["article_id"] = int(m.group(1))
            break
    for pat in _CLUB_PATTERNS:
        m = pat.search(url)
        if m:
            result["club_id"] = m.group(1)
            break
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    # https://cafe.naver.com/{cafe_name}/{article_id}
    if parsed.netloc.endswith("cafe.naver.com") and len(parts) >= 2 and parts[1].isdigit() \
            and not parts[0].lower().startswith(("f-e", "ca-fe")):
        result["cafe_name"] = parts[0]
        if result["article_id"] is None:
            result["article_id"] = int(parts[1])
    if result["cafe_name"] is None and cafe_name:
        result["cafe_name"] = cafe_name
    return result

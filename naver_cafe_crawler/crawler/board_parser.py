"""게시글 목록 파서. 특정 테이블 구조에 의존하지 않도록 '게시글 링크 → 상위 행' 방식 사용."""
from __future__ import annotations

from datetime import datetime

from bs4 import Tag

from crawler import selectors as S
from crawler.parse_utils import (clean_text, first_regex, make_soup, parse_int,
                                 parse_naver_datetime, select_first, select_text)
from crawler.types import ArticleSummary


def _row_of(a: Tag) -> Tag | None:
    for parent in a.parents:
        if isinstance(parent, Tag) and parent.name in S.LIST_ROW_TAGS:
            return parent
    return None


def _is_notice(row: Tag) -> bool:
    classes = " ".join(row.get("class", []))
    inner = " ".join(" ".join(t.get("class", [])) for t in row.find_all(True))
    return any(h in classes or h in inner for h in S.ROW_NOTICE_HINTS)


def parse_article_list(html: str, now: datetime | None = None) -> list[ArticleSummary]:
    soup = make_soup(html)
    results: dict[int, ArticleSummary] = {}
    title_candidates: dict[int, list[str]] = {}
    for a in soup.find_all("a", href=True):
        aid = first_regex(S.ARTICLE_ID_PATTERNS, a["href"])
        if aid is None:
            continue
        aid_i = int(aid)
        text = clean_text(a.get_text(" "))
        classes = a.get("class", [])
        is_title_link = "article" in classes or "title" in classes
        is_comment_link = "cmt" in classes or "commentFocus" in a["href"]
        if text and not is_comment_link:
            title_candidates.setdefault(aid_i, [])
            if is_title_link:
                title_candidates[aid_i].insert(0, text)
            else:
                title_candidates[aid_i].append(text)
        if aid_i in results:
            continue
        row = _row_of(a)
        summary = ArticleSummary(article_id=aid_i, title="", url=a["href"])
        if row is not None:
            title_el = select_first(row, S.ROW_TITLE_SELECTORS)
            if title_el is not None:
                t = clean_text(title_el.get_text(" "))
                if t:
                    title_candidates.setdefault(aid_i, []).insert(0, t)
            summary.author = select_text(row, S.ROW_AUTHOR_SELECTORS)
            summary.written_at = parse_naver_datetime(select_text(row, S.ROW_DATE_SELECTORS), now)
            summary.view_count = parse_int(select_text(row, S.ROW_VIEW_SELECTORS))
            summary.comment_count = parse_int(select_text(row, S.ROW_COMMENT_SELECTORS))
            summary.is_notice = _is_notice(row)
        results[aid_i] = summary
    for aid_i, summary in results.items():
        cands = [c for c in title_candidates.get(aid_i, []) if c and not c.startswith("[")]
        summary.title = cands[0] if cands else ""
    return list(results.values())


def regular_articles(items: list[ArticleSummary]) -> list[ArticleSummary]:
    """공지 제외 + 게시글 ID 내림차순(최신순)."""
    return sorted([i for i in items if not i.is_notice], key=lambda x: x.article_id, reverse=True)

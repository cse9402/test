"""게시글 상세 파서 및 접근 상태 판정."""
from __future__ import annotations

from datetime import datetime

from crawler import selectors as S
from crawler.parse_utils import (clean_text, make_soup, parse_int, parse_naver_datetime,
                                 select_first, select_text)
from crawler.types import AccessStatus, ArticleDetail, Comment, FetchResult


def _contains_any(text: str, markers: list[str]) -> bool:
    low = text.lower()
    return any(m.lower() in low for m in markers)


def detect_access_status(result: FetchResult) -> AccessStatus:
    """
    판정 순서:
      1) 로그인 페이지로 이동 → LOGIN_REQUIRED
      2) 본문 요소 존재 → OK (본문 속 단어 때문에 오판하지 않도록 우선 판정)
      3) CAPTCHA 요소/문구 → CAPTCHA
      4) 알림창·페이지 문구 → NOT_FOUND / LEVEL_RESTRICTED / MEMBERS_ONLY / LOGIN_REQUIRED
      5) 그 외 → UNKNOWN_STRUCTURE (선택자 수정 필요 가능성)
    """
    if result.status == 429:
        return AccessStatus.BLOCKED
    if any(h in (result.final_url or "") for h in S.LOGIN_URL_HINTS):
        return AccessStatus.LOGIN_REQUIRED
    soup = make_soup(result.html)
    if select_first(soup, S.DETAIL_CONTENT_SELECTORS) is not None:
        return AccessStatus.OK
    top_soup = make_soup(result.top_html) if result.top_html else soup
    if select_first(soup, S.CAPTCHA_SELECTORS) or select_first(top_soup, S.CAPTCHA_SELECTORS):
        return AccessStatus.CAPTCHA
    page_text = clean_text(soup.get_text(" ")) + " " + clean_text(top_soup.get_text(" "))
    if _contains_any(page_text, S.CAPTCHA_MARKERS):
        return AccessStatus.CAPTCHA
    texts = " ".join(result.dialogs) + " " + page_text
    if _contains_any(texts, S.NOT_FOUND_MARKERS):
        return AccessStatus.NOT_FOUND
    if _contains_any(texts, S.LEVEL_MARKERS):
        return AccessStatus.LEVEL_RESTRICTED
    if _contains_any(texts, S.LOGIN_MARKERS):
        return AccessStatus.LOGIN_REQUIRED
    if _contains_any(texts, S.MEMBERS_ONLY_MARKERS):
        return AccessStatus.MEMBERS_ONLY
    if result.status in (403,):
        return AccessStatus.BLOCKED
    return AccessStatus.UNKNOWN_STRUCTURE


def parse_comments(soup) -> list[Comment]:
    items = []
    for sel in S.COMMENT_ITEM_SELECTORS:
        items = soup.select(sel)
        if items:
            break
    comments: list[Comment] = []
    for idx, li in enumerate(items):
        text = select_text(li, S.COMMENT_TEXT_SELECTORS)
        if not text:
            continue  # 삭제 댓글 등
        classes = " ".join(li.get("class", []))
        key = li.get("id") or li.get("data-comment-id") or f"idx-{idx}"
        comments.append(Comment(
            comment_key=str(key),
            author=select_text(li, S.COMMENT_AUTHOR_SELECTORS),
            content=text,
            written_at=parse_naver_datetime(select_text(li, S.COMMENT_DATE_SELECTORS)),
            is_reply=any(h in classes for h in S.COMMENT_REPLY_HINTS),
        ))
    return comments


def parse_article(html: str, include_html: bool = False, include_comments: bool = False,
                  now: datetime | None = None) -> ArticleDetail:
    soup = make_soup(html)
    detail = ArticleDetail()
    detail.title = select_text(soup, S.DETAIL_TITLE_SELECTORS)
    content_el = select_first(soup, S.DETAIL_CONTENT_SELECTORS)
    if content_el is not None:
        for bad in content_el.select("script, style"):
            bad.decompose()
        detail.content_text = clean_text(content_el.get_text("\n"))
        if include_html:
            detail.content_html = str(content_el)
    detail.author = select_text(soup, S.DETAIL_AUTHOR_SELECTORS)
    detail.written_at = parse_naver_datetime(select_text(soup, S.DETAIL_DATE_SELECTORS), now)
    detail.view_count = parse_int(select_text(soup, S.DETAIL_VIEW_SELECTORS))
    detail.comment_count = parse_int(select_text(soup, S.DETAIL_COMMENT_COUNT_SELECTORS))
    detail.board_name = select_text(soup, S.DETAIL_BOARD_NAME_SELECTORS)

    seen: set[str] = set()
    for sel in S.DETAIL_IMAGE_SELECTORS:
        for img in soup.select(sel):
            src = img.get("data-lazy-src") or img.get("data-src") or img.get("src")
            if src and src.startswith("http") and src not in seen:
                seen.add(src)
                detail.image_urls.append(src)
    for sel in S.DETAIL_ATTACHMENT_SELECTORS:
        for el in soup.select(sel):
            name = clean_text(el.get_text(" "))
            link = el if el.name == "a" else el.find("a", href=True)
            href = link.get("href") if link is not None else None
            if name:
                detail.attachments.append({"name": name[:200], "url": href})
        if detail.attachments:
            break
    if include_comments:
        detail.comments = parse_comments(soup)
    return detail

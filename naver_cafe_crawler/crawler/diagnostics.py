"""
현장 진단: 실제 사이트 구조를 저장하고 파서 적중 여부를 보고서로 출력.
결과 폴더(diagnostics/날짜시각)에 HTML·스크린샷·report.json 이 저장됩니다.
※ HTML 에는 닉네임 등 개인정보가 포함될 수 있으므로 외부에 공유하지 마세요.
  쿠키·요청 헤더는 저장하지 않습니다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config import Settings
from crawler import selectors as S
from crawler.article_parser import detect_access_status, parse_article
from crawler.board_parser import parse_article_list, regular_articles
from crawler.browser import BrowserSession
from crawler.cafe_parser import is_join_required, parse_board_list, parse_cafe_info
from crawler.parse_utils import make_soup
from crawler.urls import build_article_url, build_list_url


def _selector_hits(html: str, selectors: list[str]) -> dict[str, int]:
    soup = make_soup(html)
    hits = {}
    for sel in selectors:
        try:
            hits[sel] = len(soup.select(sel))
        except Exception:
            hits[sel] = -1
    return hits


def run_diagnostics(settings: Settings, menu_id: int | None = None,
                    article_url: str | None = None) -> Path:
    out = settings.diagnostics_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"cafe_url": settings.cafe_url, "created_at": datetime.now().isoformat()}
    with BrowserSession(settings) as b:
        assert b.page is not None
        requests: list[str] = []
        b.page.on("request", lambda r: requests.append(f"{r.method} {r.resource_type} "
                                                       f"{r.url.split('?')[0]}"))
        report["logged_in"] = b.is_logged_in()

        # 1) 메인
        res = b.fetch(settings.cafe_url)
        (out / "main_top.html").write_text(res.top_html, encoding="utf-8")
        (out / "main_frame.html").write_text(res.html, encoding="utf-8")
        b.screenshot(out / "main.png")
        info = parse_cafe_info(res.top_html or res.html, settings.cafe_name, settings.cafe_url,
                               extra_html=res.html)
        boards = parse_board_list(res.html) or parse_board_list(res.top_html)
        report["main"] = {
            "final_url": res.final_url, "http_status": res.status, "frame_url": res.frame_url,
            "frames": [{"name": f.name, "url": f.url.split("?")[0]} for f in b.page.frames],
            "club_id": info.club_id, "title": info.title, "join_button_visible":
                is_join_required(res.top_html) or is_join_required(res.html),
            "boards_found": len(boards),
            "boards": [{"menu_id": x.menu_id, "name": x.name} for x in boards[:80]],
            "dialogs": res.dialogs,
        }

        # 2) 목록
        try:
            first_article_url = _diagnose_list(b, settings, out, report, info, boards, menu_id,
                                               article_url)
        except Exception as exc:  # noqa: BLE001
            report["list_error"] = str(exc)[:500]
            first_article_url = article_url
        # 3) 상세
        if first_article_url:
            try:
                _diagnose_article(b, out, report, first_article_url)
            except Exception as exc:  # noqa: BLE001
                report["article_error"] = str(exc)[:500]
        report["requests_sample"] = sorted(set(requests))[:300]
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    return out


def _diagnose_list(b, settings, out, report, info, boards, menu_id, article_url):
    target_menu = menu_id if menu_id is not None else (boards[0].menu_id if boards else None)
    first_article_url = article_url
    if info.club_id and target_menu is not None:
        url = build_list_url(settings, info.club_id, target_menu, 1)
        lres = b.fetch(url, S.LIST_WAIT_SELECTORS)
        (out / "list_frame.html").write_text(lres.html, encoding="utf-8")
        b.screenshot(out / "list.png")
        items = parse_article_list(lres.html)
        report["list"] = {
            "url": url, "final_url": lres.final_url, "http_status": lres.status,
            "frame_url": lres.frame_url, "articles_found": len(items),
            "sample": [vars(i) for i in items[:10]],
            "selector_hits": _selector_hits(lres.html, S.ROW_TITLE_SELECTORS
                                            + S.ROW_DATE_SELECTORS + S.ROW_VIEW_SELECTORS),
            "dialogs": lres.dialogs,
        }
        if not first_article_url and items:
            first_article_url = build_article_url(
            settings, (regular_articles(items) or items)[0].article_id, info.club_id)
    return first_article_url


def _diagnose_article(b, out, report, first_article_url):
    ares = b.fetch(first_article_url, S.DETAIL_WAIT_SELECTORS)
    (out / "article_frame.html").write_text(ares.html, encoding="utf-8")
    b.screenshot(out / "article.png")
    status = detect_access_status(ares)
    detail = parse_article(ares.html, include_comments=True)
    report["article"] = {
        "url": first_article_url, "final_url": ares.final_url,
        "http_status": ares.status, "frame_url": ares.frame_url,
        "access_status": status.value, "dialogs": ares.dialogs,
        "title": detail.title, "author": detail.author, "written_at": detail.written_at,
        "view_count": detail.view_count, "content_preview": (detail.content_text or "")[:200],
        "images": len(detail.image_urls), "comments": len(detail.comments),
        "selector_hits": _selector_hits(ares.html, S.DETAIL_TITLE_SELECTORS
                                        + S.DETAIL_CONTENT_SELECTORS
                                        + S.DETAIL_AUTHOR_SELECTORS
                                        + S.DETAIL_DATE_SELECTORS
                                        + S.COMMENT_ITEM_SELECTORS),
    }

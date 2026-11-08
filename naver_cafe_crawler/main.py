"""
명령줄 실행 진입점.

  python main.py login                    # 브라우저에서 직접 로그인
  python main.py status                   # 로그인/회원 상태 확인
  python main.py boards                   # 게시판 목록 조회·저장
  python main.py crawl --menu 1 --pages 1-3 --max 50
  python main.py crawl --resume 3         # 중단된 작업 재개
  python main.py article https://cafe.naver.com/adoutdoor/12345
  python main.py export --format xlsx
  python main.py diagnose                 # 사이트 구조 진단
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from config import load_settings
from utils.logger import setup_logging


def _settings(args):
    s = load_settings()
    if getattr(args, "cafe_url", None):
        s = s.with_cafe_url(args.cafe_url)
    s.ensure_dirs()
    setup_logging(s.log_dir)
    return s


def _parse_pages(text: str) -> tuple[int, int]:
    if "-" in text:
        a, b = text.split("-", 1)
        return int(a), int(b)
    return int(text), int(text)


def cmd_login(args) -> int:
    from crawler.auth import interactive_login
    return 0 if interactive_login(_settings(args), timeout_seconds=args.timeout) else 1


def cmd_logout(args) -> int:
    from crawler.auth import clear_local_session
    s = _settings(args)
    if not args.yes:
        ans = input(f"로컬 세션 폴더({s.profile_dir})를 삭제합니다. 계속할까요? [y/N] ")
        if ans.strip().lower() != "y":
            return 1
    print("삭제했습니다." if clear_local_session(s) else "삭제할 세션이 없습니다.")
    return 0


def cmd_status(args) -> int:
    from crawler.auth import check_login_status
    status = check_login_status(_settings(args))
    if args.json:
        print("JSON:" + json.dumps(status.to_dict(), ensure_ascii=False))
    else:
        print(f"로그인: {'예' if status.logged_in else '아니오'} / 카페 회원 추정: {status.cafe_member}")
        print(status.message)
    return 0


def cmd_boards(args) -> int:
    from crawler.browser import BrowserSession
    from crawler.collector import Collector
    from database.repository import Repository
    s = _settings(args)
    repo = Repository(s.db_path)
    with BrowserSession(s) as b:
        info, boards = Collector(s, repo, b, progress=print).discover_cafe()
    if args.json:
        print("JSON:" + json.dumps({"club_id": info.club_id, "title": info.title,
                                    "boards": [vars(x) for x in boards]}, ensure_ascii=False))
    else:
        print(f"카페: {info.title} (ID: {info.club_id})")
        for x in boards:
            print(f"  [{x.menu_id:>5}] {x.name}")
    return 0 if boards else 2


def _run_job(s, job_id: int, resume: bool) -> int:
    from crawler.browser import BrowserSession
    from crawler.collector import Collector
    from database.repository import Repository
    repo = Repository(s.db_path)
    try:
        with BrowserSession(s) as b:
            result = Collector(s, repo, b, progress=print).run(job_id, resume=resume)
    except Exception as exc:  # 브라우저 실행 실패 등
        repo.update_job(job_id, status="failed", message=str(exc),
                        finished_at=datetime.now().isoformat(timespec="seconds"))
        print(f"실패: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 3


def cmd_crawl(args) -> int:
    from crawler.collector import CrawlOptions
    from database.repository import Repository
    s = _settings(args)
    repo = Repository(s.db_path)
    if args.resume:
        return _run_job(s, args.resume, resume=True)
    if args.job_id:  # Streamlit 앱이 미리 만든 작업
        return _run_job(s, args.job_id, resume=False)
    start, end = _parse_pages(args.pages)
    options = CrawlOptions(
        menu_ids=args.menu or [], article_urls=args.urls or [], start_page=start, end_page=end,
        keyword=args.keyword or "", keyword_scope=args.scope, use_site_search=args.site_search,
        date_from=args.date_from, date_to=args.date_to,
        max_articles=args.max or s.default_max_articles, only_new=args.only_new,
        include_comments=args.comments, save_html=args.save_html,
        download_media=args.download_media, recheck_restricted=args.recheck)
    try:
        options.validate()
    except ValueError as exc:
        print(f"입력 오류: {exc}")
        return 1
    job_id = repo.create_job(s.cafe_name, options.to_dict())
    print(f"작업 {job_id} 시작")
    return _run_job(s, job_id, resume=False)


def cmd_article(args) -> int:
    args.menu, args.pages, args.keyword, args.scope = [], "1", "", "title"
    args.site_search = args.only_new = args.save_html = args.download_media = False
    args.date_from = args.date_to = None
    args.max, args.resume, args.job_id, args.recheck = len(args.urls), None, None, True
    return cmd_crawl(args)


def cmd_export(args) -> int:
    from database.repository import Repository
    from utils.exporter import export_file
    s = _settings(args)
    rows = Repository(s.db_path).query_articles(
        cafe_name=s.cafe_name, keyword=args.keyword or "", menu_ids=args.menu,
        statuses=None if args.all_status else ["ok"], date_from=args.date_from,
        date_to=args.date_to)
    out = args.out or (s.export_dir / f"{s.cafe_name}_{datetime.now():%Y%m%d_%H%M%S}.{args.format}")
    path = export_file(rows, out, include_html=args.include_html)
    print(f"{len(rows)}건 저장: {path}")
    return 0


def cmd_jobs(args) -> int:
    from database.repository import Repository
    s = _settings(args)
    for j in Repository(s.db_path).list_jobs(args.limit):
        print(f"#{j['id']} {j['status']:<16} 성공 {j['success_count']} 제한 {j['restricted_count']} "
              f"실패 {j['failed_count']} 건너뜀 {j['skipped_count']} | {j['message'] or ''}")
    return 0


def cmd_diagnose(args) -> int:
    from crawler.diagnostics import run_diagnostics
    out = run_diagnostics(_settings(args), menu_id=args.menu, article_url=args.article_url)
    print(f"진단 결과 저장: {out}\n report.json 의 boards_found / articles_found / selector_hits 를 확인하세요.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="네이버 카페 게시글 수집기 (본인 계정 권한 범위 내)")
    p.add_argument("--cafe-url", help="대상 카페 주소 (기본: .env 의 CAFE_URL)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("login", help="브라우저에서 직접 네이버 로그인")
    sp.add_argument("--timeout", type=int, default=300)
    sp.set_defaults(func=cmd_login)

    sp = sub.add_parser("logout", help="로컬 로그인 세션 삭제")
    sp.add_argument("-y", "--yes", action="store_true")
    sp.set_defaults(func=cmd_logout)

    sp = sub.add_parser("status", help="로그인 상태 확인")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("boards", help="게시판 목록 조회")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_boards)

    sp = sub.add_parser("crawl", help="게시글 수집")
    sp.add_argument("--menu", type=int, nargs="*", help="게시판 ID (여러 개 가능)")
    sp.add_argument("--urls", nargs="*", help="게시글 URL 직접 지정")
    sp.add_argument("--pages", default="1-3", help="페이지 범위 예: 1-5")
    sp.add_argument("--keyword")
    sp.add_argument("--scope", choices=["title", "body", "both"], default="title")
    sp.add_argument("--site-search", action="store_true", help="카페 내부 검색 페이지 사용(검증 필요)")
    sp.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    sp.add_argument("--to", dest="date_to", help="YYYY-MM-DD")
    sp.add_argument("--max", type=int)
    sp.add_argument("--only-new", action="store_true", help="마지막 수집 이후 신규 글만")
    sp.add_argument("--comments", action="store_true", help="댓글 수집")
    sp.add_argument("--save-html", action="store_true", help="본문 HTML 저장")
    sp.add_argument("--download-media", action="store_true", help="이미지 다운로드(정책 확인 필요)")
    sp.add_argument("--recheck", action="store_true", help="접근 제한 글 다시 확인")
    sp.add_argument("--resume", type=int, help="중단된 작업 ID 재개")
    sp.add_argument("--job-id", type=int, help=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_crawl)

    sp = sub.add_parser("article", help="게시글 URL 직접 수집")
    sp.add_argument("urls", nargs="+")
    sp.add_argument("--comments", action="store_true")
    sp.set_defaults(func=cmd_article)

    sp = sub.add_parser("export", help="CSV/Excel 내보내기")
    sp.add_argument("--format", choices=["csv", "xlsx"], default="xlsx")
    sp.add_argument("--out")
    sp.add_argument("--keyword")
    sp.add_argument("--menu", type=int, nargs="*")
    sp.add_argument("--from", dest="date_from")
    sp.add_argument("--to", dest="date_to")
    sp.add_argument("--all-status", action="store_true", help="접근 제한·실패 기록도 포함")
    sp.add_argument("--include-html", action="store_true")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("jobs", help="작업 이력")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_jobs)

    sp = sub.add_parser("diagnose", help="사이트 구조 진단")
    sp.add_argument("--menu", type=int)
    sp.add_argument("--article-url")
    sp.set_defaults(func=cmd_diagnose)
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

"""크롤링 오케스트레이션: 게시판 순회 → 필터 → 상세 수집 → 저장."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Protocol

from config import Settings
from crawler import selectors as S
from crawler.article_parser import detect_access_status, parse_article
from crawler.board_parser import parse_article_list, regular_articles
from crawler.cafe_parser import parse_board_list, parse_cafe_info
from crawler.types import (AccessStatus, ArticleSummary, BlockedError, CafeInfo,
                           CaptchaDetectedError, CrawlerError, FetchResult, SessionExpiredError,
                           TransientError)
from crawler.urls import build_article_url, build_list_url, build_search_url, parse_article_url
from database.models import FINAL_JOB_STATUSES
from database.repository import Repository
from utils.logger import get_logger
from utils.rate_limiter import RateLimiter, with_retry

log = get_logger("collector")


class Fetcher(Protocol):
    def fetch(self, url: str, wait_selectors: list[str] | None = None) -> FetchResult: ...
    def is_logged_in(self) -> bool: ...
    def download(self, url: str, dest: Path) -> Path: ...


@dataclass
class CrawlOptions:
    menu_ids: list[int] = field(default_factory=list)
    article_urls: list[str] = field(default_factory=list)
    start_page: int = 1
    end_page: int = 3
    keyword: str = ""
    keyword_scope: str = "title"     # title | body | both
    use_site_search: bool = False    # 카페 내부 검색 페이지 사용 (URL 템플릿 검증 필요)
    date_from: str | None = None     # 'YYYY-MM-DD'
    date_to: str | None = None
    max_articles: int = 100
    only_new: bool = False           # 마지막 수집 이후 신규 글만
    include_comments: bool = False
    save_html: bool = False
    download_media: bool = False
    recheck_restricted: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlOptions":
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def validate(self) -> None:
        if self.start_page < 1 or self.end_page < self.start_page:
            raise ValueError("페이지 범위가 올바르지 않습니다.")
        if self.keyword_scope not in {"title", "body", "both"}:
            raise ValueError("keyword_scope 는 title/body/both 중 하나여야 합니다.")
        if self.max_articles < 1:
            raise ValueError("최대 수집 건수는 1 이상이어야 합니다.")
        for d in (self.date_from, self.date_to):
            if d:
                date.fromisoformat(d)
        if not self.menu_ids and not self.article_urls:
            raise ValueError("수집할 게시판 또는 게시글 URL을 지정하세요.")


@dataclass
class JobCounters:
    success: int = 0
    restricted: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def processed(self) -> int:
        return self.success + self.restricted + self.failed


class StopRequested(Exception):
    pass


class Collector:
    def __init__(self, settings: Settings, repo: Repository, fetcher: Fetcher,
                 progress: Callable[[str], None] | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.settings = settings
        self.repo = repo
        self.fetcher = fetcher
        self.progress = progress or (lambda msg: None)
        self.sleep = sleep
        self.limiter = RateLimiter(settings.delay_min, settings.delay_max, sleep=sleep)
        self.cafe_name = settings.cafe_name
        self.job_id: int | None = None
        self.counters = JobCounters()
        self._started_logged_in = False

    # ---------- logging ----------
    def _log(self, level: str, msg: str) -> None:
        getattr(log, level.lower(), log.info)(msg)
        self.repo.add_log(self.job_id, level.upper(), msg)
        self.progress(msg)

    # ---------- fetch with safety checks ----------
    def _fetch(self, url: str, wait: list[str] | None) -> FetchResult:
        self.limiter.wait()

        def attempt() -> FetchResult:
            res = self.fetcher.fetch(url, wait)
            if res.status == 429:
                raise BlockedError(f"HTTP 429(요청 과다) 응답: {url}")
            if res.status is not None and res.status >= 500:
                raise TransientError(f"HTTP {res.status}: {url}")
            return res

        return with_retry(attempt, self.settings.max_retries,
                          self.settings.retry_backoff_seconds, sleep=self.sleep)

    def _guard(self, res: FetchResult, status: AccessStatus) -> None:
        if status == AccessStatus.CAPTCHA:
            raise CaptchaDetectedError(
                "보안 확인(자동입력 방지) 화면이 나타났습니다. 수집을 중단합니다. "
                "브라우저에서 직접 확인을 완료한 뒤 충분한 시간이 지나고 다시 실행하세요.")
        if status == AccessStatus.BLOCKED:
            raise BlockedError(f"차단 또는 접근 거부 응답(HTTP {res.status}). 수집을 중단합니다.")
        if status == AccessStatus.LOGIN_REQUIRED and self._started_logged_in \
                and not self.fetcher.is_logged_in():
            raise SessionExpiredError("로그인 세션이 만료되었습니다. 다시 로그인한 뒤 '재개'하세요.")

    def _check_stop(self) -> None:
        if self.job_id is not None and self.repo.is_stop_requested(self.job_id):
            raise StopRequested()

    # ---------- discovery ----------
    def discover_cafe(self, save: bool = True) -> tuple[CafeInfo, list]:
        res = self._fetch(self.settings.cafe_url, None)
        status = self._list_page_guard(res)
        info = parse_cafe_info(res.top_html or res.html, self.cafe_name, self.settings.cafe_url,
                               extra_html=res.html)
        boards = parse_board_list(res.html) or parse_board_list(res.top_html)
        if not boards:
            self._log("WARNING", "게시판 목록을 찾지 못했습니다. 'diagnose' 로 구조를 확인하세요."
                      f" (페이지 상태: {status})")
        if info.club_id is None:
            self._log("WARNING", "카페 숫자 ID(clubid)를 찾지 못했습니다. selectors.py 확인 필요.")
        if save:
            self.repo.upsert_cafe(info)
            if boards:
                self.repo.upsert_boards(self.cafe_name, boards)
        return info, boards

    def _list_page_guard(self, res: FetchResult) -> str:
        """목록/메인 페이지에서 CAPTCHA·차단 여부만 확인."""
        if res.status in (403, 429):
            raise BlockedError(f"HTTP {res.status} 응답. 수집을 중단합니다.")
        from crawler.parse_utils import make_soup, select_first
        for html in (res.html, res.top_html):
            if html and select_first(make_soup(html), S.CAPTCHA_SELECTORS):
                self._guard(res, AccessStatus.CAPTCHA)
        return f"HTTP {res.status}"

    def _club_id(self) -> str:
        cafe = self.repo.get_cafe(self.cafe_name)
        if cafe and cafe.get("club_id"):
            return cafe["club_id"]
        info, _ = self.discover_cafe()
        if not info.club_id:
            raise CrawlerError("카페 ID를 확인할 수 없어 게시판을 탐색할 수 없습니다.")
        return info.club_id

    # ---------- main ----------
    def create_job(self, options: CrawlOptions) -> int:
        options.validate()
        return self.repo.create_job(self.cafe_name, options.to_dict())

    def run(self, job_id: int, resume: bool = False) -> dict:
        job = self.repo.get_job(job_id)
        if job is None:
            raise CrawlerError(f"작업 {job_id} 이 없습니다.")
        if job["status"] == "completed" and resume:
            raise CrawlerError("이미 완료된 작업입니다.")
        self.job_id = job_id
        options = CrawlOptions.from_dict(job["params"])
        options.validate()
        if resume:
            self.counters = JobCounters(job["success_count"] or 0, job["restricted_count"] or 0,
                                        job["failed_count"] or 0, job["skipped_count"] or 0)
        resume_menu = job.get("current_menu_id") if resume else None
        resume_page = job.get("current_page") if resume else None
        import os
        self.repo.update_job(job_id, status="running", stop_requested=0, pid=os.getpid(),
                             message="수집 중", finished_at=None)

        final_status, message = "completed", "수집 완료"
        try:
            self._started_logged_in = self.fetcher.is_logged_in()
            if not self._started_logged_in:
                self._log("WARNING", "비로그인 상태입니다. 공개 게시글만 수집되며, "
                                     "제한된 글은 '접근 제한'으로 기록됩니다.")
            for url in options.article_urls:
                self._check_stop()
                if self._reached_max(options):
                    break
                self._process_direct_url(url, options)

            menu_ids = list(options.menu_ids)
            if resume_menu is not None and resume_menu in menu_ids:
                menu_ids = menu_ids[menu_ids.index(resume_menu):]
            for menu_id in menu_ids:
                if self._reached_max(options):
                    break
                start = resume_page if (resume_menu == menu_id and resume_page) else options.start_page
                self._crawl_board(menu_id, start, options)
            if self._reached_max(options):
                message = f"최대 수집 건수({options.max_articles}) 도달"
        except StopRequested:
            final_status, message = "stopped", "사용자 요청으로 중지됨 (재개 가능)"
        except KeyboardInterrupt:
            final_status, message = "stopped", "중단됨 (재개 가능)"
        except CaptchaDetectedError as exc:
            final_status, message = "captcha", str(exc)
        except BlockedError as exc:
            final_status, message = "blocked", f"{exc} 충분한 시간(수 시간 이상) 후 재개하세요."
        except SessionExpiredError as exc:
            final_status, message = "session_expired", str(exc)
        except Exception as exc:  # noqa: BLE001
            log.exception("수집 중 오류")
            final_status, message = "failed", f"오류: {exc}"
        self._log("INFO" if final_status == "completed" else "WARNING",
                  f"[작업 {job_id}] {message} | 성공 {self.counters.success}, "
                  f"제한 {self.counters.restricted}, 실패 {self.counters.failed}, "
                  f"건너뜀 {self.counters.skipped}")
        assert final_status in FINAL_JOB_STATUSES
        self._save_counters(status=final_status, message=message,
                            finished_at=datetime.now().isoformat(timespec="seconds"))
        return {"status": final_status, "message": message, **asdict(self.counters)}

    def _save_counters(self, **extra) -> None:
        if self.job_id is None:
            return
        self.repo.update_job(self.job_id, success_count=self.counters.success,
                             restricted_count=self.counters.restricted,
                             failed_count=self.counters.failed,
                             skipped_count=self.counters.skipped, **extra)

    def _reached_max(self, options: CrawlOptions) -> bool:
        return self.counters.processed >= options.max_articles

    # ---------- board ----------
    def _board_name(self, menu_id: int) -> str | None:
        for b in self.repo.list_boards(self.cafe_name):
            if b["menu_id"] == menu_id:
                return b["name"]
        return None

    def _crawl_board(self, menu_id: int, start_page: int, options: CrawlOptions) -> None:
        club_id = self._club_id()
        board_name = self._board_name(menu_id)
        threshold = self.repo.max_article_id(self.cafe_name, menu_id) if options.only_new else None
        if options.only_new:
            self._log("INFO", f"[게시판 {menu_id}] 신규 글만 수집 (기준 게시글ID > {threshold})")
        previous_ids: set[int] = set()
        for page in range(start_page, options.end_page + 1):
            self._check_stop()
            if self._reached_max(options):
                return
            self.repo.update_job(self.job_id, current_menu_id=menu_id, current_page=page)
            if options.use_site_search and options.keyword:
                url = build_search_url(self.settings, club_id, menu_id, options.keyword, page)
            else:
                url = build_list_url(self.settings, club_id, menu_id, page)
            self._log("INFO", f"[게시판 {board_name or menu_id}] {page}페이지 목록 확인")
            try:
                res = self._fetch(url, S.LIST_WAIT_SELECTORS)
            except TransientError as exc:
                self._log("ERROR", f"목록 페이지 실패(재시도 초과), 다음 게시판으로: {exc}")
                return
            self._list_page_guard(res)
            items = parse_article_list(res.html)
            articles = regular_articles(items)
            if not items:
                status = detect_access_status(res)
                if status.is_restricted:
                    self._log("WARNING", f"[게시판 {menu_id}] 목록 접근 제한({status.value}). 건너뜁니다.")
                elif page == start_page:
                    self._log("WARNING", f"[게시판 {menu_id}] 게시글을 찾지 못했습니다. "
                                         "구조 변경 가능성 → diagnose 실행 권장")
                return
            ids = {a.article_id for a in articles}
            if not articles or ids == previous_ids:
                self._log("INFO", f"[게시판 {menu_id}] 마지막 페이지 도달")
                return
            previous_ids = ids
            # 공지는 페이지마다 반복되므로 첫 페이지에서만 처리
            candidates = articles + ([i for i in items if i.is_notice] if page == start_page else [])
            stop_board = False
            for summary in candidates:
                self._check_stop()
                if self._reached_max(options):
                    return
                if threshold is not None and summary.article_id <= threshold:
                    if not summary.is_notice:
                        stop_board = True
                    continue
                if not self._passes_list_filters(summary, options):
                    if self._older_than_range(summary, options) and not summary.is_notice:
                        stop_board = True
                    continue
                self._process_article(summary.article_id, menu_id, board_name, summary, options,
                                      club_id)
            if stop_board:
                self._log("INFO", f"[게시판 {menu_id}] 기준 시점/기간 이전 글에 도달하여 종료")
                return

    # ---------- filters ----------
    @staticmethod
    def _date_part(value: str | None) -> str | None:
        return value[:10] if value else None

    def _older_than_range(self, s: ArticleSummary, o: CrawlOptions) -> bool:
        d = self._date_part(s.written_at)
        return bool(o.date_from and d and d < o.date_from)

    def _passes_list_filters(self, s: ArticleSummary, o: CrawlOptions) -> bool:
        d = self._date_part(s.written_at)
        if o.date_from and d and d < o.date_from:
            return False
        if o.date_to and d and d > o.date_to:
            return False
        if o.keyword and o.keyword_scope == "title" and not o.use_site_search:
            if o.keyword.lower() not in (s.title or "").lower():
                return False
        return True

    def _passes_detail_filters(self, title: str | None, body: str | None, written: str | None,
                               o: CrawlOptions) -> bool:
        d = self._date_part(written)
        if o.date_from and d and d < o.date_from:
            return False
        if o.date_to and d and d > o.date_to:
            return False
        if o.keyword and not o.use_site_search:
            kw = o.keyword.lower()
            t, b = (title or "").lower(), (body or "").lower()
            hit = {"title": kw in t, "body": kw in b, "both": kw in t or kw in b}[o.keyword_scope]
            return hit
        return True

    # ---------- article ----------
    def _process_direct_url(self, url: str, options: CrawlOptions) -> None:
        info = parse_article_url(url, self.cafe_name)
        if info["article_id"] is None:
            self._log("ERROR", f"게시글 URL을 해석할 수 없습니다: {url}")
            self.counters.failed += 1
            return
        if info["cafe_name"] and info["cafe_name"] != self.cafe_name:
            self._log("WARNING", f"다른 카페의 URL은 건너뜁니다: {url}")
            self.counters.skipped += 1
            return
        self._process_article(info["article_id"], None, None, None, options, info["club_id"],
                              direct_url=url, apply_filters=False)

    def _should_skip(self, article_id: int, options: CrawlOptions) -> bool:
        status = self.repo.get_article_status(self.cafe_name, article_id)
        if status is None:
            return False
        if status in ("ok", "not_found"):
            return True
        if status in ("members_only", "level_restricted", "login_required"):
            return not options.recheck_restricted
        return False  # failed / unknown_structure 는 재시도

    def _process_article(self, article_id: int, menu_id: int | None, board_name: str | None,
                         summary: ArticleSummary | None, options: CrawlOptions,
                         club_id: str | None, direct_url: str | None = None,
                         apply_filters: bool = True) -> None:
        if self._should_skip(article_id, options):
            self.counters.skipped += 1
            self._save_counters()
            return
        url = direct_url or build_article_url(self.settings, article_id, club_id)
        record = {"cafe_name": self.cafe_name, "club_id": club_id, "menu_id": menu_id,
                  "board_name": board_name, "article_id": article_id, "url": url,
                  "job_id": self.job_id}
        if summary:
            record.update(title=summary.title or None, author=summary.author,
                          written_at=summary.written_at, view_count=summary.view_count,
                          comment_count=summary.comment_count)
        try:
            res = self._fetch(url, S.DETAIL_WAIT_SELECTORS)
        except TransientError as exc:
            record.update(access_status=AccessStatus.FAILED.value, error_message=str(exc)[:500])
            self.repo.save_article(record)
            self.counters.failed += 1
            self._log("ERROR", f"게시글 {article_id} 수집 실패: {exc}")
            self._save_counters()
            return
        status = detect_access_status(res)
        self._guard(res, status)
        if status != AccessStatus.OK:
            record.update(access_status=status.value,
                          error_message=("; ".join(res.dialogs) or None))
            if status == AccessStatus.UNKNOWN_STRUCTURE:
                self.counters.failed += 1
                self._log("ERROR", f"게시글 {article_id}: 본문 요소를 찾지 못함(구조 변경 의심)")
            elif status == AccessStatus.NOT_FOUND:
                self.counters.skipped += 1
                self._log("INFO", f"게시글 {article_id}: 삭제되었거나 없는 글")
            else:
                self.counters.restricted += 1
                self._log("INFO", f"게시글 {article_id}: 접근 제한({status.value}) - 수집하지 않음")
            self.repo.save_article(record)
            self._save_counters()
            return

        detail = parse_article(res.html, include_html=options.save_html,
                               include_comments=options.include_comments)
        title = detail.title or record.get("title")
        written = detail.written_at or record.get("written_at")
        if apply_filters and not self._passes_detail_filters(title, detail.content_text, written,
                                                             options):
            self.counters.skipped += 1
            self._save_counters()
            return
        record.update(
            title=title, content_text=detail.content_text, content_html=detail.content_html,
            author=detail.author or record.get("author"), written_at=written,
            view_count=detail.view_count if detail.view_count is not None else record.get("view_count"),
            comment_count=(detail.comment_count if detail.comment_count is not None
                           else record.get("comment_count")),
            board_name=board_name or detail.board_name,
            image_urls=detail.image_urls, attachments=detail.attachments,
            access_status=AccessStatus.OK.value, error_message=None)
        self.repo.save_article(record)
        if options.include_comments and detail.comments:
            self.repo.save_comments(self.cafe_name, article_id, detail.comments)
        if options.download_media:
            self._download_media(article_id, detail.image_urls)
        self.counters.success += 1
        self._log("INFO", f"게시글 {article_id} 저장: {(title or '')[:40]}")
        self._save_counters()

    def _download_media(self, article_id: int, urls: list[str]) -> None:
        if not self.settings.media_download_policy_confirmed:
            self._log("WARNING", "MEDIA_DOWNLOAD_POLICY_CONFIRMED=false 이므로 이미지 다운로드를 건너뜁니다.")
            return
        for idx, url in enumerate(urls, start=1):
            ext = Path(url.split("?")[0]).suffix[:5] or ".jpg"
            dest = self.settings.media_dir / self.cafe_name / str(article_id) / f"{idx:03d}{ext}"
            if dest.exists():
                continue
            self.limiter.wait()
            try:
                self.fetcher.download(url, dest)
            except Exception as exc:  # noqa: BLE001
                self._log("WARNING", f"이미지 다운로드 실패({article_id}): {exc}")

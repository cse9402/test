"""수집 엔진 시나리오 테스트 (Mock Fetcher 사용 — 실제 사이트 접속 없음)."""
from pathlib import Path

import pytest

from conftest import load_fixture
from crawler.collector import Collector, CrawlOptions
from crawler.types import Board, CafeInfo, FetchResult, TransientError

LIST1 = "https://cafe.naver.com/ArticleList.nhn?search.clubid=12345678&search.menuid=5&search.boardtype=L&search.page=1"
LIST2 = LIST1.replace("page=1", "page=2")
LIST3 = LIST1.replace("page=1", "page=3")


def art(aid):
    return f"https://cafe.naver.com/testcafe/{aid}"


class FakeFetcher:
    def __init__(self, pages: dict, logged_in=True):
        self.pages = pages          # url -> html | FetchResult | Exception | list(순차 응답)
        self.logged_in = logged_in
        self.calls: list[str] = []
        self.on_fetch = None

    def fetch(self, url, wait_selectors=None):
        self.calls.append(url)
        if self.on_fetch:
            self.on_fetch(url)
        value = self.pages.get(url, "<html><body></body></html>")
        if isinstance(value, list):
            value = value.pop(0) if len(value) > 1 else value[0]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, FetchResult):
            return value
        return FetchResult(url=url, final_url=url, status=200, html=value, top_html=value)

    def is_logged_in(self):
        return self.logged_in

    def download(self, url, dest: Path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"img")
        return dest


def restricted(url, msg="등급이 되시면 읽기가 가능한 게시판입니다."):
    return FetchResult(url=url, final_url=url, status=200, html="<html><body></body></html>",
                       dialogs=[msg])


def article_html(title, body="본문", date="2024.05.10. 10:00"):
    return (f"<html><body><h3 class='title_text'>{title}</h3><span class='nickname'>작성자</span>"
            f"<div class='article_info'><span class='date'>{date}</span><span class='count'>조회 5</span></div>"
            f"<div class='se-main-container'><p>{body}</p></div></body></html>")


@pytest.fixture
def base_pages():
    return {
        LIST1: load_fixture("board_list.html"),
        LIST2: load_fixture("board_list_page2.html"),
        art(100): article_html("카페 이용 규칙 안내", date="2023.01.01. 09:00"),
        art(5003): load_fixture("article_ok.html"),
        art(5002): restricted(art(5002)),
        art(5001): article_html("등산화 사이즈 질문", body="270mm 고민", date="2023.12.20. 08:00"),
        art(4999): article_html("랜턴 추천", body="LED 랜턴", date="2023.11.02. 08:00"),
    }


def make(settings, repo, fetcher):
    repo.upsert_cafe(CafeInfo("testcafe", "12345678", "테스트", settings.cafe_url))
    repo.upsert_boards("testcafe", [Board(5, "자유게시판")])
    return Collector(settings, repo, fetcher, sleep=lambda s: None)


def run(col, **opts):
    jid = col.create_job(CrawlOptions(**opts))
    return jid, col.run(jid)


def test_login_user_collects_and_records_restricted(settings, repo, base_pages):  # 시나리오 2·3·5·9
    col = make(settings, repo, FakeFetcher(base_pages))
    jid, result = run(col, menu_ids=[5], start_page=1, end_page=3, max_articles=50,
                      include_comments=True)
    assert result["status"] == "completed"
    # 3페이지: 기본 빈 페이지 → 목록 없음으로 종료
    assert result["success"] == 4 and result["restricted"] == 1
    assert repo.get_article_status("testcafe", 5002) == "level_restricted"
    rows = {r["article_id"]: r for r in repo.query_articles("testcafe")}
    assert rows[5002]["content_text"] is None  # 제한 글 본문 미수집
    assert rows[5003]["board_name"] == "자유게시판" and "2인용" in rows[5003]["content_text"]
    assert len(repo.query_comments("testcafe", 5003)) == 2
    assert repo.get_job(jid)["status"] == "completed"


def test_public_access_without_login(settings, repo, base_pages):  # 시나리오 1
    base_pages[art(5003)] = FetchResult(art(5003), art(5003), 200,
                                        load_fixture("article_members_only.html"))
    col = make(settings, repo, FakeFetcher(base_pages, logged_in=False))
    _, result = run(col, menu_ids=[5], end_page=1)
    assert result["status"] == "completed"
    assert repo.get_article_status("testcafe", 5003) == "members_only"
    assert repo.get_article_status("testcafe", 5001) == "ok"


def test_session_expired_stops_job(settings, repo, base_pages):  # 시나리오 4
    fetcher = FakeFetcher(base_pages)
    login_page = FetchResult(art(5002), "https://nid.naver.com/nidlogin.login?url=x", 200, "<html/>")
    base_pages[art(5002)] = login_page

    def expire(url):
        if url == art(5002):
            fetcher.logged_in = False
    fetcher.on_fetch = expire
    col = make(settings, repo, fetcher)
    jid, result = run(col, menu_ids=[5], end_page=2)
    assert result["status"] == "session_expired"
    assert repo.get_job(jid)["current_page"] == 1
    assert art(5001) not in fetcher.calls  # 만료 후 더 이상 요청하지 않음


def test_duplicate_skip_on_rerun(settings, repo, base_pages):  # 시나리오 7
    fetcher = FakeFetcher(base_pages)
    col = make(settings, repo, fetcher)
    run(col, menu_ids=[5], end_page=2)
    fetcher.calls.clear()
    col2 = make(settings, repo, fetcher)
    _, result = run(col2, menu_ids=[5], end_page=2)
    assert result["success"] == 0 and result["skipped"] == 5
    assert not any(c.startswith("https://cafe.naver.com/testcafe/") for c in fetcher.calls)


def test_retry_then_success_and_exhaustion(settings, repo, base_pages):  # 시나리오 8
    base_pages[art(5003)] = [TransientError("timeout"), load_fixture("article_ok.html")]
    base_pages[art(5001)] = TransientError("network down")
    fetcher = FakeFetcher(base_pages)
    col = make(settings, repo, fetcher)
    _, result = run(col, menu_ids=[5], end_page=1)
    assert repo.get_article_status("testcafe", 5003) == "ok"
    assert fetcher.calls.count(art(5003)) == 2
    assert fetcher.calls.count(art(5001)) == 1 + settings.max_retries
    assert repo.get_article_status("testcafe", 5001) == "failed"
    assert result["failed"] == 1


def test_http_429_stops_immediately(settings, repo, base_pages):
    base_pages[art(5003)] = FetchResult(art(5003), art(5003), 429, "")
    fetcher = FakeFetcher(base_pages)
    _, result = run(make(settings, repo, fetcher), menu_ids=[5], end_page=2)
    assert result["status"] == "blocked"
    assert art(5002) not in fetcher.calls


def test_captcha_stops(settings, repo, base_pages):
    base_pages[art(5003)] = load_fixture("captcha.html")
    _, result = run(make(settings, repo, FakeFetcher(base_pages)), menu_ids=[5], end_page=1)
    assert result["status"] == "captcha"


def test_only_new_since_last_crawl(settings, repo, base_pages):
    repo.save_article({"cafe_name": "testcafe", "menu_id": 5, "article_id": 5002,
                       "access_status": "ok", "title": "기존"})
    fetcher = FakeFetcher(base_pages)
    _, result = run(make(settings, repo, fetcher), menu_ids=[5], end_page=2, only_new=True)
    assert result["success"] == 1  # 5003 만
    assert LIST2 not in fetcher.calls  # 기준 이전 글 도달 → 다음 페이지 요청 안 함


def test_title_keyword_and_date_filters(settings, repo, base_pages):
    fetcher = FakeFetcher(base_pages)
    _, result = run(make(settings, repo, fetcher), menu_ids=[5], end_page=2, keyword="텐트")
    assert result["success"] == 1 and art(5001) not in fetcher.calls

    fetcher2 = FakeFetcher(base_pages)
    repo2_col = make(settings, repo, fetcher2)
    _, result = run(repo2_col, menu_ids=[5], end_page=2, date_from="2024-01-01",
                    recheck_restricted=False)
    assert LIST2 not in fetcher2.calls  # 기간 이전 글 도달 → 종료


def test_body_keyword_filter(settings, repo, base_pages):
    _, result = run(make(settings, repo, FakeFetcher(base_pages)), menu_ids=[5], end_page=2,
                    keyword="랜턴", keyword_scope="body")
    assert repo.get_article_status("testcafe", 4999) == "ok"
    assert repo.get_article_status("testcafe", 5001) is None  # 본문 불일치 → 저장 안 함


def test_max_articles_and_stop_and_resume(settings, repo, base_pages):
    fetcher = FakeFetcher(base_pages)
    _, result = run(make(settings, repo, fetcher), menu_ids=[5], end_page=2, max_articles=2)
    assert result["success"] + result["restricted"] == 2

    fetcher2 = FakeFetcher(base_pages)
    col = make(settings, repo, fetcher2)
    jid = col.create_job(CrawlOptions(menu_ids=[5], start_page=1, end_page=2, recheck_restricted=True))

    def stop_on(url):
        if url == LIST2:
            repo.request_stop(jid)
    fetcher2.on_fetch = stop_on
    result = col.run(jid)
    assert result["status"] == "stopped"
    job = repo.get_job(jid)
    assert job["current_page"] == 2
    fetcher2.on_fetch = None
    result = make(settings, repo, fetcher2).run(jid, resume=True)
    assert result["status"] == "completed"
    assert repo.get_article_status("testcafe", 4999) == "ok"


def test_direct_article_urls(settings, repo, base_pages):
    _, result = run(make(settings, repo, FakeFetcher(base_pages)),
                    article_urls=[art(5003), "https://cafe.naver.com/othercafe/1", "bad-url"])
    assert result["success"] == 1 and result["skipped"] == 1 and result["failed"] == 1


def test_media_download_requires_policy_flag(settings, repo, base_pages, tmp_path):
    from dataclasses import replace
    run(make(settings, repo, FakeFetcher(base_pages)), article_urls=[art(5003)],
        download_media=True)
    assert not (settings.media_dir / "testcafe").exists()
    from database.repository import Repository
    s2 = replace(settings, media_download_policy_confirmed=True)
    col = Collector(s2, Repository(tmp_path / "media.db"), FakeFetcher(base_pages),
                    sleep=lambda s: None)
    jid = col.create_job(CrawlOptions(article_urls=[art(5003)], download_media=True))
    col.run(jid)
    assert len(list((s2.media_dir / "testcafe" / "5003").iterdir())) == 2


def test_discover_cafe(settings, repo):
    pages = {settings.cafe_url: load_fixture("cafe_main.html")}
    col = Collector(settings, repo, FakeFetcher(pages), sleep=lambda s: None)
    info, boards = col.discover_cafe()
    assert info.club_id == "12345678" and len(boards) == 4
    assert repo.get_cafe("testcafe")["club_id"] == "12345678"


def test_options_validation():
    with pytest.raises(ValueError):
        CrawlOptions().validate()
    with pytest.raises(ValueError):
        CrawlOptions(menu_ids=[1], start_page=3, end_page=1).validate()
    with pytest.raises(ValueError):
        CrawlOptions(menu_ids=[1], date_from="2024-13-01").validate()

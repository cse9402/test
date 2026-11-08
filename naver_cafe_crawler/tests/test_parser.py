"""파서 단위 테스트 (가상 HTML Fixture 기반 — 실제 사이트 검증 아님)."""
from datetime import datetime

from conftest import load_fixture
from crawler.article_parser import detect_access_status, parse_article
from crawler.board_parser import parse_article_list, regular_articles
from crawler.cafe_parser import is_join_required, parse_board_list, parse_cafe_info
from crawler.parse_utils import parse_int, parse_naver_datetime
from crawler.types import AccessStatus, FetchResult
from crawler.urls import parse_article_url

NOW = datetime(2024, 6, 1, 18, 0)


def fr(html, dialogs=None, final_url="https://cafe.naver.com/testcafe/1", status=200):
    return FetchResult(url=final_url, final_url=final_url, status=status, html=html,
                       top_html="", dialogs=dialogs or [])


def test_cafe_info_and_boards():
    html = load_fixture("cafe_main.html")
    info = parse_cafe_info(html, "testcafe", "https://cafe.naver.com/testcafe")
    assert info.club_id == "12345678"
    assert info.title == "테스트 아웃도어 카페"
    boards = parse_board_list(html)
    assert [(b.menu_id, b.name) for b in boards] == [
        (1, "공지사항"), (5, "자유게시판"), (9, "등업게시판"), (12, "장비후기")]
    assert is_join_required(html)


def test_article_list_legacy_table():  # 시나리오 5: 게시판 페이지 데이터
    items = parse_article_list(load_fixture("board_list.html"), now=NOW)
    by_id = {i.article_id: i for i in items}
    assert set(by_id) == {100, 5003, 5002, 5001}
    assert by_id[100].is_notice and not by_id[5003].is_notice
    a = by_id[5003]
    assert a.title == "텐트 추천 부탁드립니다"
    assert a.author == "캠핑초보"
    assert a.written_at == "2024-06-01T13:45"
    assert a.view_count == 120 and a.comment_count == 3
    assert by_id[5002].view_count == 12000
    assert [x.article_id for x in regular_articles(items)] == [5003, 5002, 5001]


def test_article_list_new_ui():
    items = parse_article_list(load_fixture("board_list_newui.html"), now=NOW)
    assert [(i.article_id, i.title, i.author, i.view_count) for i in items] == [
        (7002, "새 UI 게시글 2", "새유저", 33), (7001, "새 UI 게시글 1", "옛유저", 7)]


def test_parse_article_detail():  # 시나리오 6
    d = parse_article(load_fixture("article_ok.html"), include_html=True, include_comments=True)
    assert d.title == "텐트 추천 부탁드립니다"
    assert d.author == "캠핑초보"
    assert d.written_at == "2024-05-10T13:45"
    assert d.view_count == 120 and d.comment_count == 2
    assert d.board_name == "자유게시판"
    assert "2인용 텐트" in d.content_text and "evil" not in d.content_text
    assert d.content_html.startswith("<div")
    assert d.image_urls == ["https://cafeptthumb-phinf.pstatic.net/test/1.jpg",
                            "https://cafeptthumb-phinf.pstatic.net/test/2.jpg"]
    assert d.attachments[0]["name"] == "캠핑장목록.xlsx"
    assert [(c.comment_key, c.author, c.is_reply) for c in d.comments] == [
        ("c-1", "산사람", False), ("c-2", "캠핑초보", True)]


def test_access_status_detection():  # 시나리오 1·2·3
    assert detect_access_status(fr(load_fixture("article_ok.html"))) == AccessStatus.OK
    # 본문 안에 '등급 이상' 문구가 있어도 본문 요소가 있으면 OK
    assert detect_access_status(fr(load_fixture("article_members_only.html"))) \
        == AccessStatus.MEMBERS_ONLY
    assert detect_access_status(fr(load_fixture("article_empty.html"),
                                   dialogs=["등급이 되시면 읽기가 가능한 게시판입니다."])) \
        == AccessStatus.LEVEL_RESTRICTED
    assert detect_access_status(fr(load_fixture("article_deleted.html"))) == AccessStatus.NOT_FOUND
    assert detect_access_status(fr(load_fixture("captcha.html"))) == AccessStatus.CAPTCHA
    assert detect_access_status(fr("<html></html>",
                                   final_url="https://nid.naver.com/nidlogin.login?url=x")) \
        == AccessStatus.LOGIN_REQUIRED
    assert detect_access_status(fr(load_fixture("article_empty.html"))) \
        == AccessStatus.UNKNOWN_STRUCTURE
    assert detect_access_status(fr("", status=429)) == AccessStatus.BLOCKED


def test_date_and_number_parsing():
    assert parse_naver_datetime("2024.05.01. 13:45", NOW) == "2024-05-01T13:45"
    assert parse_naver_datetime("2024.05.01.", NOW) == "2024-05-01"
    assert parse_naver_datetime("24.05.01", NOW) == "2024-05-01"
    assert parse_naver_datetime("09:30", NOW) == "2024-06-01T09:30"
    assert parse_naver_datetime("5분 전", NOW) == "2024-06-01T17:55"
    assert parse_naver_datetime("어제", NOW) == "2024-05-31"
    assert parse_naver_datetime("", NOW) is None
    assert parse_int("조회 1,234") == 1234 and parse_int("[3]") == 3 and parse_int(None) is None


def test_parse_article_url_variants():
    assert parse_article_url("https://cafe.naver.com/adoutdoor/12345") == {
        "article_id": 12345, "club_id": None, "cafe_name": "adoutdoor"}
    r = parse_article_url("https://cafe.naver.com/ArticleRead.nhn?clubid=111&articleid=222")
    assert r["article_id"] == 222 and r["club_id"] == "111"
    r = parse_article_url("https://cafe.naver.com/f-e/cafes/111/articles/333?menuid=5", "adoutdoor")
    assert r == {"article_id": 333, "club_id": "111", "cafe_name": "adoutdoor"}
    assert parse_article_url("https://example.com/nothing")["article_id"] is None
